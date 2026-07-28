"""
鸿讯 HONGXUN · 文献书架三栏布局
左: 论文卡片列表 (支持多选)
中: QuickLookPanel (inline 预览)
右: 元数据卡片 (固定 220px)
"""

import tkinter as tk
from tkinter import ttk, messagebox
from gui.theme import COLORS, ICONS, FONT_BODY, FONT_BODY_BOLD, FONT_HEADING, FONT_TITLE, FONT_CAPTION, FONT_LABEL
from gui.widgets import RoundedCard, StatusPill, IconLabel, IconCache, EmptyState, SkeletonLoader
from core.library import (
    get_paper, get_stats, get_all_task_names,
    update_paper_status, batch_update_status,
    export_ris,
    load_library,
)

_BATCH_SIZE = 20  # 每批创建的卡片数

STATUS_MAP = {"全部": None, "待读": "pending", "已读": "read", "排除": "excluded"}
STATUS_ICON = {"pending": "○", "read": "●", "excluded": "✕"}
STATUS_COLORS = {"pending": COLORS["warning"], "read": COLORS["success"], "excluded": COLORS["danger"]}
COLOR_BAR = {"pending": COLORS["warning"], "read": COLORS["success"], "excluded": COLORS["danger"]}


class PaperCard(tk.Frame):
    """论文卡片"""

    def __init__(self, master, paper, selected=False, on_click=None,
                 on_ctrl_click=None, on_shift_click=None,
                 on_double_click=None):
        super().__init__(master, bg=COLORS["bg_page"], cursor="hand2")
        self.paper = paper
        self._selected = selected
        self._on_click = on_click
        self._on_ctrl_click = on_ctrl_click
        self._on_shift_click = on_shift_click
        self._on_double_click = on_double_click

        self._build_card()
        self.bind("<Button-1>", self._handle_click)
        self.bind("<Double-1>", self._handle_double)
        self.bind("<Control-Button-1>", self._handle_ctrl_click)
        self.bind("<Shift-Button-1>", self._handle_shift_click)

    def _build_card(self):
        self._bg_frame = tk.Frame(self, bg=COLORS["bg_page"])
        self._bg_frame.pack(fill=tk.BOTH, expand=True)

        # 左侧状态色条 (3px)
        status = self.paper.get("status", "pending")
        bar_color = COLOR_BAR.get(status, COLORS["text_hint"])
        bar = tk.Frame(self._bg_frame, bg=bar_color, width=3)
        bar.pack(side=tk.LEFT, fill=tk.Y)

        # 内容区域
        content = tk.Frame(self._bg_frame, bg=COLORS["bg_page"])
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 6), pady=4)

        title_text = self.paper.get("title", "") or "无标题"
        tk.Label(content, text=title_text, font=FONT_BODY,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"],
                 anchor=tk.W, wraplength=260).pack(fill=tk.X)

        authors = self.paper.get("authors", "") or ""
        if authors:
            # 简化作者显示
            parts = [a.strip() for a in authors.replace(", ", ",").split(",") if a.strip()]
            if len(parts) > 2:
                authors = parts[0] + " et al."
            tk.Label(content, text=authors, font=FONT_CAPTION,
                     fg=COLORS["text_secondary"], bg=COLORS["bg_page"],
                     anchor=tk.W).pack(fill=tk.X)

        journal = self.paper.get("container_title", "") or ""
        if journal:
            tk.Label(content, text=journal, font=FONT_CAPTION,
                     fg=COLORS["text_hint"], bg=COLORS["bg_page"],
                     anchor=tk.W).pack(fill=tk.X)

        # 转发事件
        for w in [content] + content.winfo_children():
            w.bind("<Button-1>", self._handle_click, add="+")

        self._apply_selection()

    def _apply_selection(self):
        bg = COLORS["selected_bg"] if self._selected else COLORS["bg_page"]
        self._bg_frame.configure(bg=bg)
        for w in self._bg_frame.winfo_children():
            try:
                w.configure(bg=bg)
            except Exception:
                pass
            try:
                for sw in w.winfo_children():
                    sw.configure(bg=bg)
            except Exception:
                pass

    def set_selected(self, selected):
        self._selected = selected
        self._apply_selection()

    def _handle_click(self, event):
        if self._on_click:
            self._on_click(self)

    def _handle_ctrl_click(self, event):
        if self._on_ctrl_click:
            self._on_ctrl_click(self)
        return "break"

    def _handle_shift_click(self, event):
        if self._on_shift_click:
            self._on_shift_click(self)
        return "break"

    def _handle_double(self, event):
        if self._on_double_click:
            self._on_double_click(self.paper)


