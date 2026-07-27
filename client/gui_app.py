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
import requests

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
    run_history_search, run_increment_check, send_combined_email, add_push_record,
    cancel_current_search, reset_search_cancel, is_search_cancelled,
    search, abstract,
    coupon_manager,
    code_protector,
    auto_updater,
)
from gui.widgets import (
    PlaceholderEntry, CollapsibleFrame, ToggleSwitch,
    RoundedCard, ModernButton, StatusPill, IconLabel,
    IconCache, SkeletonLoader, EmptyState,
)
from gui.sidebar import TaskSidebar
from gui.library_view import LibraryView
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
class PaperMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("鸿讯 · 论文监控工具（郑州大学定制版）")
        self.root.geometry("1080x720")
        self.root.minsize(900, 640)
        self.root.configure(bg=COLORS["bg_page"])

        # 先隐藏主窗口，显示启动页
        self.root.withdraw()
        self._icon_refs = []  # 强引用图片对象，防止GC回收
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
            auto_updater.init(base_dir)
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
                self._load_window_icons()
                self._refresh_task_list()
                self._load_email_config()
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

                # 启动后检查未发送附件
                self.root.after(2000, self._check_unsent_attachments)

                # 启动后检查
                self.root.after(1200, self._check_resume_on_startup)
                self.root.after(1500, self._check_scheduler_daemon_status)
                self.root.after(1800, self._check_trial_status_at_startup)
                self.root.after(2200, self._check_first_run_wizard)
                self.root.after(5000, self._check_update_auto)
                self.root.after(10000, self._poll_daemon_result)
            except Exception:
                # 防止构建 UI 异常导致启动页永远不关闭
                import traceback
                traceback.print_exc()
                self._close_splash()

        # 安全兜底：5 秒后无论是否构建完成都关闭启动页
        self.root.after(5000, self._close_splash)

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

        tk.Label(self.splash, text="科研论文助手（郑州大学定制版）",
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
        """加载并缩放图标，size 为最长边像素，保持宽高比。失败返回None"""
        try:
            if os.path.exists(path):
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
                return ImageTk.PhotoImage(img)
        except Exception:
            pass
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
            if hasattr(self, 'notebook') and self.notebook.winfo_exists():
                try:
                    self.notebook.master.pack_configure(padx=pad, pady=pady)
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
        # ========== 顶部工具栏 ==========
        toolbar = tk.Frame(self.root, bg=COLORS["bg_page"], height=44)
        toolbar.pack(fill=tk.X)
        toolbar.pack_propagate(False)

        tk.Frame(toolbar, bg="#E8E8ED", height=1).pack(side=tk.BOTTOM, fill=tk.X)

        left_group = tk.Frame(toolbar, bg=COLORS["bg_page"])
        left_group.pack(side=tk.LEFT, padx=(16, 0), pady=6)

        # 标题栏小图标（28×28 缩放，完全左靠齐）
        title_icon = self._load_scaled_icon(ICON_TITLE, 28)
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

        tk.Label(left_group,
                 text="HONGXUN",
                 font=FONT_TITLE,
                 fg=COLORS["text_title"],
                 bg=COLORS["bg_page"]).pack(side=tk.LEFT, padx=(12, 0))

        # 顶部工具栏右侧（图标按钮）
        right_tool_group = tk.Frame(toolbar, bg=COLORS["bg_page"])
        right_tool_group.pack(side=tk.RIGHT, padx=(0, 8))

        for icon_char, text, cmd in [
            ("⬇", "更新", self._check_update_manual),
            ("?", "说明", self._show_usage_guide),
            ("✉", "反馈", self._open_feedback),
        ]:
            btn = tk.Label(right_tool_group, text=f"{icon_char} {text}",
                           font=FONT_BODY, fg=COLORS["text_secondary"],
                           bg=COLORS["bg_page"], cursor="hand2",
                           padx=8, pady=2)
            btn.pack(side=tk.RIGHT, padx=(2, 0))
            btn.bind("<Button-1>", lambda e, c=cmd: c())
            btn.bind("<Enter>", lambda e, b=btn: b.configure(fg=COLORS["primary"]))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(fg=COLORS["text_secondary"]))

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
            load_tasks_fn=load_all_tasks,
            get_task_fn=get_task,
            save_task_fn=save_task,
        )
        self.sidebar.pack(fill=tk.BOTH, expand=True)

        # -------- 右侧内容区（ttk.Notebook 双标签） --------
        right_frame = ttk.Frame(self.content_frame, style="TFrame")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=16)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(right_frame)
        self.notebook.grid(row=0, column=0, sticky=tk.NSEW)

        # Notebook 标签样式（VS Code 风格底部下划线）
        style = ttk.Style()
        style.configure("TNotebook", background=COLORS["bg_page"], borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=COLORS["bg_page"],
                        foreground=COLORS["text_secondary"],
                        padding=[20, 6, 20, 6],
                        borderwidth=0,
                        focusthickness=0,
                        font=FONT_BODY_BOLD)
        style.map("TNotebook.Tab",
                  background=[("selected", COLORS["bg_page"])],
                  foreground=[("selected", COLORS["primary"])])

        # ========== Tab 1: 任务设置（可滚动） ==========
        self._task_tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self._task_tab, text="  📋 任务设置  ")
        self._task_tab.columnconfigure(0, weight=1)
        self._task_tab.rowconfigure(0, weight=1)

        # Tab 1 内嵌 Canvas + Scrollbar
        self._task_canvas = tk.Canvas(self._task_tab, borderwidth=0, highlightthickness=0,
                                      bg=COLORS["bg_page"])
        task_v_scroll = ttk.Scrollbar(self._task_tab, orient=tk.VERTICAL,
                                      command=self._task_canvas.yview)
        task_h_scroll = ttk.Scrollbar(self._task_tab, orient=tk.HORIZONTAL,
                                      command=self._task_canvas.xview)
        self._task_canvas.configure(yscrollcommand=task_v_scroll.set,
                                    xscrollcommand=task_h_scroll.set)
        self._task_canvas.grid(row=0, column=0, sticky=tk.NSEW)
        task_v_scroll.grid(row=0, column=1, sticky=tk.NS)
        task_h_scroll.grid(row=1, column=0, sticky=tk.EW)

        scrollable = ttk.Frame(self._task_canvas, style="TFrame")
        scrollable.bind("<Configure>",
                        lambda e: self._task_canvas.configure(scrollregion=self._task_canvas.bbox("all")))
        self._task_canvas_window = self._task_canvas.create_window((0, 0), window=scrollable, anchor=tk.NW)

        def _configure_task_canvas_width(event):
            self._task_canvas.itemconfig(self._task_canvas_window, width=max(event.width, 400))
        self._task_canvas.bind("<Configure>", _configure_task_canvas_width)

        # 鼠标滚轮
        def _on_mousewheel(event):
            self._task_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _on_shift_mousewheel(event):
            self._task_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        def _bind_mousewheel(event):
            self._task_canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")
            self._task_canvas.bind_all("<Shift-MouseWheel>", _on_shift_mousewheel, add="+")
        def _unbind_mousewheel(event):
            self._task_canvas.unbind_all("<MouseWheel>")
            self._task_canvas.unbind_all("<Shift-MouseWheel>")
        scrollable.bind("<Enter>", _bind_mousewheel)
        scrollable.bind("<Leave>", _unbind_mousewheel)

        # 任务设置内容（原 scrollable 内的全部内容）
        # ========== 任务设置区 ==========
        # ── 卡片 1: 检索参数 ──
        search_card = tk.Frame(scrollable, bg=COLORS["bg_card"],
                               relief="solid", borderwidth=1)
        search_card.pack(fill=tk.X, padx=2, pady=(0, 12))

        tk.Label(search_card, text="🔍 检索参数", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Frame(search_card, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 10))

        # 表单区域用 grid
        sf = tk.Frame(search_card, bg=COLORS["bg_card"])
        sf.pack(fill=tk.X, padx=16, pady=(0, 14))
        sf.columnconfigure(1, weight=1)

        row = 0
        # 任务名称
        tk.Label(sf, text="任务名称", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=row, column=0, sticky=tk.W, padx=(0, 12), pady=6)
        self.task_name_var = tk.StringVar()
        tk.Entry(sf, textvariable=self.task_name_var,
                 bd=1, relief="solid", highlightthickness=0,
                 bg=COLORS["bg_input"], fg=COLORS["text_body"],
                 insertbackground=COLORS["text_body"], font=FONT_BODY).grid(
            row=row, column=1, sticky=tk.EW, pady=6)
        row += 1

        # 期刊名称
        tk.Label(sf, text="期刊名称", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_page"]).grid(row=row, column=0, sticky=tk.W, padx=(0, 12), pady=6)
        self.journal_var = tk.StringVar()
        self.journal_entry = tk.Entry(sf, textvariable=self.journal_var,
                                      bd=1, relief="solid", highlightthickness=0,
                                      bg=COLORS["bg_input"], fg=COLORS["text_body"],
                                      insertbackground=COLORS["text_body"], font=FONT_BODY)
        self.journal_entry.grid(row=row, column=1, sticky=tk.EW, pady=6)
        tk.Label(sf, text="英文分号分隔，最多10个，如 Nature;Science;Cell",
                 font=FONT_CAPTION, fg=COLORS["text_hint"], bg=COLORS["bg_page"]
                 ).grid(row=row+1, column=1, sticky=tk.W, pady=(0, 6))
        row += 2

        # 关键词
        tk.Label(sf, text="关键词", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_page"]).grid(row=row, column=0, sticky=tk.W, padx=(0, 12), pady=6)
        self.keyword_var = tk.StringVar()
        tk.Entry(sf, textvariable=self.keyword_var,
                 bd=1, relief="solid", highlightthickness=0,
                 bg=COLORS["bg_input"], fg=COLORS["text_body"],
                 insertbackground=COLORS["text_body"], font=FONT_BODY).grid(
            row=row, column=1, sticky=tk.EW, pady=6)
        tk.Label(sf, text="英文分号分隔，最多10个",
                 font=FONT_CAPTION, fg=COLORS["text_hint"], bg=COLORS["bg_page"]
                 ).grid(row=row+1, column=1, sticky=tk.W, pady=(0, 6))
        row += 2

        # 检索范围（双输入框）
        tk.Label(sf, text="检索范围", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_page"]).grid(row=row, column=0, sticky=tk.W, padx=(0, 12), pady=6)
        range_frame = tk.Frame(sf, bg=COLORS["bg_page"])
        range_frame.grid(row=row, column=1, sticky=tk.EW, pady=6)
        self.date_start_var = tk.StringVar()
        self.date_end_var = tk.StringVar()
        # 从原有的 date_var 解析初始值
        _init_dates = self.date_var.get().split(";") if hasattr(self, 'date_var') else ["", ""]
        self.date_start_var.set(_init_dates[0] if len(_init_dates) > 0 else "")
        self.date_end_var.set(_init_dates[1] if len(_init_dates) > 1 else "")
        tk.Entry(range_frame, textvariable=self.date_start_var,
                 width=16, bd=1, relief="solid", highlightthickness=0,
                 bg=COLORS["bg_input"], fg=COLORS["text_body"],
                 insertbackground=COLORS["text_body"], font=FONT_BODY).pack(side=tk.LEFT)
        tk.Label(range_frame, text=" → ", font=FONT_BODY,
                 fg=COLORS["text_secondary"], bg=COLORS["bg_page"]).pack(side=tk.LEFT, padx=6)
        tk.Entry(range_frame, textvariable=self.date_end_var,
                 width=16, bd=1, relief="solid", highlightthickness=0,
                 bg=COLORS["bg_input"], fg=COLORS["text_body"],
                 insertbackground=COLORS["text_body"], font=FONT_BODY).pack(side=tk.LEFT)
        tk.Label(sf, text="格式: 2020-01-01 → 2026-07-26",
                 font=FONT_CAPTION, fg=COLORS["text_hint"], bg=COLORS["bg_page"]
                 ).grid(row=row+1, column=1, sticky=tk.W, pady=(0, 6))

        # 保留 date_var 供旧代码使用（同步双输入框→旧变量）
        self.date_var = tk.StringVar()
        def _sync_date(*_):
            self.date_var.set(f"{self.date_start_var.get()};{self.date_end_var.get()}")
        self.date_start_var.trace_add("write", _sync_date)
        self.date_end_var.trace_add("write", _sync_date)
        _sync_date()
        row += 2

        # 操作按钮
        btn_frame = tk.Frame(sf, bg=COLORS["bg_page"])
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(12, 4))
        ttk.Button(btn_frame, text=f" {ICONS['search']}  执行检索", style="Primary.TButton",
                   command=self._run_history).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=f" {ICONS['save']}  保存任务", style="Secondary.TButton",
                   command=self._save_task).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="🗑 删除", style="Danger.TButton",
                   command=self._delete_task).pack(side=tk.LEFT, padx=4)

        # 示例填充
        example_btn = tk.Label(sf, text="🌰 试试示例", font=FONT_CAPTION,
                               fg=COLORS["primary"], bg=COLORS["bg_page"],
                               cursor="hand2")
        example_btn.grid(row=row+1, column=1, sticky=tk.W, pady=(6, 0))
        example_btn.bind("<Button-1>", lambda e: self._fill_example())

        # ── 卡片 2: 每日推送状态 ──
        push_card = tk.Frame(scrollable, bg=COLORS["bg_card"],
                             relief="solid", borderwidth=1)
        push_card.pack(fill=tk.X, padx=2, pady=(0, 12))

        tk.Label(push_card, text="📧 每日推送", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Frame(push_card, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 10))

        pf = tk.Frame(push_card, bg=COLORS["bg_card"])
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

        self._push_toggle_btn = ttk.Button(push_row1, text="启动每日推送",
                                           style="Primary.TButton",
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
        self._push_time_label = tk.Label(stats_left, text="每日 08:00",
                                         font=FONT_BODY_BOLD,
                                         fg=COLORS["text_body"], bg=COLORS["bg_card"])
        self._push_time_label.pack(side=tk.LEFT, padx=(0, 16))

        tk.Label(stats_left, text="累计推送  ", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_card"]).pack(side=tk.LEFT)
        self._push_total_label = tk.Label(stats_left, text="0 篇",
                                          font=FONT_BODY_BOLD,
                                          fg=COLORS["success"], bg=COLORS["bg_card"])
        self._push_total_label.pack(side=tk.LEFT)

        # ── 卡片 3: 邮箱配置 ──
        monitor_card = tk.Frame(scrollable, bg=COLORS["bg_card"],
                                relief="solid", borderwidth=1)
        monitor_card.pack(fill=tk.X, padx=2, pady=(0, 12))

        tk.Label(monitor_card, text="📧 邮箱配置", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Frame(monitor_card, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 10))

        mf = tk.Frame(monitor_card, bg=COLORS["bg_card"])
        mf.pack(fill=tk.X, padx=16, pady=(0, 14))
        mf.columnconfigure(1, weight=1)

        # 收件邮箱
        tk.Label(mf, text="收件邮箱", font=FONT_LABEL,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"]).grid(row=1, column=0, sticky=tk.NW, padx=(0, 12), pady=8)
        receiver_container = tk.Frame(mf, bg=COLORS["bg_card"])
        receiver_container.grid(row=1, column=1, sticky=tk.EW, pady=8)
        receiver_container.columnconfigure(0, weight=1)

        self._receiver_frame = tk.Frame(receiver_container, bg=COLORS["bg_card"])
        self._receiver_frame.pack(fill=tk.X)
        self._receiver_list = []

        receiver_add_frame = tk.Frame(receiver_container, bg=COLORS["bg_card"])
        receiver_add_frame.pack(fill=tk.X, pady=(4, 0))

        self._new_receiver_var = tk.StringVar()
        self._new_receiver_entry = tk.Entry(receiver_add_frame, textvariable=self._new_receiver_var,
                                            width=30, bd=1, relief="solid", highlightthickness=0,
                                            bg=COLORS["bg_input"], fg=COLORS["text_body"],
                                            insertbackground=COLORS["text_body"], font=FONT_BODY)
        self._new_receiver_entry.pack(side=tk.LEFT, padx=(0, 8))
        add_btn = tk.Label(receiver_add_frame, text="+ 添加",
                           font=FONT_CAPTION, fg=COLORS["primary"], bg=COLORS["bg_card"], cursor="hand2")
        add_btn.pack(side=tk.LEFT)
        add_btn.bind("<Button-1>", lambda e: self._add_receiver())
        add_btn.bind("<Enter>", lambda e: add_btn.configure(fg=COLORS["primary_hover"]))
        add_btn.bind("<Leave>", lambda e: add_btn.configure(fg=COLORS["primary"]))
        self._new_receiver_entry.bind("<Return>", lambda e: self._add_receiver())

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
        ttk.Button(btn_row_email, text="保存配置", style="Primary.TButton",
                   command=self._save_email_config).pack(side=tk.LEFT)
        self._resend_btn = ttk.Button(btn_row_email, text="再发送", style="Secondary.TButton",
                                      command=self._resend_unsent_email)
        self._resend_btn.pack(side=tk.LEFT, padx=(8, 0))
        self._resend_btn.state(["disabled"])

        # 使用指南 + 礼品券 链接
        links_frame = tk.Frame(monitor_card, bg=COLORS["bg_card"])
        links_frame.pack(fill=tk.X, padx=16, pady=(0, 12))
        for text, cmd in [("📖 使用指南", self._show_email_intro),
                          ("🎟 礼品券", self._redeem_coupon_dialog)]:
            lb = tk.Label(links_frame, text=text, font=FONT_CAPTION,
                          fg=COLORS["primary"], bg=COLORS["bg_card"], cursor="hand2")
            lb.pack(side=tk.LEFT, padx=(0, 16))
            lb.bind("<Button-1>", lambda e, c=cmd: c())
            lb.bind("<Enter>", lambda e, l=lb: l.configure(fg=COLORS["primary_hover"]))
            lb.bind("<Leave>", lambda e, l=lb: l.configure(fg=COLORS["primary"]))

        # ========== CNKI 知网数据获取模块 ==========
        # 已移除

        # ========== Tab 2: 文献书架 (LibraryView) ==========
        self.library_view = LibraryView(self.notebook)
        self.notebook.add(self.library_view, text="  📚 文献书架  ")

        # 兼容旧代码：保留 _refresh_library 别名
        def _refresh_library():
            self.library_view.refresh()
        self._refresh_library = _refresh_library

        # ========== Notebook 标签切换事件 ==========
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

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
        self._cancel_search_btn = ttk.Button(
            progress_frame, text=f" {ICONS['cancel']}  取消",
            style="Secondary.TButton",
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
                 bg=COLORS["sidebar_bg"]
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True, pady=8)

        self._version_label = tk.Label(inner_sf,
                                        text="郑州大学 v1.0.0",
                                        font=FONT_CAPTION,
                                        fg=COLORS["text_hint"],
                                        bg=COLORS["sidebar_bg"])
        self._version_label.pack(side=tk.RIGHT, padx=(8, 16), pady=8)

        self._next_run_label = tk.Label(inner_sf,
                                        text=f"{ICONS['clock']} 下次执行：--",
                                        font=FONT_CAPTION,
                                        fg=COLORS["text_secondary"],
                                        bg=COLORS["sidebar_bg"])
        self._next_run_label.pack(side=tk.RIGHT, padx=(0, 16), pady=8)

        # 现在 pack idle 细线（在所有控件之后）
        self._progress_idle.pack(side=tk.BOTTOM, fill=tk.X)
        self._progress_idle_packed = True

    # ===================== 任务列表操作 =====================
    def _refresh_task_list(self):
        if hasattr(self, 'sidebar'):
            self.sidebar.refresh_tasks()
            # 同步更新侧栏底部任务计数
            tasks = load_all_tasks()
            enabled_count = sum(1 for t in tasks.values() if t.get("enabled", True))
            self.sidebar.set_task_count(len(tasks), enabled_count)
            # 调试：打印 task_count
            print(f"[DEBUG] set_task_count({len(tasks)}, {enabled_count})")

    def _on_sidebar_select(self, task_id):
        """Sidebar 选中任务时的回调"""
        if self._executing:
            return
        self.current_task_id = task_id
        self._load_task_to_form(task_id)

    def _new_task(self):
        self.current_task_id = None
        self.task_name_var.set("")
        self.journal_var.set("")
        self.keyword_var.set("")
        self.date_start_var.set("2016-01-01")
        self.date_end_var.set("2026-01-01")
        self.date_var.set("2016-01-01;2026-01-01")
        self.status_var.set("当前：新建任务")

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

    def _load_task_to_form(self, task_id):
        task = get_task(task_id)
        if not task:
            return
        self.task_name_var.set(task["name"])
        self.journal_var.set("; ".join(task["journals"]))
        self.keyword_var.set("; ".join(task["keywords"]))
        ds = task.get("date_start", "")
        de = task.get("date_end", "")
        self.date_start_var.set(ds)
        self.date_end_var.set(de)
        self.date_var.set(f"{ds};{de}")
        self.status_var.set(f"当前编辑：{task['name']}")

    # ===================== 保存与校验 =====================
    def _save_task(self):
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
        self.journal_var.set("Nature;Science;Cell")
        self.keyword_var.set("artificial intelligence;machine learning;deep learning")
        self.date_start_var.set("2025-01-01")
        self.date_end_var.set("2026-07-26")
        self.status_var.set("示例已填充，点击「保存任务」→「执行检索」开始使用")
        # 如果当前没有任务，自动新建
        if not self.current_task_id:
            self._save_task()

    def _is_activated_cached(self) -> bool:
        """会话级激活缓存：先查 14 天试用，再查礼品券"""
        if self._activation_cache is None:
            self._activation_cache = coupon_manager.is_feature_allowed()
        return self._activation_cache

    def _get_trial_info(self) -> tuple[bool, int]:
        """获取试用期信息，(is_in_trial, remaining_days)"""
        return coupon_manager.is_trial_period()

    def _invalidate_activation_cache(self):
        """礼品券兑换成功后清除缓存，下次调用重新联网确认"""
        self._activation_cache = None

    def _on_tab_changed(self, event=None):
        """Notebook 标签切换时刷新书架"""
        if not hasattr(self, 'notebook'):
            return
        current = self.notebook.index(self.notebook.select())
        if current == 1:  # 文献书架
            if hasattr(self, 'library_view'):
                self.library_view.refresh()

    # ===================== 检索执行（一键检索） =====================
    def _run_history(self):
        if not self.current_task_id:
            messagebox.showwarning("提示", "请先保存任务后再执行检索")
            return
        if self._history_running:
            messagebox.showinfo("提示", "历史检索正在执行中，请等待完成")
            return
        if self._scheduler_daemon_running:
            messagebox.showwarning("提示", "每日推送正在运行中，请先关闭后再执行历史检索")
            return

        # 一键检索：自动保存到 output 目录
        task = get_task(self.current_task_id)
        task_name = task["name"] if task else "unknown"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{task_name}_{timestamp}.doc")

        self._executing = True
        self._history_running = True
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
                                            progress_callback=_progress)
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
                self.root.after(0, lambda: self._on_history_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, ratio, message):
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

    def _on_history_done(self, file_path):
        self._executing = False
        self._history_running = False
        self.sidebar.clear_task_running()
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
        """切换到文献书架 Tab"""
        if hasattr(self, 'notebook'):
            self.notebook.select(1)
        if hasattr(self, 'library_view'):
            self.library_view.refresh()

    def _on_history_cancelled(self):
        """检索被用户取消"""
        self._executing = False
        self._history_running = False
        self.sidebar.clear_task_running()
        self._progress_frame.pack_forget()
        self._progress_idle.pack(side=tk.BOTTOM, fill=tk.X)
        self._cancel_search_btn.pack_forget()
        self.status_var.set(f"{ICONS['cancel']} 检索已取消")

    def _on_history_error(self, error_msg):
        self._executing = False
        self._history_running = False
        self.sidebar.clear_task_running()
        self._progress_frame.pack_forget()
        self._progress_idle.pack(side=tk.BOTTOM, fill=tk.X)
        self._cancel_search_btn.pack_forget()
        self.status_var.set(f"{ICONS['error']} 检索出错")
        self._show_toast(f"{ICONS['error']} 检索失败: {error_msg[:60]}", duration=5)

    def _cancel_current_search(self):
        """取消当前正在执行的检索任务"""
        if not self._history_running:
            return
        ret = messagebox.askyesno("确认取消", "确定要取消当前检索吗？\n已完成的进度不会保存。")
        if ret:
            self.status_var.set("正在取消检索...")
            cancel_current_search()

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

            for _ in range(30):
                if self._is_daemon_alive():
                    break
                time.sleep(0.2)
            else:
                messagebox.showerror("启动失败", "调度守护进程启动超时，请重试")
                return

            self._scheduler_daemon_running = True
            self._update_daily_push_btn(True)
            self._status_indicator.configure(
                text=f"{ICONS['dot_on']} 推送运行中", fg=COLORS["success"])

            if not self._history_running and not self._increment_running:
                self.status_var.set("每日推送已启动 | 守护进程将持续运行 | 每日 8:00 自动推送")

            self._refresh_status_bar()

            # 简化弹窗：只提示启动成功
            messagebox.showinfo("每日推送", "每日推送启动成功")

            # 注册 launchd 开机自启（仅 macOS）
            if sys.platform == "darwin":
                install_launchd()
            # 注册 Windows 开机自启
            elif sys.platform == "win32":
                install_windows_startup()

            # 启动后立即执行一周检索并发送邮件（在后台进行）
            self._do_weekly_startup_mail()

        except Exception as e:
            messagebox.showerror("启动失败", f"调度守护进程启动失败：\n{e}")

    def _do_weekly_startup_mail(self):
        """启动每日推送后，对所有已启用任务进行近一周检索并合并发送邮件"""
        tasks = load_all_tasks()
        enabled_tasks = {tid: t for tid, t in tasks.items() if t.get("enabled", True)}
        if not enabled_tasks:
            return

        task_names = [t["name"] for t in enabled_tasks.values()]
        self.status_var.set(f"每日推送启动：正在检索 {len(enabled_tasks)} 个任务近一周数据...")
        self.progress_var.set(0.0)
        self.progress_label_var.set("0% 近一周检索中...")
        self._progress_idle.pack_forget()
        self._progress_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 0))
        self.root.update_idletasks()

        def _progress(ratio, message):
            self.root.after(0, lambda: self._update_progress(ratio, message))

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

                            tk.Button(btn_fail_frame, text=" 打开文件夹 ",
                                      font=FONT_BODY, bg=COLORS["primary"], fg="white",
                                      relief="flat", padx=16, pady=4, cursor="hand2",
                                      command=_open_and_close).pack(side=tk.LEFT, padx=6)
                            tk.Button(btn_fail_frame, text=" 知道了 ",
                                      font=FONT_BODY, bg=COLORS["bg_card"], fg=COLORS["text_body"],
                                      relief="flat", padx=16, pady=4, cursor="hand2",
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

    def _toggle_scheduler(self):
        """切换每日推送开/关（启动或停止外部守护进程）"""
        if not self._scheduler_daemon_running:
            # 当前是暂停状态 → 启动
            # 确保有选中任务：如果没有则自动选第一个可用任务
            if not self.current_task_id:
                tasks = load_all_tasks()
                if not tasks:
                    messagebox.showwarning("提示", "请先创建并保存任务后再启动每日推送")
                    return
                # 自动选第一个已启用的任务
                first_id = next(iter(tasks))
                self.current_task_id = first_id
                self._load_task_to_form(first_id)
                # 刷新列表选中状态
                if hasattr(self, 'sidebar'):
                    self.sidebar.select_task(first_id)

            if not self._require_activation("每日推送"):
                return
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

            self._stop_daemon_scheduler()

            self._update_daily_push_btn(False)
            self._status_indicator.configure(
                text=f"{ICONS['dot_off']} 已暂停", fg=COLORS["warning"])
            self.status_var.set("每日推送已关闭")
            self._refresh_status_bar()

    def _update_daily_push_btn(self, running: bool):
        """更新侧栏和右侧推送状态"""
        if running:
            self._push_status_indicator.configure(text="●", fg=COLORS["success"])
            self._push_status_text.configure(text="每日推送运行中", fg=COLORS["success"])
            self._push_toggle_btn.configure(text="暂停推送", style="Danger.TButton")
            # 刷新统计数据
            self._update_push_stats()
        else:
            self._push_status_indicator.configure(text="○", fg=COLORS["dot_off"])
            self._push_status_text.configure(text="每日推送未启动", fg=COLORS["text_body"])
            self._push_toggle_btn.configure(text="启动每日推送", style="Primary.TButton")

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
        """检查是否已激活，未激活则弹出引导。返回是否已激活。"""
        if self._is_activated_cached():
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
        dialog.title("激活提示")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg=COLORS["bg_page"])

        if trial_over:
            heading = f"🔒 「{feature_name}」试用已到期"
            desc = "14 天免费试用已结束，请使用礼品券激活服务后继续使用。"
        else:
            heading = f"🔒 「{feature_name}」需要激活"
            desc = "请使用礼品券激活服务后再使用此功能。"

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

        # 两个按钮蓝底黑字
        tk.Button(btn_frame, text="  现在激活  ",
                  font=FONT_BODY,
                  bg=COLORS["primary"], fg="black",
                  relief="flat", padx=20, pady=6,
                  cursor="hand2",
                  activebackground=COLORS["primary_hover"],
                  activeforeground="black",
                  command=on_now).pack(side=tk.LEFT, padx=8)

        tk.Button(btn_frame, text="  稍后激活  ",
                  font=FONT_BODY,
                  bg=COLORS["primary"], fg="black",
                  relief="flat", padx=20, pady=6,
                  cursor="hand2",
                  activebackground=COLORS["primary_hover"],
                  activeforeground="black",
                  command=on_later).pack(side=tk.LEFT, padx=8)

        # 全部构建完成后才显示
        dialog.update_idletasks()
        dialog.geometry("420x200")
        x = self.root.winfo_x() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 200) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        dialog.deiconify()

        self.root.wait_window(dialog)

        if result[0]:
            self._redeem_coupon_dialog()
            return self._is_activated_cached()
        return False

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

        ttk.Button(attach_frame, text="添加附件",
                   style="Secondary.TButton", command=_add_attachment).pack(side=tk.RIGHT)

        ttk.Label(fb, text="支持上传 500KB 以内的图片或 1MB 以内的 PDF 文件",
                  foreground=COLORS["text_secondary"],
                  font=FONT_CAPTION).pack(anchor=tk.W, padx=16, pady=(2, 6))

        email_row = ttk.Frame(fb)
        email_row.pack(fill=tk.X, padx=16, pady=6)
        ttk.Label(email_row, text="您的邮箱：", font=FONT_BODY).pack(side=tk.LEFT)
        email_var = tk.StringVar()
        email_entry = tk.Entry(email_row, textvariable=email_var, width=30,
                               font=FONT_BODY,
                               insertbackground=COLORS["text_body"],
                               selectbackground=COLORS["primary_light"],
                               selectforeground=COLORS["primary_active"],
                               bg=COLORS["bg_input"], fg=COLORS["text_body"],
                               relief="solid", bd=1)
        email_entry.pack(side=tk.LEFT, padx=(10, 0))

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
        ttk.Button(btn_fb, text="发送反馈", style="Primary.TButton",
                   command=_send_feedback).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_fb, text="取消", style="Secondary.TButton",
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
        """更新邮件许可状态显示"""
        # 区分：礼品券激活 vs 试用期
        if coupon_manager.is_activated():
            remaining = coupon_manager.get_remaining_days()
            if remaining >= 99999:
                status_text = f"{ICONS['check']} ✓ 邮件推送服务已永久激活（礼品券兑换）"
            else:
                status_text = f"{ICONS['check']} ✓ 邮件推送服务已激活（礼品券兑换）"
                if remaining > 0:
                    status_text += f" · 剩余{remaining}天"
            self._license_status_label.configure(
                text=status_text, fg=COLORS["success"])
        elif self._is_activated_cached():
            # 处于 14 天试用期
            _, remaining_days = coupon_manager.is_trial_period()
            status_text = f"{ICONS['check']} ✓ 邮件推送服务试用中（免费试用14天）"
            if remaining_days > 0:
                status_text += f" · 剩余{remaining_days}天"
            self._license_status_label.configure(
                text=status_text, fg=COLORS["success"])
        else:
            self._license_status_label.configure(
                text=f"{ICONS['warning']} ⚠ 邮件推送服务未激活，请使用礼品券兑换",
                fg=COLORS["warning"])


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

            tk.Button(btn_fail_frame, text=" 打开文件夹 ",
                      font=FONT_BODY, bg=COLORS["primary"], fg="white",
                      relief="flat", padx=16, pady=4, cursor="hand2",
                      command=_open_and_close).pack(side=tk.LEFT, padx=6)
            tk.Button(btn_fail_frame, text=" 知道了 ",
                      font=FONT_BODY, bg=COLORS["bg_card"], fg=COLORS["text_body"],
                      relief="flat", padx=16, pady=4, cursor="hand2",
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
        row_frame = tk.Frame(self._receiver_frame, bg=COLORS["bg_page"])
        row_frame.pack(fill=tk.X, pady=2)

        sv = tk.StringVar(value=email)
        entry = tk.Entry(row_frame, textvariable=sv,
                         bd=1, relief="solid", highlightthickness=0,
                         bg=COLORS["bg_input"], fg=COLORS["text_body"],
                         insertbackground=COLORS["text_body"],
                         insertofftime=0,
                         selectbackground=COLORS["primary_light"],
                         selectforeground=COLORS["primary_active"],
                         cursor="xterm",
                         font=FONT_BODY)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        idx = len(self._receiver_list)
        remove_btn = tk.Label(row_frame, text=f"{ICONS['trash']}",
                              font=FONT_CAPTION,
                              fg=COLORS["danger"],
                              bg=COLORS["bg_page"],
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

━━━ 关于激活 ━━━

软件提供 14 天免费试用，试用期内可正常使用邮件推送。
试用到期后需使用礼品券激活才能继续使用。

点击「🎁 礼品券」按钮输入24位编码即可解锁服务。
服务解锁后绑定当前设备，更换设备需重新激活。
"""
        text.insert("1.0", content)
        text.configure(state=tk.DISABLED)

        tk.Button(intro, text="知道了",
                  font=FONT_BODY,
                  bg=COLORS["primary"], fg="white",
                  relief="flat", padx=24, pady=4,
                  cursor="hand2",
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
  时间范围自动按月度切割逐月检索，确保结果完整稳定。支持一键检索，
  报告自动保存到 output/ 目录。

▸ 文献书架
  三栏布局文献管理器：左侧论文列表、中间摘要预览、右侧元数据卡片。
  支持多选、批量操作、状态标记（待读/已读/排除）、RIS 格式导出。

▸ 每日邮件推送
  每日 8:00 自动检查符合监控条件的新论文，并通过 SMTP 邮件
  推送到指定收件箱（支持最多 5 个收件人）。启动时立即检索近一周
  数据并发送邮件。当日无新增论文时软件弹窗提示。

▸ 邮件发送失败处理
  邮件发送失败时弹窗提示，并提供「打开文件夹」按钮快速定位
  本地保存的附件，方便查看和手动发送。

▸ 礼品券激活系统
  通过 24 位礼品券激活全部高级功能，包含 AI 翻译、邮件推送。
  14 天免费试用期内可体验全部功能。"""},
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

■ 关于激活服务

· 软件提供 14 天免费试用，试用期内可正常使用邮件推送
· 试用到期后需使用礼品券激活才能继续使用
· 激活状态显示在邮箱设置区域顶部（绿色为已激活，黄色为未激活）

■ 注意事项

· 每日 8:00 执行一次增量检查
· 首次推送周期从启动时间到次日 8:00（不足24h按实际时长计算）
· 无新增论文时软件弹窗提示
· 同一时间最多支持 5 个并行任务
· 建议在暂停每日推送后再执行历史检索"""},
            {"title": "🌐 四、AI翻译", "content": """AI 翻译基于 DeepSeek API（OpenAI 兼容接口），
可将论文标题和摘要从英文自动翻译为中文。

■ 使用方法

在「任务设置」区域找到「AI翻译（英→中）」开关，
点击方框使其显示 ✓ 即为开启。

■ 生效范围

· 历史检索报告：翻译结果写入报告文档
· 每日推送邮件：翻译结果附在邮件正文中
· 全局生效：开启后所有检索和推送都包含翻译

■ 注意事项

· AI 翻译需要礼品券激活
· 翻译功能在检索过程中自动调用，无需手动触发"""},

            {"title": "🎟 六、礼品券", "content": """礼品券用于解锁软件的高级功能，包含：

   ✓ AI 翻译（英→中）
   ✓ 邮件推送服务


■ 兑换方法

① 点击「礼品券」按钮（位于邮箱设置标题栏右侧）
② 输入 24 位礼品券编码
③ 格式：XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
④ 点击「兑换」

■ 有效期

· 兑换后服务与当前设备（MAC 地址）绑定
· 兑换后永久有效
· 到期后需重新兑换

■ 激活状态

兑换成功后，以下位置的状态提示将变为绿色：
· 邮箱设置区域的许可状态


■ 获取礼品券

如有需要请联系：
抖音号：83987351113"""},
            {"title": "⚠ 七、常见问题", "content": """Q: 点击各按钮后反应慢（卡顿 2-3 秒）？
A: 激活状态首次检测需要联网确认，请确保网络畅通。
   首次确认后同次会话内不再重复联网，后续操作瞬时响应。

Q: 检索过程中出现网络错误？
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

   另外，软件提供 14 天免费试用，试用期内可直接使用邮件推送功能，
   无需礼品券即可测试邮箱配置是否正确。

Q: 每日推送 8:00 没有收到邮件？
A: 请检查：
   · 软件是否已激活或仍在 14 天试用期内（查看邮箱设置顶部状态提示）
   · 邮箱配置是否正确（发件邮箱、授权码、收件邮箱）
   · 前一天是否有新增论文（无新增则不发送）
   · 守护进程是否仍在运行（查看底部状态栏指示灯）
   · 邮件是否发送失败（失败时会弹窗提示，附件保存在本地）

Q: 两次检索结果数量不一致？
A: 历史检索已改为按月切割逐月检索，大幅提升了结果一致性。
   但如果 CrossRef API 自身索引更新，不同时间检索仍可能有差异。

Q: 窗口最大化后内容显示不全？
A: 窗口大小变化时字体和滚动区域会自动适配。
   如仍有遮挡，可手动调整窗口大小。

Q: 如何反馈问题？
A: 点击顶部工具栏的「意见反馈」按钮，
   填写问题描述和您的邮箱后提交。"""},
            {"title": "📋 八、版本信息", "content": f"""鸿讯 HONGXUN — 版本信息

━━━ 当前版本 ━━━

  版本：{APP_VERSION}
  发布日期：2026-07-27
  软件著作权登记版

━━━ 版本历程 ━━━

  v1.4.0（2026-07-27）
    · UI 布局重构：侧栏固定宽度、每日推送移至右侧内容区
    · 工具栏精简（图标+文字按钮）、品牌名精简（HONGXUN）
    · Notebook Tab VS Code 风格、卡片边框跨平台修复
    · 一键检索（自动保存到 output/ 、不强制切 Tab）
    · 示例填充、macOS 原生通知、首次运行向导
    · Logger 系统、硬编码凭据集中管理、删除按钮替换
    · 任务卡「⋯」更多菜单、运行指示器

  v1.3.0（2026-07-26）
    · GUI 架构重构：拆分 gui/ 组件包
    · 圆角卡片系统、暖色调色彩体系、三栏文献书架
    · Quick Look、批量操作、48 个线性图标

  v1.2.0（2026-07-23）
    · 文献书架功能：三栏布局、状态筛选、RIS 导出
    · Apple 色系 GUI 视觉重构

  v1.1.0（2026-07-21）
    · 项目重组、检索按月切割、每日推送改进

  v1.0.0（2026-07-20）
    · 首版发布：CrossRef 检索、AI 翻译、邮件推送

━━━ 技术栈 ━━━

  · Python 3 + Tkinter GUI
  · CrossRef API 论文检索（按月切割逐月查询）
  · OpenAlex / Semantic Scholar 摘要补全
  · SMTP SSL 邮件推送（每日 8:00）
  · launchd 开机自启（macOS）

━━━ 联系 ━━━

  意见反馈：点击顶部工具栏按钮或发送邮件至 xuhan@henetc.cn
  礼品券获取：抖音号 83987351113"""},
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
        entry = tk.Entry(entry_frame, textvariable=entry_var, width=34,
                          font=(_ui_mono_family(), FONT_BASE_SIZE),
                          bg=COLORS["bg_input"], fg=COLORS["text_body"],
                          relief="solid", bd=1)
        entry.pack(side=tk.LEFT, padx=(0, 8))
        entry.focus_set()

        def do_redeem():
            code = entry_var.get().strip()
            if not code:
                messagebox.showwarning("提示", "请输入礼品券编码", parent=dialog)
                return
            success, msg = coupon_manager.redeem_coupon(code)
            if success:
                messagebox.showinfo("兑换成功", msg, parent=dialog)
                self._invalidate_activation_cache()
                self._update_license_status()
                self._update_email_badge()
                dialog.destroy()
            else:
                messagebox.showerror("兑换失败", msg, parent=dialog)

        tk.Button(entry_frame, text="兑换",
                  font=FONT_BODY,
                  bg=COLORS["primary"], fg="black",
                  relief="flat", padx=16, pady=4,
                  cursor="hand2",
                  command=do_redeem).pack(side=tk.LEFT)

        entry.bind("<Return>", lambda e: do_redeem())

        tk.Label(dialog, text="提示：兑换后服务与当前设备绑定，永久有效",
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
        pwd_entry = tk.Entry(dialog, textvariable=pwd_var, show="*", width=30,
                              font=FONT_BODY,
                              insertbackground=COLORS["text_body"],
                              selectbackground=COLORS["primary_light"],
                              selectforeground=COLORS["primary_active"],
                              bg=COLORS["bg_input"], fg=COLORS["text_body"],
                              relief="solid", bd=1)
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
        tk.Button(btn_frame, text="确认",
                  font=FONT_BODY,
                  bg=COLORS["primary"], fg="white",
                  relief="flat", padx=20, pady=4,
                  cursor="hand2",
                  command=do_verify).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="取消",
                  font=FONT_BODY,
                  bg=COLORS["bg_card"], fg=COLORS["text_body"],
                  relief="flat", padx=20, pady=4,
                  cursor="hand2",
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
            # 首次运行，弹出试用欢迎
            self.status_var.set(f"欢迎使用！您有 {remaining_days} 天免费试用期")
            try:
                messagebox.showinfo(
                    "欢迎使用鸿讯 HONGXUN",
                    f"欢迎使用鸿讯论文监控工具！\n\n"
                    f"您有 {remaining_days} 天的免费试用期，可体验全部功能（AI翻译、邮件推送）。\n\n"
                    f"试用已绑定本机设备，删除配置文件不会延长试用期。\n\n"
                    f"试用到期后需使用礼品券激活才能继续使用。\n\n"
                    f"祝您使用愉快！"
                )
            except Exception:
                pass

    def _check_first_run_wizard(self):
        """首次运行向导：引导用户创建第一个任务"""
        tasks_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "data", "tasks.json")
        if os.path.exists(tasks_path):
            try:
                import json
                with open(tasks_path, 'r') as f:
                    tasks = json.load(f)
                if tasks:
                    return
            except Exception:
                pass

        # 没有任务 — 弹出向导
        welcome = tk.Toplevel(self.root)
        welcome.title("首次使用向导")
        welcome.geometry("480x360")
        welcome.minsize(420, 320)
        welcome.transient(self.root)
        welcome.configure(bg=COLORS["bg_page"])
        try:
            welcome.attributes("-topmost", True)
        except Exception:
            pass

        tk.Label(welcome, text="欢迎使用鸿讯 HONGXUN",
                 font=FONT_TITLE, fg=COLORS["text_title"],
                 bg=COLORS["bg_page"]).pack(pady=(20, 6))
        tk.Label(welcome, text="只需 3 步即可开始监控论文",
                 font=FONT_BODY, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_page"]).pack(pady=(0, 16))

        steps_frame = tk.Frame(welcome, bg=COLORS["bg_page"])
        steps_frame.pack(padx=30, fill=tk.X)

        steps = [
            ("1", "创建任务", "填写期刊名称和关键词，设置检索时间范围"),
            ("2", "执行检索", "一键检索 CrossRef 数据库，论文自动入库"),
            ("3", "浏览书架", "在三栏文献书架中阅读摘要、管理文献"),
        ]
        for num, title, desc in steps:
            row = tk.Frame(steps_frame, bg=COLORS["bg_page"])
            row.pack(fill=tk.X, pady=6)
            num_label = tk.Label(row, text=num,
                                 font=FONT_HEADING,
                                 fg=COLORS["primary"], bg=COLORS["bg_page"],
                                 width=2)
            num_label.pack(side=tk.LEFT)
            text_frame = tk.Frame(row, bg=COLORS["bg_page"])
            text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
            tk.Label(text_frame, text=title, font=FONT_BODY_BOLD,
                     fg=COLORS["text_title"], bg=COLORS["bg_page"],
                     anchor=tk.W).pack(fill=tk.X)
            tk.Label(text_frame, text=desc, font=FONT_CAPTION,
                     fg=COLORS["text_secondary"], bg=COLORS["bg_page"],
                     anchor=tk.W).pack(fill=tk.X)

        btn_frame = tk.Frame(welcome, bg=COLORS["bg_page"])
        btn_frame.pack(pady=(16, 0))
        tk.Button(btn_frame, text="开始使用",
                  font=FONT_BODY, bg=COLORS["primary"],
                  fg="white", relief="flat", padx=24, pady=6,
                  cursor="hand2",
                  command=welcome.destroy).pack()

        welcome.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 480) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 360) // 2
        welcome.geometry(f"+{x}+{y}")
        welcome.grab_set()

    # ===================== 自动更新 =====================

    def _check_update_auto(self):
        """启动后静默检查更新，有新版则弹窗通知"""
        try:
            info = auto_updater.check_update(skip_notified=True)
            if info:
                self._show_update_dialog(info)
        except Exception:
            pass

    def _check_update_manual(self):
        """手动点击「检查更新」"""
        try:
            info = auto_updater.check_update(skip_notified=False)
            if not info:
                messagebox.showinfo("检查更新", f"已是最新版本 v{AUTO_UPDATER_VERSION}")
                return
            self._show_update_dialog(info)
        except Exception as e:
            messagebox.showerror("检查更新失败", f"无法检查更新：{e}")

    def _show_update_dialog(self, info: dict):
        """显示更新确认对话框"""
        version = info.get("version", "")
        body = info.get("body", "暂无更新说明")
        result = messagebox.askyesno(
            "发现新版本",
            f"发现新版本 v{version}\n\n"
            f"更新内容：\n{body}\n\n"
            f"是否立即下载更新？"
        )
        if result:
            self._download_and_apply_update(info)
        else:
            auto_updater.skip_current_version()
            messagebox.showinfo("已跳过", f"当前版本 v{AUTO_UPDATER_VERSION} 将继续使用")

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
