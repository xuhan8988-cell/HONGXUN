# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 论文监控工具 v1.0.0
软件著作权登记版 · GUI 主程序（礼品券激活版）

版本历程:
  v1.0.0 — 首版发布，礼品券激活、AI翻译、七级摘要补全
"""

import sys
import os

# Enable Windows high-DPI support (must be before tkinter import)
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import tkinter as tk
from tkinter import ttk, font, messagebox, simpledialog, scrolledtext
import uuid
import base64
from datetime import datetime, timedelta
import threading
import time
import subprocess
import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import re, textwrap, signal
import logging

logger = logging.getLogger("HONGXUN")
if not logger.handlers:
    logger.setLevel(logging.WARNING)
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_handler)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gui.theme import (
    APP_NAME, APP_VERSION, AUTO_UPDATER_VERSION,
    LOGO_DIR, ICON_APP, ICON_TITLE, ICON_SPLASH, ICON_DIR,
    COLORS, ICONS, SMTP_PROVIDERS, EMAIL_DOMAIN_SMTP_MAP,
    get_provider_configs, find_provider_by_server, find_provider_by_domain,
    LABEL_WIDTH,
    FONT_BODY, FONT_BODY_BOLD, FONT_HEADING, FONT_TITLE,
    FONT_CAPTION, FONT_MONO, FONT_LABEL,
    FONT_BASE_SIZE, FONT_TITLE_SIZE, FONT_MIN_SIZE, FONT_MAX_SIZE, LAYOUT_SCALE_CAP,
    init_fonts, update_font_scale, _apply_styles, lerp_color,
    _ui_font_family, _ui_mono_family,
)
from core import (
    load_all_tasks, save_task, delete_task, get_task,
    load_email_config, save_email_config,
    load_email_data, save_email_data,
    load_app_config, save_app_config,
    SCHEDULER_PID_FILE, SCHEDULER_STOP_FILE, SCHEDULER_LOG_FILE,
    UNSENT_DIR,
    validate_journals, validate_keywords, validate_date_range, validate_email_config,
    validate_receivers,
    add_push_record,
    coupon_manager,
    code_protector,
    auto_updater,
)
# 检索/引擎函数（run_history_search 等）经 core.__getattr__ 惰性导入，
# 避免启动阶段冷加载 requests/urllib3（约 330ms）。使用时在函数内：
#   from core import run_history_search
from core.journal_store import JournalStore
from gui.widgets import (
    ModernEntry, PlaceholderEntry, CollapsibleFrame, ToggleSwitch,
    RoundedCard, ModernButton, StatusPill, IconLabel,
    IconCache, SkeletonLoader, EmptyState, attach_focus_ring,
    ModernScrollbar, smooth_wheel_handler,
)
from gui.sidebar import TaskSidebar
from gui.library_view import LibraryView
from gui.ref_formatter_view import RefFormatterView
from gui.dashboard import DashboardView
IconCache.init(ICON_DIR)

# 开机自启管理（scheduler_daemon 与 gui_app.py 同级）
from scheduler_daemon import (
    install_launchd, uninstall_launchd, is_launchd_installed,
    install_windows_startup, uninstall_windows_startup, is_windows_startup_installed,
)
# APP_NAME, APP_VERSION, COLORS, ICONS, FONTS, SMTP_PROVIDERS, styles → now in gui/theme.py
# APP_DIR for local file discovery
APP_DIR = os.path.dirname(os.path.abspath(__file__))


# PlaceholderEntry, CollapsibleFrame, ToggleSwitch → now in gui/widgets.py


# ======================================================================
# 主应用
# ======================================================================

def _simple_card(master):
    """普通白底圆角边框卡片，替代 RoundedCard（规避其 fit_content 布局 bug）。

    RoundedCard(fit_content=True) 用 canvas.create_window 固定 content 尺寸，
    导致内部 pack 子组件塌缩成 1x1（设置/监控页内容不可见的根源）。
    这里用普通 Frame + 细边框实现同等外观，content 正常 pack 布局。
    """
    card = tk.Frame(master, bg=COLORS["bg_card"], highlightthickness=1,
                    highlightbackground=COLORS["border"])
    card.content = tk.Frame(card, bg=COLORS["bg_card"])
    card.content.pack(fill=tk.BOTH, expand=True)
    return card


class PaperMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("鸿讯 · 论文监控工具")
        self.root.geometry("1080x720")
        self.root.minsize(900, 640)
        self.root.configure(bg=COLORS["bg_page"])

        # 先隐藏主窗口，显示启动页
        self.root.withdraw()
        self._icon_refs = []  # 强引用图片对象，防止GC回收
        self._scaled_icon_cache = {}  # (path, size) → PhotoImage，避免重复 PIL 缩放
        self._scale = 1.0  # 当前缩放系数，用于缩放布局间距

        self.current_task_id = None
        self._scheduler_process: subprocess.Popen | None = None
        self._scheduler_daemon_running = False
        self._executing = False
        self._history_running = False
        self._increment_running = False
        self._base_window_width = 1080
        self._resize_timer = None
        self._last_scale = 1.0
        self._activation_cache = None  # 会话级激活缓存

        # 进度条主人制（允许 "history" / "startup_mail" / None）
        self._progress_owner: str | None = None
        self._progress_lock = threading.Lock()
        self._deferred_progress: list[tuple[float, str]] = []

        init_fonts()
        _apply_styles()

        # Apply DPI-aware initial font scaling
        self.root.update_idletasks()
        try:
            init_w = self.root.winfo_width()
            if init_w > 100:
                scale = min(init_w / self._base_window_width, LAYOUT_SCALE_CAP)
                if abs(scale - 1.0) > 0.05:
                    update_font_scale(scale)
                    self._last_scale = scale
                    self._scale = scale
        except Exception:
            pass

        # 构建完成后应用布局缩放
        def _apply_initial_layout():
            if hasattr(self, '_scale'):
                self._scale_layout(self._scale)
        self.root.after(100, _apply_initial_layout)

        # 显示启动页并强制渲染，让用户立即看到启动画面
        self._show_splash()
        self.root.update_idletasks()

        # 初始化 auto_updater
        try:
            base_dir = coupon_manager.BASE_DIR
            auto_updater.init(base_dir, APP_VERSION)
        except Exception:
            pass

        # 启动时锁定所有受保护文件（仅首次初始化 manifest）
        try:
            if not os.path.exists(code_protector.MANIFEST_FILE):
                code_protector.save_manifest()
                code_protector.lock_all_protected_files()
        except Exception:
            pass

        # 后台构建主UI（使用 after_idle 让事件循环先绘制启动页）
        def _build_and_finish():
            try:
                self._build_ui()
                # 窗口图标（macOS iconphoto 同步 Dock 交互很慢，约 3.5s），
                # 延后到启动页关闭后再异步设置，避免阻塞首次渲染。
                self._refresh_task_list()
                self._refresh_status_bar()

                # 绑定事件
                self.root.bind("<Configure>", self._on_window_resize)
                self.root.bind("<Command-n>", lambda e: self._new_task())
                self.root.bind("<Command-s>", lambda e: self._save_task())
                self.root.bind("<Control-n>", lambda e: self._new_task())
                self.root.bind("<Control-s>", lambda e: self._save_task())
        # 删除快捷键绑定移到 sidebar 上

                self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

                # 延迟关闭启动页，让 UI 有时间渲染
                self.root.after(800, self._close_splash)

                # 启动页关闭后再设置窗口图标（macOS iconphoto 很慢，延后避免阻塞）
                self.root.after(900, self._load_window_icons)

                # 邮箱配置加载含许可状态刷新（会触发网络时间校验，约 1-2s），
                # 延后到启动页关闭后执行，避免阻塞首次渲染。
                self.root.after(1000, self._load_email_config)

                # 启动后检查未发送附件
                self.root.after(2000, self._check_unsent_attachments)

                # 启动后检查
                self.root.after(1200, self._check_resume_on_startup)
                self.root.after(1500, self._check_scheduler_daemon_status)
                self.root.after(1800, self._check_trial_status_at_startup)
                self.root.after(5000, self._check_update_auto)
                self.root.after(10000, self._poll_daemon_result)
                # LLM API 可用性检测（异步，不阻塞启动）
                self.root.after(3500, self._check_llm_api_on_startup)
                # 订阅/礼品券到期检测（自动关停受限功能）
                self.root.after(2500, self._check_expiry_on_startup)
                # 刷新状态栏登录状态；未登录则延迟提示可登录
                self.root.after(1300, self._refresh_login_status)
                self.root.after(2000, self._maybe_prompt_login)
            except Exception:
                # 防止构建 UI 异常导致启动页永远不关闭
                import traceback
                traceback.print_exc()
                self._close_splash()

        # 安全兜底：5 秒后无论是否构建完成都关闭启动页
        self.root.after(5000, self._close_splash)

        # 后台预热网络时间缓存：让 _build_and_finish 里的 _load_email_config
        # 不再同步等待网络（首次 _get_network_time 约 1.5s），加速启动。
        try:
            coupon_manager.prewarm_network_time()
        except Exception:
            pass

        self.root.after_idle(_build_and_finish)

    # ===================== 启动页实现 =====================
    def _show_splash(self):
        """创建并显示启动页（先渲染文字，图片异步加载）"""
        self.splash = tk.Toplevel(self.root)
        self.splash.overrideredirect(True)  # 无边框
        self.splash.configure(bg=COLORS["bg_page"])

        # 居中显示
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        splash_w = 420
        splash_h = 320
        x = (screen_w - splash_w) // 2
        y = (screen_h - splash_h) // 2
        self.splash.geometry(f"{splash_w}x{splash_h}+{x}+{y}")

        # 先渲染文字部分，毫秒级显示
        logo_text = tk.Label(self.splash, text=ICONS["logo"],
                             font=(_ui_font_family(), 64, "bold"),
                             fg=COLORS["primary"],
                             bg=COLORS["bg_page"])
        logo_text.pack(pady=(60, 20))
        self._splash_logo_label = logo_text

        tk.Label(self.splash, text="科研论文助手",
                 font=FONT_TITLE,
                 fg=COLORS["text_title"],
                 bg=COLORS["bg_page"]).pack(pady=(0, 8))
        tk.Label(self.splash, text="正在加载...",
                 font=FONT_CAPTION,
                 fg=COLORS["text_secondary"],
                 bg=COLORS["bg_page"]).pack()

        # 细边框
        self.splash.configure(highlightbackground=COLORS["border"], highlightthickness=1)

        # 强制立即渲染启动页，确保用户看到
        self.splash.update_idletasks()

        # 异步加载图片（不阻塞启动页显示）
        def _load_splash_image():
            try:
                splash_img = self._load_scaled_icon(ICON_SPLASH, 360)
                if splash_img:
                    self.root.after(0, lambda: self._set_splash_image(splash_img))
            except Exception:
                pass

        threading.Thread(target=_load_splash_image, daemon=True).start()

    def _set_splash_image(self, splash_img):
        """异步加载完成后替换启动页图片"""
        if hasattr(self, 'splash') and self.splash.winfo_exists():
            if hasattr(self, '_splash_logo_label') and self._splash_logo_label.winfo_exists():
                self._splash_logo_label.destroy()
            img_label = tk.Label(self.splash, image=splash_img, bg=COLORS["bg_page"])
            img_label.image = splash_img
            self._icon_refs.append(splash_img)
            img_label.pack(pady=(60, 20))
            self.splash.update_idletasks()

    def _close_splash(self):
        """关闭启动页，显示主窗口"""
        try:
            if hasattr(self, 'splash') and self.splash.winfo_exists():
                self.splash.destroy()
        except Exception:
            pass
        try:
            self.root.deiconify()
            self.root.lift()
        except Exception:
            pass

    # ===================== 图标加载 =====================
    def _load_icon(self, path):
        """安全加载图标，失败返回None"""
        try:
            if os.path.exists(path):
                return tk.PhotoImage(file=path)
        except Exception:
            pass
        return None

    def _load_scaled_icon(self, path, size):
        """加载并缩放图标，size 为最长边像素，保持宽高比。失败返回None。

        带 (path, size) 缓存：同一图标同一尺寸只缩放一次，避免订阅弹窗
        反复打开时重复 PIL 缩放造成卡顿。
        """
        if not path or not os.path.exists(path):
            return None
        cache_key = (os.path.abspath(path), size)
        cached = self._scaled_icon_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            from PIL import Image, ImageTk
            img = Image.open(path).convert("RGBA")
            w, h = img.size
            if w >= h:
                new_w = size
                new_h = int(h * size / w)
            else:
                new_h = size
                new_w = int(w * size / h)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            result = ImageTk.PhotoImage(img)
            self._scaled_icon_cache[cache_key] = result
            return result
        except Exception:
            return None

    def _load_window_icons(self):
        """加载窗口标题栏和应用图标"""
        # 标题栏图标
        title_icon = self._load_icon(ICON_TITLE)
        if title_icon:
            self.root.iconphoto(False, title_icon)
            self._icon_refs.append(title_icon)

        # 应用图标（桌面/Dock）
        app_icon = self._load_icon(ICON_APP)
        if app_icon:
            self.root.iconphoto(True, app_icon)
            self._icon_refs.append(app_icon)

    # ===================== 响应式字体缩放 =====================
    def _on_window_resize(self, event):
        if event.widget == self.root and event.width > 0:
            scale = min(event.width / self._base_window_width, LAYOUT_SCALE_CAP)
            if abs(scale - self._last_scale) < 0.05:
                return  # 忽略微小变化
            if self._resize_timer:
                self.root.after_cancel(self._resize_timer)
            self._resize_timer = self.root.after(150, lambda s=scale: self._apply_resize(s))
            self._last_scale = scale

    def _apply_resize(self, scale):
        """防抖后执行实际缩放"""
        self._resize_timer = None
        self._scale = scale
        update_font_scale(scale)
        # 缩放左侧面板宽度和布局间距
        self._scale_layout(scale)
        # 强制刷新右侧内容区域，防止最大化后文字被遮挡
        if hasattr(self, '_task_canvas') and self._task_canvas.winfo_exists():
            self._task_canvas.update_idletasks()
            self._task_canvas.configure(scrollregion=self._task_canvas.bbox("all"))
        self.root.update_idletasks()

    def _scale_layout(self, scale):
        """根据缩放系数调整布局间距和面板宽度"""
        if hasattr(self, 'left_frame') and self.left_frame.winfo_exists():
            new_width = max(240, min(440, int(240 * min(scale, 1.85))))
            self.left_frame.configure(width=new_width)
        # 调整主内容区边距
        if hasattr(self, 'content_frame') and self.content_frame.winfo_exists():
            pad = max(8, min(40, int(24 * min(scale, 1.15))))
            pady = max(8, min(36, int(20 * min(scale, 1.15))))
            if hasattr(self, '_page_frame') and self._page_frame.winfo_exists():
                try:
                    self._page_frame.pack_configure(padx=pad, pady=pady)
                except Exception:
                    pass

    def _bind_safe(self, widget, sequence, callback):
        """安全绑定事件，避免重复绑定导致卡顿"""
        try:
            widget.unbind(sequence)
        except Exception:
            pass
        widget.bind(sequence, callback)

    # ===================== UI 构建 =====================
    def _build_ui(self):
        # ========== 顶部品牌栏 ==========
        toolbar = tk.Frame(self.root, bg=COLORS["bg_page"], height=56)
        toolbar.pack(fill=tk.X)
        toolbar.pack_propagate(False)

        tk.Frame(toolbar, bg=COLORS["border_light"], height=1).pack(side=tk.BOTTOM, fill=tk.X)

        left_group = tk.Frame(toolbar, bg=COLORS["bg_page"])
        left_group.pack(side=tk.LEFT, padx=(16, 0), pady=8)

        # 标题栏小图标（32×32 缩放，完全左靠齐）
        title_icon = self._load_scaled_icon(ICON_TITLE, 32)
        if title_icon:
            logo_label = tk.Label(left_group, image=title_icon, bg=COLORS["bg_page"])
            logo_label.image = title_icon
            self._icon_refs.append(title_icon)
        else:
            logo_label = tk.Label(left_group,
                                  text=ICONS["logo"],
                                  font=(_ui_font_family(), 20, "bold"),
                                  fg=COLORS["primary"],
                                  bg=COLORS["bg_page"])
        logo_label.pack(side=tk.LEFT)

        brand_text = tk.Frame(left_group, bg=COLORS["bg_page"])
        brand_text.pack(side=tk.LEFT, padx=(12, 0))
        tk.Label(brand_text,
                 text="HONGXUN",
                 font=FONT_TITLE,
                 fg=COLORS["text_title"],
                 bg=COLORS["bg_page"]).pack(anchor=tk.W)
        tk.Label(brand_text,
                 text="论文监控助手",
                 font=FONT_CAPTION,
                 fg=COLORS["text_secondary"],
                 bg=COLORS["bg_page"]).pack(anchor=tk.W)

        # 顶部工具栏右侧（文字按钮：无 tooltip，直观清晰）
        right_tool_group = tk.Frame(toolbar, bg=COLORS["bg_page"])
        right_tool_group.pack(side=tk.RIGHT, padx=(0, 12))

        from gui.widgets import LinkButton
        # 工具栏文字：加深颜色 + 字号增大 10%（更醒目）
        _tool_color = COLORS["text_body"]          # 更深的文字色
        _tool_font = (_ui_font_family(), int(FONT_BODY.cget("size") * 1.1))
        for text, cmd in [
            ("意见反馈", self._open_feedback),
            ("使用说明", self._show_usage_guide),
            ("检查更新", self._check_update_manual),
        ]:
            LinkButton(right_tool_group, text=text, command=cmd,
                       color=_tool_color, bg=COLORS["bg_page"], font=_tool_font,
                       padx=8, pady=6).pack(side=tk.RIGHT, padx=(2, 0))

        # 登录 / 注册 + 邀请码入口（与检查更新同一工具栏分组）
        self._tool_login_link = LinkButton(right_tool_group, text="登录",
                                           command=self._open_login_dialog,
                                           color=_tool_color, bg=COLORS["bg_page"],
                                           font=_tool_font, padx=8, pady=6)
        self._tool_login_link.pack(side=tk.RIGHT, padx=(2, 0))
        self._tool_register_link = LinkButton(right_tool_group, text="注册",
                                              command=self._open_register_dialog,
                                              color=_tool_color, bg=COLORS["bg_page"],
                                              font=_tool_font, padx=8, pady=6)
        self._tool_register_link.pack(side=tk.RIGHT, padx=(2, 0))
        self._tool_invite_link = LinkButton(right_tool_group, text="我的邀请码",
                                            command=self._show_invite_code,
                                            color=_tool_color, bg=COLORS["bg_page"],
                                            font=_tool_font, padx=8, pady=6)
        self._tool_invite_link.pack(side=tk.RIGHT, padx=(2, 0))

        # ========== 主内容区 ==========
        self.content_frame = ttk.Frame(self.root, style="TFrame")
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # -------- 左侧任务面板 (TaskSidebar) — 固定宽度 pack --------
        self.left_frame = tk.Frame(self.content_frame, bg=COLORS["sidebar_bg"], width=240)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.left_frame.pack_propagate(False)

        self.sidebar = TaskSidebar(
            self.left_frame,
            on_select=self._on_sidebar_select,
            on_new=self._new_task,
            on_toggle_push=self._toggle_scheduler,
            on_nav=self._on_sidebar_nav,
            on_task_changed=self._refresh_task_list,
            on_delete_task=self._delete_task_from_sidebar,
            load_tasks_fn=load_all_tasks,
            get_task_fn=get_task,
            save_task_fn=save_task,
        )
        self.sidebar.pack(fill=tk.BOTH, expand=True)

        # -------- 右侧内容区（页面栈：侧栏主导航切换，一次只显示一页） --------
        right_frame = ttk.Frame(self.content_frame, style="TFrame")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=24, pady=24)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)

        self._page_frame = right_frame
        self._pages = {}

        # ========== 页面 0: 概览 Dashboard（首页） ==========
        self.dashboard_view = DashboardView(
            right_frame,
            on_new_task=self._new_task,
            on_run_search=self._run_history,
            on_open_library=self._switch_to_library,
            on_export=self._export_library,
            on_coupon=self._redeem_coupon_dialog,
            on_subscribe=self._open_subscription_dialog,
        )
        self._pages["dashboard"] = self.dashboard_view

        # ========== 页面 1: 监控任务（检索参数） ==========
        self._task_tab = ttk.Frame(right_frame, style="TFrame")
        self._pages["monitor"] = self._task_tab
        self._task_tab.columnconfigure(0, weight=1)
        self._task_tab.rowconfigure(0, weight=1)

        # 页面 1 内嵌 Canvas + Scrollbar（仅垂直：表单不再需要横向滚动）
        self._task_canvas = tk.Canvas(self._task_tab, borderwidth=0, highlightthickness=0,
                                      bg=COLORS["bg_page"])
        task_v_scroll = ModernScrollbar(self._task_tab, width=8,
                                        command=self._task_canvas.yview)
        self._task_canvas.configure(yscrollcommand=task_v_scroll.set)
        self._task_canvas.grid(row=0, column=0, sticky=tk.NSEW)
        task_v_scroll.grid(row=0, column=1, sticky=tk.NS)

        scrollable = ttk.Frame(self._task_canvas, style="TFrame")
        scrollable.bind("<Configure>",
                        lambda e: self._task_canvas.configure(scrollregion=self._task_canvas.bbox("all")))
        self._task_canvas_window = self._task_canvas.create_window((0, 0), window=scrollable, anchor=tk.NW)

        def _configure_task_canvas_width(event):
            self._task_canvas.itemconfig(self._task_canvas_window, width=max(event.width, 400))
        self._task_canvas.bind("<Configure>", _configure_task_canvas_width)

        # 鼠标滚轮（平滑滚轮，避免轻推直接跳到底部）
        _on_mousewheel, _bind_mousewheel, _unbind_mousewheel = smooth_wheel_handler(
            self._task_canvas)
        scrollable.bind("<Enter>", _bind_mousewheel)
        scrollable.bind("<Leave>", _unbind_mousewheel)

        # ========== 页面 3: 设置（每日推送 + 邮箱配置） ==========
        self._settings_tab = ttk.Frame(right_frame, style="TFrame")
        self._pages["settings"] = self._settings_tab
        self._settings_tab.columnconfigure(0, weight=1)
        self._settings_tab.rowconfigure(0, weight=1)

        settings_canvas = tk.Canvas(self._settings_tab, borderwidth=0, highlightthickness=0,
                                    bg=COLORS["bg_page"])
        s_v_scroll = ModernScrollbar(self._settings_tab, width=8,
                                     command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=s_v_scroll.set)
        settings_canvas.grid(row=0, column=0, sticky=tk.NSEW)
        s_v_scroll.grid(row=0, column=1, sticky=tk.NS)

        settings_scrollable = ttk.Frame(settings_canvas, style="TFrame")
        settings_scrollable.bind("<Configure>",
                                 lambda e: settings_canvas.configure(scrollregion=settings_canvas.bbox("all")))
        self._settings_canvas_window = settings_canvas.create_window(
            (0, 0), window=settings_scrollable, anchor=tk.NW)

        def _configure_settings_canvas_width(event):
            settings_canvas.itemconfig(self._settings_canvas_window, width=max(event.width, 400))
        settings_canvas.bind("<Configure>", _configure_settings_canvas_width)

        _s_mousewheel, _s_bind, _s_unbind = smooth_wheel_handler(settings_canvas)
        settings_scrollable.bind("<Enter>", _s_bind)
        settings_scrollable.bind("<Leave>", _s_unbind)

        self._settings_scrollable = settings_scrollable

        # 任务设置内容（原 scrollable 内的全部内容）
        # ═══ 监控任务页：检索参数 ═══
        monitor_header = tk.Frame(scrollable, bg=COLORS["bg_page"])
        monitor_header.pack(fill=tk.X, padx=4, pady=(0, 8))
        tk.Label(monitor_header, text="监控任务", font=FONT_TITLE,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"]).pack(side=tk.LEFT)
        tk.Label(monitor_header, text="配置期刊与关键词，执行论文检索", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_page"]).pack(side=tk.LEFT, padx=(10, 0), pady=(4, 0))

        # ── 卡片 1: 检索参数 ──
        search_card = _simple_card(scrollable)
        search_card.pack(fill=tk.X, padx=2, pady=(0, 16))

        tk.Label(search_card.content, text="检索参数", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Frame(search_card.content, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 10))

        # 表单区域用 grid
        sf = tk.Frame(search_card.content, bg=COLORS["bg_card"])
        sf.pack(fill=tk.X, padx=16, pady=(0, 14))
        sf.columnconfigure(1, weight=1)

        row = 0
        # 任务名称
        tk.Label(sf, text="任务名称", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=row, column=0, sticky=tk.E, padx=(0, 16), pady=6)
        self.task_name_var = tk.StringVar()
        ModernEntry(sf, textvariable=self.task_name_var).grid(
            row=row, column=1, sticky=tk.EW, pady=6)
        row += 1

        # 期刊名称
        tk.Label(sf, text="期刊名称", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=row, column=0, sticky=tk.E, padx=(0, 16), pady=6)
        self.journal_var = tk.StringVar()  # 分号分隔期刊名，供保存/加载兼容
        self.selected_journals: list = []   # 已选期刊 dict 列表
        self.selected_journal_ids: list = []  # 已选期刊 id 列表
        journal_row = tk.Frame(sf, bg=COLORS["bg_card"])
        journal_row.grid(row=row, column=1, sticky=tk.EW, pady=6)
        self.journal_pick_btn = ModernButton(
            journal_row, text="选择期刊 ▾", variant="secondary", height=30,
            pad_x=16, command=self._open_journal_picker)
        self.journal_pick_btn.pack(side=tk.LEFT)
        self._journal_count_label = tk.Label(
            journal_row, text="已选 0 本", font=FONT_CAPTION,
            fg=COLORS["primary"], bg=COLORS["bg_card"])
        self._journal_count_label.pack(side=tk.LEFT, padx=(10, 0))

        # 已选期刊 pill 标签区
        self._journal_tags_frame = tk.Frame(sf, bg=COLORS["bg_card"])
        self._journal_tags_frame.grid(row=row+1, column=1, sticky=tk.W, pady=(2, 6))
        self._journal_hint_label = tk.Label(
            sf, text="最多选择 10 本期刊，点击「选择期刊」可视化添加",
            font=FONT_CAPTION, fg=COLORS["text_hint"], bg=COLORS["bg_card"]
        )
        self._journal_hint_label.grid(row=row+2, column=1, sticky=tk.W, pady=(0, 6))
        row += 3

        # 关键词
        tk.Label(sf, text="关键词", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=row, column=0, sticky=tk.E, padx=(0, 16), pady=6)
        self.keyword_var = tk.StringVar()
        ModernEntry(sf, textvariable=self.keyword_var).grid(
            row=row, column=1, sticky=tk.EW, pady=6)
        tk.Label(sf, text="英文分号分隔，最多10个",
                 font=FONT_CAPTION, fg=COLORS["text_hint"], bg=COLORS["bg_card"]
                 ).grid(row=row+1, column=1, sticky=tk.W, pady=(2, 6))
        row += 2

        # 检索范围（双输入框）
        tk.Label(sf, text="检索范围", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=row, column=0, sticky=tk.E, padx=(0, 16), pady=6)
        range_frame = tk.Frame(sf, bg=COLORS["bg_card"])
        range_frame.grid(row=row, column=1, sticky=tk.EW, pady=6)
        range_frame.columnconfigure(0, weight=1)
        range_frame.columnconfigure(1, weight=1)
        range_frame.columnconfigure(2, weight=1)
        self.date_start_var = tk.StringVar()
        self.date_end_var = tk.StringVar()
        # 从原有的 date_var 解析初始值
        _init_dates = self.date_var.get().split(";") if hasattr(self, 'date_var') else ["", ""]
        self.date_start_var.set(_init_dates[0] if len(_init_dates) > 0 else "")
        self.date_end_var.set(_init_dates[1] if len(_init_dates) > 1 else "")
        ModernEntry(range_frame, textvariable=self.date_start_var).grid(
            row=0, column=0, sticky=tk.EW)
        tk.Label(range_frame, text=" → ", font=FONT_BODY,
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).grid(row=0, column=1)
        ModernEntry(range_frame, textvariable=self.date_end_var).grid(
            row=0, column=2, sticky=tk.EW)
        tk.Label(sf, text="格式: 2020-01-01 → 2026-07-26",
                 font=FONT_CAPTION, fg=COLORS["text_hint"], bg=COLORS["bg_card"]
                 ).grid(row=row+1, column=1, sticky=tk.W, pady=(2, 6))

        # 保留 date_var 供旧代码使用（同步双输入框→旧变量）
        self.date_var = tk.StringVar()
        def _sync_date(*_):
            self.date_var.set(f"{self.date_start_var.get()};{self.date_end_var.get()}")
        self.date_start_var.trace_add("write", _sync_date)
        self.date_end_var.trace_add("write", _sync_date)
        _sync_date()
        row += 2

        # 操作按钮
        btn_frame = tk.Frame(sf, bg=COLORS["bg_card"])
        btn_frame.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(12, 4))
        ModernButton(btn_frame, text=f" {ICONS['search']} 执行检索", variant="primary",
                     command=self._run_history).pack(side=tk.LEFT, padx=(0, 8))
        ModernButton(btn_frame, text=f" {ICONS['save']} 保存任务", variant="secondary",
                     command=self._save_task).pack(side=tk.LEFT, padx=(0, 8))
        ModernButton(btn_frame, text="🗑 删除", variant="danger",
                     command=self._delete_task).pack(side=tk.LEFT)

        # 示例填充
        example_btn = tk.Label(sf, text="🌰 试试示例", font=FONT_CAPTION,
                               fg=COLORS["primary"], bg=COLORS["bg_card"],
                               cursor="hand2")
        example_btn.grid(row=row+1, column=1, sticky=tk.W, pady=(6, 0))
        example_btn.bind("<Button-1>", lambda e: self._fill_example())

        # 监控页底部留白：避免最后一个元素贴边
        tk.Frame(scrollable, bg=COLORS["bg_page"], height=20).pack(fill=tk.X)

        # ═══ 设置页：每日推送 + 邮箱配置 ═══
        settings_header = tk.Frame(self._settings_scrollable, bg=COLORS["bg_page"])
        settings_header.pack(fill=tk.X, padx=4, pady=(0, 8))
        tk.Label(settings_header, text="设置", font=FONT_TITLE,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"]).pack(side=tk.LEFT)
        tk.Label(settings_header, text="每日推送与邮件配置", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_page"]).pack(side=tk.LEFT, padx=(10, 0), pady=(4, 0))

        # ── 卡片 1: 激活状态 + 礼品券入口 ──
        license_card = _simple_card(self._settings_scrollable)
        license_card.pack(fill=tk.X, padx=2, pady=(0, 16))

        tk.Label(license_card.content, text="激活状态", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Frame(license_card.content, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 10))

        lf = tk.Frame(license_card.content, bg=COLORS["bg_card"])
        lf.pack(fill=tk.X, padx=16, pady=(0, 14))
        self._settings_license_label = tk.Label(lf, text="", font=FONT_BODY_BOLD,
                                                fg=COLORS["text_body"], bg=COLORS["bg_card"],
                                                anchor=tk.W)
        self._settings_license_label.pack(fill=tk.X, pady=4)
        self._settings_coupon_btn = ModernButton(lf, text="🎟 兑换礼品券",
                                                 variant="primary",
                                                 command=self._redeem_coupon_dialog)
        self._settings_coupon_btn.pack(anchor=tk.W, pady=(4, 0))
        ModernButton(lf, text="📧 邮箱注册 · 每日推送默认邮箱",
                     variant="secondary",
                     command=self._open_login_dialog).pack(anchor=tk.W, pady=(6, 0))
        self._settings_reg_label = tk.Label(lf, text="", font=FONT_CAPTION,
                                            fg=COLORS["text_hint"], bg=COLORS["bg_card"],
                                            anchor=tk.W)
        self._settings_reg_label.pack(fill=tk.X, pady=(2, 0))
        # 显示已注册邮箱
        try:
            from core import user_manager
            reg_email = user_manager.get_registered_email()
            if reg_email:
                self._settings_reg_label.configure(
                    text=f"已注册邮箱：{reg_email}", fg=COLORS["success"])
            else:
                self._settings_reg_label.configure(text="未注册邮箱", fg=COLORS["text_hint"])
        except Exception:
            pass

        # ── 卡片 2: 每日推送状态（归入"设置"页） ──
        push_card = _simple_card(self._settings_scrollable)
        push_card.pack(fill=tk.X, padx=2, pady=(0, 16))

        tk.Label(push_card.content, text="每日推送", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Frame(push_card.content, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 10))

        pf = tk.Frame(push_card.content, bg=COLORS["bg_card"])
        pf.pack(fill=tk.X, padx=16, pady=(0, 14))

        # 第一行：状态 + 开关
        push_row1 = tk.Frame(pf, bg=COLORS["bg_card"])
        push_row1.pack(fill=tk.X, pady=4)
        self._push_status_indicator = tk.Label(push_row1, text="○",
                                               font=FONT_BODY_BOLD,
                                               fg=COLORS["dot_off"],
                                               bg=COLORS["bg_card"])
        self._push_status_indicator.pack(side=tk.LEFT, padx=(0, 6))
        self._push_status_text = tk.Label(push_row1, text="每日推送未启动",
                                          font=FONT_LABEL,
                                          fg=COLORS["text_body"],
                                          bg=COLORS["bg_card"])
        self._push_status_text.pack(side=tk.LEFT)

        self._push_toggle_btn = ModernButton(push_row1, text="启动每日推送",
                                             variant="primary",
                                             command=self._toggle_scheduler)
        self._push_toggle_btn.pack(side=tk.RIGHT)

        # 第二行：监控统计
        push_row2 = tk.Frame(pf, bg=COLORS["bg_card"])
        push_row2.pack(fill=tk.X, pady=4)
        stats_left = tk.Frame(push_row2, bg=COLORS["bg_card"])
        stats_left.pack(side=tk.LEFT)
        tk.Label(stats_left, text="监控期刊  ", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_card"]).pack(side=tk.LEFT)
        self._push_journal_label = tk.Label(stats_left, text="0 个",
                                            font=FONT_BODY_BOLD,
                                            fg=COLORS["primary"], bg=COLORS["bg_card"])
        self._push_journal_label.pack(side=tk.LEFT, padx=(0, 16))

        tk.Label(stats_left, text="推送时间  ", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_card"]).pack(side=tk.LEFT)
        _cur_push = str(load_app_config().get("push_time", "08:00"))
        self._push_time_label = tk.Label(stats_left, text=f"每日 {_cur_push}",
                                         font=FONT_BODY_BOLD,
                                         fg=COLORS["text_body"], bg=COLORS["bg_card"])
        self._push_time_label.pack(side=tk.LEFT, padx=(0, 16))

        tk.Label(stats_left, text="累计推送  ", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_card"]).pack(side=tk.LEFT)
        self._push_total_label = tk.Label(stats_left, text="0 篇",
                                          font=FONT_BODY_BOLD,
                                          fg=COLORS["success"], bg=COLORS["bg_card"])
        self._push_total_label.pack(side=tk.LEFT)

        # 推送时间选择器（用户自选，每半小时一档）
        push_time_row = tk.Frame(pf, bg=COLORS["bg_card"])
        push_time_row.pack(fill=tk.X, pady=4)
        tk.Label(push_time_row, text="推送时间", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_card"]).pack(side=tk.LEFT)
        self._push_time_var = tk.StringVar(value=_cur_push)
        self._push_time_combo = ttk.Combobox(
            push_time_row, textvariable=self._push_time_var,
            width=12, font=FONT_BODY,
            values=[f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)])
        self._push_time_combo.pack(side=tk.LEFT, padx=(8, 0))
        self._push_time_combo.bind("<<ComboboxSelected>>",
                                   lambda e: self._on_push_time_changed())
        tk.Label(push_time_row, text="每日推送时刻（修改后需重启推送生效）", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(10, 0))

        # ── 卡片: AI 翻译（英→中） ──
        ai_card = _simple_card(self._settings_scrollable)
        ai_card.pack(fill=tk.X, padx=2, pady=(0, 16))

        tk.Label(ai_card.content, text="🌐 AI 翻译（英→中）", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Frame(ai_card.content, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 10))

        ai_form = tk.Frame(ai_card.content, bg=COLORS["bg_card"])
        ai_form.pack(fill=tk.X, padx=16, pady=(0, 14))
        ai_row = tk.Frame(ai_form, bg=COLORS["bg_card"])
        ai_row.pack(fill=tk.X, pady=4)
        self._ai_translate_var = tk.BooleanVar(
            value=bool(load_app_config().get("translate_enabled", False)))
        self._ai_translate_toggle = ToggleSwitch(
            ai_row, width=64, height=32,
            initial=self._ai_translate_var.get(),
            command=self._on_ai_translate_toggle)
        self._ai_translate_toggle.pack(side=tk.LEFT)
        tk.Label(ai_row, text="开启后论文标题与摘要自动翻译为中文（检索报告与推送邮件均含）",
                 font=FONT_CAPTION, fg=COLORS["text_hint"],
                 bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(8, 0))

        # AI 配置按钮（与 Sci-Hub「保存 PDF 设置」一致：Secondary 按钮）
        ai_btn_row = tk.Frame(ai_form, bg=COLORS["bg_card"])
        ai_btn_row.pack(fill=tk.X, pady=(8, 4))
        ModernButton(ai_btn_row, text="⚙ 配置 API", variant="secondary", height=30,
                     command=self._open_llm_config_dialog).pack(side=tk.LEFT)
        tk.Label(ai_btn_row, text="选择厂商并填写 API Key（DeepSeek / 豆包 / MiniMax）",
                 font=FONT_CAPTION, fg=COLORS["text_hint"],
                 bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(8, 0))

        # ── 卡片 3: 邮箱配置（归入"设置"页） ──
        monitor_card = _simple_card(self._settings_scrollable)
        monitor_card.pack(fill=tk.X, padx=2, pady=(0, 16))

        tk.Label(monitor_card.content, text="邮箱配置", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Frame(monitor_card.content, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 10))

        mf = tk.Frame(monitor_card.content, bg=COLORS["bg_card"])
        mf.pack(fill=tk.X, padx=16, pady=(0, 14))
        mf.columnconfigure(1, weight=1)

        # 收件邮箱
        tk.Label(mf, text="收件邮箱", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=1, column=0, sticky=tk.NW, padx=(0, 16), pady=8)
        receiver_container = tk.Frame(mf, bg=COLORS["bg_card"])
        receiver_container.grid(row=1, column=1, sticky=tk.EW, pady=8)
        receiver_container.columnconfigure(0, weight=1)

        self._receiver_frame = tk.Frame(receiver_container, bg=COLORS["bg_card"])
        self._receiver_frame.pack(fill=tk.X)
        self._receiver_list = []

        receiver_add_frame = tk.Frame(receiver_container, bg=COLORS["bg_card"])
        receiver_add_frame.pack(fill=tk.X, pady=(4, 0))

        self._new_receiver_var = tk.StringVar()
        self._new_receiver_entry = ModernEntry(receiver_add_frame,
                                               textvariable=self._new_receiver_var,
                                               placeholder="name@example.com")
        self._new_receiver_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ModernButton(receiver_add_frame, text="＋ 添加", variant="secondary", height=30,
                     command=self._add_receiver).pack(side=tk.LEFT)
        self._new_receiver_entry.entry.bind("<Return>", lambda e: self._add_receiver())

        # ── SMTP 配置（可折叠） ──
        smtp_header = tk.Frame(mf, bg=COLORS["bg_card"])
        smtp_header.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
        self._smtp_expanded = False
        smtp_toggle = tk.Label(smtp_header, text="▸ SMTP 配置",
                               font=FONT_CAPTION, fg=COLORS["primary"],
                               bg=COLORS["bg_card"], cursor="hand2")
        smtp_toggle.pack(side=tk.LEFT)
        self._smtp_config_frame = tk.Frame(mf, bg=COLORS["bg_card"])

        def _toggle_smtp():
            self._smtp_expanded = not self._smtp_expanded
            if self._smtp_expanded:
                smtp_toggle.configure(text="▾ SMTP 配置")
                self._smtp_config_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
            else:
                smtp_toggle.configure(text="▸ SMTP 配置")
                self._smtp_config_frame.grid_forget()

        smtp_toggle.bind("<Button-1>", lambda e: _toggle_smtp())

        # SMTP 配置内容
        scf = self._smtp_config_frame
        scf.columnconfigure(1, weight=1)
        scf.columnconfigure(3, weight=1)

        # 许可状态
        self._license_status_label = tk.Label(scf, text="", anchor=tk.W,
                                              font=FONT_CAPTION, bg=COLORS["bg_card"])
        self._license_status_label.grid(row=0, column=0, columnspan=4, sticky=tk.EW, pady=(0, 6))

        # 发件邮箱
        tk.Label(scf, text="发件邮箱", font=FONT_CAPTION,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.sender_var = tk.StringVar()
        self.sender_entry = PlaceholderEntry(scf, placeholder="your_email@qq.com",
                                             textvariable=self.sender_var)
        self.sender_entry.grid(row=1, column=1, sticky=tk.EW, padx=(0, 12), pady=4)

        tk.Label(scf, text="SMTP授权码", font=FONT_CAPTION,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=1, column=2, sticky=tk.W, padx=(0, 8), pady=4)
        self.auth_code_var = tk.StringVar()
        ac_frame = tk.Frame(scf, bg=COLORS["bg_card"])
        ac_frame.grid(row=1, column=3, sticky=tk.EW, pady=4)
        ac_frame.columnconfigure(0, weight=1)
        self.auth_code_entry = PlaceholderEntry(ac_frame, placeholder="16位授权码", show="*",
                                                textvariable=self.auth_code_var)
        self.auth_code_entry.grid(row=0, column=0, sticky=tk.EW)
        self._auth_code_visible = False
        toggle_auth = tk.Label(ac_frame, text="显示",
                               font=FONT_CAPTION, fg=COLORS["primary"],
                               bg=COLORS["bg_card"], cursor="hand2", padx=6)
        toggle_auth.grid(row=0, column=1)
        toggle_auth.bind("<Button-1>", lambda e: self._toggle_auth_code_visibility())

        # SMTP 服务器
        tk.Label(scf, text="SMTP服务", font=FONT_CAPTION,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=2, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.smtp_preset_var = tk.StringVar(value="QQ邮箱")
        self.smtp_combo = ttk.Combobox(scf, textvariable=self.smtp_preset_var,
                                       state="readonly", width=28, font=FONT_BODY)
        self.smtp_combo['values'] = list(SMTP_PROVIDERS.keys())
        self.smtp_combo.grid(row=2, column=1, columnspan=3, sticky=tk.W, pady=4)
        self.smtp_combo.bind("<<ComboboxSelected>>", self._on_smtp_preset_selected)
        configs = get_provider_configs("QQ邮箱")
        self.smtp_server_var = tk.StringVar(value=configs[0]["server"] if configs else "smtp.qq.com")
        self.port_var = tk.StringVar(value=configs[0]["port"] if configs else "465")

        # 操作按钮
        btn_row_email = tk.Frame(scf, bg=COLORS["bg_card"])
        btn_row_email.grid(row=4, column=0, columnspan=4, sticky=tk.EW, pady=(8, 4))
        ModernButton(btn_row_email, text="保存配置", variant="primary",
                     command=self._save_email_config).pack(side=tk.LEFT)
        self._resend_btn = ttk.Button(btn_row_email, text="再发送", style="Secondary.TButton",
                                      command=self._resend_unsent_email)
        self._resend_btn.pack(side=tk.LEFT, padx=(8, 0))
        self._resend_btn.state(["disabled"])

        # 使用指南 + 礼品券 链接
        links_frame = tk.Frame(monitor_card.content, bg=COLORS["bg_card"])
        links_frame.pack(fill=tk.X, padx=16, pady=(0, 12))
        for text, cmd in [("📖 使用指南", self._show_email_intro),
                          ("🎟 礼品券", self._redeem_coupon_dialog)]:
            lb = tk.Label(links_frame, text=text, font=FONT_CAPTION,
                          fg=COLORS["primary"], bg=COLORS["bg_card"], cursor="hand2")
            lb.pack(side=tk.LEFT, padx=(0, 16))
            lb.bind("<Button-1>", lambda e, c=cmd: c())
            lb.bind("<Enter>", lambda e, l=lb: l.configure(fg=COLORS["primary_hover"]))
            lb.bind("<Leave>", lambda e, l=lb: l.configure(fg=COLORS["primary"]))

        # ── 卡片: PDF 下载 ──
        from core.pdf_config import load_pdf_config, save_pdf_config
        pdf_cfg = load_pdf_config()
        pdf_card = _simple_card(self._settings_scrollable)
        pdf_card.pack(fill=tk.X, padx=2, pady=(0, 16))

        tk.Label(pdf_card.content, text="📄 PDF 下载", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Frame(pdf_card.content, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 10))

        pdf_form = tk.Frame(pdf_card.content, bg=COLORS["bg_card"])
        pdf_form.pack(fill=tk.X, padx=16, pady=(0, 14))
        pdf_form.columnconfigure(1, weight=1)

        # 保存目录
        tk.Label(pdf_form, text="保存目录", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 16), pady=8)
        dir_row = tk.Frame(pdf_form, bg=COLORS["bg_card"])
        dir_row.grid(row=0, column=1, sticky=tk.EW, pady=8)
        dir_row.columnconfigure(0, weight=1)
        self._pdf_dir_var = tk.StringVar(value=pdf_cfg.get("pdf_dir", ""))
        self._pdf_dir_entry = ModernEntry(dir_row, textvariable=self._pdf_dir_var)
        self._pdf_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ModernButton(dir_row, text="浏览…", variant="secondary", height=30,
                     command=self._browse_pdf_dir).pack(side=tk.LEFT)

        # 启用 Sci-Hub 增强
        tk.Label(pdf_form, text="Sci-Hub 增强", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 16), pady=8)
        sci_row = tk.Frame(pdf_form, bg=COLORS["bg_card"])
        sci_row.grid(row=1, column=1, sticky=tk.W, pady=8)
        self._scihub_toggle = ToggleSwitch(
            sci_row, width=64, height=32,
            initial=bool(pdf_cfg.get("enable_scihub")),
            command=self._on_scihub_toggle)
        self._scihub_toggle.pack(side=tk.LEFT)
        tk.Label(sci_row, text="开启后可从 Sci-Hub 获取付费论文 PDF（存在版权风险）",
                 font=FONT_CAPTION, fg=COLORS["text_hint"],
                 bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(8, 0))

        ModernButton(pdf_form, text="保存 PDF 设置", variant="secondary", height=30,
                     command=self._on_pdf_cfg_changed).grid(
            row=2, column=1, sticky=tk.W, pady=(8, 4))

        # 设置页底部留白：避免最后一个元素贴边
        tk.Frame(self._settings_scrollable, bg=COLORS["bg_page"], height=20).pack(fill=tk.X)

        # ========== CNKI 知网数据获取模块 ==========
        # 已移除

        # ========== 页面 2/4: 文献书架 & 格式助手（懒加载） ==========
        # 不在此同步创建，改为首次导航到时经 _ensure_page 惰性构建，
        # 避免启动阶段冷加载 LibraryView 的重依赖（加速启动）。

        # 显示默认页面（概览）
        self._current_page = "dashboard"
        self._show_page("dashboard")

        # -------- 进度条（常驻 2px 分割线，活跃时展开） --------
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_label_var = tk.StringVar(value="0%")

        # 不活跃状态：2px 灰色细线（在 status_frame 构建完后再 pack）
        self._progress_idle = tk.Frame(self.root, bg=COLORS["border_light"], height=2)
        self._progress_idle_packed = False

        # 活跃进度条容器（默认隐藏）
        progress_frame = ttk.Frame(self.root, style="TFrame")
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=1.0,
            mode="determinate",
            style="Horizontal.TProgressbar"
        )
        self.progress_label = ttk.Label(
            progress_frame,
            textvariable=self.progress_label_var,
            style="Caption.TLabel",
            anchor=tk.W
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(24, 8))
        self.progress_label.pack(side=tk.LEFT, fill=tk.X, padx=(0, 24))

        # 取消检索按钮（Secondary 灰色）
        self._cancel_search_btn = ModernButton(
            progress_frame, text=f" {ICONS['cancel']} 取消",
            variant="secondary",
            command=self._cancel_current_search,
        )
        self._cancel_search_btn.pack(side=tk.RIGHT, padx=(0, 24))
        self._cancel_search_btn.pack_forget()  # 默认隐藏

        progress_frame.pack_forget()
        self._progress_frame = progress_frame

        # -------- 底部状态栏 --------
        status_frame = tk.Frame(self.root, bg=COLORS["sidebar_bg"],
                                highlightbackground=COLORS["border_light"],
                                highlightthickness=0, height=38)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        status_frame.pack_propagate(False)

        # 上部分隔线
        tk.Frame(status_frame, bg=COLORS["border_light"], height=1).pack(fill=tk.X, side=tk.TOP)

        inner_sf = tk.Frame(status_frame, bg=COLORS["sidebar_bg"])
        inner_sf.pack(fill=tk.BOTH, expand=True)

        self._status_indicator = tk.Label(inner_sf,
                                          text=f"{ICONS['dot_off']} 就绪",
                                          font=FONT_CAPTION,
                                          fg=COLORS["dot_off"],
                                          bg=COLORS["sidebar_bg"])
        self._status_indicator.pack(side=tk.LEFT, padx=(20, 10), pady=8)

        self.status_var = tk.StringVar(value="")
        tk.Label(inner_sf, textvariable=self.status_var,
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["sidebar_bg"], anchor=tk.W
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True, pady=8)

        # 版本号弱化显示（报告建议：不占状态栏主要位置）
        self._version_label = tk.Label(inner_sf,
                                        text=f"v{APP_VERSION}",
                                        font=(_ui_font_family(), 8),
                                        fg=COLORS["border"],
                                        bg=COLORS["sidebar_bg"])
        self._version_label.pack(side=tk.RIGHT, padx=(0, 16), pady=8)

        self._next_run_label = tk.Label(inner_sf,
                                        text=f"{ICONS['clock']} 下次执行：--",
                                        font=FONT_CAPTION,
                                        fg=COLORS["text_secondary"],
                                        bg=COLORS["sidebar_bg"])
        self._next_run_label.pack(side=tk.RIGHT, padx=(0, 8), pady=8)

        # 现在 pack idle 细线（在所有控件之后）
        self._progress_idle.pack(side=tk.BOTTOM, fill=tk.X)
        self._progress_idle_packed = True

    # ===================== 任务列表操作 =====================
    def _refresh_task_list(self):
        if hasattr(self, 'sidebar'):
            self.sidebar.refresh_tasks()
            # 同步更新侧栏底部任务计数
            tasks = load_all_tasks()
            real_tasks = [t for t in tasks.values() if isinstance(t, dict)]
            enabled_count = sum(1 for t in real_tasks if t.get("enabled", True))
            self.sidebar.set_task_count(len(real_tasks), enabled_count)
            self.sidebar.set_push_status(self._scheduler_daemon_running)
            # 刷新概览页
            if hasattr(self, 'dashboard_view'):
                self.dashboard_view.refresh()
            # 调试：打印 task_count
            print(f"[DEBUG] set_task_count({len(tasks)}, {enabled_count})")

    def _on_sidebar_select(self, task_id):
        """Sidebar 选中任务时的回调：切到监控任务页并加载表单"""
        if self._executing:
            return
        self.current_task_id = task_id
        self._load_task_to_form(task_id)
        # 选中任务时切到监控任务页
        if hasattr(self, '_pages') and "monitor" in self._pages:
            self._show_page("monitor")
            if hasattr(self, 'sidebar'):
                self.sidebar.set_current_page("monitor")

    def _ensure_page(self, page):
        """确保页面已构建（懒加载：首次访问才创建 library / ref_formatter）。"""
        if page in self._pages:
            return
        if not hasattr(self, "_page_frame"):
            return
        right_frame = self._page_frame
        if page == "library":
            self.library_view = LibraryView(
                right_frame,
                on_download_pdf=self._download_paper_pdf,
            )
            self._pages["library"] = self.library_view
            self._refresh_library = lambda: self.library_view.refresh()
        elif page == "ref_formatter":
            self._ref_formatter_view = RefFormatterView(
                right_frame,
                on_open_llm_config=self._open_llm_config_dialog,
                on_require_activation=self._require_activation,
            )
            self._pages["ref_formatter"] = self._ref_formatter_view

    def _show_page(self, page):
        """页面栈切换：显示指定页面，隐藏其他（首次访问自动构建懒加载页）。"""
        if not hasattr(self, '_pages'):
            return
        self._ensure_page(page)
        if page not in self._pages:
            return
        for name, widget in self._pages.items():
            if name == page:
                widget.grid(row=0, column=0, sticky=tk.NSEW)
            else:
                widget.grid_remove()
        self._current_page = page

    def _on_sidebar_nav(self, page):
        """侧栏导航点击：切换到对应内容页（首次访问自动构建懒加载页）"""
        if not hasattr(self, '_pages'):
            return
        self._show_page(page)
        if page == "dashboard" and hasattr(self, 'dashboard_view'):
            self.dashboard_view.refresh()
        elif page == "library" and hasattr(self, 'library_view'):
            self.library_view.refresh()
        elif page == "ref_formatter" and hasattr(self, '_ref_formatter_view'):
            self._ref_formatter_view.refresh()

    def _new_task(self):
        self.current_task_id = None
        self.task_name_var.set("")
        self.journal_var.set("")
        self.selected_journals = []
        self.selected_journal_ids = []
        self.keyword_var.set("")
        self.date_start_var.set("2016-01-01")
        self.date_end_var.set("2026-01-01")
        self.date_var.set("2016-01-01;2026-01-01")
        self.status_var.set("当前：新建任务")
        self._refresh_journal_tags()

    def _delete_task(self):
        task_id = self.sidebar.get_selected_task_id() if hasattr(self, 'sidebar') else None
        if not task_id:
            messagebox.showwarning("提示", "请先选择要删除的任务")
            return
        if messagebox.askyesno("确认", "确定要删除选中的任务吗？"):
            delete_task(task_id)
            self._refresh_task_list()
            self._new_task()
        return "break"

    def _delete_task_from_sidebar(self, task_id):
        """侧栏右键菜单「删除」：确认后删除任务并刷新。"""
        task = get_task(task_id)
        name = task.get("name", "") if task else task_id
        if not messagebox.askyesno("删除任务", f"确定要删除任务「{name}」吗？"):
            return
        delete_task(task_id)
        # 若删除的是当前选中/编辑中的任务，清空表单
        if self.current_task_id == task_id:
            self._new_task()
        self._refresh_task_list()

    def _load_task_to_form(self, task_id):
        task = get_task(task_id)
        if not task:
            return
        self.task_name_var.set(task["name"])
        self.keyword_var.set("; ".join(task["keywords"]))
        ds = task.get("date_start", "")
        de = task.get("date_end", "")
        self.date_start_var.set(ds)
        self.date_end_var.set(de)
        self.date_var.set(f"{ds};{de}")
        # 还原已选期刊（任务存期刊名 → 通过期刊库映射为 dict）
        journals = task.get("journals", [])
        mapped = []
        try:
            store = self._journal_store()
            for nm in journals:
                j = store.get_by_name(nm, fuzzy=False)
                if j:
                    mapped.append(j)
                else:
                    # 库外/手动输入期刊保留名称，避免还原时丢失
                    mapped.append({"full_name": nm})
        except Exception:
            mapped = []
        if mapped:
            self.selected_journals = mapped
            self.selected_journal_ids = [j.get("jid") for j in mapped]
        else:
            self.selected_journals = []
            self.selected_journal_ids = []
        self._refresh_journal_tags()
        self.status_var.set(f"当前编辑：{task['name']}")

    # ===================== 期刊选择器 =====================
    def _journal_store(self) -> JournalStore:
        """惰性创建期刊数据库访问层。"""
        if not hasattr(self, "_journal_store_obj"):
            from core.journal_store import JournalStore
            self._journal_store_obj = JournalStore()
            try:
                self._journal_store_obj.ensure_db()
            except Exception:
                pass
        return self._journal_store_obj

    def _update_journal_var(self):
        """同步 journal_var（分号分隔名）与 selected_journals，供保存/校验兼容。"""
        self.journal_var.set("; ".join(j.get("full_name", "") for j in self.selected_journals))

    def _refresh_journal_tags(self):
        """渲染已选期刊 pill 标签区 + 数量。"""
        if not hasattr(self, "_journal_tags_frame"):
            return
        for w in self._journal_tags_frame.winfo_children():
            w.destroy()

        n = len(self.selected_journals)
        self._journal_count_label.configure(text=f"已选 {n} 本")

        if n == 0:
            tk.Label(self._journal_tags_frame, text="尚未选择期刊",
                     font=FONT_CAPTION, fg=COLORS["text_hint"],
                     bg=COLORS["bg_card"]).pack(side=tk.LEFT)
        else:
            for j in self.selected_journals:
                name = j.get("full_name", "")
                tag = tk.Label(self._journal_tags_frame,
                               text=f"{name[:14]}{'…' if len(name) > 14 else ''} ×",
                               font=FONT_CAPTION, fg=COLORS["primary"],
                               bg=COLORS["primary_light"], padx=8, pady=3, cursor="hand2")
                tag.pack(side=tk.LEFT, padx=3, pady=2)
                tag.bind("<Button-1>",
                         lambda e, jj=j: self._remove_journal(jj))

        # 提示文案
        if n == 0:
            self._journal_hint_label.configure(
                text="至少选择 1 本期刊，点击「选择期刊」可视化添加",
                fg=COLORS["text_hint"])
        elif n <= 10:
            self._journal_hint_label.configure(
                text=f"✓ 已选 {n} 本期刊（上限 10）", fg=COLORS["success"])
        else:
            self._journal_hint_label.configure(
                text=f"✗ 已选 {n} 本，超过上限 10 本", fg=COLORS["danger"])

        self._update_journal_var()

    def _open_journal_picker(self):
        """打开智能期刊选择器，确认后回填已选期刊。"""
        from gui.journal_picker import JournalPickerDialog
        try:
            store = self._journal_store()
        except Exception as e:
            messagebox.showerror("期刊库错误", f"无法加载期刊数据库：{e}")
            return

        current_names = [j.get("full_name", "") for j in self.selected_journals]

        def _on_confirm(names):
            # names 为期刊名 list，重新映射为 dict（库外/手动输入期刊保留名称）
            mapped = []
            for nm in names:
                j = store.get_by_name(nm, fuzzy=False)
                if j:
                    mapped.append(j)
                else:
                    mapped.append({"full_name": nm})
            self.selected_journals = mapped
            self.selected_journal_ids = [j.get("jid") for j in mapped]
            self._refresh_journal_tags()
            self.status_var.set("期刊选择完成，可保存任务")

        JournalPickerDialog(self.root, store, selected=current_names,
                            max_selected=10, on_confirm=_on_confirm)

    def _remove_journal(self, journal: dict):
        """移除单个已选期刊。"""
        jid = journal.get("jid")
        if jid is not None:
            # 库内期刊按 jid 匹配
            self.selected_journals = [j for j in self.selected_journals
                                      if j.get("jid") != jid]
            self.selected_journal_ids = [i for i in self.selected_journal_ids if i != jid]
        else:
            # 库外/手动输入期刊无 jid，按名称匹配；重建 id 列表保持对应
            name = journal.get("full_name", "")
            self.selected_journals = [j for j in self.selected_journals
                                      if j.get("full_name") != name]
            self.selected_journal_ids = [j.get("jid") for j in self.selected_journals]
        self._refresh_journal_tags()

    # ===================== 保存与校验 =====================
    def _save_task(self):
        # 游客模式不能保存任务
        if not self._require_login("保存任务"):
            return
        name = self.task_name_var.get().strip()
        if not name:
            messagebox.showerror("错误", "任务名称不能为空")
            return

        j_list, j_err = validate_journals(self.journal_var.get())
        k_list, k_err = validate_keywords(self.keyword_var.get())
        (d_start, d_end), d_err = validate_date_range(self.date_var.get())

        all_errors = j_err + k_err + d_err
        if all_errors:
            error_msg = "输入存在以下错误，请修正后再保存：\n\n" + "\n".join(f"• {e}" for e in all_errors)
            messagebox.showerror("输入错误", error_msg)
            return

        if self.current_task_id:
            task = get_task(self.current_task_id)
            task.update({
                "name": name,
                "journals": j_list,
                "keywords": k_list,
                "date_start": d_start,
                "date_end": d_end
            })
            save_task(self.current_task_id, task)
            self.status_var.set(f"{ICONS['check']} 任务「{name}」已保存")
        else:
            task_id = str(uuid.uuid4())[:8]
            task_data = {
                "name": name,
                "journals": j_list,
                "keywords": k_list,
                "date_start": d_start,
                "date_end": d_end,
                "enabled": True,
                "create_time": datetime.now().isoformat()
            }
            save_task(task_id, task_data)
            self.current_task_id = task_id
            self.status_var.set(f"{ICONS['check']} 任务「{name}」已创建")

        self._refresh_task_list()

    def _cancel_edit(self):
        self._new_task()

    def _fill_example(self):
        """快速填入示例数据，让新用户一键跑通"""
        self.task_name_var.set("AI 顶刊监控")
        # 通过期刊库映射示例期刊
        try:
            store = self._journal_store()
            mapped = []
            for nm in ("Nature", "Science", "Cell"):
                j = store.get_by_name(nm, fuzzy=False)
                if j:
                    mapped.append(j)
            if mapped:
                self.selected_journals = mapped
                self.selected_journal_ids = [j.get("jid") for j in mapped]
                self._refresh_journal_tags()
            else:
                self.journal_var.set("Nature;Science;Cell")
        except Exception:
            self.journal_var.set("Nature;Science;Cell")
        self.keyword_var.set("artificial intelligence;machine learning;deep learning")
        self.date_start_var.set("2025-01-01")
        self.date_end_var.set("2026-07-26")
        self.status_var.set("示例已填充，点击「保存任务」→「执行检索」开始使用")
        # 如果当前没有任务，自动新建
        if not self.current_task_id:
            self._save_task()

    def _is_activated_cached(self) -> bool:
        """会话级激活缓存：先查 7 天试用，再查礼品券"""
        if self._activation_cache is None:
            self._activation_cache = coupon_manager.is_feature_allowed()
        return self._activation_cache

    def _get_trial_info(self) -> tuple[bool, int]:
        """获取试用期信息，(is_in_trial, remaining_days)"""
        return coupon_manager.is_trial_period()

    def _invalidate_activation_cache(self):
        """礼品券兑换成功后清除缓存，下次调用重新联网确认"""
        self._activation_cache = None

    def _on_page_changed(self, page):
        """侧栏导航切换后刷新对应页面内容"""
        if page == "dashboard" and hasattr(self, 'dashboard_view'):
            self.dashboard_view.refresh()
        elif page == "library" and hasattr(self, 'library_view'):
            self.library_view.refresh()
        elif page == "ref_formatter" and hasattr(self, '_ref_formatter_view'):
            self._ref_formatter_view.refresh()

    # ===================== 检索执行（一键检索） =====================
    def _run_history(self):
        from core import (
            run_history_search, register_search_cancel, unregister_search_cancel,
            cancel_search,
        )
        # 游客模式不能执行检索（只能查看界面）
        if not self._require_login("执行检索"):
            return
        if not self.current_task_id:
            messagebox.showwarning("提示", "请先保存任务后再执行检索")
            return
        if self._history_running:
            messagebox.showinfo("提示", "历史检索正在执行中，请等待完成")
            return

        # 生成唯一取消 token，隔离于每日推送的取消信号
        import uuid
        self._search_cancel_token = f"history_{uuid.uuid4().hex[:8]}"
        self._cancel_evt = register_search_cancel(self._search_cancel_token)

        # 用户选择保存路径
        from tkinter import filedialog
        task = get_task(self.current_task_id)
        task_name = task["name"] if task else "unknown"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{task_name}_{timestamp}.doc"
        file_path = filedialog.asksaveasfilename(
            title="保存检索报告",
            initialfile=default_name,
            defaultextension=".doc",
            filetypes=[("Word 文档", "*.doc"), ("文本文档", "*.txt"), ("Markdown", "*.md"), ("所有文件", "*.*")],
        )
        if not file_path:
            cancel_search(self._search_cancel_token)
            unregister_search_cancel(self._search_cancel_token)
            return

        self._executing = True
        self._history_running = True
        self._progress_owner = "history"
        # 侧栏标记运行状态
        self.sidebar.set_task_running(self.current_task_id)
        self.progress_var.set(0.0)
        self.progress_label_var.set("0% 准备中")
        self.status_var.set("正在执行检索，请稍候...")
        # 隐藏 idle 线，显示进度条
        self._progress_idle.pack_forget()
        self._progress_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 0))
        # 显示取消按钮
        self._cancel_search_btn.pack(side=tk.RIGHT, padx=(0, 24))
        self.root.update_idletasks()

        self._progress_cb_last_time = 0

        def _progress(ratio, message):
            # 节流：避免高频回调淹没 tkinter 事件队列
            now_m = time.time()
            if ratio < 1.0 and ratio > 0.0 and now_m - self._progress_cb_last_time < 0.3:
                return
            self._progress_cb_last_time = now_m
            self.root.after(0, lambda: self._update_progress(ratio, message))

        def worker():
            try:
                result = run_history_search(self.current_task_id, task, file_path,
                                            progress_callback=_progress,
                                            cancel_token=self._search_cancel_token)
                if isinstance(result, tuple):
                    fp, papers = result
                    # 自动入库到文献书架
                    from core.library import import_papers
                    count = import_papers(papers, task_name)
                    if count > 0:
                        self.root.after(0, lambda c=count: self.status_var.set(
                            f"{ICONS['check']} 检索完成，{count} 篇新论文已收录"))
                    else:
                        self.root.after(0, lambda: self.status_var.set(
                            f"{ICONS['check']} 检索完成，未发现新论文（已在书架中）"))
                else:
                    fp = result
                self.root.after(0, lambda: self._on_history_done(fp))
            except KeyboardInterrupt:
                self.root.after(0, lambda: self._on_history_cancelled())
            except Exception as e:
                from core.translator import TranslationError
                if isinstance(e, TranslationError):
                    self.root.after(0, lambda: self._on_history_error(e))
                else:
                    self.root.after(0, lambda: self._on_history_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, ratio, message, owner=None):
        """更新进度条，支持主人制避免冲突。"""
        # 如果其他操作拥有进度条，缓存在队列中
        if owner and self._progress_owner is not None and self._progress_owner != owner:
            with self._progress_lock:
                self._deferred_progress.append((ratio, message))
            return
        pct = int(ratio * 100)
        self.progress_var.set(ratio)
        # 从消息中提取 "（当前/总数）" 或 "(当前/总数)"，突出显示
        import re
        m = re.search(r'[（(](\d+)/(\d+)[)）]', message)
        if m:
            cnt, total = m.group(1), m.group(2)
            self.progress_label_var.set(f"{cnt}/{total}  |  {pct}%  {message}")
        else:
            self.progress_label_var.set(f"{pct}% {message}")

    def _release_progress(self, owner):
        """释放进度条主人权，转交缓存进度给另一方。"""
        if self._progress_owner != owner:
            return
        self._progress_owner = None
        with self._progress_lock:
            deferred = self._deferred_progress[:]
            self._deferred_progress.clear()
        # 如果有缓存进度且另一方还在运行，自动转交
        if deferred:
            other_owner = "startup_mail" if owner == "history" else "history"
            other_running = (other_owner == "history" and self._history_running) or \
                            (other_owner == "startup_mail" and self._scheduler_daemon_running)
            if other_running:
                self._progress_owner = other_owner
                for r, msg in deferred:
                    self._update_progress(r, msg, owner=other_owner)

    def _on_history_done(self, file_path):
        self._executing = False
        self._history_running = False
        self.sidebar.clear_task_running()
        self._release_progress("history")
        # 注销取消 token
        try:
            unregister_search_cancel(self._search_cancel_token)
        except Exception:
            pass
        self._progress_frame.pack_forget()
        self._progress_idle.pack(side=tk.BOTTOM, fill=tk.X)
        self._cancel_search_btn.pack_forget()
        self.status_var.set(f"{ICONS['check']} 检索完成")
        # 不自动切换书架，只在任务设置页底部显示提示
        # (用户可通过侧栏快捷操作或 Tab 自行切换)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["osascript", "-e",
                    'display notification "检索完成" with title "鸿讯 HONGXUN"'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _show_toast(self, message, action_text=None, action_cmd=None, duration=3):
        """系统通知（优先 macOS 原生通知，回退 Toplevel）"""
        try:
            if sys.platform == "darwin" and not action_text:
                subprocess.Popen(["osascript", "-e",
                    f'display notification "{message}" with title "鸿讯 HONGXUN"'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            elif sys.platform == "win32":
                try:
                    from plyer import notification
                    notification.notify(title="鸿讯 HONGXUN", message=message, timeout=duration)
                    return
                except ImportError:
                    pass
        except Exception:
            pass

        # Fallback Toplevel toast
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=COLORS["bg_page"])

        # 内容容器（圆角卡片）
        frame = tk.Frame(toast, bg=COLORS["bg_card"],
                         highlightbackground=COLORS["border_light"],
                         highlightthickness=1)
        frame.pack(padx=1, pady=1)

        tk.Label(frame, text=message, font=FONT_BODY,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"],
                 anchor=tk.W).pack(side=tk.LEFT, padx=(14, 8), pady=10)

        if action_text:
            btn = tk.Label(frame, text=action_text, font=FONT_BODY_BOLD,
                           fg=COLORS["primary"], bg=COLORS["bg_card"],
                           cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(0, 14), pady=10)
            btn.bind("<Button-1>", lambda e: (toast.destroy(), action_cmd() if action_cmd else None))
            btn.bind("<Enter>", lambda e: btn.configure(fg=COLORS["primary_hover"]))
            btn.bind("<Leave>", lambda e: btn.configure(fg=COLORS["primary"]))

        # 右上角关闭
        close_btn = tk.Label(frame, text="✕", font=FONT_CAPTION,
                             fg=COLORS["text_hint"], bg=COLORS["bg_card"],
                             cursor="hand2")
        close_btn.pack(side=tk.RIGHT, padx=(4, 8), pady=10)
        close_btn.bind("<Button-1>", lambda e: toast.destroy())

        toast.update_idletasks()
        w = toast.winfo_reqwidth()
        h = toast.winfo_reqheight()
        x = self.root.winfo_x() + self.root.winfo_width() - w - 20
        target_y = self.root.winfo_y() + self.root.winfo_height() - h - 60

        # 滑入动画：从下方 30px 处起始，5 步滑到目标位置
        start_y = target_y + 30
        toast.geometry(f"+{x}+{start_y}")

        def _slide_in(step=0):
            if step > 5 or not toast.winfo_exists():
                return
            y_pos = start_y + (target_y - start_y) * (step / 5)
            try:
                toast.geometry(f"+{x}+{int(y_pos)}")
            except Exception:
                pass
            toast.after(30, lambda: _slide_in(step + 1))

        _slide_in()

        # 自动消失
        self.root.after(duration * 1000, lambda: toast.destroy() if toast.winfo_exists() else None)

    def _switch_to_library(self):
        """切换到文献书架页面"""
        if hasattr(self, '_pages'):
            self._show_page("library")
            if hasattr(self, 'sidebar'):
                self.sidebar.set_current_page("library")
        if hasattr(self, 'library_view'):
            self.library_view.refresh()

    def _export_library(self):
        """从概览页导出书架（导出全部论文为 RIS）"""
        if not self._require_login("导出书架"):
            return
        try:
            from core.library import load_library, export_ris
            from tkinter import filedialog
            lib = load_library()
            papers = lib.get("papers", [])
            if not papers:
                messagebox.showwarning("提示", "书架为空，无数据可导出")
                return
            fp = filedialog.asksaveasfilename(
                defaultextension=".ris",
                filetypes=[("RIS 文件", "*.ris")],
                initialfile="hongxun_export.ris")
            if fp:
                export_ris(papers, fp)
                messagebox.showinfo("导出成功", f"已导出 {len(papers)} 篇论文")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ═══ PDF 下载 ═══
    def _browse_pdf_dir(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="选择 PDF 保存目录",
                                    initialdir=self._pdf_dir_var.get() or "~")
        if d:
            self._pdf_dir_var.set(d)
            self._on_pdf_cfg_changed()

    def _on_ai_translate_toggle(self):
        """AI 翻译开关：读写 app_config.translate_enabled。开启时引导配置 API。"""
        cfg = load_app_config()
        enabled = bool(self._ai_translate_toggle.get())
        if enabled and not coupon_manager.is_in_validity():
            # 未激活/已到期 → 回退开关并引导订阅
            self._ai_translate_toggle.set(False)
            self._require_activation("AI 翻译")
            return
        cfg["translate_enabled"] = enabled
        save_app_config(cfg)
        if enabled:
            # 开启后若尚未配置 API Key，引导用户到配置弹窗
            from core.translator import get_api_key
            if not get_api_key():
                self._show_toast("请先配置 LLM API Key")
                self._open_llm_config_dialog()
            else:
                self._show_toast("AI 翻译已开启")
        else:
            self._show_toast("AI 翻译已关闭")

    def _open_llm_config_dialog(self):
        """打开 LLM 大模型 API 配置弹窗（厂商 / Key / Base URL / 模型 + 测试连接）。"""
        from core import translator

        cfg = load_app_config()
        cur_provider = cfg.get("llm_provider", "deepseek") or "deepseek"
        cur_base = (cfg.get("llm_base_url") or "").strip()
        cur_model = (cfg.get("llm_model") or "").strip()
        cur_key = translator.get_api_key()

        win = tk.Toplevel(self.root)
        win.title("AI 翻译 · LLM API 配置")
        win.transient(self.root)
        win.resizable(False, False)
        win.configure(bg=COLORS["bg_page"])
        win.attributes("-topmost", True)

        form = tk.Frame(win, bg=COLORS["bg_page"])
        form.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        def _row():
            r = tk.Frame(form, bg=COLORS["bg_page"])
            r.pack(fill=tk.X, pady=6)
            return r

        # 厂商下拉
        r0 = _row()
        tk.Label(r0, text="厂商", font=FONT_LABEL, fg=COLORS["text_body"],
                 bg=COLORS["bg_page"]).pack(side=tk.LEFT)
        providers_keys = list(translator.PROVIDERS.keys())
        self._llm_provider_var = tk.StringVar(value=cur_provider if cur_provider in providers_keys else "custom")
        self._llm_provider_cb = ttk.Combobox(
            r0, textvariable=self._llm_provider_var, state="readonly",
            values=[translator.PROVIDERS[k]["label"] for k in providers_keys],
            width=34, font=FONT_BODY)
        self._llm_provider_cb.pack(side=tk.LEFT, padx=(10, 0))

        # API Key（掩码 + 可见性切换）
        r1 = _row()
        tk.Label(r1, text="API Key", font=FONT_LABEL, fg=COLORS["text_body"],
                 bg=COLORS["bg_page"]).pack(side=tk.LEFT)
        self._llm_key_var = tk.StringVar(value=cur_key)
        self._llm_key_entry = ModernEntry(r1, textvariable=self._llm_key_var, width=36, show="•")
        self._llm_key_entry.pack(side=tk.LEFT, padx=(10, 0))
        self._llm_key_show = False
        key_eye = tk.Label(r1, text="👁", font=FONT_BODY, fg=COLORS["primary"], cursor="hand2",
                           bg=COLORS["bg_page"])
        key_eye.pack(side=tk.LEFT, padx=(6, 0))
        def _toggle_key_visibility():
            self._llm_key_show = not self._llm_key_show
            self._llm_key_entry.configure(show="" if self._llm_key_show else "•")
            key_eye.configure(text="🙈" if self._llm_key_show else "👁")
        key_eye.bind("<Button-1>", lambda e: _toggle_key_visibility())

        # Base URL
        r2 = _row()
        tk.Label(r2, text="Base URL", font=FONT_LABEL, fg=COLORS["text_body"],
                 bg=COLORS["bg_page"]).pack(side=tk.LEFT)
        self._llm_base_var = tk.StringVar(value=cur_base)
        self._llm_base_entry = ModernEntry(r2, textvariable=self._llm_base_var, width=36)
        self._llm_base_entry.pack(side=tk.LEFT, padx=(10, 0))

        # Model
        r3 = _row()
        tk.Label(r3, text="Model", font=FONT_LABEL, fg=COLORS["text_body"],
                 bg=COLORS["bg_page"]).pack(side=tk.LEFT)
        self._llm_model_var = tk.StringVar(value=cur_model)
        self._llm_model_entry = ModernEntry(r3, textvariable=self._llm_model_var, width=36)
        self._llm_model_entry.pack(side=tk.LEFT, padx=(10, 0))

        # 厂商选择后自动填充预设
        def _on_provider_select(event=None):
            label = self._llm_provider_cb.get()
            key = None
            for k, p in translator.PROVIDERS.items():
                if p["label"] == label:
                    key = k
                    break
            if not key:
                return
            preset = translator.PROVIDERS[key]
            # 仅在用户未手动改过时填充
            if not self._llm_base_var.get().strip():
                self._llm_base_var.set(preset["base_url"])
            if not self._llm_model_var.get().strip():
                self._llm_model_var.set(preset["model"])
        self._llm_provider_cb.bind("<<ComboboxSelected>>", _on_provider_select)
        # 初始按当前 provider 填充默认（combobox 未显示 label 前，直接用 key 填充）
        if cur_provider in translator.PROVIDERS:
            preset = translator.PROVIDERS[cur_provider]
            if not self._llm_base_var.get().strip():
                self._llm_base_var.set(preset["base_url"])
            if not self._llm_model_var.get().strip():
                self._llm_model_var.set(preset["model"])
        # 同步 combobox 显示
        cur_label = translator.PROVIDERS.get(cur_provider, translator.PROVIDERS["custom"])["label"]
        self._llm_provider_cb.set(cur_label)

        # 测试连接 / 保存 / 关闭
        btn_row = tk.Frame(form, bg=COLORS["bg_page"])
        btn_row.pack(fill=tk.X, pady=(16, 0))
        self._llm_test_result = tk.StringVar(value="")
        test_btn = ModernButton(btn_row, text="🔌 测试连接", variant="secondary", height=32,
                                command=lambda: self._test_llm_connection())
        test_btn.pack(side=tk.LEFT)
        save_btn = ModernButton(btn_row, text="保存", variant="primary", height=32,
                                command=lambda: self._save_llm_config(win))
        save_btn.pack(side=tk.LEFT, padx=(10, 0))
        close_btn = ModernButton(btn_row, text="关闭", variant="secondary", height=32,
                                 command=win.destroy)
        close_btn.pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(form, textvariable=self._llm_test_result, font=FONT_CAPTION,
                 fg=COLORS["text_body"], bg=COLORS["bg_page"],
                 wraplength=380, justify=tk.LEFT).pack(fill=tk.X, pady=(12, 0))

        tip = ("提示：\n"
               "· 千问/智谱/DeepSeek/Kimi 直接用官方 API Key 即可，无需额外配置\n"
               "· 豆包（火山方舟）Model 需填「推理接入点 ID」（ep-开头的接入点）\n"
               "· MiniMax 使用 OpenAI 兼容层；旧版需在厂商侧申请兼容访问\n"
               "· 各厂商 Model 下拉后自动填充，可按需修改")
        tk.Label(form, text=tip, font=FONT_CAPTION, fg=COLORS["text_hint"],
                 bg=COLORS["bg_page"], justify=tk.LEFT, wraplength=380).pack(fill=tk.X, pady=(10, 0))

        try:
            win.update_idletasks()
            win.geometry("540x540")
            win.update_idletasks()
        except Exception:
            pass
        try:
            win.lift()
        except Exception:
            pass
        win.grab_set()

    def _test_llm_connection(self):
        """测试 LLM API 连接。"""
        from core import translator
        self._llm_test_result.set("正在测试...")
        key = self._llm_key_var.get().strip()
        base = self._llm_base_var.get().strip()
        model = self._llm_model_var.get().strip()

        def _work():
            ok, msg = translator.test_api_connection(api_key=key, base_url=base, model=model)
            self.root.after(0, lambda: self._llm_test_result.set(("✓ " if ok else "✗ ") + msg))

        threading.Thread(target=_work, daemon=True).start()

    def _save_llm_config(self, win):
        """保存 LLM 配置到 .env + app_config。"""
        from core import translator
        label = self._llm_provider_cb.get()
        provider = "deepseek"
        for k, p in translator.PROVIDERS.items():
            if p["label"] == label:
                provider = k
                break
        key = self._llm_key_var.get().strip()
        base = self._llm_base_var.get().strip()
        model = self._llm_model_var.get().strip()
        try:
            translator.save_env_config(provider, key, base, model)
            messagebox.showinfo("已保存", "LLM API 配置已保存。", parent=win)
            win.destroy()
        except Exception as e:
            messagebox.showerror("保存失败", f"LLM 配置保存失败：{e}", parent=win)

    def _on_pdf_cfg_changed(self):
        from core.pdf_config import save_pdf_config
        try:
            save_pdf_config({
                "pdf_dir": self._pdf_dir_var.get().strip() or os.path.expanduser("~/Downloads/HONGXUN-PDF"),
                "enable_scihub": bool(self._scihub_toggle.get()),
                "unpaywall_email": "691678079@qq.com",
            })
            self._show_toast("PDF 设置已保存")
        except Exception as e:
            messagebox.showerror("保存失败", f"PDF 设置保存失败：{e}")

    def _on_scihub_toggle(self):
        """Sci-Hub 增强开关：开启需激活 + 阅读风险提示并确认。"""
        from core.pdf_config import load_pdf_config, save_pdf_config
        new_state = bool(self._scihub_toggle.get())
        # 关闭 → 直接保存
        if not new_state:
            self._on_pdf_cfg_changed()
            return
        # 开启前先检查激活状态
        if not coupon_manager.is_in_validity():
            self._scihub_toggle.set(False)
            self._require_activation("Sci-Hub 增强")
            return
        # 开启 → 弹风险提示，要求阅读 5s 后才能确认
        cfg = load_pdf_config()
        win = tk.Toplevel(self.root)
        win.title("启用 Sci-Hub 增强")
        win.transient(self.root)
        win.resizable(False, False)
        win.configure(bg=COLORS["bg_page"])

        tk.Label(win, text="⚠ Sci-Hub 版权风险提示", font=FONT_HEADING,
                 fg=COLORS["danger"], bg=COLORS["bg_page"]).pack(pady=(20, 10))
        msg = ("Sci-Hub 通过非官方渠道提供付费论文 PDF，\n"
               "下载受版权保护的文献可能违反当地法律法规，\n"
               "也可能带来网络安全风险。\n\n"
               "请确认你了解并愿意自行承担相关风险。")
        tk.Label(win, text=msg, font=FONT_CAPTION, fg=COLORS["text_body"],
                 bg=COLORS["bg_page"], justify=tk.LEFT).pack(padx=48, pady=(0, 16))


        # 计算加宽 20% 的按钮宽度：先按默认 pad_x 得自然宽度，再乘 1.2
        _probe = ModernButton(win, text="我已阅读风险提示（5 秒后可确认）",
                              variant="primary", height=36, pad_x=20)
        _scihub_btn_w = int(_probe._width * 1.2)
        _probe.destroy()
        self._scihub_agree_btn = ModernButton(win, text="我已阅读风险提示（5 秒后可确认）",
                                              variant="primary", height=36, width=_scihub_btn_w,
                                              command=lambda: self._confirm_scihub(win))
        self._scihub_agree_btn.pack(pady=(4, 6))
        self._scihub_agree_btn.set_enabled(False)  # 初始灰色不可点
        tk.Label(win, text="建议使用机构合法途径获取文献", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_page"]).pack(pady=(0, 14))

        self._scihub_countdown = 5
        self._scihub_after = win.after(1000, lambda: self._scihub_tick(win))
        win.protocol("WM_DELETE_WINDOW", lambda: self._cancel_scihub(win))

        # 确保弹窗尺寸生效（geometry 在子组件全部 pack 后再设置，
        # 否则可能被 pack 的默认尺寸覆盖成 1x1）
        try:
            win.update_idletasks()
            win.geometry("480x300")
            win.update_idletasks()
        except Exception:
            pass
        try:
            win.lift()
        except Exception:
            pass

    def _scihub_tick(self, win):
        """风险提示 5s 倒计时。"""
        if not win.winfo_exists():
            return
        self._scihub_countdown -= 1
        if self._scihub_countdown <= 0:
            self._scihub_agree_btn.set_enabled(True)  # 倒计时结束变蓝可点
            self._scihub_agree_btn.set_text("我已阅读风险提示，确认启用", resize=False)
        else:
            self._scihub_agree_btn.set_enabled(False)
            self._scihub_agree_btn.set_text(
                f"我已阅读风险提示（{self._scihub_countdown} 秒后可确认）",
                resize=False)
            self._scihub_after = win.after(1000, lambda: self._scihub_tick(win))

    def _confirm_scihub(self, win):
        """确认启用 Sci-Hub，并让开关保持开启。"""
        try:
            if self._scihub_after:
                win.after_cancel(self._scihub_after)
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass
        self._scihub_toggle.set(True)
        self._on_pdf_cfg_changed()

    def _cancel_scihub(self, win):
        """取消启用 Sci-Hub：开关回退为关闭，不保存。"""
        try:
            if self._scihub_after:
                win.after_cancel(self._scihub_after)
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass
        self._scihub_toggle.set(False)

    def _download_paper_pdf(self, paper: dict, reopen: bool = False):
        """下载论文 PDF（多来源回退），或打开已下载的 PDF。"""
        if not self._require_login("下载 PDF"):
            return
        from core.pdf_config import load_pdf_config
        from core import pdf_fetcher
        from core.library import update_paper_pdf

        paper_id = paper.get("id") or ""
        if not paper_id:
            messagebox.showwarning("提示", "无法定位论文")
            return

        # 已下载 → 直接打开
        if reopen:
            path = paper.get("pdf_path") or ""
            if path and os.path.exists(path):
                if pdf_fetcher.open_pdf(path):
                    return
                messagebox.showerror("打开失败", f"无法打开 PDF 文件：\n{path}")
            else:
                messagebox.showwarning("提示", "PDF 文件已不存在，请重新下载")
            return

        cfg = load_pdf_config()
        dest_dir = cfg.get("pdf_dir") or os.path.expanduser("~/Downloads/HONGXUN-PDF")

        # 进度窗口
        progress_win = tk.Toplevel(self.root)
        progress_win.title("下载 PDF")
        progress_win.geometry("420x130")
        progress_win.transient(self.root)
        progress_win.resizable(False, False)
        progress_win.configure(bg=COLORS["bg_page"])

        title = (paper.get("title") or "论文")[:40]
        tk.Label(progress_win, text=f"正在下载：{title}",
                 font=FONT_BODY, bg=COLORS["bg_page"],
                 fg=COLORS["text_body"], wraplength=380).pack(pady=(16, 8))
        pb = ttk.Progressbar(progress_win, mode='determinate',
                             style="Horizontal.TProgressbar")
        pb.pack(fill=tk.X, padx=24, pady=8)
        progress_win.update()

        def progress_cb(received, total):
            try:
                pct = int(received / total * 100)
                pb["value"] = pct
                progress_win.update()
            except Exception:
                pass

        def _do_download():
            try:
                result = pdf_fetcher.fetch_pdf_url(
                    paper.get("doi", ""), paper.get("title", ""), cfg)
                if not result:
                    self.root.after(0, lambda: self._on_pdf_done(
                        progress_win, None, None, paper_id,
                        "未找到可下载的开放获取 PDF（合法来源均失败）"))
                    return
                dl = pdf_fetcher.download_pdf(
                    result["pdf_url"], dest_dir, paper, progress_cb)
                self.root.after(0, lambda: self._on_pdf_done(
                    progress_win, dl.get("path"), result.get("source"),
                    paper_id, None))
            except pdf_fetcher.DownloadError as e:
                self.root.after(0, lambda: self._on_pdf_done(
                    progress_win, None, None, paper_id, str(e)))
            except Exception as e:
                self.root.after(0, lambda: self._on_pdf_done(
                    progress_win, None, None, paper_id, f"下载异常：{e}"))

        threading.Thread(target=_do_download, daemon=True).start()

    def _on_pdf_done(self, win, path, source, paper_id, err_msg):
        """下载完成回调（主线程）。path 非空 = 成功。"""
        try:
            if win.winfo_exists():
                win.destroy()
        except Exception:
            pass
        if path:
            update_paper_pdf(paper_id, path, "ok")
            src = f"（来源：{source}）" if source else ""
            self._show_toast(f"PDF 下载完成 {src}")
            if hasattr(self, 'library_view'):
                self.library_view.refresh()
            if messagebox.askyesno("下载完成",
                                   f"PDF 已保存到：\n{path}\n\n是否立即打开？"):
                pdf_fetcher.open_pdf(path)
        else:
            update_paper_pdf(paper_id, "", "failed")
            messagebox.showerror("下载失败", err_msg or "未知错误")

    def _on_history_cancelled(self):
        """检索被用户取消"""
        self._executing = False
        self._history_running = False
        self.sidebar.clear_task_running()
        self._release_progress("history")
        try:
            unregister_search_cancel(self._search_cancel_token)
        except Exception:
            pass
        self._progress_frame.pack_forget()
        self._progress_idle.pack(side=tk.BOTTOM, fill=tk.X)
        self._cancel_search_btn.pack_forget()
        self.status_var.set(f"{ICONS['cancel']} 检索已取消")

    def _on_history_error(self, error_msg):
        self._executing = False
        self._history_running = False
        self.sidebar.clear_task_running()
        self._release_progress("history")
        try:
            unregister_search_cancel(self._search_cancel_token)
        except Exception:
            pass
        self._progress_frame.pack_forget()
        self._progress_idle.pack(side=tk.BOTTOM, fill=tk.X)
        self._cancel_search_btn.pack_forget()
        self.status_var.set(f"{ICONS['error']} 检索出错")

        # 识别 LLM 翻译失败（TranslationError），走专门弹窗
        if isinstance(error_msg, BaseException) or "API Key" in str(error_msg) or \
                str(error_msg).startswith("API 错误") or "翻译" in str(error_msg):
            self._show_llm_error_dialog(str(error_msg))
            return
        self._show_toast(f"{ICONS['error']} 检索失败: {error_msg[:60]}", duration=5)

    def _show_llm_error_dialog(self, reason):
        """LLM API 失败弹窗：提示原因，提供「关闭翻译」/「稍后重试」。"""
        from core.translator import TranslationError
        from core import translator
        code = ""
        if isinstance(reason, BaseException):
            if isinstance(reason, TranslationError):
                code = reason.code
                reason = reason.detail
            else:
                reason = str(reason)
        reason = str(reason)

        # 尝试关闭翻译功能（用户确认后）
        def _disable_translate():
            cfg = load_app_config()
            cfg["translate_enabled"] = False
            save_app_config(cfg)
            try:
                if self._ai_translate_toggle is not None:
                    self._ai_translate_toggle.set(False)
            except Exception:
                pass
            self.status_var.set("AI 翻译已关闭")

        ret = messagebox.askyesnocancel(
            "AI 翻译失败",
            f"LLM 大模型 API 调用失败：\n\n{reason}\n\n"
            f"可能是 API Key 无效/被删除，或账户欠费/配额用尽。\n\n"
            f"「是」→ 关闭 AI 翻译并继续检索（跳过翻译）\n"
            f"「否」→ 保持翻译开启，稍后重试\n"
            f"「取消」→ 本次任务中止")
        if ret is True:
            _disable_translate()
            self._show_toast("AI 翻译已关闭，可重新执行检索")
        elif ret is False:
            self._show_toast("AI 翻译保持开启，请检查 API 配置")
        else:
            self.status_var.set("检索已中止（AI 翻译失败）")

    def _cancel_current_search(self):
        """取消当前正在执行的检索任务"""
        from core import cancel_search
        if not self._history_running:
            return
        ret = messagebox.askyesno("确认取消", "确定要取消当前检索吗？\n已完成的进度不会保存。")
        if ret:
            self.status_var.set("正在取消检索...")
            if hasattr(self, '_search_cancel_token'):
                cancel_search(self._search_cancel_token)

    def _is_daemon_alive(self) -> bool:
        """检查调度守护进程是否仍在运行"""
        if not os.path.exists(SCHEDULER_PID_FILE):
            return False
        try:
            with open(SCHEDULER_PID_FILE, "r", encoding='utf-8') as f:
                pid = int(f.read().strip())
            # 跨平台检查进程是否存在
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x400000, False, pid)  # PROCESS_QUERY_INFORMATION
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (ValueError, ProcessLookupError, OSError, IOError):
            self._cleanup_daemon_pid()
            return False

    def _cleanup_daemon_pid(self):
        """清理残留的 PID 文件和停止标记"""
        for f in [SCHEDULER_PID_FILE, SCHEDULER_STOP_FILE]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

    def _check_scheduler_daemon_status(self):
        """启动后检查调度守护进程是否仍在运行（进程级持久化）"""
        if self._is_daemon_alive():
            # 检查试用期是否已到期——到期则自动暂停
            try:
                if not coupon_manager.is_feature_allowed():
                    self._stop_daemon_scheduler()
                    self._scheduler_daemon_running = False
                    self._update_daily_push_btn(False)
                    self._status_indicator.configure(
                        text=f"{ICONS['dot_off']} 已暂停（试用到期）", fg=COLORS["warning"])
                    self.status_var.set("试用期已结束，每日推送已自动暂停，请使用礼品券激活")
                    self._refresh_status_bar()
                    return
            except Exception:
                pass

            self._scheduler_daemon_running = True
            self._update_daily_push_btn(True)
            self._status_indicator.configure(
                text=f"{ICONS['dot_on']} 推送运行中", fg=COLORS["success"])
            self.status_var.set("每日推送运行中（后台守护进程） | 监控周期：24小时")
            self._refresh_status_bar()

            # 检查是否有未发送附件
            self._check_unsent_attachments()

            # 确保 launchd 开机自启已注册（即便是其他会话启动的守护进程）
            if sys.platform == "darwin" and not is_launchd_installed():
                install_launchd()
            # 确保 Windows 开机自启已注册
            elif sys.platform == "win32" and not is_windows_startup_installed():
                install_windows_startup()
        else:
            # 清理残留
            self._cleanup_daemon_pid()
            self._scheduler_daemon_running = False
            self._update_daily_push_btn(False)
            self._status_indicator.configure(
                text=f"{ICONS['dot_off']} 已暂停", fg=COLORS["warning"])

    def _start_daily_push(self):
        """启动每日推送 — 异步启动外部调度守护进程"""
        # 检查是否已在运行
        if self._is_daemon_alive():
            messagebox.showinfo("提示", "每日推送守护进程已在运行中")
            return

        # 校验所有已启用任务的期刊和关键词是否完整
        tasks = load_all_tasks()
        enabled_tasks = {tid: t for tid, t in tasks.items() if t.get("enabled", True)}

        if not enabled_tasks:
            messagebox.showwarning("提示", "没有已启用的监控任务，请先创建并保存任务")
            return

        # 检查并行任务数不超过5个
        enabled_count = len(enabled_tasks)
        if enabled_count > 5:
            messagebox.showwarning(
                "并行任务超限",
                f"当前已启用 {enabled_count} 个任务，每日推送最多支持5个任务同时运行。\n\n"
                f"请先关闭其他任务后再启动推送。\n（在任务列表中关闭不需要的任务）"
            )
            return

        # 校验每个任务的期刊是否完整（每日推送仅需期刊，不按关键词过滤）
        incomplete_tasks = []
        for tid, t in enabled_tasks.items():
            missing_fields = []
            if not t.get("journals"):
                missing_fields.append("期刊名称")
            if missing_fields:
                incomplete_tasks.append((t["name"], missing_fields))

        if incomplete_tasks:
            msg_parts = []
            for name, fields in incomplete_tasks:
                msg_parts.append(f"任务「{name}」缺少：{'、'.join(fields)}")
            messagebox.showwarning(
                "任务信息不完整",
                "以下任务信息不完整，请完善后重新启动：\n\n" + "\n".join(msg_parts) +
                "\n\n提示：请确保已选中任务并填写期刊名称和关键词。"
            )
            return

        # 检查许可是否激活
        if not self._is_activated_cached():
            if self._require_activation("每日推送"):
                pass
            else:
                return

        # 检查邮箱配置是否完整
        cfg = load_email_config()
        if not cfg.get("sender") or not cfg.get("auth_code"):
            messagebox.showwarning(
                "配置不完整",
                "邮件推送设置未完成，请先填写发件邮箱、SMTP授权码等信息并保存。"
            )
            return

        # 让用户核对收件邮箱
        email_data = load_email_data()
        receivers = email_data.get("receivers", [])
        if not receivers and cfg.get("receiver", "").strip():
            receivers = [cfg["receiver"].strip()]

        if not receivers:
            messagebox.showwarning("提示", "请先添加至少一个收件邮箱")
            return

        receivers_str = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(receivers))
        confirm = messagebox.askyesno(
            "核对收件邮箱",
            f"每日论文推送将通过以下邮箱发送，请确认正确：\n\n{receivers_str}\n\n确认启动自动监控？"
        )
        if not confirm:
            return

        # 启动外部调度守护进程
        # 在 PyInstaller 打包模式下，以 --scheduler 参数调用自身
        is_frozen = getattr(sys, 'frozen', False)
        if is_frozen:
            scheduler_cmd = [sys.executable, "--scheduler"]
        else:
            scheduler_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "scheduler_daemon.py")
            if not os.path.exists(scheduler_path):
                messagebox.showerror("文件缺失", f"找不到调度脚本：{scheduler_path}")
                return
            scheduler_cmd = [sys.executable, scheduler_path]

        try:
            self._cleanup_daemon_pid()

            self._scheduler_process = subprocess.Popen(
                scheduler_cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            # 守护进程等待（最多 6s）移到后台线程，避免卡住 UI
            def _wait_daemon():
                alive = False
                for _ in range(30):
                    if self._is_daemon_alive():
                        alive = True
                        break
                    time.sleep(0.2)
                if alive:
                    self._scheduler_daemon_running = True
                    self.after(0, self._on_daemon_started)
                else:
                    self.after(0, lambda: messagebox.showerror(
                        "启动失败", "调度守护进程启动超时，请重试"))
                    self.after(0, self._reset_push_button)

            import threading
            threading.Thread(target=_wait_daemon, daemon=True).start()

            # 注册 launchd / Windows 开机自启
            if sys.platform == "darwin":
                try:
                    install_launchd()
                except Exception:
                    pass
            elif sys.platform == "win32":
                try:
                    install_windows_startup()
                except Exception:
                    pass

        except Exception as e:
            messagebox.showerror("启动失败", str(e))
            self._reset_push_button()

        # 启动后立即执行一周检索并发送邮件（在后台进行）
        self._do_weekly_startup_mail()

    def _on_daemon_started(self):
        """守护进程启动成功后更新 UI。"""
        self._update_daily_push_btn(True)
        self._status_indicator.configure(
            text=f"{ICONS['dot_on']} 推送运行中", fg=COLORS["success"])
        if not self._history_running and not self._increment_running:
            self.status_var.set("每日推送已启动 | 守护进程将持续运行 | 每日 8:00 自动推送")
        self._refresh_status_bar()
        self._push_toggle_btn.set_enabled(True)
        messagebox.showinfo("每日推送", "每日推送启动成功")

    def _do_weekly_startup_mail(self):
        """启动每日推送后，对所有已启用任务进行近一周检索并合并发送邮件"""
        from core import run_increment_check, send_combined_email
        tasks = load_all_tasks()
        enabled_tasks = {tid: t for tid, t in tasks.items() if t.get("enabled", True)}
        if not enabled_tasks:
            return

        task_names = [t["name"] for t in enabled_tasks.values()]
        self.status_var.set(f"每日推送启动：正在检索 {len(enabled_tasks)} 个任务近一周数据...")
        self._progress_owner = "startup_mail"
        self.progress_var.set(0.0)
        self.progress_label_var.set("0% 近一周检索中...")
        self._progress_idle.pack_forget()
        self._progress_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 0))
        self.root.update_idletasks()

        def _progress(ratio, message):
            self.root.after(0, lambda: self._update_progress(ratio, message, owner="startup_mail"))

        def worker():
            try:
                end_dt = datetime.now()
                start_dt = end_dt - timedelta(days=7)
                start_str = start_dt.strftime("%Y-%m-%d")
                end_str = end_dt.strftime("%Y-%m-%d")

                tid_list = list(enabled_tasks.keys())
                all_results = []
                total_new = 0
                task_details = []
                task_count = len(tid_list)
                failed_tasks = []

                for idx, tid in enumerate(tid_list):
                    task = enabled_tasks[tid]
                    base_progress = 0.05 + (idx / task_count) * 0.55

                    _progress(base_progress, f"正在检索：{task['name']}（{idx+1}/{task_count}）")

                    try:
                        new_papers = run_increment_check(tid, task, start_str=start_str, end_str=end_str)
                        if new_papers:
                            all_results.append((tid, task["name"], new_papers))
                            total_new += len(new_papers)
                            task_details.append(f"{task['name']}（{len(new_papers)}篇）")
                    except Exception as e:
                        failed_tasks.append(task['name'])

                if all_results:
                    _progress(0.70, f"共 {len(all_results)} 个任务有新论文，合并发送邮件中...")

                    try:
                        sent = send_combined_email(all_results)
                        if sent:
                            email_ok = True
                            # 邮件发送成功后再记录推送状态
                            try:
                                for tid_task, tname_task, papers_task in all_results:
                                    add_push_record(tid_task, [p["doi"] for p in papers_task])
                            except Exception:
                                pass
                        else:
                            email_ok = False
                    except Exception:
                        email_ok = False

                    def _show_complete():
                        self._release_progress("startup_mail")
                        self._progress_frame.pack_forget()
                        detail_str = "；".join(task_details) if task_details else "无"
                        if email_ok:
                            self.status_var.set(
                                f"近一周检索完成，已发送 {total_new} 篇论文到邮箱 | 守护进程持续监控中")
                            msg = (
                                f"每日推送启动成功！已完成以下任务的近一周检索并发送邮件：\n\n"
                                f"{chr(10).join(f'  ✓ {d}' for d in task_details)}"
                            )
                            if failed_tasks:
                                msg += f"\n\n以下任务检索失败：{', '.join(failed_tasks)}"
                            messagebox.showinfo("每日推送 · 启动完成", msg)
                        else:
                            self.status_var.set(f"{ICONS['error']} 邮件发送失败，请检查邮箱设置")
                            # 自定义对话框：提示发送失败 + 提供打开文件夹选项
                            fail_dialog = tk.Toplevel(self.root)
                            fail_dialog.withdraw()
                            fail_dialog.title("邮件发送失败")
                            fail_dialog.resizable(False, False)
                            fail_dialog.transient(self.root)
                            fail_dialog.configure(bg=COLORS["bg_page"])

                            tk.Label(fail_dialog, text="⚠ 邮件发送失败",
                                     font=FONT_HEADING, fg=COLORS["danger"],
                                     bg=COLORS["bg_page"]).pack(pady=(20, 10))
                            tk.Label(fail_dialog,
                                     text="论文已检索完成，附件已保存到本地。\n请检查邮箱设置后再尝试发送。",
                                     font=FONT_BODY, fg=COLORS["text_body"],
                                     bg=COLORS["bg_page"], wraplength=320,
                                     justify=tk.LEFT).pack(padx=20, pady=(0, 16))

                            btn_fail_frame = tk.Frame(fail_dialog, bg=COLORS["bg_page"])
                            btn_fail_frame.pack(pady=(0, 16))

                            def _open_and_close():
                                self._open_unsent_folder()
                                fail_dialog.destroy()

                            ModernButton(btn_fail_frame, text=" 打开文件夹 ", variant="primary",
                                         command=_open_and_close).pack(side=tk.LEFT, padx=6)
                            ModernButton(btn_fail_frame, text=" 知道了 ", variant="secondary",
                                         command=fail_dialog.destroy).pack(side=tk.LEFT, padx=6)

                            fail_dialog.update_idletasks()
                            pw, ph = 380, 200
                            px = self.root.winfo_x() + (self.root.winfo_width() - pw) // 2
                            py = self.root.winfo_y() + (self.root.winfo_height() - ph) // 2
                            fail_dialog.geometry(f"{pw}x{ph}+{px}+{py}")
                            fail_dialog.deiconify()
                            fail_dialog.grab_set()
                        self.root.after(0, self._check_unsent_attachments)
                    self.root.after(0, _show_complete)
                else:
                    def _show_no_result():
                        self._release_progress("startup_mail")
                        self._progress_frame.pack_forget()
                        no_new = "所有任务均无新增论文" if not failed_tasks else \
                                 f"有{'，'.join(failed_tasks)}个任务检索失败"
                        self.status_var.set(f"近一周无匹配论文，守护进程持续监控中 | 每日 8:00 推送")
                        messagebox.showinfo("每日推送", f"近一周未检索到符合条件的论文。\n{no_new}\n\n守护进程将持续监控。")
                    self.root.after(0, _show_no_result)

            except Exception as e:
                def _show_err():
                    self._progress_frame.pack_forget()
                    self.status_var.set(f"启动邮件发送失败: {str(e)[:60]}")
                self.root.after(0, _show_err)

        threading.Thread(target=worker, daemon=True).start()

    def _stop_daemon_scheduler(self):
        """停止外部调度守护进程"""
        # 0. 卸载 launchd 开机自启（仅 macOS）
        if sys.platform == "darwin":
            uninstall_launchd()
        # 0b. 卸载 Windows 开机自启
        if sys.platform == "win32":
            uninstall_windows_startup()

        # 1. 写停止标记文件（优雅通知）
        try:
            with open(SCHEDULER_STOP_FILE, "w", encoding='utf-8') as f:
                f.write("stop")
        except Exception:
            pass

        # 2. 发送 SIGTERM（Windows 用 TerminateProcess）
        if os.path.exists(SCHEDULER_PID_FILE):
            try:
                with open(SCHEDULER_PID_FILE, "r", encoding='utf-8') as f:
                    pid = int(f.read().strip())
                if sys.platform == "win32":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
                    if handle:
                        kernel32.TerminateProcess(handle, 0)
                        kernel32.CloseHandle(handle)
                else:
                    os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, OSError, ValueError):
                pass

        # 3. 等待进程退出，最多 5 秒
        for _ in range(25):
            if not self._is_daemon_alive():
                break
            time.sleep(0.2)

        # 4. 清理
        self._cleanup_daemon_pid()

        if self._scheduler_process:
            try:
                self._scheduler_process.poll()
                if self._scheduler_process.returncode is None:
                    self._scheduler_process.kill()
            except Exception:
                pass
            self._scheduler_process = None

        self._scheduler_daemon_running = False

    def _on_push_time_changed(self):
        """用户选择新的每日推送时间，保存到 app_config。"""
        try:
            cfg = load_app_config()
            cfg["push_time"] = self._push_time_var.get() or "08:00"
            save_app_config(cfg)
            self._push_time_label.configure(text=f"每日 {cfg['push_time']}")
            self._show_toast(f"推送时间已设为 {cfg['push_time']}（重启推送后生效）")
        except Exception as e:
            messagebox.showerror("保存失败", f"推送时间保存失败：{e}")

    def _toggle_scheduler(self):
        """切换每日推送开/关（启动/停止外部守护进程，带即时反馈）"""
        if not self._scheduler_daemon_running:
            # 当前是暂停状态 → 启动
            # ✅ 立即给反馈：按钮禁用 + 「启动中...」
            self._push_toggle_btn.set_enabled(False)
            self._push_toggle_btn.set_text("启动中...", variant="primary")
            self.status_var.set("正在启动每日推送守护进程...")
            self._refresh_status_bar()

            # 确保有选中任务：如果没有则自动选第一个可用任务
            if not self.current_task_id:
                tasks = load_all_tasks()
                if not tasks:
                    messagebox.showwarning("提示", "请先创建并保存任务后再启动每日推送")
                    self._reset_push_button()
                    return
                first_id = next(iter(tasks))
                self.current_task_id = first_id
                self._load_task_to_form(first_id)
                if hasattr(self, 'sidebar'):
                    self.sidebar.select_task(first_id)

            if not self._require_activation("每日推送"):
                self._reset_push_button()
                return

            # 启动（校验/确认在主线程，守护进程等待在 _start_daily_push 内线程化）
            self._start_daily_push()
        else:
            # 当前是运行状态 → 关闭
            ret = messagebox.askyesno(
                "确认关闭",
                "确定要关闭每日推送吗？\n\n"
                "关闭后守护进程将退出，不再自动检测和推送论文。"
            )
            if not ret:
                return

            self._push_toggle_btn.set_enabled(False)
            self._push_toggle_btn.set_text("关闭中...", variant="danger")

            self._stop_daemon_scheduler()

            self._update_daily_push_btn(False)
            self._status_indicator.configure(
                text=f"{ICONS['dot_off']} 已暂停", fg=COLORS["warning"])
            self.status_var.set("每日推送已关闭")
            self._refresh_status_bar()
            self._push_toggle_btn.set_enabled(True)

    def _reset_push_button(self):
        """重置推送按钮状态（启动失败/校验不通过时）。"""
        try:
            self._push_toggle_btn.set_enabled(True)
            self._push_toggle_btn.set_text("启动每日推送", variant="primary")
            self.status_var.set("每日推送未启动")
            self._refresh_status_bar()
        except Exception:
            pass

    def _update_daily_push_btn(self, running: bool):
        """更新侧栏和右侧推送状态"""
        if running:
            self._push_status_indicator.configure(text="●", fg=COLORS["success"])
            self._push_status_text.configure(text="每日推送运行中", fg=COLORS["success"])
            self._push_toggle_btn.set_text("暂停推送", variant="danger")
            # 刷新统计数据
            self._update_push_stats()
        else:
            self._push_status_indicator.configure(text="○", fg=COLORS["dot_off"])
            self._push_status_text.configure(text="每日推送未启动", fg=COLORS["text_body"])
            self._push_toggle_btn.set_text("启动每日推送", variant="primary")
        # 同步侧栏底部推送状态
        if hasattr(self, 'sidebar'):
            self.sidebar.set_push_status(running)

    def _update_push_stats(self):
        """从推送记录计算统计信息"""
        from core.config_manager import load_push_records
        records = load_push_records()
        all_dois = set()
        journal_set = set()
        for tid, dois in records.items():
            all_dois.update(dois)
            task = get_task(tid)
            if task:
                for j in task.get("journals", []):
                    journal_set.add(j)
        self._push_journal_label.configure(text=f"{len(journal_set)} 个")
        self._push_total_label.configure(text=f"{len(all_dois)} 篇")

    def _require_activation(self, feature_name: str) -> bool:
        """检查是否已激活，未激活则弹出引导（引导订阅付费）。返回是否已激活。"""
        # 用统一有效期检测（试用 / 礼品券 / 订阅 / 宽限）
        if coupon_manager.is_in_validity():
            self._activation_cache = True
            return True

        # 检查试用期是否刚到期
        trial_over = False
        try:
            _, remaining = coupon_manager.is_trial_period()
            if remaining <= 0:
                trial_over = True
        except Exception:
            trial_over = True

        result = [False]
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.title("功能激活")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg=COLORS["bg_page"])

        if trial_over:
            heading = f"🔒 「{feature_name}」试用已到期"
            desc = "7 天免费试用已结束，开通订阅即可继续使用此功能。"
        else:
            heading = f"🔒 「{feature_name}」需要激活"
            desc = "开通订阅服务后即可使用此功能。"

        tk.Label(dialog, text=heading,
                 font=FONT_HEADING, fg=COLORS["text_title"],
                 bg=COLORS["bg_page"]).pack(pady=(20, 6))
        tk.Label(dialog, text=desc,
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_page"]).pack(pady=(0, 10))

        btn_frame = tk.Frame(dialog, bg=COLORS["bg_page"])

        def on_now():
            result[0] = True
            dialog.destroy()

        def on_later():
            result[0] = False
            dialog.destroy()

        # 立即订阅（主按钮）→ 打开订阅付费弹窗
        ModernButton(btn_frame, text="  💳 立即订阅  ", variant="primary",
                     command=on_now).pack(side=tk.LEFT, padx=8)
        ModernButton(btn_frame, text="  稍后再说  ", variant="secondary",
                     command=on_later).pack(side=tk.LEFT, padx=8)

        # 全部构建完成后才显示
        dialog.update_idletasks()
        dialog.geometry("440x200")
        x = self.root.winfo_x() + (self.root.winfo_width() - 440) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 200) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        dialog.deiconify()

        self.root.wait_window(dialog)

        if result[0]:
            self._open_subscription_dialog()
            return self._is_activated_cached()
        return False

    def _open_subscription_dialog(self):
        """订阅付费弹窗（专业版 UI）：左品牌价值区 + 右套餐定价区，扫码支付轮询激活。"""
        from core import subscription

        W, H = 680, 480
        LEFT_W = int(W * 0.4)          # 272
        RIGHT_W = W - LEFT_W           # 408

        win = tk.Toplevel(self.root)
        win.title("开通订阅")
        win.overrideredirect(True)
        win.transient(self.root)
        win.configure(bg=COLORS["bg_page"])
        win.attributes("-topmost", True)
        win.resizable(False, False)

        # 居中于主窗口
        try:
            win.update_idletasks()
            x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - W) // 2)
            y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - H) // 2)
            win.geometry(f"{W}x{H}+{x}+{y}")
        except Exception:
            win.geometry(f"{W}x{H}")

        # ── 细边框 + 白底主体 ──
        outer = tk.Frame(win, bg=COLORS["border"])
        outer.pack(fill=tk.BOTH, expand=True)
        card = tk.Frame(outer, bg="#FFFFFF")
        card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        body = tk.Frame(card, bg="#FFFFFF")
        body.pack(fill=tk.BOTH, expand=True)

        # 关闭按钮（右上角）
        close_btn = tk.Label(card, text="✕", font=(_ui_font_family(), 14, "bold"),
                             fg=COLORS["text_hint"], bg="#FFFFFF", cursor="hand2")
        close_btn.place(x=W - 34, y=10)

        def _close(_e=None):
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        close_btn.bind("<Button-1>", _close)
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=COLORS["text_title"]))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=COLORS["text_hint"]))
        win.bind("<Escape>", _close)

        # ════════════ 左侧：品牌价值区（40%） ════════════
        left = tk.Canvas(body, width=LEFT_W, highlightthickness=0, bd=0, bg="#EFF6FF")
        left.pack(side=tk.LEFT, fill=tk.Y)
        # 浅蓝渐变（EFF6FF → DBEAFE，从上到下）
        # 优化：4px 一条色带代替逐像素（480→120 个元素），视觉几乎无差别，渲染更快
        for yy in range(0, H, 4):
            col = lerp_color("#EFF6FF", "#DBEAFE", yy / float(H))
            left.create_rectangle(0, yy, LEFT_W, min(yy + 4, H), fill=col, outline="")

        # Logo（放大居中）
        logo_img = None
        try:
            logo_img = self._load_scaled_icon(ICON_APP, 80)
        except Exception:
            logo_img = None
        if logo_img:
            left.create_image(LEFT_W / 2, 96, image=logo_img)
            self._icon_refs.append(logo_img)
        else:
            left.create_text(LEFT_W / 2, 96, text=ICONS["logo"],
                             font=(_ui_font_family(), 44, "bold"), fill="#3B82F6")
        # 图标下方装饰线
        left.create_line(LEFT_W / 2 - 24, 140, LEFT_W / 2 + 24, 140, fill="#93C5FD", width=1.5)
        # 主标题 / 副标题
        left.create_text(LEFT_W / 2, 178, text="解锁鸿讯专业版",
                         font=(_ui_font_family(), 22, "bold"), fill="#1E293B")
        left.create_text(LEFT_W / 2, 210, text="让科研管理更高效",
                         font=(_ui_font_family(), 14), fill="#64748B")

        # 价值点列表
        features = [
            "每日邮件推送服务",
            "无限监控任务数量",
            "实验中心全模块开放",
            "后续新功能优先体验",
        ]
        fy = 252
        for feat in features:
            left.create_text(40, fy, text="✓", font=(_ui_font_family(), 16, "bold"),
                             fill="#10B981", anchor=tk.CENTER)
            left.create_text(64, fy, text=feat, font=(_ui_font_family(), 14),
                             fill="#334155", anchor=tk.W)
            fy += 48  # 行距 40 → 48（+20%）

        # 底部信任背书
        left.create_text(LEFT_W / 2, H - 56, text="⭐⭐⭐⭐⭐ 4.9 分用户评价",
                         font=(_ui_font_family(), 12), fill="#94A3B8")
        left.create_text(LEFT_W / 2, H - 30, text="已有 1,200+ 科研工作者选择",
                         font=(_ui_font_family(), 13), fill="#94A3B8")

        # ════════════ 右侧：套餐定价区（60%） ════════════
        right = tk.Frame(body, bg="#FFFFFF", width=RIGHT_W)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right.pack_propagate(False)

        self._sub_plan_var = tk.StringVar(value=subscription.DEFAULT_PLAN)

        def _rounded_rect(c, x1, y1, x2, y2, r, **kw):
            pts = [x1 + r, y1, x2 - r, y1, x2, y1,
                   x2, y1 + r, x2, y2 - r, x2, y2,
                   x2 - r, y2, x1 + r, y2, x1, y2,
                   x1, y2 - r, x1, y1 + r, x1, y1]
            return c.create_polygon(pts, smooth=True, **kw)

        # ── 套餐选择行（4 档横向胶囊）──
        pill_row = tk.Frame(right, bg="#FFFFFF")
        self._sub_pill_row = pill_row
        self._sub_pills = {}

        def _select_plan(key):
            self._sub_plan_var.set(key)
            for k, b in self._sub_pills.items():
                b.set_text(subscription.PLANS[k]["label"],
                           variant="primary" if k == key else "secondary")
            _redraw_price_card(key)
            # resize=False：保持按钮宽度一致，避免不同价格位数导致按钮长短变化
            self._sub_cta.set_text(f"立即解锁 · ¥{subscription.PLANS[key]['price']}",
                                   resize=False)

        for key in subscription.PLANS:
            p = subscription.PLANS[key]
            is_def = (key == subscription.DEFAULT_PLAN)
            btn = ModernButton(pill_row, text=p["label"], height=30,
                               variant="primary" if is_def else "secondary",
                               command=lambda k=key: _select_plan(k))
            btn.pack(side=tk.LEFT, padx=4)
            self._sub_pills[key] = btn

        # ── 价格卡片（蓝边高亮）──
        # 蓝色边框范围缩小 15%（S=0.85），内部内容坐标与字号同步按相同比例缩放
        _PC_S = 0.85
        self._sub_price_card = tk.Canvas(right,
                                         width=round(400 * _PC_S), height=round(170 * _PC_S),
                                         highlightthickness=0, bd=0, bg="#FFFFFF")
        self._sub_price_card.pack(pady=(26, 6))

        def _redraw_price_card(key):
            p = subscription.PLANS[key]
            c = self._sub_price_card
            c.delete("all")
            w, h = round(400 * _PC_S), round(170 * _PC_S)  # 340 x 145
            # 蓝色柔光阴影
            c.create_polygon(4, 6, w - 4, 6, w - 4, h + 6, 4, h + 6,
                             fill="#DBEAFE", outline="")
            # 白卡 + 1.5px 蓝色边框（范围同步缩小）
            _rounded_rect(c, 1, 1, w - 1, h - 1, round(12 * _PC_S), fill="#FFFFFF",
                          outline="#3B82F6", width=2)

            # ── 折扣徽章（右上角，同步缩放）──
            badge_w, badge_h = round(104 * _PC_S), round(36 * _PC_S)   # 88 x 31
            badge_x = w - badge_w - round(10 * _PC_S)
            badge_y = round(10 * _PC_S)
            _rounded_rect(c, badge_x, badge_y, badge_x + badge_w, badge_y + badge_h,
                          round(18 * _PC_S), fill="#EF4444", outline="")
            c.create_text(badge_x + badge_w / 2, badge_y + badge_h / 2,
                          text=f"🔥 {p['discount']}",
                          fill="#FFFFFF", font=(_ui_font_family(), round(14 * _PC_S), "bold"))
            # 稀缺性提示（徽章旁小字）
            c.create_text(w - round(10 * _PC_S), badge_y + badge_h + round(12 * _PC_S),
                          text="限时特惠，即将恢复原价",
                          font=(_ui_font_family(), round(10 * _PC_S)), fill="#F59E0B", anchor=tk.E)

            # ── 原价（删除线，同步缩放）──
            # 永久档不显示原价删除线（无期限概念）
            if not p.get("permanent"):
                orig = f"原价 ¥{p['origin_price']}"
                orig_y = round(42 * _PC_S)
                orig_font = (_ui_font_family(), round(16 * _PC_S))
                orig_id = c.create_text(round(28 * _PC_S), orig_y, text=orig, font=orig_font,
                                        fill="#94A3B8", anchor=tk.W)
                # 删除线：精确计算文字宽度，线在文字垂直中间
                try:
                    orig_bbox = c.bbox(orig_id)
                    orig_w = orig_bbox[2] - orig_bbox[0]
                    orig_x_start = orig_bbox[0]
                    line_y = orig_y  # 文字基线附近，正好穿过中间
                except Exception:
                    orig_w = round(10 * _PC_S) * len(orig)
                    orig_x_start = round(28 * _PC_S)
                    line_y = orig_y
                # 删除线（从文字左边到右边，垂直居中）
                c.create_line(orig_x_start - 2, line_y, orig_x_start + orig_w + 2, line_y,
                              fill="#94A3B8", width=1.5)

            # ── 现价（超大字号，视觉中心，同步缩放）──
            price_num = str(p['price'])
            price_y = round(96 * _PC_S)
            # ¥ 符号（小一号）
            yuan_font = (_ui_font_family(), round(28 * _PC_S), "bold")
            yuan_id = c.create_text(round(28 * _PC_S), price_y, text="¥", font=yuan_font,
                                    fill="#1D4ED8", anchor=tk.W)
            try:
                yuan_w = c.bbox(yuan_id)[2] - round(28 * _PC_S)
            except Exception:
                yuan_w = round(22 * _PC_S)
            # 价格数字（超大）
            num_font = (_ui_font_family(), round(52 * _PC_S), "bold")
            num_id = c.create_text(round(28 * _PC_S) + yuan_w + round(4 * _PC_S), price_y,
                                   text=price_num, font=num_font,
                                   fill="#1D4ED8", anchor=tk.W)
            try:
                num_w = c.bbox(num_id)[2] - (round(28 * _PC_S) + yuan_w + round(4 * _PC_S))
            except Exception:
                num_w = round(32 * _PC_S) * len(price_num)
            # 「/月|年|永久」后缀
            suffix = f"/{p['label']}"
            suffix_font = (_ui_font_family(), round(18 * _PC_S))
            c.create_text(round(28 * _PC_S) + yuan_w + round(4 * _PC_S) + num_w + round(10 * _PC_S),
                          price_y, text=suffix,
                          font=suffix_font, fill="#64748B", anchor=tk.W)

            # ── 单位说明 ──
            if p.get("permanent"):
                unit_text = "一次付费 · 永久使用 · 含后续所有更新"
            elif p.get("daily") is not None:
                unit_text = f"一次付费 · 每天折合 ¥{p['daily']} 元 · 到期自动停止"
            else:
                unit_text = "一次付费 · 到期自动停止"
            c.create_text(round(28 * _PC_S), round(140 * _PC_S),
                          text=unit_text,
                          font=(_ui_font_family(), round(12 * _PC_S)), fill="#64748B", anchor=tk.W)

        _redraw_price_card(subscription.DEFAULT_PLAN)

        # 套餐选择移到价格卡片下方（价格优先，提升转化率）
        pill_row.pack(pady=(2, 0))

        # 最推荐标签（默认套餐胶囊上加引导，字号调大 100%）
        self._sub_reco_tag = tk.Label(right, text="★ 最推荐", font=(_ui_font_family(), 20, "bold"),
                                      fg=COLORS["primary"], bg="#FFFFFF")
        self._sub_reco_tag.pack(pady=(4, 0))

        # ── 主行动按钮（CTA，加宽）──
        self._sub_cta = ModernButton(
            right,
            text=f"立即解锁 · ¥{subscription.PLANS[subscription.DEFAULT_PLAN]['price']}",
            variant="primary", height=50, width=400,
            command=lambda: self._start_sub_payment(win))
        self._sub_cta.pack(pady=(10, 0))

        # ── 次级选项：继续试用 ──
        def _on_trial(e=None):
            _close()
            try:
                in_trial, remain = coupon_manager.is_trial_period()
            except Exception:
                in_trial, remain = False, 0
            if in_trial:
                messagebox.showinfo("免费试用",
                                    f"您当前处于 {remain} 天免费试用期，可继续使用全部功能。")
            else:
                messagebox.showinfo("免费试用",
                                    "7 天免费试用已结束，开通订阅即可继续使用全部功能。")

        self._sub_trial_link = tk.Label(right, text="继续使用 7 天免费试用",
                                        font=(_ui_font_family(), 13),
                                        fg=COLORS["text_secondary"], bg="#FFFFFF", cursor="hand2")
        self._sub_trial_link.pack(pady=(10, 0))
        self._sub_trial_link.bind("<Button-1>", _on_trial)
        self._sub_trial_link.bind("<Enter>",
                                  lambda e: self._sub_trial_link.config(fg="#2563EB"))
        self._sub_trial_link.bind("<Leave>",
                                  lambda e: self._sub_trial_link.config(fg=COLORS["text_secondary"]))

        # 注册邮箱入口（邮箱注册制，注册后作为每日推送默认邮箱）
        self._sub_reg_link = tk.Label(right, text="📧 注册邮箱 · 每日推送默认邮箱",
                                      font=(_ui_font_family(), 12),
                                      fg=COLORS["primary"], bg="#FFFFFF", cursor="hand2")
        self._sub_reg_link.pack(pady=(4, 0))
        self._sub_reg_link.bind("<Button-1>",
                                lambda e: self._open_login_dialog())
        self._sub_reg_link.bind("<Enter>",
                                lambda e: self._sub_reg_link.config(fg="#2563EB"))
        self._sub_reg_link.bind("<Leave>",
                                lambda e: self._sub_reg_link.config(fg=COLORS["primary"]))

        # ── 底部保障信息 ──
        footer = tk.Frame(right, bg="#FFFFFF")
        footer.pack(side=tk.BOTTOM, pady=(0, 14))
        for t in ["🔒 安全支付", "·", "✓ 终身更新", "·", "⭐ 4.9 用户评价"]:
            tk.Label(footer, text=t, font=(_ui_font_family(), 11),
                     fg=COLORS["text_hint"], bg="#FFFFFF").pack(side=tk.LEFT, padx=4)

        # ── 二维码区（点「立即解锁」后显示）──
        self._sub_qr_frame = tk.Frame(right, bg="#FFFFFF")
        self._sub_qr_canvas = tk.Canvas(self._sub_qr_frame, width=200, height=200,
                                        highlightthickness=1, bd=0,
                                        highlightbackground=COLORS["border"], bg="#FFFFFF")
        self._sub_qr_plan_label = tk.Label(self._sub_qr_frame, text="",
                                           font=FONT_BODY_BOLD,
                                           fg=COLORS["text_title"], bg="#FFFFFF")
        self._sub_status_label = tk.Label(self._sub_qr_frame, text="",
                                          font=FONT_CAPTION,
                                          fg=COLORS["text_secondary"], bg="#FFFFFF")
        self._sub_back_link = ModernButton(self._sub_qr_frame, text="← 返回修改套餐",
                                           variant="secondary", height=30,
                                           pad_x=14, command=self._show_sub_back)

        # ── 支付成功区 ──
        self._sub_success_frame = tk.Frame(right, bg="#FFFFFF")
        self._sub_success_canvas = tk.Canvas(self._sub_success_frame, width=96, height=96,
                                             highlightthickness=0, bd=0, bg="#FFFFFF")
        self._sub_success_title = tk.Label(self._sub_success_frame, text="支付成功！",
                                           font=(_ui_font_family(), 20, "bold"),
                                           fg=COLORS["success"], bg="#FFFFFF")
        self._sub_success_sub = tk.Label(self._sub_success_frame,
                                         text="订阅已自动激活，全部功能已解锁",
                                         font=FONT_CAPTION,
                                         fg=COLORS["text_secondary"], bg="#FFFFFF")

        # 收尾：置顶 + 模态
        try:
            win.update_idletasks()
            win.lift()
        except Exception:
            pass
        win.grab_set()

    def _show_sub_qr(self):
        """点「立即解锁」后隐藏定价区，显示二维码与支付状态。"""
        from core import subscription
        for w in (self._sub_pill_row, self._sub_price_card, self._sub_reco_tag,
                  self._sub_cta, self._sub_trial_link):
            try:
                w.pack_forget()
            except Exception:
                pass
        self._sub_qr_frame.pack(pady=(26, 4))
        self._sub_qr_canvas.pack()
        self._sub_qr_plan_label.pack(pady=(8, 0))
        self._sub_status_label.pack(pady=(4, 0))
        self._sub_back_link.pack(pady=(6, 0))
        self._render_mock_qr()

    def _show_sub_back(self):
        """从二维码区返回套餐选择。"""
        self._sub_qr_frame.pack_forget()
        self._sub_success_frame.pack_forget()
        self._sub_price_card.pack(pady=(26, 6))
        self._sub_pill_row.pack(pady=(2, 0))
        self._sub_reco_tag.pack(pady=(4, 0))
        self._sub_cta.pack(pady=(10, 0))
        self._sub_trial_link.pack(pady=(10, 0))

    def _show_sub_success(self):
        """支付成功后原地切换为成功状态（绿色对勾）。"""
        self._sub_qr_frame.pack_forget()
        self._sub_success_frame.pack(pady=(34, 4))
        self._sub_success_canvas.pack()
        self._sub_success_title.pack(pady=(8, 0))
        self._sub_success_sub.pack(pady=(4, 0))
        c = self._sub_success_canvas
        c.create_oval(6, 6, 90, 90, outline="#10B981", width=6)
        c.create_line(28, 50, 42, 66, fill="#10B981", width=7,
                      capstyle=tk.ROUND, joinstyle=tk.ROUND)
        c.create_line(42, 66, 70, 32, fill="#10B981", width=7,
                      capstyle=tk.ROUND, joinstyle=tk.ROUND)

    def _render_mock_qr(self):
        """绘制占位二维码图案（虚假二维码），下方标注套餐与金额。"""
        try:
            from core import subscription
            plan = self._sub_plan_var.get()
            p = subscription.PLANS[plan]
            order = subscription.create_order(plan)
            qr_text = order["qr_content"]
            self._sub_qr_canvas.delete("all")
            w, h = 200, 200
            # 白底
            self._sub_qr_canvas.create_rectangle(0, 0, w, h, fill="#FFFFFF", outline="")
            # 伪随机点阵（模拟二维码）
            import hashlib
            seed = int(hashlib.md5(qr_text.encode()).hexdigest()[:8], 16)
            import random
            random.seed(seed)
            cell = 9
            for y in range(24, h - 24, cell):
                for x in range(24, w - 24, cell):
                    if random.random() < 0.45:
                        self._sub_qr_canvas.create_rectangle(x, y, x + cell, y + cell,
                                                             fill="#1E293B", outline="")
            # 三个定位角
            for ox, oy in [(8, 8), (w - 48, 8), (8, h - 48)]:
                self._sub_qr_canvas.create_rectangle(ox, oy, ox + 40, oy + 40,
                                                     fill="#1E293B", outline="")
                self._sub_qr_canvas.create_rectangle(ox + 8, oy + 8, ox + 32, oy + 32,
                                                     fill="#FFFFFF", outline="")
                self._sub_qr_canvas.create_rectangle(ox + 16, oy + 16, ox + 24, oy + 24,
                                                     fill="#1E293B", outline="")
            self._sub_qr_plan_label.configure(
                text=f"{p['label']} · ¥{p['price']} · 开通后可用 {p['days']} 天")
        except Exception:
            self._sub_qr_canvas.create_text(100, 100, text="（二维码占位）",
                                            fill="#64748B")

    def _start_sub_payment(self, win):
        """开始支付流程：显示二维码 → 生成订单 → 轮询查询 → 支付成功激活。"""
        from core import subscription
        plan = self._sub_plan_var.get()
        p = subscription.PLANS[plan]

        # 点击支付后显示二维码
        self._show_sub_qr()

        # 生成订单
        self._sub_status_label.configure(text=f"订单生成中 · {p['label']} ¥{p['price']} ...")
        try:
            order = subscription.create_order(plan)
        except Exception as e:
            self._sub_status_label.configure(text=f"下单失败：{e}")
            return
        order_id = order["order_id"]
        self._sub_status_label.configure(
            text=f"请使用微信/支付宝扫码支付 ¥{p['price']}，支付完成后将自动解锁")

        def _close_safe():
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        def _poll():
            if not win.winfo_exists():
                return
            try:
                status = subscription.query_order(order_id)
            except Exception:
                status = "pending"
            if status == "paid":
                ok = subscription.activate_subscription(plan)
                if ok:
                    from core.config_manager import load_app_config, save_app_config
                    cfg = load_app_config()
                    cfg["translate_enabled"] = True
                    save_app_config(cfg)
                    try:
                        if self._ai_translate_toggle is not None:
                            self._ai_translate_toggle.set(True)
                    except Exception:
                        pass
                    self._invalidate_activation_cache()
                    self._update_license_status()
                    try:
                        self._show_sub_success()
                    except Exception:
                        pass
                    win.after(1500, _close_safe)
                else:
                    self._sub_status_label.configure(text="激活失败，请重试")
                    win.after(2000, _poll)
                return
            elif status == "failed":
                self._sub_status_label.configure(text="支付失败，请重试")
                return
            win.after(2000, _poll)

        _poll()
    # ===================== 登录 / 注册 =====================

    def _open_login_dialog(self, parent=None):
        """登录弹窗：邮箱 + 密码验证登录。"""
        from core import user_manager
        parent = parent or self.root

        win = tk.Toplevel(parent)
        win.title("登录")
        win.geometry("440x320")
        win.minsize(420, 300)
        win.transient(parent)
        win.configure(bg=COLORS["bg_page"])
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass

        tk.Label(win, text="🔐 登录鸿讯 HONGXUN", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"]).pack(
            anchor=tk.W, padx=20, pady=(18, 4))
        tk.Label(win, text="使用注册邮箱和密码登录",
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_page"]).pack(anchor=tk.W, padx=20, pady=(0, 12))

        form = tk.Frame(win, bg=COLORS["bg_page"])
        form.pack(fill=tk.X, padx=20)

        tk.Label(form, text="邮箱：", font=FONT_BODY,
                 fg=COLORS["text_body"], bg=COLORS["bg_page"]).pack(anchor=tk.W)
        email_entry = tk.Entry(form, font=FONT_BODY, relief="flat",
                               highlightthickness=1,
                               highlightbackground=COLORS["border"],
                               bg=COLORS["bg_input"], fg=COLORS["text_body"])
        email_entry.pack(fill=tk.X, ipady=5, pady=(2, 4))

        tk.Label(form, text="密码：", font=FONT_BODY,
                 fg=COLORS["text_body"], bg=COLORS["bg_page"]).pack(anchor=tk.W)
        pwd_entry = tk.Entry(form, font=FONT_BODY, relief="flat", show="•",
                             highlightthickness=1,
                             highlightbackground=COLORS["border"],
                             bg=COLORS["bg_input"], fg=COLORS["text_body"])
        pwd_entry.pack(fill=tk.X, ipady=5, pady=(2, 4))

        self._login_status = tk.Label(form, text="", font=FONT_CAPTION,
                                      fg=COLORS["text_secondary"], bg=COLORS["bg_page"])
        self._login_status.pack(anchor=tk.W, pady=(6, 0))

        btn_row = tk.Frame(win, bg=COLORS["bg_page"])
        btn_row.pack(pady=(12, 16))
        ModernButton(btn_row, text="登录", variant="primary", height=38,
                     command=lambda: _do_login()).pack(side=tk.LEFT, padx=6)
        ModernButton(btn_row, text="注册账号", variant="secondary", height=38,
                     command=lambda: (win.destroy(), self._open_register_dialog(parent))
                     ).pack(side=tk.LEFT, padx=6)
        ModernButton(btn_row, text="关闭", variant="secondary", height=38,
                     command=win.destroy).pack(side=tk.LEFT, padx=6)

        def _do_login():
            email = email_entry.get().strip()
            pwd = pwd_entry.get().strip()
            if not email or not pwd:
                self._login_status.configure(text="请输入邮箱和密码", fg=COLORS["warning"])
                return
            try:
                ok, msg = user_manager.login(email, pwd)
            except Exception as e:
                ok, msg = False, f"登录失败：{e}"
            self._login_status.configure(text=msg,
                                         fg=COLORS["success"] if ok else COLORS["danger"])
            if ok:
                self._refresh_login_status()
                win.after(1200, win.destroy)

    def _open_register_dialog(self, parent=None):
        """注册弹窗：注册邮箱 + 验证码 + 密码设置 + 邀请码（选填）。"""
        from core import user_manager
        parent = parent or self.root

        win = tk.Toplevel(parent)
        win.title("注册")
        win.geometry("460x440")
        win.minsize(440, 420)
        win.transient(parent)
        win.configure(bg=COLORS["bg_page"])
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass

        tk.Label(win, text="📧 注册鸿讯 HONGXUN", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"]).pack(
            anchor=tk.W, padx=20, pady=(18, 4))
        tk.Label(win, text="注册后即可使用免费版功能（检索 / 书架 / 格式助手）",
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_page"]).pack(anchor=tk.W, padx=20, pady=(0, 12))

        form = tk.Frame(win, bg=COLORS["bg_page"])
        form.pack(fill=tk.X, padx=20)

        tk.Label(form, text="注册邮箱：", font=FONT_BODY,
                 fg=COLORS["text_body"], bg=COLORS["bg_page"]).pack(anchor=tk.W)
        email_entry = tk.Entry(form, font=FONT_BODY, relief="flat",
                               highlightthickness=1,
                               highlightbackground=COLORS["border"],
                               bg=COLORS["bg_input"], fg=COLORS["text_body"])
        email_entry.pack(fill=tk.X, ipady=5, pady=(2, 4))

        tk.Label(form, text="验证码：", font=FONT_BODY,
                 fg=COLORS["text_body"], bg=COLORS["bg_page"]).pack(anchor=tk.W)
        code_row = tk.Frame(form, bg=COLORS["bg_page"])
        code_row.pack(fill=tk.X, pady=(2, 4))
        code_entry = tk.Entry(code_row, font=FONT_BODY, relief="flat",
                              highlightthickness=1,
                              highlightbackground=COLORS["border"],
                              bg=COLORS["bg_input"], fg=COLORS["text_body"], width=12)
        code_entry.pack(side=tk.LEFT, ipady=5)
        ModernButton(code_row, text="发送验证码", variant="secondary", height=32,
                     command=lambda: _send_code()).pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(form, text="设置密码：", font=FONT_BODY,
                 fg=COLORS["text_body"], bg=COLORS["bg_page"]).pack(anchor=tk.W)
        pwd_entry = tk.Entry(form, font=FONT_BODY, relief="flat", show="•",
                             highlightthickness=1,
                             highlightbackground=COLORS["border"],
                             bg=COLORS["bg_input"], fg=COLORS["text_body"])
        pwd_entry.pack(fill=tk.X, ipady=5, pady=(2, 4))
        tk.Label(form, text="密码至少 6 位，需包含数字和英文字母",
                 font=FONT_CAPTION, fg=COLORS["text_hint"],
                 bg=COLORS["bg_page"]).pack(anchor=tk.W, pady=(0, 4))

        tk.Label(form, text="邀请码（选填）：", font=FONT_CAPTION,
                 fg=COLORS["text_secondary"], bg=COLORS["bg_page"]).pack(anchor=tk.W)
        invite_entry = tk.Entry(form, font=FONT_CAPTION, relief="flat",
                                highlightthickness=1,
                                highlightbackground=COLORS["border"],
                                bg=COLORS["bg_input"], fg=COLORS["text_body"])
        invite_entry.pack(fill=tk.X, ipady=4, pady=(2, 4))

        self._reg_status = tk.Label(form, text="", font=FONT_CAPTION,
                                    fg=COLORS["text_secondary"], bg=COLORS["bg_page"])
        self._reg_status.pack(anchor=tk.W, pady=(6, 0))

        btn_row = tk.Frame(win, bg=COLORS["bg_page"])
        btn_row.pack(pady=(12, 16))
        ModernButton(btn_row, text="注册", variant="primary", height=38,
                     command=lambda: _do_register()).pack(side=tk.LEFT, padx=6)
        ModernButton(btn_row, text="关闭", variant="secondary", height=38,
                     command=win.destroy).pack(side=tk.LEFT, padx=6)

        def _send_code():
            email = email_entry.get().strip()
            if not email:
                self._reg_status.configure(text="请输入注册邮箱", fg=COLORS["warning"])
                return
            try:
                ok, msg = user_manager.request_verification_code(email)
            except Exception as e:
                ok, msg = False, f"发送失败：{e}"
            self._reg_status.configure(text=msg,
                                       fg=COLORS["success"] if ok else COLORS["danger"])

        def _do_register():
            email = email_entry.get().strip()
            pwd = pwd_entry.get().strip()
            code = code_entry.get().strip()
            invite = invite_entry.get().strip() or None
            try:
                ok, msg = user_manager.register(email, pwd, code, invite)
            except Exception as e:
                ok, msg = False, f"注册失败：{e}"
            self._reg_status.configure(text=msg,
                                       fg=COLORS["success"] if ok else COLORS["danger"])
            if ok:
                self._refresh_login_status()
                win.after(1200, win.destroy)

    def _show_invite_code(self, parent=None):
        """展示我的邀请码（首次生成，后续直接展示）。"""
        from core import user_manager
        email = user_manager.get_logged_in_email()
        if not email:
            messagebox.showinfo("提示", "请先登录后查看邀请码")
            self._open_login_dialog(parent)
            return
        try:
            ok, code = user_manager.generate_invite_code(email)
        except Exception:
            ok, code = False, ""
        if not ok:
            messagebox.showinfo("邀请码", f"生成失败：{code}")
            return
        messagebox.showinfo(
            "我的邀请码",
            f"您的专属邀请码：\n\n  {code}  \n\n"
            f"好友注册时填写该邀请码，您将获得 1 个月全功能奖励。")

    def _maybe_prompt_login(self):
        """启动后若未登录，温和提示可登录使用免费版（可跳过）。"""
        try:
            from core import user_manager
            if user_manager.is_logged_in():
                return
            if messagebox.askyesno(
                    "欢迎使用鸿讯 HONGXUN",
                    "注册登录后即可使用免费版功能（检索 / 书架 / 格式助手 GB/T）。\n\n"
                    "现在登录/注册？"):
                self._open_login_dialog()
        except Exception:
            pass

    def _require_login(self, action_name: str) -> bool:
        """游客模式只能查看功能，不能执行。执行操作前检查登录。返回是否已登录。"""
        try:
            from core import user_manager
            if user_manager.is_logged_in():
                return True
        except Exception:
            return False
        # 未登录 → 提示登录
        if messagebox.askyesno(
                "需要登录",
                f"「{action_name}」需要登录后才能使用。\n\n"
                f"游客模式仅可浏览功能界面。\n\n现在登录/注册？"):
            self._open_login_dialog()
        return False

    def _refresh_login_status(self):
        """刷新顶部工具栏登录状态显示。"""
        try:
            from core import user_manager
            email = user_manager.get_logged_in_email()
            if hasattr(self, "_tool_login_link"):
                if email:
                    self._tool_login_link.configure(text=f"👤 {email}", fg=COLORS["success"])
                    self._tool_login_link._link_command = self._show_invite_code
                    # 已登录后「注册」改为「退出」
                    if hasattr(self, "_tool_register_link"):
                        self._tool_register_link.configure(text="退出",
                                                           fg=COLORS["text_secondary"])
                        self._tool_register_link._link_command = self._logout
                else:
                    self._tool_login_link.configure(text="登录",
                                                    fg=COLORS["text_secondary"])
                    self._tool_login_link._link_command = self._open_login_dialog
                    if hasattr(self, "_tool_register_link"):
                        self._tool_register_link.configure(text="注册",
                                                           fg=COLORS["text_secondary"])
                        self._tool_register_link._link_command = self._open_register_dialog
        except Exception:
            pass

    def _logout(self):
        """退出登录。"""
        try:
            from core import user_manager
            if messagebox.askyesno("退出登录", "确定要退出登录吗？"):
                user_manager.logout()
                self._refresh_login_status()
                messagebox.showinfo("已退出", "已退出登录，游客模式仅可浏览功能")
        except Exception:
            pass

    def _update_settings_register_label(self):
        """更新设置页的邮箱注册状态显示。"""
        try:
            from core import user_manager
            email = user_manager.get_registered_email()
            if hasattr(self, "_settings_reg_label"):
                if email:
                    self._settings_reg_label.configure(
                        text=f"已注册邮箱：{email}", fg=COLORS["success"])
                else:
                    self._settings_reg_label.configure(
                        text="未注册邮箱", fg=COLORS["text_hint"])
        except Exception:
            pass

    # ===================== 意见反馈 =====================

    def _open_feedback(self):
        fb = tk.Toplevel(self.root)
        fb.title("意见反馈")
        fb.geometry("560x520")
        fb.minsize(420, 400)
        fb.resizable(True, True)
        fb.transient(self.root)
        fb.configure(bg=COLORS["bg_page"])

        attachments = []

        # 静默读取日志（不提示用户）
        scheduler_log_content = ""
        scheduler_log_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "scheduler.log"
        )
        try:
            if os.path.exists(scheduler_log_path):
                with open(scheduler_log_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                    # 最多取最近 500 行，避免文件过大
                    lines = raw.splitlines()
                    scheduler_log_content = "\n".join(lines[-500:])
        except Exception:
            scheduler_log_content = "（日志读取失败）"

        ttk.Label(fb, text="请描述您的问题或需求：",
                  font=FONT_BODY_BOLD).pack(anchor=tk.W, padx=16, pady=(16, 6))
        content_text = scrolledtext.ScrolledText(
            fb, width=62, height=12,
            font=FONT_BODY, undo=True,
            bg=COLORS["bg_card"],
            fg=COLORS["text_body"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            insertbackground=COLORS["text_body"],
            selectbackground=COLORS["primary_light"],
            selectforeground=COLORS["primary_active"]
        )
        content_text.pack(padx=16, pady=6)
        content_text.focus_set()

        def _text_context_menu(event):
            menu = tk.Menu(fb, tearoff=0)
            menu.add_command(label="撤销", command=lambda: content_text.edit_undo())
            menu.add_separator()
            menu.add_command(label="剪切", command=lambda: fb.focus_get().event_generate("<<Cut>>"))
            menu.add_command(label="复制", command=lambda: fb.focus_get().event_generate("<<Copy>>"))
            menu.add_command(label="粘贴", command=lambda: fb.focus_get().event_generate("<<Paste>>"))
            menu.add_separator()
            menu.add_command(label="全选", command=lambda: content_text.tag_add(tk.SEL, "1.0", tk.END))
            menu.tk_popup(event.x_root, event.y_root)
        content_text.bind("<Button-3>", _text_context_menu)

        attach_frame = ttk.Frame(fb)
        attach_frame.pack(fill=tk.X, padx=16, pady=(6, 0))
        attach_label = ttk.Label(attach_frame, text="附件：无", foreground=COLORS["text_secondary"])
        attach_label.pack(side=tk.LEFT)

        def _add_attachment():
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                parent=fb,
                title="选择附件",
                filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp"), ("PDF文件", "*.pdf")])
            if not path:
                return
            fname = os.path.basename(path)
            fsize = os.path.getsize(path)
            ext = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
            if ext in ("png", "jpg", "jpeg", "gif", "bmp"):
                if fsize > 500 * 1024:
                    messagebox.showwarning("附件过大", "图片附件不能超过 500KB", parent=fb)
                    return
            elif ext == "pdf":
                if fsize > 1024 * 1024:
                    messagebox.showwarning("附件过大", "PDF附件不能超过 1MB", parent=fb)
                    return
            else:
                messagebox.showwarning("不支持格式", "仅支持图片（500KB以内）和 PDF（1MB以内）", parent=fb)
                return
            attachments.append(path)
            names = [os.path.basename(p) for p in attachments]
            attach_label.configure(text=f"附件：{', '.join(names)}", foreground=COLORS["text_body"])

        ModernButton(attach_frame, text="添加附件", variant="secondary",
                     command=_add_attachment).pack(side=tk.RIGHT)

        ttk.Label(fb, text="支持上传 500KB 以内的图片或 1MB 以内的 PDF 文件",
                  foreground=COLORS["text_secondary"],
                  font=FONT_CAPTION).pack(anchor=tk.W, padx=16, pady=(2, 6))

        email_row = ttk.Frame(fb)
        email_row.pack(fill=tk.X, padx=16, pady=6)
        ttk.Label(email_row, text="您的邮箱：", font=FONT_BODY).pack(side=tk.LEFT)
        email_var = tk.StringVar()
        email_entry = ModernEntry(email_row, textvariable=email_var, placeholder="you@example.com")
        email_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        def _validate_email(email):
            return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None

        def _send_feedback():
            content = content_text.get("1.0", tk.END).strip()
            email = email_var.get().strip()
            if not content:
                messagebox.showwarning("提示", "请输入反馈内容", parent=fb)
                return
            if not email:
                messagebox.showwarning("提示", "请输入您的邮箱", parent=fb)
                return
            if not _validate_email(email):
                messagebox.showwarning("提示", "邮箱格式不正确，请检查后重新输入", parent=fb)
                return

            body = f"用户邮箱：{email}\n\n反馈内容：\n{content}"
            if attachments:
                body += "\n\n---\n附件列表：\n"
                for p in attachments:
                    body += f"  {os.path.basename(p)}（{os.path.getsize(p)} 字节）\n"

            # 静默附带调度日志（用户不可见）
            if scheduler_log_content:
                body += "\n\n--- 调度日志（系统自动附带）---\n"
                body += scheduler_log_content[-3000:]  # 日志最后 3000 字符

            msg = MIMEMultipart()
            msg['From'] = Header("691678079@qq.com")
            msg['To'] = Header("xuhan@henetc.cn")
            msg['Subject'] = Header("论文监控助手 - 意见反馈", 'utf-8')
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            for p in attachments:
                fname = os.path.basename(p)
                with open(p, 'rb') as f:
                    file_data = f.read()
                import mimetypes
                mime_type, _ = mimetypes.guess_type(fname)
                if not mime_type:
                    mime_type = "application/octet-stream"
                main_type, sub_type = mime_type.split("/", 1)
                attach_part = MIMEText(base64.b64encode(file_data).decode(), 'base64', 'utf-8')
                attach_part.add_header('Content-Disposition', 'attachment',
                                       filename=('utf-8', '', fname))
                attach_part.add_header('Content-Type', f'{main_type}/{sub_type}',
                                       name=('utf-8', '', fname))
                msg.attach(attach_part)

            try:
                server = smtplib.SMTP_SSL("smtp.qq.com", 465)
                server.login("691678079@qq.com", "zdyrsbsmhfwqbbjf")
                server.sendmail("691678079@qq.com", "xuhan@henetc.cn", msg.as_string())
                server.quit()
                messagebox.showinfo("发送成功", "感谢您的反馈，我们已收到！", parent=fb)
                fb.destroy()
            except Exception as e:
                messagebox.showerror("发送失败",
                                     f"反馈发送失败，请稍后重试。\n错误：{str(e)}", parent=fb)

        btn_fb = ttk.Frame(fb)
        btn_fb.pack(pady=16)
        ModernButton(btn_fb, text="发送反馈", variant="primary",
                     command=_send_feedback).pack(side=tk.LEFT, padx=10)
        ModernButton(btn_fb, text="取消", variant="secondary",
                     command=fb.destroy).pack(side=tk.LEFT, padx=10)

    # ===================== 邮箱配置（升级版） =====================

    def _load_email_config(self):
        cfg = load_email_config()
        self.sender_entry.set(cfg.get("sender", ""))

        # 如果有授权码，设置并默认不显示密码
        auth_code = cfg.get("auth_code", "")
        self.auth_code_entry.set(auth_code)

        # 从 cfg 反推 SMTP 供应商
        smtp_server = cfg.get("smtp_server", "smtp.qq.com")
        port = str(cfg.get("port", 465))
        provider_name = find_provider_by_server(smtp_server)
        if provider_name:
            self.smtp_combo.set(provider_name)
        else:
            self.smtp_combo.set("")
        self.smtp_server_var.set(smtp_server)
        self.port_var.set(port)

        email_data = load_email_data()
        receivers = email_data.get("receivers", [])
        if not receivers and cfg.get("receiver", "").strip():
            receivers = [cfg["receiver"].strip()]
        self._receiver_list.clear()
        for r in self._receiver_frame.winfo_children():
            r.destroy()
        for r_addr in receivers:
            self._add_receiver_widget(r_addr)

        self._update_email_badge()
        self._update_license_status()
        # CNKI 知网模块已移除

    def _save_email_config(self):
        # 检查许可是否激活（无需代码解锁）
        if not self._require_activation("邮件推送设置"):
            return

        receivers = []
        for sv, _, _ in self._receiver_list:
            r = sv.get().strip()
            if r:
                receivers.append(r)

        # 检查新增收件邮箱输入框中是否有未添加的有效邮箱，自动加入
        new_email = self._new_receiver_var.get().strip()
        if new_email and new_email not in receivers:
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', new_email):
                receivers.append(new_email)
                self._add_receiver_widget(new_email)
                self._new_receiver_var.set("")

        sender = self.sender_entry.get().strip()
        auth_code = self.auth_code_entry.get().strip()
        smtp_server = self.smtp_server_var.get().strip()
        port = self.port_var.get().strip()

        cfg = {
            "sender": sender,
            "auth_code": auth_code,
            "smtp_server": smtp_server,
            "port": port,
            "receiver": receivers[0] if receivers else "",
            "receivers": receivers,
        }
        errors = validate_email_config(cfg)
        if errors:
            error_msg = "邮箱配置存在以下错误：\n\n" + "\n".join(f"• {e}" for e in errors)
            messagebox.showerror("配置错误", error_msg)
            return

        # 校验发件邮箱域名与所选的 SMTP 服务器是否匹配
        if sender and "@" in sender:
            sender_domain = sender.split("@")[1].lower()
            expected_server = EMAIL_DOMAIN_SMTP_MAP.get(sender_domain)
            if expected_server and smtp_server and expected_server != smtp_server:
                # 自动修正为匹配的 SMTP 服务器
                provider_name = find_provider_by_server(expected_server)
                if provider_name and messagebox.askyesno(
                    "邮箱与服务器不匹配",
                    f"发件邮箱「{sender}」的域名是 {sender_domain}，\n"
                    f"但选择的 SMTP 服务器是 {smtp_server}。\n\n"
                    f"已将 SMTP 服务器修正为：{expected_server}\n"
                    f"是否继续保存？"
                ):
                    self.smtp_server_var.set(expected_server)
                    self.smtp_combo.set(provider_name)
                    smtp_server = expected_server
                elif not provider_name:
                    if not messagebox.askyesno(
                        "邮箱与服务器不匹配",
                        f"发件邮箱「{sender}」的域名是 {sender_domain}，\n"
                        f"但选择的 SMTP 服务器是 {smtp_server}。\n\n"
                        f"建议使用 SMTP 服务器：{expected_server}\n\n"
                        f"是否仍要保存当前配置？"
                    ):
                        return
            elif expected_server is None:
                # 未识别的邮箱域名，不阻拦
                pass

        save_email_config(cfg)
        save_email_data({"receivers": receivers})
        self._update_email_badge()
        self.status_var.set(f"{ICONS['check']} 邮箱配置已保存")
        self._check_unsent_attachments()

    def _on_smtp_preset_selected(self, event=None):
        """下拉菜单选择 SMTP 供应商时，自动填充 server 和 port（取第一个配置）"""
        key = self.smtp_preset_var.get()
        configs = get_provider_configs(key)
        if configs:
            self.smtp_server_var.set(configs[0]["server"])
            self.port_var.set(configs[0]["port"])

    def _toggle_auth_code_visibility(self):
        """切换 SMTP 授权码的显示/隐藏"""
        self._auth_code_visible = not self._auth_code_visible
        if self._auth_code_visible:
            self.auth_code_entry.configure(show="")
            self.auth_code_entry._show = ""
        else:
            self.auth_code_entry.configure(show="*")
            self.auth_code_entry._show = "*"

    def _update_email_badge(self):
        cfg = load_email_config()
        sender = cfg.get("sender", "")
        email_data = load_email_data()
        receivers = email_data.get("receivers", [])
        if not receivers and cfg.get("receiver", "").strip():
            receivers = [cfg["receiver"].strip()]

    def _update_license_status(self):
        """更新许可状态显示（订阅/礼品券/试用，含具体到期日期）"""
        info = coupon_manager.get_expiry_info()
        active = info.get("active", False) or coupon_manager.is_in_validity()
        source = info.get("source", "")
        expires_at = info.get("expires_at", "")
        permanent = info.get("permanent", False)
        in_grace = info.get("in_grace", False)

        def _expiry_suffix():
            # 到期时间统一显示具体日期（YYYY-MM-DD）
            if permanent:
                return " · 永久"
            if expires_at:
                return f" · 到期 {expires_at[:10]}"
            return ""

        if active and permanent:
            status_text = f"{ICONS['check']} ✓ 服务已永久激活（礼品券）"
            self._license_status_label.configure(text=status_text, fg=COLORS["success"])
        elif active and source == "subscription":
            status_text = f"{ICONS['check']} ✓ 订阅已开通{_expiry_suffix()}"
            if in_grace:
                status_text += " · 宽限期"
            self._license_status_label.configure(text=status_text, fg=COLORS["success"])
        elif active and source and source != "unknown":
            # 礼品券（非永久）
            status_text = f"{ICONS['check']} ✓ 服务已激活（礼品券）{_expiry_suffix()}"
            self._license_status_label.configure(text=status_text, fg=COLORS["success"])
        elif active:
            # 试用期
            _, remaining_days = coupon_manager.is_trial_period()
            status_text = f"{ICONS['check']} ✓ 邮件推送服务试用中（免费试用7天）"
            if remaining_days > 0:
                status_text += f" · 剩余{remaining_days}天"
            self._license_status_label.configure(text=status_text, fg=COLORS["success"])
        else:
            self._license_status_label.configure(
                text=f"{ICONS['warning']} ⚠ 服务未激活，请开通订阅或兑换礼品券",
                fg=COLORS["warning"])

        # 同步概览页与设置页的激活状态/礼品券入口
        self._refresh_license_widgets()

    def _refresh_license_widgets(self):
        """刷新概览页与设置页的激活状态/礼品券入口。"""
        try:
            activated = coupon_manager.is_activated()
        except Exception:
            return
        # 设置页
        if hasattr(self, '_settings_license_label'):
            if activated:
                self._settings_license_label.configure(
                    text="✓ 服务已激活（永久）", fg=COLORS["success"])
                self._settings_coupon_btn.set_text("✓ 已激活")
                self._settings_coupon_btn.configure(state="disabled")
            else:
                try:
                    in_trial, remain = coupon_manager.is_trial_period()
                except Exception:
                    in_trial, remain = False, 0
                if in_trial:
                    self._settings_license_label.configure(
                        text=f"试用期剩余 {remain} 天", fg=COLORS["warning"])
                else:
                    self._settings_license_label.configure(
                        text=f"⚠ 未激活，请兑换礼品券", fg=COLORS["warning"])
                self._settings_coupon_btn.set_text("🎟 兑换礼品券")
                self._settings_coupon_btn.configure(state="normal")
        # 概览页
        if hasattr(self, 'dashboard_view') and hasattr(self.dashboard_view, 'refresh_license'):
            self.dashboard_view.refresh_license()


    # ===================== 未发送邮件重发 =====================

    def _check_unsent_attachments(self):
        """检查是否有未发送的附件，更新再发送按钮状态"""
        pending_path = os.path.join(UNSENT_DIR, "pending_email.json")
        if os.path.exists(pending_path):
            self._resend_btn.state(["!disabled"])
        else:
            self._resend_btn.state(["disabled"])

    def _open_unsent_folder(self):
        """打开未发送附件所在文件夹"""
        path = UNSENT_DIR
        if os.path.exists(path):
            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                elif sys.platform == "win32":
                    os.startfile(path)
                else:
                    subprocess.Popen(["xdg-open", path])
            except Exception as e:
                messagebox.showerror("错误", f"无法打开文件夹: {e}")
        else:
            messagebox.showinfo("提示", "没有未发送的附件文件夹")

    def _resend_unsent_email(self):
        """重新发送之前发送失败的邮件（不重新检索）"""
        import json
        pending_path = os.path.join(UNSENT_DIR, "pending_email.json")
        if not os.path.exists(pending_path):
            messagebox.showinfo("提示", "没有待发送的附件")
            return

        try:
            with open(pending_path, 'r', encoding='utf-8') as f:
                pending = json.load(f)
        except Exception as e:
            messagebox.showerror("错误", f"读取待发送记录失败: {e}")
            return

        files = pending.get("files", [])
        valid_files = [fp for fp in files if os.path.exists(fp)]
        if not valid_files:
            messagebox.showwarning("提示", "未找到待发送的附件文件，请重新执行检索")
            try:
                os.remove(pending_path)
            except Exception:
                pass
            self._check_unsent_attachments()
            return

        cfg = load_email_config()
        if not cfg.get("sender") or not cfg.get("auth_code"):
            messagebox.showwarning("邮箱配置不完整",
                                   "请先完成邮箱设置（发件邮箱、SMTP授权码、收件邮箱）后再发送。")
            return

        receivers = cfg.get("receivers", [])
        if isinstance(receivers, str):
            receivers = [r.strip() for r in receivers.replace('；', ';').split(';') if r.strip()]
        if not receivers and cfg.get("receiver", "").strip():
            receivers = [cfg["receiver"].strip()]
        if not receivers:
            messagebox.showwarning("邮箱配置不完整", "请添加收件邮箱后再发送。")
            return

        # 重新构建邮件并发送
        from email.mime.multipart import MIMEMultipart
        from email.mime.base import MIMEBase
        from email import encoders
        from email.mime.text import MIMEText
        import smtplib

        try:
            subject = pending.get("subject", "论文更新提醒")

            msg = MIMEMultipart()
            msg['From'] = cfg["sender"]
            msg['To'] = '; '.join(receivers)
            msg['Subject'] = subject

            body = MIMEText("附件为之前未成功发送的论文报告，请查收。", 'plain', 'utf-8')
            msg.attach(body)

            for fp in valid_files:
                fname = os.path.basename(fp)
                with open(fp, 'rb') as f:
                    docx_bytes = f.read()
                part = MIMEBase('application', 'vnd.openxmlformats-officedocument.wordprocessingml.document')
                part.set_payload(docx_bytes)
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment', filename=('utf-8', '', fname))
                msg.attach(part)

            # 使用 engine.py 中的 SMTP 发送（含端口备选）
            from core.engine import _smtp_send
            _smtp_send(cfg, msg, receivers)

            # 发送成功 → 清理文件
            for fp in valid_files:
                try:
                    os.remove(fp)
                except Exception:
                    pass
            try:
                os.remove(pending_path)
            except Exception:
                pass

            self._check_unsent_attachments()
            messagebox.showinfo("发送成功", "未发送的附件已成功发送到邮箱。")
        except Exception as e:
            # 自定义失败弹窗，含"打开文件夹"按钮
            fail_dialog = tk.Toplevel(self.root)
            fail_dialog.withdraw()
            fail_dialog.title("发送失败")
            fail_dialog.resizable(False, False)
            fail_dialog.transient(self.root)
            fail_dialog.configure(bg=COLORS["bg_page"])

            tk.Label(fail_dialog, text="⚠ 邮件发送失败",
                     font=FONT_HEADING, fg=COLORS["danger"],
                     bg=COLORS["bg_page"]).pack(pady=(20, 10))
            tk.Label(fail_dialog,
                     text=f"错误：{e}\n\n请检查邮箱设置后重试，或打开文件夹查看已保存的附件。",
                     font=FONT_BODY, fg=COLORS["text_body"],
                     bg=COLORS["bg_page"], wraplength=360,
                     justify=tk.LEFT).pack(padx=20, pady=(0, 16))

            btn_fail_frame = tk.Frame(fail_dialog, bg=COLORS["bg_page"])
            btn_fail_frame.pack(pady=(0, 16))

            def _open_and_close():
                self._open_unsent_folder()
                fail_dialog.destroy()

            ModernButton(btn_fail_frame, text=" 打开文件夹 ", variant="primary",
                         command=_open_and_close).pack(side=tk.LEFT, padx=6)
            ModernButton(btn_fail_frame, text=" 知道了 ", variant="secondary",
                         command=fail_dialog.destroy).pack(side=tk.LEFT, padx=6)

            fail_dialog.update_idletasks()
            pw, ph = 420, 220
            px = self.root.winfo_x() + (self.root.winfo_width() - pw) // 2
            py = self.root.winfo_y() + (self.root.winfo_height() - ph) // 2
            fail_dialog.geometry(f"{pw}x{ph}+{px}+{py}")
            fail_dialog.deiconify()
            fail_dialog.grab_set()

        messagebox.showinfo("知网模块已移除", "知网数据获取模块已移除。")
        self._refresh_remove_buttons()

    def _add_receiver(self):
        email = self._new_receiver_var.get().strip()
        if not email:
            messagebox.showwarning("提示", "请输入收件邮箱地址")
            return
        if len(self._receiver_list) >= 5:
            messagebox.showwarning("超限", "收件邮箱最多设置5个，已达上限")
            return
        for sv, _, _ in self._receiver_list:
            if sv.get().strip() == email:
                messagebox.showwarning("重复", f"收件邮箱「{email}」已存在")
                return
        self._add_receiver_widget(email)
        self._new_receiver_var.set("")
        self._new_receiver_entry.focus_set()

    def _add_receiver_widget(self, email: str):
        """创建单个收件邮箱行（输入框 + 删除按钮）"""
        row_frame = tk.Frame(self._receiver_frame, bg=COLORS["bg_card"])
        row_frame.pack(fill=tk.X, pady=2)

        sv = tk.StringVar(value=email)
        entry = ModernEntry(row_frame, textvariable=sv)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        idx = len(self._receiver_list)
        remove_btn = tk.Label(row_frame, text=f"{ICONS['trash']}",
                              font=FONT_CAPTION,
                              fg=COLORS["danger"],
                              bg=COLORS["bg_card"],
                              cursor="hand2",
                              padx=3)
        remove_btn.pack(side=tk.RIGHT)
        remove_btn.bind("<Button-1>", lambda e, i=idx: self._remove_receiver(i))
        remove_btn.bind("<Enter>", lambda e, b=remove_btn: b.configure(fg=COLORS["danger"]))
        remove_btn.bind("<Leave>", lambda e, b=remove_btn: b.configure(fg=COLORS["danger"]))

        self._receiver_list.append((sv, entry, remove_btn))
        self._refresh_remove_buttons()

    def _remove_receiver(self, index: int):
        if index < len(self._receiver_list):
            sv, entry, btn = self._receiver_list[index]
            entry.master.destroy()
            del self._receiver_list[index]
            self._refresh_remove_buttons()

    def _refresh_remove_buttons(self):
        for i, (sv, entry, btn) in enumerate(self._receiver_list):
            btn.configure(state=tk.NORMAL if len(self._receiver_list) > 1 else tk.DISABLED)

    # ===================== 功能介绍弹窗 =====================

    def _show_email_intro(self):
        intro = tk.Toplevel(self.root)
        intro.title("邮件推送 · 功能介绍")
        intro.geometry("520x480")
        intro.minsize(400, 360)
        intro.resizable(True, True)
        intro.transient(self.root)
        intro.configure(bg=COLORS["bg_page"])

        text = scrolledtext.ScrolledText(
            intro, width=58, height=22,
            font=FONT_BODY,
            bg=COLORS["bg_card"],
            fg=COLORS["text_body"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            padx=12, pady=12,
            wrap=tk.WORD
        )
        text.pack(padx=16, pady=(16, 8), fill=tk.BOTH, expand=True)

        content = """📧 邮件推送功能介绍

