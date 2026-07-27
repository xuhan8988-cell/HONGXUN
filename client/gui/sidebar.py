"""
鸿讯 HONGXUN · 侧栏任务列表
卡片式任务列表替代原生 Listbox
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from gui.theme import COLORS, ICONS, FONT_BODY, FONT_BODY_BOLD, FONT_CAPTION, FONT_HEADING


TASK_ACCENTS = [
    COLORS["task_accent_1"],
    COLORS["task_accent_2"],
    COLORS["task_accent_3"],
    COLORS["task_accent_4"],
    COLORS["task_accent_5"],
]


class TaskCard(tk.Frame):
    """任务卡片组件"""

    def __init__(self, master, task_id, task_name, enabled=True,
                 accent_index=0, selected=False, on_click=None,
                 on_rename=None, on_context=None, **kwargs):
        self._task_id = task_id
        self._task_name = task_name
        self._enabled = enabled
        self._selected = selected
        self._on_click = on_click
        self._on_rename = on_rename
        self._on_context = on_context

        super().__init__(master, bg=COLORS["bg_page"], cursor="hand2", **kwargs)
        self._build_card(accent_index)

        self.bind("<Button-1>", self._handle_click)
        self.bind("<Double-1>", self._handle_rename)
        self.bind("<Button-3>", self._handle_context)

    def _build_card(self, accent_index):
        accent = TASK_ACCENTS[accent_index % len(TASK_ACCENTS)] if self._enabled else COLORS["text_hint"]
        bg = COLORS["selected_bg"] if self._selected else COLORS["bg_page"]

        self.configure(bg=bg)

        # 左侧彩色边条 — Canvas 绘制圆角矩形
        c = tk.Canvas(self, width=5, height=56, borderwidth=0,
                      highlightthickness=0, bg=bg)
        c.pack(side=tk.LEFT, fill=tk.Y)
        r = 2
        pts = [r, 0, 5, 0, 5, 56, r, 56, 0, 56, 0, 0]
        c.create_polygon(pts, smooth=True, fill=accent, outline="")

        # 右侧内容
        content = tk.Frame(self, bg=bg)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 8), pady=6)

        # 任务名
        tk.Label(content, text=self._task_name,
                 font=FONT_BODY_BOLD,
                 fg=COLORS["text_title"] if self._enabled else COLORS["text_hint"],
                 bg=bg, anchor=tk.W).pack(fill=tk.X)

        # 状态行
        status_text = "● 运行中" if self._enabled else "○ 已禁用"
        status_color = COLORS["dot_on"] if self._enabled else COLORS["dot_off"]
        tk.Label(content, text=status_text,
                 font=FONT_CAPTION,
                 fg=status_color,
                 bg=bg, anchor=tk.W).pack(fill=tk.X)

        # 隔开点击区覆盖整个卡片
        for w in [content] + content.winfo_children():
            w.bind("<Button-1>", self._handle_click, add="+")

    def set_selected(self, selected):
        self._selected = selected
        bg = COLORS["selected_bg"] if selected else COLORS["bg_page"]
        self.configure(bg=bg)
        for child in self.winfo_children():
            try:
                child.configure(bg=bg)
            except Exception:
                pass
            try:
                for sub in child.winfo_children():
                    sub.configure(bg=bg)
            except Exception:
                pass

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
    """卡片式任务侧栏"""

    def __init__(self, master, on_select=None, on_new=None,
                 load_tasks_fn=None, get_task_fn=None,
                 save_task_fn=None, width=260, **kwargs):
        super().__init__(master, **kwargs)
        self._on_select = on_select
        self._on_new_callback = on_new
        self._load_tasks = load_tasks_fn or (lambda: {})
        self._get_task = get_task_fn or (lambda tid: None)
        self._save_task = save_task_fn or (lambda tid, task: None)
        self._selected_task_id = None
        self._task_cards = {}  # task_id -> TaskCard
        self._task_order = []  # ordered list of task_ids

        self._build_ui()

    def _build_ui(self):
        # 侧栏背景
        self.configure(style="TFrame")

        # 标题行
        title_row = tk.Frame(self, bg=COLORS["sidebar_bg"])
        title_row.pack(fill=tk.X, padx=12, pady=(16, 0))

        tk.Label(title_row, text="📋 监控任务",
                 font=FONT_HEADING, fg=COLORS["text_title"],
                 bg=COLORS["sidebar_bg"]).pack(side=tk.LEFT)

        self._new_btn = tk.Label(title_row,
                                 text=ICONS["plus"],
                                 font=("PingFang SC", 20, "bold"),
                                 fg=COLORS["primary"],
                                 bg=COLORS["sidebar_bg"],
                                 cursor="hand2",
                                 padx=6)
        self._new_btn.pack(side=tk.RIGHT)
        self._new_btn.bind("<Button-1>", lambda e: self._on_new_callback() if self._on_new_callback else None)

        tk.Frame(self, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=12, pady=(8, 6))

        # Canvas 滚动区域
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0,
                                 bg=COLORS["sidebar_bg"])
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)

        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 12))

        self._inner = tk.Frame(self._canvas, bg=COLORS["sidebar_bg"])
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas_window = self._canvas.create_window((0, 0), window=self._inner,
                                                          anchor=tk.NW)

        def _configure_width(event):
            self._canvas.itemconfig(self._canvas_window, width=max(event.width, 240))
        self._canvas.bind("<Configure>", _configure_width)

        # 推送状态卡
        push_card = tk.Frame(self, bg=COLORS["bg_card"],
                             highlightbackground=COLORS["border_light"],
                             highlightthickness=1)
        push_card.pack(fill=tk.X, padx=12, pady=(6, 12))

        self._push_label = tk.Label(push_card,
                                    text=f"{ICONS['dot_off']} 每日推送未启动",
                                    font=FONT_CAPTION,
                                    fg=COLORS["text_secondary"],
                                    bg=COLORS["bg_card"],
                                    anchor=tk.W, padx=12, pady=8)
        self._push_label.pack(fill=tk.X)

    def set_push_status(self, running, next_run_text=""):
        if running:
            icon = ICONS["dot_on"]
            color = COLORS["dot_on"]
            text = f"{icon} 每日推送运行中"
            if next_run_text:
                text += f" | {next_run_text}"
        else:
            icon = ICONS["dot_off"]
            color = COLORS["dot_off"]
            text = f"{icon} 每日推送未启动"
        self._push_label.configure(text=text, fg=color)

    def refresh_tasks(self):
        """从数据源加载并重建所有卡片"""
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
                accent_index=i,
                selected=(tid == self._selected_task_id),
                on_click=self._on_card_click,
                on_rename=self._on_card_rename,
                on_context=self._on_card_context,
            )
            card.pack(fill=tk.X, pady=(0, 4))
            self._task_cards[tid] = card
            self._task_order.append(tid)

    def select_task(self, task_id):
        """选中一个任务，取消其他选中"""
        self._selected_task_id = task_id
        for tid, card in self._task_cards.items():
            card.set_selected(tid == task_id)

    def get_selected_task_id(self):
        return self._selected_task_id

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
        """右键菜单：启用/禁用"""
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
