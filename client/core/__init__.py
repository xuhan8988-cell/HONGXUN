# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 论文监控工具 — 核心模块
版本 1.1.0 · 软件著作权登记版

模块划分:
  - config_manager: 配置读写、输入校验、路径常量
  - session:        共享 HTTP Session + 代理清理
  - search:         CrossRef 检索 + ISSN 解析
  - abstract:       六级摘要补全流水线
  - coupon_manager: 礼品券管理（永久有效）
  - translator:     DeepSeek AI 翻译（英→中）
  - email_sender:   邮件发送
  - code_protector: 底层代码保护
  - engine:         编排协调层（run_history_search / run_increment_check）

调整某个功能只需修改对应模块：
  - 检索逻辑 → search.py
  - 摘要补全 → abstract.py（增删级别/换 API）
  - 礼品券 → coupon_manager.py
  - 邮件推送 → email_sender.py
  - 代码保护 → code_protector.py
  - 报告格式 → engine.py
"""
__version__ = "2.0.0"

# 配置层
from .config_manager import (
    DATA_DIR, OUTPUT_DIR, UNSENT_DIR, TASKS_FILE, EMAIL_FILE, RECORDS_FILE,
    SCHEDULER_PID_FILE, SCHEDULER_STOP_FILE, SCHEDULER_LOG_FILE,
    load_all_tasks, save_task, delete_task, get_task,
    load_email_config, save_email_config,
    load_email_data, save_email_data,
    load_push_records, add_push_record,
    validate_journals, validate_keywords, validate_date_range, validate_email_config,
    validate_receivers, validate_keywords2,
    load_app_config, save_app_config,
)

# 检索引擎（编排层）
# 惰性导入：engine → search → session → requests 冷加载约 330ms。用模块级
# __getattr__ 推迟到真正访问时才导入，加快应用启动（requests/urllib3 不必在启动阶段加载）。
_ENGINE_NAMES = {
    "run_history_search", "run_increment_check", "send_combined_email",
    "cancel_current_search", "reset_search_cancel", "is_search_cancelled",
    "register_search_cancel", "unregister_search_cancel", "cancel_search",
}
_LAZY_SUBMODULES = {"search", "abstract", "translator", "library", "email_sender"}


def __getattr__(name):
    if name in _ENGINE_NAMES:
        from . import engine as _engine
        return getattr(_engine, name)
    if name in _LAZY_SUBMODULES:
        import importlib
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# 礼品券 & 许可管理
from . import coupon_manager

# 代码保护
from . import code_protector

# 自动更新
from . import auto_updater

# 引入调度守护进程 launchd 管理
# (launchd 函数由 gui_app.py 直接从 scheduler_daemon 导入，无需经此中转)
# search / abstract / email_sender / library / translator 经模块级 __getattr__ 惰性提供，
# 避免启动阶段冷加载 requests/urllib3。
from .journal_store import JournalStore