HONGXUN · 论文监控工具支持在检测到符合条件的新论文时，自动将检索结果推送到您的邮箱，让您第一时间掌握学术动态。

━━━ 核心功能 ━━━

▸ 自动推送：每日 8:00 自动增量检查，检测到新论文后自动发送邮件通知
▸ 启动即时检索：启动推送后立即检索近一周数据并发送邮件
▸ 无结果通知：当日无新增论文时，软件弹窗提示
▸ 多收件人：支持同时设置最多5个收件邮箱
▸ 灵活配置：支持任意 SMTP 服务（QQ邮箱、163邮箱、Gmail等）
▸ 发送失败处理：发送失败时弹窗提示并提供「打开文件夹」快速定位附件
▸ 再发送机制：修正邮箱配置后，可通过「再发送」按钮重新发送

━━━ 快速配置指南 ━━━

1. 获取 SMTP 授权码（以QQ邮箱为例）
   · 登录 QQ 邮箱 → 设置 → 账户
   · 开启 POP3/SMTP 服务
   · 生成授权码（16位字母）

2. 填写配置信息
   · 发件邮箱：your@qq.com
   · SMTP授权码：上一步获取的16位码
   · SMTP服务器：smtp.qq.com（默认）
   · SMTP端口：465（默认）

3. 添加收件邮箱（可选多个）
"""
        text.insert("1.0", content)
        text.configure(state=tk.DISABLED)

        ModernButton(intro, text="知道了", variant="primary",
                     command=intro.destroy).pack(pady=(4, 16))

    # ===================== 完整使用说明 =====================

    def _show_usage_guide(self):
        """显示完整使用说明和流程介绍"""
        win = tk.Toplevel(self.root)
        win.title("鸿讯 HONGXUN · 完整使用说明")
        win.geometry("780x560")
        win.minsize(600, 450)
        win.resizable(True, True)
        win.transient(self.root)
        win.configure(bg=COLORS["bg_page"])

        # 左树 + 右侧内容布局
        main_frame = tk.Frame(win, bg=COLORS["bg_page"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        nav_frame = tk.Frame(main_frame, bg=COLORS["bg_card"],
                             highlightbackground=COLORS["border"], highlightthickness=1)
        nav_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        content_frame = tk.Frame(main_frame, bg=COLORS["bg_page"])
        content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sections = [
            {"title": "📋 一、概览", "content": """鸿讯 HONGXUN 是一款面向科研人员的论文监控与学术辅助工具。

