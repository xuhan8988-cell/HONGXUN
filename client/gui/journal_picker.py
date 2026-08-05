"""
鸿讯 HONGXUN · 智能期刊选择器（分类树版）
版本 2.0.0

布局：
  左侧 240px 分类树（大类 → 小类 → 分区三级，可滚动，顶部搜索）
  右侧 期刊列表（面包屑导航 + 表头 + 期刊行 + 底部状态栏）
  底部 已选期刊 pill 标签区（名× 移除 + 数量限制 1≤n≤10）

交互：
  - 点击大类/小类节点展开/收起；点击分区节点在右侧显示期刊
  - 每行期刊：复选框选中作任务 + 行尾 ☆收藏 / 详情
  - 全选/取消全选当前节点；底部已选标签可点 × 移除
  - 搜索：左侧顶部输入 300ms 防抖，右侧切搜索结果视图
"""

import tkinter as tk
from tkinter import ttk
import re
import sys

from gui.theme import COLORS, FONT_BODY, FONT_BODY_BOLD, FONT_CAPTION, FONT_HEADING
from gui.widgets import ModernButton, ModernEntry, EmptyState, ModernScrollbar

MAX_SELECT = 10
MIN_SELECT = 1

_DIVISION_COLORS = {1: "#EF4444", 2: "#F59E0B", 3: "#10B981", 4: "#64748B"}


