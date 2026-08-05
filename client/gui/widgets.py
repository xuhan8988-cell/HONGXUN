"""
鸿讯 HONGXUN · 自定义控件库
Canvas 绘制控件、输入框、折叠面板、开关等
"""

import tkinter as tk
from tkinter import ttk, font
from gui.theme import COLORS, ICONS, RADIUS_LG, RADIUS_MD, RADIUS_SM, RADIUS_PILL, FONT_BODY, FONT_BODY_BOLD, FONT_HEADING, FONT_CAPTION, FONT_LABEL, lerp_color, gradient_stops
from PIL import Image, ImageDraw, ImageTk
import os


# ======================================================================
# ModernEntry — 统一现代风格输入框（1px 细边框 + 聚焦主蓝）
# ======================================================================
class ModernEntry(tk.Frame):
    """现代风格输入框：1px 冷灰细边框 + 白底，聚焦时边框变主蓝。

    用 highlightthickness=1 + highlightbackground 实现 1px 细边框，
    聚焦时 highlightcolor 切换为主蓝（替代默认黑色粗边框）。
    支持 placeholder 与密码掩码。
    """

    def __init__(self, master, textvariable=None, placeholder="", width=None,
                 show=None, font=None, **kwargs):
        super().__init__(master, bg=COLORS["bg_page"], **kwargs)
        self._entry = tk.Entry(
            self,
            textvariable=textvariable,
            width=width,
            show=show,
            bd=0,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLORS["input_border"],
            highlightcolor=COLORS["primary"],
            bg=COLORS["bg_input"],
            fg=COLORS["text_body"],
            insertbackground=COLORS["text_body"],
            insertwidth=1,
            insertofftime=0,
            selectbackground=COLORS["primary_light"],
            selectforeground=COLORS["primary_active"],
            font=font or FONT_BODY,
            cursor="xterm",
        )
        self._entry.pack(fill=tk.X, ipady=5)

        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        self._entry.bind("<Command-a>", self._select_all)
        self._entry.bind("<Control-a>", self._select_all)

        self._placeholder = placeholder
        self._show_orig = show
        self._has_placeholder = False
        if placeholder:
            self._apply_placeholder()

    def _select_all(self, event=None):
        self._entry.select_range(0, tk.END)
        self._entry.icursor(tk.END)
        return "break"

    def _apply_placeholder(self):
        if self._has_placeholder:
            return
        self._has_placeholder = True
        if self._show_orig:
            self._entry.configure(show="")
        self._entry.delete(0, tk.END)
        self._entry.insert(0, self._placeholder)
        self._entry.configure(foreground=COLORS["text_hint"])

    def _on_focus_in(self, event):
        self._entry.configure(highlightbackground=COLORS["primary"],
                              highlightcolor=COLORS["primary"])
        if self._has_placeholder:
            self._entry.delete(0, tk.END)
            self._has_placeholder = False
            if self._show_orig:
                self._entry.configure(show=self._show_orig)
            self._entry.configure(foreground=COLORS["text_body"])

    def _on_focus_out(self, event):
        self._entry.configure(highlightbackground=COLORS["input_border"],
                              highlightcolor=COLORS["input_border"])
        if not self._entry.get().strip():
            self._apply_placeholder()

    def get(self):
        if self._has_placeholder:
            return ""
        return self._entry.get()

    def set(self, value):
        self._entry.delete(0, tk.END)
        if value.strip():
            self._has_placeholder = False
            self._entry.configure(foreground=COLORS["text_body"])
            if self._show_orig:
                self._entry.configure(show=self._show_orig)
            self._entry.insert(0, value)
        else:
            self._apply_placeholder()

    def focus_set(self):
        self._entry.focus_set()

    @property
    def entry(self):
        return self._entry


def attach_focus_ring(entry):
    """给普通 tk.Entry 加聚焦高亮：聚焦时 2px 蓝色边框 + 光晕，失焦恢复。

    在聚焦输入框上调用一次，返回 entry 本身以便链式使用。
    """
    entry.configure(highlightthickness=2,
                    highlightbackground=COLORS["input_border"],
                    highlightcolor=COLORS["primary"],
                    relief="solid", bd=1)
    entry.bind("<FocusIn>", lambda e: entry.configure(highlightbackground=COLORS["primary"],
                                                      highlightcolor=COLORS["primary"]))
    entry.bind("<FocusOut>", lambda e: entry.configure(highlightbackground=COLORS["input_border"],
                                                       highlightcolor=COLORS["input_border"]))
    return entry


# ======================================================================
# PlaceholderEntry — 统一输入框样式
# ======================================================================
class PlaceholderEntry(tk.Entry):
    def __init__(self, master=None, placeholder="", show=None, **kwargs):
        self._var = kwargs.pop('textvariable', None)
        super().__init__(master, show=show, **kwargs)
        self.placeholder = placeholder
        self._show = show
        self.has_placeholder = False

        self.configure(
            bd=1,
            relief="solid",
            highlightthickness=2,
            highlightbackground=COLORS["input_border"],
            highlightcolor=COLORS["input_border"],
            bg=COLORS["bg_input"],
            fg=COLORS["text_body"],
            insertbackground=COLORS["text_body"],
            insertwidth=1,
            insertofftime=0,
            selectbackground=COLORS["primary_light"],
            selectforeground=COLORS["primary_active"],
            font=FONT_BODY,
            cursor="xterm"
        )

        initial = self._var.get().strip() if self._var else ""
        if initial:
            self.insert(0, initial)
            self.configure(foreground=COLORS["text_body"])
        else:
            self._show_placeholder()

        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Command-a>", self._select_all)

    def _select_all(self, event=None):
        self.select_range(0, tk.END)
        self.icursor(tk.END)
        return "break"

    def _show_placeholder(self):
        if self.has_placeholder:
            return
        self.has_placeholder = True
        if self._show:
            super().configure(show="")
        self.delete(0, tk.END)
        self.insert(0, self.placeholder)
        self.configure(foreground=COLORS["text_hint"])

    def _on_focus_in(self, event):
        self.configure(highlightbackground=COLORS["primary"],
                       highlightcolor=COLORS["primary"])
        if self.has_placeholder:
            self.delete(0, tk.END)
            self.has_placeholder = False
            if self._show:
                super().configure(show=self._show)
            self.configure(foreground=COLORS["text_body"])

    def _on_focus_out(self, event):
        self.configure(highlightbackground=COLORS["input_border"],
                       highlightcolor=COLORS["input_border"])
        if not self.get().strip():
            self._show_placeholder()

    def get(self):
        if self.has_placeholder:
            return ""
        return super().get()

    def set(self, value):
        self.delete(0, tk.END)
        if value.strip():
            self.has_placeholder = False
            self.configure(foreground=COLORS["text_body"])
            if self._show:
                super().configure(show=self._show)
            self.insert(0, value)
        else:
            self._show_placeholder()


