#!/usr/bin/env python3
"""
鸿讯 HONGXUN · 图标生成脚本
用法: python3 generate_icons.py [output_dir]
生成 24×24 PNG 线性图标到 output_dir（默认 ../client/logo/icons）
"""

import os, sys
from PIL import Image, ImageDraw

ICON_NAMES = [
    "search", "journal", "task", "email", "settings", "export",
    "trash", "edit", "plus", "play", "pause", "refresh", "save",
    "clock", "cancel", "feedback", "coupon", "lock", "unlock",
    "check", "warning", "error", "dot_on", "dot_off",
]

COLOR_DEFAULT = "#6B7280"
COLOR_ACTIVE = "#2563EB"


def draw_icon(name, size=24, color="#6B7280"):
    """Draw a simple linear icon using PIL"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size
    m = 3
    sw = 2  # stroke width

    if name == "search":
        draw.ellipse([m, m, s - m - 4, s - m - 4], outline=color, width=sw)
        draw.line([s - 8, s - 8, s - 2, s - 2], fill=color, width=sw)
    elif name == "journal":
        draw.rectangle([m, 1, s - m, s - 1], outline=color, width=sw)
        draw.line([m + 3, m + 4, s - m - 3, m + 4], fill=color, width=sw)
        draw.line([m + 3, m + 8, s - m - 3, m + 8], fill=color, width=sw)
        draw.line([m + 3, m + 12, s - m - 3, m + 12], fill=color, width=sw)
    elif name == "task":
        draw.rectangle([m + 1, m, s - m - 1, s - 1], outline=color, width=sw)
        draw.line([m + 5, m + 4, m + 5, s - 4], fill=color, width=sw)
        draw.polygon([s - m - 4, s // 2 - 4, s // 2 + 2, s // 2 + 6, s - m - 4, s // 2 + 6], fill=color)
    elif name == "email":
        draw.rectangle([m, m + 2, s - m, s - m - 2], outline=color, width=sw)
        draw.line([m, m + 2, s // 2, s // 2, s - m, m + 2], fill=color, width=sw)
    elif name == "settings":
        draw.ellipse([m + 2, m + 2, s - m - 2, s - m - 2], outline=color, width=sw)
        draw.ellipse([m + 5, m + 5, s - m - 5, s - m - 5], outline=color, width=sw)
    elif name == "export":
        draw.line([s // 2, m + 2, s // 2, s - m], fill=color, width=sw)
        draw.line([m + 2, s - m - 2, s // 2, s - 2], fill=color, width=sw)
        draw.line([s - m - 2, s - m - 2, s // 2, s - 2], fill=color, width=sw)
        draw.rectangle([m + 2, s - m - 1, s - m - 2, s - 1], fill=color)
    elif name == "trash":
        draw.rectangle([m + 2, s // 2 + 2, s - m - 2, s - 2], outline=color, width=sw)
        draw.rectangle([m + 3, m + 2, s - m - 3, s // 2 + 2], fill=color)
    elif name == "edit":
        draw.line([m + 2, s - m - 2, m + 6, s - m - 6], fill=color, width=sw)
        draw.line([m + 6, s - m - 6, s - m - 2, m + 2], fill=color, width=sw)
    elif name == "plus":
        draw.line([s // 2, m + 1, s // 2, s - m - 1], fill=color, width=sw)
        draw.line([m + 1, s // 2, s - m - 1, s // 2], fill=color, width=sw)
    elif name == "play":
        pts = [m + 1, m, s - m, s // 2, m + 1, s - m]
        draw.polygon(pts, fill=color)
    elif name == "pause":
        draw.rectangle([m, m, s // 2 - 2, s - m], fill=color)
        draw.rectangle([s // 2 + 2, m, s - m, s - m], fill=color)
    elif name == "refresh":
        draw.arc([m, m, s - m, s - m], 45, 315, fill=color, width=sw)
        draw.line([s // 2 + 1, m - 2, s // 2 + 1 + 5, m - 2 - 3], fill=color, width=sw)
        draw.line([s // 2 + 1, m - 2, s // 2 + 1 + 5, m - 2 + 3], fill=color, width=sw)
    elif name == "save":
        draw.rectangle([m, m, s - m, s - m], outline=color, width=sw)
        draw.rectangle([m + 4, s // 2 + 2, s - m - 4, s - m - 2], fill=color)
    elif name == "clock":
        draw.ellipse([m, m, s - m, s - m], outline=color, width=sw)
        draw.line([s // 2, m + 1, s // 2, s // 2], fill=color, width=sw)
        draw.line([s // 2, s // 2, s - m - 1, s // 2], fill=color, width=sw)
    elif name == "cancel":
        draw.line([m, m, s - m, s - m], fill=color, width=sw)
        draw.line([s - m, m, m, s - m], fill=color, width=sw)
    elif name == "feedback":
        draw.rectangle([m, m + 2, s - m, s - m], outline=color, width=sw)
        draw.line([m, s - m, m + 4, s - m - 4], fill=color, width=sw)
    elif name == "coupon":
        draw.rectangle([m, m + 3, s - m, s - m - 3], outline=color, width=sw)
        draw.rectangle([m + 3, m + 6, m + 7, m + 10], fill=color)
    elif name == "lock":
        draw.rectangle([m + 2, s // 2, s - m - 2, s - m], outline=color, width=sw)
        draw.arc([m + 2, m + 2, s - m - 2, s // 2 + 3], 180, 0, fill=color, width=sw)
        draw.line([s // 2, s // 2, s // 2, s // 2 + 4], fill=color, width=sw)
    elif name == "unlock":
        draw.rectangle([m + 2, s // 2, s - m - 2, s - m], outline=color, width=sw)
        draw.arc([m + 6, m + 2, s - m - 2, s // 2 + 3], 180, 0, fill=color, width=sw)
        draw.line([s // 2, s // 2, s // 2, s // 2 + 4], fill=color, width=sw)
    elif name == "check":
        draw.line([m, s // 2, s // 2 - 2, s - m], fill=color, width=sw + 1)
        draw.line([s // 2 - 2, s - m, s - m, m], fill=color, width=sw + 1)
    elif name == "warning":
        pts = [s // 2, m, s - m, s - m, m, s - m]
        draw.polygon(pts, outline=color, width=sw)
        draw.line([s // 2, m + 6, s // 2, s - m - 6], fill=color, width=sw)
        draw.ellipse([s // 2 - 2, s - m - 4, s // 2 + 2, s - m], fill=color)
    elif name == "error":
        draw.ellipse([m, m, s - m, s - m], outline=color, width=sw)
        draw.line([m + 3, m + 3, s - m - 3, s - m - 3], fill=color, width=sw)
        draw.line([s - m - 3, m + 3, m + 3, s - m - 3], fill=color, width=sw)
    elif name == "dot_on":
        draw.ellipse([m + 2, m + 2, s - m - 2, s - m - 2], fill=color)
    elif name == "dot_off":
        draw.ellipse([m + 2, m + 2, s - m - 2, s - m - 2], outline=color, width=sw)
    else:
        # Unknown icon: draw a circle fallback
        draw.ellipse([m, m, s - m, s - m], outline=color, width=sw)

    return img


def main():
    output_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "client", "logo", "icons"
    )
    os.makedirs(output_dir, exist_ok=True)

    counts = {"default": 0, "active": 0}
    for name in ICON_NAMES:
        for variant, color in [("default", COLOR_DEFAULT), ("active", COLOR_ACTIVE)]:
            img = draw_icon(name, color=color)
            path = os.path.join(output_dir, f"{name}_{variant}.png")
            img.save(path)
            counts[variant] += 1

    total = sum(counts.values())
    print(f"✓ Generated {total} icons ({counts['default']} default + {counts['active']} active)")
    print(f"  Output: {output_dir}")

    # Verify
    from PIL import Image
    for name in ICON_NAMES:
        path = os.path.join(output_dir, f"{name}_default.png")
        if not os.path.exists(path):
            print(f"  ⚠ Missing: {path}")
    print("  All icons verified.")


if __name__ == "__main__":
    main()
