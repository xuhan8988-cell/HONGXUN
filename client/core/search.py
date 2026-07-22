# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · CrossRef 论文检索模块
版本 1.0.0
"""

import re
from datetime import datetime, timedelta
from calendar import monthrange
from .session import _session
from .abstract import _clean_abstract


# ── 常见期刊年发文量估算表（篇/年） ─────────────────────────
# 数据来源：各期刊官网 / ISSN 统计 / 近 3 年平均
# 命中 10 篇 → 返回 rows = 10 × 年跨度 × 1.5 倍裕量
ESTIMATED_VOLUME: dict[str, int] = {
    # ===== 综合 / 跨学科 =====
    "nature": 1000,
    "science": 900,
    "pnas": 3500,
    "nature communications": 6000,
    "scientific reports": 20000,
    "plos one": 12000,
    "iscience": 3000,
    "advanced science": 2500,
    "the innovation": 400,
    "national science review": 200,
    "research": 800,
    # ===== 医学 / 临床 =====
    "the lancet": 400,
    "lancet": 400,
    "new england journal of medicine": 400,
    "nejm": 400,
    "jama": 300,
    "bmj": 2000,
    "nature medicine": 400,
    "cell": 500,
    "cell reports": 2000,
    "cell research": 200,
    "cancer cell": 200,
    "immunity": 300,
    # ===== 材料 / 工程 =====
    "nature materials": 300,
    "nature nanotechnology": 300,
    "advanced materials": 4000,
    "advanced functional materials": 3000,
    "acs nano": 3000,
    "nano letters": 2000,
    "nano today": 400,
    "chemistry of materials": 1500,
    "materials today": 400,
    "matter": 400,
    "cement and concrete research": 600,
    "cement and concrete composites": 600,
    "construction and building materials": 3000,
    "journal of building engineering": 2000,
    "engineering structures": 2000,
    "structural concrete": 600,
    "magazine of concrete research": 300,
    "journal of materials in civil engineering": 800,
    "acs sustainable chemistry & engineering": 3000,
    "journal of cleaner production": 6000,
    "resources, conservation and recycling": 1500,
    "waste management": 1500,
    # ===== 化学 =====
    "journal of the american chemical society": 5000,
    "angewandte chemie": 4000,
    "chemical reviews": 300,
    "chemical society reviews": 400,
    "chemical science": 2500,
    "chemical communications": 5000,
    "green chemistry": 1500,
    "dalton transactions": 3000,
    # ===== 物理 =====
    "physical review letters": 5000,
    "physical review b": 8000,
    "physical review d": 6000,
    "applied physics letters": 4000,
    "journal of applied physics": 3000,
    "nano energy": 2000,
    # ===== 环境 / 地球 =====
    "environmental science & technology": 3000,
    "water research": 2500,
    "environmental pollution": 3000,
    "journal of hazardous materials": 4000,
    "science of the total environment": 8000,
    "chemosphere": 4000,
    "atmospheric environment": 2000,
    "geophysical research letters": 4000,
    "earth and planetary science letters": 1000,
    # ===== 计算机 / AI =====
    "nature machine intelligence": 300,
    "ieee transactions on pattern analysis and machine intelligence": 800,
    "ieee transactions on neural networks and learning systems": 1500,
    "ieee transactions on image processing": 1500,
    "ieee transactions on information theory": 1000,
    "pattern recognition": 2000,
    "computer vision and image understanding": 400,
    "neural networks": 1000,
    "machine learning": 300,
    "journal of machine learning research": 400,
    "artificial intelligence": 400,
    "expert systems with applications": 4000,
    "knowledge-based systems": 2000,
    "information sciences": 4000,
    "computers in human behavior": 2000,
    "ieee access": 15000,
    # ===== 生物 =====
    "cell": 500,
    "nature genetics": 300,
    "nature cell biology": 200,
    "nature reviews molecular cell biology": 100,
    "molecular cell": 600,
    "developmental cell": 300,
    "current biology": 1000,
    "elife": 3000,
    "the embo journal": 600,
    "the plant cell": 400,
    "plant physiology": 1000,
    # ===== 神经 / 心理 =====
    "nature neuroscience": 300,
    "neuron": 600,
    "journal of neuroscience": 3000,
    "brain": 500,
    "neuroimage": 2000,
    "human brain mapping": 800,
    # ===== 经济学 / 社科 =====
    "the quarterly journal of economics": 60,
    "american economic review": 300,
    "journal of political economy": 60,
    "econometrica": 80,
    "journal of econometrics": 400,
    "journal of finance": 100,
    "journal of financial economics": 150,
    "the review of financial studies": 100,
}

# 兜底：当期刊名称未在估算表中时，使用该默认值（中等规模期刊）
DEFAULT_ANNUAL_VOLUME = 2000


def estimate_annual_volume(journal_name: str) -> int:
    """根据期刊名称估算年发文量。不区分大小写，精确匹配优先。"""
    key = journal_name.strip().lower()
    # 精确匹配
    if key in ESTIMATED_VOLUME:
        return ESTIMATED_VOLUME[key]
    # 前缀匹配（如 "ieee transactions on xxx" 系列）
    for known_key, vol in ESTIMATED_VOLUME.items():
        if known_key.startswith(key) or key.startswith(known_key):
            return vol
    return DEFAULT_ANNUAL_VOLUME


def calc_max_per_journal(journal_names: list[str],
                          start_date: str, end_date: str,
                          progress_callback=None) -> int:
    """
    根据期刊年发文量 × 时间跨度自动计算每期刊应返回的最大行数。
    返回值在各期刊估算值中取最大值，再乘以 1.5 倍裕量系数。
    无硬上限——CrossRef cursor 深度分页可以翻到足够。
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        span_years = max((end_dt - start_dt).days / 365.25, 0.1)
    except Exception:
        span_years = 1

    max_vol = 0
    for jn in journal_names:
        vol = estimate_annual_volume(jn)
        if vol > max_vol:
            max_vol = vol

    # 所需总条数 = 最大年发文量 × 时间跨度年 × 1.5 倍裕量
    needed = int(max_vol * span_years * 1.5)
    # 保底下限 100，取消 800 硬上限——用户需要获取全部文献
    return max(needed, 100)


