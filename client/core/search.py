# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · CrossRef 论文检索模块
版本 1.0.0
"""

import re
from datetime import datetime, timedelta
from calendar import monthrange
from .session import _session, _session_bulk
from .abstract import _clean_abstract
from .journal_db import (
    resolve_journal_issn,
    estimate_journal_volume,
    normalize_journal_name,
    DEFAULT_ANNUAL_VOLUME,
)


# ── 兼容旧版 import —— search.py 仍导出这些符号供 engine.py 等调用 ──
ESTIMATED_VOLUME: dict[str, int] = {}
COMMON_JOURNALS: dict[str, list[str]] = {}


def estimate_annual_volume(journal_name: str) -> int:
    """根据期刊名称估算年发文量。委托 journal_db。"""
    return estimate_journal_volume(journal_name)


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
                            works_url: str = None,
                            session=None) -> list[str]:
    """通过本地期刊数据库 + CrossRef API 将期刊名称解析为ISSN列表。

    查询顺序：
    1. 本地数据库 journal_db.py（覆盖中科院一区+二区top，含别名）
    2. CrossRef 期刊 API 精确匹配
    3. CrossRef 期刊 API 模糊匹配
    4. CrossRef works API 反向查询
    """
    if session is None:
        session = _session

    # 1. 本地数据库优先
    local_result = resolve_journal_issn(journal_name)
    if local_result:
        return local_result

    # 2-4. CrossRef API 查询（原逻辑保留）
    params = {"query": journal_name, "rows": 15}
    try:
        resp = session.get(base_url, params=params, timeout=15)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])

        for item in items:
            title = (item.get("title") or item.get("name") or "").strip()
            if title.lower() == normalize_journal_name(journal_name):
                issns = list(set(item.get("ISSN", []) + item.get("issn", [])))
                if issns:
                    return issns

        for item in items:
            title = (item.get("title") or item.get("name") or "").lower()
            if normalize_journal_name(journal_name) in title:
                idx = title.find(normalize_journal_name(journal_name))
                after_char = title[idx + len(normalize_journal_name(journal_name)):idx + len(normalize_journal_name(journal_name)) + 1] if idx >= 0 else ""
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
            if title.startswith(normalize_journal_name(journal_name)):
                after = title[len(normalize_journal_name(journal_name)):len(normalize_journal_name(journal_name))+1]
                if after and after.isalpha():
                    continue
                issns = list(set(item.get("ISSN", []) + item.get("issn", [])))
                if issns:
                    return list(set(issns))

        if len(journal_name) >= 8:
            for item in items:
                title = (item.get("title") or item.get("name") or "").lower()
                if normalize_journal_name(journal_name) in title:
                    issns = list(set(item.get("ISSN", []) + item.get("issn", [])))
                    if issns:
                        return list(set(issns))

    except Exception as e:
        print(f"解析期刊名称失败 '{journal_name}': {str(e)}", flush=True)

    if works_url:
        try:
            resp = session.get(works_url, params={
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
                            progress_callback=None,
                            session=None) -> list[dict]:
    """
    使用 CrossRef cursor 深度分页检索，取够 max_needed 篇或者直到 API 没有下一页。
    检索阶段不按关键词过滤，所有论文先获取，待 engine.py 摘要补全后统一匹配。
    """
    if session is None:
        session = _session
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
            resp = session.get(url, params=params, timeout=30)
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
                  seen_dois: set = None,
                  session=None) -> list[dict]:
    if seen_dois is None:
        seen_dois = set()
    """执行CrossRef检索并提取论文信息，单页查询（ISSN 未匹配时的备用路径）"""
    papers = []
    if seen_dois is None:
        seen_dois = set()
    if session is None:
        session = _session
    try:
        resp = session.get(url, params=params, timeout=30)
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
                  progress_callback=None,
                  date_filter: str = "pub") -> list[dict]:
    """
    按期刊名称、时间范围检索论文，返回标准化论文列表。
    当 keywords 为 None 或空时，不关键词过滤，返回期刊所有论文。
    使用 CrossRef cursor 深度分页突破 1000 条限制，直到取够所需条数。

    date_filter: "pub" 用 from-pub-date（按出版日期，仅到月）
                 "index" 用 from-index-date（按收录日期，精确到日，适合增量检查）
    """
    works_url = "https://api.crossref.org/works"
    journals_url = "https://api.crossref.org/journals"
    all_papers = []
    seen_dois = set()
    max_needed = calc_max_per_journal(journal_names, start_date, end_date, progress_callback)

    # 每日推送用独立 Session 池，避免与历史检索争抢连接
    _http = _session_bulk if date_filter == "index" else _session
    query_str = " ".join(keywords) if keywords else ""

    for journal_name in journal_names:
        issns = resolve_journal_to_issn(journal_name, journals_url, works_url, session=_http)

        if issns:
            for issn in issns:
                _date_key = "from-index-date" if date_filter == "index" else "from-pub-date"
                params_base = {
                    "filter": f"issn:{issn},{_date_key}:{start_date},until-index-date:{end_date}" if date_filter == "index"
                              else f"issn:{issn},{_date_key}:{start_date},until-pub-date:{end_date}",
                    "rows": 1000,
                    "sort": "published",
                    "order": "desc",
                }
                if query_str:
                    params_base["query"] = query_str
                papers = _fetch_papers_paginated(
                    works_url, params_base, f"{journal_name}[{issn}]", seen_dois, max_needed,
                    progress_callback, session=_http,
                )
                all_papers.extend(papers)
        else:
            # 模糊匹配：不使用分页，单页查询即可
            _date_key_fuzzy = "from-index-date" if date_filter == "index" else "from-pub-date"
            params = {
                "filter": f"{_date_key_fuzzy}:{start_date},until-index-date:{end_date}" if date_filter == "index"
                          else f"from-pub-date:{start_date},until-pub-date:{end_date}",
                "rows": 1000,
                "sort": "relevance",
                "order": "desc",
            }
            if query_str:
                params["query"] = query_str
            params["query.container-title"] = journal_name
            papers = _fetch_papers(works_url, params,
                                   f"{journal_name}(fuzzy)", seen_dois, session=_http)
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
