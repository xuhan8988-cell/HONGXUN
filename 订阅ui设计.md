
## 一、问题定位
| 问题 | 代码位置 | 原因 |
|------|---------|------|
| 删除线在文字下面 | 第167行 | `create_line` 的 y 坐标是 39，而文字在 y=32，线在文字底部 |
| 折扣徽章太小 | 第158-162行 | 徽章高度只有 23px，字号只有 10px |
| 原价字体太小 | 第165行 | 字号只有 13px |
| 字体有遮挡 | 第142行 | 价格卡片高度 128px 不够，三行文字挤在一起 |

---

## 二、完整修改代码
直接替换 `_open_subscription_dialog` 函数中的对应部分：


### 修改2：左侧价值区垂直分布优化（第63-102行）
```python
# Logo（放大居中）
logo_img = None
try:
    logo_img = self._load_scaled_icon(ICON_APP, 80)
except Exception:
    logo_img = None
if logo_img:
    left.create_image(LEFT_W / 2, 96, image=logo_img)
    self._icon_refs.append(logo_img)
else:
    left.create_text(LEFT_W / 2, 96, text=ICONS["logo"],
                     font=(_ui_font_family(), 44, "bold"), fill="#3B82F6")
# 图标下方装饰线
left.create_line(LEFT_W / 2 - 24, 140, LEFT_W / 2 + 24, 140, fill="#93C5FD", width=1.5)
# 主标题 / 副标题
left.create_text(LEFT_W / 2, 178, text="解锁鸿讯专业版",
                 font=(_ui_font_family(), 22, "bold"), fill="#1E293B")
left.create_text(LEFT_W / 2, 210, text="让科研管理更高效",
                 font=(_ui_font_family(), 14), fill="#64748B")

# 价值点列表
features = [
    "每日邮件推送服务",
    "无限监控任务数量",
    "实验中心全模块开放",
    "后续新功能优先体验",
]
fy = 268
for feat in features:
    left.create_text(40, fy, text="✓", font=(_ui_font_family(), 16, "bold"),
                     fill="#10B981", anchor=tk.CENTER)
    left.create_text(64, fy, text=feat, font=(_ui_font_family(), 14),
                     fill="#334155", anchor=tk.W)
    fy += 40

# 底部信任背书
left.create_text(LEFT_W / 2, H - 64, text="⭐⭐⭐⭐⭐ 4.9 分用户评价",
                 font=(_ui_font_family(), 12), fill="#94A3B8")
left.create_text(LEFT_W / 2, H - 36, text="已有 1,200+ 科研工作者选择",
                 font=(_ui_font_family(), 13), fill="#94A3B8")
```

---

### 修改3：价格卡片整体放大（第142-183行）
这是最核心的修改，**直接替换整个 `_redraw_price_card` 函数**：