def resolve_journal_to_issn(journal_name: str, base_url: str,
                            works_url: str = None) -> list[str]:
    """通过CrossRef期刊API将期刊名称解析为ISSN列表（精确匹配优先）"""

    COMMON_JOURNALS = {
        "science": ["0036-8075", "1095-9203"],
        "nature": ["0028-0836", "1476-4687"],
        "cell": ["0092-8674", "1097-4172"],
        "pnas": ["0027-8424", "1091-6490"],
        "the lancet": ["0140-6736", "1474-547X"],
        "lancet": ["0140-6736", "1474-547X"],
        "new england journal of medicine": ["0028-4793", "1533-4406"],
        "nejm": ["0028-4793", "1533-4406"],
        "jama": ["0098-7484", "1538-3598"],
        "bmj": ["0959-535X", "1759-2151"],
    }
    key = journal_name.strip().lower()
    if key in COMMON_JOURNALS:
        return COMMON_JOURNALS[key]

    params = {"query": journal_name, "rows": 15}
    try:
        resp = _session.get(base_url, params=params, timeout=15)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])

        for item in items:
            title = (item.get("title") or item.get("name") or "").strip()
            if title.lower() == journal_name.lower():
                issns = list(set(item.get("ISSN", []) + item.get("issn", [])))
                if issns:
                    return issns

        for item in items:
            title = (item.get("title") or item.get("name") or "").lower()
            if journal_name.lower() in title:
                idx = title.find(journal_name.lower())
                after_char = title[idx + len(journal_name):idx + len(journal_name) + 1] if idx >= 0 else ""
                before_char = title[idx - 1:idx] if idx > 0 else ""
                if before_char and before_char.isalpha():
                    continue
                if after_char and after_char.isalpha():
                    continue
                issns = list(set(item.get("ISSN", []) + item.get("issn", [])))
                if issns:
                    return list(set(issns))

        for item in items:
            title = (item.get("title") or item.get("name") or "").lower()
            if title.startswith(journal_name.lower()):
                after = title[len(journal_name):len(journal_name)+1]
                if after and after.isalpha():
                    continue
                issns = list(set(item.get("ISSN", []) + item.get("issn", [])))
                if issns:
                    return list(set(issns))

        if len(journal_name) >= 8:
            for item in items:
                title = (item.get("title") or item.get("name") or "").lower()
                if journal_name.lower() in title:
                    issns = list(set(item.get("ISSN", []) + item.get("issn", [])))
                    if issns:
                        return list(set(issns))

    except Exception as e:
        print(f"解析期刊名称失败 '{journal_name}': {str(e)}", flush=True)

    if works_url:
        try:
            resp = _session.get(works_url, params={
                "query.container-title": journal_name,
                "rows": 1,
                "filter": "from-pub-date:2020-01-01,until-pub-date:2026-12-31"
            }, timeout=15)
            resp.raise_for_status()
            items = resp.json().get("message", {}).get("items", [])
            if items:
                item = items[0]
                issn = item.get("ISSN", [])
                if issn:
                    return list(set(issn))
        except Exception:
            pass

    return []


