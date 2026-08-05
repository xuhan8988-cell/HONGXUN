"""
鸿讯 HONGXUN · 期刊详情弹窗
版本 1.0.0

展示期刊的完整信息：核心指标卡（IF / 中科院分区 / TOP / H指数）、
基本信息、投稿经验、相似期刊推荐，以及收藏 / 添加操作。
打开即记录浏览历史，用于智能推荐。
"""

import tkinter as tk
from tkinter import ttk

from gui.theme import COLORS, FONT_BODY, FONT_BODY_BOLD, FONT_CAPTION, FONT_HEADING, FONT_METRIC, FONT_TITLE
from gui.widgets import ModernButton, RoundedCard, EmptyState, ModernScrollbar

_DIVISION_COLORS = {1: "#EF4444", 2: "#F59E0B", 3: "#10B981", 4: "#64748B"}


class JournalDetailDialog(tk.Toplevel):
    """期刊详情弹窗。"""

    def __init__(self, master, journal: dict, store,
                 on_add=None, on_favorite=None):
        super().__init__(master)
        self.title(journal.get("full_name") or "期刊详情")
        self.geometry("560x640")
        self.minsize(480, 520)
        self.resizable(False, True)
        self.configure(bg=COLORS["bg_page"])
        self.transient(master)
        self.grab_set()

        self.journal = journal
        self.store = store
        self.on_add = on_add
        self.on_favorite = on_favorite

        # 记录浏览历史（用于智能推荐）
        jid = journal.get("jid")
        if jid:
            try:
                store.record_view(jid)
            except Exception:
                pass

        self._build_ui()
        self._place_center()

    # ── 布局 ──────────────────────────────────────────────
    def _place_center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - w) // 2, max((sh - h) // 2 - 40, 40)
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # 滚动容器
        outer = tk.Frame(self, bg=COLORS["bg_page"])
        outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=(16, 8))
        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0,
                           bg=COLORS["bg_page"])
        vsb = ModernScrollbar(outer, width=8, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._body = tk.Frame(canvas, bg=COLORS["bg_page"])
        self._win = canvas.create_window((0, 0), window=self._body, anchor=tk.NW)
        self._body.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(self._win, width=e.width))
        self._bind_mousewheel(canvas, self._body)

        # 标题区
        self._build_header()

        # 核心指标卡
        self._build_metrics()

        # 基本信息
        self._build_section("基本信息", [
            ("出版社", self.journal.get("publisher") or "—"),
            ("国家/地区", self.journal.get("country") or "—"),
            ("ISSN", self.journal.get("issn") or "—"),
            ("eISSN", self.journal.get("eissn") or "—"),
            ("学科领域", self._category_text()),
            ("是否 OA", "是" if self.journal.get("is_oa") else "否"),
        ])

        # 投稿经验
        self._build_section("投稿经验", [
            ("审稿周期", self.journal.get("review_cycle") or "—"),
            ("录用比例", self.journal.get("acceptance_rate") or "—"),
        ])

        # 相似期刊推荐
        self._build_recommendations()

        # 底部操作按钮
        self._build_actions()

    def _bind_mousewheel(self, canvas, body):
        def _wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")
        for w in (canvas, body):
            w.bind("<MouseWheel>", _wheel, add="+")

    # ── 各区块 ────────────────────────────────────────────
    def _build_header(self):
        header = tk.Frame(self._body, bg=COLORS["bg_page"])
        header.pack(fill=tk.X, pady=(0, 10))

        name = self.journal.get("full_name") or ""
        tk.Label(header, text=name, font=FONT_TITLE,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"],
                 wraplength=500, justify=tk.LEFT).pack(anchor=tk.W)

        abbr = self.journal.get("abbreviation") or ""
        cn = self.journal.get("full_name_cn") or ""
        sub = []
        if cn:
            sub.append(cn)
        if abbr:
            sub.append(f"缩写：{abbr}")
        if sub:
            tk.Label(header, text=" · ".join(sub), font=FONT_BODY,
                     fg=COLORS["text_secondary"], bg=COLORS["bg_page"]).pack(
                anchor=tk.W, pady=(4, 0))

    def _build_metrics(self):
        j = self.journal
        metrics_frame = tk.Frame(self._body, bg=COLORS["bg_page"])
        metrics_frame.pack(fill=tk.X, pady=(0, 10))

        division = j.get("cas_division_2024") or 0
        div_label = {1: "1区", 2: "2区", 3: "3区", 4: "4区"}.get(division, "—")
        div_color = _DIVISION_COLORS.get(division, COLORS["text_hint"])

        metric_data = [
            (f"{j.get('impact_factor_2025') or 0:.1f}", "影响因子", COLORS["primary"]),
            (div_label, "中科院分区", div_color),
            ("TOP" if j.get("is_top") else "—", "TOP期刊",
             COLORS["success"] if j.get("is_top") else COLORS["text_hint"]),
            (str(j.get("h_index") or 0), "H指数", COLORS["text_secondary"]),
        ]

        for i, (value, label, color) in enumerate(metric_data):
            card = RoundedCard(metrics_frame, radius=10, pad=0, shadow=True,
                               bg_color=COLORS["bg_card"], fit_content=True)
            card.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6) if i < 3 else (0, 0))
            inner = tk.Frame(card.content, bg=COLORS["bg_card"])
            inner.pack(fill=tk.X, pady=10, padx=4)
            tk.Label(inner, text=value, font=FONT_METRIC,
                     fg=color, bg=COLORS["bg_card"]).pack()
            tk.Label(inner, text=label, font=FONT_CAPTION,
                     fg=COLORS["text_hint"], bg=COLORS["bg_card"]).pack()

    def _build_section(self, title: str, items: list[tuple[str, str]]):
        card = RoundedCard(self._body, radius=12, pad=0, shadow=True,
                           bg_color=COLORS["bg_card"], fit_content=True)
        card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(card.content, text=title, font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]).pack(
            anchor=tk.W, padx=14, pady=(12, 4))
        tk.Frame(card.content, bg=COLORS["border_light"], height=1).pack(
            fill=tk.X, padx=14, pady=(0, 6))

        inner = tk.Frame(card.content, bg=COLORS["bg_card"])
        inner.pack(fill=tk.X, padx=14, pady=(0, 10))

        for label, value in items:
            row = tk.Frame(inner, bg=COLORS["bg_card"])
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=label, font=FONT_BODY,
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                     width=12, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row, text=value, font=FONT_BODY,
                     fg=COLORS["text_body"], bg=COLORS["bg_card"],
                     wraplength=360, justify=tk.LEFT).pack(side=tk.LEFT)

    def _category_text(self) -> str:
        cat = self.journal.get("category") or ""
        sub = self.journal.get("subcategory") or ""
        if cat and sub:
            return f"{cat} / {sub}"
        return cat or "—"

    def _build_recommendations(self):
        card = RoundedCard(self._body, radius=12, pad=0, shadow=True,
                           bg_color=COLORS["bg_card"], fit_content=True)
        card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(card.content, text="相似期刊推荐", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_card"]).pack(
            anchor=tk.W, padx=14, pady=(12, 4))
        tk.Frame(card.content, bg=COLORS["border_light"], height=1).pack(
            fill=tk.X, padx=14, pady=(0, 6))

        inner = tk.Frame(card.content, bg=COLORS["bg_card"])
        inner.pack(fill=tk.X, padx=14, pady=(0, 12))

        try:
            recs = self.store.recommended(limit=4)
        except Exception:
            recs = []

        if not recs:
            EmptyState(inner, icon="search", title="暂无推荐",
                       subtitle="浏览更多期刊后可获取相似推荐").pack(pady=12)
            return

        # 排除当前期刊本身
        jid = self.journal.get("jid")
        recs = [r for r in recs if r.get("jid") != jid][:4]

        for rec in recs:
            row = tk.Frame(inner, bg=COLORS["bg_card"])
            row.pack(fill=tk.X, pady=2)
            name_label = tk.Label(row, text=rec.get("full_name", ""),
                                  font=FONT_BODY_BOLD,
                                  fg=COLORS["primary"], bg=COLORS["bg_card"],
                                  cursor="hand2")
            name_label.pack(side=tk.LEFT)
            d = rec.get("cas_division_2024") or 0
            div = {1: "1区", 2: "2区", 3: "3区", 4: "4区"}.get(d, "")
            tag = f"  {div}" if div else ""
            if rec.get("is_top"):
                tag += " TOP"
            tag += f"  IF {rec.get('impact_factor_2025') or 0:.1f}"
            tk.Label(row, text=tag, font=FONT_CAPTION,
                     fg=COLORS["text_hint"], bg=COLORS["bg_card"]).pack(
                side=tk.LEFT, padx=(8, 0))
            name_label.bind("<Button-1>",
                            lambda e, r=rec: self._open_recommended(r))

    def _open_recommended(self, rec):
        # 点击相似期刊 → 关闭当前，打开新的详情
        new_journal = self.store.get_by_id(rec.get("jid"))
        if not new_journal:
            return
        self.destroy()
        JournalDetailDialog(self.master, new_journal, self.store,
                            on_add=self.on_add, on_favorite=self.on_favorite)

    # ── 底部操作 ──────────────────────────────────────────
    def _build_actions(self):
        btn_frame = tk.Frame(self._body, bg=COLORS["bg_page"])
        btn_frame.pack(fill=tk.X, pady=(4, 14))

        jid = self.journal.get("jid")
        is_fav = jid and self.store.is_favorite(jid)

        fav_btn = ModernButton(btn_frame, text="⭐ 已收藏" if is_fav else "☆ 收藏",
                               variant="secondary", command=self._toggle_favorite)
        fav_btn.pack(side=tk.LEFT)

        ModernButton(btn_frame, text="+ 添加到任务", variant="primary",
                     command=self._on_add_click).pack(side=tk.RIGHT)

    def _toggle_favorite(self):
        jid = self.journal.get("jid")
        if not jid:
            return
        if self.store.is_favorite(jid):
            self.store.remove_favorite(jid)
        else:
            self.store.add_favorite(jid)
        if self.on_favorite:
            try:
                self.on_favorite(self.journal)
            except Exception:
                pass
        # 重建底部按钮刷新状态
        self._body.winfo_children()[-1].destroy()
        self._build_actions()

    def _on_add_click(self):
        if self.on_add:
            try:
                self.on_add(self.journal)
            except Exception:
                pass
        self.destroy()
