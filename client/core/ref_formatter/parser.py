"""文档解析：识别正文引用与参考文献条目，规范化成结构化 dict。"""

import re
from dataclasses import dataclass, field

from .utils.docx_utils import (
    extract_citations_from_document,
    extract_reference_paragraphs,
    find_references_heading_index,
)

# 类型标记 → 统一类型
_TYPE_TAGS = {
    "J": "journal",
    "C": "conference",
    "M": "book",
    "D": "thesis",
    "P": "patent",
    "S": "standard",
    "EB/OL": "electronic",
    "EB": "electronic",
    "OL": "electronic",
    "R": "report",
    "N": "other",
    "Z": "other",
}

# 提取年份
_YEAR_RE = re.compile(r"(19|20)\d{2}")
# DOI
_DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s,;。]+)", re.I)
# 卷(期)
# 卷(期)
_VOL_RE = re.compile(r"[，,]?\s*(\d+)\s*[（(]\s*(\d+)\s*[）)]\s*[:：]?\s*([\d\-–\s,，]+)")
_VOL_ONLY_RE = re.compile(r"[，,]?\s*(\d+)\s*[（(]\s*(\d+)\s*[）)]\s*$")
_PAGES_RE = re.compile(r"[:：]\s*([\d\-–\s,，]+)\s*$")


@dataclass
class DocData:
    """解析结果。"""
    citations: list[int] = field(default_factory=list)   # 正文引用，首次出现顺序
    references: list[dict] = field(default_factory=list) # 参考文献结构化
    ref_start_index: int = -1                            # 参考文献区起始段落下标
    raw_reference_texts: list[str] = field(default_factory=list)


def _strip_number(text: str) -> str:
    """去掉条目开头的 [N]。"""
    return re.sub(r"^\s*\[\d+\]\s*", "", text).strip()


def _extract_type(text: str) -> str:
    """根据 [X] 标记判断文献类型。"""
    m = re.search(r"\[([A-Z/]+)\]", text)
    if m:
        tag = m.group(1).upper()
        if tag in _TYPE_TAGS:
            return _TYPE_TAGS[tag]
    # 无标记时按内容启发
    low = text.lower()
    if "doi.org" in low or "http" in low:
        return "electronic"
    if "学位论文" in text or "dissertation" in low or "thesis" in low:
        return "thesis"
    if "会议" in text or "proceedings" in low or "conf" in low:
        return "conference"
    return "journal"


