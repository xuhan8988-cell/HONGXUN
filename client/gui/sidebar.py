"""
鸿讯 HONGXUN · 侧栏（v5 — 主导航 + 任务复合侧栏）
纵向圆角导航（概览/监控任务/文献书架/设置）+ 两行任务卡片 + 底部推送控制
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import sys
from gui.theme import COLORS, ICONS, RADIUS_SM, FONT_BODY, FONT_BODY_BOLD, FONT_CAPTION, FONT_HEADING
from gui.widgets import IconCache, ModernScrollbar, smooth_wheel_handler, IconButton


def _rounded_rect_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class NavItem(tk.Canvas):
    """侧栏导航项：Canvas 绘制圆角背景 + 图标 + 文字，支持选中/悬停态"""

    _ITEM_H = 40
    _RADIUS = 8
    _ACCENT_W = 3   # 选中态左侧主色竖条宽度

    def __init__(self, master, page, label, command=None, **kwargs):
        self._page = page
        self._label = label
        self._command = command
        self._height = self._ITEM_H
        self._active = False
        self._hover = False
        super().__init__(master, width=180, height=self._height,
                         borderwidth=0, highlightthickness=0,
                         bg=COLORS["sidebar_bg"], cursor="hand2", **kwargs)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Configure>", self._on_resize)
        self.bind("<Map>", self._on_map)
        # 延迟初始化：窗口未完成布局前 winfo_width/height 可能返回 1，
        # 首帧绘制会得到错误的坐标。等一帧再绘制，避免启动时乱码/重叠。
        self.after(30, self._redraw)

    def _redraw(self):
        self._draw(self._bg_for_state())

    def _bg_for_state(self):
        if self._active:
            return COLORS["nav_active_bg"]
        if self._hover:
            return COLORS["nav_hover_bg"]
        return COLORS["sidebar_bg"]

    def _on_map(self, event):
        self._redraw()

    def _on_resize(self, event):
        self._redraw()

    def _draw(self, bg):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 20:
            w = 180
        if h < 20:
            h = self._ITEM_H
        r = self._RADIUS
        self.create_polygon(_rounded_rect_points(0, 0, w, h, r),
                            smooth=True, fill=bg, outline="")
        # 选中态：左侧 3px 主色竖条（圆角内缩，视觉更精致）
        if self._active:
            bar = self._ACCENT_W
            self.create_rectangle(0, (h - 18) / 2, bar, (h + 18) / 2,
                                  fill=COLORS["primary"], outline="")
        # ref_formatter 无专属图标，用 edit（笔形，与"格式/编辑"语义匹配）
        icon_name = self._page
        if icon_name == "ref_formatter":
            icon_name = "edit"
        icon = IconCache.get(icon_name, 18, "default",
                             tint=COLORS["primary"] if self._active else None)
        if icon:
            self.create_image(19, h / 2, image=icon)
            self._icon_ref = icon
        else:
            self.create_text(19, h / 2, text=ICONS.get(self._page, ""),
                             font=FONT_CAPTION, anchor=tk.CENTER,
                             fill=COLORS["primary"] if self._active else COLORS["text_secondary"])
        fg = COLORS["primary"] if self._active else COLORS["text_secondary"]
        self.create_text(38, h / 2, text=self._label, font=FONT_BODY_BOLD,
                         fill=fg, anchor=tk.W)

    def set_active(self, active):
        self._active = active
        self._redraw()

    def _set_hover(self, hover):
        if self._active:
            self._hover = False
            return
        self._hover = hover
        self._redraw()

    def _on_click(self, event):
        if self._command:
            self._command(self._page)


# 任务彩色边条（5 色循环）
_TASK_ACCENTS = [COLORS["task_accent_1"], COLORS["task_accent_2"], COLORS["task_accent_3"],
                 COLORS["task_accent_4"], COLORS["task_accent_5"]]


class TaskCard(tk.Frame):
    """任务卡片：左侧彩色边条 + 两行信息（任务名 / 元数据）"""

    def __init__(self, master, task_id, task_name, enabled=True,
                 selected=False, running=False, on_click=None,
                 on_rename=None, on_context=None,
                 on_search=None, on_delete=None, on_copy=None,
                 meta_text="", **kwargs):
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
        self._meta_text = meta_text

        super().__init__(master, bg=COLORS["sidebar_bg"], cursor="hand2", **kwargs)
        self._build_card()
        self.bind("<Button-1>", self._handle_click)
        self.bind("<Double-1>", self._handle_rename)
        self.bind("<Button-3>", self._handle_context)

    def _build_card(self):
        bg = COLORS["selected_bg"] if self._selected else COLORS["sidebar_bg"]
        self.configure(bg=bg)
        for w in self.winfo_children():
            w.destroy()

        # 左侧 3px 彩色边条（语义化：运行=蓝，暂停=灰，出错=红；选中用主色）
        if self._selected:
            accent = COLORS["primary"]
        elif self._running:
            accent = COLORS["task_running"]
        elif self._enabled:
            accent = COLORS["task_running"]
        else:
            accent = COLORS["task_paused"]
        tk.Frame(self, bg=accent, width=3).pack(side=tk.LEFT, fill=tk.Y)

        row = tk.Frame(self, bg=bg)
        row.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 4), pady=(4, 1))

        # 第一行：运行点 + 任务名 + 「⋯」更多
        line1 = tk.Frame(row, bg=bg)
        line1.pack(fill=tk.X)

        if self._running:
            dot_color = COLORS["primary"]
            dot_text = "◉"
        elif self._enabled:
            dot_color = COLORS["dot_on"]
            dot_text = "●"
        else:
            dot_color = COLORS["dot_off"]
            dot_text = "●"
        tk.Label(line1, text=dot_text, font=FONT_CAPTION,
                 fg=dot_color, bg=bg).pack(side=tk.LEFT, padx=(0, 4))

        tk.Label(line1, text=self._task_name,
                 font=FONT_BODY_BOLD,
                 fg=COLORS["primary"] if self._enabled else COLORS["text_hint"],
                 bg=bg, anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._more_btn = tk.Label(line1, text="⋯", font=FONT_BODY_BOLD,
                                  fg=COLORS["text_secondary"], bg=bg, cursor="hand2",
                                  padx=6, pady=2, width=2)
        self._more_btn.pack(side=tk.RIGHT)
        self._more_btn.bind("<Button-1>", self._show_more_menu)
        self._more_btn.bind("<Enter>", lambda e: self._more_btn.configure(
            bg=COLORS["primary_light"], fg=COLORS["primary"]))
        self._more_btn.bind("<Leave>", lambda e: self._more_btn.configure(
            bg=bg, fg=COLORS["text_secondary"]))

        # 第二行：元数据（期刊数 · 关键词数）
        tk.Label(row, text=self._meta_text, font=FONT_CAPTION,
                 fg=COLORS["text_hint"], bg=bg, anchor=tk.W
                 ).pack(fill=tk.X, padx=(0, 8))

        for w in [row, line1] + list(row.winfo_children()):
            if w != self._more_btn:
                w.bind("<Button-1>", self._handle_click, add="+")

    def set_running(self, running):
        """外部设置运行状态，触发重绘"""
        self._running = running
        self._build_card()

    def set_selected(self, selected):
        self._selected = selected
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
    """侧栏：主导航区 + 任务列表 + 底部推送控制"""

    NAV_ITEMS = [
        ("dashboard", "概览"),
        ("monitor", "监控任务"),
        ("library", "文献书架"),
        ("ref_formatter", "格式助手"),
        ("settings", "设置"),
    ]

    def __init__(self, master, on_select=None, on_new=None,
                 on_toggle_push=None, on_nav=None, on_task_changed=None,
                 on_delete_task=None,
                 load_tasks_fn=None, get_task_fn=None,
                 save_task_fn=None, width=200, **kwargs):
        super().__init__(master, **kwargs)
        self._on_select = on_select
        self._on_new_callback = on_new
        self._on_toggle_push = on_toggle_push
        self._on_nav = on_nav or (lambda page: None)
        self._on_task_changed = on_task_changed or (lambda: None)
        self._on_delete_task = on_delete_task or (lambda task_id: None)
        self._load_tasks = load_tasks_fn or (lambda: {})
        self._get_task = get_task_fn or (lambda tid: None)
        self._save_task = save_task_fn or (lambda tid, task: None)
        self._selected_task_id = None
        self._task_cards = {}
        self._task_order = []
        self._push_running = False
        self._running_task_id = None
        self._current_page = "dashboard"

        self._build_ui()

    def _build_ui(self):
        self.configure(style="TFrame")

        # ═══ 顶部：主导航区（纵向，圆角选中态） ═══
        nav = tk.Frame(self, bg=COLORS["sidebar_bg"])
        nav.pack(fill=tk.X, padx=8, pady=(12, 8))
        self._nav_buttons = {}
        for page, label in self.NAV_ITEMS:
            item = NavItem(nav, page, label, command=self._navigate)
            item.pack(fill=tk.X, pady=2)
            self._nav_buttons[page] = item

        tk.Frame(self, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=10, pady=(4, 6))
        self._highlight_nav(self._current_page)

        # ═══ 监控标题行（分区：主导航 vs 我的任务） ═══
        title_row = tk.Frame(self, bg=COLORS["sidebar_bg"])
        title_row.pack(fill=tk.X, padx=10, pady=(2, 0))
        tk.Label(title_row, text="我的任务",
                 font=FONT_HEADING, fg=COLORS["text_title"],
                 bg=COLORS["sidebar_bg"]).pack(side=tk.LEFT)
        self._task_count_badge = tk.Label(title_row, text="",
                                          font=FONT_CAPTION, fg=COLORS["text_hint"],
                                          bg=COLORS["sidebar_bg"])
        self._task_count_badge.pack(side=tk.LEFT, padx=(4, 0), pady=(3, 0))
        self._new_btn = IconButton(title_row, icon="plus", command=self._on_new_task_click,
                                   size=28, bg_color=COLORS["sidebar_bg"], tooltip="新建任务")
        self._new_btn.pack(side=tk.RIGHT)

        tk.Frame(self, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=10, pady=(6, 4))

        # 任务列表（滚动）
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0,
                                 bg=COLORS["sidebar_bg"])
        scrollbar = ModernScrollbar(self, width=8, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10))

        self._inner = tk.Frame(self._canvas, bg=COLORS["sidebar_bg"])
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas_window = self._canvas.create_window((0, 0), window=self._inner, anchor=tk.NW)

        def _configure_width(event):
            self._canvas.itemconfig(self._canvas_window, width=max(event.width, 120))
        self._canvas.bind("<Configure>", _configure_width)

        # ── 滚轮滚动：平滑滚轮，进入侧栏时绑定，离开时解绑 ──
        _on_mousewheel, _bind_wheel, _unbind_wheel = smooth_wheel_handler(self._canvas)

        self._canvas.bind("<Enter>", _bind_wheel)
        self._canvas.bind("<Leave>", _unbind_wheel)

        # ═══ 底部：任务计数 + 推送控制 ═══
        summary_bar = tk.Frame(self, bg=COLORS["sidebar_bg"])
        summary_bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(summary_bar, bg=COLORS["border_light"], height=1).pack(fill=tk.X, padx=8)

        summary_inner = tk.Frame(summary_bar, bg=COLORS["sidebar_bg"])
        summary_inner.pack(fill=tk.X, padx=8, pady=6)

        self._task_count_label = tk.Label(summary_inner, text="0 个任务",
                                          font=FONT_CAPTION,
                                          fg=COLORS["text_secondary"],
                                          bg=COLORS["sidebar_bg"])
        self._task_count_label.pack(side=tk.LEFT)

        # 推送状态 + 启动按钮（紧凑）
        push_inner = tk.Frame(summary_bar, bg=COLORS["sidebar_bg"])
        push_inner.pack(fill=tk.X, padx=8, pady=(0, 8))

        self._push_status_dot = tk.Label(push_inner, text=ICONS["dot_off"],
                                         font=FONT_CAPTION, fg=COLORS["dot_off"],
                                         bg=COLORS["sidebar_bg"])
        self._push_status_dot.pack(side=tk.LEFT, padx=(0, 4))

        self._push_status_label = tk.Label(push_inner, text="推送未启动",
                                           font=FONT_CAPTION, fg=COLORS["text_secondary"],
                                           bg=COLORS["sidebar_bg"])
        self._push_status_label.pack(side=tk.LEFT)

        self._push_btn = tk.Label(push_inner, text=f"{ICONS['play']} 启动",
                                  font=FONT_BODY_BOLD, fg=COLORS["primary"],
                                  bg=COLORS["sidebar_bg"], cursor="hand2", padx=6)
        self._push_btn.pack(side=tk.RIGHT)
        self._push_btn.bind("<Button-1>",
                            lambda e: self._on_toggle_push() if self._on_toggle_push else None)

    # ═══ 导航 ═══

    def _navigate(self, page):
        self._current_page = page
        self._highlight_nav(page)
        self._on_nav(page)

    def _highlight_nav(self, page):
        for p, item in self._nav_buttons.items():
            item.set_active(p == page)

    def set_current_page(self, page):
        """外部同步当前页面"""
        self._current_page = page
        self._highlight_nav(page)

    # ═══ 对外接口 ═══

    def set_task_count(self, count, enabled_count=0):
        """底部摘要显示任务数，同时更新标题栏计数徽章"""
        self._task_count_label.configure(text=f"{count} 个任务")
        if hasattr(self, "_task_count_badge"):
            self._task_count_badge.configure(text=f"{count}" if count else "")

    def _on_new_task_click(self):
        if self._on_new_callback:
            self._on_new_callback()

    def set_push_status(self, running):
        """更新底部推送状态"""
        self._push_running = running
        if running:
            self._push_status_dot.configure(text=ICONS["dot_on"], fg=COLORS["success"])
            self._push_status_label.configure(text="推送运行中", fg=COLORS["success"])
            self._push_btn.configure(text=f"{ICONS['pause']} 暂停", fg=COLORS["warning"])
        else:
            self._push_status_dot.configure(text=ICONS["dot_off"], fg=COLORS["dot_off"])
            self._push_status_label.configure(text="推送未启动", fg=COLORS["text_secondary"])
            self._push_btn.configure(text=f"{ICONS['play']} 启动", fg=COLORS["primary"])

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
        # 过滤任务文件中的元数据键（_trial_mac 等），仅保留真正的任务 dict
        task_items = [(tid, t) for tid, t in tasks.items()
                      if not tid.startswith("_") and isinstance(t, dict)]
        for i, (tid, t) in enumerate(task_items):
            meta = self._format_meta(t)
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
                meta_text=meta,
            )
            card.pack(fill=tk.X, pady=(0, 3))
            self._task_cards[tid] = card
            self._task_order.append(tid)

    @staticmethod
    def _format_meta(task):
        journals = task.get("journals", []) or []
        keywords = task.get("keywords", []) or []
        n_j = len(journals)
        n_k = len(keywords)
        parts = []
        if n_j:
            parts.append(f"{n_j} 期刊")
        if n_k:
            parts.append(f"{n_k} 关键词")
        if not parts:
            return "待配置"
        return " · ".join(parts)

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
        if self._on_delete_task:
            self._on_delete_task(task_id)
        elif self._on_select:
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
        self._on_task_changed()

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
            self._on_task_changed()

    def _on_card_context(self, task_id, event):
        """点击「禁用/启用」直接切换，不再弹出二级子菜单。"""
        self._toggle_enabled(task_id)

    def _toggle_enabled(self, task_id):
        task = self._get_task(task_id)
        if task:
            task["enabled"] = not task.get("enabled", True)
            self._save_task(task_id, task)
            self.refresh_tasks()
            # 通知主程序刷新概览任务状态/侧栏计数（实时更新）
            self._on_task_changed()