class QuickLookPanel(tk.Frame):
    """中栏详情预览"""

    def __init__(self, master, on_status_change=None, on_export=None, **kwargs):
        super().__init__(master, bg=COLORS["bg_page"], **kwargs)
        self._on_status_change = on_status_change
        self._on_export = on_export
        self._paper = None
        self._visible = False
        self._build_ui()

    def _build_ui(self):
        # 标题
        self._title_label = tk.Label(self, text="", font=FONT_TITLE,
                                     fg=COLORS["text_title"], bg=COLORS["bg_page"],
                                     anchor=tk.W, wraplength=500, justify=tk.LEFT)
        self._title_label.pack(fill=tk.X, padx=16, pady=(16, 4))

        # 作者
        self._authors_label = tk.Label(self, text="", font=FONT_BODY,
                                       fg=COLORS["text_secondary"], bg=COLORS["bg_page"],
                                       anchor=tk.W, wraplength=500)
        self._authors_label.pack(fill=tk.X, padx=16, pady=(0, 8))

        # 操作按钮行
        btn_row = tk.Frame(self, bg=COLORS["bg_page"])
        btn_row.pack(fill=tk.X, padx=16, pady=(0, 8))

        self._status_btn = tk.Label(btn_row, text="", font=FONT_BODY_BOLD,
                                    bg=COLORS["bg_page"], cursor="hand2")
        self._status_btn.pack(side=tk.LEFT, padx=(0, 12))
        self._status_btn.bind("<Button-1>", self._cycle_status)

        self._export_btn = tk.Label(btn_row, text="📤 导出", font=FONT_BODY_BOLD,
                                    fg=COLORS["primary"], bg=COLORS["bg_page"], cursor="hand2")
        self._export_btn.pack(side=tk.LEFT)
        self._export_btn.bind("<Button-1>", lambda e: self._on_export(self._paper) if self._on_export else None)

        # 分隔线
        tk.Frame(self, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 8))

        # 摘要
        self._abstract_text = tk.Text(self, wrap=tk.WORD, font=FONT_BODY,
                                      fg=COLORS["text_body"], bg=COLORS["bg_page"],
                                      borderwidth=0, highlightthickness=0,
                                      padx=16, pady=4, state=tk.DISABLED)
        self._abstract_text.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        # 滚动条
        scroll = ttk.Scrollbar(self._abstract_text, orient=tk.VERTICAL,
                               command=self._abstract_text.yview)
        self._abstract_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 导航
        nav_frame = tk.Frame(self, bg=COLORS["bg_page"])
        nav_frame.pack(fill=tk.X, padx=16, pady=(0, 16))

        self._prev_btn = tk.Label(nav_frame, text="← 上一篇", font=FONT_CAPTION,
                                  fg=COLORS["primary"], bg=COLORS["bg_page"], cursor="hand2")
        self._prev_btn.pack(side=tk.LEFT)
        self._prev_btn.bind("<Button-1>", lambda e: self._navigate(-1))

        self._pos_label = tk.Label(nav_frame, text="", font=FONT_CAPTION,
                                   fg=COLORS["text_secondary"], bg=COLORS["bg_page"])
        self._pos_label.pack(side=tk.LEFT, padx=16)

        self._next_btn = tk.Label(nav_frame, text="下一篇 →", font=FONT_CAPTION,
                                  fg=COLORS["primary"], bg=COLORS["bg_page"], cursor="hand2")
        self._next_btn.pack(side=tk.LEFT)
        self._next_btn.bind("<Button-1>", lambda e: self._navigate(1))

    def show(self, paper, papers_list=None, current_index=0):
        self._paper = paper
        self._papers_list = papers_list
        self._current_index = current_index
        self._visible = True

        self._title_label.configure(text=paper.get("title", ""))
        self._authors_label.configure(text=paper.get("authors", ""))
        self._update_status_btn()
        self._update_abstract()
        self._update_nav()

    def hide(self):
        self._visible = False
        self._paper = None
        self._title_label.configure(text="")
        self._authors_label.configure(text="")

        self._abstract_text.configure(state=tk.NORMAL)
        self._abstract_text.delete("1.0", tk.END)
        self._abstract_text.configure(state=tk.DISABLED)

        self._pos_label.configure(text="")

    def _update_abstract(self):
        if not self._paper:
            return
        abstract = self._paper.get("abstract", "") or "暂无摘要"
        self._abstract_text.configure(state=tk.NORMAL)
        self._abstract_text.delete("1.0", tk.END)
        self._abstract_text.insert("1.0", abstract)
        self._abstract_text.configure(state=tk.DISABLED)

    def _update_status_btn(self):
        if not self._paper:
            return
        status = self._paper.get("status", "pending")
        icon = STATUS_ICON.get(status, "○")
        self._status_btn.configure(text=f"{icon} {status}", fg=STATUS_COLORS.get(status, COLORS["text_secondary"]))

    def _update_nav(self):
        if self._papers_list and len(self._papers_list) > 0:
            self._pos_label.configure(text=f"{self._current_index + 1} / {len(self._papers_list)}")
        else:
            self._pos_label.configure(text="")

    def _cycle_status(self, event=None):
        if not self._paper:
            return
        cur = self._paper.get("status", "pending")
        nxt = {"pending": "read", "read": "excluded", "excluded": "pending"}
        new_status = nxt.get(cur, "pending")
        update_paper_status(self._paper["id"], new_status)
        self._paper["status"] = new_status
        self._update_status_btn()
        if self._on_status_change:
            self._on_status_change(self._paper["id"], new_status)

    def _navigate(self, direction):
        if not self._papers_list:
            return
        idx = self._current_index + direction
        if idx < 0 or idx >= len(self._papers_list):
            return
        self.show(self._papers_list[idx], self._papers_list, idx)