# ======================================================================
# CollapsibleFrame — 可折叠面板
# ======================================================================
class CollapsibleFrame(ttk.Frame):
    def __init__(self, master, title="", icon="", collapsed=True, **kwargs):
        super().__init__(master, style="TFrame", **kwargs)
        self._collapsed = collapsed
        self._title_text = title
        self._icon = icon

        self._header = tk.Frame(self, bg=COLORS["bg_page"], height=36)
        self._header.pack(fill=tk.X)
        self._header.pack_propagate(False)

        left_group = tk.Frame(self._header, bg=COLORS["bg_page"])
        left_group.pack(side=tk.LEFT)

        self._arrow_label = tk.Label(left_group,
                                     text=ICONS["arrow_down"] if not collapsed else ICONS["arrow_right"],
                                     font=FONT_BODY,
                                     fg=COLORS["text_secondary"],
                                     bg=COLORS["bg_page"],
                                     cursor="hand2")
        self._arrow_label.pack(side=tk.LEFT, padx=(4, 6))

        if icon:
            self._icon_label = tk.Label(left_group,
                                        text=icon,
                                        font=FONT_BODY,
                                        fg=COLORS["text_secondary"],
                                        bg=COLORS["bg_page"],
                                        cursor="hand2")
            self._icon_label.pack(side=tk.LEFT, padx=(0, 6))

        self._title_label = tk.Label(left_group,
                                     text=title,
                                     font=FONT_HEADING,
                                     fg=COLORS["text_title"],
                                     bg=COLORS["bg_page"],
                                     cursor="hand2")
        self._title_label.pack(side=tk.LEFT)

        self._badge = tk.Label(self._header,
                               text="",
                               font=FONT_CAPTION,
                               fg=COLORS["text_secondary"],
                               bg=COLORS["bg_page"])
        self._badge.pack(side=tk.RIGHT, padx=(0, 8))

        for w in [self._header, self._arrow_label, self._title_label, left_group]:
            w.bind("<Button-1>", self._toggle)
            w.configure(cursor="hand2")

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 6))

        self._body = tk.Frame(self, bg=COLORS["bg_page"])
        if not collapsed:
            self._body.pack(fill=tk.X, pady=(0, 6))

    def _toggle(self, event=None):
        if self._collapsed:
            self._expand()
        else:
            self._collapse()

    def _expand(self):
        self._collapsed = False
        self._arrow_label.configure(text=ICONS["arrow_down"])
        self._body.pack(fill=tk.X, pady=(0, 6))

    def _collapse(self):
        self._collapsed = True
        self._arrow_label.configure(text=ICONS["arrow_right"])
        self._body.pack_forget()

    @property
    def body(self):
        return self._body

    def set_badge(self, text, color):
        self._badge.configure(text=text, fg=color)


# ======================================================================
# ToggleSwitch — iOS 风格开关（画布绘制 + 滑动动画）
# ======================================================================
class ToggleSwitch(tk.Canvas):
    """iOS 风格开关：点击切换，带滑动动画"""

    def __init__(self, master, width=50, height=28, command=None, initial=False,
                 bg_color=COLORS["bg_page"]):
        self._command = command
        self._state = initial
        self._animating = False
        # 注意：不能用 _w/_h（tkinter Misc 保留属性，super().__init__ 会覆盖成 widget path）
        self._sw_width = width
        self._sw_height = height
        self._radius = height / 2
        self._thumb_margin = 2

        track_width = width
        track_height = height

        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, bg=bg_color)

        self._track_color_on = COLORS["primary"]
        self._track_color_off = "#E5E5EA"
        self._thumb_color = "#FFFFFF"

        self._track = self.create_rounded_rect(
            0, 0, track_width, track_height, self._radius,
            fill=self._track_color_off, outline=""
        )
        thumb_x = self._thumb_margin if not initial else width - self._radius - self._thumb_margin
        self._thumb = self.create_oval(
            thumb_x, self._thumb_margin,
            thumb_x + self._radius * 2 - self._thumb_margin * 2,
            height - self._thumb_margin,
            fill=self._thumb_color, outline=""
        )

        self.bind("<Button-1>", self._on_click, add="+")

    def create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1,
            x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2,
            x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _on_click(self, event):
        if self._animating:
            return
        self._state = not self._state
        self._animate()
        if self._command:
            self._command()

    def _animate(self):
        self._animating = True
        on = self._state
        target_x = self._sw_width - self._radius - self._thumb_margin if on else self._thumb_margin
        current_x = self.coords(self._thumb)[0]
        steps = 6
        delta = (target_x - current_x) / steps

        def _step(step=0):
            if not self._animating:
                return
            if step >= steps:
                self._draw_state()
                self._animating = False
                return
            cx = current_x + delta * (step + 1)
            cy = self._thumb_margin
            self.coords(self._thumb, cx, cy,
                        cx + self._radius * 2 - self._thumb_margin * 2,
                        self._sw_height - self._thumb_margin)
            ratio = (step + 1) / steps
            c = self._lerp_color(self._track_color_off, self._track_color_on, ratio) if on \
                else self._lerp_color(self._track_color_on, self._track_color_off, ratio)
            self.itemconfig(self._track, fill=c)
            self.after(30, lambda s=step + 1: _step(s))

        _step()

    def _lerp_color(self, c1, c2, t):
        return lerp_color(c1, c2, t)

    def get(self):
        return self._state

    def set(self, value):
        self._animating = False
        self._state = bool(value)
        self._draw_state()

    def _draw_state(self):
        if self._state:
            tx = self._sw_width - self._radius - self._thumb_margin
            self.itemconfig(self._track, fill=self._track_color_on)
        else:
            tx = self._thumb_margin
            self.itemconfig(self._track, fill=self._track_color_off)
        self.coords(self._thumb,
                    tx, self._thumb_margin,
                    tx + self._radius * 2 - self._thumb_margin * 2,
                    self._sw_height - self._thumb_margin)


