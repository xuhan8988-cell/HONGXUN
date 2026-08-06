"""MLA 9th 格式。"""

from .base import BaseReferenceFormatter, split_author_list, is_surname_initial


class MLAFormatter(BaseReferenceFormatter):
    key = "mla"
    name = "MLA 9th"
    citation_style = "author-page"

    def _mla_name(self, name: str) -> str:
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

    def _mla_authors(self, raw: str) -> str:
        names = split_author_list(raw)
        if not names:
            return ""
        converted = [self._mla_name(n) for n in names]
        if len(converted) <= 1:
            return converted[0]
        if len(converted) == 2:
            return f"{converted[0]} and {converted[1]}"
        if len(converted) == 3:
            return f"{converted[0]}, {converted[1]}, and {converted[2]}"
        return f"{converted[0]}, et al."

    def format_journal(self, ref) -> str:
        # Author. "Title." Journal, vol. V, no. I, Year, pp. P.
        authors = self._mla_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        journal = (ref.get("journal") or "").strip()
        vol = ref.get("volume") or ""
        issue = ref.get("issue") or ""
        pages = ref.get("pages") or ""
        year = ref.get("year") or ""
        s = ""
        if authors:
            s += authors + ". "
        if title:
            s += f'"{title}." '
        parts = []
        if journal:
            parts.append(f"*{journal}*")
        if vol:
            parts.append(f"vol. {vol}")
        if issue:
            parts.append(f"no. {issue}")
        if year:
            parts.append(str(year))
        if pages:
            parts.append(f"pp. {pages}")
        if parts:
            s += ", ".join(parts)
        s = s.rstrip(".,; ") + "."
        return s

    def format_book(self, ref) -> str:
        authors = self._mla_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        year = ref.get("year") or ""
        publisher = ref.get("publisher") or ""
        s = ""
        if authors:
            s += authors + ". "
        if title:
            s += f"*{title}*. "
        if publisher:
            s += publisher + ", "
        if year:
            s += str(year)
        s = s.rstrip(".,; ") + "."
        return s

    def format_conference(self, ref) -> str:
        authors = self._mla_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        conf = (ref.get("conference") or ref.get("journal") or "").strip()
        year = ref.get("year") or ""
        s = ""
        if authors:
            s += authors + ". "
        if title:
            s += f'"{title}." '
        parts = []
        if conf:
            parts.append(conf)
        if year:
            parts.append(str(year))
        if parts:
            s += ", ".join(parts)
        s = s.rstrip(".,; ") + "."
        return s

    def format_thesis(self, ref) -> str:
        authors = self._mla_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        year = ref.get("year") or ""
        school = ref.get("school") or ref.get("publisher") or ""
        s = ""
        if authors:
            s += authors + ". "
        if title:
            s += f'"{title}." '
        if school:
            s += school + ", "
        if year:
            s += str(year)
        s = s.rstrip(".,; ") + "."
        return s

    def format_other(self, ref) -> str:
        s = super().format_other(ref)
        return s.rstrip(".")
