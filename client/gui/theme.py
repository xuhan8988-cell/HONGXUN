"""
鸿讯 HONGXUN · 主题系统
颜色、字体、图标常量与 ttk 样式表
"""

import sys
import tkinter as tk
from tkinter import font, ttk

# ======================================================================
# 版本标识（暂存于此供 gui_app 导入）
# ======================================================================
APP_NAME = "鸿讯 HONGXUN（郑州大学定制版）"
APP_VERSION = "1.0.0"
AUTO_UPDATER_VERSION = APP_VERSION

# ======================================================================
# 图标资源路径
# ======================================================================
import os
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_DIR = os.path.join(APP_DIR, "..", "logo")  # gui/../logo = client/logo
ICON_APP = os.path.join(LOGO_DIR, "zm.png")
ICON_TITLE = os.path.join(LOGO_DIR, "ztl.png")
ICON_SPLASH = os.path.join(LOGO_DIR, "qdy.png")
ICON_DIR = os.path.join(LOGO_DIR, "icons")

# ======================================================================
# 全局字体系统
# ======================================================================
FONT_BASE_SIZE = 13
FONT_TITLE_SIZE = 15
FONT_MIN_SIZE = 9
FONT_MAX_SIZE = 19
LAYOUT_SCALE_CAP = 1.35


def _ui_font_family() -> str:
    return "Microsoft YaHei" if sys.platform == "win32" else "PingFang SC"


def _ui_font_base() -> int:
    return 9 if sys.platform == "win32" else 13


def _ui_font_title() -> int:
    return 11 if sys.platform == "win32" else 15


FONT_BASE_SIZE = _ui_font_base()
FONT_TITLE_SIZE = _ui_font_title()
FONT_MIN_SIZE = 8
FONT_MAX_SIZE = 18


def _ui_mono_family() -> str:
    return "Consolas" if sys.platform == "win32" else "Menlo"


# 模块级字体变量声明（保持 None 初始值供 from-import 引用）
FONT_BODY = None
FONT_BODY_BOLD = None
FONT_HEADING = None
FONT_TITLE = None
FONT_CAPTION = None
FONT_MONO = None
FONT_LABEL = None
FONT_METRIC = None
FONT_DISPLAY = None


def init_fonts():
    global FONT_BODY, FONT_BODY_BOLD, FONT_HEADING, FONT_TITLE, FONT_CAPTION, FONT_MONO, FONT_LABEL, FONT_METRIC, FONT_DISPLAY
    _ff = _ui_font_family()
    FONT_BODY = font.Font(family=_ff, size=FONT_BASE_SIZE)
    FONT_BODY_BOLD = font.Font(family=_ff, size=FONT_BASE_SIZE, weight="bold")
    FONT_HEADING = font.Font(family=_ff, size=FONT_TITLE_SIZE if FONT_TITLE_SIZE > 12 else FONT_BASE_SIZE, weight="bold")
    FONT_TITLE = font.Font(family=_ff, size=FONT_TITLE_SIZE, weight="bold")
    FONT_CAPTION = font.Font(family=_ff, size=max(FONT_BASE_SIZE - 2, FONT_MIN_SIZE))
    FONT_MONO = font.Font(family=_ui_mono_family(), size=FONT_BASE_SIZE)
    FONT_LABEL = font.Font(family=_ff, size=FONT_BASE_SIZE, weight="bold")
    FONT_METRIC = font.Font(family=_ff, size=min(32, FONT_TITLE_SIZE * 2))
    FONT_DISPLAY = font.Font(family=_ff, size=min(28, FONT_TITLE_SIZE + 8), weight="bold")

    # 推送字体变量到所有依赖模块（from-import 在导入时拷贝 None）
    import sys as _sys
    _fnames = ('FONT_BODY', 'FONT_BODY_BOLD', 'FONT_HEADING', 'FONT_TITLE',
               'FONT_CAPTION', 'FONT_MONO', 'FONT_LABEL', 'FONT_METRIC', 'FONT_DISPLAY')
    _g = globals()
    for _mn in ('gui.widgets', 'gui.sidebar', 'gui.library_view', '__main__'):
        _m = _sys.modules.get(_mn)
        if _m:
            for _n in _fnames:
                setattr(_m, _n, _g[_n])