# ======================================================================
# RoundedCard — 带阴影和圆角的卡片容器
# ======================================================================
class RoundedCard(tk.Frame):
    """Canvas 绘制圆角矩形 + 多层阴影的卡片容器"""

    # 卡片主体相对画布右下角的内缩量 = 阴影可见宽度
    _SHADOW_MARGIN = 6

    def __init__(self, master, radius=12, bg_color="#FFFFFF", pad=14,
                 hover_elevate=False, shadow=True, scrollable=False,
                 fit_content=False, **kwargs):
        # Pop 'bg' if passed in kwargs (duplicated by bg_color)
        kwargs.pop('bg', None)
        kwargs.pop('fit_content', None)  # 仅作内部开关，不传给底层 Frame
        # 固定高度模式：显式传 height 时锁定 Frame 高度（配合 fit_content=False）
        fixed_height = kwargs.pop('height', None)
        self._fixed_height = fixed_height
        self._radius = radius
        self._bg_color = bg_color
        self._pad = pad
        self._hover_elevate = hover_elevate
        self._shadow_enabled = shadow
        self._shadow_lift = False
        self._lift = 0
        self._scrollable = scrollable
        self._fit_content = fit_content

        super().__init__(master, bg=COLORS["bg_page"], **kwargs)
        if fixed_height:
            # 固定高度：禁止子控件撑破卡片，高度精确等于请求值
            self.pack_propagate(False)
            self.configure(height=fixed_height)
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0,
                                 bg=COLORS["bg_page"])
        self._canvas.pack(fill=tk.BOTH, expand=True)

        if scrollable:
            self._v_scroll = ModernScrollbar(self, width=8,
                                             command=self._canvas.yview)
            self._v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            self._canvas.configure(yscrollcommand=self._v_scroll.set)

        self.content = tk.Frame(self._canvas, bg=bg_color)
        # 关键：不能对 content 用 pack_propagate(False)。content 在 canvas.create_window
        # 中，尺寸由窗口精确控制；pack_propagate(False) 会让 content 内部 pack 子组件
        # 全部塌缩成 1x1（推送卡片/监控表单布局损坏的根源）。
        self._canvas_window = self._canvas.create_window(
            (pad, pad), window=self.content, anchor=tk.NW,
            tags="content"
        )

        self.bind("<Configure>", self._on_configure)
        self.content.bind("<Configure>", self._on_content_configure)

        if hover_elevate:
            self._canvas.bind("<Enter>", self._on_enter)
            self._canvas.bind("<Leave>", self._on_leave)
            # 整卡 hover：鼠标进入卡片区域时也触发（content 铺满卡片时
            # 鼠标常停在 content 上而非 canvas）
            self.content.bind("<Enter>", self._on_enter)
            self.content.bind("<Leave>", self._on_leave)

        if scrollable:
            self._bind_mousewheel()

        if fit_content:
            # 初次布局后按内容自适应高度（避免卡片停在 1px）
            self.after_idle(self._fit_height)

    def _fit_height(self):
        """内容自适应：根据 content 子控件请求总高，设置卡片与内容窗口高度"""
        if not self._fit_content:
            return
        children_h = sum(w.winfo_reqheight() for w in self.content.winfo_children())
        m = self._SHADOW_MARGIN if self._shadow_enabled else 0
        total = children_h + self._pad * 2 + m
        if total > 10:
            self.configure(height=total)
            # content 窗口高度 = 子控件总高 + 上下 padding（不扣阴影，阴影在画布边缘）
            try:
                self._canvas.itemconfig(self._canvas_window, height=children_h + self._pad * 2)
            except Exception:
                pass
            self._draw()

    def _bind_mousewheel(self):
        def _on_mousewheel(event):
            if event.num == 4:
                self._canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self._canvas.yview_scroll(1, "units")
            elif event.delta:
                import sys as _sys
                delta = event.delta if _sys.platform == "darwin" else event.delta / 120
                self._canvas.yview_scroll(int(-delta), "units")
            return "break"
        if self._scrollable:
            self._canvas.bind("<MouseWheel>", _on_mousewheel, add="+")
            self._canvas.bind("<Button-4>", _on_mousewheel, add="+")
            self._canvas.bind("<Button-5>", _on_mousewheel, add="+")

    def _inner_size(self, w, h):
        """卡片主体内部（内容区）的可用尺寸：减去 padding 与阴影边距"""
        m = self._SHADOW_MARGIN if self._shadow_enabled else 0
        return max(w - m - self._pad * 2, 1), max(h - m - self._pad * 2, 1)

    def _on_configure(self, event):
        w = self.winfo_width()
        h = self.winfo_height()
        if w > 10 and h > 10:
            self._canvas.configure(width=w, height=h)
            iw, ih = self._inner_size(w, h)
            if self._scrollable:
                self._canvas.itemconfig(self._canvas_window, width=iw)
            elif self._fit_content:
                # 内容自适应：窗口宽度跟随画布，高度由 content 自己决定
                self._canvas.itemconfig(self._canvas_window, width=iw)
                self._fit_height()
            else:
                self._canvas.itemconfig(self._canvas_window, width=iw, height=ih)
            self._draw()
            if self._scrollable:
                self._update_scrollregion()

    def _on_content_configure(self, event):
        if self._scrollable:
            self._update_scrollregion()
        elif self._fit_content:
            self._fit_height()

    def _update_scrollregion(self):
        ch = self.content.winfo_reqheight() + self._pad * 2
        cw = self._canvas.winfo_width()
        self._canvas.configure(scrollregion=(0, 0, cw, ch))

    def _on_enter(self, event):
        if not self._hover_elevate:
            return
        self._shadow_lift = True
        self._lift = 2
        self._apply_lift()
        self._draw()

    def _on_leave(self, event):
        if not self._hover_elevate:
            return
        self._shadow_lift = False
        self._lift = 0
        self._apply_lift()
        self._draw()

    def _apply_lift(self):
        """hover 抬升：卡片内容上移 2px，配合加深阴影营造"浮起"感"""
        if not self._hover_elevate:
            return
        lift = getattr(self, "_lift", 0)
        try:
            self._canvas.coords(self._canvas_window, self._pad, self._pad - lift)
        except Exception:
            pass

    def _draw(self):
        self._canvas.delete("shadow", "bg")
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 10 or h < 10:
            return

        r = self._radius
        m = self._SHADOW_MARGIN if self._shadow_enabled else 0

        if self._shadow_enabled:
            # 4 层叠加软阴影：卡片主体内缩 m，阴影从内缩处延伸到画布边缘。
            # 先画最大/最浅层，再画逐层缩小/加深层，形成「近卡片深 → 远处淡」的柔和衰减。
            # 层与层之间留空隙，让阴影更"远"、更柔和；hover 时整体加深并多画一层。
            if self._shadow_lift:
                s1 = lerp_color(COLORS["shadow_1"], "#0F172A", 0.32)
                s2 = lerp_color(COLORS["shadow_2"], "#0F172A", 0.22)
                s3 = lerp_color(COLORS["shadow_3"], "#0F172A", 0.12)
                s4 = lerp_color(COLORS["shadow_3"], "#0F172A", 0.06)
            else:
                s1, s2, s3, s4 = COLORS["shadow_1"], COLORS["shadow_2"], COLORS["shadow_3"], COLORS["shadow_3"]
            for inset, color in [(0, s4), (2, s3), (4, s2), (6, s1)]:
                self._rounded_rect(inset, inset + 1, w - inset, h - inset,
                                   r + 3, fill=color, outline="", tags="shadow")

        if m:
            self._rounded_rect(0, 0, w - m, h - m, r,
                               fill=self._bg_color, outline="", tags="bg")
            # 1px 极浅边框（比主体内缩 1px，避免被阴影挡），提升浅色背景上的精致感
            self._rounded_rect(1, 1, w - m - 1, h - m - 1, r,
                               fill="", outline=COLORS["border"], width=1, tags="bg")
        else:
            self._rounded_rect(0, 0, w, h, r,
                               fill=self._bg_color, outline=COLORS["border_light"], tags="bg")

    def _rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1,
            x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2,
            x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self._canvas.create_polygon(pts, smooth=True, **kwargs)


