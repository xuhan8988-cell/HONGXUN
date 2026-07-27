"""
鸿讯 HONGXUN · 文献书架模块
版本 1.0.0

本地 JSON 存储的论文库，支持按 DOI / 标题去重、阅读状态标记、RIS 导出。
"""

import os
import json
from datetime import datetime
from .config_manager import LIBRARY_FILE, _save_json, _load_json


def _next_id(lib: dict) -> str:
    """生成自增论文 ID: lib_YYYYMMDD_NNNN"""
    prefix = datetime.now().strftime("lib_%Y%m%d_")
    existing = [p["id"] for p in lib["papers"] if p["id"].startswith(prefix)]
    if existing:
        nums = [int(e.split("_")[-1]) for e in existing if e.split("_")[-1].isdigit()]
        n = max(nums) + 1 if nums else 1
    else:
        n = 1
    return f"{prefix}{n:04d}"


def load_library() -> dict:
    """读取 library.json，返回 {"version": 1, "papers": [...]}"""
    default = {"version": 1, "papers": []}
    data = _load_json(LIBRARY_FILE, default)
    if "papers" not in data:
        data["papers"] = []
    return data


def save_library(data: dict):
    """写回 library.json"""
    _save_json(LIBRARY_FILE, data)


def import_papers(papers: list[dict], task_name: str = "") -> int:
    """导入论文列表到书架，按 DOI 去重，返回新增数量。

    去重逻辑：
    1. 优先用 DOI 作为唯一键
    2. 无 DOI 时用 (title_lower, container_title_lower) 作为联合键
    """
    lib = load_library()

    existing_dois = {p.get("doi") for p in lib["papers"] if p.get("doi")}
    existing_tj = {
        (p.get("title", "").strip().lower(),
         p.get("container_title", "").strip().lower())
        for p in lib["papers"]
    }

    added = 0
    for p in papers:
        doi = (p.get("doi") or "").strip()
        if doi and doi in existing_dois:
            continue
        if not doi:
            # 无 DOI 时用 (标题, 期刊) 联合去重
            tj = (p.get("title", "").strip().lower(),
                  p.get("container_title", "").strip().lower())
            if tj in existing_tj:
                continue

        entry = {
            "id": _next_id(lib),
            "title": p.get("title", ""),
            "title_cn": p.get("title_cn", ""),
            "authors": p.get("authors", ""),
            "abstract": p.get("abstract", ""),
            "abstract_cn": p.get("abstract_cn", ""),
            "doi": doi,
            "container_title": p.get("container_title", ""),
            "pub_date": p.get("pub_date", ""),
            "matched_keywords": p.get("matched_keywords", []),
            "status": "pending",
            "added_date": datetime.now().strftime("%Y-%m-%d"),
            "task_name": task_name,
        }
        lib["papers"].insert(0, entry)  # 最新在前
        existing_dois.add(doi) if doi else None
        if not doi:
            existing_tj.add((
                p.get("title", "").strip().lower(),
                p.get("container_title", "").strip().lower(),
            ))
        added += 1

    save_library(lib)
    return added


def get_paper(paper_id: str) -> dict | None:
    """按 ID 获取单篇论文"""
    lib = load_library()
    for p in lib["papers"]:
        if p["id"] == paper_id:
            return p
    return None


def update_paper_status(paper_id: str, status: str):
    """更新论文阅读状态 (pending/read/excluded)"""
    lib = load_library()
    for p in lib["papers"]:
        if p["id"] == paper_id:
            p["status"] = status
            break
    save_library(lib)


def batch_update_status(ids: list[str], status: str) -> int:
    """批量更新论文阅读状态。返回更新的数量。"""
    lib = load_library()
    count = 0
    for p in lib["papers"]:
        if p["id"] in ids:
            p["status"] = status
            count += 1
    save_library(lib)
    return count


def delete_paper(paper_id: str):
    """从书架删除一篇论文"""
    lib = load_library()
    lib["papers"] = [p for p in lib["papers"] if p["id"] != paper_id]
    save_library(lib)


