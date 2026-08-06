"""
鸿讯 HONGXUN · 论文格式修改助手 — Tkinter 界面（v2）
蓝白极简风格。左右分栏：左侧步骤导航 + 右侧内容区。
含 AI 智能格式解析流程（上传格式要求文件 → LLM 解析 → 确认套用）。
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

from gui.theme import COLORS, ICONS, FONT_BODY, FONT_BODY_BOLD, FONT_HEADING, \
    FONT_TITLE, FONT_CAPTION, FONT_LABEL
from gui.widgets import ModernButton, ModernEntry, ModernScrollbar, ToggleSwitch, smooth_wheel_handler


def _rounded_pts(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class RefFormatterView(ttk.Frame):
    """论文格式修改助手页（v2：左右分栏 + 步骤导航 + 卡片式交互）。"""

    FORMAT_LABELS = [
        ("gbt7714", "GB/T 7714", "中文期刊标准"),
        ("ieee", "IEEE", "工程/计算机"),
        ("apa7", "APA 7th", "心理/教育/社科"),
        ("chicago", "Chicago", "人文/历史"),
        ("mla", "MLA", "文学/艺术"),
        ("harvard", "Harvard", "英国/澳洲/社科"),
    ]

    STEPS = ["选择文件", "选择格式", "选项设置", "开始处理"]

    def __init__(self, master, on_open_llm_config=None, on_require_activation=None, **kwargs):
        super().__init__(master, **kwargs)
        self._engine = None
        self._last_output = None
        self._running = False
        self._ai_rules = ""          # AI 解析确认后的格式规则
        self._ai_upload_path = None  # 已上传的格式要求文件
        self._on_open_llm_config = on_open_llm_config or (lambda: None)
        # 激活检测回调：由 gui_app 传入 _require_activation（礼品券/付费）
        self._on_require_activation = on_require_activation or (lambda f: False)
        self._build_ui()

    # ═════════════════ 步骤导航 ═════════════════
    def _build_step_nav(self, master):
        nav = tk.Frame(master, bg=COLORS["sidebar_bg"], width=180)
        nav.grid(row=0, column=0, sticky=tk.NS)
        nav.pack_propagate(False)

        self._completed_steps = set()  # 已完成步骤索引
        self._current_step = 0         # 当前步骤
        self._step_dots = {}   # idx -> circle canvas
        self._step_labels = {} # idx -> label
        self._step_rows = {}   # idx -> row frame（可点击）
        tk.Label(nav, text="操作流程", font=FONT_LABEL,
                 fg=COLORS["text_secondary"], bg=COLORS["sidebar_bg"]
                 ).pack(anchor=tk.W, padx=20, pady=(24, 16))

        for i, name in enumerate(self.STEPS):
            row = tk.Frame(nav, bg=COLORS["sidebar_bg"], cursor="hand2")
            row.pack(fill=tk.X, padx=20, pady=8)
            dot = tk.Canvas(row, width=22, height=22, highlightthickness=0,
                            bd=0, bg=COLORS["sidebar_bg"])
            dot.pack(side=tk.LEFT)
            lbl = tk.Label(row, text=name, font=FONT_BODY,
                           fg=COLORS["text_secondary"], bg=COLORS["sidebar_bg"],
                           anchor=tk.W)
            lbl.pack(side=tk.LEFT, padx=(8, 0))
            self._step_dots[i] = dot
            self._step_labels[i] = lbl
            self._step_rows[i] = row
            # 点击步骤 → 滚动到对应区域（若该步未完成则跳转并提示）
            row.bind("<Button-1>", lambda e, idx=i: self._on_step_click(idx))
            dot.bind("<Button-1>", lambda e, idx=i: self._on_step_click(idx))
            lbl.bind("<Button-1>", lambda e, idx=i: self._on_step_click(idx))

        tk.Frame(nav, bg=COLORS["bg_page"], height=1).pack(fill=tk.X, padx=20, pady=(24, 0))

        self._update_steps(0)

    def _on_step_click(self, idx):
        """点击步骤：滚动定位到对应区域，若该步未完成则提示需先完成前置步骤。"""
        self._current_step = idx
        self._update_steps(idx)
        # 滚动定位到对应卡片
        self._scroll_to_step(idx)

    def _scroll_to_step(self, idx):
        """把对应步骤的卡片滚动到窗口中部。"""
        try:
            targets = {
                0: getattr(self, "_drop_zone", None),
                1: getattr(self, "_format_cards", None),
                2: getattr(self, "_opt_switches", None),
                3: getattr(self, "_start_btn", None),
            }
            widget = None
            if idx == 1 and self._format_cards:
                widget = next(iter(self._format_cards.values()))
            else:
                widget = targets.get(idx)
            if widget is None:
                return
            # 计算 widget 在 scrollable 内的 y 坐标，滚动到窗口中部
            y = widget.winfo_rooty() - self._scrollable.winfo_rooty()
            canvas_h = self._canvas.winfo_height()
            if canvas_h <= 0:
                return
            # yview_moveto 的分数 = 目标y / 内容总高
            total = self._canvas.bbox("all")[3] if self._canvas.bbox("all") else 0
            if total <= 0:
                return
            frac = max(0.0, min(1.0, (y - canvas_h / 3) / total))
            self._canvas.yview_moveto(frac)
        except Exception:
            pass

    def mark_step_complete(self, idx):
        """标记某步骤已完成（保持绿色，离开不变灰）。"""
        self._completed_steps.add(idx)
        if idx >= self._current_step:
            self._current_step = idx + 1
        self._update_steps(self._current_step)

    def _update_steps(self, current_idx):
        self._current_step = current_idx
        for i in range(len(self.STEPS)):
            dot = self._step_dots[i]
            lbl = self._step_labels[i]
            dot.delete("all")
            if i in self._completed_steps:
                # 已完成：绿色打勾（保持，离开不变灰）
                dot.create_oval(2, 2, 20, 20, fill=COLORS["success"], outline="")
                dot.create_line(6, 11, 9, 14, fill="#FFFFFF", width=2)
                dot.create_line(9, 14, 16, 7, fill="#FFFFFF", width=2)
                lbl.configure(fg=COLORS["success"], font=FONT_BODY)
            elif i == current_idx:
                # 当前：主色实心
                dot.create_oval(2, 2, 20, 20, fill=COLORS["primary"], outline="")
                dot.create_oval(6, 6, 16, 16, fill="#FFFFFF", outline="")
                lbl.configure(fg=COLORS["primary"], font=FONT_BODY_BOLD)
            else:
                # 未到：灰色空心
                dot.create_oval(2, 2, 20, 20, fill=COLORS["sidebar_bg"], outline=COLORS["text_hint"])
                lbl.configure(fg=COLORS["text_hint"], font=FONT_BODY)

    # ═════════════════ UI 构建 ═════════════════
    def _card(self, parent, title):
        card = tk.Frame(parent, bg=COLORS["bg_card"], highlightthickness=1,
                        highlightbackground=COLORS["border"])
        card.pack(fill=tk.X, padx=2, pady=(0, 14))
        if title:
            tk.Label(card, text=title, font=FONT_HEADING,
                     fg=COLORS["text_title"], bg=COLORS["bg_card"]
                     ).pack(anchor=tk.W, padx=16, pady=(12, 4))
            tk.Frame(card, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16)
        card.content = tk.Frame(card, bg=COLORS["bg_card"])
        card.content.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)
        return card

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # 左侧步骤导航
        self._build_step_nav(self)

        # 右侧内容（可滚动）
        right = tk.Frame(self, bg=COLORS["bg_page"])
        right.grid(row=0, column=1, sticky=tk.NSEW)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(right, borderwidth=0, highlightthickness=0,
                                 bg=COLORS["bg_page"])
        vs = ModernScrollbar(right, width=8, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vs.set)
        self._canvas.grid(row=0, column=0, sticky=tk.NSEW)
        vs.grid(row=0, column=1, sticky=tk.NS)

        self._scrollable = tk.Frame(self._canvas, bg=COLORS["bg_page"])
        self._scrollable.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._win = self._canvas.create_window((0, 0), window=self._scrollable, anchor=tk.NW)
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._win, width=e.width))

        _wheel, _bind, _unbind = smooth_wheel_handler(self._canvas)
        self._scrollable.bind("<Enter>", _bind)
        self._scrollable.bind("<Leave>", _unbind)

        # 标题
        header = tk.Frame(self._scrollable, bg=COLORS["bg_page"])
        header.pack(fill=tk.X, padx=4, pady=(4, 12))
        tk.Label(header, text="📝 论文格式修改助手", font=FONT_TITLE,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"]).pack(side=tk.LEFT)
        tk.Label(header, text="自动格式化 · 交叉引用 · 角标上标",
                 font=FONT_CAPTION, fg=COLORS["text_hint"],
                 bg=COLORS["bg_page"]).pack(side=tk.LEFT, padx=(10, 0), pady=(4, 0))

        # ── 第一步：选择文件（视觉拖拽卡） ──
        c1 = self._card(self._scrollable, "第一步 · 选择文件")
        self._drop_zone = tk.Frame(c1.content, bg=COLORS["bg_input"],
                                   highlightthickness=2,
                                   highlightbackground=COLORS["border"],
                                   highlightcolor=COLORS["primary"],
                                   cursor="hand2")
        self._drop_zone.pack(fill=tk.X, ipady=28, pady=(4, 8))
        self._drop_zone.bind("<Button-1>", lambda e: self._browse_file())
        self._drop_zone.bind("<Enter>", lambda e: self._on_drop_hover(True))
        self._drop_zone.bind("<Leave>", lambda e: self._on_drop_hover(False))
        inner = tk.Frame(self._drop_zone, bg=COLORS["bg_input"])
        inner.pack(expand=True)
        inner.bind("<Button-1>", lambda e: self._browse_file())
        tk.Label(inner, text="📄", font=(FONT_BODY.cget("family"), 40) if FONT_BODY else None,
                 bg=COLORS["bg_input"]).pack()
        tk.Label(inner, text="点击选择 Word 文件，或拖拽到此处", font=FONT_BODY,
                 fg=COLORS["text_secondary"], bg=COLORS["bg_input"]).pack(pady=(6, 0))
        ModernButton(inner, text="浏览文件", variant="secondary", height=32,
                     command=self._browse_file).pack(pady=(12, 0))
        self._file_var = tk.StringVar()
        self._file_hint = tk.Label(c1.content, text="支持 .docx 格式的 Word 文档",
                                   font=FONT_CAPTION, fg=COLORS["text_hint"],
                                   bg=COLORS["bg_card"])
        self._file_hint.pack(anchor=tk.W)

        # ── 第二步：选择目标格式（卡片式） ──
        c2 = self._card(self._scrollable, "第二步 · 选择目标格式")
        self._format_var = tk.StringVar(value="gbt7714")
        self._format_cards = {}
        grid = tk.Frame(c2.content, bg=COLORS["bg_card"])
        grid.pack(fill=tk.X)
        for i in range(3):
            grid.columnconfigure(i, weight=1, uniform="fmt")
        for idx, (key, label, desc) in enumerate(self.FORMAT_LABELS):
            card = tk.Frame(grid, bg=COLORS["bg_card"], highlightthickness=2,
                            highlightbackground=COLORS["border"], cursor="hand2",
                            padx=12, pady=10)
            card.grid(row=idx // 3, column=idx % 3, sticky=tk.NSEW,
                      padx=4, pady=4)
            card.bind("<Button-1>", lambda e, k=key: self._select_format(k))
            tk.Label(card, text=label, font=FONT_LABEL,
                     fg=COLORS["text_title"], bg=COLORS["bg_card"],
                     anchor=tk.W).pack(fill=tk.X)
            tk.Label(card, text=desc, font=FONT_CAPTION,
                     fg=COLORS["text_hint"], bg=COLORS["bg_card"],
                     anchor=tk.W).pack(fill=tk.X, pady=(2, 0))
            self._format_cards[key] = card
            for child in card.winfo_children():
                child.bind("<Button-1>", lambda e, k=key: self._select_format(k))

        # ⭐ 自定义（AI 解析）卡片 — 第 7 张，选「自定义」后展示 AI 解析区
        custom_card = tk.Frame(grid, bg=COLORS["bg_card"], highlightthickness=2,
                               highlightbackground=COLORS["border"], cursor="hand2",
                               padx=12, pady=10)
        custom_card.grid(row=2, column=0, sticky=tk.NSEW, padx=4, pady=4)
        custom_card.bind("<Button-1>", lambda e: self._select_format("custom"))
        tk.Label(custom_card, text="⭐ 自定义（AI 解析）", font=FONT_LABEL,
                 fg=COLORS["primary"], bg=COLORS["bg_card"],
                 anchor=tk.W).pack(fill=tk.X)
        tk.Label(custom_card, text="上传格式要求，AI 自动识别",
                 font=FONT_CAPTION, fg=COLORS["text_hint"],
                 bg=COLORS["bg_card"], anchor=tk.W).pack(fill=tk.X, pady=(2, 0))
        self._format_cards["custom"] = custom_card
        for child in custom_card.winfo_children():
            child.bind("<Button-1>", lambda e: self._select_format("custom"))

        self._select_format("gbt7714")

        # ⭐ 自定义格式（AI 解析）区（默认隐藏，选「自定义」后显示）
        self._build_ai_card(c2)

        # ── 第三步：选项设置（开关化）──
        # 滑块初始在左边（关），用户点击后到右边（开，变绿）
        c3 = self._card(self._scrollable, "第三步 · 选项设置")
        self._opt_hyperlinks = tk.BooleanVar(value=False)
        self._opt_superscript = tk.BooleanVar(value=False)
        self._opt_reorder = tk.BooleanVar(value=False)
        self._opt_merge = tk.BooleanVar(value=False)
        self._opt_backup = tk.BooleanVar(value=False)
        self._opt_switches = {}
        opts = [
            ("添加交叉引用超链接（Ctrl+Click 跳转）", self._opt_hyperlinks),
            ("角标设置为上标", self._opt_superscript),
            ("按引用顺序自动重排参考文献", self._opt_reorder),
            ("合并连续引用（[1][2][3] → [1-3]）", self._opt_merge),
            ("自动备份原文件", self._opt_backup),
        ]
        for text, var in opts:
            row = tk.Frame(c3.content, bg=COLORS["bg_card"])
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=text, font=FONT_BODY, fg=COLORS["text_body"],
                     bg=COLORS["bg_card"], anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)
            sw = ToggleSwitch(row, width=50, height=26, initial=var.get())
            sw.pack(side=tk.RIGHT)
            self._opt_switches[text] = sw

        # ── 操作 + 进度 ──
        c4 = self._card(self._scrollable, "开始处理")
        self._start_btn = ModernButton(c4.content, text="开始格式化", variant="primary",
                                       height=46, command=self._start)
        self._start_btn.pack(fill=tk.X)
        self._progress = ttk.Progressbar(c4.content, mode="determinate")
        self._progress.pack(fill=tk.X, pady=(14, 6))
        self._status_label = tk.Label(c4.content, text="就绪", font=FONT_CAPTION,
                                      fg=COLORS["text_secondary"], bg=COLORS["bg_card"])
        self._status_label.pack(anchor=tk.W)

        # ── 处理结果 ──
        self._result_card = tk.Frame(self._scrollable, bg=COLORS["bg_card"],
                                     highlightthickness=1,
                                     highlightbackground=COLORS["border"])

        # 底部留白
        tk.Frame(self._scrollable, bg=COLORS["bg_page"], height=20).pack(fill=tk.X)

    # ═════════════════ 格式卡片选择 ═════════════════
    def _select_format(self, key):
        # 免费版限制：未登录仅可用 GB/T；非 GB/T 或自定义需订阅
        if key != "gbt7714":
            try:
                from core import user_manager, coupon_manager
                if not user_manager.is_logged_in() and not coupon_manager.is_activated():
                    if self._on_require_activation:
                        self._on_require_activation("完整格式（含自定义）")
                    self._format_var.set("gbt7714")
                    key = "gbt7714"
            except Exception:
                pass
        self._render_format_selection(key)
        # 选择格式即完成步骤 1（标准格式或自定义都算）
        if key != "custom" or self._ai_rules.strip():
            self.mark_step_complete(1)
        # 选「自定义」→ 显示 AI 解析区；选标准格式 → 隐藏
        if key == "custom":
            self._ai_card.pack(fill=tk.X, pady=(10, 2))
            self._check_ai_activation()
            # 展示知情同意 + 上传区，让用户能立即上传格式要求文件
            self._ai_show_upload_view()
        else:
            try:
                self._ai_card.pack_forget()
            except Exception:
                pass

    def _render_format_selection(self, key):
        """只更新格式卡片高亮显示（不触发放大检查）。"""
        self._format_var.set(key)
        for k, card in self._format_cards.items():
            if k == key:
                card.configure(highlightbackground=COLORS["primary"],
                               bg=COLORS["primary_light"])
                for child in card.winfo_children():
                    child.configure(bg=COLORS["primary_light"])
            else:
                card.configure(highlightbackground=COLORS["border"], bg=COLORS["bg_card"])
                for child in card.winfo_children():
                    child.configure(bg=COLORS["bg_card"])

    def _check_ai_activation(self):
        """选自定义格式时检查是否已激活（礼品券/付费），未激活则引导订阅。"""
        try:
            from core import coupon_manager
            if not coupon_manager.is_in_validity():
                # 未激活 → 提示并回退到标准格式
                if self._on_require_activation:
                    self._on_require_activation("AI 格式解析")
                self._select_format("gbt7714")
        except Exception:
            pass

    # ═════════════════ 文件拖拽卡 ═════════════════
    def _on_drop_hover(self, hover):
        self._drop_zone.configure(
            highlightbackground=COLORS["primary"] if hover else COLORS["border"])

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="选择论文文件",
            filetypes=[("Word 文档", "*.docx"), ("所有文件", "*.*")])
        if path:
            self._file_var.set(path)
            self._file_hint.configure(text=f"已选择：{os.path.basename(path)}",
                                      fg=COLORS["primary"])
            self.mark_step_complete(0)

    # ═════════════════ AI 智能格式解析 ═════════════════
    def _build_ai_card(self, parent):
        self._ai_card = tk.Frame(parent.content, bg=COLORS["bg_card"],
                                 highlightthickness=1,
                                 highlightbackground=COLORS["border"])
        self._ai_card.pack(fill=tk.X, pady=(10, 2))
        head = tk.Frame(self._ai_card, bg=COLORS["bg_card"])
        head.pack(fill=tk.X, padx=14, pady=(10, 4))
        tk.Label(head, text="⭐ 自定义格式（AI 解析）", font=FONT_LABEL,
                 fg=COLORS["primary"], bg=COLORS["bg_card"]).pack(side=tk.LEFT)
        tk.Label(head, text="上传期刊格式要求，AI 自动识别并套用", font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=COLORS["bg_card"]).pack(
            side=tk.LEFT, padx=(10, 0), pady=(3, 0))

        # 步骤 1：开启 + 知情同意
        self._ai_step1 = tk.Frame(self._ai_card, bg=COLORS["bg_card"])
        self._ai_step1.pack(fill=tk.X, padx=14, pady=(0, 10))
        self._ai_key_label = tk.Label(self._ai_step1, text="", font=FONT_CAPTION,
                                      fg=COLORS["warning"], bg=COLORS["bg_card"])
        self._ai_key_label.pack(anchor=tk.W)
        self._ai_go_config_btn = ModernButton(self._ai_step1, text="⚙️ 前往设置配置",
                                              variant="secondary", height=30,
                                              command=self._on_open_llm_config)
        consent_row = tk.Frame(self._ai_step1, bg=COLORS["bg_card"])
        consent_row.pack(fill=tk.X, pady=(6, 0))
        self._ai_consent = ToggleSwitch(consent_row, width=46, height=24, initial=False)
        self._ai_consent.pack(side=tk.LEFT)
        tk.Label(consent_row, text="我已了解并同意上传格式文件至 AI 服务解析",
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(8, 0))

        # 步骤 2：上传文件
        self._ai_step2 = tk.Frame(self._ai_card, bg=COLORS["bg_card"])
        self._ai_upload_zone = tk.Frame(self._ai_step2, bg=COLORS["bg_input"],
                                        highlightthickness=2,
                                        highlightbackground=COLORS["border"],
                                        cursor="hand2")
        self._ai_upload_zone.pack(fill=tk.X, ipady=16, pady=(0, 6))
        self._ai_upload_zone.bind("<Button-1>", lambda e: self._ai_upload())
        u_inner = tk.Frame(self._ai_upload_zone, bg=COLORS["bg_input"])
        u_inner.pack()
        tk.Label(u_inner, text="📎 上传格式要求文件", font=FONT_BODY,
                 fg=COLORS["text_secondary"], bg=COLORS["bg_input"]).pack()
        tk.Label(u_inner, text="支持 PDF / Word / 文本",
                 font=FONT_CAPTION, fg=COLORS["text_hint"],
                 bg=COLORS["bg_input"]).pack(pady=(4, 0))
        # 浏览文件按钮（同第一步样式）
        ModernButton(u_inner, text="浏览文件", variant="secondary", height=32,
                     command=self._ai_upload).pack(pady=(10, 0))
        self._ai_file_label = tk.Label(self._ai_step2, text="", font=FONT_CAPTION,
                                       fg=COLORS["text_secondary"], bg=COLORS["bg_card"])
        self._ai_parse_btn = ModernButton(self._ai_step2, text="🤖 开始 AI 解析",
                                          variant="primary", height=34,
                                          command=self._ai_parse)

        # 步骤 3：解析进度
        self._ai_step3 = tk.Frame(self._ai_card, bg=COLORS["bg_card"])
        self._ai_progress = ttk.Progressbar(self._ai_step3, mode="determinate")
        self._ai_progress.pack(fill=tk.X, padx=14, pady=(4, 0))
        self._ai_progress_label = tk.Label(self._ai_step3, text="", font=FONT_CAPTION,
                                           fg=COLORS["text_secondary"], bg=COLORS["bg_card"])
        self._ai_progress_label.pack(anchor=tk.W, padx=14, pady=(6, 10))

        # 步骤 4：确认结果
        self._ai_step4 = tk.Frame(self._ai_card, bg=COLORS["bg_card"])
        tk.Label(self._ai_step4, text="✅ 解析完成！AI 识别到以下格式规则：",
                 font=FONT_BODY_BOLD, fg=COLORS["success"],
                 bg=COLORS["bg_card"]).pack(anchor=tk.W, padx=14, pady=(4, 6))
        self._ai_rules_text = scrolledtext.ScrolledText(
            self._ai_step4, width=70, height=6, font=FONT_BODY, wrap=tk.WORD,
            bg=COLORS["bg_input"], fg=COLORS["text_body"],
            relief="flat", highlightthickness=1,
            highlightbackground=COLORS["border"])
        self._ai_rules_text.pack(fill=tk.X, padx=14)
        self._ai_rules_text.configure(state=tk.DISABLED)
        ai_btn_row = tk.Frame(self._ai_step4, bg=COLORS["bg_card"])
        ai_btn_row.pack(fill=tk.X, padx=14, pady=(8, 10))
        ModernButton(ai_btn_row, text="确认并使用", variant="primary", height=32,
                     command=self._ai_confirm).pack(side=tk.LEFT, padx=(0, 8))
        ModernButton(ai_btn_row, text="重新上传", variant="secondary", height=32,
                     command=self._ai_reset).pack(side=tk.LEFT, padx=(0, 8))
        ModernButton(ai_btn_row, text="手动调整规则", variant="secondary", height=32,
                     command=self._ai_manual_edit).pack(side=tk.LEFT)

        self._ai_show_step(1)
        self._ai_refresh_key_state()
        # 默认隐藏：选「自定义」格式时才显示
        try:
            self._ai_card.pack_forget()
        except Exception:
            pass

    def _ai_refresh_key_state(self):
        try:
            from core import translator
            has_key = bool(translator.get_api_key())
        except Exception:
            has_key = False
        if has_key:
            self._ai_key_label.configure(text="✓ 已配置 AI API 密钥", fg=COLORS["success"])
            self._ai_go_config_btn.pack_forget()
        else:
            self._ai_key_label.configure(
                text="⚙️ 此功能需要配置 AI API 密钥，请先在设置页配置",
                fg=COLORS["warning"])
            self._ai_go_config_btn.pack(anchor=tk.W, pady=(4, 0))

    def _ai_show_step(self, n):
        for frame in (self._ai_step1, self._ai_step2, self._ai_step3, self._ai_step4):
            frame.pack_forget()
        target = {1: self._ai_step1, 2: self._ai_step2,
                  3: self._ai_step3, 4: self._ai_step4}[n]
        target.pack(fill=tk.X, padx=14, pady=(0, 10))

    def _ai_show_upload_view(self):
        """选「自定义」时展示：知情同意 + 上传区同时可见，让用户能立即上传。"""
        for frame in (self._ai_step1, self._ai_step2, self._ai_step3, self._ai_step4):
            frame.pack_forget()
        self._ai_step1.pack(fill=tk.X, padx=14, pady=(0, 10))
        self._ai_step2.pack(fill=tk.X, padx=14, pady=(0, 10))
        self._ai_refresh_key_state()

    def _ai_upload(self):
        path = filedialog.askopenfilename(
            title="选择期刊格式要求文件",
            filetypes=[("支持的文件", "*.pdf *.docx *.doc *.txt *.md"),
                       ("PDF", "*.pdf"), ("Word", "*.docx *.doc"),
                       ("文本", "*.txt *.md"), ("所有文件", "*.*")])
        if not path:
            return
        self._ai_upload_path = path
        self._ai_file_label.configure(text=f"已上传：{os.path.basename(path)}")
        self._ai_file_label.pack(anchor=tk.W, pady=(0, 6))
        self._ai_parse_btn.pack(anchor=tk.W)
        # 上传本身不要求同意；点「开始 AI 解析」时才检查同意

    def _ai_parse(self):
        if not self._ai_upload_path:
            messagebox.showwarning("提示", "请先上传格式要求文件")
            return
        if not self._ai_consent.get():
            messagebox.showinfo("知情同意",
                                "请先勾选「我已了解并同意上传格式文件至 AI 服务解析」")
            return
        # 激活检测：未激活（试用/礼品券/订阅都失效）则引导订阅，不执行 AI 解析
        try:
            from core import coupon_manager
            if not coupon_manager.is_in_validity():
                if self._on_require_activation:
                    self._on_require_activation("AI 格式解析")
                return
        except Exception:
            pass
        try:
            from core import translator
            if not translator.get_api_key():
                messagebox.showwarning("提示",
                                       "未配置 AI API 密钥，请先到「设置 → AI 翻译 → 配置 API」填写")
                return
        except Exception:
            pass

        path = self._ai_upload_path
        self._ai_show_step(3)
        self._ai_progress.configure(value=5)
        self._ai_progress_label.configure(text="正在读取格式要求文件...")

        def _worker():
            try:
                from core.ref_formatter.file_reader import extract_text_from_file, truncate_content
                from core.ref_formatter.llm_enhancer import RefLLMEnhancer, RefLLMError
                self._ai_progress_label.after(0, lambda: self._ai_progress.configure(value=25))
                content = extract_text_from_file(path)
                if not content.strip():
                    self.after(0, lambda: self._ai_fail("无法从文件中提取文本，请确认文件可读"))
                    return
                content = truncate_content(content)
                self.after(0, lambda: self._ai_progress.configure(value=45))
                self.after(0, lambda: self._ai_progress_label.configure(
                    text="🤖 AI 正在识别参考文献格式规范..."))
                rules = RefLLMEnhancer().parse_custom_style(content)
                self.after(0, lambda: self._ai_show_result(rules))
            except RefLLMError as e:
                self.after(0, lambda: self._ai_fail(str(e)))
            except Exception as e:
                self.after(0, lambda: self._ai_fail(f"AI 解析失败：{e}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _ai_show_result(self, rules):
        self._ai_rules = rules
        self._ai_progress.configure(value=100)
        self._ai_progress_label.configure(text="解析完成")
        self._ai_rules_text.configure(state=tk.NORMAL)
        self._ai_rules_text.delete("1.0", tk.END)
        self._ai_rules_text.insert(tk.END, rules)
        self._ai_rules_text.configure(state=tk.DISABLED)
        self._ai_show_step(4)
        self.mark_step_complete(1)

    def _ai_confirm(self):
        messagebox.showinfo("已采用", "自定义格式规则已采用，可开始格式化")
        self._ai_rules = self._ai_rules_text.get("1.0", tk.END).strip()
        self._format_var.set("custom")
        self._select_format("custom") if "custom" in self._format_cards else None
        self._status_label.configure(text="已选用 AI 自定义格式", fg=COLORS["primary"])
        self.mark_step_complete(1)
        self._update_steps(2)

    def _ai_reset(self):
        self._ai_upload_path = None
        self._ai_file_label.pack_forget()
        self._ai_parse_btn.pack_forget()
        self._ai_show_step(2)

    def _ai_manual_edit(self):
        win = tk.Toplevel(self)
        win.title("手动调整格式规则")
        win.geometry("560x420")
        win.transient(self)
        win.configure(bg=COLORS["bg_page"])
        tk.Label(win, text="编辑 AI 解析出的格式规则", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"]).pack(
            anchor=tk.W, padx=16, pady=(14, 8))
        txt = scrolledtext.ScrolledText(
            win, width=70, height=16, font=FONT_BODY, wrap=tk.WORD,
            bg=COLORS["bg_input"], fg=COLORS["text_body"],
            relief="flat", highlightthickness=1,
            highlightbackground=COLORS["border"])
        txt.pack(fill=tk.BOTH, expand=True, padx=16)
        txt.insert(tk.END, self._ai_rules)
        def _save():
            self._ai_rules = txt.get("1.0", tk.END).strip()
            self._ai_rules_text.configure(state=tk.NORMAL)
            self._ai_rules_text.delete("1.0", tk.END)
            self._ai_rules_text.insert(tk.END, self._ai_rules)
            self._ai_rules_text.configure(state=tk.DISABLED)
            win.destroy()
        btn_row = tk.Frame(win, bg=COLORS["bg_page"])
        btn_row.pack(pady=12)
        ModernButton(btn_row, text="保存", variant="primary", height=34,
                     command=_save).pack(side=tk.LEFT, padx=6)
        ModernButton(btn_row, text="取消", variant="secondary", height=34,
                     command=win.destroy).pack(side=tk.LEFT, padx=6)

    def _ai_fail(self, msg):
        self._ai_progress.configure(value=0)
        self._ai_progress_label.configure(text=f"❌ {msg}", fg=COLORS["danger"])
        self._status_label.configure(text=msg, fg=COLORS["danger"])

    # ═════════════════ 处理流程 ═════════════════
    def _get_engine(self):
        if self._engine is None:
            from core.ref_formatter import RefFormatterEngine
            self._engine = RefFormatterEngine()
        return self._engine

    def _start(self):
        if self._running:
            return
        # 游客模式不能执行格式化（只能查看界面）
        try:
            from core import user_manager, coupon_manager
            if not user_manager.is_logged_in() and not coupon_manager.is_activated():
                if self._on_require_activation:
                    self._on_require_activation("执行格式化")
                return
        except Exception:
            pass
        path = self._file_var.get().strip()
        if not path:
            messagebox.showwarning("提示", "请先选择要格式化的 Word 文件")
            return
        if not os.path.exists(path):
            messagebox.showwarning("提示", "文件不存在，请重新选择")
            return
        if not path.lower().endswith(".docx"):
            messagebox.showwarning("提示", "仅支持 .docx 格式的 Word 文档")
            return

        fmt = self._format_var.get()

        # 选了「自定义（AI 解析）」但 AI 解析未开启/未完成 → 引导先完成 AI 解析
        if fmt == "custom":
            if not self._ai_consent.get():
                messagebox.showwarning(
                    "请先开启 AI 解析",
                    "您选择了「自定义（AI 解析）」格式，但尚未开启 AI 解析。\n\n"
                    "请先在「⭐ 自定义格式（AI 解析）」区域勾选知情同意并完成 AI 解析。")
                self._ai_card.pack(fill=tk.X, pady=(10, 2))
                self._ai_show_step(1)
                return
            if not self._ai_rules.strip():
                messagebox.showwarning(
                    "请先完成 AI 解析",
                    "您选择了「自定义（AI 解析）」格式，但尚未完成 AI 解析。\n\n"
                    "请上传格式要求文件并点击「开始 AI 解析」，确认规则后再格式化。")
                self._ai_card.pack(fill=tk.X, pady=(10, 2))
                self._ai_show_step(2)
                return

        # 选项值从 ToggleSwitch 状态读取（ToggleSwitch 自身管理状态）
        _sw = self._opt_switches
        options = {
            "format_type": fmt,
            "add_hyperlinks": _sw.get("添加交叉引用超链接（Ctrl+Click 跳转）",
                                      self._opt_hyperlinks).get(),
            "superscript": _sw.get("角标设置为上标", self._opt_superscript).get(),
            "reorder": _sw.get("按引用顺序自动重排参考文献", self._opt_reorder).get(),
            "merge_citations": _sw.get("合并连续引用（[1][2][3] → [1-3]）", self._opt_merge).get(),
            "backup": _sw.get("自动备份原文件", self._opt_backup).get(),
            "validate": True,
        }
        if fmt == "custom":
            rules = self._ai_rules.strip()
            options["custom_rules"] = rules
            if rules:
                from core.ref_formatter.llm_enhancer import RefLLMEnhancer
                options["llm_enhancer"] = RefLLMEnhancer()

        stem, ext = os.path.splitext(path)
        out = os.path.join(os.path.dirname(path), f"{os.path.basename(stem)}_格式化.docx")
        self._last_output = out
        self._running = True
        self._start_btn.set_enabled(False)
        self._start_btn.set_text("处理中...")
        self._progress.configure(value=0)
        self.mark_step_complete(3)

        def _progress(ratio, message):
            try:
                self._progress.configure(value=int(ratio * 100))
                self._status_label.configure(text=message)
            except Exception:
                pass

        def _done(stats):
            self._running = False
            self._start_btn.set_enabled(True)
            self._start_btn.set_text("开始格式化")
            self._show_result(stats)

        def _run():
            try:
                eng = self._get_engine()
                eng.set_progress_callback(_progress)
                stats = eng.format_document(path, out, options)
            except Exception as e:
                stats = {"success": False, "message": str(e),
                         "errors": [str(e)], "warnings": [], "output_path": out}
            try:
                self.after(0, lambda: _done(stats))
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    # ═════════════════ 结果展示（数据卡片） ═════════════════
    def _show_result(self, stats):
        self._result_card.pack(fill=tk.X, padx=2, pady=(0, 14))
        for w in self._result_card.winfo_children():
            w.destroy()
        tk.Label(self._result_card, text="处理结果", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]
                 ).pack(anchor=tk.W, padx=16, pady=(12, 4))
        tk.Frame(self._result_card, bg=COLORS["border_light"], height=1).pack(
            fill=tk.X, padx=16)

        body = tk.Frame(self._result_card, bg=COLORS["bg_card"])
        body.pack(fill=tk.X, padx=16, pady=12)

        if not stats.get("success"):
            tk.Label(body, text=f"❌ {stats.get('message', '处理失败')}", font=FONT_BODY_BOLD,
                     fg=COLORS["danger"], bg=COLORS["bg_card"]).pack(anchor=tk.W)
            for e in stats.get("errors", [])[:3]:
                tk.Label(body, text=f"   {e}", font=FONT_CAPTION,
                         fg=COLORS["danger"], bg=COLORS["bg_card"]).pack(anchor=tk.W)
            return

        # 数据卡片网格（2x2）
        grid = tk.Frame(body, bg=COLORS["bg_card"])
        grid.pack(fill=tk.X)
        for i in range(2):
            grid.columnconfigure(i, weight=1, uniform="stat")
        items = [
            ("识别正文引用", f"{stats.get('citations_found', 0)}", "处"),
            ("参考文献条目", f"{stats.get('references_found', 0)}", "条"),
            ("格式修正", f"{stats.get('format_fixed', 0)}", "处"),
            ("交叉引用", "是" if stats.get('hyperlinks_added') else "否", ""),
        ]
        for idx, (label, value, unit) in enumerate(items):
            cell = tk.Frame(grid, bg=COLORS["bg_card"], highlightthickness=1,
                            highlightbackground=COLORS["border"], padx=12, pady=10)
            cell.grid(row=idx // 2, column=idx % 2, sticky=tk.NSEW, padx=4, pady=4)
            tk.Label(cell, text=label, font=FONT_CAPTION, fg=COLORS["text_hint"],
                     bg=COLORS["bg_card"], anchor=tk.W).pack(fill=tk.X)
            tk.Label(cell, text=f"{value}{unit}", font=(FONT_BODY.cget("family"), 20, "bold")
                     if FONT_BODY else None,
                     fg=COLORS["primary"], bg=COLORS["bg_card"]).pack(anchor=tk.W, pady=(2, 0))

        tk.Label(body, text=f"按引用顺序重排：{'是' if stats.get('reordered') else '否'}",
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor=tk.W, pady=(8, 0))
        if stats.get("backup_path"):
            tk.Label(body, text=f"📦 已备份原文件：{os.path.basename(stats['backup_path'])}",
                     font=FONT_CAPTION, fg=COLORS["text_hint"],
                     bg=COLORS["bg_card"]).pack(anchor=tk.W)
        warnings = stats.get("warnings", [])
        if warnings:
            tk.Label(body, text=f"⚠️ {len(warnings)} 条提示，点击「查看报告」查看详情",
                     font=FONT_CAPTION, fg=COLORS["warning"],
                     bg=COLORS["bg_card"]).pack(anchor=tk.W, pady=(4, 0))

        btn_row = tk.Frame(body, bg=COLORS["bg_card"])
        btn_row.pack(fill=tk.X, pady=(12, 4))
        ModernButton(btn_row, text="打开文件", variant="primary", height=34,
                     command=self._open_output).pack(side=tk.LEFT, padx=(0, 8))
        ModernButton(btn_row, text="另存为...", variant="secondary", height=34,
                     command=self._save_as).pack(side=tk.LEFT, padx=(0, 8))
        if warnings or stats.get("errors"):
            ModernButton(btn_row, text="查看报告", variant="secondary", height=34,
                         command=lambda: self._show_report(stats)).pack(side=tk.LEFT)

    def _open_output(self):
        if not self._last_output or not os.path.exists(self._last_output):
            messagebox.showinfo("提示", "输出文件不存在")
            return
        try:
            if sys.platform == "darwin":
                os.system(f'open "{self._last_output}"')
            elif sys.platform == "win32":
                os.startfile(self._last_output)
            else:
                os.system(f'xdg-open "{self._last_output}"')
        except Exception:
            messagebox.showinfo("输出文件", self._last_output)

    def _save_as(self):
        if not self._last_output or not os.path.exists(self._last_output):
            return
        path = filedialog.asksaveasfilename(
            title="另存为",
            initialfile=os.path.basename(self._last_output),
            defaultextension=".docx",
            filetypes=[("Word 文档", "*.docx")])
        if path:
            import shutil
            try:
                shutil.copy2(self._last_output, path)
                messagebox.showinfo("完成", f"已保存到：{path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败：{e}")

    def _show_report(self, stats):
        win = tk.Toplevel(self)
        win.title("处理报告")
        win.geometry("560x420")
        win.transient(self)
        win.configure(bg=COLORS["bg_page"])
        tk.Label(win, text="处理报告", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"]).pack(
            anchor=tk.W, padx=16, pady=(14, 8))
        txt = scrolledtext.ScrolledText(
            win, width=70, height=18, font=FONT_BODY, wrap=tk.WORD,
            bg=COLORS["bg_input"], fg=COLORS["text_body"],
            relief="flat", highlightthickness=1,
            highlightbackground=COLORS["border"])
        txt.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        txt.insert(tk.END, "提示（warnings）：\n")
        for w in stats.get("warnings", []):
            txt.insert(tk.END, f"  ⚠️ {w}\n")
        txt.insert(tk.END, "\n错误（errors）：\n")
        for e in stats.get("errors", []):
            txt.insert(tk.END, f"  ❌ {e}\n")
        txt.configure(state=tk.DISABLED)

    def refresh(self):
        """侧栏切换到本页时调用。"""
        self._ai_refresh_key_state()