━━━ 核心功能 ━━━

▸ 论文检索监控
  按期刊 + 关键词检索 CrossRef 学术数据库，自动获取论文标题、作者、
  摘要、DOI 等信息，支持六级摘要深度补全，并生成结构化检索报告。
  时间范围自动按周切割逐周检索，降低漏检概率，确保结果完整稳定。
  支持一键检索，报告自动保存到 output/ 目录。

▸ 文献书架
  三栏布局文献管理器：左侧论文列表、中间摘要预览、右侧元数据卡片。
  支持多选、批量操作、状态标记（待读/已读/排除）、Zotero 格式导出。

▸ 论文 PDF 下载
  内置多来源回退下载（Unpaywall / OpenAlex / arXiv / PMC / 出版社直连），
  并支持可选的 Sci-Hub 增强获取付费论文。

▸ 每日邮件推送
  每日 8:00 自动检查符合监控条件的新论文，并通过 SMTP 邮件
  推送到指定收件箱（支持最多 5 个收件人）。启动时立即检索近一周
  数据并发送邮件。当日无新增论文时软件弹窗提示。

▸ 邮件发送失败处理
  邮件发送失败时弹窗提示，并提供「打开文件夹」按钮快速定位
  本地保存的附件，方便查看和手动发送。

▸ 智能期刊选择
  内置中科院 1/2 区 4295 本期刊库，按大类 → 小类 → 分区三级分类树
  可视化选择期刊，并支持手动输入库外期刊。