def query_papers(status: str = None, search_text: str = None,
                 task_name: str = None) -> list[dict]:
    """查询论文列表。

    Args:
        status: 筛选状态 (pending/read/excluded)，None 返回全部
        search_text: 在标题中模糊搜索（不区分大小写）
        task_name: 按来源任务筛选，None 返回全部
    Returns:
        匹配的论文列表，按 added_date 降序
    """
    lib = load_library()
    papers = lib["papers"]

    if status:
        papers = [p for p in papers if p.get("status") == status]

    if search_text:
        q = search_text.strip().lower()
        if q:
            papers = [p for p in papers if q in p.get("title", "").lower()]

    if task_name:
        papers = [p for p in papers if p.get("task_name") == task_name]

    return papers


def query_papers_paginated(status=None, search_text=None, task_name=None,
                           page=1, page_size=100) -> tuple[list[dict], int]:
    """分页查询论文列表。

    Returns:
        (论文列表, 总数量)
    """
    all_papers = query_papers(status=status, search_text=search_text, task_name=task_name)
    total = len(all_papers)
    start = (page - 1) * page_size
    end = start + page_size
    return all_papers[start:end], total


def get_all_task_names() -> list[str]:
    """返回书架中所有不同的来源任务名（按添加时间降序）"""
    lib = load_library()
    seen = set()
    names = []
    for p in lib["papers"]:
        name = p.get("task_name", "")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def get_stats() -> dict:
    """返回统计信息"""
    lib = load_library()
    papers = lib["papers"]
    total = len(papers)
    read = sum(1 for p in papers if p.get("status") == "read")
    excluded = sum(1 for p in papers if p.get("status") == "excluded")
    pending = total - read - excluded
    return {"total": total, "read": read, "excluded": excluded, "pending": pending}


def export_ris(papers: list[dict], file_path: str):
    """将论文列表导出为 RIS 格式文件，供 Zotero/EndNote 等导入。

    RIS 字段映射:
        TY  - 文献类型 (JOUR)
        TI  - 标题
        AU  - 作者 (每人一行)
        PY  - 出版日期 (YYYY//)
        DP  - DOI
        AB  - 摘要
        JO  - 期刊名称
        ER  - 记录结束
    """
    lines = []
    for p in papers:
        title = (p.get("title") or "").strip()
        authors = (p.get("authors") or "").strip()
        year = (p.get("pub_date") or "")[:4]
        doi = (p.get("doi") or "").strip()
        abstract = (p.get("abstract") or "").strip()
        journal = (p.get("container_title") or "").strip()

        lines.append("TY  - JOUR")
        if title:
            lines.append(f"TI  - {title}")
        if authors:
            for a in _split_authors(authors):
                lines.append(f"AU  - {a}")
        if year:
            lines.append(f"PY  - {year}//")
        if doi:
            lines.append(f"DP  - {doi}")
        if abstract:
            lines.append(f"AB  - {abstract}")
        if journal:
            lines.append(f"JO  - {journal}")
        lines.append("ER  - ")
        lines.append("")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _split_authors(authors_str: str) -> list[str]:
    """将 "Zhang S, Wang L, Li M" 拆分为 ["Zhang, S", "Wang, L", "Li, M"]"""
    parts = [a.strip() for a in authors_str.replace(";", ",").split(",") if a.strip()]
    result = []
    for p in parts:
        # 跳过 et al.
        if p.lower() in ("et al", "et al.", "…", ""):
            continue
        # 如果已经是 "姓, 名" 格式
        if "," in p:
            result.append(p)
        else:
            # "名 姓" → "姓, 名"（取最后一段为姓）
            tokens = p.split()
            if len(tokens) >= 2:
                surname = tokens[-1]
                given = " ".join(tokens[:-1])
                result.append(f"{surname}, {given}")
            else:
                result.append(p)
    return result
