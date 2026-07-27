"""
鸿讯 HONGXUN · 侧栏（v2 — 紧凑版 + 每日推送底部集成）
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from gui.theme import COLORS, ICONS, FONT_BODY, FONT_BODY_BOLD, FONT_CAPTION, FONT_HEADING


class TaskCard(tk.Frame):
    """紧凑任务卡片（38px，点 + 名 + 状态标签，无 Canvas 边条）"""

    def __init__(self, master, task_id, task_name, enabled=True,
                 selected=False, on_click=None,
                 on_rename=None, on_context=None, **kwargs):
        self._task_id = task_id
        self._task_name = task_name
        self._enabled = enabled
        self._selected = selected
        self._on_click = on_click
        self._on_rename = on_rename
        self._on_context = on_context

        super().__init__(master, bg=COLORS["sidebar_bg"], cursor="hand2", **kwargs)
        self._build_card()
        self.bind("<Button-1>", self._handle_click)
        self.bind("<Double-1>", self._handle_rename)
        self.bind("<Button-3>", self._handle_context)

    def _build_card(self):
        bg = COLORS["selected_bg"] if self._selected else COLORS["sidebar_bg"]
        self.configure(bg=bg)

        # 左侧 3px 蓝色边条（选中时显示）
        if self._selected:
            accent_bar = tk.Frame(self, bg=COLORS["primary"], width=3)
            accent_bar.pack(side=tk.LEFT, fill=tk.Y)

        # 行容器
        row = tk.Frame(self, bg=bg)
        row.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6), pady=6)

        # 状态点 + 任务名（左）
        dot_color = COLORS["dot_on"] if self._enabled else COLORS["dot_off"]
        tk.Label(row, text="●", font=FONT_CAPTION,
                 fg=dot_color, bg=bg).pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(row, text=self._task_name,
                 font=FONT_BODY_BOLD,
                 fg=COLORS["text_title"] if self._enabled else COLORS["text_hint"],
                 bg=bg, anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 状态标签（右）
        status_text = "运行中" if self._enabled else "禁用"
        status_color = COLORS["success"] if self._enabled else COLORS["text_hint"]
        tk.Label(row, text=status_text,
                 font=FONT_CAPTION,
                 fg=status_color,
                 bg=bg).pack(side=tk.RIGHT, padx=(4, 0))

        # 事件转发
        for w in [row] + row.winfo_children():
            w.bind("<Button-1>", self._handle_click, add="+")

    def set_selected(self, selected):
        """重绘卡片——选中时加蓝色边条"""
        self._selected = selected
        for w in self.winfo_children():
            w.destroy()
        self._build_card()

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
    """侧栏：任务列表面板 + 底部推送控制"""

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

        self._build_ui()

    def _build_ui(self):
        self.configure(style="TFrame")

        # ═══ 标题行 ═══
        title_row = tk.Frame(self, bg=COLORS["sidebar_bg"])
        title_row.pack(fill=tk.X, padx=10, pady=(12, 0))
        tk.Label(title_row, text="📋 监控任务",
                 font=FONT_HEADING, fg=COLORS["text_title"],
                 bg=COLORS["sidebar_bg"]).pack(side=tk.LEFT)
        self._new_btn = tk.Label(title_row,
                                 text="+",
                                 font=FONT_HEADING,
                                 fg=COLORS["primary"],
                                 bg=COLORS["sidebar_bg"],
                                 cursor="hand2",
                                 padx=6)
        self._new_btn.pack(side=tk.RIGHT)
        self._new_btn.bind("<Button-1>",
                           lambda e: self._on_new_callback() if self._on_new_callback else None)

        tk.Frame(self, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=10, pady=(8, 4))

        # ═══ 任务列表（滚动） ═══
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

        # ═══ 底部：每日推送控制 ═══
        push_section = tk.Frame(self, bg=COLORS["sidebar_bg"])
        push_section.pack(fill=tk.X, side=tk.BOTTOM, padx=0, pady=0)

        tk.Frame(push_section, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=10)

        push_inner = tk.Frame(push_section, bg=COLORS["sidebar_bg"])
        push_inner.pack(fill=tk.X, padx=10, pady=(8, 10))

        # 标题行
        push_title_row = tk.Frame(push_inner, bg=COLORS["sidebar_bg"])
        push_title_row.pack(fill=tk.X)
        tk.Label(push_title_row, text="📧 每日推送",
                 font=FONT_HEADING, fg=COLORS["text_title"],
                 bg=COLORS["sidebar_bg"]).pack(side=tk.LEFT)

        # 状态 + 操作行
        push_action_row = tk.Frame(push_inner, bg=COLORS["sidebar_bg"])
        push_action_row.pack(fill=tk.X, pady=(4, 0))

        self._push_status_label = tk.Label(push_action_row,
                                           text="○ 已暂停",
                                           font=FONT_BODY_BOLD,
                                           fg=COLORS["text_secondary"],
                                           bg=COLORS["sidebar_bg"])
        self._push_status_label.pack(side=tk.LEFT)

        self._push_toggle_btn = tk.Label(push_action_row,
                                         text="启动",
                                         font=FONT_BODY_BOLD,
                                         fg=COLORS["primary"],
                                         bg=COLORS["sidebar_bg"],
                                         cursor="hand2",
                                         padx=10, pady=2)
        self._push_toggle_btn.pack(side=tk.RIGHT)
        self._push_toggle_btn.bind("<Button-1>",
                                   lambda e: self._on_toggle_push() if self._on_toggle_push else None)
        self._push_toggle_btn.bind("<Enter>",
                                   lambda e: self._push_toggle_btn.configure(fg=COLORS["primary_hover"]))
        self._push_toggle_btn.bind("<Leave>",
                                   lambda e: self._push_toggle_btn.configure(fg=COLORS["primary"]
                                   if not self._push_running else COLORS["danger"]))

        # 下次执行时间
        self._next_run_label = tk.Label(push_inner,
                                        text="下次：--",
                                        font=FONT_CAPTION,
                                        fg=COLORS["text_hint"],
                                        bg=COLORS["sidebar_bg"],
                                        anchor=tk.W)
        self._next_run_label.pack(fill=tk.X)

    # ═══ 对外接口 ═══

    def set_push_status(self, running, next_run_text=""):
        """更新推送状态显示"""
        self._push_running = running
        if running:
            self._push_status_label.configure(text="● 运行中", fg=COLORS["success"])
            self._push_toggle_btn.configure(text="暂停", fg=COLORS["danger"])
        else:
            self._push_status_label.configure(text="○ 已暂停", fg=COLORS["text_secondary"])
            self._push_toggle_btn.configure(text="启动", fg=COLORS["primary"])
        self._next_run_label.configure(text=f"下次：{next_run_text}" if next_run_text else "下次：--")

    def set_next_run(self, next_run_str):
        self._next_run_label.configure(text=f"下次：{next_run_str}")

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
                selected=(tid == self._selected_task_id),
                on_click=self._on_card_click,
                on_rename=self._on_card_rename,
                on_context=self._on_card_context,
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
