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
APP_NAME = "鸿讯 HONGXUN"
APP_VERSION = "2.0.0"
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
    FONT_DISPLAY = font.Font(family=_ff, size=min(32, FONT_TITLE_SIZE + 10), weight="bold")

    # 推送字体变量到所有依赖模块（from-import 在导入时拷贝 None）
    import sys as _sys
    _fnames = ('FONT_BODY', 'FONT_BODY_BOLD', 'FONT_HEADING', 'FONT_TITLE',
               'FONT_CAPTION', 'FONT_MONO', 'FONT_LABEL', 'FONT_METRIC', 'FONT_DISPLAY')
    _g = globals()
    for _mn in ('gui.widgets', 'gui.sidebar', 'gui.library_view', 'gui.dashboard', 'gui_app', '__main__'):
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
    # ── 主色调（Tailwind Blue-500 为基准，更通透）──
    "primary": "#3B82F6",           # Blue-500（主色，更亮更通透）
    "primary_2": "#60A5FA",         # Blue-400（渐变起始，更柔和）
    "primary_hover": "#2563EB",     # Blue-600（hover 态）
    "primary_active": "#1D4ED8",    # Blue-700（active 态）
    "primary_light": "#DBEAFE",     # Blue-100（选中背景）
    "primary_focus_ring": "#BFDBFE",  # Blue-200（聚焦光晕）

    # ── 语义色（500 色阶）──
    "success": "#10B981",           # Emerald-500
    "success_light": "#D1FAE5",     # Emerald-100
    "warning": "#F59E0B",           # Amber-500
    "warning_light": "#FEF3C7",     # Amber-100
    "danger": "#EF4444",            # Red-500
    "danger_light": "#FEE2E2",      # Red-100

    # ── 背景色（冷色调基调）──
    "bg_page": "#F8FAFC",           # Slate-50（和侧栏统一，让白色卡片浮起来）
    "bg_card": "#FFFFFF",           # 卡片纯白（浮在浅灰蓝背景上）
    "sidebar_bg": "#F1F5F9",        # Slate-100（侧栏稍深）
    "bg_input": "#FFFFFF",
    "bg_input_focus": "#FFFFFF",

    # ── 边框（冷灰）──
    "border": "#E2E8F0",            # Slate-200（卡片边框）
    "border_light": "#F1F5F9",      # Slate-100（分割线）
    "input_border": "#CBD5E1",      # Slate-300

    # ── 文字 ──
    "text_title": "#0F172A",        # Slate-900（标题，最深）
    "text_body": "#1E293B",         # Slate-800（正文）
    "text_secondary": "#64748B",    # Slate-500（次要文字）
    "text_hint": "#94A3B8",         # Slate-400（提示文字）

    # ── 交互状态 ──
    "selected_bg": "#DBEAFE",       # Blue-100
    "selected_fg": "#1D4ED8",       # Blue-700
    "hover_bg": "#F1F5F9",          # Slate-100

    # ── 导航 ──
    "nav_active_bg": "#EFF6FF",     # Blue-50（导航选中底色）
    "nav_hover_bg": "#F8FAFC",      # 导航悬停底色（极浅冷灰）

    # ── 按钮 ──
    "btn_secondary_bg": "#FFFFFF",
    "btn_secondary_fg": "#0F172A",  # Slate-900，更深，接近纯黑
    "btn_secondary_border": "#CBD5E1",

    # ── 状态指示 ──
    "dot_on": "#10B981",
    "dot_off": "#94A3B8",

    # ── 阴影（3 层叠色，更柔和，针对白底）──
    "shadow_1": "#E2E8F0",           # 最顶层（近边缘，更浅）
    "shadow_2": "#EEF2F7",           # 中间层（中等扩散）
    "shadow_3": "#F8FAFC",           # 最底层（大面积柔和，几乎看不见）

    # ── 标签/胶囊色 ──
    "pill_pending_bg": "#FEF3C7",
    "pill_pending_fg": "#B45309",
    "pill_read_bg": "#D1FAE5",
    "pill_read_fg": "#065F46",
    "pill_excluded_bg": "#FEE2E2",
    "pill_excluded_fg": "#B91C1C",

    # ── 任务卡片彩色边条 ──
    "task_accent_1": "#3B82F6",
    "task_accent_2": "#8B5CF6",
    "task_accent_3": "#10B981",
    "task_accent_4": "#F59E0B",
    "task_accent_5": "#EF4444",

    # ── 滚动条 ──
    "scrollbar_bg": "#F1F5F9",      # 滚动条背景
    "scrollbar_thumb": "#CBD5E1",   # 滑块
    "scrollbar_thumb_hover": "#94A3B8",  # 滑块 hover
}

# ======================================================================
# 分级圆角系统
# ======================================================================
RADIUS_LG = 16      # 大卡片（主内容卡）
RADIUS_MD = 12      # 小卡片（侧栏、元数据卡）
RADIUS_SM = 8       # 按钮 / 输入框
RADIUS_PILL = 999   # 标签 / 胶囊

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
    # ── 导航 / Lucide 风格图标键（优先查 PNG，emoji 作回退）──
    "dashboard": "\U0001f4ca",
    "settings": "⚙",
    "bell": "\U0001f514",
    "folder": "\U0001f4c2",
    "layers": "\U0001f5c3",
    "users": "\U0001f465",
    "external": "↗",
    "copy": "\U0001f4cb",
    "history": "↺",
    "send": "\U0001f4e4",
    "arrow_up": "↑",
    "download": "⬇",
    "help": "?",
    "alert": "⚠",
    "monitor": "\U0001f4cb",
    "library": "\U0001f4da",
    "export": "↗",
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


def gradient_stops(c1: str, c2: str, steps: int = 6) -> list[str]:
    """生成 c1 → c2 的渐变色阶列表（自上而下）"""
    if steps < 2:
        return [c1]
    return [lerp_color(c1, c2, i / (steps - 1)) for i in range(steps)]
