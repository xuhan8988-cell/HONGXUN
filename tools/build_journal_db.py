#!/usr/bin/env python3
"""
鸿讯 HONGXUN · 期刊数据库构建脚本（一次性）
=================================================
从公开的期刊分区数据源构建智能期刊选择器所需的种子数据：

  数据源（来自 GitHub hitfyd/ShowJCR 仓库，均为公开整理数据）:
    - 中科院分区表 2025 版  FQBJCR2025-UTF8.csv  → 期刊名 / ISSN / 中科院大类分区 / Top / OA / WoS 类型
    - JCR 2025 版           JCR2025-UTF8.csv     → 期刊名 / ISSN / 影响因子 IF(2025)
    - JCR 2024 版           JCR2024-UTF8.csv     → IF(2024)（兜底）

  主期刊集：项目内 client/core/journal_db.py 的 COMMON_JOURNALS（约 350 本，
  覆盖中科院一区 + 二区 top），按"规范名去重 + ISSN 反查"与上述 CSV 关联。

  输出：client/data/journals_seed.json（智能期刊选择器首次打开时灌入 SQLite）

用法:
    python3 tools/build_journal_db.py [--csv-dir /path/to/csv] [--out client/data/journals_seed.json] [--dry-run]

说明:
    - 未提供 --csv-dir 时自动从 GitHub 下载 CSV 到 /tmp/hongxun_journal_csv/
    - 出版社/国家字段来自内置的 PUBLISHER_TABLE（按 ISSN 前缀/名称匹配），
      未命中时置空字符串（数据库支持空字段）。
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request

# ── 项目根路径 ─────────────────────────────────────────────
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
DEFAULT_OUT = os.path.join(PROJECT_ROOT, "client", "data", "journals_seed.json")
DEFAULT_CSV_DIR = os.path.join(os.path.expanduser("~"), ".cache", "hongxun_journal_csv")

# 数据源下载地址（master 分支，中文目录需 URL 编码）
GITHUB_RAW = "https://raw.githubusercontent.com/hitfyd/ShowJCR/master/"
DATA_SUBDIR = "中科院分区表及JCR原始数据文件/"
CSV_FILES = {
    "FQBJCR2025-UTF8.csv": "https://api.github.com/repos/hitfyd/ShowJCR/contents/%E4%B8%AD%E7%A7%91%E9%99%A2%E5%88%86%E5%8C%BA%E8%A1%A8%E5%8F%8AJCR%E5%8E%9F%E5%A7%8B%E6%95%B0%E6%8D%AE%E6%96%87%E4%BB%B6/FQBJCR2025-UTF8.csv",
    "JCR2025-UTF8.csv": "https://api.github.com/repos/hitfyd/ShowJCR/contents/%E4%B8%AD%E7%A7%91%E9%99%A2%E5%88%86%E5%8C%BA%E8%A1%A8%E5%8F%8AJCR%E5%8E%9F%E5%A7%8B%E6%95%B0%E6%8D%AE%E6%96%87%E4%BB%B6/JCR2025-UTF8.csv",
    "JCR2024-UTF8.csv": "https://api.github.com/repos/hitfyd/ShowJCR/contents/%E4%B8%AD%E7%A7%91%E9%99%A2%E5%88%86%E5%8C%BA%E8%A1%A8%E5%8F%8AJCR%E5%8E%9F%E5%A7%8B%E6%95%B0%E6%8D%AE%E6%96%87%E4%BB%B6/JCR2024-UTF8.csv",
}


def norm(name: str) -> str:
    """期刊名归一化：NFKC + 小写 + &→and + 标点转空格 + 去 the 前缀。"""
    n = unicodedata.normalize("NFKC", (name or "").lower())
    n = n.replace("&", "and")
    n = re.sub(r"[.,;:()\[\]\"\\'\-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if n.startswith("the "):
        n = n[4:]
    return n


# 保留全大写的缩写词（title_case 时例外）
_TITLE_KEEP_UPPER = {"ieee", "acs", "acs", "aip", "ai", "siam", "acm", "ifac"}


def title_case(name: str) -> str:
    """英文标题化：每个单词首字母大写，但保留已知缩写全大写。

    处理两类输入：
      - 已标题化的名（如 '2D Materials'）→ 原样规范化
      - 全大写名（如 'AAPG BULLETIN'）→ 先小写再标题化（保留 ACS/IEEE 等缩写）
    介词/连词（of/and/the/for/in/to/on）在词中保留小写。
    """
    if not name:
        return name
    # 判断整体是否全大写（含 ≥4 个字母时）
    letters = [c for c in name if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(letters) >= 4:
        name = name.lower()
    words = name.split(" ")
    _LOW = {"of", "and", "the", "for", "in", "to", "on", "at", "by", "with", "vs"}
    out = []
    for w in words:
        # 处理连字符段：'ca-a' → 'Ca-A'（数字+D 形式如 '2d' → '2D'）
        if "-" in w:
            segs = w.split("-")
            fixed = []
            for s in segs:
                if s.isdigit() or (len(s) == 1 and s.isalpha()):
                    fixed.append(s.upper())
                elif len(s) == 1:
                    fixed.append(s.upper())
                elif s.isupper() and len(s) > 1:
                    fixed.append(s)
                else:
                    fixed.append(s[:1].upper() + s[1:])
            out.append("-".join(fixed))
        elif w.lower() in _TITLE_KEEP_UPPER:
            out.append(w.upper())
        elif w.isupper() and len(w) > 2:
            out.append(w)
        elif len(w) == 1 and w.isalpha():
            out.append(w.upper())
        elif len(w) == 2 and w[0].isdigit() and w[1].isalpha():
            out.append(w.upper())  # '2d' → '2D'
        else:
            out.append(w[:1].upper() + w[1:] if w else w)
    joined = " ".join(out)
    # 词中短介词小写（避开首尾词）
    tokens = joined.split(" ")
    for i in range(1, len(tokens) - 1):
        if tokens[i].lower() in _LOW:
            tokens[i] = tokens[i].lower()
    return " ".join(tokens)


def extract_subcats(row: dict) -> list[dict]:
    """从分区表行的 小类1-6 字段提取干净的「大类→小类→分区」关联。

    CSV 小类字段格式：' 英文CODE 中文大类名：子类名'
    例：' MATERIALS SCIENCE, MULTIDISCIPLINARY 材料科学：综合'
    提取冒号后的中文子类名（'综合'）；无冒号时取中文部分。

    返回：[{category, subcat, division}, ...]（去重保序）
    """
    result = []
    seen = set()
    for i in range(1, 7):
        raw = row.get(f"小类{i}") or ""
        raw = raw.strip()
        if not raw:
            continue
        sub = _clean_subcat_name(raw)
        if not sub:
            continue
        # 小类归属大类：冒号前中文若与行大类一致则用行大类，否则用行大类兜底
        category = (row.get("大类") or "").strip() or ""
        key = (category, sub)
        if key in seen:
            continue
        seen.add(key)
        div_raw = row.get(f"小类{i}分区") or ""
        division = parse_division(div_raw)
        result.append({"category": category, "subcat": sub, "division": division})
    return result


def _clean_subcat_name(raw: str) -> str:
    """从小类原始串提取中文子类名。"""
    # 冒号后为子类名（中英文冒号均可）
    for sep in ("：", ":"):
        if sep in raw:
            after = raw.split(sep, 1)[1].strip()
            if after and re.search(r"[一-鿿]", after):
                return _extract_cn(after)
            break
    # 无冒号：从整串提取中文片段
    return _extract_cn(raw)


def _extract_cn(text: str) -> str:
    """提取字符串中的中文片段（去英文/标点前缀）。"""
    m = re.search(r"[一-鿿][一-鿿·（）()a-zA-Z0-9\- ]*", text)
    if m:
        return m.group(0).strip()
    return ""


# ── 出版社/国家权威映射表 ───────────────────────────────────
# 按"名称关键词"匹配，顺序在前者优先。数据为公开常识，供选择器展示。
PUBLISHER_RULES: list[tuple[str, str, str]] = [
    # (期刊名包含关键词, 出版社, 国家/地区)
    ("nature reviews", "Springer Nature", "英国"),
    ("nature communications", "Springer Nature", "英国"),
    ("nature", "Springer Nature", "英国"),
    ("scientific reports", "Springer Nature", "英国"),
    ("the lancet", "Elsevier", "英国"),
    ("lancet", "Elsevier", "英国"),
    ("cell reports", "Elsevier", "美国"),
    ("cell", "Elsevier (Cell Press)", "美国"),
    ("cancer cell", "Elsevier (Cell Press)", "美国"),
    ("immunity", "Elsevier (Cell Press)", "美国"),
    ("cell metabolism", "Elsevier (Cell Press)", "美国"),
    ("cell stem cell", "Elsevier (Cell Press)", "美国"),
    ("molecular cell", "Elsevier (Cell Press)", "美国"),
    ("developmental cell", "Elsevier (Cell Press)", "美国"),
    ("neuron", "Elsevier (Cell Press)", "美国"),
    ("current biology", "Elsevier (Cell Press)", "美国"),
    ("the embo journal", "Wiley", "德国"),
    ("embo journal", "Wiley", "德国"),
    ("embo reports", "Wiley", "德国"),
    ("nature medicine", "Springer Nature", "美国"),
    ("nature", "Springer Nature", "英国"),
    ("jama", "American Medical Association", "美国"),
    ("journal of the american medical association", "American Medical Association", "美国"),
    ("new england journal of medicine", "Massachusetts Medical Society", "美国"),
    ("nejm", "Massachusetts Medical Society", "美国"),
    ("bmj", "BMJ Publishing Group", "英国"),
    ("british medical journal", "BMJ Publishing Group", "英国"),
    ("science advances", "American Association for the Advancement of Science", "美国"),
    ("science", "American Association for the Advancement of Science", "美国"),
    ("pnas", "National Academy of Sciences", "美国"),
    ("proceedings of the national academy of sciences", "National Academy of Sciences", "美国"),
    ("plos", "Public Library of Science", "美国"),
    ("elife", "eLife Sciences", "英国"),
    ("advanced materials", "Wiley-VCH", "德国"),
    ("advanced functional materials", "Wiley-VCH", "德国"),
    ("advanced energy materials", "Wiley-VCH", "德国"),
    ("advanced science", "Wiley-VCH", "德国"),
    ("small", "Wiley-VCH", "德国"),
    ("small methods", "Wiley-VCH", "德国"),
    ("angewandte chemie", "Wiley-VCH", "德国"),
    ("ankewandte", "Wiley-VCH", "德国"),
    ("chem", "Cell Press", "美国"),
    ("matter", "Elsevier (Cell Press)", "美国"),
    ("joule", "Elsevier (Cell Press)", "美国"),
    ("journal of the american chemical society", "American Chemical Society", "美国"),
    ("jacs", "American Chemical Society", "美国"),
    ("acs nano", "American Chemical Society", "美国"),
    ("acs applied", "American Chemical Society", "美国"),
    ("acs energy letters", "American Chemical Society", "美国"),
    ("acs photonics", "American Chemical Society", "美国"),
    ("acs sustainable", "American Chemical Society", "美国"),
    ("chemical reviews", "American Chemical Society", "美国"),
    ("chemical society reviews", "Royal Society of Chemistry", "英国"),
    ("chemical science", "Royal Society of Chemistry", "英国"),
    ("chemical communications", "Royal Society of Chemistry", "英国"),
    ("green chemistry", "Royal Society of Chemistry", "英国"),
    ("analytical chemistry", "American Chemical Society", "美国"),
    ("inorganic chemistry", "American Chemical Society", "美国"),
    ("organic letters", "American Chemical Society", "美国"),
    ("macromolecules", "American Chemical Society", "美国"),
    ("polymer chemistry", "Royal Society of Chemistry", "英国"),
    ("journal of organic chemistry", "American Chemical Society", "美国"),
    ("journal of materials chemistry", "Royal Society of Chemistry", "英国"),
    ("dalton transactions", "Royal Society of Chemistry", "英国"),
    ("energy & environmental science", "Royal Society of Chemistry", "英国"),
    ("electrochimica acta", "Elsevier", "英国"),
    ("journal of catalysis", "Elsevier", "美国"),
    ("physical review", "American Physical Society", "美国"),
    ("reviews of modern physics", "American Physical Society", "美国"),
    ("applied physics letters", "AIP Publishing", "美国"),
    ("journal of applied physics", "AIP Publishing", "美国"),
    ("optics letters", "Optica Publishing Group", "美国"),
    ("optics express", "Optica Publishing Group", "美国"),
    ("laser & photonics reviews", "Wiley-VCH", "德国"),
    ("light: science & applications", "Springer Nature", "中国"),
    ("photonics research", "Optica Publishing Group", "美国"),
    ("the innovation", "Cell Press", "中国"),
    ("national science review", "Oxford University Press", "中国"),
    ("research", "AAAS", "中国"),
    ("signal transduction and targeted therapy", "Springer Nature", "中国"),
    ("cell research", "Springer Nature", "中国"),
    ("nano-micro letters", "Springer Open", "中国"),
    ("nano research", "Springer", "中国"),
    ("nano energy", "Elsevier", "荷兰"),
    ("nano letters", "American Chemical Society", "美国"),
    ("nanoscale", "Royal Society of Chemistry", "英国"),
    ("materials today", "Elsevier", "英国"),
    ("chemistry of materials", "American Chemical Society", "美国"),
    ("carbon energy", "Wiley-VCH", "中国"),
    ("carbon", "Elsevier", "英国"),
    ("composites", "Elsevier", "英国"),
    ("chemical engineering journal", "Elsevier", "荷兰"),
    ("cement and concrete research", "Elsevier", "英国"),
    ("construction and building materials", "Elsevier", "英国"),
    ("journal of building engineering", "Elsevier", "英国"),
    ("engineering structures", "Elsevier", "英国"),
    ("computers and geotechnics", "Elsevier", "英国"),
    ("geotechnique", "Thomas Telford", "英国"),
    ("environmental science & technology", "American Chemical Society", "美国"),
    ("water research", "Elsevier", "英国"),
    ("environmental pollution", "Elsevier", "英国"),
    ("journal of hazardous materials", "Elsevier", "荷兰"),
    ("science of the total environment", "Elsevier", "荷兰"),
    ("chemosphere", "Elsevier", "英国"),
    ("atmospheric environment", "Elsevier", "英国"),
    ("environmental research", "Elsevier", "荷兰"),
    ("environment international", "Elsevier", "英国"),
    ("geophysical research letters", "Wiley", "美国"),
    ("earth and planetary science letters", "Elsevier", "荷兰"),
    ("renewable and sustainable energy reviews", "Elsevier", "英国"),
    ("energy conversion and management", "Elsevier", "英国"),
    ("energy", "Elsevier", "英国"),
    ("fuel", "Elsevier", "英国"),
    ("bioresource technology", "Elsevier", "英国"),
    ("journal of cleaner production", "Elsevier", "荷兰"),
    ("waste management", "Elsevier", "英国"),
    ("global change biology", "Wiley", "英国"),
    ("ecology letters", "Wiley", "英国"),
    ("nature machine intelligence", "Springer Nature", "英国"),
    ("nature human behaviour", "Springer Nature", "英国"),
    ("ieee transactions", "IEEE", "美国"),
    ("ieee access", "IEEE", "美国"),
    ("ieee internet of things journal", "IEEE", "美国"),
    ("ieee robotics", "IEEE", "美国"),
    ("pattern recognition", "Elsevier", "英国"),
    ("computer vision and image understanding", "Elsevier", "美国"),
    ("neural networks", "Elsevier", "英国"),
    ("machine learning", "Springer", "荷兰"),
    ("journal of machine learning research", "JMLR", "美国"),
    ("artificial intelligence", "Elsevier", "荷兰"),
    ("expert systems with applications", "Elsevier", "英国"),
    ("knowledge-based systems", "Elsevier", "荷兰"),
    ("information sciences", "Elsevier", "荷兰"),
    ("computers in human behavior", "Elsevier", "英国"),
    ("neurocomputing", "Elsevier", "荷兰"),
    ("information fusion", "Elsevier", "荷兰"),
    ("medical image analysis", "Elsevier", "荷兰"),
    ("international journal of computer vision", "Springer", "荷兰"),
    ("acm computing surveys", "ACM", "美国"),
    ("proceedings of the ieee", "IEEE", "美国"),
    ("nature genetics", "Springer Nature", "美国"),
    ("nature cell biology", "Springer Nature", "美国"),
    ("nature structural", "Springer Nature", "美国"),
    ("nature chemical biology", "Springer Nature", "美国"),
    ("nature immunology", "Springer Nature", "美国"),
    ("nature microbiology", "Springer Nature", "英国"),
    ("nature plants", "Springer Nature", "英国"),
    ("nature ecology & evolution", "Springer Nature", "英国"),
    ("nature methods", "Springer Nature", "美国"),
    ("nature protocols", "Springer Nature", "英国"),
    ("nature biotechnology", "Springer Nature", "美国"),
    ("nature neuroscience", "Springer Nature", "美国"),
    ("nature reviews", "Springer Nature", "英国"),
    ("nature", "Springer Nature", "英国"),
    ("science", "AAAS", "美国"),
    ("journal of neuroscience", "Society for Neuroscience", "美国"),
    ("brain", "Oxford University Press", "英国"),
    ("neuroimage", "Elsevier", "美国"),
    ("human brain mapping", "Wiley", "美国"),
    ("trends in cognitive sciences", "Elsevier (Cell Press)", "英国"),
    ("biological psychiatry", "Elsevier", "美国"),
    ("journal of affective disorders", "Elsevier", "荷兰"),
    ("the quarterly journal of economics", "Oxford University Press", "美国"),
    ("american economic review", "American Economic Association", "美国"),
    ("journal of political economy", "University of Chicago Press", "美国"),
    ("econometrica", "Wiley", "美国"),
    ("journal of econometrics", "Elsevier", "荷兰"),
    ("journal of finance", "Wiley", "美国"),
    ("journal of financial economics", "Elsevier", "荷兰"),
    ("the review of financial studies", "Oxford University Press", "美国"),
    ("management science", "INFORMS", "美国"),
    ("operations research", "INFORMS", "美国"),
    ("journal of the american mathematical society", "American Mathematical Society", "美国"),
    ("annals of mathematics", "Princeton University", "美国"),
    ("inventiones mathematicae", "Springer", "德国"),
    ("acta mathematica", "Springer", "瑞典"),
    ("annals of statistics", "Institute of Mathematical Statistics", "美国"),
    ("siam review", "SIAM", "美国"),
    ("siam journal on numerical analysis", "SIAM", "美国"),
    ("mathematics of computation", "American Mathematical Society", "美国"),
    ("foundations of computational mathematics", "Springer", "美国"),
    ("ieee transactions on automatic control", "IEEE", "美国"),
    ("automatica", "Elsevier", "英国"),
    ("systems & control letters", "Elsevier", "荷兰"),
    ("gut", "BMJ Publishing Group", "英国"),
    ("hepatology", "Wiley", "美国"),
    ("blood", "American Society of Hematology", "美国"),
    ("circulation", "Lippincott Williams & Wilkins", "美国"),
    ("european heart journal", "Oxford University Press", "英国"),
    ("intensive care medicine", "Springer", "美国"),
    ("american journal of respiratory", "American Thoracic Society", "美国"),
    ("annals of internal medicine", "American College of Physicians", "美国"),
    ("annals of surgery", "Lippincott Williams & Wilkins", "美国"),
    ("clinical infectious diseases", "Oxford University Press", "美国"),
    ("journal of clinical investigation", "ASCI", "美国"),
    ("journal of hematology & oncology", "BMC", "英国"),
    ("molecular psychiatry", "Springer Nature", "美国"),
    ("science translational medicine", "AAAS", "美国"),
    ("science immunology", "AAAS", "美国"),
    ("science signaling", "AAAS", "美国"),
]


def detect_publisher(name: str) -> tuple[str, str]:
    """根据期刊名匹配出版社与国家。返回 (出版社, 国家/地区)。"""
    n = (name or "").lower()
    for keyword, publisher, country in PUBLISHER_RULES:
        if keyword in n:
            return publisher, country
    return "", ""


def parse_division(raw: str) -> int:
    """从 '1 [1/118]' 提取分区数字（1-4区，5区视为4，其他0）。"""
    m = re.match(r"\s*(\d+)", raw or "")
    if not m:
        return 0
    d = int(m.group(1))
    return d if 1 <= d <= 4 else 0


def load_common_journals() -> dict:
    """加载现有 journal_db.py 的 COMMON_JOURNALS + JOURNAL_ALIASES。

    以"唯一 ISSN"为单位归并：同一 ISSN 的多个名称键合并为一条记录，
    显示名优先取能在分区表/JCR 精确命中的名称，否则取最长名称。
    """
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "client"))
    try:
        from core.journal_db import COMMON_JOURNALS, JOURNAL_ALIASES
    except Exception as e:
        print(f"[warn] 无法加载 journal_db.py（{e}），将仅从 CSV 构建。")
        return {}, {}

    alias_map = {norm(k): norm(v) for k, v in JOURNAL_ALIASES.items()}

    def canonical(key: str) -> str:
        nk = norm(key)
        return alias_map.get(nk, nk)

    # issn -> {"names": {name}, "issns": [...]}
    by_issn: dict[str, dict] = {}
    for key, issns in COMMON_JOURNALS.items():
        std = canonical(key)
        for issn in issns:
            rec = by_issn.setdefault(issn, {"names": set(), "issns": []})
            rec["names"].add(std)
            if issn not in rec["issns"]:
                rec["issns"].append(issn)

    journals: dict[str, dict] = {}
    for issn, rec in by_issn.items():
        names = rec["names"]
        if not names:
            continue
        # 显示名：优先最长（最全称）
        display = sorted(names, key=lambda n: (-len(n), n))[0]
        journals[display] = {"full_name": display, "issns": list(rec["issns"])}
    return journals, alias_map


def load_csv(path: str):
    """读取 CSV，返回 (名称索引, ISSN索引)。"""
    name_index = {}
    issn_index = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jname = (row.get("Journal") or "").strip()
            if not jname:
                continue
            name_index.setdefault(norm(jname), row)
            for part in str(row.get("ISSN/EISSN", "") or row.get("ISSN", "")).split("/"):
                p = part.strip().replace("-", "")
                if p:
                    issn_index.setdefault(p, row)
            for fld in ("eISSN", "ISSN"):
                p = (row.get(fld) or "").strip().replace("-", "")
                if p:
                    issn_index.setdefault(p, row)
    return name_index, issn_index


def ensure_csv(csv_dir: str) -> list[str]:
    """确保 CSV 文件存在（缺失则下载），返回本地路径列表。"""
    os.makedirs(csv_dir, exist_ok=True)
    paths = []
    for fname, api_url in CSV_FILES.items():
        local = os.path.join(csv_dir, fname)
        if not os.path.exists(local):
            print(f"[download] {fname} ...")
            # 通过 GitHub API 获取 download_url（处理中文路径）
            try:
                req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    info = json.loads(resp.read().decode("utf-8"))
                    dl = info.get("download_url")
            except Exception as e:
                print(f"[warn] 获取下载地址失败: {e}")
                dl = None
            if not dl:
                continue
            try:
                req = urllib.request.Request(dl, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    with open(local, "wb") as out:
                        out.write(resp.read())
                print(f"[ok] {fname} 已下载")
            except Exception as e:
                print(f"[warn] 下载失败 {fname}: {e}")
                continue
        if os.path.exists(local):
            paths.append(local)
    return paths


def build(csv_dir: str, out_path: str, dry_run: bool = False) -> None:
    # 1. 加载主期刊集（仅用于出版社识别兜底；不再作白名单过滤）
    common_journals, _ = load_common_journals()
    print(f"主期刊集: {len(common_journals)} 本（journal_db.py，仅作出版社兜底）")

    # 2. 加载 CSV 数据源
    csv_paths = ensure_csv(csv_dir)
    if not csv_paths:
        print("[error] 没有可用的 CSV 数据源，无法构建。请先手动下载到目录后重试。")
        sys.exit(1)

    fqb_name, fqb_issn = {}, {}
    jcr25_name, jcr25_issn = {}, {}
    jcr24_name, jcr24_issn = {}, {}
    for p in csv_paths:
        base = os.path.basename(p)
        if "FQBJCR" in base:
            fqb_name, fqb_issn = load_csv(p)
        elif "JCR2025" in base:
            jcr25_name, jcr25_issn = load_csv(p)
        elif "JCR2024" in base:
            jcr24_name, jcr24_issn = load_csv(p)
    print(f"分区表 {len(fqb_name)} 条 / JCR2025 {len(jcr25_name)} 条 / JCR2024 {len(jcr24_name)} 条")

    # 3. 全量导入：以分区表为主数据集，仅保留中科院 1 区 + 2 区
    #    （3 区、4 区、无分区一律丢弃；Top 期刊保留标注）
    dropped = {"no_division": 0, "div34": 0, "no_name": 0, "dup": 0}
    seen_full_names: set[str] = set()

    # JCR 按 ISSN 建立快速索引（去连字符）
    def _issn_index(idx: dict) -> dict:
        return {issn.replace("-", ""): row for issn, row in idx.items()}

    jcr25_by_issn = _issn_index(jcr25_issn)
    jcr24_by_issn = _issn_index(jcr24_issn)

    # 分区表行按 ISSN 去重聚合；无 ISSN 的行按名称兜底
    fqb_rows: dict[str, dict] = {}
    for issn, row in fqb_issn.items():
        fqb_rows.setdefault(issn.replace("-", ""), row)
    for name, row in fqb_name.items():
        if not str(row.get("ISSN/EISSN", "") or "").strip():
            fqb_rows.setdefault("__name__" + norm(name), row)

    records = []
    for key, row in fqb_rows.items():
        division = parse_division(row.get("大类分区"))
        if division == 0:
            dropped["no_division"] += 1
            continue
        if division not in (1, 2):
            dropped["div34"] += 1
            continue

        jname = (row.get("Journal") or "").strip()
        if not jname:
            dropped["no_name"] += 1
            continue
        display = title_case(jname)
        if display in seen_full_names:
            dropped["dup"] += 1
            continue
        seen_full_names.add(display)

        # 从行的 ISSN/EISSN 取 ISSN（首段 / 次段）
        raw_issns = [p.strip().replace("-", "") for p in str(row.get("ISSN/EISSN", "")).split("/") if p.strip()]
        issn = raw_issns[0] if raw_issns else ""
        eissn = raw_issns[1] if len(raw_issns) > 1 else ""

        # 关联 JCR 拿 IF（2025 优先，2024 兜底；ISSN 与 eISSN 都试）
        ifi = 0.0
        for tbl in (jcr25_by_issn, jcr24_by_issn):
            for idf in ("IF(2025)", "IF(2024)"):
                for c in (issn, eissn):
                    if c and c in tbl and idf in tbl[c]:
                        try:
                            v = float((tbl[c].get(idf) or "0").strip() or 0)
                        except (TypeError, ValueError):
                            v = 0.0
                        if v:
                            ifi = v
                            break
                if ifi:
                    break
            if ifi:
                break

        is_top = 1 if (row.get("Top") or "").strip() == "是" else 0
        is_oa = 1 if (row.get("Open Access") or "").strip() in ("是", "Gold", "Hybrid") else 0
        category = (row.get("大类") or "").strip() or ""
        subcats = extract_subcats(row)
        subcat = subcats[0]["subcat"] if subcats else ""

        publisher, country = detect_publisher(jname)

        records.append({
            "full_name": display,
            "full_name_cn": "",
            "abbreviation": "",
            "issn": issn,
            "eissn": eissn,
            "category": category,
            "subcategory": subcat,
            "subcats": subcats,
            "cas_division_2024": division,
            "is_top": is_top,
            "impact_factor_2025": round(ifi, 1),
            "h_index": 0,
            "publisher": publisher,
            "country": country,
            "is_oa": is_oa,
            "review_cycle": "",
            "acceptance_rate": "",
        })

    print(f"全量导入: 保留 1区+2区 {len(records)} 本；丢弃 {dropped}")

    # 4. 排序（IF 降序）+ 统计
    records.sort(key=lambda r: r["impact_factor_2025"], reverse=True)
    with_div = sum(1 for r in records if r["cas_division_2024"] > 0)
    with_if = sum(1 for r in records if r["impact_factor_2025"] > 0)
    with_pub = sum(1 for r in records if r["publisher"])
    with_cat = sum(1 for r in records if r["category"])
    n_top = sum(1 for r in records if r["is_top"])
    print(f"\n构建完成: {len(records)} 本期刊")
    print(f"  有分区: {with_div} ({with_div/len(records)*100:.0f}%)")
    print(f"  有IF:   {with_if} ({with_if/len(records)*100:.0f}%)")
    print(f"  有出版社: {with_pub} ({with_pub/len(records)*100:.0f}%)")
    print(f"  有学科: {with_cat} ({with_cat/len(records)*100:.0f}%)")
    print(f"  Top:    {n_top} ({n_top/len(records)*100:.0f}%)")

    if dry_run:
        print("[dry-run] 不写文件。前 5 条预览：")
        for r in records[:5]:
            print(" ", r["full_name"], "| 分区", r["cas_division_2024"], "| IF", r["impact_factor_2025"], "|", r["publisher"])
        return

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    payload = {"seed_version": 2, "journals": records}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"\n已写入: {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="构建智能期刊选择器种子数据")
    ap.add_argument("--csv-dir", default=DEFAULT_CSV_DIR, help="CSV 数据源目录（缺省自动下载）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出 JSON 路径")
    ap.add_argument("--dry-run", action="store_true", help="只预览不写文件")
    args = ap.parse_args()
    build(args.csv_dir, args.out, args.dry_run)
