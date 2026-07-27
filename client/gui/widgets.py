"""
鸿讯 HONGXUN · 自定义控件库
Canvas 绘制控件、输入框、折叠面板、开关等
"""

import tkinter as tk
from tkinter import ttk, font
from gui.theme import COLORS, ICONS, FONT_BODY, FONT_BODY_BOLD, FONT_HEADING, FONT_CAPTION, FONT_LABEL, lerp_color
from PIL import Image, ImageDraw, ImageTk
import os


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
            highlightthickness=0,
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
        if self.has_placeholder:
            self.delete(0, tk.END)
            self.has_placeholder = False
            if self._show:
                super().configure(show=self._show)
            self.configure(foreground=COLORS["text_body"])

    def _on_focus_out(self, event):
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
        self._w = width
        self._h = height
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
        target_x = self._w - self._radius - self._thumb_margin if on else self._thumb_margin
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
                        self._h - self._thumb_margin)
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
            tx = self._w - self._radius - self._thumb_margin
            self.itemconfig(self._track, fill=self._track_color_on)
        else:
            tx = self._thumb_margin
            self.itemconfig(self._track, fill=self._track_color_off)
        self.coords(self._thumb,
                    tx, self._thumb_margin,
                    tx + self._radius * 2 - self._thumb_margin * 2,
                    self._h - self._thumb_margin)


# ======================================================================
# RoundedCard — 带阴影和圆角的卡片容器
# ======================================================================
class RoundedCard(tk.Frame):
    """Canvas 绘制圆角矩形 + 多层阴影的卡片容器"""

    def __init__(self, master, radius=10, bg_color="#FFFFFF", pad=14,
                 hover_elevate=False, shadow=True, **kwargs):
        # Pop 'bg' if passed in kwargs (duplicated by bg_color)
        kwargs.pop('bg', None)
        self._radius = radius
        self._bg_color = bg_color
        self._pad = pad
        self._hover_elevate = hover_elevate
        self._shadow_enabled = shadow
        self._shadow_offset_base = 2
        self._shadow_offset = 2

        super().__init__(master, bg=COLORS["bg_page"], **kwargs)
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0,
                                 bg=COLORS["bg_page"])
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self.content = tk.Frame(self._canvas, bg=bg_color)
        self._canvas_window = self._canvas.create_window(
            (pad, pad), window=self.content, anchor=tk.NW,
            tags="content"
        )

        self.bind("<Configure>", self._on_configure)
        self.content.bind("<Configure>", self._on_content_configure)

        if hover_elevate:
            self._canvas.bind("<Enter>", self._on_enter)
            self._canvas.bind("<Leave>", self._on_leave)

    def _on_configure(self, event):
        w = self.winfo_width()
        h = self.winfo_height()
        if w > 10 and h > 10:
            self._canvas.configure(width=w, height=h)
            self._draw()

    def _on_content_configure(self, event):
        self._canvas.itemconfig(self._canvas_window,
                                width=max(event.width, 10))
        self._update_canvas_size()

    def _update_canvas_size(self):
        cw = self.content.winfo_reqwidth() + self._pad * 2
        ch = self.content.winfo_reqheight() + self._pad * 2
        self._canvas.configure(width=cw, height=ch)

    def _draw(self):
        self._canvas.delete("shadow", "bg")
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 10 or h < 10:
            return

        r = self._radius
        so = self._shadow_offset

        if self._shadow_enabled:
            # 单层阴影 + 1px 边框（替代原 3 层阴影）
            self._rounded_rect(so, so + 1, w - so, h - so + 1,
                               r + 1, fill="#E8E8ED", outline="", tags="shadow")

        self._rounded_rect(0, 0, w, h, r,
                           fill=self._bg_color, outline="", tags="bg")

    def _rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1,
            x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2,
            x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self._canvas.create_polygon(pts, smooth=True, **kwargs)


