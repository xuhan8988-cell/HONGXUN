"""顺序重排：按正文首次出现顺序重排参考文献并重编号。"""


class ReferenceReorder:
    """按正文引用首次出现顺序重排。"""

    def reorder(self, doc_data, formatted_refs: list[str]):
        """返回 (重排后的条目列表, old→new 映射)。"""
        citations = doc_data.citations
        if not citations:
            return formatted_refs, {}
        # 首次出现顺序：引用编号 → 新编号（1-based）
        order_map = {}
        new_num = 1
        for c in citations:
            if c not in order_map:
                order_map[c] = new_num
                new_num += 1
        # 补齐未在正文出现的引用（保持相对顺序，追加到末尾）
        n = len(formatted_refs)
        for old in range(1, n + 1):
            if old not in order_map:
                order_map[old] = new_num
                new_num += 1
        # 重排条目
        renumbered = [None] * len(formatted_refs)
        for old, new in order_map.items():
            if 1 <= old <= len(formatted_refs) and new - 1 < len(renumbered):
                text = formatted_refs[old - 1]
                # 替换开头的 [old]
                import re
                text = re.sub(r"^\s*\[\d+\]\s*", f"[{new}] ", text)
                renumbered[new - 1] = text
        renumbered = [r for r in renumbered if r]
        return renumbered, order_map