# ======================================================================
# 渐变按钮位图缓存（PIL 渲染，key: (w,h,radius,c1,c2)）
# ======================================================================
_gradient_cache = {}


def _make_gradient_bg(w, h, radius, c1, c2):
    """渲染圆角渐变背景图（垂直渐变 + 顶部内高光）。返回 PhotoImage 引用。"""
    key = (w, h, radius, c1, c2)
    cached = _gradient_cache.get(key)
    if cached is not None:
        return cached
    try:
        # 用 2x 尺寸渲染再缩放，获得平滑圆角与渐变
        scale = 2
        W, H = w * scale, h * scale
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        stops = gradient_stops(c1, c2, 8)
        # 逐行填充渐变
        step_h = H / max(len(stops), 1)
        for i, color in enumerate(stops):
            y0 = int(i * step_h)
            y1 = int((i + 1) * step_h)
            draw.rectangle([0, y0, W, y1], fill=color)
        # 圆角遮罩
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        rr = radius * scale
        md.rounded_rectangle([0, 0, W - 1, H - 1], radius=rr, fill=255)
        # 顶部 1px 内高光（白色半透明）——模拟玻璃质感
        highlight = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        hd = ImageDraw.Draw(highlight)
        hd.rounded_rectangle([0, 0, W - 1, max(2, int(2 * scale))], radius=rr, fill=(255, 255, 255, 70))
        highlight.putalpha(mask)
        img.paste(highlight, (0, 0), highlight)
        img = img.resize((w, h), Image.LANCZOS)
        img.putalpha(mask.resize((w, h), Image.LANCZOS))
        photo = ImageTk.PhotoImage(img)
        _gradient_cache[key] = photo
        return photo
    except Exception:
        return None