def update_font_scale(scale_factor):
    new_body = int(max(FONT_MIN_SIZE, min(FONT_MAX_SIZE, FONT_BASE_SIZE * scale_factor)))
    new_title = int(max(FONT_MIN_SIZE + 2, min(FONT_MAX_SIZE + 2, FONT_TITLE_SIZE * scale_factor)))
    new_caption = int(max(FONT_MIN_SIZE - 1, min(FONT_MAX_SIZE - 2, (FONT_BASE_SIZE - 1) * scale_factor)))

    FONT_BODY.configure(size=new_body)
    FONT_BODY_BOLD.configure(size=new_body, weight="bold")
    FONT_HEADING.configure(size=new_body, weight="bold")
    FONT_TITLE.configure(size=new_title, weight="bold")
    FONT_CAPTION.configure(size=new_caption)
    FONT_MONO.configure(size=new_body)


# ======================================================================
# 颜色系统
# ======================================================================
COLORS = {
    # ── 主色调（Tailwind Blue-600, 比 Apple Blue 更沉稳）──
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_active": "#1E40AF",
    "primary_light": "#DBEAFE",

    # ── 语义色 ──
    "success": "#16A34A",           # Green-600
    "success_light": "#DCFCE7",
    "warning": "#D97706",           # Amber-600
    "warning_light": "#FEF3C7",
    "danger": "#DC2626",            # Red-600
    "danger_light": "#FEE2E2",

    # ── 背景色（暖白基调，更适合长时间阅读）──
    "bg_page": "#FFFFFF",           # 纯白（原暖白 #F8F9FA，与侧栏拉大对比）
    "bg_card": "#FFFFFF",           # 卡片保持纯白
    "sidebar_bg": "#EAECEF",        # 更深暖灰侧栏（原 #F1F3F5，与页面 bg 拉开对比）
    "bg_input": "#FFFFFF",
    "bg_input_focus": "#FFFFFF",

    # ── 边框（更高对比度）──
    "border": "#C8CCD0",            # 暖灰边框
    "border_light": "#DEE0E3",      # 浅暖灰
    "input_border": "#D1D5DB",

    # ── 文字（更明显的对比度梯度）──
    "text_title": "#111827",        # Gray-900（原 #1D1D1F）
    "text_body": "#1F2937",         # Gray-800（原 #1D1D1F）
    "text_secondary": "#6B7280",    # Gray-500（原 #86868B）
    "text_hint": "#9CA3AF",         # Gray-400（原 #AEAEB2）

    # ── 交互状态 ──
    "selected_bg": "#DBEAFE",       # Blue-100（原 #E8F0FE）
    "selected_fg": "#1D4ED8",       # Blue-700（原 #007AFF）
    "hover_bg": "#F3F4F6",          # Gray-100（原 #E8E8ED）

    # ── 按钮 ──
    "btn_secondary_bg": "#FFFFFF",
    "btn_secondary_fg": "#1F2937",
    "btn_secondary_border": "#D1D5DB",

    # ── 状态指示 ──
    "dot_on": "#16A34A",
    "dot_off": "#9CA3AF",

    # ── 阴影（预乘混合色，针对 bg_page=#F8F9FA）──
    "shadow_1": "#ECECEF",           # 阴影层1（alpha 8%）
    "shadow_2": "#E7E7EA",           # 阴影层2（alpha 6%）
    "shadow_3": "#E2E2E5",           # 阴影层3（alpha 4%）

    # ── 标签/胶囊色 ──
    "pill_pending_bg": "#FEF3C7",
    "pill_pending_fg": "#92400E",
    "pill_read_bg": "#DCFCE7",
    "pill_read_fg": "#166534",
    "pill_excluded_bg": "#FEE2E2",
    "pill_excluded_fg": "#991B1B",

    # ── 任务卡片彩色边条 ──
    "task_accent_1": "#2563EB",
    "task_accent_2": "#7C3AED",
    "task_accent_3": "#059669",
    "task_accent_4": "#D97706",
    "task_accent_5": "#DC2626",
}