def _extract_authors_and_rest(text: str, ref_type: str):
    """尽力切分作者与其余内容。返回 (authors_raw, rest)。"""
    if not text:
        return "", ""
    # 中文：作者与标题用「. 」或「。 」分隔
    if re.search(r"[一-鿿]", text):
        m = re.match(r"^(.+?)[\.。]\s+(.+)$", text)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return text, ""
    # 英文：作者以「. 」或「, 」或「 (」结束（排除已是逗号分节的内容）
    # 优先「. 」(句点) 分节：Smith J. Title...
    m = re.match(r"^(.+?\.)\s+(.+)$", text)
    if m and "." in m.group(1):
        return m.group(1).rstrip(".").strip(), m.group(2).strip()
    # 其次「, 」分节（作者列表结尾或 Last, F. 后）
    m = re.match(r"^(.+?),?\s+\(?\d{4}\)?[,. ]+(.+)$", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # 作者 与 (Year) 形式
    m = re.match(r"^(.+?)\s+\(?\d{4}[\s,.)]+(.+)$", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text, ""


def parse_reference(text: str) -> dict:
    """把一条参考文献文本解析为规范化 dict。"""
    raw = _strip_number(text)
    ref_type = _extract_type(raw)
    # 去掉类型标记如 [J]（含可能的标点残留）
    body = re.sub(r"\s*\[[A-Z/]+\]\s*", " ", raw)
    body = re.sub(r"\s+", " ", body).strip()
    body = re.sub(r"^[.,，。;；\s]+", "", body).strip()

    doi = ""
    m = _DOI_RE.search(body)
    if m:
        doi = m.group(1).rstrip(".,;，。")
        body = body[:m.start()] + body[m.end():]

    # 先切作者与其余，再从其余里抽年份（年份通常紧跟作者）
    authors, rest = _extract_authors_and_rest(body, ref_type)

    year = ""
    m = _YEAR_RE.search(rest)
    if m:
        year = m.group(0)
        rest = rest[:m.start()] + rest[m.end():]
        # 清理年份前后的括号/标点残留
        rest = re.sub(r"\(\)|\[\]|,,|  ", " ", rest).strip()

    ref = {
        "type": ref_type,
        "raw": raw,
        "authors": authors.strip(),
        "title": "",
        "year": year,
        "journal": "",
        "volume": "",
        "issue": "",
        "pages": "",
        "publisher": "",
        "conference": "",
        "school": "",
        "doi": doi,
        "url": "",
    }

    rest = re.sub(r"^[.,，。;；\s]+|[.,，。;；\s]+$", "", rest).strip()

    if ref_type == "journal":
        # 尝试卷(期):页码 或 卷(期)
        m = _VOL_RE.search(rest)
        if m:
            ref["volume"] = m.group(1)
            ref["issue"] = m.group(2)
            ref["pages"] = re.sub(r"^[:：,\s]+", "", m.group(3).replace(" ", ""))
            rest = rest[:m.start()] + rest[m.end():]
        else:
            m = _VOL_ONLY_RE.search(rest)
            if m:
                ref["volume"] = m.group(1)
                ref["issue"] = m.group(2)
                rest = rest[:m.start()] + rest[m.end():]
        # 刊名 与 标题：标题一般在引号/书名号内或逗号前
        title, tail = _split_title(rest)
        ref["title"] = title
        ref["journal"] = _clean_journal(tail)
    elif ref_type == "book":
        # 格式：书名. 出版地: 出版者, 出版年
        # 类型标记残留的「. 」切分书名与出版信息
        parts = re.split(r"\s*\.\s+", rest, maxsplit=1)
        ref["title"] = parts[0].strip()
        loc_pub = parts[1].strip() if len(parts) > 1 else rest
        if ":" in loc_pub or "：" in loc_pub:
            pub_seg = re.split(r":|：", loc_pub, maxsplit=1)
            ref["publisher"] = pub_seg[-1].strip()
        elif "," in loc_pub:
            ref["publisher"] = loc_pub.split(",", 1)[-1].strip()
        ref["publisher"] = re.sub(r"^[.,，。;；\s]+|[.,，。;；\s]+$", "",
                                  ref["publisher"]).strip()
    elif ref_type == "conference":
        ref["title"] = rest
        # 会议名在 title 后（. 或 , 分隔）
        parts = re.split(r"[,.:：]\s+", rest, maxsplit=1)
        if len(parts) >= 2:
            ref["title"] = parts[0].strip()
            ref["conference"] = parts[1].strip()
    elif ref_type == "thesis":
        ref["title"] = rest
    else:
        ref["title"] = rest

    return ref


def _split_title(rest: str):
    """从剩余文本中切分标题与刊名。

    支持：引号/书名号标题、或「Title. Journal」（英文点分节）、
    或「Title，Journal」（中文逗号）。
    """
    rest = rest.strip()
    if not rest:
        return "", ""
    # 引号 / 书名号内的标题
    m = re.match(r'^[“"\'](.+?)[”"\']\s*[.,，。]?\s*(.*)$', rest)
    if m and len(m.group(1)) > 2:
        return m.group(1).strip(), m.group(2).strip()
    # 「Title. Journal」——点后是刊名
    m = re.match(r"^(.+?)\.[,，]?\s*(.+)$", rest)
    if m:
        title = m.group(1).strip()
        tail = m.group(2).strip()
        if 2 <= len(title) <= 120:
            return title, tail
    # 中文逗号分节
    m = re.match(r"^(.+?)[，,]\s*(.+)$", rest)
    if m and len(m.group(1)) < 80:
        return m.group(1).strip(), m.group(2).strip()
    return rest, ""


def _clean_journal(tail: str) -> str:
    return re.sub(r"^[,，.:：\s]+|[,，.:：\s]+$", "", tail)


class DocumentParser:
    """解析 .docx 文档中的正文引用与参考文献。"""

    def parse(self, path: str) -> DocData:
        from docx import Document
        doc = Document(path)
        ref_start = find_references_heading_index(doc)
        data = DocData()
        data.ref_start_index = ref_start
        data.citations = extract_citations_from_document(doc, ref_start)
        if ref_start >= 0:
            _, ref_paras = extract_reference_paragraphs(doc)
        else:
            ref_paras = []
        data.raw_reference_texts = [(p.text or "").strip() for p in ref_paras
                                    if (p.text or "").strip()]
        for t in data.raw_reference_texts:
            data.references.append(parse_reference(t))
        return data