class MetadataCard(RoundedCard):
    """右侧元数据卡片"""

    def __init__(self, master, **kwargs):
        super().__init__(master, bg_color=COLORS["bg_card"], pad=12, hover_elevate=False, shadow=False, **kwargs)

        # Journal
        self._journal_label = tk.Label(self.content, text="", font=FONT_BODY,
                                       fg=COLORS["text_body"], bg=COLORS["bg_card"],
                                       anchor=tk.W, wraplength=180)
        self._journal_label.pack(fill=tk.X, pady=(0, 6))

        # DOI
        self._doi_label = tk.Label(self.content, text="", font=FONT_CAPTION,
                                   fg=COLORS["primary"], bg=COLORS["bg_card"],
                                   anchor=tk.W, cursor="hand2", wraplength=180)
        self._doi_label.pack(fill=tk.X, pady=(0, 6))
        self._doi_label.bind("<Button-1>", self._copy_doi)

        # Date
        self._date_label = tk.Label(self.content, text="", font=FONT_CAPTION,
                                    fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                                    anchor=tk.W)
        self._date_label.pack(fill=tk.X, pady=(0, 6))

        # Keywords
        self._keywords_frame = tk.Frame(self.content, bg=COLORS["bg_card"])
        self._keywords_frame.pack(fill=tk.X, pady=(0, 6))

        # Source task
        self._task_label = tk.Label(self.content, text="", font=FONT_CAPTION,
                                    fg=COLORS["text_hint"], bg=COLORS["bg_card"],
                                    anchor=tk.W)
        self._task_label.pack(fill=tk.X)

    def show(self, paper):
        journal = paper.get("container_title", "") or ""
        self._journal_label.configure(text=f"📖 {journal}" if journal else "")

        doi = paper.get("doi", "") or ""
        self._doi_label.configure(text=f"🔗 {doi}" if doi else "")

        pub_date = paper.get("pub_date", "") or paper.get("published_print", "") or ""
        self._date_label.configure(text=f"📅 {pub_date}" if pub_date else "")

        # 关键词
        for w in self._keywords_frame.winfo_children():
            w.destroy()
        keywords = paper.get("matched_keywords", paper.get("keywords", "")) or ""
        if keywords:
            kw_list = keywords.split("; ") if isinstance(keywords, str) else keywords
            tag = tk.Frame(self._keywords_frame, bg=COLORS["primary_light"])
            tag.pack(side=tk.LEFT, padx=(0, 4))
            tk.Label(tag, text=kw_list[0] if isinstance(kw_list, list) else kw_list,
                     font=FONT_CAPTION, fg=COLORS["primary"],
                     bg=COLORS["primary_light"], padx=6).pack()

        task = paper.get("task_name", "") or ""
        self._task_label.configure(text=f"📎 {task}" if task else "")

    def clear(self):
        self._journal_label.configure(text="")
        self._doi_label.configure(text="")
        self._date_label.configure(text="")
        self._task_label.configure(text="")
        for w in self._keywords_frame.winfo_children():
            w.destroy()

    def _copy_doi(self, event=None):
        doi = self._doi_label.cget("text").replace("🔗 ", "")
        if doi:
            self.clipboard_clear()
            self.clipboard_append(doi)
            # Flash feedback
            orig = self._doi_label.cget("fg")
            self._doi_label.configure(fg=COLORS["success"])
            self.after(1000, lambda: self._doi_label.configure(fg=orig) if self._doi_label.winfo_exists() else None)


