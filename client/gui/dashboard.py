"""
鸿讯 HONGXUN · 概览仪表盘（Tab 0 首页）
统计卡片 + 最近文献 + 任务状态 + 快捷操作
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
import sys

from gui.theme import COLORS, ICONS, FONT_BODY, FONT_BODY_BOLD, FONT_HEADING, FONT_TITLE, FONT_CAPTION, FONT_LABEL, FONT_METRIC, FONT_DISPLAY, lerp_color
from gui.widgets import RoundedCard, ModernButton, StatusPill, IconCache, ModernScrollbar
from core.library import load_library, get_stats, get_all_task_names
from core import load_all_tasks, load_push_records


def _rounded_rect(x1, y1, x2, y2, r):
    """圆角矩形坐标点列表（供 Canvas create_polygon smooth 使用）"""
    return [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def _next_push_str(now: datetime = None) -> tuple:
    """下次每日推送日期与时间，返回 (日期, 时间)。时间从 app_config 读取，默认 08:00。"""
    now = now or datetime.now()
    try:
        from core.config_manager import load_app_config
        push_time = load_app_config().get("push_time", "08:00")
        hh, mm = (str(push_time).split(":") + ["00", "00"])[:2]
        hh, mm = int(hh), int(mm)
    except Exception:
        hh, mm = 8, 0
    today = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < today:
        nxt = today
    else:
        nxt = today + timedelta(days=1)
    return nxt.strftime("%m-%d"), nxt.strftime("%H:%M")


class StatCard(RoundedCard):
    """概览统计卡片：白色卡片 + 36px 实心主题色图标 + 16pt 深灰数字，简洁不截断"""

    def __init__(self, master, icon="", label="", value="", accent=COLORS["primary"],
                 trend="", trend_up=True, **kwargs):
        self._accent = accent
        self._icon_name = icon
        self._label_text = label
        self._value_text = value

        super().__init__(master, radius=14, pad=12, hover_elevate=True,  # pad 16→12
                         fit_content=False, height=72, **kwargs)  # 固定高度 72px
        self._build_ui()

    def _build_ui(self):
        for w in self.content.winfo_children():
            w.destroy()
        card_bg = COLORS["bg_card"]

        # 顶部行：图标块 + 文字
        top_row = tk.Frame(self.content, bg=card_bg)
        top_row.pack(fill=tk.X)

        # 40x40 实心主题色圆角图标块 + 白色图标（更精致、图标更清晰）
        icon_bg = tk.Frame(top_row, bg=card_bg)
        icon_bg.pack(side=tk.LEFT)
        self._icon_canvas = tk.Canvas(icon_bg, width=40, height=40,
                                      borderwidth=0, highlightthickness=0, bg=card_bg)
        self._icon_canvas.pack()
        self._icon_canvas.create_polygon(
            self._rounded_pts(1, 1, 39, 39, 10), smooth=True,
            fill=self._accent, outline="")
        icon_img = IconCache.get(self._icon_name, 24, "default", tint="#FFFFFF")
        if icon_img:
            self._icon_canvas.create_image(20, 20, image=icon_img)
            self._icon_ref = icon_img
        else:
            self._icon_canvas.create_text(20, 20,
                                          text=ICONS.get(self._icon_name, ""),
                                          font=FONT_HEADING, fill="#FFFFFF")

        # 文字列：15pt 加粗深灰数字 + 11pt 中灰标签（单行不换行）
        text_col = tk.Frame(top_row, bg=card_bg)
        text_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 0))
        self._value_label = tk.Label(text_col, text=self._value_text,
                                     font=FONT_HEADING, fg=COLORS["text_title"],
                                     bg=card_bg, anchor=tk.W)
        self._value_label.pack(fill=tk.X)
        self._sub_label = tk.Label(text_col, text="", font=FONT_CAPTION,
                                   fg=COLORS["text_hint"], bg=card_bg, anchor=tk.W)
        self._label_label = tk.Label(text_col, text=self._label_text,
                                     font=FONT_CAPTION, fg=COLORS["text_secondary"],
                                     bg=card_bg, anchor=tk.W)
        self._label_label.pack(fill=tk.X, pady=(2, 0))

    def set_value(self, value, trend=None, trend_up=True, sub_value=None):
        self._value_text = value
        self._value_label.configure(text=self._value_text)
        if sub_value is not None:
            self._sub_label.configure(text=sub_value)
            self._sub_label.pack(fill=tk.X)
        else:
            self._sub_label.pack_forget()

    @staticmethod
    def _rounded_pts(x1, y1, x2, y2, r):
        """生成圆角矩形 polygon 顶点。"""
        return [
            x1 + r, y1, x2 - r, y1, x2, y1,
            x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2,
            x1, y2 - r, x1, y1 + r, x1, y1,
        ]


class DashboardView(ttk.Frame):
    """概览首页：统计卡片 + 最近文献 + 任务状态 + 快捷操作"""

    def __init__(self, master, on_new_task=None, on_run_search=None,
                 on_open_library=None, on_export=None, on_coupon=None,
                 on_subscribe=None, **kwargs):
        super().__init__(master, **kwargs)
        self._on_new_task = on_new_task or (lambda: None)
        self._on_run_search = on_run_search or (lambda: None)
        self._on_open_library = on_open_library or (lambda: None)
        self._on_export = on_export or (lambda: None)
        self._on_coupon = on_coupon or (lambda: None)
        self._on_subscribe = on_subscribe or (lambda: None)
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # 可滚动容器
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0,
                                 bg=COLORS["bg_page"])
        vs = ModernScrollbar(self, width=8, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vs.set)
        self._canvas.grid(row=0, column=0, sticky=tk.NSEW)
        vs.grid(row=0, column=1, sticky=tk.NS)

        inner = tk.Frame(self._canvas, bg=COLORS["bg_page"])
        inner.bind("<Configure>",
                   lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._win = self._canvas.create_window((0, 0), window=inner, anchor=tk.NW)

        # ── 滚轮滚动：鼠标进入时绑定，离开时解绑（避免与侧栏冲突） ──
        def _on_mousewheel(event):
            if event.num == 4:
                self._canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self._canvas.yview_scroll(1, "units")
            elif event.delta:
                delta = event.delta if sys.platform == "darwin" else event.delta / 120
                self._canvas.yview_scroll(int(-delta), "units")
            return "break"

        def _bind_wheel(_e):
            self._canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")
            self._canvas.bind_all("<Button-4>", _on_mousewheel, add="+")
            self._canvas.bind_all("<Button-5>", _on_mousewheel, add="+")

        def _unbind_wheel(_e):
            self._canvas.unbind_all("<MouseWheel>")
            self._canvas.unbind_all("<Button-4>")
            self._canvas.unbind_all("<Button-5>")

        self._canvas.bind("<Enter>", _bind_wheel)
        self._canvas.bind("<Leave>", _unbind_wheel)

        def _cw(event):
            self._canvas.itemconfig(self._win, width=event.width)
        self._canvas.bind("<Configure>", _cw)

        # ── 标题行：标题(24pt 加粗深灰) + 副标题 + 快捷操作(右对齐) ──
        header = tk.Frame(inner, bg=COLORS["bg_page"])
        header.pack(fill=tk.X, padx=24, pady=(20, 16))

        left = tk.Frame(header, bg=COLORS["bg_page"])
        left.pack(side=tk.LEFT)
        self._title_label = tk.Label(left, text="概览", font=FONT_DISPLAY,
                                     fg=COLORS["text_title"], bg=COLORS["bg_page"])
        self._title_label.pack(anchor=tk.W)
        self._subtitle_label = tk.Label(left, text="", font=FONT_CAPTION,
                                        fg=COLORS["text_secondary"], bg=COLORS["bg_page"])
        self._subtitle_label.pack(anchor=tk.W, pady=(4, 0))

        # 激活状态 + 礼品券入口
        self._license_label = tk.Label(left, text="", font=FONT_CAPTION,
                                       fg=COLORS["text_hint"], bg=COLORS["bg_page"],
                                       cursor="hand2")
        self._license_label.pack(anchor=tk.W, pady=(4, 0))
        self._license_label.bind("<Button-1>", lambda e: self._on_coupon())

        actions = tk.Frame(header, bg=COLORS["bg_page"])
        actions.pack(side=tk.RIGHT)
        ModernButton(actions, text="＋ 新建任务", command=self._on_new_task,
                     variant="primary").pack(side=tk.LEFT, padx=(0, 8))
        ModernButton(actions, text="▶ 执行检索", command=self._on_run_search,
                     variant="secondary").pack(side=tk.LEFT, padx=(0, 8))
        ModernButton(actions, text="导出书架", command=self._on_export,
                     variant="secondary").pack(side=tk.LEFT, padx=(0, 8))
        self._coupon_btn = ModernButton(actions, text="🎟 礼品券",
                                        command=self._on_coupon,
                                        variant="secondary")
        self._coupon_btn.pack(side=tk.LEFT)
        self._subscribe_btn = ModernButton(actions, text="💳 订阅",
                                           command=self._on_subscribe,
                                           variant="secondary")
        self._subscribe_btn.pack(side=tk.LEFT, padx=(8, 0))

        # ── 4 个统计卡 ──
        self._stats_row = tk.Frame(inner, bg=COLORS["bg_page"])
        self._stats_row.pack(fill=tk.X, padx=24, pady=(0, 8))
        for i in range(4):
            self._stats_row.columnconfigure(i, weight=1, uniform="stat")

        self._stat_cards = []
        # 每个卡片：(图标, 标签, 初始值, 主题色 500 色阶)
        specs = [
            # 蓝色系：总文献数
            ("journal", "总文献数", "0", "#3B82F6"),
            # 紫色系：本周新增
            ("plus", "本周新增", "0", "#8B5CF6"),
            # 绿色系：已读率
            ("check", "已读率", "0%", "#10B981"),
            # 橙色系：下次推送
            ("clock", "下次推送", "--", "#F59E0B"),
        ]
        for i, (icon, label, value, accent) in enumerate(specs):
            card = StatCard(self._stats_row, icon=icon, label=label, value=value,
                            accent=accent)
            card.grid(row=0, column=i, sticky=tk.NSEW,
                      padx=(0 if i == 0 else 16, 16 if i < 3 else 0))
            self._stat_cards.append(card)

        # ── 下排：最近文献 + 任务状态 ──
        self._bottom_row = tk.Frame(inner, bg=COLORS["bg_page"])
        self._bottom_row.pack(fill=tk.BOTH, expand=True, padx=24, pady=(20, 24))
        self._bottom_row.columnconfigure(0, weight=3)
        self._bottom_row.columnconfigure(1, weight=2)

        # 左：最近文献
        recent_card = RoundedCard(self._bottom_row, radius=12, pad=14, fit_content=True)
        recent_card.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 16))
        tk.Label(recent_card.content, text="最近文献", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]).pack(anchor=tk.W, pady=(0, 8))
        self._recent_frame = tk.Frame(recent_card.content, bg=COLORS["bg_card"])
        self._recent_frame.pack(fill=tk.BOTH, expand=True)
        self._recent_rows = []

        # 右：任务状态
        task_card = RoundedCard(self._bottom_row, radius=12, pad=14, fit_content=True)
        task_card.grid(row=0, column=1, sticky=tk.NSEW, padx=(16, 0))
        tk.Label(task_card.content, text="任务状态", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]).pack(anchor=tk.W, pady=(0, 8))
        self._task_frame = tk.Frame(task_card.content, bg=COLORS["bg_card"])
        self._task_frame.pack(fill=tk.BOTH, expand=True)
        self._task_rows = []
        tk.Frame(task_card.content, bg=COLORS["border_light"], height=1).pack(fill=tk.X, pady=(10, 8))
        self._push_total_label = tk.Label(task_card.content, text="累计推送 0 篇",
                                          font=FONT_CAPTION, fg=COLORS["text_hint"],
                                          bg=COLORS["bg_card"], anchor=tk.W)
        self._push_total_label.pack(fill=tk.X)

        # 底部留白：避免最后一个元素贴边
        tk.Frame(inner, bg=COLORS["bg_page"], height=20).pack(fill=tk.X)

        self._inner = inner

    # ═══ 数据刷新 ═══

    def refresh_license(self):
        """更新激活状态与礼品券入口显示。
        激活后入口变「已激活」不可点；未激活/失效时恢复可点击。"""
        try:
            from core import coupon_manager
        except Exception:
            return
        activated = coupon_manager.is_activated()
        try:
            if activated:
                self._license_label.configure(
                    text=f"{ICONS['check']} 服务已激活（永久）", fg=COLORS["success"],
                    cursor="arrow")
                self._coupon_btn.set_text("✓ 已激活")
                self._coupon_btn.configure(state="disabled")
            else:
                # 试用期
                try:
                    in_trial, remain = coupon_manager.is_trial_period()
                except Exception:
                    in_trial, remain = False, 0
                if in_trial:
                    self._license_label.configure(
                        text=f"{ICONS['check']} 试用期剩余 {remain} 天", fg=COLORS["warning"],
                        cursor="hand2")
                else:
                    self._license_label.configure(
                        text=f"{ICONS['warning']} 服务未激活，点击兑换礼品券", fg=COLORS["warning"],
                        cursor="hand2")
                self._coupon_btn.set_text("🎟 礼品券")
                self._coupon_btn.configure(state="normal")
        except Exception:
            pass

    def refresh(self):
        self._subtitle_label.configure(text=self._greeting())
        self.refresh_license()

        stats = get_stats()
        total = stats["total"]
        read = stats["read"]
        read_rate = int(read / total * 100) if total else 0

        lib = load_library()
        papers = lib.get("papers", [])
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        week_new = sum(1 for p in papers if (p.get("added_date") or "") >= week_ago)

        self._stat_cards[0].set_value(f"{total}", trend=f"{len(papers)} 篇文献")
        self._stat_cards[1].set_value(f"+{week_new}", trend="本周收录")
        self._stat_cards[2].set_value(f"{read_rate}%", trend=f"已读 {read} 篇")
        push_date, push_time = _next_push_str()
        self._stat_cards[3].set_value(push_date, trend="每日推送", sub_value=push_time)

        # 最近文献（最多 6 篇）
        for w in self._recent_frame.winfo_children():
            w.destroy()
        self._recent_rows.clear()
        recent = papers[:6]
        if not recent:
            tk.Label(self._recent_frame, text="暂无文献，点击「执行检索」开始收集",
                     font=FONT_CAPTION, fg=COLORS["text_hint"],
                     bg=COLORS["bg_card"]).pack(anchor=tk.W, pady=6)
        else:
            for p in recent:
                row = tk.Frame(self._recent_frame, bg=COLORS["bg_card"], cursor="hand2")
                row.pack(fill=tk.X, pady=2)
                # 两行布局：标题 + 期刊/时间
                title = (p.get("title") or "").strip()
                journal = (p.get("container_title") or "").strip()
                status = p.get("status", "pending")
                pill = StatusPill(row, status=status)
                pill.pack(side=tk.RIGHT, padx=(8, 0))

                text_col = tk.Frame(row, bg=COLORS["bg_card"])
                text_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
                tk.Label(text_col, text=title, font=FONT_BODY_BOLD,
                         fg=COLORS["text_title"], bg=COLORS["bg_card"],
                         anchor=tk.W, justify=tk.LEFT).pack(fill=tk.X)
                meta_parts = []
                if journal:
                    meta_parts.append(journal)
                if p.get("pub_date"):
                    meta_parts.append(str(p["pub_date"]))
                meta_text = " · ".join(meta_parts) if meta_parts else ""
                tk.Label(text_col, text=meta_text, font=FONT_CAPTION,
                         fg=COLORS["text_hint"], bg=COLORS["bg_card"],
                         anchor=tk.W).pack(fill=tk.X, pady=(1, 0))

                def _on_row_enter(e, r=row):
                    r.configure(bg=COLORS["hover_bg"])
                    for w in r.winfo_children():
                        if isinstance(w, tk.Frame):
                            for c in w.winfo_children():
                                c.configure(bg=COLORS["hover_bg"])
                        else:
                            w.configure(bg=COLORS["hover_bg"])
                def _on_row_leave(e, r=row):
                    r.configure(bg=COLORS["bg_card"])
                    for w in r.winfo_children():
                        if isinstance(w, tk.Frame):
                            for c in w.winfo_children():
                                c.configure(bg=COLORS["bg_card"])
                        else:
                            w.configure(bg=COLORS["bg_card"])
                for w in [row, text_col, pill] + text_col.winfo_children():
                    w.bind("<Button-1>", lambda e: self._on_open_library())
                    w.bind("<Enter>", _on_row_enter)
                    w.bind("<Leave>", _on_row_leave)

        # 任务状态
        for w in self._task_frame.winfo_children():
            w.destroy()
        self._task_rows.clear()
        tasks = load_all_tasks()
        # 过滤任务文件中的元数据键（_trial_mac 等），仅保留真正的任务 dict
        task_items = [(tid, t) for tid, t in tasks.items()
                      if not tid.startswith("_") and isinstance(t, dict)]
        if not task_items:
            tk.Label(self._task_frame, text="还没有监控任务",
                     font=FONT_CAPTION, fg=COLORS["text_hint"],
                     bg=COLORS["bg_card"]).pack(anchor=tk.W, pady=6)
        else:
            for tid, t in task_items[:8]:
                row = tk.Frame(self._task_frame, bg=COLORS["bg_card"], cursor="hand2")
                row.pack(fill=tk.X, pady=4)
                enabled = t.get("enabled", True)
                dot_color = COLORS["dot_on"] if enabled else COLORS["dot_off"]
                tk.Label(row, text=ICONS["dot_on"], font=FONT_CAPTION,
                         fg=dot_color, bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(0, 6))
                tk.Label(row, text=t.get("name", ""), font=FONT_BODY_BOLD,
                         fg=COLORS["text_title"] if enabled else COLORS["text_hint"],
                         bg=COLORS["bg_card"], anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)
                state = "运行中" if enabled else "已禁用"
                tk.Label(row, text=state, font=FONT_CAPTION,
                         fg=COLORS["success"] if enabled else COLORS["text_hint"],
                         bg=COLORS["bg_card"]).pack(side=tk.RIGHT)

        # 累计推送
        records = load_push_records()
        total_dois = set()
        for dois in records.values():
            total_dois.update(dois)
        self._push_total_label.configure(text=f"累计推送 {len(total_dois)} 篇")

    @staticmethod
    def _greeting():
        h = datetime.now().hour
        if h < 6:
            g = "夜深了"
        elif h < 12:
            g = "早上好"
        elif h < 18:
            g = "下午好"
        else:
            g = "晚上好"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"{g}，现在是 {now}"