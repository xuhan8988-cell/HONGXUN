"""参考文献格式化引擎 - 统一入口。"""

import os

from .parser import DocumentParser
from .formatter import ReferenceFormatter
from .cross_ref import CrossReferenceManager
from .reorder import ReferenceReorder
from .validator import ReferenceValidator
from .utils.backup import create_backup


class RefFormatterEngine:
    """参考文献格式化引擎。

    用法：
        engine = RefFormatterEngine()
        engine.set_progress_callback(lambda r, m: print(r, m))
        stats = engine.format_document(input, output, options)
    """

    def __init__(self):
        self.parser = DocumentParser()
        self.formatter = ReferenceFormatter()
        self.cross_ref = CrossReferenceManager()
        self.reorder = ReferenceReorder()
        self.validator = ReferenceValidator()
        self.progress_callback = None

    def set_progress_callback(self, callback):
        """设置进度回调 callback(ratio: float, message: str)。"""
        self.progress_callback = callback

    def _progress(self, ratio, message):
        if self.progress_callback:
            try:
                self.progress_callback(ratio, message)
            except Exception:
                pass

    def format_document(self, input_path, output_path=None, options=None) -> dict:
        """
        格式化 Word 文档中的参考文献。

        options:
          - format_type: gbt7714/ieee/apa7/chicago/mla/harvard 或 "custom"
          - add_hyperlinks: 是否添加交叉引用超链接
          - superscript: 角标是否上标
          - reorder: 是否按引用顺序重排
          - merge_citations: 是否合并连续引用
          - backup: 是否备份原文件
          - validate: 是否校验
          - custom_rules: 自定义格式规则（LLM 增强，format_type="custom" 时使用）
          - llm_enhancer: RefLLMEnhancer 实例（可选）

        返回 stats 字典。
        """
        opt = {
            "format_type": "gbt7714",
            "add_hyperlinks": True,
            "superscript": True,
            "reorder": True,
            "merge_citations": True,
            "backup": True,
            "validate": True,
            "custom_rules": "",
            "llm_enhancer": None,
        }
        if options:
            opt.update(options)

        if not input_path or not os.path.exists(input_path):
            return {"success": False, "message": "输入文件不存在",
                    "errors": ["输入文件不存在"]}

        if output_path is None:
            stem, ext = os.path.splitext(input_path)
            output_path = f"{stem}_格式化{ext or '.docx'}"

        stats = {
            "citations_found": 0,
            "references_found": 0,
            "format_fixed": 0,
            "hyperlinks_added": False,
            "reordered": False,
            "warnings": [],
            "errors": [],
            "success": False,
            "message": "",
            "output_path": output_path,
            "backup_path": None,
        }

        try:
            # 1. 备份
            if opt["backup"]:
                self._progress(0.05, "正在备份原文件...")
                stats["backup_path"] = create_backup(input_path)

            # 2. 解析
            self._progress(0.15, "正在解析文档...")
            doc_data = self.parser.parse(input_path)
            stats["citations_found"] = len(doc_data.citations)
            stats["references_found"] = len(doc_data.references)

            if not doc_data.references and not doc_data.citations:
                stats["message"] = "未识别到正文引用或参考文献，请检查文档格式"
                stats["warnings"] = ["未识别到正文引用或参考文献"]
                # 仍保存一份（等价拷贝）
                self._copy_fallback(input_path, output_path)
                return stats

            # 3. 格式化
            self._progress(0.35, "正在格式化参考文献...")
            format_key = opt["format_type"]
            if format_key == "custom":
                formatted, fixed = self._format_custom(
                    doc_data.references, opt.get("custom_rules", ""),
                    opt.get("llm_enhancer"))
            else:
                formatted, fixed = self.formatter.format(doc_data.references, format_key)
            stats["format_fixed"] = fixed

            # 4. 重排
            order_map = None
            if opt["reorder"] and len(doc_data.citations) > 1:
                self._progress(0.55, "正在按引用顺序重排...")
                formatted, order_map = self.reorder.reorder(doc_data, formatted)
                stats["reordered"] = True

            # 5. 写回 + 交叉引用
            self._progress(0.75, "正在生成交叉引用...")
            if opt["add_hyperlinks"]:
                cr_stats = self.cross_ref.apply(
                    input_path, output_path, formatted, doc_data,
                    superscript=opt["superscript"],
                    order_map=order_map)
                stats["hyperlinks_added"] = cr_stats["hyperlinks_added"] > 0
            else:
                self.formatter.write_back(input_path, output_path, formatted,
                                          merge=opt["merge_citations"])

            # 6. 校验
            if opt["validate"]:
                self._progress(0.92, "正在校验...")
                v = self.validator.validate(output_path, format_key)
                stats["warnings"] = v.warnings
                stats["errors"] = v.errors

            self._progress(1.0, "完成")
            stats["success"] = True
            stats["message"] = "格式化完成"
            return stats

        except Exception as e:
            stats["success"] = False
            stats["message"] = str(e)
            stats["errors"].append(str(e))
            return stats

    def _format_custom(self, references, rules, enhancer):
        """LLM 自定义格式格式化。无 enhancer 或规则为空时回退 GB/T 7714。"""
        if enhancer is None or not (rules or "").strip():
            return self.formatter.format(references, "gbt7714")
        fixed = 0
        formatted = []
        for i, ref in enumerate(references, start=1):
            try:
                text = enhancer.format_with_custom_style(ref, rules)
            except Exception:
                text = self.formatter.format_single(ref, "gbt7714")
            if text and ref.get("raw") and text != ref.get("raw"):
                fixed += 1
            formatted.append(f"[{i}] {text}" if text else f"[{i}]")
        return formatted, fixed

    def _copy_fallback(self, input_path, output_path):
        import shutil
        try:
            shutil.copy2(input_path, output_path)
        except Exception:
            pass