class LibraryView(ttk.Frame):
    """三栏文献书架"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._papers = []
        self._card_widgets = []  # PaperCard list
        self._selected_ids = set()
        self._last_clicked_card = None
        self._ql_paper = None  # current quicklook paper

        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Row 0: Toolbar ──
        toolbar = tk.Frame(self, bg=COLORS["bg_page"])
        toolbar.grid(row=0, column=0, sticky=tk.EW, pady=(0, 8))
        toolbar.columnconfigure(4, weight=1)

        tk.Label(toolbar, text="状态:", fg=COLORS["text_secondary"],
                 bg=COLORS["bg_page"], font=FONT_BODY).grid(row=0, column=0, padx=(0, 4))
        self._status_var = tk.StringVar(value="全部")
        status_combo = ttk.Combobox(toolbar, textvariable=self._status_var,
                                    values=["全部", "待读", "已读", "排除"],
                                    state="readonly", width=6, font=FONT_BODY)
        status_combo.grid(row=0, column=1, padx=(0, 8))
        status_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        tk.Label(toolbar, text="任务:", fg=COLORS["text_secondary"],
                 bg=COLORS["bg_page"], font=FONT_BODY).grid(row=0, column=2, padx=(0, 4))
        self._task_var = tk.StringVar(value="全部")
        self._task_combo = ttk.Combobox(toolbar, textvariable=self._task_var,
                                        state="readonly", width=14, font=FONT_BODY)
        self._task_combo.grid(row=0, column=3, padx=(0, 8))
        self._task_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        self._search_var = tk.StringVar()
        search_entry = tk.Entry(toolbar, textvariable=self._search_var,
                                bd=1, relief="solid", highlightthickness=0,
                                bg=COLORS["bg_input"], fg=COLORS["text_body"],
                                insertbackground=COLORS["text_body"], font=FONT_BODY)
        search_entry.grid(row=0, column=4, sticky=tk.EW, padx=(0, 8), ipadx=4)
        search_entry.bind("<Return>", lambda e: self._refresh())

        search_btn = tk.Label(toolbar, text="🔍", font=FONT_BODY,
                              fg=COLORS["primary"], bg=COLORS["bg_page"], cursor="hand2")
        search_btn.grid(row=0, column=5, padx=(0, 8))
        search_btn.bind("<Button-1>", lambda e: self._refresh())

        export_btn = ttk.Button(toolbar, text="📤 导出 RIS", style="Primary.TButton",
                                command=self._export_ris)
        export_btn.grid(row=0, column=6, padx=(0, 4))
        refresh_btn = ttk.Button(toolbar, text="↻", style="Secondary.TButton",
                                 command=self._refresh)
        refresh_btn.grid(row=0, column=7)

        # ── Row 1: Three-column PanedWindow ──
        self._pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._pane.grid(row=1, column=0, sticky=tk.NSEW)

        # ─ Left Panel: Paper list ──
        self._left_panel = tk.Frame(self._pane, bg=COLORS["bg_page"])
        self._pane.add(self._left_panel, weight=1)

        # Batch action bar (hidden by default)
        self._batch_bar = tk.Frame(self._left_panel, bg=COLORS["primary_light"])
        self._batch_bar.pack(fill=tk.X)
        self._batch_bar.pack_forget()

        tk.Label(self._batch_bar, text="", font=FONT_CAPTION,
                 fg=COLORS["primary"], bg=COLORS["primary_light"],
                 padx=8).pack(side=tk.LEFT)

        for text, status in [("标记已读", "read"), ("标记待读", "pending"), ("导出选中", None)]:
            btn = tk.Label(self._batch_bar, text=text, font=FONT_CAPTION,
                           fg=COLORS["primary"], bg=COLORS["primary_light"],
                           cursor="hand2", padx=8)
            btn.pack(side=tk.LEFT)
            if status:
                btn.bind("<Button-1>", lambda e, s=status: self._batch_set_status(s))
            else:
                btn.bind("<Button-1>", lambda e: self._batch_export())

        clear_btn = tk.Label(self._batch_bar, text="取消选择", font=FONT_CAPTION,
                             fg=COLORS["text_hint"], bg=COLORS["primary_light"],
                             cursor="hand2", padx=8)
        clear_btn.pack(side=tk.RIGHT)
        clear_btn.bind("<Button-1>", lambda e: self._clear_selection())

        # Scrollable paper list
        self._list_canvas = tk.Canvas(self._left_panel, borderwidth=0,
                                      highlightthickness=0, bg=COLORS["bg_page"])
        list_scrollbar = ttk.Scrollbar(self._left_panel, orient=tk.VERTICAL,
                                       command=self._list_canvas.yview)
        self._list_canvas.configure(yscrollcommand=list_scrollbar.set)

        self._list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._list_inner = tk.Frame(self._list_canvas, bg=COLORS["bg_page"])
        self._list_inner.bind("<Configure>",
                              lambda e: self._list_canvas.configure(
                                  scrollregion=self._list_canvas.bbox("all")))
        self._list_canvas_window = self._list_canvas.create_window(
            (0, 0), window=self._list_inner, anchor=tk.NW)

        def _configure_list_width(event):
            self._list_canvas.itemconfig(self._list_canvas_window,
                                         width=max(event.width - 4, 260))
        self._list_canvas.bind("<Configure>", _configure_list_width)

        # Mousweheel
        def _on_mw(event):
            self._list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mw(event):
            self._list_canvas.bind_all("<MouseWheel>", _on_mw, add="+")

        def _unbind_mw(event):
            self._list_canvas.unbind_all("<MouseWheel>")

        self._list_inner.bind("<Enter>", _bind_mw)
        self._list_inner.bind("<Leave>", _unbind_mw)

        # Space key for QuickLook
        self._list_inner.bind("<Key-space>", self._toggle_quicklook)
        self._list_inner.bind("<Escape>", lambda e: self._hide_ql())
        self._list_inner.focus_set()

        # ─ Center Panel: QuickLook ──
        self._ql_panel = QuickLookPanel(
            self._pane,
            on_status_change=self._on_ql_status_change,
            on_export=lambda p: None,
        )
        # Not added to pane by default — added when show() is called

        # ─ Right Panel: Metadata ──
        self._right_panel = tk.Frame(self._pane, bg=COLORS["bg_page"], width=220)
        self._pane.add(self._right_panel, weight=0)

        self._meta_card = MetadataCard(self._right_panel)
        self._meta_card.pack(fill=tk.X, padx=8, pady=(0, 8))

        # Stats at bottom
        stats_frame = tk.Frame(self._right_panel, bg=COLORS["bg_card"])
        stats_frame.pack(fill=tk.X, padx=8)
        self._stats_var = tk.StringVar(value="总计: 0 篇")
        tk.Label(stats_frame, textvariable=self._stats_var,
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"], anchor=tk.W).pack(side=tk.LEFT, padx=12, pady=6)

        # ── Row 2: Stats bar (below pane) ──
        stats_bar = tk.Frame(self, bg=COLORS["bg_card"],
                             highlightbackground=COLORS["border_light"],
                             highlightthickness=1)
        stats_bar.grid(row=2, column=0, sticky=tk.EW, pady=(8, 0))
        self._main_stats_var = tk.StringVar(value="总计: 0  待读: 0  已读: 0  排除: 0")
        tk.Label(stats_bar, textvariable=self._main_stats_var,
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"], anchor=tk.W).pack(side=tk.LEFT, padx=16, pady=6)

        # Empty state (initially hidden)
        self._empty_state = EmptyState(self, icon="search",
                                        title="文献书架是空的",
                                        subtitle="执行检索后，论文会自动出现在这里")
        self._empty_state.grid(row=1, column=0, sticky=tk.NSEW)
        self._empty_state.grid_remove()

    def refresh(self):
        self._refresh()

    def _refresh_lazy(self, batch_start=0):
        """分批加载卡片，避免 UI 线程长时间阻塞。"""
        batch = self._papers[batch_start:batch_start + _BATCH_SIZE]
        for paper in batch:
            card = PaperCard(self._list_inner, paper,
                             on_click=self._on_card_click,
                             on_ctrl_click=self._on_card_ctrl_click,
                             on_shift_click=self._on_card_shift_click,
                             on_double_click=self._on_card_double_click)
            card.pack(fill=tk.X, padx=4, pady=(0, 2))
            self._card_widgets.append(card)

        next_start = batch_start + _BATCH_SIZE
        if next_start < len(self._papers):
            # 下一批用 after 调度，让 UI 来得及刷新
            self.after(10, lambda: self._refresh_lazy(next_start))
        else:
            # 最后一批完成，更新统计
            stats = get_stats()
            self._main_stats_var.set(
                f"总计: {stats['total']}  待读: {stats['pending']}  已读: {stats['read']}  排除: {stats['excluded']}")
            self._stats_var.set(f"总计: {len(self._papers)} 篇")

    def _refresh(self):
        # 缓存 library 数据，避免反复读取 JSON
        self._lib_cache = load_library()

        # Update task names
        task_names = get_all_task_names()
        current_task_val = self._task_var.get()
        self._task_combo["values"] = ["全部"] + task_names
        if current_task_val not in ["全部"] + task_names:
            self._task_var.set("全部")

        status = STATUS_MAP.get(self._status_var.get(), None)
        search_text = self._search_var.get().strip() or None
        task_filter = self._task_var.get()
        task_filter = None if task_filter == "全部" else task_filter

        # 在内存中过滤，不重复读 JSON
        all_papers = self._lib_cache.get("papers", [])
        if status:
            all_papers = [p for p in all_papers if p.get("status") == status]
        if search_text:
            q = search_text.lower()
            all_papers = [p for p in all_papers if q in p.get("title", "").lower()]
        if task_filter:
            all_papers = [p for p in all_papers if p.get("task_name") == task_filter]
        self._papers = all_papers

        # Toggle empty state
        if not self._papers:
            self._empty_state.grid()
            self._list_inner.pack_forget()
            self._stats_var.set("总计: 0 篇")
            self._main_stats_var.set("总计: 0  待读: 0  已读: 0  排除: 0")
            self._hide_ql()
            self._meta_card.clear()
            return

        self._empty_state.grid_remove()
        self._list_inner.pack(fill=tk.BOTH, expand=True)

        # Destroy old cards
        for w in self._list_inner.winfo_children():
            w.destroy()
        self._card_widgets = []
        self._selected_ids = set()
        self._last_clicked_card = None

        # 分批懒加载（每批 20 张，用 after 让 UI 呼吸）
        self._refresh_lazy(0)

    def _on_card_click(self, card):
        self._clear_selection()
        self._selected_ids.add(card.paper["id"])
        card.set_selected(True)
        self._last_clicked_card = card
        self._show_detail(card)
        self._update_batch_bar()

    def _on_card_ctrl_click(self, card):
        if card.paper["id"] in self._selected_ids:
            self._selected_ids.discard(card.paper["id"])
            card.set_selected(False)
        else:
            self._selected_ids.add(card.paper["id"])
            card.set_selected(True)
        self._last_clicked_card = card
        self._update_batch_bar()

    def _on_card_shift_click(self, card):
        if self._last_clicked_card and self._last_clicked_card in self._card_widgets:
            last_idx = self._card_widgets.index(self._last_clicked_card)
            current_idx = self._card_widgets.index(card)
            start, end = (last_idx, current_idx) if last_idx <= current_idx else (current_idx, last_idx)
            for i in range(start, end + 1):
                c = self._card_widgets[i]
                self._selected_ids.add(c.paper["id"])
                c.set_selected(True)
        self._update_batch_bar()

    def _on_card_double_click(self, paper):
        # Trigger existing abstract popup (handled by gui_app.py)
        if hasattr(self.master, 'master') and hasattr(self.master.master, '_show_abstract_popup'):
            self.master.master._show_abstract_popup(paper["id"])

    def _show_detail(self, card):
        self._meta_card.show(card.paper)

        # Show in QuickLook center panel
        idx = self._card_widgets.index(card) if card in self._card_widgets else 0
        if not self._ql_panel._visible:
            self._pane.insert(self._ql_panel, 1, weight=2)
        self._ql_panel.show(card.paper, self._papers, idx)

    def _toggle_quicklook(self, event=None):
        if not self._card_widgets:
            return
        # Toggle last selected paper
        target = None
        if self._last_clicked_card:
            target = self._last_clicked_card.paper
        elif self._card_widgets:
            target = self._card_widgets[0].paper

        if target and self._ql_panel._visible and self._ql_panel._paper and \
                self._ql_panel._paper.get("id") == target.get("id"):
            self._hide_ql()
        elif target:
            idx = next((i for i, c in enumerate(self._card_widgets) if c.paper.get("id") == target.get("id")), 0)
            if not self._ql_panel._visible:
                self._pane.insert(self._ql_panel, 1, weight=2)
            self._ql_panel.show(target, self._papers, idx)
            # Also show metadata
            self._meta_card.show(target)

    def _hide_ql(self):
        if self._ql_panel._visible:
            self._pane.forget(self._ql_panel)
            self._ql_panel.hide()

    def _on_ql_status_change(self, paper_id, new_status):
        # Refresh cards to show updated status
        self._refresh()

    def _clear_selection(self):
        for card in self._card_widgets:
            card.set_selected(False)
        self._selected_ids.clear()
        self._meta_card.clear()
        self._hide_ql()
        self._update_batch_bar()

    def _update_batch_bar(self):
        n = len(self._selected_ids)
        if n >= 2:
            children = self._batch_bar.pack_info() if len(self._batch_bar.pack_info()) > 0 else {}
            if not children:
                self._batch_bar.pack(fill=tk.X, before=self._list_canvas)
            # Update count label
            for w in self._batch_bar.winfo_children():
                if isinstance(w, tk.Label) and "已选" in (w.cget("text") or ""):
                    w.configure(text=f"已选 {n} 篇")
                    break
        else:
            try:
                self._batch_bar.pack_forget()
            except Exception:
                pass

    def _batch_set_status(self, status):
        if not self._selected_ids:
            return
        n = batch_update_status(list(self._selected_ids), status)
        self._clear_selection()
        self._refresh()

    def _batch_export(self):
        if not self._selected_ids:
            return
        papers = [p for p in self._papers if p["id"] in self._selected_ids]
        if not papers:
            return
        from tkinter import filedialog, messagebox
        fp = filedialog.asksaveasfilename(
            defaultextension=".ris",
            filetypes=[("RIS 文件", "*.ris")],
            initialfile="hongxun_export.ris")
        if fp:
            export_ris(papers, fp)
            messagebox.showinfo("导出成功", f"已导出 {len(papers)} 篇论文")

    def _export_ris(self):
        if not self._papers:
            messagebox.showwarning("提示", "书架为空，无数据可导出")
            return
        from tkinter import filedialog, messagebox
        fp = filedialog.asksaveasfilename(
            defaultextension=".ris",
            filetypes=[("RIS 文件", "*.ris")],
            initialfile="hongxun_export.ris")
        if fp:
            export_ris(self._papers, fp)
            messagebox.showinfo("导出成功", f"已导出 {len(self._papers)} 篇论文")
