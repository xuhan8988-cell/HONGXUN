"""Chicago 17th（作者-年份参考文献表）。"""

from .base import BaseReferenceFormatter, split_author_list, is_surname_initial


class ChicagoFormatter(BaseReferenceFormatter):
    key = "chicago"
    name = "Chicago 17th"
    citation_style = "author-date"

    def _chicago_name(self, name: str) -> str:
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

    def _chicago_authors(self, raw: str) -> str:
        names = split_author_list(raw)
        if not names:
            return ""
        converted = [self._chicago_name(n) for n in names]
        if len(converted) <= 1:
            return converted[0]
        if len(converted) <= 10:
            if len(converted) == 2:
                return f"{converted[0]} and {converted[1]}"
            if len(converted) == 3:
                return f"{converted[0]}, {converted[1]}, and {converted[2]}"
            return ", ".join(converted[:-1]) + f", and {converted[-1]}"
        return ", ".join(converted[:7]) + ", et al."

    def format_journal(self, ref) -> str:
        # Author. Year. "Title." Journal V (I): pages.
        authors = self._chicago_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        journal = (ref.get("journal") or "").strip()
        vol = ref.get("volume") or ""
        issue = ref.get("issue") or ""
        pages = ref.get("pages") or ""
        doi = self._doi(ref)
        s = ""
        if authors:
            s += authors + ". "
        if year:
            s += f"{year}. "
        if title:
            s += f'"{title}." '
        if journal:
            s += f"*{journal}*"
            if vol:
                s += f" {vol}"
            if issue:
                s += f" ({issue})"
            if pages:
                s += f": {pages}"
            s += ". "
        if doi:
            s += f"https://doi.org/{doi}"
        s = s.rstrip(" ") + ("." if not s.rstrip().endswith(".") else "")
        return s

    def format_book(self, ref) -> str:
        authors = self._chicago_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        publisher = ref.get("publisher") or ""
        edition = ref.get("edition") or ""
        s = ""
        if authors:
            s += authors + ". "
        if year:
            s += f"{year}. "
        if title:
            s += f"*{title}*. "
        if edition:
            s += f"{edition}. "
        if publisher:
            s += publisher + ". "
        return s.rstrip(" ")

    def format_conference(self, ref) -> str:
        authors = self._chicago_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        conf = (ref.get("conference") or ref.get("journal") or "").strip()
        s = ""
        if authors:
            s += authors + ". "
        if year:
            s += f"{year}. "
        if title:
            s += f'"{title}." '
        if conf:
            s += conf + ". "
        return s.rstrip(" ")

    def format_thesis(self, ref) -> str:
        authors = self._chicago_authors(ref.get("authors", ""))
        year = ref.get("year") or ""
        title = (ref.get("title") or "").strip()
        school = ref.get("school") or ref.get("publisher") or ""
        s = ""
        if authors:
            s += authors + ". "
        if year:
            s += f"{year}. "
        if title:
            s += f'"{title}." '
        if school:
            s += f"{school}. "
        return s.rstrip(" ")

    def format_other(self, ref) -> str:
        s = super().format_other(ref)
        return s.rstrip(".")