▸ AI 翻译
  基于 DeepSeek API 将论文标题和摘要从英文自动翻译为中文，
  检索报告与推送邮件中均包含翻译结果。"""},
            {"title": "📖 二、论文监控", "content": """论文监控是软件的核心功能，支持按期刊和关键词检索 CrossRef 学术数据库。

■ 任务设置

【期刊名称】
  输入英文期刊名称，多个以分号 ; 分隔，最多 10 个。
  例：Nature;Science;Cell;The Lancet;PNAS

【关键词】
  输入英文关键词，多个以分号 ; 分隔，最多 10 个。
  例：machine learning;deep learning;neural network

【关键词（选填）】
  与主关键词同时匹配时生效，最多 2 个，可为空。

【历史检索范围】
  格式：yyyy-mm-dd;yyyy-mm-dd
  例：2016-01-01;2026-01-01
  范围限制：1949-10-01 至 2100-10-01

■ 操作流程

① 点击新建任务或直接编辑表单 → 填写任务名称及各字段
② 点击「保存任务」→ 任务出现在左侧任务列表
③ 选中任务 → 点击「执行检索」→ 一键检索，报告自动保存到 output/ 目录
④ 检索完成后可通过下方「📚 文献书架」Tab 浏览结果
⑤ 新用户可点击「🌰 试试示例」快速填入 Nature/Science/Cell 预置数据

