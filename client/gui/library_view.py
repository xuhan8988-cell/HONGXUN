"""
鸿讯 HONGXUN · 文献书架三栏布局
左: 论文列表（ttk.Treeview）— 支持多选
中: QuickLookPanel (inline 预览)
右: 元数据卡片 (固定 220px)
"""

import tkinter as tk
from tkinter import ttk, messagebox
from gui.theme import COLORS, ICONS, FONT_BODY, FONT_BODY_BOLD, FONT_HEADING, FONT_TITLE, FONT_CAPTION, FONT_LABEL
from gui.widgets import RoundedCard, EmptyState
from core.library import (
    get_paper, get_stats, get_all_task_names,
    update_paper_status, batch_update_status,
    export_ris,
    load_library,
)

STATUS_MAP = {"全部": None, "待读": "pending", "已读": "read", "排除": "excluded"}
STATUS_ICON = {"pending": "●", "read": "●", "excluded": "✕"}
STATUS_COLORS = {"pending": COLORS["text_hint"], "read": COLORS["success"], "excluded": COLORS["danger"]}
STATUS_LABELS = {"pending": "待读", "read": "已读", "excluded": "排除"}

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
        self._title_label = tk.Label(self, text="", font=FONT_TITLE,
                                     fg=COLORS["text_title"], bg=COLORS["bg_page"],
                                     anchor=tk.W, wraplength=500, justify=tk.LEFT)
        self._title_label.pack(fill=tk.X, padx=16, pady=(16, 4))

        self._authors_label = tk.Label(self, text="", font=FONT_BODY,
                                       fg=COLORS["text_secondary"], bg=COLORS["bg_page"],
                                       anchor=tk.W, wraplength=500)
        self._authors_label.pack(fill=tk.X, padx=16, pady=(0, 8))

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

        tk.Frame(self, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=16, pady=(0, 8))

        self._abstract_text = tk.Text(self, wrap=tk.WORD, font=FONT_BODY,
                                      fg=COLORS["text_body"], bg=COLORS["bg_page"],
                                      borderwidth=0, highlightthickness=0,
                                      padx=16, pady=4, state=tk.DISABLED)
        self._abstract_text.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        scroll = ttk.Scrollbar(self._abstract_text, orient=tk.VERTICAL,
                               command=self._abstract_text.yview)
        self._abstract_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

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

        self._journal_label = tk.Label(self.content, text="", font=FONT_BODY,
                                       fg=COLORS["text_body"], bg=COLORS["bg_card"],
                                       anchor=tk.W, wraplength=180)
        self._journal_label.pack(fill=tk.X, pady=(0, 6))

        self._doi_label = tk.Label(self.content, text="", font=FONT_CAPTION,
                                   fg=COLORS["primary"], bg=COLORS["bg_card"],
                                   anchor=tk.W, cursor="hand2", wraplength=180)
        self._doi_label.pack(fill=tk.X, pady=(0, 6))
        self._doi_label.bind("<Button-1>", self._copy_doi)

        self._date_label = tk.Label(self.content, text="", font=FONT_CAPTION,
                                    fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                                    anchor=tk.W)
        self._date_label.pack(fill=tk.X, pady=(0, 6))

        self._keywords_frame = tk.Frame(self.content, bg=COLORS["bg_card"])
        self._keywords_frame.pack(fill=tk.X, pady=(0, 6))

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
            orig = self._doi_label.cget("fg")
            self._doi_label.configure(fg=COLORS["success"])
            self.after(1000, lambda: self._doi_label.configure(fg=orig) if self._doi_label.winfo_exists() else None)


