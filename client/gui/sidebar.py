"""
鸿讯 HONGXUN · 侧栏（v3 — 精简紧凑版）
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from gui.theme import COLORS, ICONS, FONT_BODY, FONT_BODY_BOLD, FONT_CAPTION, FONT_HEADING


class TaskCard(tk.Frame):
    """任务卡片（32px 紧凑，无状态标签，支持运行指示）"""

    def __init__(self, master, task_id, task_name, enabled=True,
                 selected=False, running=False, on_click=None,
                 on_rename=None, on_context=None,
                 on_search=None, on_delete=None, on_copy=None, **kwargs):
        self._task_id = task_id
        self._task_name = task_name
        self._enabled = enabled
        self._selected = selected
        self._running = running
        self._on_click = on_click
        self._on_rename = on_rename
        self._on_context = on_context
        self._on_search = on_search
        self._on_delete = on_delete
        self._on_copy = on_copy

        super().__init__(master, bg=COLORS["sidebar_bg"], cursor="hand2", **kwargs)
        self._build_card()
        self.bind("<Button-1>", self._handle_click)
        self.bind("<Double-1>", self._handle_rename)
        self.bind("<Button-3>", self._handle_context)

    def _build_card(self):
        bg = COLORS["selected_bg"] if self._selected else COLORS["sidebar_bg"]
        self.configure(bg=bg)

        # 选中蓝色边条
        if self._selected:
            tk.Frame(self, bg=COLORS["primary"], width=3).pack(side=tk.LEFT, fill=tk.Y)

        row = tk.Frame(self, bg=bg)
        row.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 4), pady=4)

        # 状态点
        if self._running:
            dot_color = COLORS["primary"]
            dot_text = "◉"  # 实心运行中
        else:
            dot_color = COLORS["dot_on"] if self._enabled else COLORS["dot_off"]
            dot_text = "●"
        tk.Label(row, text=dot_text, font=FONT_CAPTION,
                 fg=dot_color, bg=bg).pack(side=tk.LEFT, padx=(0, 4))

        # 任务名
        tk.Label(row, text=self._task_name,
                 font=FONT_BODY_BOLD,
                 fg=COLORS["text_title"] if self._enabled else COLORS["text_hint"],
                 bg=bg, anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 「⋯」更多
        self._more_btn = tk.Label(row, text="⋯", font=FONT_CAPTION,
                                  fg=COLORS["text_hint"], bg=bg, cursor="hand2",
                                  padx=4)
        self._more_btn.pack(side=tk.RIGHT)
        self._more_btn.bind("<Button-1>", self._show_more_menu)

        for w in [row] + row.winfo_children():
            if w != self._more_btn:
                w.bind("<Button-1>", self._handle_click, add="+")

    def set_running(self, running):
        """外部设置运行状态，触发重绘"""
        self._running = running
        for w in self.winfo_children():
            w.destroy()
        self._build_card()

    def set_selected(self, selected):
        self._selected = selected
        for w in self.winfo_children():
            w.destroy()
        self._build_card()

    def _show_more_menu(self, event):
        menu = tk.Menu(self, tearoff=0, font=FONT_BODY,
                       bg=COLORS["bg_card"], fg=COLORS["text_body"])
        if self._enabled:
            menu.add_command(label="🔍 执行检索",
                             command=lambda: self._on_search(self._task_id) if self._on_search else None)
        menu.add_command(label="📋 复制任务",
                         command=lambda: self._on_copy(self._task_id) if self._on_copy else None)
        menu.add_separator()
        label = "⏸ 禁用" if self._enabled else "▶ 启用"
        menu.add_command(label=label,
                         command=lambda: self._on_context(self._task_id, event))
        menu.add_separator()
        menu.add_command(label="🗑 删除", foreground=COLORS["danger"],
                         command=lambda: self._on_delete(self._task_id) if self._on_delete else None)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _handle_click(self, event):
        if self._on_click:
            self._on_click(self._task_id)

    def _handle_rename(self, event):
        if self._on_rename:
            self._on_rename(self._task_id)

    def _handle_context(self, event):
        if self._on_context:
            self._on_context(self._task_id, event)

    @property
    def task_id(self):
        return self._task_id


class TaskSidebar(ttk.Frame):
    """侧栏：任务列表 + 底部紧凑推送控制"""

    def __init__(self, master, on_select=None, on_new=None,
                 on_toggle_push=None,
                 load_tasks_fn=None, get_task_fn=None,
                 save_task_fn=None, width=200, **kwargs):
        super().__init__(master, **kwargs)
        self._on_select = on_select
        self._on_new_callback = on_new
        self._on_toggle_push = on_toggle_push
        self._load_tasks = load_tasks_fn or (lambda: {})
        self._get_task = get_task_fn or (lambda tid: None)
        self._save_task = save_task_fn or (lambda tid, task: None)
        self._selected_task_id = None
        self._task_cards = {}
        self._task_order = []
        self._push_running = False
        self._running_task_id = None

        self._build_ui()

    def _build_ui(self):
        self.configure(style="TFrame")

        # 标题行
        title_row = tk.Frame(self, bg=COLORS["sidebar_bg"])
        title_row.pack(fill=tk.X, padx=10, pady=(10, 0))
        tk.Label(title_row, text="📋 监控",
                 font=FONT_HEADING, fg=COLORS["text_title"],
                 bg=COLORS["sidebar_bg"]).pack(side=tk.LEFT)
        self._new_btn = tk.Label(title_row, text="+",
                                 font=FONT_HEADING,
                                 fg=COLORS["primary"],
                                 bg=COLORS["sidebar_bg"],
                                 cursor="hand2", padx=6)
        self._new_btn.pack(side=tk.RIGHT)
        self._new_btn.bind("<Button-1>",
                           lambda e: self._on_new_callback() if self._on_new_callback else None)

        tk.Frame(self, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=10, pady=(6, 4))

        # 任务列表（滚动）
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0,
                                 bg=COLORS["sidebar_bg"])
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10))

        self._inner = tk.Frame(self._canvas, bg=COLORS["sidebar_bg"])
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas_window = self._canvas.create_window((0, 0), window=self._inner, anchor=tk.NW)

        def _configure_width(event):
            self._canvas.itemconfig(self._canvas_window, width=max(event.width, 180))
        self._canvas.bind("<Configure>", _configure_width)

        # ═══ 底部：推送控制（单行紧凑） ═══
        push_bar = tk.Frame(self, bg=COLORS["sidebar_bg"])
        push_bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(push_bar, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=10)

        push_row = tk.Frame(push_bar, bg=COLORS["sidebar_bg"])
        push_row.pack(fill=tk.X, padx=10, pady=6)

        self._push_status_label = tk.Label(push_row, text="○",
                                           font=FONT_CAPTION,
                                           fg=COLORS["dot_off"],
                                           bg=COLORS["sidebar_bg"])
        self._push_status_label.pack(side=tk.LEFT, padx=(0, 4))

        self._push_status_text = tk.Label(push_row, text="推送已暂停",
                                          font=FONT_CAPTION,
                                          fg=COLORS["text_secondary"],
                                          bg=COLORS["sidebar_bg"])
        self._push_status_text.pack(side=tk.LEFT)

        self._push_toggle_btn = tk.Label(push_row, text="启动",
                                         font=FONT_CAPTION,
                                         fg=COLORS["primary"],
                                         bg=COLORS["sidebar_bg"],
                                         cursor="hand2", padx=6)
        self._push_toggle_btn.pack(side=tk.RIGHT)
        self._push_toggle_btn.bind("<Button-1>",
                                   lambda e: self._on_toggle_push() if self._on_toggle_push else None)

    # ═══ 对外接口 ═══

    def set_push_status(self, running, next_run_text=""):
        self._push_running = running
        if running:
            self._push_status_label.configure(text="●", fg=COLORS["success"])
            self._push_status_text.configure(text="推送运行中", fg=COLORS["success"])
            self._push_toggle_btn.configure(text="暂停", fg=COLORS["danger"])
        else:
            self._push_status_label.configure(text="○", fg=COLORS["dot_off"])
            self._push_status_text.configure(text="推送已暂停", fg=COLORS["text_secondary"])
            self._push_toggle_btn.configure(text="启动", fg=COLORS["primary"])

    def set_task_running(self, task_id):
        """标记正在检索的任务，重绘卡片运行状态"""
        self._running_task_id = task_id
        for tid, card in self._task_cards.items():
            card.set_running(tid == task_id)

    def clear_task_running(self):
        """清除所有任务的运行标记"""
        self._running_task_id = None
        for tid, card in self._task_cards.items():
            card.set_running(False)

    def refresh_tasks(self):
        for widget in self._inner.winfo_children():
            widget.destroy()
        self._task_cards.clear()
        self._task_order.clear()

        tasks = self._load_tasks()
        for i, (tid, t) in enumerate(tasks.items()):
            card = TaskCard(
                self._inner,
                task_id=tid,
                task_name=t["name"],
                enabled=t.get("enabled", True),
                running=(tid == self._running_task_id),
                selected=(tid == self._selected_task_id),
                on_click=self._on_card_click,
                on_rename=self._on_card_rename,
                on_context=self._on_card_context,
                on_search=self._on_card_search,
                on_delete=self._on_card_delete,
                on_copy=self._on_card_copy,
            )
            card.pack(fill=tk.X, pady=(0, 1))
            self._task_cards[tid] = card
            self._task_order.append(tid)

    def select_task(self, task_id):
        self._selected_task_id = task_id
        for tid, card in self._task_cards.items():
            card.set_selected(tid == task_id)

    def get_selected_task_id(self):
        return self._selected_task_id

    # ═══ 更多菜单回调 ═══

    def _on_card_search(self, task_id):
        if self._on_select:
            self._on_select(task_id)

    def _on_card_delete(self, task_id):
        if self._on_select:
            self._on_select(task_id)

    def _on_card_copy(self, task_id):
        task = self._get_task(task_id)
        if not task:
            return
        import uuid
        new_id = str(uuid.uuid4())[:8]
        new_task = dict(task, name=task["name"] + " (副本)")
        self._save_task(new_id, new_task)
        self.refresh_tasks()

    # ═══ 内部事件 ═══

    def _on_card_click(self, task_id):
        self.select_task(task_id)
        if self._on_select:
            self._on_select(task_id)

    def _on_card_rename(self, task_id):
        task = self._get_task(task_id)
        if not task:
            return
        new_name = simpledialog.askstring("重命名任务", "请输入新的任务名称：",
                                          initialvalue=task["name"])
        if new_name and new_name.strip():
            task["name"] = new_name.strip()
            self._save_task(task_id, task)
            self.refresh_tasks()

    def _on_card_context(self, task_id, event):
        task = self._get_task(task_id)
        if not task:
            return
        enabled = task.get("enabled", True)
        label = "禁用任务" if enabled else "启用任务"
        menu = tk.Menu(self, tearoff=0, font=FONT_BODY,
                       bg=COLORS["bg_card"], fg=COLORS["text_body"])
        menu.add_command(label=label,
                         command=lambda: self._toggle_enabled(task_id))
        menu.add_separator()
        menu.add_command(label="取消", command=lambda: None)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _toggle_enabled(self, task_id):
        task = self._get_task(task_id)
        if task:
            task["enabled"] = not task.get("enabled", True)
            save_task(task_id, task)
            self.refresh_tasks()