■ 任务管理

· 左侧列表展示所有已保存任务
· 双击任务名称可重命名
· 右键弹出菜单可启用/禁用任务
· 禁用后该任务不参与每日推送"""},
            {"title": "📧 三、邮件推送", "content": """支持每日 8:00 自动检测新论文并通过邮件推送到指定收件箱。
启动推送时立即执行近一周检索并发送邮件，之后转入每日定时推送。

■ 快速启动

① 确认已保存至少一个监控任务
② 填写发件邮箱和 SMTP 授权码，添加收件邮箱
③ 点击「保存配置」
④ 在左侧侧栏底部或右侧「每日推送」信息卡中点击「启动每日推送」
⑤ 系统立即启动守护进程，并进行近一周检索和邮件发送
⑥ 之后每天 8:00 自动执行增量检索并推送

■ 获取 SMTP 授权码（以QQ邮箱为例）

① 登录 QQ 邮箱 → 设置 → 账户
② 开启 POP3/SMTP 服务
③ 生成 16 位授权码

■ 邮件发送失败处理

· 发送失败时弹窗提示具体错误原因
· 弹窗提供「打开文件夹」按钮，点击可直接定位到本地保存的附件
· 附件保存在 output/unsent/ 目录下，数据不丢失
· 修正邮箱配置后，点击「再发送」按钮重新尝试发送