def _fetch_papers_paginated(url: str, params_base: dict,
                            source_label: str,
                            seen_dois: set, max_needed: int,
                            progress_callback=None) -> list[dict]:
    """
    使用 CrossRef cursor 深度分页检索，取够 max_needed 篇或者直到 API 没有下一页。
    检索阶段不按关键词过滤，所有论文先获取，待 engine.py 摘要补全后统一匹配。
    """
    all_papers = []
    cursor = "*"
    raw_total = 0
    page_no = 0

    while raw_total < max_needed:
        page_no += 1
        if progress_callback:
            progress_callback(0.0, f"检索 {source_label} - 第{page_no}页")

        params = {**params_base, "cursor": cursor}
        try:
            resp = _session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message", {})
            items = msg.get("items", [])

            if not items:
                break

            for item in items:
                raw_total += 1
                doi = item.get("DOI", "")
                if not doi or doi in seen_dois:
                    continue

                title = item.get("title", ["无标题"])[0]
                abstract = item.get("abstract", "")
                if abstract:
                    abstract = _clean_abstract(abstract)
                if not abstract:
                    abstract = "无摘要"

                # 检索阶段不按关键词过滤——所有论文统一先获取，
                # 等 engine.py 中摘要补全完成后才匹配关键词，避免遗漏
                authors = []
                affiliations_map = {}
                for a in item.get("author", []):
                    name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                    affs = a.get("affiliation", [])
                    aff_names = [aff.get("name", "") for aff in affs if aff.get("name")]
                    if name:
                        authors.append(name)
                        if aff_names:
                            affiliations_map[name] = "; ".join(aff_names)

                pub_info = item.get("published-online", item.get("published-print", {}))
                date_parts = pub_info.get("date-parts", [["未知"]])[0]
                pub_date = "-".join(map(str, date_parts))

                container_title = item.get("container-title", [""])
                seen_dois.add(doi)
                all_papers.append({
                    "title": title,
                    "authors": ", ".join(authors) if authors else "无作者",
                    "affiliations": affiliations_map,
                    "pub_date": pub_date,
                    "abstract": abstract,
                    "doi": doi,
                    "container_title": container_title[0] if container_title else "",
                    "matched_keywords": [],  # 关键词匹配在 engine.py 摘要补全后执行
                    "source": source_label,
                })

            next_cursor = msg.get("next-cursor", "")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        except Exception as e:
            print(f"检索 {source_label} 分页失败: {str(e)}", flush=True)
            break

    return all_papers


