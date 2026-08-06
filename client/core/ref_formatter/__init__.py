"""
鸿讯 HONGXUN · 论文格式修改助手 — 核心引擎包

纯代码参考文献格式化引擎（不依赖 Tkinter）：
  - 解析 Word 文档中的正文引用与参考文献条目
  - 6 种标准格式转换（GB/T 7714 / IEEE / APA 7th / Chicago / MLA / Harvard）
  - 交叉引用超链接（Ctrl+Click 跳转）、角标上标、按引用顺序重排、连续引用合并
  - 自动备份、格式校验、可选 LLM 自定义格式解析与智能修复

统一入口：RefFormatterEngine.format_document(...)
"""

from .engine import RefFormatterEngine

__version__ = "1.0.0"