■ 注意事项

· 每日 8:00 执行一次增量检查
· 首次推送周期从启动时间到次日 8:00（不足24h按实际时长计算）
· 无新增论文时软件弹窗提示
· 同一时间最多支持 5 个并行任务
· 建议在暂停每日推送后再执行历史检索"""},
            {"title": "🌐 四、AI翻译", "content": """AI 翻译基于 DeepSeek API（OpenAI 兼容接口），
可将论文标题和摘要从英文自动翻译为中文。

■ 配置方法

在「设置」页找到「AI翻译（英→中）」开关，点击使其显示 ✓ 即为开启。
同时在项目根目录 .env 文件中配置 DeepSeek API Key：
DEEPSEEK_API_KEY=sk-your-key-here

请将 sk-your-key-here 替换为实际的 DeepSeek API Key。
配置完成后重启软件即可生效。

■ 生效范围

· 历史检索报告：翻译结果写入报告文档（中英双语）
· 每日推送邮件：翻译结果附在邮件正文中（中英双语）
· 文献书架：保存中英文双语内容

■ 注意事项

· AI 翻译需要礼品券激活
· 翻译功能在检索过程中自动调用，无需手动触发"""},

            {"title": "📄 五、PDF 下载", "content": """支持从多个来源获取论文 PDF 文件，按顺序自动回退直到成功。

