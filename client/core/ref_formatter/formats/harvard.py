"""Harvard（作者-年份，作者-日期参考文献表）。"""

from .base import BaseReferenceFormatter, split_author_list, is_surname_initial


class HarvardFormatter(BaseReferenceFormatter):
    key = "harvard"
    name = "Harvard"
    citation_style = "author-date"

    def _harvard_name(self, name: str) -> str:
        """Last, A. 形式。姓+缩写（Smith J）→ Smith, J；名+姓 → Last, First。"""
        name = name.strip()
        if "," in name:
            return name
        if is_surname_initial(name):
            parts = name.split()
            return (parts[0] + ", " + " ".join(parts[1:])).strip()
        parts = name.split()
        if len(parts) <= 1:
            return name
        last = parts[-1]
        first = " ".join(parts[:-1])
        return f"{last}, {first}".strip()

    def _harvard_authors(self, raw: str) -> str:
        names = split_author_list(raw)
        if not names:
            return ""
        converted = [self._harvard_name(n) for n in names]
        if len(converted) <= 1:
            return converted[0]
        if len(converted) == 2:
            return f"{converted[0]} and {converted[1]}"
        if len(converted) == 3:
            return f"{converted[0]}, {converted[1]} and {converted[2]}"
        return ", ".join(converted[:3]) + " et al."

    def format_journal(self, ref) -> str:
        # Author (Year) 'Title', Journal, V(I), pp. P.
        authors = self._harvard_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        journal = (ref.get("journal") or "").strip()
        vol = ref.get("volume") or ""
        issue = ref.get("issue") or ""
        pages = ref.get("pages") or ""
        s = ""
        if authors:
            s += authors + " "
        if year:
            s += f"({year}) "
        if title:
            s += f"'{title}', "
        parts = []
        if journal:
            parts.append(f"*{journal}*")
        if vol:
            parts.append(str(vol))
        if issue:
            parts.append(f"({issue})")
        if parts:
            s += ", ".join(parts)
        if pages:
            s += f", pp. {pages}"
        s = s.rstrip(".,; ") + "."
        return s

    def format_book(self, ref) -> str:
        authors = self._harvard_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        publisher = ref.get("publisher") or ""
        s = ""
        if authors:
            s += authors + " "
        if year:
            s += f"({year}) "
        if title:
            s += f"*{title}*. "
        if publisher:
            s += publisher + "."
        return s.rstrip(" ,.")

    def format_conference(self, ref) -> str:
        authors = self._harvard_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        conf = (ref.get("conference") or ref.get("journal") or "").strip()
        s = ""
        if authors:
            s += authors + " "
        if year:
            s += f"({year}) "
        if title:
            s += f"'{title}', "
        if conf:
            s += conf + "."
        return s.rstrip(" ,.")

    def format_thesis(self, ref) -> str:
        authors = self._harvard_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        school = ref.get("school") or ref.get("publisher") or ""
        s = ""
        if authors:
            s += authors + " "
        if year:
            s += f"({year}) "
        if title:
            s += f"'{title}', "
        if school:
            s += school + "."
        return s.rstrip(" ,.")

    def format_other(self, ref) -> str:
        s = super().format_other(ref)
        return s.rstrip(".")