```python
# ── 价格卡片（蓝边高亮）──
self._sub_price_card = tk.Canvas(right, width=400, height=170,
                                 highlightthickness=0, bd=0, bg="#FFFFFF")
self._sub_price_card.pack(pady=(0, 6))

def _redraw_price_card(key):
    p = subscription.PLANS[key]
    c = self._sub_price_card
    c.delete("all")
    w, h = 400, 170
    # 蓝色柔光阴影
    c.create_polygon(4, 6, w - 4, 6, w - 4, h + 6, 4, h + 6,
                     fill="#DBEAFE", outline="")
    # 白卡 + 1.5px 蓝色边框
    _rounded_rect(c, 1, 1, w - 1, h - 1, 12, fill="#FFFFFF",
                  outline="#3B82F6", width=2)
    
    # ── 折扣徽章（右上角，放大）──
    badge_w, badge_h = 104, 36
    badge_x = w - badge_w - 10
    badge_y = 10
    _rounded_rect(c, badge_x, badge_y, badge_x + badge_w, badge_y + badge_h, 18,
                  fill="#EF4444", outline="")
    c.create_text(badge_x + badge_w / 2, badge_y + badge_h / 2,
                  text=f"🔥 {p['discount']}",
                  fill="#FFFFFF", font=(_ui_font_family(), 14, "bold"))
    
    # ── 原价（删除线，字号加大）──
    orig = f"原价 ¥{p['origin_price']}"
    orig_y = 42
    orig_font = (_ui_font_family(), 16)
    orig_id = c.create_text(28, orig_y, text=orig, font=orig_font,
                            fill="#94A3B8", anchor=tk.W)
    # 删除线：精确计算文字宽度，线在文字垂直中间
    try:
        orig_bbox = c.bbox(orig_id)
        orig_w = orig_bbox[2] - orig_bbox[0]
        orig_x_start = orig_bbox[0]
        line_y = orig_y  # 文字基线附近，正好穿过中间
    except Exception:
        orig_w = 10 * len(orig)
        orig_x_start = 28
        line_y = orig_y
    # 删除线（1.5px粗，从文字左边到右边，垂直居中）
    c.create_line(orig_x_start - 2, line_y, orig_x_start + orig_w + 2, line_y,
                  fill="#94A3B8", width=1.5)
    
    # ── 现价（超大字号，视觉中心）──
    price_num = str(p['price'])
    price_y = 96
    # ¥ 符号（小一号）
    yuan_font = (_ui_font_family(), 28, "bold")
    yuan_id = c.create_text(28, price_y, text="¥", font=yuan_font,
                            fill="#1D4ED8", anchor=tk.W)
    try:
        yuan_w = c.bbox(yuan_id)[2] - 28
    except Exception:
        yuan_w = 22
    # 价格数字（超大）
    num_font = (_ui_font_family(), 52, "bold")
    num_id = c.create_text(28 + yuan_w + 4, price_y, text=price_num, font=num_font,
                           fill="#1D4ED8", anchor=tk.W)
    try:
        num_w = c.bbox(num_id)[2] - (28 + yuan_w + 4)
    except Exception:
        num_w = 32 * len(price_num)
    # 「/永久」后缀
    suffix = f"/{p['label']}"
    suffix_font = (_ui_font_family(), 18)
    c.create_text(28 + yuan_w + 4 + num_w + 10, price_y, text=suffix,
                  font=suffix_font, fill="#64748B", anchor=tk.W)
    
    # ── 单位说明 ──
    c.create_text(28, 140,
                  text=f"一次付费 · 每天折合 ¥{p['daily']} 元 · 到期自动停止",
                  font=(_ui_font_family(), 12), fill="#64748B", anchor=tk.W)

_redraw_price_card(subscription.DEFAULT_PLAN)
```

---

### 修改4：主按钮加宽（第186-191行）
```python
# 原来：
self._sub_cta = ModernButton(
    right,
    text=f"立即解锁 · ¥{subscription.PLANS[subscription.DEFAULT_PLAN]['price']}",
    variant="primary", height=46, width=348,
    command=lambda: self._start_sub_payment(win))
self._sub_cta.pack(pady=(8, 0))

# 改成：
self._sub_cta = ModernButton(
    right,
    text=f"立即解锁 · ¥{subscription.PLANS[subscription.DEFAULT_PLAN]['price']}",
    variant="primary", height=50, width=400,
    command=lambda: self._start_sub_payment(win))
self._sub_cta.pack(pady=(10, 0))
```

---

### 修改5：关闭按钮位置微调（第36-38行）
```python
# 原来：
close_btn = tk.Label(card, text="✕", font=(_ui_font_family(), 13, "bold"),
                     fg=COLORS["text_hint"], bg="#FFFFFF", cursor="hand2")
close_btn.place(x=W - 30, y=8)

# 改成：
close_btn = tk.Label(card, text="✕", font=(_ui_font_family(), 14, "bold"),
                     fg=COLORS["text_hint"], bg="#FFFFFF", cursor="hand2")
close_btn.place(x=W - 34, y=10)
```

## 四、额外优化建议
### 1. 套餐选择胶囊位置
现在套餐选择在价格卡片上方，可以考虑移到价格卡片下方，让价格成为用户看到的第一个元素，转化率更高。

### 2. 「最推荐」标签
可以在默认选中的套餐胶囊上加一个「最推荐」小标签，引导用户选择。

### 3. 稀缺性提示
在折扣徽章旁边加一行小字「限时特惠，即将恢复原价」，增加紧迫感。

需要我继续帮你调整这些细节吗？或者你先看看上面的修改效果怎么样？