class LibraryView(ttk.Frame):
    """三栏文献书架——左栏使用 ttk.Treeview 实现高性能列表"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._papers = []
        self._paper_map = {}
        self._ql_paper = None
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

        # ─ Left Panel: Treeview ──
        self._left_panel = tk.Frame(self._pane, bg=COLORS["bg_page"])
        self._pane.add(self._left_panel, weight=1)

        self._tree = ttk.Treeview(
            self._left_panel,
            columns=("status", "title", "authors", "journal", "task", "id"),
            show="headings",
            selectmode="extended",
            height=12,
        )
        self._tree.heading("status", text="  ")
        self._tree.heading("title", text="标题")
        self._tree.heading("authors", text="作者")
        self._tree.heading("journal", text="期刊")
        self._tree.heading("task", text="来源任务")
        self._tree.heading("id", text="ID")
        self._tree.column("status", width=30, minwidth=24, anchor=tk.CENTER)
        self._tree.column("title", width=280, minwidth=150, stretch=True)
        self._tree.column("authors", width=160, minwidth=80)
        self._tree.column("journal", width=180, minwidth=100)
        self._tree.column("task", width=100, minwidth=60)
        self._tree.column("id", width=0, stretch=False)

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-1>", self._on_tree_double)
        self._tree.bind("<ButtonRelease-1>", self._on_tree_click_column)
        self._tree.bind("<Key-space>", self._toggle_quicklook)
        self._tree.bind("<Escape>", lambda e: self._hide_ql())

        tree_scroll = ttk.Scrollbar(self._left_panel, orient=tk.VERTICAL,
                                    command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # ─ Center Panel: QuickLook ──
        self._ql_panel = QuickLookPanel(
            self._pane,
            on_status_change=self._on_ql_status_change,
            on_export=lambda p: None,
        )

        # ─ Right Panel: Metadata ──
        self._right_panel = tk.Frame(self._pane, bg=COLORS["bg_page"], width=220)
        self._pane.add(self._right_panel, weight=0)

        self._meta_card = MetadataCard(self._right_panel)
        self._meta_card.pack(fill=tk.X, padx=8, pady=(0, 8))

        stats_frame = tk.Frame(self._right_panel, bg=COLORS["bg_card"])
        stats_frame.pack(fill=tk.X, padx=8)
        self._stats_var = tk.StringVar(value="总计: 0 篇")
        tk.Label(stats_frame, textvariable=self._stats_var,
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"], anchor=tk.W).pack(side=tk.LEFT, padx=12, pady=6)

        # ── Row 2: Stats bar ──
        stats_bar = tk.Frame(self, bg=COLORS["bg_card"],
                             highlightbackground=COLORS["border_light"],
                             highlightthickness=1)
        stats_bar.grid(row=2, column=0, sticky=tk.EW, pady=(8, 0))
        self._main_stats_var = tk.StringVar(value="总计: 0  待读: 0  已读: 0  排除: 0")
        tk.Label(stats_bar, textvariable=self._main_stats_var,
                 font=FONT_CAPTION, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"], anchor=tk.W).pack(side=tk.LEFT, padx=16, pady=6)

        self._empty_state = EmptyState(self, icon="search",
                                        title="文献书架是空的",
                                        subtitle="执行检索后，论文会自动出现在这里")
        self._empty_state.grid(row=1, column=0, sticky=tk.NSEW)
        self._empty_state.grid_remove()

    def refresh(self):
        self._refresh()

    def _refresh(self):
        lib = load_library()
        task_names = get_all_task_names()
        current_task_val = self._task_var.get()

        self._task_combo["values"] = ["全部"] + task_names
        if current_task_val not in ["全部"] + task_names:
            self._task_var.set("全部")

        status = STATUS_MAP.get(self._status_var.get(), None)
        search_text = self._search_var.get().strip() or None
        task_filter = self._task_var.get()
        task_filter = None if task_filter == "全部" else task_filter

        papers = lib.get("papers", [])
        if status:
            papers = [p for p in papers if p.get("status") == status]
        if search_text:
            q = search_text.lower()
            papers = [p for p in papers if q in p.get("title", "").lower()]
        if task_filter:
            papers = [p for p in papers if p.get("task_name") == task_filter]
        self._papers = papers

        if not papers:
            self._empty_state.grid()
            self._tree.pack_forget()
            self._stats_var.set("总计: 0 篇")
            self._main_stats_var.set("总计: 0  待读: 0  已读: 0  排除: 0")
            self._hide_ql()
            self._meta_card.clear()
            return

        self._empty_state.grid_remove()
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for item in self._tree.get_children():
            self._tree.delete(item)
        self._paper_map = {}

        for p in papers:
            title = (p.get("title") or "")[:100]
            authors = (p.get("authors") or "")
            if authors:
                parts = [a.strip() for a in authors.replace(", ", ",").split(",") if a.strip()]
                if len(parts) > 2:
                    authors = parts[0] + " et al."
            journal = (p.get("container_title") or "")[:60]
            task_name = (p.get("task_name") or "")[:30]
            status_icon = STATUS_ICON.get(p.get("status", "pending"), "○")

            iid = self._tree.insert("", tk.END, values=(
                status_icon, title, authors, journal, task_name, p.get("id", "")))
            self._paper_map[iid] = p

        stats = get_stats()
        self._main_stats_var.set(
            f"总计: {stats['total']}  待读: {stats['pending']}  已读: {stats['read']}  排除: {stats['excluded']}")
        self._stats_var.set(f"总计: {len(papers)} 篇")

    def _get_selected_papers(self):
        sel = self._tree.selection()
        papers = []
        for iid in sel:
            p = self._paper_map.get(iid)
            if p:
                papers.append(p)
        return papers

    def _mark_paper(self, p, new_status, iid=None):
        """更新论文状态并刷新 Treeview 行显示。"""
        update_paper_status(p["id"], new_status)
        p["status"] = new_status
        icon = STATUS_ICON.get(new_status, "●")
        if iid:
            vals = list(self._tree.item(iid, "values"))
            vals[0] = icon
            self._tree.item(iid, values=vals)
        stats = get_stats()
        self._main_stats_var.set(
            f"总计: {stats['total']}  待读: {stats['pending']}  已读: {stats['read']}  排除: {stats['excluded']}")

    def _on_tree_select(self, event):
        """单击——自动标记已读，更新元数据。"""
        sel = self._tree.selection()
        if not sel:
            self._meta_card.clear()
            return
        iid = sel[0]
        p = self._paper_map.get(iid)
        if not p:
            return
        # 自动标记为已读
        if p.get("status") != "read":
            self._mark_paper(p, "read", iid=iid)
        self._meta_card.show(p)
        if self._ql_panel._visible:
            idx = next((i for i, pp in enumerate(self._papers) if pp.get("id") == p.get("id")), 0)
            self._ql_panel.show(p, self._papers, idx)

    _on_tree_click = None  # unused, remove from bindings

    def _on_tree_click_column(self, event):
        """点击状态列循环切换阅读状态。"""
        col = self._tree.identify_column(event.x)
        if col == "#1":
            iid = self._tree.identify_row(event.y)
            if not iid:
                return
            p = self._paper_map.get(iid)
            if p:
                cur = p.get("status", "pending")
                nxt = {"pending": "read", "read": "excluded", "excluded": "pending"}
                new_status = nxt.get(cur, "pending")
                self._mark_paper(p, new_status, iid=iid)

    def _on_tree_double(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        p = self._paper_map.get(iid)
        if not p:
            return
        # 双击也自动标记为已读
        if p.get("status") != "read":
            self._mark_paper(p, "read", iid=iid)
        self._show_paper_popup(p)

    def _show_paper_popup(self, paper):
        """双击弹出论文详情窗口。"""
        win = tk.Toplevel(self.master)
        win.title(paper.get("title", "")[:60])
        win.configure(bg=COLORS["bg_page"])
        win.transient(self.master)
        win.geometry("600x500")
        win.resizable(True, True)

        frame = tk.Frame(win, bg=COLORS["bg_page"])
        frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # 标题
        tk.Label(frame, text=paper.get("title", ""), font=FONT_TITLE,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"],
                 anchor=tk.W, wraplength=540, justify=tk.LEFT).pack(fill=tk.X)

        # 作者
        authors = paper.get("authors", "") or ""
        if authors:
            tk.Label(frame, text=authors, font=FONT_BODY,
                     fg=COLORS["text_secondary"], bg=COLORS["bg_page"],
                     anchor=tk.W, wraplength=540).pack(fill=tk.X, pady=(4, 0))

        # 期刊 + DOI
        meta = []
        j = paper.get("container_title", "")
        if j:
            meta.append(j)
        d = paper.get("doi", "")
        if d:
            meta.append(f"DOI: {d}")
        if meta:
            tk.Label(frame, text=" | ".join(meta), font=FONT_CAPTION,
                     fg=COLORS["text_hint"], bg=COLORS["bg_page"],
                     anchor=tk.W).pack(fill=tk.X, pady=(4, 8))

        # 分隔线
        tk.Frame(frame, bg=COLORS["border_light"], height=1).pack(fill=tk.X)

        # 摘要
        abstract = paper.get("abstract", "") or "暂无摘要"
        text_w = tk.Text(frame, wrap=tk.WORD, font=FONT_BODY,
                         fg=COLORS["text_body"], bg=COLORS["bg_input"],
                         borderwidth=0, highlightthickness=0,
                         padx=12, pady=8)
        text_w.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        text_w.insert("1.0", abstract)
        text_w.configure(state=tk.DISABLED)

        scroll = ttk.Scrollbar(text_w, orient=tk.VERTICAL, command=text_w.yview)
        text_w.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 关闭快捷键
        win.bind("<Escape>", lambda e: win.destroy())
        win.focus_set()

    def _toggle_quicklook(self, event=None):
        if not self._papers:
            return
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        p = self._paper_map.get(iid)
        if not p:
            return
        if self._ql_panel._visible and self._ql_panel._paper and \
                self._ql_panel._paper.get("id") == p.get("id"):
            self._hide_ql()
        else:
            if not self._ql_panel._visible:
                self._pane.insert(self._ql_panel, 1, weight=2)
            idx = next((i for i, pp in enumerate(self._papers) if pp.get("id") == p.get("id")), 0)
            self._ql_panel.show(p, self._papers, idx)
            self._meta_card.show(p)

    def _hide_ql(self):
        if self._ql_panel._visible:
            self._pane.forget(self._ql_panel)
            self._ql_panel.hide()

    def _on_ql_status_change(self, paper_id, new_status):
        self._refresh()

    def _export_ris(self):
        if not self._papers:
            messagebox.showwarning("提示", "书架为空，无数据可导出")
            return
        from tkinter import filedialog
        fp = filedialog.asksaveasfilename(
            defaultextension=".ris",
            filetypes=[("RIS 文件", "*.ris")],
            initialfile="hongxun_export.ris")
        if fp:
            export_ris(self._papers, fp)
            messagebox.showinfo("导出成功", f"已导出 {len(self._papers)} 篇论文")

    def _batch_set_status(self, status):
        sel_ids = [p["id"] for p in self._get_selected_papers() if p.get("id")]
        if not sel_ids:
            return
        batch_update_status(sel_ids, status)
        self._refresh()

    def _batch_export(self):
        papers = self._get_selected_papers()
        if not papers:
            return
        from tkinter import filedialog
        fp = filedialog.asksaveasfilename(
            defaultextension=".ris",
            filetypes=[("RIS 文件", "*.ris")],
            initialfile="hongxun_export.ris")
        if fp:
            export_ris(papers, fp)
            messagebox.showinfo("导出成功", f"已导出 {len(papers)} 篇论文")