# ======================================================================
# ModernButton — Canvas 绘制圆角按钮
# ======================================================================
class ModernButton(tk.Canvas):
    """圆角按钮，支持渐变背景、hover 抬升与 press 反馈"""

    def __init__(self, master, text="", command=None, variant="primary",
                 radius=8, height=34, pad_x=20, width=None, **kwargs):
        # 根据当前字体大小缩放按钮默认高度与字符宽度，保证全屏缩放后文字不溢出
        font_scale = 1.0
        try:
            cur = FONT_BODY.cget("size") or 13
            font_scale = max(1.0, cur / 13.0)
        except Exception:
            pass
        if height == 34:
            height = max(30, int(34 * font_scale))
        if pad_x == 20:
            pad_x = max(16, int(20 * font_scale))
        self._text = text
        self._command = command
        self._radius = radius
        self._height = height
        self._pad_x = pad_x

        # 按钮色组：(普通色, hover色, press色, 文字色)
        # 不依赖渐变，纯色圆角 + 顶部高光 + 底部阴影线，任意环境稳定渲染
        self._color_specs = {
            "primary": (COLORS["primary"], COLORS["primary_hover"],
                        COLORS["primary_active"], "#FFFFFF"),
            "secondary": (COLORS["btn_secondary_bg"], COLORS["hover_bg"],
                          COLORS["border_light"], COLORS["btn_secondary_fg"]),
            "danger": (COLORS["btn_secondary_bg"], COLORS["danger_light"],
                       COLORS["danger_light"], COLORS["danger"]),
        }
        spec = self._color_specs.get(variant, self._color_specs["primary"])
        self._color = spec[0]
        self._color_h = spec[1]
        self._color_p = spec[2]
        self._fg = spec[3]

        self._state = "normal"   # normal / hover / press
        self._lift = 0
        self._enabled = True

        if not width:
            # 字符宽度随字体缩放（中文约 1.0 倍字高，英文约 0.55）
            try:
                fs = FONT_BODY.cget("size") or 13
                char_w = max(6.0, fs * 0.62)
            except Exception:
                char_w = 8.0
            text_w = len(text) * char_w
            width = max(int(text_w + pad_x * 2), 60)

        super().__init__(master, width=width, height=height + 3,
                         borderwidth=0, highlightthickness=0,
                         bg=COLORS["bg_page"], **kwargs)
        self._width = width
        self._height = height

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _bg_color(self):
        if not self._enabled:
            return "#CBD5E1"  # 禁用态：灰色
        if self._state == "press":
            return self._color_p
        if self._state == "hover":
            return self._color_h
        return self._color

    def _draw(self):
        self.delete("all")
        r = self._radius
        w, h = self._width, self._height
        lift = self._lift  # 0 或 -1（hover 上移）
        yoff = 0

        fill = self._bg_color()

        # 阴影（hover 时加深，营造"上浮"感）
        sh = "#CBD5E1" if self._state in ("hover", "press") else "#E2E8F0"
        self.create_rounded_rect_poly(0, lift + 3, w, h + 3, r + 2,
                                      fill=sh, outline="")

        # 纯色圆角背景（核心，不依赖 PIL 渐变）
        self.create_rounded_rect_poly(0, yoff, w, h, r, fill=fill, outline="")

        # 次要/危险按钮：细边框描边
        if self._fg != "#FFFFFF":
            outline = COLORS["danger_light"] if self._fg == COLORS["danger"] else COLORS["btn_secondary_border"]
            self.create_rounded_rect_poly(0, yoff, w - 1, h - 1, r,
                                          fill="", outline=outline, width=1)  # ✅ 加上 fill=""

        # 顶部 1px 高光（主按钮：白色半透明；浅色按钮：白色更亮）
        hl = "#FFFFFF" if self._fg == "#FFFFFF" else "#FFFFFF"
        self.create_rounded_rect_poly(0, yoff, w, yoff + 2, r,
                                      fill=hl, outline="")

        # 底部 1px 阴影线（比背景色深一点，增加立体感）
        if self._fg == "#FFFFFF":
            shade = lerp_color("#000000", fill, 0.82)
        else:
            shade = lerp_color("#FFFFFF", COLORS["btn_secondary_border"], 0.5)
        self.create_rounded_rect_poly(0, yoff + h - 1, w, yoff + h + 1, r,
                                      fill=shade, outline="")

        # 主文字（加粗，更清晰；禁用态用灰色）
        txt_color = COLORS["text_hint"] if not self._enabled else self._fg
        shadow_color = lerp_color("#000000", txt_color, 0.92) if txt_color == "#FFFFFF" \
            else lerp_color("#FFFFFF", txt_color, 0.55)
        self.create_text(w / 2, yoff + h / 2 + 1, text=self._text,
                         fill=shadow_color, font=FONT_BODY_BOLD, anchor=tk.CENTER)
        self.create_text(w / 2, yoff + h / 2, text=self._text, fill=txt_color,
                         font=FONT_BODY_BOLD, anchor=tk.CENTER)

    def create_rounded_rect_poly(self, x1, y1, x2, y2, r, **kwargs):
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1,
            x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2,
            x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(pts, smooth=True, **kwargs)

    def _on_enter(self, event):
        if not self._enabled:
            return
        self._state = "hover"
        self._lift = -1
        self._draw()

    def _on_leave(self, event):
        if not self._enabled:
            return
        self._state = "normal"
        self._lift = 0
        self._draw()

    def _on_press(self, event):
        if not self._enabled:
            return
        self._state = "press"
        self._lift = 0
        self._draw()
        if self._command:
            self.after(100, self._command)

    def _on_release(self, event):
        if not self._enabled:
            return
        if self._lift < 0:
            return
        self._state = "hover"
        self._lift = -1
        self._draw()

    def set_enabled(self, enabled):
        """启用/禁用按钮。禁用时显示灰色且点击无效。"""
        self._enabled = bool(enabled)
        self._draw()

    def set_text(self, text, variant=None, resize=True):
        """动态更新按钮文字（可选切变体）。

        resize=False 时保持当前宽度不变（用于倒计时等文本长度变化的场景，
        避免按钮宽度随文字跳动）。
        """
        self._text = text
        if variant and variant in self._color_specs:
            spec = self._color_specs[variant]
            self._color = spec[0]
            self._color_h = spec[1]
            self._color_p = spec[2]
            self._fg = spec[3]
        if resize:
            try:
                fs = FONT_BODY.cget("size") or 13
                char_w = max(6.0, fs * 0.62)
            except Exception:
                char_w = 8.0
            text_w = len(text) * char_w
            width = max(int(text_w + self._pad_x * 2), 60)
            self._width = width
            self.configure(width=width)
        self._draw()