# ======================================================================
# Unicode 图标系统
# ======================================================================
ICONS = {
    "logo": "Ⲃⱘ",
    "feedback": "✉",
    "plus": "➕",
    "trash": "\U0001f5d1",
    "play": "▶",
    "pause": "⏸",
    "edit": "✎",
    "task": "\U0001f4cb",
    "journal": "\U0001f4d6",
    "tag": "\U0001f3f7",
    "calendar": "\U0001f4c5",
    "search": "\U0001f50d",
    "refresh": "↻",
    "save": "\U0001f4be",
    "clock": "⏱",
    "cancel": "✕",
    "email": "✉",
    "send": "\U0001f4e4",
    "key": "\U0001f511",
    "server": "\U0001f5a5",
    "inbox": "\U0001f4e5",
    "test": "✓",
    "info": "❓",
    "lock": "\U0001f512",
    "unlock": "\U0001f513",
    "coupon": "\U0001f39f",
    "gift": "\U0001f381",
    "update": "⬇",
    "receiver": "\U0001f465",
    "dot_on": "●",
    "dot_off": "○",
    "check": "✓",
    "warning": "⚠",
    "error": "✕",
    "arrow_right": "▸",
    "arrow_down": "▾",
}

# ======================================================================
# 邮箱 SMTP 供应商定义
# ======================================================================
SMTP_PROVIDERS = {
    "QQ邮箱": [
        {"server": "smtp.qq.com", "port": "465"},
        {"server": "smtp.qq.com", "port": "587"},
    ],
    "163邮箱": [
        {"server": "smtp.163.com", "port": "465"},
        {"server": "smtp.163.com", "port": "587"},
    ],
    "126邮箱": [
        {"server": "smtp.126.com", "port": "465"},
        {"server": "smtp.126.com", "port": "587"},
    ],
    "Google Gmail": [
        {"server": "smtp.gmail.com", "port": "465"},
        {"server": "smtp.gmail.com", "port": "587"},
    ],
    "新浪邮箱": [
        {"server": "smtp.sina.com", "port": "465"},
    ],
    "Outlook/Hotmail": [
        {"server": "smtp-mail.outlook.com", "port": "587"},
    ],
    "189邮箱": [
        {"server": "smtp.189.cn", "port": "465"},
    ],
}

EMAIL_DOMAIN_SMTP_MAP = {
    "qq.com": "smtp.qq.com",
    "foxmail.com": "smtp.qq.com",
    "163.com": "smtp.163.com",
    "126.com": "smtp.126.com",
    "yeah.net": "smtp.163.com",
    "gmail.com": "smtp.gmail.com",
    "sina.com": "smtp.sina.com",
    "sina.cn": "smtp.sina.com",
    "outlook.com": "smtp-mail.outlook.com",
    "hotmail.com": "smtp-mail.outlook.com",
    "189.cn": "smtp.189.cn",
}


def get_provider_configs(provider_name: str) -> list[dict]:
    return SMTP_PROVIDERS.get(provider_name, [])


def find_provider_by_server(server: str):
    for provider, configs in SMTP_PROVIDERS.items():
        if any(c["server"] == server for c in configs):
            return provider
    return None


def find_provider_by_domain(domain: str):
    expected_server = EMAIL_DOMAIN_SMTP_MAP.get(domain)
    if expected_server:
        return find_provider_by_server(expected_server)
    return None


LABEL_WIDTH = 16

