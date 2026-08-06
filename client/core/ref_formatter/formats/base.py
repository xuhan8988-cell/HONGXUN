"""参考文献格式基类（ABC）。"""

from abc import ABC, abstractmethod
import re

# 统一引用类型键
TYPE_JOURNAL = "journal"
TYPE_BOOK = "book"
TYPE_CONFERENCE = "conference"
TYPE_THESIS = "thesis"
TYPE_PATENT = "patent"
TYPE_STANDARD = "standard"
TYPE_ELECTRONIC = "electronic"
TYPE_REPORT = "report"
TYPE_OTHER = "other"

# 中文字符检测
_CJK_RE = re.compile(r"[一-鿿]")


def has_cjk(text: str) -> bool:
    """是否含中文。"""
    return bool(text and _CJK_RE.search(text))


def split_author_list(raw: str):
    """把原始作者串切成作者列表（兼容中英文多种分隔）。

    返回规范化后的作者列表（每项去空白）。中英文名暂不转换大小写。
    """
    if not raw:
        return []
    text = raw.strip()
    # 去尾随的 et al. / 等
    text = re.sub(r"\s*(?:,?\s*et\s+al\.?|,?\s*等)\s*$", "", text, flags=re.I)
    # 按常见分隔符切分（英文逗号、中文逗号、分号、&、and、/）
    parts = re.split(r"[;；]|,\s*(?=[A-Z一-鿿])|&|\band\b", text)
    out = []
    for p in parts:
        p = p.strip(" ,;。.")
        if p:
            out.append(p)
    return out


def is_surname_initial(name: str) -> bool:
    """判断是否为「姓 + 名缩写」格式（如 Smith J / Wang Y / Zhang L）而不是
    「名 + 姓」（如 John Smith）。

    True 表示姓在前的格式，name 应以姓为核心；False 表示「名 姓」顺序。
    """
    name = name.strip()
    if "," in name:
        return True  # "Last, First" 或 "Last, A." 都已是姓在前
    if re.search(r"[一-鿿]", name):
        return False
    # 末尾缩写：单个大写字母 或 字母+点，可多个（Smith J.D. / Wang Y.）
    m = re.match(r"^(.*?)(?:\s+[A-Z](?:\.[A-Z]?\.?)?)+$", name)
    if not m:
        return False
    rest = m.group(1).strip()
    # 剩余部分应是单个姓（无空格、非多词名），否则按名+姓处理
    return bool(rest) and " " not in rest


class BaseReferenceFormatter(ABC):
    """参考文献格式基类。

    子类实现各 format_<type> 方法，把规范化 ref dict 渲染为字符串。
    """

    key = "base"
    name = "Base"
    citation_style = "numeric"  # numeric / author-date

    @abstractmethod
    def format_journal(self, ref) -> str:
        pass

    @abstractmethod
    def format_book(self, ref) -> str:
        pass

    @abstractmethod
    def format_conference(self, ref) -> str:
        pass

    @abstractmethod
    def format_thesis(self, ref) -> str:
        pass

    def format_patent(self, ref) -> str:
        return self.format_other(ref)

    def format_standard(self, ref) -> str:
        return self.format_other(ref)

    def format_electronic(self, ref) -> str:
        return self.format_other(ref)

    def format_report(self, ref) -> str:
        return self.format_other(ref)

    def format_other(self, ref) -> str:
        # 兜底：拼出最基本的信息
        parts = []
        authors = self._authors_plain(ref.get("authors", ""))
        if authors:
            parts.append(authors)
        if ref.get("title"):
            parts.append(ref["title"])
        if ref.get("year"):
            parts.append(str(ref["year"]))
        return ", ".join(p for p in parts if p) + "."

    def format(self, ref) -> str:
        """统一入口，根据类型分发。"""
        ref_type = ref.get("type", TYPE_JOURNAL)
        formatters = {
            TYPE_JOURNAL: self.format_journal,
            TYPE_BOOK: self.format_book,
            TYPE_CONFERENCE: self.format_conference,
            TYPE_THESIS: self.format_thesis,
            TYPE_PATENT: self.format_patent,
            TYPE_STANDARD: self.format_standard,
            TYPE_ELECTRONIC: self.format_electronic,
            TYPE_REPORT: self.format_report,
            TYPE_OTHER: self.format_other,
        }
        f = formatters.get(ref_type, self.format_journal)
        try:
            return f(ref)
        except Exception:
            return self.format_other(ref)

    # ── 辅助方法 ────────────────────────────────────────
    def _authors(self, raw: str, max_show: int, et_al: str = "et al.",
                 joiner: str = ", ", final_joiner: str = None) -> str:
        """格式化作者列表。超出 max_show 截断为 et al./等。"""
        names = split_author_list(raw)
        if not names:
            return ""
        final_joiner = final_joiner or joiner
        if len(names) <= max_show:
            if len(names) <= 1:
                return names[0]
            return joiner.join(names[:-1]) + final_joiner + names[-1]
        return joiner.join(names[:max_show]) + f", {et_al}"

    def _authors_plain(self, raw: str) -> str:
        names = split_author_list(raw)
        return ", ".join(names)

    def _year(self, ref) -> str:
        return str(ref.get("year") or "")

    def _doi(self, ref) -> str:
        doi = (ref.get("doi") or "").strip()
        return doi if doi.startswith("10.") else doi