# ======================================================================
# ModernScrollbar — 现代风格滚动条
# ======================================================================
class ModernScrollbar(tk.Canvas):
    """现代风格滚动条：浅灰背景 + 中灰滑块 + 圆角。

    与 ttk.Scrollbar 的接口兼容：set(first, last) 由关联控件回调，
    get() 返回当前区间；构造时传入 command=可关联 Canvas/Text 的 yview。
    """

    def __init__(self, master, width=8, command=None, **kwargs):
        super().__init__(master, width=width, highlightthickness=0,
                         bg=COLORS["scrollbar_bg"], **kwargs)
        self._command = command or (lambda *args: None)
        self._thumb_top = 0
        self._thumb_height = 50
        self._total_height = 100
        self._visible_height = 50
        self._hover = False
        self._dragging = False
        self._drag_start_y = 0
        self._drag_start_top = 0

        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._draw()

    def _on_configure(self, event):
        self._draw()

    def _on_enter(self, event):
        self._hover = True
        self._draw()

    def _on_leave(self, event):
        self._hover = False
        self._dragging = False
        self._draw()

    def _on_click(self, event):
        # 点击滚动条轨道，跳转到对应位置
        ratio = event.y / max(self.winfo_height(), 1)
        new_top = ratio * (self._total_height - self._visible_height)
        first = new_top / self._total_height
        self.set(first, (new_top + self._visible_height) / self._total_height)
        self._move_to(first)
        self._dragging = True
        self._drag_start_y = event.y
        self._drag_start_top = self._thumb_top

    def _on_drag(self, event):
        if not self._dragging:
            return
        delta_y = event.y - self._drag_start_y
        track_height = self.winfo_height() - self._thumb_height
        if track_height <= 0:
            return
        ratio = delta_y / track_height
        new_top = self._drag_start_top + ratio * (self._total_height - self._visible_height)
        new_top = max(0, min(new_top, self._total_height - self._visible_height))
        first = new_top / self._total_height
        self.set(first, (new_top + self._visible_height) / self._total_height)
        self._move_to(first)

    def _on_release(self, event):
        self._dragging = False
        self._draw()

    def set(self, first, last):
        """设置滚动位置（和 ttk.Scrollbar 接口兼容）。

        只更新滑块外观，不回调 command——canvas 通过 yscrollcommand
        回调 set() 时只是同步滑块位置，若在这里反调 yview("moveto")
        会在窗口缩放/首次布局时与 canvas 形成反馈回路，导致内容上下跳动。
        """
        first = float(first)
        last = float(last)
        self._total_height = 1000  # 虚拟总高度
        self._visible_height = (last - first) * self._total_height
        self._thumb_top = first * self._total_height
        self._draw()

    def _move_to(self, first):
        """用户交互（点击/拖动滑块）时通知关联的 Canvas/Text 滚动。"""
        if self._command:
            self._command("moveto", first)

    def get(self):
        return (self._thumb_top / self._total_height,
                (self._thumb_top + self._visible_height) / self._total_height)

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()

        if h <= 0 or self._total_height <= 0:
            return

        # 计算滑块位置和大小
        track_h = h
        # 内容无需滚动时（可见高度≥总高度）隐藏滑块，避免画出整条"滑轨"，
        # 也避免滚动时滑块残影干扰内容区
        if self._visible_height >= self._total_height - 1:
            return
        thumb_h = max(30, (self._visible_height / self._total_height) * track_h)
        thumb_top = (self._thumb_top / self._total_height) * track_h

        # 限制滑块范围
        thumb_top = max(0, min(thumb_top, track_h - thumb_h))

        # 绘制滑块
        thumb_color = COLORS["scrollbar_thumb_hover"] if self._hover else COLORS["scrollbar_thumb"]
        radius = 4  # 圆角 4px

        # 用 polygon 画圆角矩形
        x1 = (w - 6) / 2  # 滑块宽度 6px，居中
        x2 = x1 + 6
        y1 = thumb_top
        y2 = thumb_top + thumb_h

        self.create_polygon(
            self._rounded_pts(x1, y1, x2, y2, radius),
            smooth=True,
            fill=thumb_color,
            outline=""
        )

    @staticmethod
    def _rounded_pts(x1, y1, x2, y2, r):
        return [
            x1 + r, y1, x2 - r, y1, x2, y1,
            x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2,
            x1, y2 - r, x1, y1 + r, x1, y1,
        ]