class CategoryTree(tk.Frame):
    """左侧三级分类树：大类 → 小类 → 分区，Canvas 滚动 + 自定义节点。"""

    def __init__(self, master, store, on_select_node=None, on_search=None,
                 bg=COLORS["bg_card"]):
        super().__init__(master, bg=bg)
        self.store = store
        self._on_select_node = on_select_node or (lambda category, subcat, division: None)
        self._on_search = on_search or (lambda kw: None)

        # 搜索框
        search_row = tk.Frame(self, bg=bg)
        search_row.pack(fill=tk.X, padx=10, pady=(10, 6))
        self._search_entry = ModernEntry(search_row, placeholder="搜索期刊名称…", width=18)
        self._search_entry.pack(fill=tk.X)
        self._search_entry.entry.bind("<KeyRelease>", self._on_search_key)
        self._search_after = None

        # 树容器
        canvas_frame = tk.Frame(self, bg=bg)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=(6, 2), pady=(0, 8))
        self._canvas = tk.Canvas(canvas_frame, borderwidth=0, highlightthickness=0, bg=bg)
        vsb = ModernScrollbar(canvas_frame, width=8, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._body = tk.Frame(self._canvas, bg=bg)
        self._win = self._canvas.create_window((0, 0), window=self._body, anchor=tk.NW)
        self._body.bind(
            "<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>", lambda e: self._canvas.itemconfig(self._win, width=e.width))
        def _on_mousewheel(e):
            if e.num == 4:
                self._canvas.yview_scroll(-1, "units")
            elif e.num == 5:
                self._canvas.yview_scroll(1, "units")
            elif e.delta:
                delta = e.delta if sys.platform == "darwin" else e.delta / 120
                self._canvas.yview_scroll(int(-delta), "units")
            return "break"
        self._canvas.bind("<MouseWheel>", _on_mousewheel, add="+")
        self._canvas.bind("<Button-4>", _on_mousewheel, add="+")
        self._canvas.bind("<Button-5>", _on_mousewheel, add="+")

        self._expanded_cats = set()
        self._expanded_subs = set()
        self._selected_node = None  # (category, subcat, division)

        self._load_tree()

    # ── 搜索 ─────────────────────────────────────────────
    def _on_search_key(self, event=None):
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(300, self._fire_search)

    def _fire_search(self):
        kw = self._search_entry.get().strip()
        self._on_search(kw)

    def get_keyword(self) -> str:
        return self._search_entry.get().strip()

    # ── 树加载 ───────────────────────────────────────────
    def _load_tree(self):
        for w in self._body.winfo_children():
            w.destroy()
        try:
            tree = self.store.get_category_tree()
        except Exception as e:
            print(f"[journal_picker] 加载分类树失败: {e}", flush=True)
            tree = []
        self._tree = tree
        self._render()

    def refresh(self):
        self._load_tree()

    def _render(self):
        for w in self._body.winfo_children():
            w.destroy()
        if not self._tree:
            EmptyState(self._body, icon="search", title="暂无分类",
                       subtitle="期刊库为空").pack(pady=30)
            return
        for cat in self._tree:
            self._render_cat(cat)

    def _render_cat(self, cat):
        cat_key = cat["name"]
        expanded = cat_key in self._expanded_cats

        row = tk.Frame(self._body, bg=COLORS["bg_card"])
        row.pack(fill=tk.X, pady=1)
        arrow = "▾" if expanded else "▸"
        btn = tk.Label(row, text=f"{arrow}  {cat['name']}", font=FONT_BODY,
                       fg=COLORS["text_body"], bg=COLORS["bg_card"], anchor=tk.W,
                       padx=8, pady=5, cursor="hand2")
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        cnt = tk.Label(row, text=str(cat["count"]), font=FONT_CAPTION,
                       fg=COLORS["text_hint"], bg=COLORS["bg_card"])
        cnt.pack(side=tk.RIGHT, padx=(0, 10))
        btn.bind("<Button-1>", lambda e, k=cat_key: self._toggle_cat(k))

        if expanded:
            for sub in cat["children"]:
                self._render_sub(cat_key, sub)

    def _render_sub(self, cat_key, sub):
        sub_key = sub["name"]
        sub_id = (cat_key, sub_key)
        expanded = sub_id in self._expanded_subs

        row = tk.Frame(self._body, bg=COLORS["bg_card"])
        row.pack(fill=tk.X, pady=1)
        arrow = "▾" if expanded else "▸"
        btn = tk.Label(row, text=f"    {arrow}  {sub['name']}", font=FONT_BODY,
                       fg=COLORS["text_secondary"], bg=COLORS["bg_card"], anchor=tk.W,
                       padx=8, pady=4, cursor="hand2")
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        cnt = tk.Label(row, text=str(sub["count"]), font=FONT_CAPTION,
                       fg=COLORS["text_hint"], bg=COLORS["bg_card"])
        cnt.pack(side=tk.RIGHT, padx=(0, 10))
        btn.bind("<Button-1>", lambda e: self._toggle_sub(cat_key, sub_key))

        if expanded:
            for div_node in sub["children"]:
                self._render_division(cat_key, sub_key, div_node)

    def _render_division(self, cat_key, sub_key, div_node):
        row = tk.Frame(self._body, bg=COLORS["bg_card"])
        row.pack(fill=tk.X, pady=1)
        node_key = (cat_key, sub_key, div_node["division"])
        is_sel = (self._selected_node == node_key)
        bg = COLORS["primary_light"] if is_sel else COLORS["bg_card"]
        fg = COLORS["primary"] if is_sel else COLORS["text_secondary"]
        btn = tk.Label(row, text=f"        {div_node['name']}", font=FONT_CAPTION,
                       fg=fg, bg=bg, anchor=tk.W, padx=8, pady=4, cursor="hand2")
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        cnt = tk.Label(row, text=str(div_node["count"]), font=FONT_CAPTION,
                       fg=COLORS["text_hint"], bg=bg)
        cnt.pack(side=tk.RIGHT, padx=(0, 10))
        btn.bind("<Button-1>",
                 lambda e: self._select_node(cat_key, sub_key, div_node["division"]))

    # ── 交互 ─────────────────────────────────────────────
    def _toggle_cat(self, cat_key):
        if cat_key in self._expanded_cats:
            self._expanded_cats.discard(cat_key)
        else:
            self._expanded_cats.add(cat_key)
        self._render()

    def _toggle_sub(self, cat_key, sub_key):
        sub_id = (cat_key, sub_key)
        if sub_id in self._expanded_subs:
            self._expanded_subs.discard(sub_id)
        else:
            self._expanded_subs.add(sub_id)
        self._render()

    def _select_node(self, cat_key, sub_key, division):
        self._selected_node = (cat_key, sub_key, division)
        self._render()
        self._on_select_node(cat_key, sub_key, division)


class JournalRowList(tk.Frame):
    """右侧期刊列表：面包屑 + 表头 + 期刊行 + 底部状态栏。"""

    def __init__(self, master, store, get_selected_ids, on_toggle,
                 on_favorite_changed, on_show_detail, bg=COLORS["bg_card"]):
        super().__init__(master, bg=bg)
        self.store = store
        self._get_selected_ids = get_selected_ids
        self._on_toggle = on_toggle
        self._on_favorite_changed = on_favorite_changed
        self._on_show_detail = on_show_detail

        # 面包屑
        self._crumb = tk.Label(self, text="", font=FONT_CAPTION,
                               fg=COLORS["text_secondary"], bg=bg, anchor=tk.W)
        self._crumb.pack(fill=tk.X, padx=12, pady=(10, 6))

        # 表头
        header = tk.Frame(self, bg=COLORS["border_light"])
        header.pack(fill=tk.X)
        for text, wpx in (("", 40), ("期刊名称", 260), ("IF", 60), ("TOP", 45), ("收藏", 45), ("操作", 60)):
            tk.Label(header, text=text, font=FONT_CAPTION,
                     fg=COLORS["text_secondary"], bg=COLORS["border_light"],
                     width=max(wpx // 8, 4), anchor=tk.W).pack(side=tk.LEFT, padx=4, pady=6)

        # 列表（滚动）
        list_frame = tk.Frame(self, bg=bg)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self._canvas = tk.Canvas(list_frame, borderwidth=0, highlightthickness=0, bg=bg)
        vsb = ModernScrollbar(list_frame, width=8, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._body = tk.Frame(self._canvas, bg=bg)
        self._win = self._canvas.create_window((0, 0), window=self._body, anchor=tk.NW)
        self._body.bind(
            "<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>", lambda e: self._canvas.itemconfig(self._win, width=e.width))
        def _on_mousewheel(e):
            if e.num == 4:
                self._canvas.yview_scroll(-1, "units")
            elif e.num == 5:
                self._canvas.yview_scroll(1, "units")
            elif e.delta:
                delta = e.delta if sys.platform == "darwin" else e.delta / 120
                self._canvas.yview_scroll(int(-delta), "units")
            return "break"
        self._canvas.bind("<MouseWheel>", _on_mousewheel, add="+")
        self._canvas.bind("<Button-4>", _on_mousewheel, add="+")
        self._canvas.bind("<Button-5>", _on_mousewheel, add="+")

        # 底部状态栏
        status = tk.Frame(self, bg=bg)
        status.pack(fill=tk.X, padx=12, pady=(6, 8))
        self._status_label = tk.Label(status, text="", font=FONT_CAPTION,
                                      fg=COLORS["text_hint"], bg=bg)
        self._status_label.pack(side=tk.LEFT)
        self._select_all_btn = tk.Label(status, text="全选", font=FONT_CAPTION,
                                        fg=COLORS["primary"], bg=bg, cursor="hand2",
                                        padx=8)
        self._select_all_btn.pack(side=tk.RIGHT)
        self._select_all_btn.bind("<Button-1>", lambda e: self._on_select_all())

        self._current_journals = []
        self._current_path = []

    # ── 数据渲染 ─────────────────────────────────────────
    def show_node(self, category, subcat, division):
        """按分类节点显示期刊。"""
        self._current_path = [category, subcat,
                              {1: "1区", 2: "2区", 3: "3区", 4: "4区"}.get(division, "")]
        self._crumb.configure(text="当前位置： " + " > ".join(self._current_path))
        try:
            journals = self.store.get_journals_by_node(category, subcat, division, limit=500)
        except Exception as e:
            print(f"[journal_picker] 加载期刊失败: {e}", flush=True)
            journals = []
        self._current_journals = journals
        self._render_rows()
        self._update_status()

    def show_search_results(self, keyword: str):
        """按关键词搜索显示结果。"""
        self._current_path = [f"搜索: {keyword}"]
        self._crumb.configure(text=f"搜索结果： “{keyword}”")
        try:
            journals = self.store.search_journals(keyword, limit=100)
        except Exception as e:
            print(f"[journal_picker] 搜索失败: {e}", flush=True)
            journals = []
        self._current_journals = journals
        self._render_rows()
        self._update_status()

    def _render_rows(self):
        for w in self._body.winfo_children():
            w.destroy()
        if not self._current_journals:
            EmptyState(self._body, icon="search", title="该分类暂无期刊",
                       subtitle="试试其他分类或搜索").pack(pady=40)
            return
        for j in self._current_journals:
            self._render_row(j)

    def _render_row(self, j: dict):
        item = tk.Frame(self._body, bg=COLORS["bg_card"])
        item.pack(fill=tk.X, pady=1)
        jid = j.get("jid")

        # hover
        def _enter(_e):
            item.configure(bg=COLORS["hover_bg"])
            for w in item.winfo_children():
                if isinstance(w, (tk.Frame, tk.Label)):
                    w.configure(bg=COLORS["hover_bg"])
        def _leave(_e):
            item.configure(bg=COLORS["bg_card"])
            for w in item.winfo_children():
                if isinstance(w, (tk.Frame, tk.Label)):
                    w.configure(bg=COLORS["bg_card"])
        item.bind("<Enter>", _enter)
        item.bind("<Leave>", _leave)

        # 复选框
        var = tk.BooleanVar(value=jid in self._get_selected_ids())
        var.trace_add("write", lambda *_: self._on_toggle(jid, var.get()))
        tk.Checkbutton(item, variable=var, bg=COLORS["bg_card"],
                       activebackground=COLORS["bg_card"],
                       selectcolor=COLORS["bg_page"]).pack(side=tk.LEFT, padx=8, pady=8)

        # 期刊名（全称 + 缩写两行，长名自动换行统一高度）
        name_col = tk.Frame(item, bg=COLORS["bg_card"])
        name_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=6)
        tk.Label(name_col, text=j.get("full_name", ""), font=FONT_BODY_BOLD,
                 fg=COLORS["text_body"], bg=COLORS["bg_card"], anchor=tk.W,
                 wraplength=240, justify=tk.LEFT).pack(fill=tk.X)
        abbr = j.get("abbreviation") or ""
        if abbr:
            tk.Label(name_col, text=abbr, font=FONT_CAPTION,
                     fg=COLORS["text_hint"], bg=COLORS["bg_card"], anchor=tk.W,
                     wraplength=240, justify=tk.LEFT).pack(fill=tk.X)

        # IF
        ifi = j.get("impact_factor_2025") or 0
        tk.Label(item, text=f"{ifi:.1f}", font=FONT_BODY_BOLD,
                 fg=COLORS["primary"] if ifi >= 10 else COLORS["text_secondary"],
                 bg=COLORS["bg_card"], width=8).pack(side=tk.LEFT, padx=4, pady=8)

        # TOP（是则该区 Top 期刊，显示醒目标记）
        top_text = "TOP" if j.get("is_top") else ""
        tk.Label(item, text=top_text, font=FONT_CAPTION,
                 fg=COLORS["success"] if j.get("is_top") else COLORS["bg_card"],
                 bg=COLORS["bg_card"], width=5).pack(side=tk.LEFT, padx=4, pady=8)

        # 收藏星（独立列，始终显示 ★/☆）
        fav_text = "★" if self._is_fav(jid) else "☆"
        fav = tk.Label(item, text=fav_text, font=FONT_HEADING,
                       fg=COLORS["warning"] if self._is_fav(jid) else COLORS["text_hint"],
                       bg=COLORS["bg_card"], cursor="hand2", padx=4, width=2)
        fav.pack(side=tk.LEFT, padx=4, pady=8)
        fav.bind("<Button-1>", lambda e, jj=j: self._toggle_fav(jj))

        # 操作：详情
        ops = tk.Frame(item, bg=COLORS["bg_card"])
        ops.pack(side=tk.RIGHT, padx=8, pady=8)
        detail = tk.Label(ops, text="详情", font=FONT_CAPTION,
                          fg=COLORS["primary"], bg=COLORS["primary_light"],
                          padx=8, pady=2, cursor="hand2")
        detail.pack(side=tk.LEFT)
        detail.bind("<Button-1>", lambda e, jj=j: self._on_show_detail(jj))

    def _is_fav(self, jid: int) -> bool:
        try:
            return self.store.is_favorite(jid)
        except Exception:
            return False

    def _toggle_fav(self, j: dict):
        jid = j.get("jid")
        if not jid:
            return
        try:
            if self.store.is_favorite(jid):
                self.store.remove_favorite(jid)
            else:
                self.store.add_favorite(jid)
        except Exception:
            pass
        if self._on_favorite_changed:
            self._on_favorite_changed()
        self._render_rows()

    def _update_status(self):
        total = len(self._current_journals)
        selected = len(self._get_selected_ids())
        self._status_label.configure(
            text=f"共 {total} 本 | 已选 {selected} 本")

    def _on_select_all(self):
        ids = [j.get("jid") for j in self._current_journals if j.get("jid")]
        self._on_toggle(ids, None)  # 批量切换

    def refresh_checks(self):
        """外部选中变化后刷新复选框状态。"""
        self._render_rows()


class JournalPickerDialog(tk.Toplevel):
    """智能期刊选择器（分类树版）。"""

    def __init__(self, master, store, selected=None,
                 max_selected=MAX_SELECT, on_confirm=None):
        super().__init__(master)
        self.title("选择期刊")
        self.geometry("900x680")
        self.minsize(760, 560)
        self.configure(bg=COLORS["bg_page"])
        self.transient(master)
        self.grab_set()

        self.store = store
        self.store.ensure_db()
        self.on_confirm = on_confirm
        self._max_selected = max_selected

        # 已选期刊：保持 id 集合 + 名→dict 映射（selected 传期刊名 list）
        self._selected_ids = set()
        self._selected_map = {}  # jid -> dict
        self._manual_seq = 0  # 手动输入期刊的合成键计数（key: "manual:N"）
        for name in (selected or []):
            j = store.get_by_name(name, fuzzy=False)
            if j:
                self._selected_ids.add(j["jid"])
                self._selected_map[j["jid"]] = j
            else:
                # 库外期刊（手动输入过、任务还原而来）用合成键保留
                self._manual_seq += 1
                key = f"manual:{self._manual_seq}"
                self._selected_ids.add(key)
                self._selected_map[key] = {"full_name": name}

        self._build_ui()
        self._place_center()
        # 默认展开第一个大类，选中其首个分区
        self._default_select()

    def _place_center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - w) // 2, max((sh - h) // 2 - 30, 30)
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # 标题栏
        header = tk.Frame(self, bg=COLORS["bg_page"])
        header.pack(fill=tk.X, padx=16, pady=(14, 8))
        tk.Label(header, text="选择期刊", font=FONT_HEADING,
                 fg=COLORS["text_title"], bg=COLORS["bg_page"]).pack(side=tk.LEFT)

        # 左右分栏
        main = tk.Frame(self, bg=COLORS["bg_page"])
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        main.columnconfigure(1, weight=1)

        # 左：分类树（240px）
        left_card = tk.Frame(main, bg=COLORS["bg_card"], highlightthickness=1,
                             highlightbackground=COLORS["border_light"])
        left_card.grid(row=0, column=0, sticky=tk.NS, padx=(0, 12))
        left_card.configure(width=240)
        left_card.pack_propagate(False)
        self._tree = CategoryTree(left_card, self.store,
                                  on_select_node=self._on_node_select,
                                  on_search=self._on_tree_search)
        self._tree.pack(fill=tk.BOTH, expand=True)

        # 右：期刊列表
        self._list = JournalRowList(main, self.store,
                                    get_selected_ids=lambda: self._selected_ids,
                                    on_toggle=self._on_toggle,
                                    on_favorite_changed=lambda: None,
                                    on_show_detail=self._show_detail)
        self._list.grid(row=0, column=1, sticky=tk.NSEW)

        # 底部已选区 + 按钮
        self._build_bottom()

        self._update_selected_display()

    def _default_select(self):
        """默认全部折叠：不展开任何一级栏目，由用户自行选择。"""
        pass

    # ── 分类树回调 ───────────────────────────────────────
    def _on_node_select(self, category, subcat, division):
        self._list.show_node(category, subcat, division)

    def _on_tree_search(self, keyword):
        if keyword:
            self._list.show_search_results(keyword)
        else:
            # 恢复分类视图：重新触发当前节点
            if self._tree._selected_node:
                c, s, d = self._tree._selected_node
                self._list.show_node(c, s, d)

    # ── 选中管理 ─────────────────────────────────────────
    def _on_toggle(self, jid, checked):
        """切换期刊选中。jid 为 int 时 toggle 单个；为 list 时批量。"""
        if isinstance(jid, (list, tuple)):
            ids = [j for j in jid if j]
            all_selected = all(i in self._selected_ids for i in ids)
            if all_selected:
                for i in ids:
                    self._selected_ids.discard(i)
                    self._selected_map.pop(i, None)
            else:
                room = self._max_selected - len(self._selected_ids)
                for i in ids:
                    if i not in self._selected_ids and room > 0:
                        self._selected_ids.add(i)
                        j = self.store.get_by_id(i)
                        if j:
                            self._selected_map[i] = j
                        room -= 1
            self._list.refresh_checks()
            self._update_selected_display()
            return

        if checked:
            if jid not in self._selected_ids:
                if len(self._selected_ids) >= self._max_selected:
                    return  # 已达上限
                self._selected_ids.add(jid)
                j = self.store.get_by_id(jid)
                if j:
                    self._selected_map[jid] = j
        else:
            self._selected_ids.discard(jid)
            self._selected_map.pop(jid, None)
        self._list.refresh_checks()
        self._update_selected_display()

    def _show_detail(self, j: dict):
        from gui.journal_detail import JournalDetailDialog
        full = self.store.get_by_id(j.get("jid"))
        if not full:
            return
        JournalDetailDialog(self, full, self.store,
                            on_add=self._add_from_detail,
                            on_favorite=self._on_fav_changed)

    def _add_from_detail(self, j: dict):
        jid = j.get("jid")
        if jid and jid not in self._selected_ids:
            if len(self._selected_ids) >= self._max_selected:
                return
            self._selected_ids.add(jid)
            self._selected_map[jid] = j
            self._list.refresh_checks()
            self._update_selected_display()

    def _on_fav_changed(self):
        self._list.refresh_checks()

    # ── 底部已选区 ───────────────────────────────────────
    def _build_bottom(self):
        bottom = tk.Frame(self, bg=COLORS["bg_page"])
        bottom.pack(fill=tk.X, side=tk.BOTTOM, padx=16, pady=12)

        self._sel_header = tk.Frame(bottom, bg=COLORS["bg_page"])
        self._sel_header.pack(fill=tk.X)
        tk.Label(self._sel_header, text="已选期刊:", font=FONT_BODY,
                 fg=COLORS["text_secondary"], bg=COLORS["bg_page"]).pack(side=tk.LEFT)
        self._sel_count_label = tk.Label(self._sel_header, text="",
                                         font=FONT_CAPTION, fg=COLORS["text_hint"],
                                         bg=COLORS["bg_page"])
        self._sel_count_label.pack(side=tk.LEFT, padx=(8, 0))

        self._sel_frame = tk.Frame(bottom, bg=COLORS["bg_page"])
        self._sel_frame.pack(fill=tk.X, pady=6)

        self._hint_label = tk.Label(bottom, text="", font=FONT_CAPTION,
                                    fg=COLORS["text_hint"], bg=COLORS["bg_page"])
        self._hint_label.pack(side=tk.LEFT)

        btn_frame = tk.Frame(bottom, bg=COLORS["bg_page"])
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        ModernButton(btn_frame, text="📥 批量导入", variant="secondary",
                     command=self._open_import).pack(side=tk.LEFT, padx=(0, 8))
        ModernButton(btn_frame, text="✍️ 手动输入", variant="secondary",
                     command=self._open_manual_input).pack(side=tk.LEFT)
        ModernButton(btn_frame, text="取消", variant="secondary",
                     command=self.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        self._confirm_btn = ModernButton(btn_frame, text="确认选择", variant="primary",
                                         command=self._on_confirm)
        self._confirm_btn.pack(side=tk.RIGHT)

    def _update_selected_display(self):
        for w in self._sel_frame.winfo_children():
            w.destroy()

        n = len(self._selected_ids)
        self._sel_count_label.configure(text=f"{n}/{self._max_selected}")

        if not self._selected_ids:
            tk.Label(self._sel_frame, text="尚未选择期刊", font=FONT_CAPTION,
                     fg=COLORS["text_hint"], bg=COLORS["bg_page"]).pack(anchor=tk.W)
        else:
            for jid, j in self._selected_map.items():
                name = j.get("full_name", "")
                tag = tk.Label(self._sel_frame,
                               text=f"{name[:16]}{'…' if len(name) > 16 else ''} ×",
                               font=FONT_CAPTION, fg=COLORS["primary"],
                               bg=COLORS["primary_light"], padx=8, pady=3, cursor="hand2")
                tag.pack(side=tk.LEFT, padx=3, pady=2)
                tag.bind("<Button-1>", lambda e, i=jid: self._remove_selected(i))

        if n == 0:
            self._hint_label.configure(text="请至少选择 1 本期刊", fg=COLORS["text_hint"])
            self._confirm_btn.configure(state="disabled")
        elif n > self._max_selected:
            self._hint_label.configure(text=f"最多选择 {self._max_selected} 本，当前 {n} 本",
                                       fg=COLORS["danger"])
            self._confirm_btn.configure(state="disabled")
        else:
            self._hint_label.configure(text=f"✓ 已选 {n} 本", fg=COLORS["success"])
            self._confirm_btn.configure(state="normal")

    def _remove_selected(self, jid: int):
        self._selected_ids.discard(jid)
        self._selected_map.pop(jid, None)
        self._list.refresh_checks()
        self._update_selected_display()

    # ── 批量导入 ─────────────────────────────────────────
    def _open_import(self):
        from gui.journal_import import JournalImportDialog
        JournalImportDialog(self, self.store, on_import=self._on_import)

    def _on_import(self, journals: list[dict]):
        for j in journals:
            jid = j.get("jid")
            if jid and jid not in self._selected_ids:
                if len(self._selected_ids) >= self._max_selected:
                    break
                self._selected_ids.add(jid)
                self._selected_map[jid] = j
        self._list.refresh_checks()
        self._update_selected_display()

    # ── 手动输入 ─────────────────────────────────────────
    def _open_manual_input(self):
        """弹出输入框，手动添加数据库未收录的期刊（可多本，分号/换行分隔）。"""
        import tkinter.simpledialog as simpledialog
        val = simpledialog.askstring(
            "手动输入期刊",
            "输入期刊名称（一本一行，或分号分隔；\n数据库未收录的期刊将按名称直接添加）：",
            parent=self,
        )
        if not val:
            return
        names = [n.strip() for n in re.split(r"[;；\n]", val) if n.strip()]
        added = 0
        for nm in names:
            if len(self._selected_ids) >= self._max_selected:
                break
            if any(j.get("full_name", "") == nm for j in self._selected_map.values()):
                continue  # 已选
            j = self.store.get_by_name(nm, fuzzy=False)
            if j:
                if j["jid"] in self._selected_ids:
                    continue
                self._selected_ids.add(j["jid"])
                self._selected_map[j["jid"]] = j
            else:
                self._manual_seq += 1
                key = f"manual:{self._manual_seq}"
                self._selected_ids.add(key)
                self._selected_map[key] = {"full_name": nm}
            added += 1
        if added:
            self._list.refresh_checks()
            self._update_selected_display()
            self._hint_label.configure(
                text=f"✓ 已手动添加 {added} 本期刊", fg=COLORS["success"])

    # ── 确认 ─────────────────────────────────────────────
    def _on_confirm(self):
        n = len(self._selected_ids)
        if n < MIN_SELECT or n > self._max_selected:
            return
        if self.on_confirm:
            # 返回期刊名 list（与任务 journals 字段格式兼容）
            names = [self._selected_map[i].get("full_name", "")
                     for i in self._selected_ids if i in self._selected_map]
            try:
                self.on_confirm(names)
            except Exception:
                pass
        self.destroy()
