"""IEEE 格式。"""

from .base import BaseReferenceFormatter, split_author_list, is_surname_initial


class IEEEFormatter(BaseReferenceFormatter):
    key = "ieee"
    name = "IEEE"
    citation_style = "numeric"

    def _ieee_name(self, name: str) -> str:
        """First Last → F. Last；Last, A. → A. Last；姓+缩写（Smith J）保持。"""
        name = name.strip()
        if "," in name:
            last, first = name.split(",", 1)
            last = last.strip()
            first = first.strip()
        elif is_surname_initial(name):
            return name
        else:
            parts = name.split()
            if len(parts) <= 1:
                return name
            first = " ".join(parts[:-1])
            last = parts[-1]
        if not first:
            return last
        initials = []
        for tok in first.replace(".", " ").split():
            if not tok:
                continue
            initials.append(tok[0].upper() + ".")
        return f"{' '.join(initials)} {last}".strip()

    def _ieee_authors(self, raw: str) -> str:
        names = split_author_list(raw)
        if not names:
            return ""
        max_show = 6
        converted = [self._ieee_name(n) for n in names]
        if len(converted) <= max_show:
            return ", ".join(converted)
        return ", ".join(converted[:max_show]) + ", et al."

    def format_journal(self, ref) -> str:
        # A. Author, "Title," Journal, vol. X, no. Y, pp. Z, Year.
        authors = self._ieee_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        journal = (ref.get("journal") or "").strip()
        vol = ref.get("volume") or ""
        issue = ref.get("issue") or ""
        pages = ref.get("pages") or ""
        year = ref.get("year") or ""
        s = ""
        if authors:
            s += authors + ", "
        if title:
            s += f'"{title}," '
        parts = []
        if journal:
            parts.append(journal)
        if vol:
            parts.append(f"vol. {vol}")
        if issue:
            parts.append(f"no. {issue}")
        if pages:
            parts.append(f"pp. {pages}")
        if year:
            parts.append(str(year))
        if parts:
            s += ", ".join(parts)
        s = s.rstrip(".,; ") + "."
        return s

    def format_book(self, ref) -> str:
        authors = self._ieee_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        year = ref.get("year") or ""
        publisher = ref.get("publisher") or ""
        s = ""
        if authors:
            s += authors + ", "
        if title:
            s += f"*{title}*, "
        parts = []
        if publisher:
            parts.append(publisher)
        if year:
            parts.append(str(year))
        if parts:
            s += ", ".join(parts)
        s = s.rstrip(".,; ") + "."
        return s

    def format_conference(self, ref) -> str:
        authors = self._ieee_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        conf = (ref.get("conference") or ref.get("journal") or "").strip()
        pages = ref.get("pages") or ""
        year = ref.get("year") or ""
        s = ""
        if authors:
            s += authors + ", "
        if title:
            s += f'"{title}," '
        parts = []
        if conf:
            parts.append(conf)
        if pages:
            parts.append(f"pp. {pages}")
        if year:
            parts.append(str(year))
        if parts:
            s += ", ".join(parts)
        s = s.rstrip(".,; ") + "."
        return s

    def format_thesis(self, ref) -> str:
        authors = self._ieee_authors(ref.get("authors", ""))
        title = (ref.get("title") or "").strip()
        year = ref.get("year") or ""
        school = ref.get("school") or ref.get("publisher") or ""
        s = ""
        if authors:
            s += authors + ", "
        if title:
            s += f'"{title}, " '
        s += f"{school or ''}, {year}".strip().rstrip(", ") + "."
        return s

    def format_other(self, ref) -> str:
        s = super().format_other(ref)
        return s.rstrip(".") + "."
