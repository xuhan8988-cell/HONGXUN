# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 六级摘要补全流水线
版本 1.0.0
"""

import re
import html
import threading
from .session import _session

_enrich_lock = threading.Lock()


def _clean_abstract(text: str) -> str:
    """清理从网页提取的摘要中的乱码和标签

    处理以下垃圾内容：
    - <mml:math>...</mml:math>  MathML 数学公式 XML 标签（含嵌套）
    - ![Image N: text](url)  ScienceDirect 图片占位
    - $...$ / $$...$$  LaTeX 数学符号
    - <sub> / <sup> / <em> 等行内 HTML 标签
    - 文章导航文字（"Previous article in issue" 等）
    - 多余空白符
    """
    if not text:
        return text
    # 彻底移除所有 MathML 整块（含内部所有文本内容）
    # 用计数器方式匹配 <mml:math> ... </mml:math> 完整块
    def _remove_mathml_blocks(s):
        parts = []
        i = 0
        while True:
            start = s.find('<mml:math', i)
            if start == -1:
                parts.append(s[i:])
                break
            parts.append(s[i:start])
            end_tag = '</mml:math>'
            end = s.find(end_tag, start)
            if end == -1:
                break
            i = end + len(end_tag)
        return ''.join(parts)
    text = _remove_mathml_blocks(text)
    # 兜底：清理零散 mml: 残留标签
    text = re.sub(r'<mml:[^>]*>[^<]*</mml:[^>]*>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<mml:[^>]*/>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<mml:[^>]+>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</mml:[^>]+>', '', text, flags=re.IGNORECASE)
    # 移除外层包装 namespace 声明
    text = re.sub(r'xmlns:mml="[^"]*"', '', text)
    # 清理来自 MathML 的残留数学文本（大写字母+数字组合，在括号中）
    # 如 "(LC3)" → 移除
    text = re.sub(r'\(\s*[A-Z0-9]{1,6}\s*\)', '', text)
    # 移除 ![Image N: ...](url) 图片标记
    text = re.sub(r'!\[Image\s*\d*[^\]]*\]\([^)]*\)', '', text)
    # 移除 MathML 替代文本标记（如 "LC3" 在标签内的文本被保留后可能出现孤立数字/符号）
    # 移除 $...$ 和 $$...$$ LaTeX 数学
    text = re.sub(r'\$\$[^$]*\$\$', '', text)
    text = re.sub(r'\$[^$]*\$', '', text)
    # 移除行内 HTML 标签（保留内容）
    text = re.sub(r'<[^>]+>', '', text)
    # 移除 ScienceDirect 导航文字（含 markdown 链接格式 [text](url)）
    text = re.sub(
        r'(?i)\s*\*?\s*\[(Previous article in issue|Next article in issue|View PDF|Article preview|Download full text|Export)\][^)\]]*\)\s*',
        '', text)
    # 移除 "Research article Open access / Abstract only" 等分类标签
    text = re.sub(r'(?im)^\s*\d+\.\s*-\s*\[[x\s]\]\s+select article\s+.*$', '', text)
    text = re.sub(r'(?im)^\s*(Research article|Review article|Short communication|Open access|Abstract only)\s*.*$', '', text)
    # 移除 cookie 声明和页脚
    text = re.sub(r'(?im)(Strictly Necessary Cookies|Functional Cookies|These cookies are necessary).*$', '', text)
    text = re.sub(r'(?im)(Copyright © 202\d|Elsevier|ScienceDirect|Add to Mendeley|Complimentary|Show more|Author links|Skip to main content).*$', '', text)
    # 移除末尾的"更多"、"...更多"、"…更多"、"Show more"等展开按钮残留
    text = re.sub(r'[\s\.\,\;]*[…\.]{2,}?\s*更多\s*$', '', text)
    text = re.sub(r'[\s\.\,\;]*More\s*$', '', text, flags=re.IGNORECASE)
    # 移除末尾的"Read more"、"View full text"等截断提示
    text = re.sub(r'[\s\.\,\;]*(Read more|View full text|Full Text|View PDF|Download full text)\s*$', '', text, flags=re.IGNORECASE)
    # 移除多余空行和首尾空白
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _search_abstract_from_web(title: str, doi: str = "") -> str:
    """通过 Tavily 搜索引擎检索论文标题/DOI，从搜索结果摘要中提取文本（第6级）"""
    TAVILY_KEY = "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"

    clean_doi = re.sub(r'[<>"\'&|!(){}^~*?:\\]', ' ', doi).strip() if doi else ""
    clean_title = re.sub(r'[<>"\'&|!(){}^~*?:\\]', ' ', title)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    if len(clean_title) > 120:
        clean_title = clean_title[:120]

    pii = ""
    if clean_doi:
        pii = clean_doi.split("/")[-1] if "/" in clean_doi else clean_doi

    # 策略 A：Tavily extract + doi.org 重定向获取正确的 ScienceDirect PII（限时15s）
    if clean_doi:
        sd_abs_url = None
        try:
            doi_resp = _session.get(
                f"https://doi.org/{clean_doi}",
                allow_redirects=False,
                timeout=8,
            )
            if doi_resp.status_code in (302, 303, 307):
                loc = doi_resp.headers.get("Location", "")
                if "pii/" in loc:
                    actual_pii = loc.split("pii/")[-1].split("?")[0].split("#")[0]
                    if actual_pii.startswith("S") and len(actual_pii) > 10:
                        sd_abs_url = (
                            f"https://www.sciencedirect.com/science/article/abs/pii/{actual_pii}"
                        )
        except Exception:
            pass

        if sd_abs_url:
            try:
                ext_resp = _session.post(
                    "https://api.tavily.com/extract",
                    json={"api_key": TAVILY_KEY, "urls": [sd_abs_url], "extract_depth": "advanced"},
                    timeout=15,
                )
                if ext_resp.status_code == 200:
                    ext_data = ext_resp.json()
                    results = ext_data.get("results", [])
                    if results:
                        raw_content = results[0].get("raw_content", "")
                        if raw_content:
                            for sep in [
                                r'##\s*Abstract\s*\n(.*?)(?=\n##\s*Keywords|\n1\.\s*Introduction|\n##\s+1\.)',
                                r'Abstract\s*\n(.*?)(?=\nKeywords\n|\n1\.\s+Introduction|\n1\.\s+)',
                                r'##\s*Abstract\s*\n(.*?)(?=\n##\s+\d+\.)',
                            ]:
                                m = re.search(sep, raw_content, re.DOTALL)
                                if m:
                                    abstract = m.group(1).strip()
                                    abstract = re.sub(r'\s+', ' ', abstract).strip()
                                    if 100 < len(abstract) < 10000:
                                        return _clean_abstract(abstract)

                            blocks = re.findall(r'\n{2,}([A-Z][^\n]{200,}?)\n', raw_content)
                            for block in blocks:
                                block = re.sub(r'\s+', ' ', block).strip()
                                if 100 < len(block) < 10000:
                                    kw_hits = sum(1 for kw in
                                        ["study","research","investigat","experiment",
                                         "paper","method","result","analysis"]
                                        if kw in block.lower())
                                    if kw_hits >= 2 and 100 < len(block) < 10000:
                                        return _clean_abstract(block)
            except Exception:
                pass

    # 策略 B：Tavily search
    seen_snippets = set()
    queries = []
    if clean_doi:
        queries.append(clean_doi)
    if clean_title:
        queries.append(clean_title)

    for query in queries:
        if not query or len(query) < 8:
            continue
        try:
            resp = _session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_KEY,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 3,
                    "include_domains": ["sciencedirect.com", "researchgate.net", "semanticscholar.org"],
                },
                timeout=12,
            )
            if resp.status_code != 200:
                continue

            data = resp.json()
            results = data.get("results", [])

            for r in results:
                snippet = r.get("content", "")
                if not snippet or len(snippet) < 50:
                    continue
                snippet = html.unescape(snippet)
                snippet = re.sub(r'\s+', ' ', snippet).strip()
                snippet = re.sub(r'^Image\s+\d+:\s*\w+\s*', '', snippet).strip()
                if len(snippet) > 5000 or 'javascript' in snippet[:100].lower():
                    continue

                snippet_key = snippet[:80]
                if snippet_key in seen_snippets:
                    continue
                seen_snippets.add(snippet_key)

                result_url = r.get("url", "")
                has_sd = "sciencedirect" in result_url
                has_rg = "researchgate" in result_url
                has_pii = pii and pii[:8] in snippet

                academic_kw = [
                    "abstract","study","research","investigat","experiment","paper",
                    "method","result","hydration","magnesium","cement","concrete",
                    "gel","synthes","material","carbon","microstructure","mechanism",
                    "property","analysis","effect","process","reaction",
                    "this paper","this research","this study",
                    "we present","we report","we show","we investigate","doi",
                ]
                kw_hits = sum(1 for kw in academic_kw if kw in snippet.lower())

                if has_sd and kw_hits >= 1:
                    clean = re.sub(
                        r'(Copyright © 202\d|Elsevier|ScienceDirect|Add to Mendeley'
                        r'|Share|Cite| rights and content|Complimentary|Outline'
                        r'|Show more|Author links|Skip to main content)',
                        '', snippet, flags=re.IGNORECASE)
                    clean = re.sub(r'\s+', ' ', clean).strip()
                    if clean and len(clean) >= 50:
                        return _clean_abstract(clean)
                if has_rg and kw_hits >= 1:
                    return _clean_abstract(snippet)
                if has_pii and kw_hits >= 2:
                    return _clean_abstract(snippet)
                if len(snippet) >= 100 and kw_hits >= 4:
                    return _clean_abstract(snippet)
                if len(snippet) >= 60 and kw_hits >= 1 and ("doi.org" in snippet or "10.1016" in snippet):
                    clean = re.sub(
                        r'https?://\S+|doi\.org/\S+|Copyright[^.]*\.|Elsevier[^.]*\.',
                        '', snippet, flags=re.IGNORECASE).strip()
                    if len(clean) >= 50:
                        return _clean_abstract(clean)

        except Exception:
            continue

    return ""


def _fetch_openalex(p: dict, doi: str) -> None:
    """第1轮：OpenAlex"""
    try:
        resp = _session.get(
            f"https://api.openalex.org/works/doi:{doi}",
            params={"mailto": "academic-use@example.com"},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            inv_index = data.get("abstract_inverted_index")
            if inv_index:
                words = {}
                for word, positions in inv_index.items():
                    for pos in positions:
                        words[pos] = word
                rebuilt = " ".join(words[i] for i in sorted(words.keys()))
                if rebuilt.strip():
                    rebuilt = re.sub(r'^(Abstract\s*|Abstract\s*\n+)', '', rebuilt, flags=re.IGNORECASE).strip()
                    p["abstract"] = rebuilt
            oa_authors = data.get("authorships", [])
            if oa_authors:
                affs = p.get("affiliations", {})
                for oa_author in oa_authors:
                    name = oa_author.get("author", {}).get("display_name", "")
                    institutions = oa_author.get("institutions", [])
                    if name and institutions:
                        orgs = [inst.get("display_name", "") for inst in institutions if inst.get("display_name")]
                        if orgs:
                            affs[name] = "; ".join(orgs)
                if affs:
                    p["affiliations"] = affs
    except Exception:
        pass


def _fetch_ss_by_doi(p: dict, doi: str) -> None:
    """第2轮：Semantic Scholar（DOI查）"""
    try:
        ss_resp = _session.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params={"fields": "abstract,title"},
            timeout=10
        )
        if ss_resp.status_code == 200:
            ss_data = ss_resp.json()
            ss_abstract = ss_data.get("abstract", "")
            if ss_abstract and ss_abstract.strip():
                p["abstract"] = ss_abstract.strip()
    except Exception:
        pass


def _fetch_ss_by_title(p: dict, title: str) -> None:
    """第3轮：Semantic Scholar（标题搜）"""
    try:
        ss_search = _session.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": title, "limit": 3, "fields": "abstract,title,externalIds"},
            timeout=10
        )
        if ss_search.status_code == 200:
            ss_data = ss_search.json()
            matches = ss_data.get("data", [])
            if matches:
                ss_abstract = matches[0].get("abstract", "")
                if ss_abstract and ss_abstract.strip():
                    p["abstract"] = ss_abstract.strip()
    except Exception:
        pass


def _fetch_pubmed(p: dict, doi: str) -> None:
    """第4轮：PubMed"""
    try:
        pmid_resp = _session.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": f"{doi}[DOI]", "retmode": "json"},
            timeout=10
        )
        if pmid_resp.status_code == 200:
            id_list = pmid_resp.json().get("esearchresult", {}).get("idlist", [])
            if id_list:
                summary_resp = _session.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                    params={"db": "pubmed", "id": id_list[0], "retmode": "xml", "rettype": "abstract"},
                    timeout=10
                )
                if summary_resp.status_code == 200:
                    abstract_matches = re.findall(
                        r'<AbstractText[^>]*>(.*?)</AbstractText>',
                        summary_resp.text, re.DOTALL
                    )
                    if abstract_matches:
                        full_abstract = " ".join(
                            re.sub(r'<[^>]+>', '', m).strip()
                            for m in abstract_matches if m.strip()
                        )
                        if full_abstract:
                            p["abstract"] = full_abstract
    except Exception:
        pass


def enrich_abstract(papers: list[dict], progress_callback=None) -> list[dict]:
    """三级摘要补全流水线

    1. OpenAlex abstract_inverted_index
    2. Semantic Scholar（DOI查）
    3. Tavily 搜索引擎/科学网

    优化策略：所有论文并行处理前两轮，然后逐个兜底 Tavily。
    """
    need_enrich = [p for p in papers if p.get("abstract", "无摘要") == "无摘要" or not p.get("abstract")]
    if not need_enrich:
        return papers
    total = len(need_enrich)

    # 全局锁：同一时刻只允许一个调用方执行并行 HTTP 摘要补全，
    # 避免历史检索和每日推送同时调用时 API 限速/连接池争抢
    with _enrich_lock:
        import concurrent.futures as cf

        # 仅保留三轮：①OpenAlex ②Semantic Scholar(DOI) ⑥Tavily 搜索引擎
        def _process_one(i_p):
            i, p = i_p
            if progress_callback:
                progress_callback(0.20 + (i / total) * 0.35, f"摘要补全 ({i+1}/{total})")
            doi = p.get("doi", "")
            title = p.get("title", "")

            # 第1+2轮：OpenAlex 与 Semantic Scholar（DOI）并行
            if doi:
                with cf.ThreadPoolExecutor(max_workers=2) as ex:
                    fut_oa = ex.submit(_fetch_openalex, p, doi)
                    fut_ss = ex.submit(_fetch_ss_by_doi, p, doi)
                    for f in (fut_oa, fut_ss):
                        try:
                            f.result(timeout=12)
                        except Exception:
                            pass

            # 第6轮：Tavily 搜索引擎（前两轮失败时兜底）
            if not p.get("abstract") or p.get("abstract") in ("无摘要", ""):
                try:
                    ab = _search_abstract_from_web(title, doi)
                    if ab:
                        p["abstract"] = ab
                except Exception:
                    pass
            return p

        # 并行处理所有论文（限制并发数以防止过度资源竞争）
        max_workers = min(4, len(need_enrich))
        with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(_process_one, enumerate(need_enrich)))
    # ========== 锁外：纯 CPU 清理 ==========

    # 注意：need_enrich 中的 dict 与 papers 中的 dict 是同一对象，
    # 修改 need_enrich[i] 即修改了 papers 中对应论文，无需重新指派。

    # 对所有摘要做最终统一清理 + 质量校验
    for p in papers:
        abstract = p.get("abstract", "")
        if abstract and abstract != "无摘要":
            cleaned = _clean_abstract(abstract)
            # 英文单词数 < 40 视为获取有误（放宽门槛，覆盖早期短摘要）
            word_count = len(cleaned.split())
            if word_count < 40:
                cleaned = ""
            p["abstract"] = cleaned if cleaned else "无摘要"

    return papers
