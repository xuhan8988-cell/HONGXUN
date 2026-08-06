"""APA 7th 格式（作者-年份）。"""

from .base import BaseReferenceFormatter, split_author_list, is_surname_initial


class APA7Formatter(BaseReferenceFormatter):
    key = "apa7"
    name = "APA 7th"
    citation_style = "author-date"

    def _apa_name(self, name: str) -> str:
        """Last, A. A. 形式。姓+缩写（Smith J）→ Smith, J.；名+姓 → Last, F. M."""
        name = name.strip()
        if "," in name:
            # 已是 Last, A. 形式：补全缩写点
            last, first = name.split(",", 1)
            initials = " ".join(t.rstrip(".") + "." for t in first.split() if t)
            return f"{last.strip()}, {initials}".strip()
        if is_surname_initial(name):
            parts = name.split()
            last = parts[0]
            initials = "".join(p.rstrip(".") + "." for p in parts[1:] if p)
            return f"{last}, {initials}".strip()
        parts = name.split()
        if len(parts) <= 1:
            return name
        last = parts[-1]
        initials = "".join(p[0] + "." for p in parts[:-1] if p)
        return f"{last}, {initials}".strip()

    def _apa_authors(self, raw: str) -> str:
        names = split_author_list(raw)
        if not names:
            return ""
        converted = [self._apa_name(n) for n in names]
        if len(converted) <= 1:
            return converted[0]
        if len(converted) <= 20:
            if len(converted) == 2:
                return f"{converted[0]} & {converted[1]}"
            if len(converted) == 3:
                return f"{converted[0]}, {converted[1]}, & {converted[2]}"
            return ", ".join(converted[:-1]) + f", & {converted[-1]}"
        return ", ".join(converted[:19]) + ", … " + converted[-1]

    def format_journal(self, ref) -> str:
        authors = self._apa_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        journal = (ref.get("journal") or "").strip()
        vol = ref.get("volume") or ""
        issue = ref.get("issue") or ""
        pages = ref.get("pages") or ""
        doi = self._doi(ref)
        s = ""
        if authors:
            s += authors.rstrip(" .") + ". "
        if year:
            s += f"({year}). "
        if title:
            s += title + ". "
        if journal:
            s += f"*{journal}*"
            if vol:
                s += f", *{vol}*"
            if issue:
                s += f"({issue})"
            if pages:
                s += f", {pages}"
            s += ". "
        if doi:
            s += f"https://doi.org/{doi}"
        s = s.rstrip(" ") + ("." if not s.rstrip().endswith(".") else "")
        return s

    def format_book(self, ref) -> str:
        authors = self._apa_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        publisher = ref.get("publisher") or ""
        doi = self._doi(ref)
        s = ""
        if authors:
            s += authors.rstrip(" .") + ". "
        if year:
            s += f"({year}). "
        if title:
            s += f"*{title}*. "
        if publisher:
            s += publisher + ". "
        if doi:
            s += f"https://doi.org/{doi}"
        s = s.rstrip(" ")
        return s

    def format_conference(self, ref) -> str:
        authors = self._apa_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        conf = (ref.get("conference") or ref.get("journal") or "").strip()
        s = ""
        if authors:
            s += authors.rstrip(" .") + ". "
        if year:
            s += f"({year}). "
        if title:
            s += title + ". "
        if conf:
            s += conf + ". "
        return s.rstrip(" ")

    def format_thesis(self, ref) -> str:
        authors = self._apa_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        school = ref.get("school") or ref.get("publisher") or ""
        s = ""
        if authors:
            s += authors.rstrip(" .") + ". "
        if year:
            s += f"({year}). "
        if title:
            s += f"*{title}*"
            if school:
                s += f" [Doctoral dissertation, {school}]"
            s += ". "
        return s.rstrip(" ")

    def format_other(self, ref) -> str:
        s = super().format_other(ref)
        return s.rstrip(".")