# ======================================================================
# StatusPill — Canvas 绘制状态胶囊标签
# ======================================================================
class StatusPill(tk.Canvas):
    """圆角状态胶囊标签：左侧实心圆点 + 文字"""

    STATUS_COLORS = {
        "pending": (COLORS["warning"], "#FFF7ED", "#B45309"),
        "read": (COLORS["success"], "#F0FDF4", "#065F46"),
        "excluded": (COLORS["danger"], "#FEF2F2", "#B91C1C"),
    }
    STATUS_TEXT = {"pending": "待读", "read": "已读", "excluded": "排除"}

    def __init__(self, master, status="pending", **kwargs):
        fg, bg, dot = self.STATUS_COLORS.get(status, self.STATUS_COLORS["pending"])
        text = self.STATUS_TEXT.get(status, status)
        try:
            fs = FONT_CAPTION.cget("size") or 11
            char_w = max(6.0, fs * 0.7)
            pill_h = max(22, int(20 * (fs / 11.0)))
        except Exception:
            char_w = 8.0
            pill_h = 24
        text_w = len(text) * char_w
        total_w = int(text_w + 34)  # 圆点 + 更大内边距
        super().__init__(master, width=total_w, height=pill_h,
                         borderwidth=0, highlightthickness=0, **kwargs)
        r = 12
        w, h = total_w, pill_h
        pts = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h, r, h, 0, h, 0, h - r, 0, r, 0, 0]
        self.create_polygon(pts, smooth=True, fill=bg, outline="")
        # 左侧实心圆点（同色系更深）
        self.create_oval(9, h // 2 - 2, 13, h // 2 + 2, fill=dot, outline="")
        self.create_text(w / 2 + 5, h / 2, text=text, fill=fg,
                         font=FONT_CAPTION, anchor=tk.CENTER)


# ======================================================================
# IconLabel — 图标 + 文字组合标签
# ======================================================================
class IconLabel(tk.Frame):
    """显示图标（PNG/PIL/emoji 回退）+ 文字的标签"""

    def __init__(self, master, icon_name="", text="", icon_size=18,
                 font=None, fg=None, bg=None, **kwargs):
        fg = fg or COLORS["text_body"]
        bg = bg or COLORS["bg_page"]
        font = font or FONT_BODY
        super().__init__(master, bg=bg, **kwargs)

        # Try loading icon from cache or generate
        icon_img = IconCache.get(icon_name, icon_size, "default")
        if icon_img:
            self._icon_label = tk.Label(self, image=icon_img, bg=bg)
            self._icon_label.image = icon_img
            self._icon_label.pack(side=tk.LEFT, padx=(0, 6))
        elif icon_name in ICONS:
            self._icon_label = tk.Label(self, text=ICONS.get(icon_name, ""),
                                        font=font, fg=fg, bg=bg)
            self._icon_label.pack(side=tk.LEFT, padx=(0, 6))

        if text:
            self._text_label = tk.Label(self, text=text, font=font,
                                        fg=fg, bg=bg)
            self._text_label.pack(side=tk.LEFT)


# ======================================================================
# IconCache — 图标缓存与渲染
# ======================================================================
class IconCache:
    _cache = {}
    _icon_dir = None

    @classmethod
    def init(cls, icon_dir):
        cls._icon_dir = icon_dir

    @staticmethod
    def _tint_image(pil_img, color):
        """将线性图标重染为指定颜色（保留透明通道）。"""
        if not color:
            return pil_img
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        rgba = pil_img.convert("RGBA")
        px = rgba.load()
        w, h = rgba.size
        for y in range(h):
            for x in range(w):
                a = px[x, y][3]
                if a > 0:
                    orig_a = px[x, y][3]
                    # 白色直接用纯白，不做亮度缩放（避免灰图标透出原色）
                    if color == "#FFFFFF":
                        px[x, y] = (255, 255, 255, orig_a)
                    else:
                        # 只替换不透明像素的 RGB，保留原 alpha 与原亮度差异
                        lum = px[x, y][0] * 0.3 + px[x, y][1] * 0.59 + px[x, y][2] * 0.11
                        scale = lum / 255.0 if lum > 0 else 1.0
                        nr = max(0, min(255, int(r * scale)))
                        ng = max(0, min(255, int(g * scale)))
                        nb = max(0, min(255, int(b * scale)))
                        px[x, y] = (nr, ng, nb, orig_a)
        return rgba

    @classmethod
    def get(cls, name, size=24, variant="default", tint=None):
        key = (name, size, variant, tint)
        if key in cls._cache:
            return cls._cache[key]

        img = None
        if cls._icon_dir:
            path = os.path.join(cls._icon_dir, f"{name}_{variant}.png")
            if os.path.exists(path):
                try:
                    pil_img = Image.open(path).convert("RGBA")
                    if tint:
                        pil_img = cls._tint_image(pil_img, tint)
                    pil_img = pil_img.resize((size, size), Image.LANCZOS)
                    img = ImageTk.PhotoImage(pil_img)
                except Exception:
                    pass

        if img is None:
            img = cls._render_icon(name, size, variant, tint=tint)

        cls._cache[key] = img
        return img

    @classmethod
    def invalidate(cls):
        cls._cache.clear()

    @classmethod
    def _render_icon(cls, name, size, variant, tint=None):
        """PIL 绘制的图标后备——简单的几何图形"""
        try:
            # 有 tint 时优先用 tint 颜色（如统计卡图标要求白色）
            if tint:
                color = tint
            else:
                color = COLORS["text_secondary"] if variant == "default" else COLORS["primary"]
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            s = size
            m = 3
            # Draw simple shapes per icon name
            if name == "search":
                draw.ellipse([m, m, s - m - 3, s - m - 3], outline=color, width=2)
                draw.line([s - 7, s - 7, s - 1, s - 1], fill=color, width=2)
            elif name == "plus":
                draw.line([s // 2, m, s // 2, s - m], fill=color, width=2)
                draw.line([m, s // 2, s - m, s // 2], fill=color, width=2)
            elif name == "refresh":
                draw.arc([m, m, s - m, s - m], 45, 315, fill=color, width=2)
                draw.line([s // 2 + 2, m - 1, s // 2 + 2 + 5, m - 1 - 3], fill=color, width=2)
                draw.line([s // 2 + 2, m - 1, s // 2 + 2 + 5, m - 1 + 3], fill=color, width=2)
            elif name == "save":
                draw.rectangle([m, m, s - m, s - m], outline=color, width=2)
                draw.rectangle([m + 4, s // 2 + 2, s - m - 4, s - m - 2], fill=color)
            elif name == "cancel":
                draw.line([m, m, s - m, s - m], fill=color, width=2)
                draw.line([s - m, m, m, s - m], fill=color, width=2)
            elif name == "play":
                pts = [m + 2, m, s - m, s // 2, m + 2, s - m]
                draw.polygon(pts, fill=color)
            elif name == "pause":
                draw.rectangle([m, m, s // 2 - 2, s - m], fill=color)
                draw.rectangle([s // 2 + 2, m, s - m, s - m], fill=color)
            elif name == "check":
                draw.line([m, s // 2, s // 2 - 2, s - m], fill=color, width=3)
                draw.line([s // 2 - 2, s - m, s - m, m], fill=color, width=3)
            elif name == "trash":
                draw.rectangle([m + 2, s // 2, s - m - 2, s - 2], outline=color, width=2)
                draw.rectangle([m + 3, m + 3, s - m - 3, s // 2], fill=color)
            elif name == "edit":
                draw.line([m + 2, s - m - 2, m + 6, s - m - 6], fill=color, width=2)
                draw.line([m + 6, s - m - 6, s - m - 2, m + 2], fill=color, width=2)
            elif name == "clock":
                draw.ellipse([m, m, s - m, s - m], outline=color, width=2)
                draw.line([s // 2, m + 2, s // 2, s // 2], fill=color, width=2)
                draw.line([s // 2, s // 2, s - m - 2, s // 2], fill=color, width=2)
            elif name == "email":
                draw.rectangle([m, m + 3, s - m, s - m - 3], outline=color, width=2)
                draw.line([m, m + 3, s // 2, s // 2, s - m, m + 3], fill=color, width=2)
            elif name == "key":
                draw.ellipse([m, m, s // 2 + 2, s - m], outline=color, width=2)
                draw.line([s // 2 + 4, s // 2, s - m - 2, s // 2], fill=color, width=2)
                draw.line([s - m - 2, s // 2, s - m - 2, s // 2 - 4], fill=color, width=2)
            elif name == "lock":
                draw.rectangle([m + 3, s // 2, s - m - 3, s - m], outline=color, width=2)
                draw.arc([m + 3, m + 2, s - m - 3, s // 2 + 3], 180, 0, fill=color, width=2)
                draw.line([s // 2, s // 2, s // 2, s // 2 + 4], fill=color, width=2)
            elif name == "unlock":
                draw.rectangle([m + 3, s // 2, s - m - 3, s - m], outline=color, width=2)
                draw.arc([m + 6, m + 2, s - m - 3, s // 2 + 3], 180, 0, fill=color, width=2)
                draw.line([s // 2, s // 2, s // 2, s // 2 + 4], fill=color, width=2)
            elif name == "library":
                # 两本竖立书脊 + 顶部圆角
                draw.rectangle([m, m + 2, s // 2 - 1, s - m], fill=color)
                draw.rectangle([s // 2 + 1, m, s - m, s - m - 2], fill=color)
                draw.rectangle([m, m, s // 2 - 1, m + 3], fill=color)
                draw.rectangle([s // 2 + 1, m - 2, s - m, m + 1], fill=color)

            return ImageTk.PhotoImage(img)
        except Exception:
            return None


# ======================================================================
# SkeletonLoader — 脉冲灰条骨架屏
# ======================================================================
class SkeletonLoader(tk.Frame):
    """模拟加载动画的脉冲灰条"""

    def __init__(self, master, width=200, height=20, radius=4, count=1, **kwargs):
        super().__init__(master, bg=COLORS["bg_page"], **kwargs)
        self._items = []
        self._running = True

        for i in range(count):
            frame = tk.Frame(self, bg=COLORS["bg_page"], height=height + 4)
            frame.pack(fill=tk.X, pady=2)
            canvas = tk.Canvas(frame, width=width, height=height,
                               borderwidth=0, highlightthickness=0,
                               bg=COLORS["bg_page"])
            canvas.pack(anchor=tk.W)
            r = radius
            w, h = width, height
            pts = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h, r, h, 0, h, 0, h - r, 0, r, 0, 0]
            rect_id = canvas.create_polygon(pts, smooth=True,
                                            fill=COLORS["border_light"], outline="")
            self._items.append((canvas, rect_id))

        self._pulse()

    def _pulse(self):
        if not self._running:
            return
        colors = [COLORS["border_light"], "#F0F0F2", "#E8E8ED", "#F0F0F2", COLORS["border_light"]]
        self._pulse_step(0, colors)

    def _pulse_step(self, idx, colors):
        if not self._running or idx >= len(colors):
            self.after(100, self._pulse)
            return
        c = colors[idx]
        for canvas, rect_id in self._items:
            canvas.itemconfig(rect_id, fill=c)
        self.after(200, lambda: self._pulse_step(idx + 1, colors))

    def destroy(self):
        self._running = False
        super().destroy()


# ======================================================================
# EmptyState — 空状态插图
# ======================================================================
class EmptyState(tk.Frame):
    """居中显示的空状态组件"""

    def __init__(self, master, icon="search", title="", subtitle="", **kwargs):
        super().__init__(master, bg=COLORS["bg_page"], **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        container = tk.Frame(self, bg=COLORS["bg_page"])
        container.grid(row=0, column=0)

        icon_img = IconCache.get(icon, 64, "default")
        if icon_img:
            icon_label = tk.Label(container, image=icon_img, bg=COLORS["bg_page"])
            icon_label.image = icon_img
            icon_label.pack(pady=(0, 12))

        if title:
            tk.Label(container, text=title, font=FONT_HEADING,
                     fg=COLORS["text_secondary"], bg=COLORS["bg_page"],
                     wraplength=300).pack(pady=(0, 4))

        if subtitle:
            tk.Label(container, text=subtitle, font=FONT_CAPTION,
                     fg=COLORS["text_hint"], bg=COLORS["bg_page"],
                     wraplength=300).pack()