# ======================================================================
# ttk 样式表
# ======================================================================
def _apply_styles():
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(".", font=FONT_BODY, background=COLORS["bg_page"])
    style.configure("TLabel", background=COLORS["bg_page"], foreground=COLORS["text_body"], font=FONT_BODY)
    style.configure("TFrame", background=COLORS["bg_page"])
    style.configure("TLabelframe", background=COLORS["bg_card"],
                    relief=tk.SOLID, borderwidth=1, bordercolor=COLORS["border"])
    style.configure("TLabelframe.Label", font=FONT_HEADING,
                    foreground=COLORS["text_title"], background=COLORS["bg_card"])
    style.configure("TSeparator", background=COLORS["border"])

    style.configure("TEntry",
                    fieldbackground=COLORS["bg_input"],
                    bordercolor=COLORS["input_border"],
                    padding=(10, 6),
                    borderwidth=1,
                    relief=tk.SOLID,
                    focusthickness=0,
                    font=FONT_BODY)
    style.map("TEntry",
              bordercolor=[("focus", COLORS["input_border"])],
              fieldbackground=[("focus", COLORS["bg_input_focus"])])

    style.configure("Horizontal.TProgressbar",
                    background=COLORS["primary"],
                    troughcolor=COLORS["bg_card"],
                    borderwidth=0,
                    thickness=10)

    style.configure("Primary.TButton",
                    font=FONT_BODY,
                    foreground="white",
                    background=COLORS["primary"],
                    borderwidth=0,
                    padding=(20, 8),
                    focusthickness=0)
    style.map("Primary.TButton",
              background=[("active", COLORS["primary_hover"]),
                          ("pressed", COLORS["primary_active"])],
              foreground=[("active", "white"), ("pressed", "white")])

    style.configure("Secondary.TButton",
                    font=FONT_BODY,
                    foreground=COLORS["btn_secondary_fg"],
                    background=COLORS["btn_secondary_bg"],
                    bordercolor=COLORS["btn_secondary_border"],
                    borderwidth=1,
                    relief=tk.SOLID,
                    padding=(20, 8),
                    focusthickness=0)
    style.map("Secondary.TButton",
              background=[("active", COLORS["bg_card"])],
              foreground=[("active", COLORS["btn_secondary_fg"])])

    style.configure("Danger.TButton",
                    font=FONT_BODY,
                    foreground=COLORS["danger"],
                    background=COLORS["btn_secondary_bg"],
                    bordercolor=COLORS["btn_secondary_border"],
                    borderwidth=1,
                    relief=tk.SOLID,
                    padding=(20, 8),
                    focusthickness=0)
    style.map("Danger.TButton",
              background=[("active", COLORS["danger_light"])],
              foreground=[("active", COLORS["danger"])])

    style.configure("Title.TLabel",
                    font=FONT_TITLE,
                    foreground=COLORS["text_title"],
                    background=COLORS["bg_page"])
    style.configure("Heading.TLabel",
                    font=FONT_HEADING,
                    foreground=COLORS["text_title"],
                    background=COLORS["bg_page"])
    style.configure("Caption.TLabel",
                    font=FONT_CAPTION,
                    foreground=COLORS["text_secondary"],
                    background=COLORS["bg_page"])
    style.configure("Card.TLabel",
                    background=COLORS["bg_card"],
                    foreground=COLORS["text_body"])
    style.configure("StatusBar.TLabel",
                    font=FONT_CAPTION,
                    foreground=COLORS["text_secondary"],
                    background=COLORS["bg_card"],
                    padding=(8, 2))

    style.configure("Switch.TCheckbutton",
                    font=FONT_BODY,
                    background=COLORS["bg_card"],
                    foreground=COLORS["text_body"])


# ======================================================================
# 颜色工具函数
# ======================================================================
def lerp_color(c1: str, c2: str, t: float) -> str:
    """线性插值两个十六进制颜色"""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"
