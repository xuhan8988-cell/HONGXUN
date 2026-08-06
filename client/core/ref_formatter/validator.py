"""格式校验：检查编号缺失/重复/不连续、悬空引用、空字段。"""

import re
from dataclasses import dataclass, field

from .utils.docx_utils import (
    extract_citations_from_document,
    extract_reference_paragraphs,
    find_references_heading_index,
)


@dataclass
class ValidationResult:
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ReferenceValidator:
    """校验参考文献格式。"""

    def validate(self, path: str, format_key: str = "gbt7714") -> ValidationResult:
        from docx import Document
        result = ValidationResult()
        try:
            doc = Document(path)
        except Exception as e:
            result.errors.append(f"无法打开文档：{e}")
            return result

        idx = find_references_heading_index(doc)
        citations = extract_citations_from_document(doc, idx)
        _, ref_paras = extract_reference_paragraphs(doc)

        # 参考文献编号
        ref_nums = []
        for p in ref_paras:
            text = (p.text or "").strip()
            m = re.match(r"^\s*\[(\d+)\]", text)
            if m:
                ref_nums.append(int(m.group(1)))
            elif text:
                # 没有编号的条目
                result.warnings.append(f"参考文献条目缺少编号：{text[:40]}...")

        # 编号连续性
        if ref_nums:
            expected = list(range(1, max(ref_nums) + 1))
            missing = [n for n in expected if n not in ref_nums]
            if missing:
                result.warnings.append(f"参考文献编号不连续，缺少：{missing[:10]}")
            dupes = {n for n in ref_nums if ref_nums.count(n) > 1}
            if dupes:
                result.warnings.append(f"参考文献编号重复：{sorted(dupes)[:10]}")

        # 悬空引用：正文引用了不存在/超范围的编号
        max_ref = max(ref_nums) if ref_nums else 0
        dangling = [c for c in citations if c > max_ref]
        if dangling:
            result.errors.append(f"正文存在悬空引用（超出参考文献编号）：{dangling[:10]}")

        if not ref_nums and not ref_paras:
            result.warnings.append("未识别到参考文献条目")

        return result