■ 下载方式

在「文献书架」中选择论文，点击中栏的「⬇ 下载 PDF」按钮，
软件会依次尝试以下来源：
① Unpaywall（OA 权威索引）
② OpenAlex
③ arXiv
④ PMC（PubMed Central）
⑤ 出版社直连
⑥ Sci-Hub（可选，默认关闭）

■ Sci-Hub 增强

· 开启入口：设置 → PDF 下载 → Sci-Hub 增强
· 开启前需阅读版权风险提示并确认（5 秒倒计时）
· 通过非官方渠道获取付费论文 PDF 可能违反当地法律法规，请谨慎使用
· 建议优先使用机构合法途径获取文献

■ 文件命名与保存

· 文件名格式：首作者姓_年份_短标题.pdf
· 默认保存目录：~/Downloads/HONGXUN-PDF/
· 可在「设置 → PDF 下载 → 保存目录」中自定义

■ 注意事项

· 免费来源（Unpaywall/OpenAlex/arXiv/PMC）优先，Sci-Hub 仅作兜底
· 仅下载合法可用的 PDF，登录页 / 验证码页面会被自动拒绝"""},
            {"title": "⚠ 六、常见问题", "content": """Q: 检索过程中出现网络错误？
A: CrossRef 数据库需联网访问，请检查网络连接。
   如果频繁超时，可减少期刊或关键词数量后重试。

Q: 邮件发送失败？
A: 软件弹出提示框说明失败原因，并提供「打开文件夹」按钮定位附件。
   请依次检查：
   · SMTP 授权码是否正确（注意非邮箱密码）
   · 发件邮箱是否已开启 SMTP 服务
   · 端口号是否正确（SSL: 465, TLS: 587）
   · 网络连接是否正常

   修正后点击「再发送」按钮重新尝试发送，或从失败弹窗中打开文件夹
   手动获取已保存在本地的附件。附件路径：output/unsent/

Q: 每日推送 8:00 没有收到邮件？
A: 请检查：
   · 邮箱配置是否正确（发件邮箱、授权码、收件邮箱）
   · 前一天是否有新增论文（无新增则不发送）
   · 守护进程是否仍在运行（查看底部状态栏指示灯）
   · 邮件是否发送失败（失败时会弹窗提示，附件保存在本地）

Q: 两次检索结果数量不一致？
A: 历史检索已改为按周切割逐周检索，大幅提升了结果一致性与完整性。
   但如果 CrossRef API 自身索引更新，不同时间检索仍可能有差异。

Q: 窗口最大化后内容显示不全？
A: 窗口大小变化时字体和滚动区域会自动适配。
   如仍有遮挡，可手动调整窗口大小。

Q: 如何反馈问题？
A: 点击顶部工具栏的「意见反馈」按钮，
   填写问题描述和您的邮箱后提交。"""},
            {"title": "📋 七、版本信息", "content": f"""鸿讯 HONGXUN — 版本信息

━━━ 当前版本 ━━━

  版本：{APP_VERSION}
  发布日期：2026-08-05
  软件著作权登记版

━━━ 版本历程 ━━━

  v2.0.0（2026-08-05）
    · 大版本升级：功能与稳定性全面提升
    · 智能期刊选择器：中科院 1/2 区 4295 本期刊库，三级分类树可视化选择
    · 论文 PDF 下载：多来源回退（Unpaywall/OpenAlex/arXiv/PMC/出版社 + 可选 Sci-Hub）
    · 激活状态展示、推送时间可配置、Sci-Hub 版权风险提示、公告推送系统
    · 滚动条优化：内容放不下时才显示滑块，修复滚动残影
    · 更新检查与版本号对齐

  v1.5.0（2026-08-01）
    · UI 视觉打磨：主色 500 色阶、柔和阴影、卡片边框、底部留白
    · 期刊库全量导入 4295 本、期刊选择器过滤 3/4 区
    · 现代圆角滚动条、统计卡优化、按钮防黑底透色

  v1.4.0（2026-07-27）
    · UI 布局重构：侧栏固定宽度、每日推送移至右侧内容区
    · 工具栏精简（图标+文字按钮）、品牌名精简（HONGXUN）
    · Notebook Tab VS Code 风格、卡片边框跨平台修复
    · 一键检索（自动保存到 output/ 、不强制切 Tab）
    · 示例填充、macOS 原生通知、首次运行向导

  v1.3.0（2026-07-26）
    · GUI 架构重构：拆分 gui/ 组件包
    · 圆角卡片系统、暖色调色彩体系、三栏文献书架

  v1.2.0（2026-07-23）
    · 文献书架功能：三栏布局、状态筛选、Zotero 导出

  v1.1.0（2026-07-21）
    · 项目重组、检索按月切割、每日推送改进

  v1.0.0（2026-07-20）
    · 首版发布：CrossRef 检索、AI 翻译、邮件推送