def _fetch_papers(url: str, params: dict,
                  source_label: str,
                  seen_dois: set = None) -> list[dict]:
    if seen_dois is None:
        seen_dois = set()
    """执行CrossRef检索并提取论文信息，单页查询（ISSN 未匹配时的备用路径）"""
    papers = []
    if seen_dois is None:
        seen_dois = set()
    try:
        resp = _session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])

        for item in items:
            doi = item.get("DOI", "")
            if not doi or doi in seen_dois:
                continue

            title = item.get("title", ["无标题"])[0]

            abstract = item.get("abstract", "")
            if abstract:
                abstract = _clean_abstract(abstract)
            if not abstract:
                abstract = "无摘要"

            # 检索阶段不按关键词过滤——所有论文统一先获取，
            # 等 engine.py 中摘要补全完成后才匹配关键词，避免遗漏
            matched_kws = []

            authors = []
            affiliations_map = {}
            for a in item.get("author", []):
                name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                affs = a.get("affiliation", [])
                aff_names = [aff.get("name", "") for aff in affs if aff.get("name")]
                if name:
                    authors.append(name)
                    if aff_names:
                        affiliations_map[name] = "; ".join(aff_names)

            pub_info = item.get("published-online", item.get("published-print", {}))
            date_parts = pub_info.get("date-parts", [["未知"]])[0]
            pub_date = "-".join(map(str, date_parts))

            container_title = item.get("container-title", [""])
            seen_dois.add(doi)
            papers.append({
                "title": title,
                "authors": ", ".join(authors) if authors else "无作者",
                "affiliations": affiliations_map,
                "pub_date": pub_date,
                "abstract": abstract,
                "doi": doi,
                "container_title": container_title[0] if container_title else "",
                "matched_keywords": matched_kws,
                "source": source_label
            })
    except Exception as e:
        print(f"检索 {source_label} 失败: {str(e)}", flush=True)
    return papers


def search_papers(journal_names: list[str], start_date: str, end_date: str,
                  keywords: list[str] = None,
                  progress_callback=None) -> list[dict]:
    """
    按期刊名称、时间范围检索论文，返回标准化论文列表。
    当 keywords 为 None 或空时，不关键词过滤，返回期刊所有论文。
    使用 CrossRef cursor 深度分页突破 1000 条限制，直到取够所需条数。
    """
    works_url = "https://api.crossref.org/works"
    journals_url = "https://api.crossref.org/journals"
    all_papers = []
    seen_dois = set()
    max_needed = calc_max_per_journal(journal_names, start_date, end_date, progress_callback)

    query_str = " ".join(keywords) if keywords else ""

    for journal_name in journal_names:
        issns = resolve_journal_to_issn(journal_name, journals_url, works_url)

        if issns:
            for issn in issns:
                params_base = {
                    "filter": f"issn:{issn},from-pub-date:{start_date},until-pub-date:{end_date}",
                    "rows": 1000,
                    "sort": "published",
                    "order": "desc",
                }
                if query_str:
                    params_base["query"] = query_str
                papers = _fetch_papers_paginated(
                    works_url, params_base, f"{journal_name}[{issn}]", seen_dois, max_needed,
                    progress_callback,
                )
                all_papers.extend(papers)
        else:
            # 模糊匹配：不使用分页，单页查询即可
            params = {
                "filter": f"from-pub-date:{start_date},until-pub-date:{end_date}",
                "rows": 1000,
                "sort": "relevance",
                "order": "desc",
            }
            if query_str:
                params["query"] = query_str
            params["query.container-title"] = journal_name
            papers = _fetch_papers(works_url, params,
                                   f"{journal_name}(fuzzy)", seen_dois)
            for p in papers:
                ct = p.get("container_title", "").lower()
                jn = journal_name.lower()
                if ct == jn or ct.startswith(jn + " ") or ct.startswith(jn + "-"):
                    all_papers.append(p)

    return all_papers


def _filter_keywords2(papers: list[dict], keywords2: list[str]) -> list[dict]:
    """如果 keywords2 不为空，论文必须同时匹配至少一个 keywords2 才保留。
    在标题和摘要上匹配（摘要已在补全之后）。"""
    if not keywords2:
        return papers
    kw2_lower = [kw.lower() for kw in keywords2]
    result = []
    for p in papers:
        text = f"{p['title']} {p.get('abstract', '')}".lower()
        if any(kw in text for kw in kw2_lower):
            result.append(p)
    return result