# ======================================================================
# ModernButton — Canvas 绘制圆角按钮
# ======================================================================
class ModernButton(tk.Canvas):
    """圆角按钮，支持 hover 颜色过渡和 press 效果"""

    def __init__(self, master, text="", command=None, variant="primary",
                 radius=8, height=34, pad_x=20, width=None, **kwargs):
        self._text = text
        self._command = command
        self._radius = radius
        self._height = height
        self._pad_x = pad_x

        color_map = {
            "primary": (COLORS["primary"], COLORS["primary_hover"], COLORS["primary_active"], "white"),
            "secondary": (COLORS["btn_secondary_bg"], COLORS["hover_bg"], COLORS["border"], COLORS["btn_secondary_fg"]),
            "danger": (COLORS["btn_secondary_bg"], "#FEF2F2", COLORS["danger"], COLORS["danger"]),
        }
        self._bg_normal, self._bg_hover, self._bg_press, self._fg = color_map.get(variant, color_map["primary"])

        tmp_font = FONT_BODY
        if not width:
            text_w = len(text) * 8
            width = max(text_w + pad_x * 2, 60)

        super().__init__(master, width=width, height=height,
                         borderwidth=0, highlightthickness=0, **kwargs)
        self._current_bg = self._bg_normal
        self._w = width
        self._h = height

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw(self, bg_color):
        self.delete("all")
        r = self._radius
        w, h = self._w, self._h
        pts = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h, r, h, 0, h, 0, h - r, 0, r, 0, 0]
        self.create_polygon(pts, smooth=True, fill=bg_color, outline="")
        self.create_text(w / 2, h / 2, text=self._text, fill=self._fg,
                         font=FONT_BODY, anchor=tk.CENTER)

    def _on_enter(self, event):
        self._animate_bg(self._bg_normal, self._bg_hover, 5, 30)

    def _on_leave(self, event):
        self._animate_bg(self._current_bg, self._bg_normal, 5, 30)

    def _on_press(self, event):
        self._draw(self._bg_press)
        self._current_bg = self._bg_press
        if self._command:
            self.after(100, self._command)

    def _on_release(self, event):
        self._on_enter(None)

    def _animate_bg(self, start, end, steps, interval):
        def _step(step=0):
            if step > steps:
                self._current_bg = end
                self._draw(end)
                return
            t = step / steps
            c = lerp_color(start, end, t)
            self._draw(c)
            self.after(interval, lambda: _step(step + 1))

        _step()


# ======================================================================
# StatusPill — Canvas 绘制状态胶囊标签
# ======================================================================
class StatusPill(tk.Canvas):
    """圆角状态标签：pending, read, excluded"""

    STATUS_COLORS = {
        "pending": (COLORS["warning"], "#FFF7ED"),
        "read": (COLORS["success"], "#F0FDF4"),
        "excluded": (COLORS["danger"], "#FEF2F2"),
    }
    STATUS_TEXT = {"pending": "待读", "read": "已读", "excluded": "排除"}

    def __init__(self, master, status="pending", **kwargs):
        fg, bg = self.STATUS_COLORS.get(status, self.STATUS_COLORS["pending"])
        text = self.STATUS_TEXT.get(status, status)
        text_w = len(text) * 7
        total_w = text_w + 24
        super().__init__(master, width=total_w, height=22,
                         borderwidth=0, highlightthickness=0, **kwargs)
        r = 11
        w, h = total_w, 22
        pts = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h, r, h, 0, h, 0, h - r, 0, r, 0, 0]
        self.create_polygon(pts, smooth=True, fill=bg, outline="")
        self.create_text(w / 2, h / 2, text=text, fill=fg,
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

    @classmethod
    def get(cls, name, size=24, variant="default"):
        key = (name, size, variant)
        if key in cls._cache:
            return cls._cache[key]

        img = None
        if cls._icon_dir:
            path = os.path.join(cls._icon_dir, f"{name}_{variant}.png")
            if os.path.exists(path):
                try:
                    pil_img = Image.open(path).convert("RGBA")
                    pil_img = pil_img.resize((size, size), Image.LANCZOS)
                    img = ImageTk.PhotoImage(pil_img)
                except Exception:
                    pass

        if img is None:
            img = cls._render_icon(name, size, variant)

        cls._cache[key] = img
        return img

    @classmethod
    def invalidate(cls):
        cls._cache.clear()

    @classmethod
    def _render_icon(cls, name, size, variant):
        """PIL 绘制的图标后备——简单的几何图形"""
        try:
            color = "#6B7280" if variant == "default" else COLORS["primary"]
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