━━━ 技术栈 ━━━

  · Python 3 + Tkinter GUI
  · CrossRef API 论文检索（按周切割逐周查询，降低漏检率）
  · OpenAlex / Semantic Scholar 摘要补全
  · SMTP SSL 邮件推送（每日 8:00）
  · launchd 开机自启（macOS）

━━━ 联系 ━━━

  意见反馈：点击顶部工具栏按钮或发送邮件至 xuhan@henetc.cn"""},
        ]

        section_buttons = []
        content_text = scrolledtext.ScrolledText(
            content_frame, width=68, height=28,
            font=FONT_BODY,
            bg=COLORS["bg_card"],
            fg=COLORS["text_body"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            padx=16, pady=16,
            wrap=tk.WORD
        )
        content_text.pack(fill=tk.BOTH, expand=True)

        def show_section(idx):
            content_text.configure(state=tk.NORMAL)
            content_text.delete("1.0", tk.END)
            content_text.insert("1.0", sections[idx]["content"])
            content_text.configure(state=tk.DISABLED)
            for i, btn in enumerate(section_buttons):
                btn.configure(bg=COLORS["primary_light"] if i == idx else COLORS["bg_card"],
                              fg=COLORS["primary_active"] if i == idx else COLORS["text_body"])

        for i, sec in enumerate(sections):
            btn = tk.Label(nav_frame, text=sec["title"],
                           font=FONT_BODY,
                           fg=COLORS["text_body"],
                           bg=COLORS["bg_card"],
                           cursor="hand2",
                           padx=16, pady=8,
                           anchor=tk.W)
            btn.pack(fill=tk.X)
            btn.bind("<Button-1>", lambda e, idx=i: show_section(idx))
            btn.bind("<Enter>", lambda e, b=btn: b.configure(
                fg=COLORS["primary"]) if b.cget("bg") != COLORS["primary_light"] else None)
            btn.bind("<Leave>", lambda e, b=btn: b.configure(
                fg=COLORS["text_body"]) if b.cget("bg") != COLORS["primary_light"] else None)
            section_buttons.append(btn)

        show_section(0)

        # 窗口尺寸自适应
        win.update_idletasks()
        w = min(self.root.winfo_width() - 40, 900)
        h = min(self.root.winfo_height() - 40, 700)
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

    # ===================== 礼品券兑换 =====================

    def _redeem_coupon_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("礼品券兑换")
        dialog.geometry("520x340")
        dialog.minsize(420, 300)
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg=COLORS["bg_page"])

        tk.Label(dialog, text="🎁 兑换礼品券",
                 font=FONT_HEADING,
                 fg=COLORS["text_title"],
                 bg=COLORS["bg_page"]).pack(pady=(20, 6))

        # 黄色 5号字提示信息
        hint_frame = tk.Frame(dialog, bg="#FFFDE7", bd=1, relief="solid", highlightbackground="#F9E547")
        hint_frame.pack(pady=(0, 10), padx=30, fill=tk.X)
        tk.Label(hint_frame,
                 text="输入24位礼品券编码解锁自动翻译、邮件推送",
                 font=(_ui_font_family(), 9),
                 fg="#B8860B",
                 bg="#FFFDE7",
                 wraplength=420,
                 anchor=tk.W).pack(padx=10, pady=8)

        tk.Label(dialog, text="格式：XXXX-XXXX-XXXX-XXXX-XXXX-XXXX",
                 font=FONT_CAPTION,
                 fg=COLORS["text_hint"],
                 bg=COLORS["bg_page"]).pack()

        entry_var = tk.StringVar()
        entry_frame = tk.Frame(dialog, bg=COLORS["bg_page"])
        entry_frame.pack(pady=14)
        entry = ModernEntry(entry_frame, textvariable=entry_var, width=34,
                            font=(_ui_mono_family(), FONT_BASE_SIZE))
        entry.pack(side=tk.LEFT, padx=(0, 8))
        entry.focus_set()

        def do_redeem():
            code = entry_var.get().strip()
            if not code:
                messagebox.showwarning("提示", "请输入礼品券编码", parent=dialog)
                return
            success, msg = coupon_manager.redeem_coupon(code)
            if success:
                # 附加到期时间
                try:
                    exp_info = coupon_manager.get_expiry_info()
                    exp = exp_info.get("expires_at", "")
                    if exp:
                        src = {"subscription": "订阅", "trial": "试用"}.get(exp_info.get("source", ""), "礼品券")
                        msg += f"\n\n{src}到期时间：{exp[:10]}"
                except Exception:
                    pass
                messagebox.showinfo("兑换成功", msg, parent=dialog)
                self._invalidate_activation_cache()
                self._update_license_status()
                self._update_email_badge()
                dialog.destroy()
            else:
                messagebox.showerror("兑换失败", msg, parent=dialog)

        ModernButton(entry_frame, text="兑换", variant="primary", height=30,
                     command=do_redeem).pack(side=tk.LEFT)

        entry.bind("<Return>", lambda e: do_redeem())

        tk.Label(dialog, text="提示：兑换后服务与当前设备绑定，到期时间以兑换结果为准",
                 font=(_ui_font_family(), 9),
                 fg=COLORS["text_hint"],
                 bg=COLORS["bg_page"]).pack(pady=(6, 0))

        # 获取礼品券联系方式
        tk.Frame(dialog, bg=COLORS["bg_page"], height=10).pack()
        contact_frame = tk.Frame(dialog, bg=COLORS["bg_page"])
        contact_frame.pack(pady=(6, 0))
        tk.Label(contact_frame,
                 text="获取礼品券请联系",
                 font=FONT_CAPTION,
                 fg=COLORS["text_secondary"],
                 bg=COLORS["bg_page"]).pack(side=tk.LEFT)
        tk.Label(contact_frame,
                 text="抖音号：83987351113",
                 font=(_ui_font_family(), 14, "bold"),
                 fg="#FF0000",  # 红色
                 bg=COLORS["bg_page"]).pack(side=tk.LEFT, padx=(6, 0))

    # ===================== 底层代码保护 =====================

    def _update_code_lock_ui(self):
        if self._code_locked:
            self._code_lock_btn.configure(
                text=f"{ICONS['lock']} 底层代码已锁定",
                fg=COLORS["text_secondary"])
        else:
            self._code_lock_btn.configure(
                text=f"{ICONS['unlock']} 底层代码已解锁",
                fg=COLORS["success"])

    def _check_code_unlocked(self, action_name: str) -> bool:
        """检查代码是否已解锁，未解锁则弹出密码验证"""
        if not self._code_locked:
            return True

        resp = messagebox.askyesno(
            "代码已锁定",
            f"「{action_name}」需要修改底层代码。\n\n"
            f"当前代码处于锁定状态，是否解锁？\n\n"
            f"解锁需验证密码（本机MAC可自动通过）")
        if resp:
            return self._verify_code_access()
        return False

    def _verify_code_access(self) -> bool:
        # 先尝试自动授权（本机MAC）
        if code_protector.authorize_modification(""):
            self._code_locked = False
            self._update_code_lock_ui()
            self.status_var.set(f"{ICONS['check']} 本机设备已自动授权，代码已解锁")
            return True

        dialog = tk.Toplevel(self.root)
        dialog.title("验证 — 解锁底层代码")
        dialog.geometry("400x180")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg=COLORS["bg_page"])

        tk.Label(dialog, text="🔒 请输入解锁密码",
                 font=FONT_HEADING,
                 fg=COLORS["text_title"],
                 bg=COLORS["bg_page"]).pack(pady=(20, 12))

        pwd_var = tk.StringVar()
        pwd_entry = ModernEntry(dialog, textvariable=pwd_var, show="*", width=30)
        pwd_entry.pack()
        pwd_entry.focus_set()

        def do_verify():
            if code_protector.verify_password(pwd_var.get()):
                self._code_locked = False
                self._update_code_lock_ui()
                self.status_var.set(f"{ICONS['check']} 密码验证通过，代码已解锁")
                dialog.destroy()
            else:
                messagebox.showerror("验证失败", "密码错误，请重试", parent=dialog)
                pwd_var.set("")
                pwd_entry.focus_set()

        btn_frame = tk.Frame(dialog, bg=COLORS["bg_page"])
        btn_frame.pack(pady=16)
        ModernButton(btn_frame, text="确认", variant="primary",
                     command=do_verify).pack(side=tk.LEFT, padx=6)
        ModernButton(btn_frame, text="取消", variant="secondary",
                     command=dialog.destroy).pack(side=tk.LEFT, padx=6)
        pwd_entry.bind("<Return>", lambda e: do_verify())

        return False

    # ===================== 断点保存 / 恢复 =====================

    def _save_checkpoint(self):
        """保存当前检索的断点进度"""
        import json
        if not self.current_task_id or not self._history_running:
            return
        checkpoint_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(checkpoint_dir, exist_ok=True)
        cp_path = os.path.join(checkpoint_dir, "checkpoint.json")
        task = get_task(self.current_task_id)
        if not task:
            return
        data = {
            "task_id": self.current_task_id,
            "task_name": task.get("name", ""),
            "journals": task.get("journals", []),
            "keywords": task.get("keywords", []),
            "date_start": task.get("date_start", ""),
            "date_end": task.get("date_end", ""),
            "translate_enabled": bool(load_app_config().get("translate_enabled", False)),
            "saved_at": datetime.now().isoformat(),
        }
        with open(cp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _clear_checkpoint(self):
        """清除断点文件"""
        cp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "checkpoint.json")
        if os.path.exists(cp_path):
            os.remove(cp_path)

    def _load_checkpoint(self) -> dict | None:
        """加载断点信息，返回 None 表示无断点或已过期"""
        cp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "checkpoint.json")
        if not os.path.exists(cp_path):
            return None
        try:
            import json
            with open(cp_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _check_resume_on_startup(self):
        """启动时检查是否有未完成的断点"""
        cp = self._load_checkpoint()
        if not cp:
            return

        # 检查当前选中的任务是否与断点匹配
        task = None
        if self.current_task_id:
            task = get_task(self.current_task_id)

        if not task:
            self._clear_checkpoint()
            return

        # 条件是否匹配
        matches = (
            task.get("journals", []) == cp.get("journals", [])
            and task.get("keywords", []) == cp.get("keywords", [])
            and task.get("date_start") == cp.get("date_start")
            and task.get("date_end") == cp.get("date_end")
            and task.get("name") == cp.get("task_name")
        )

        if matches:
            resume = messagebox.askyesno(
                "检测到未完成的检索",
                f"任务「{cp.get('task_name', '')}」的上次历史检索未完成。\n\n"
                f"当前任务条件未改变，是否继续执行？\n\n"
                f"选择「是」→ 继续执行\n选择「否」→ 清除断点，从开始执行")
            if resume:
                # 若断点时翻译开启，续传前先确认 API 仍可用
                if cp.get("translate_enabled") and load_app_config().get("translate_enabled"):
                    ok, _msg = self._probe_llm_api_sync()
                    if not ok:
                        ret = messagebox.askyesno(
                            "LLM API 连接异常",
                            f"续传检索需要 AI 翻译，但检测到 API 连接异常：\n\n{_msg}\n\n"
                            f"「是」→ 关闭 AI 翻译后继续（跳过翻译）\n"
                            f"「否」→ 取消续传")
                        if ret:
                            cfg = load_app_config()
                            cfg["translate_enabled"] = False
                            save_app_config(cfg)
                        else:
                            return
                self.status_var.set("正在继续上次的检索任务...")
                self._run_history()
            else:
                self._clear_checkpoint()
                self.status_var.set("已清除断点")
        else:
            # 条件改变，清除断点
            self._clear_checkpoint()
            messagebox.showinfo(
                "断点已清除",
                f"检测到任务条件已改变，已清除上次未完成的检索断点，将重新开始。")

    def _probe_llm_api_sync(self) -> tuple[bool, str]:
        """同步探测 LLM API 可用性（阻塞，供续传前判断）。返回 (ok, msg)。"""
        from core.translator import get_api_key, test_api_connection
        if not get_api_key():
            return False, "未配置 API Key"
        try:
            return test_api_connection()
        except Exception as e:
            return False, str(e)

    def _check_llm_api_on_startup(self):
        """启动时检测 LLM API 是否可用（仅当翻译开启且有 Key 时）。

        异步测试，结果经 root.after 弹窗。可用则静默继续；不可用则让用户
        选择关闭翻译或保持开启（翻译会自动跳过）。
        """
        from core.translator import get_api_key, test_api_connection
        cfg = load_app_config()
        if not cfg.get("translate_enabled"):
            return
        if not get_api_key():
            return

        def _work():
            ok, msg = test_api_connection()
            if ok:
                return  # 可用，静默
            self.root.after(0, lambda: self._on_startup_llm_unavailable(msg))

        threading.Thread(target=_work, daemon=True).start()

    def _on_startup_llm_unavailable(self, msg):
        """启动时 LLM API 不可用 → 询问是否关闭翻译。"""
        ret = messagebox.askyesno(
            "LLM API 连接异常",
            f"检测到 AI 翻译 API 连接异常：\n\n{msg}\n\n"
            f"可能导致检索/推送的中文翻译失败。\n\n"
            f"「是」→ 关闭 AI 翻译\n"
            f"「否」→ 保持开启（翻译会自动跳过，请检查 API 配置）")
        if ret:
            cfg = load_app_config()
            cfg["translate_enabled"] = False
            save_app_config(cfg)
            try:
                if self._ai_translate_toggle is not None:
                    self._ai_translate_toggle.set(False)
            except Exception:
                pass
            self.status_var.set("AI 翻译已关闭（API 不可用）")
        else:
            self.status_var.set("AI 翻译保持开启，请检查 API 配置")

    # ===================== 窗口关闭处理（断点保存） =====================

    def _on_closing(self):
        """用户关闭窗口时：若正在检索则提示保存退出"""
        if self._history_running or self._increment_running:
            self._save_checkpoint()
            resp = messagebox.askyesnocancel(
                "任务进行中",
                "检索任务仍在进行中，是否保存进度并退出？\n\n"
                "「是」→ 保存进度并退出\n"
                "「否」→ 不保存直接退出\n"
                "「取消」→ 返回程序")
            if resp is None:
                return  # 取消
            if not resp:
                self._clear_checkpoint()  # 不保存
        self.root.destroy()

    # ===================== 启动时试用期检查 =====================

    def _check_trial_status_at_startup(self):
        """启动时检查试用期状态（MAC绑定），首次运行时提示"""
        remaining_days = 0
        is_trial = False
        is_first_run = not os.path.exists(coupon_manager.TRIAL_RECORD_FILE)

        try:
            act_ok = coupon_manager.is_activated()
            if act_ok:
                return  # 已用礼品券激活，跳过试用提示
            is_trial, remaining_days = coupon_manager.is_trial_period()
        except Exception:
            return

        if is_first_run and is_trial:
            # 首次运行：不弹窗，仅在状态栏提示（已取消弹窗，避免打扰）
            self.status_var.set(f"欢迎使用！您有 {remaining_days} 天免费试用期")

    def _check_expiry_on_startup(self):
        """启动时检测订阅/礼品券/试用是否到期，到期自动关停受限功能。

        永久激活（permanent）不在此检查范围内，永不弹到期提醒。
        """
        try:
            info = coupon_manager.get_expiry_info()
            # 永久券：直接返回，不弹任何提醒
            if info.get("permanent"):
                return

            if coupon_manager.is_in_validity():
                # 在有效期内：若处于宽限期则提示续费
                if info.get("in_grace"):
                    messagebox.showwarning(
                        "服务已到期（宽限期）",
                        f"您的服务已于 {info.get('expires_at', '')[:10]} 到期。\n\n"
                        f"宽限期至 {info.get('grace_until', '')[:10]}，期间仍可使用，"
                        f"请尽快续费以免服务中断。")
                return

            # 已完全到期 → 自动关停受限功能
            src = {"subscription": "订阅", "trial": "试用"}.get(
                info.get("source", ""), "礼品券")
            messagebox.showwarning(
                "服务已到期",
                f"您的{src}已于 {info.get('expires_at', '')[:10]} 到期。\n\n"
                f"每日推送、邮箱设置、AI 翻译、Sci-Hub 增强已自动关闭。\n"
                f"请开通订阅或兑换礼品券后继续使用。")

            # 关闭每日推送
            if self._scheduler_daemon_running:
                try:
                    self._stop_daemon_scheduler()
                    self._scheduler_daemon_running = False
                    self._update_daily_push_btn(False)
                except Exception:
                    pass
            # 关闭翻译
            try:
                cfg = load_app_config()
                if cfg.get("translate_enabled"):
                    cfg["translate_enabled"] = False
                    save_app_config(cfg)
                if self._ai_translate_toggle is not None:
                    self._ai_translate_toggle.set(False)
            except Exception:
                pass
            # 关闭 Sci-Hub
            try:
                if self._scihub_toggle is not None and self._scihub_toggle.get():
                    self._scihub_toggle.set(False)
                    self._on_pdf_cfg_changed()
            except Exception:
                pass
            self._update_license_status()
        except Exception:
            import traceback
            traceback.print_exc()

    def _check_first_run_wizard(self):
        """首次运行向导：已取消（不再弹出）。"""
        pass

    # ===================== 自动更新 & 公告 =====================

    def _check_update_auto(self):
        """启动后静默检查公告 + 更新"""
        try:
            notice = auto_updater.fetch_notice()
            if notice:
                self._show_notice_dialog(notice)
            info = auto_updater.check_update(skip_notified=True)
            if info:
                self._show_update_dialog(info)
        except Exception:
            pass

    def _check_update_manual(self):
        """手动点击「检查更新」— 始终查询最新版"""
        try:
            info = auto_updater.check_update(skip_notified=False)
            if not info:
                messagebox.showinfo("检查更新", f"已是最新版本 v{AUTO_UPDATER_VERSION}")
                return
            self._show_update_dialog(info)
        except Exception as e:
            messagebox.showerror("检查更新失败", f"无法检查更新：{e}")

    def _show_update_dialog(self, info: dict):
        """显示更新确认对话框（带版本介绍）"""
        version = info.get("version", "")
        body = info.get("body", "暂无更新说明")
        self._show_info_dialog(
            title="发现新版本",
            subtitle=f"发现新版本 v{version}",
            footnote=f"当前版本 v{AUTO_UPDATER_VERSION}",
            body=body,
            btn_text="立即更新",
            btn_alt_text="稍后提醒",
            on_btn=lambda: self._download_and_apply_update(info),
            on_alt=auto_updater.skip_current_version,
            on_close_msg="关闭窗口，下次启动仍会提醒",
        )

    def _show_notice_dialog(self, notice: dict):
        """显示公告弹窗"""
        title = notice.get("title", "公告")
        body = notice.get("body", "")
        msg_id = notice.get("msg_id", "")
        self._show_info_dialog(
            title=title,
            subtitle="",
            footnote="",
            body=body,
            btn_text="我知道了",
            btn_alt_text=None,
            on_btn=lambda: auto_updater.mark_notice_read(msg_id),
            on_alt=None,
            on_close_msg=None,
        )

    def _show_info_dialog(self, title, subtitle, footnote, body,
                           btn_text, btn_alt_text, on_btn, on_alt,
                           on_close_msg):
        """通用信息展示弹窗（公告/更新共用）"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("500x400")
        dialog.minsize(420, 320)
        dialog.transient(self.root)
        dialog.configure(bg=COLORS["bg_page"])
        try:
            dialog.attributes("-topmost", True)
        except Exception:
            pass

        if subtitle:
            tk.Label(dialog, text=subtitle,
                     font=FONT_TITLE, fg=COLORS["text_title"],
                     bg=COLORS["bg_page"]).pack(pady=(16, 4))
        if footnote:
            tk.Label(dialog, text=footnote,
                     font=FONT_CAPTION, fg=COLORS["text_secondary"],
                     bg=COLORS["bg_page"]).pack(pady=(0, 12))

        text = scrolledtext.ScrolledText(
            dialog, width=54, height=12,
            font=FONT_BODY,
            bg=COLORS["bg_card"],
            fg=COLORS["text_body"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            padx=12, pady=12,
            wrap=tk.WORD
        )
        text.pack(padx=16, fill=tk.BOTH, expand=True)
        text.insert("1.0", body)
        text.configure(state=tk.DISABLED)

        btn_frame = tk.Frame(dialog, bg=COLORS["bg_page"])
        btn_frame.pack(pady=(12, 16))

        def on_btn_click():
            if on_btn:
                on_btn()
            dialog.destroy()

        ModernButton(btn_frame, text=btn_text, variant="primary",
                     command=on_btn_click).pack(side=tk.LEFT, padx=6)

        if btn_alt_text:
            def on_alt_click():
                if on_alt:
                    on_alt()
                dialog.destroy()
            ModernButton(btn_frame, text=btn_alt_text, variant="secondary",
                         command=on_alt_click).pack(side=tk.LEFT, padx=6)

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set()
        self.root.wait_window(dialog)

    def _download_and_apply_update(self, info: dict):
        """下载并应用更新"""
        self.status_var.set("正在下载更新...")
        self.root.update_idletasks()

        # 进度窗口
        progress_win = tk.Toplevel(self.root)
        progress_win.title("下载更新")
        progress_win.geometry("400x120")
        progress_win.transient(self.root)
        progress_win.resizable(False, False)
        progress_win.configure(bg=COLORS["bg_page"])

        tk.Label(progress_win, text="正在下载更新包，请稍候...",
                 font=FONT_BODY, bg=COLORS["bg_page"],
                 fg=COLORS["text_body"]).pack(pady=(16, 8))

        pb = ttk.Progressbar(progress_win, mode='determinate',
                              style="Horizontal.TProgressbar")
        pb.pack(fill=tk.X, padx=24, pady=8)
        progress_win.update()

        def progress_cb(received, total):
            pct = int(received / total * 100)
            pb["value"] = pct
            progress_win.update()

        def _do_download():
            try:
                package_path = auto_updater.download_update(info, progress_cb)
                if not package_path:
                    self.root.after(0, lambda: self._on_update_result(progress_win, False, "下载失败"))
                    return
                success = auto_updater.apply_update(package_path)
                if success:
                    self.root.after(0, lambda: self._on_update_ready(progress_win))
                else:
                    self.root.after(0, lambda: self._on_update_result(progress_win, False, "更新安装失败"))
            except Exception as e:
                self.root.after(0, lambda: self._on_update_result(progress_win, False, str(e)))

        threading.Thread(target=_do_download, daemon=True).start()

    def _on_update_result(self, win, success: bool, msg: str):
        win.destroy()
        if success:
            messagebox.showinfo("更新成功", "更新已下载并安装，将重新启动程序")
            auto_updater.restart_and_update()
        else:
            messagebox.showerror("更新失败", f"更新失败：{msg}")
            self.status_var.set("更新失败")

    def _on_update_ready(self, win):
        win.destroy()
        restart = messagebox.askyesno(
            "更新就绪",
            "更新已下载并安装，需要重新启动程序以完成更新。\n\n是否立即重启？"
        )
        if restart:
            auto_updater.restart_and_update()
        else:
            messagebox.showinfo("提示", "请下次启动程序时使用新版本")
            self.status_var.set("更新已就绪，下次重启生效")

    # ===================== 每日推送启动时一周检查 =====================

    # ===================== 状态栏 =====================

    def _refresh_status_bar(self):
        now = datetime.now()
        today_8 = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now < today_8:
            next_run = today_8
        else:
            next_run = today_8 + timedelta(days=1)
        self._next_run_label.configure(text=f"{ICONS['clock']} 下次执行：{next_run.strftime('%Y-%m-%d %H:%M')}")

    def _poll_daemon_result(self):
        """轮询检查守护进程推送结果文件，无论文时弹窗提示"""
        result_file = os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
                                    "scheduler_last_result.json")
        if not os.path.exists(result_file):
            self.root.after(60000, self._poll_daemon_result)
            return

        if not self._scheduler_daemon_running:
            return

        try:
            import json
            with open(result_file, "r", encoding='utf-8') as f:
                result = json.load(f)

            # LLM 翻译失败标记 → 弹窗 + 暂停推送
            if result.get("llm_failed"):
                reason = result.get("reason", "LLM API 调用失败")
                self._show_llm_error_dialog(f"每日推送中止：{reason}")
                # 暂停推送
                self._stop_daemon_scheduler()
                try:
                    os.remove(result_file)
                except Exception:
                    pass
                return

            result_date = result.get("date", "").split(" ")[0]
            today_str = datetime.now().strftime("%Y-%m-%d")

            if result_date == today_str:
                if not result.get("has_new", True):
                    task_detail = result.get("task_details", "所有任务均无新增论文")
                    messagebox.showinfo(
                        "每日推送 · 今日无更新",
                        f"{result_date} 检索完成，未发现匹配条件的新论文。\n\n"
                        f"守护进程将继续监控，明天 8:00 再次检索。\n"
                        f"详情：{task_detail}"
                    )
                try:
                    os.remove(result_file)
                except Exception:
                    pass
                return

        except Exception:
            pass

        self.root.after(300000, self._poll_daemon_result)

# ======================================================================
# 入口点
# ======================================================================
if __name__ == "__main__":
    # 当作为调度守护进程启动时（--scheduler 参数），执行调度逻辑
    if "--scheduler" in sys.argv:
        from scheduler_daemon import run_scheduler
        run_scheduler()
        sys.exit(0)

    root = tk.Tk()
    app = PaperMonitorApp(root)
    root.mainloop()
