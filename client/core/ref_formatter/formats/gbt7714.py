"""GB/T 7714-2015（顺序编码制）。"""

from .base import BaseReferenceFormatter, has_cjk, split_author_list, is_surname_initial


class GBT7714Formatter(BaseReferenceFormatter):
    key = "gbt7714"
    name = "GB/T 7714-2015"
    citation_style = "numeric"

    def _authors(self, raw: str, max_show: int, et_al: str = "et al.",
                 joiner: str = ", ", final_joiner: str = None) -> str:
        names = split_author_list(raw)
        if not names:
            return ""
        # 中文名之间用逗号；结尾连接词中文用「等」、英文用 et al.
        is_cn = has_cjk(raw)
        et = "等" if is_cn else "et al."
        final_joiner = final_joiner or joiner
        if len(names) <= max_show:
            if len(names) <= 1:
                return names[0]
            return joiner.join(names[:-1]) + final_joiner + names[-1]
        return joiner.join(names[:max_show]) + f", {et}"

    def _gb_authors(self, raw: str) -> str:
        names = split_author_list(raw)
        if not names:
            return ""
        is_cn = has_cjk(raw)
        et = "等" if is_cn else "et al."
        max_show = 3
        if len(names) <= max_show:
            if len(names) <= 1:
                return names[0]
            return ", ".join(names)
        return ", ".join(names[:max_show]) + f", {et}"

    def _format_name(self, name: str) -> str:
        """英文 First Last → Last F；姓+缩写（Smith J）保持；中文保持原样。"""
        if has_cjk(name):
            return name
        name = name.strip()
        if "," in name:
            # Last, A. → Last A
            last, first = name.split(",", 1)
            return (last.strip() + " " + first.strip()).strip()
        if is_surname_initial(name):
            return name
        parts = name.split()
        if len(parts) <= 1:
            return name
        last = parts[-1]
        first_initials = " ".join(p[0] + "." for p in parts[:-1] if p)
        return f"{last} {first_initials}".strip()

    def format_journal(self, ref) -> str:
        # 作者. 题名[J]. 刊名, 年, 卷(期): 页码.
        authors = self._gb_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        journal = (ref.get("journal") or "").strip()
        year = ref.get("year") or ""
        vol = ref.get("volume") or ""
        issue = ref.get("issue") or ""
        pages = ref.get("pages") or ""
        s = ""
        if authors:
            s += authors + ". "
        if title:
            s += title
        tag = "[J]"
        s += tag
        rest = []
        if journal:
            rest.append(journal)
        if year:
            rest.append(str(year))
        if vol:
            if issue:
                seg = f"{vol}({issue})"
            else:
                seg = str(vol)
            if pages:
                seg += f":{pages}"
            rest.append(seg)
        elif pages:
            rest.append(f":{pages}")
        if rest:
            s += ". " + ", ".join(rest)
        s = s.rstrip(".,;，。；;") + "."
        return s

    def format_book(self, ref) -> str:
        authors = self._gb_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        year = ref.get("year") or ""
        publisher = ref.get("publisher") or ""
        edition = ref.get("edition") or ""
        s = ""
        if authors:
            s += authors + ". "
        if title:
            s += title
        s += "[M]"
        rest = []
        if edition:
            rest.append(edition)
        if publisher:
            rest.append(publisher)
        if year:
            rest.append(str(year))
        if rest:
            s += ". " + ", ".join(rest)
        s = s.rstrip(".,;，。；;") + "."
        return s

    def format_conference(self, ref) -> str:
        authors = self._gb_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        conf = (ref.get("conference") or ref.get("journal") or "").strip()
        year = ref.get("year") or ""
        pages = ref.get("pages") or ""
        s = ""
        if authors:
            s += authors + ". "
        if title:
            s += title
        s += "[C]"
        rest = []
        if conf:
            rest.append(conf)
        if pages:
            rest.append(f":{pages}")
        if year:
            rest.append(str(year))
        if rest:
            s += ". " + ", ".join(rest)
        s = s.rstrip(".,;，。；;") + "."
        return s

    def format_thesis(self, ref) -> str:
        authors = self._gb_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        year = ref.get("year") or ""
        school = ref.get("school") or ref.get("publisher") or ""
        s = ""
        if authors:
            s += authors + ". "
        if title:
            s += title
        s += "[D]"
        rest = []
        if school:
            rest.append(school)
        if year:
            rest.append(str(year))
        if rest:
            s += ". " + ", ".join(rest)
        s = s.rstrip(".,;，。；;") + "."
        return s

    def format_other(self, ref) -> str:
        s = super().format_other(ref)
        return s.rstrip(".") + "."
