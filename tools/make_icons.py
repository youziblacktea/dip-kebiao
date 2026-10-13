#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 PWA 所需的应用图标（写入 src/icons/）。

设计：海军蓝底 + 白色日历 + 青色“今天”格子，与 App 配色一致。
用法：python tools/make_icons.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "icons"
NAVY = (22, 52, 83)
NAVY_LIGHT = (33, 84, 127)
TEAL = (14, 116, 144)
WHITE = (255, 255, 255)
GREY = (203, 214, 226)


def draw_calendar(size: int, scale: float, bg_radius_ratio: float) -> Image.Image:
    """按比例画一张图标。scale 控制日历本体占画布的比例，maskable 用更小的值。"""
    ss = 4  # 超采样，边缘更干净
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 背景：圆角方块 + 竖向渐变
    radius = int(S * bg_radius_ratio)
    grad = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / max(1, S - 1)
        grad.putpixel((0, y), tuple(int(NAVY[i] + (NAVY_LIGHT[i] - NAVY[i]) * t) for i in range(3)))
    grad = grad.resize((S, S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    # 日历本体
    cw = int(S * 0.58 * scale / 0.58 * 0.58)      # 逻辑宽度
    cw = int(S * scale)
    ch = int(cw * 0.86)
    x0 = (S - cw) // 2
    y0 = (S - ch) // 2
    x1, y1 = x0 + cw, y0 + ch
    d.rounded_rectangle([x0, y0, x1, y1], radius=int(cw * 0.14), fill=WHITE)

    # 顶部标题条
    bar = int(ch * 0.26)
    d.rounded_rectangle([x0, y0, x1, y0 + bar + int(cw * 0.14)], radius=int(cw * 0.14), fill=TEAL)
    d.rectangle([x0, y0 + bar - int(cw * 0.14), x1, y0 + bar], fill=TEAL)

    # 两个挂环
    ring_w = int(cw * 0.07)
    for cx in (x0 + int(cw * 0.28), x1 - int(cw * 0.28)):
        d.rounded_rectangle([cx - ring_w, y0 - int(ch * 0.09), cx + ring_w, y0 + int(ch * 0.06)],
                            radius=ring_w, fill=(240, 244, 248))

    # 日期格子：3 列 × 3 行，其中一个高亮
    pad = int(cw * 0.12)
    gw = (cw - 2 * pad) / 3
    top = y0 + bar + int(ch * 0.10)
    gh = (y1 - pad - top) / 3
    dots = [(r, c) for r in range(3) for c in range(3)]
    hi = (1, 0)
    for r, c in dots:
        bx = x0 + pad + c * gw
        by = top + r * gh
        w, h = gw * 0.62, gh * 0.58
        col = TEAL if (r, c) == hi else GREY
        d.rounded_rectangle([bx, by, bx + w, by + h], radius=int(min(w, h) * 0.28), fill=col)

    return img.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # 普通图标：内容占 ~62%，圆角约 22%
    draw_calendar(192, 0.62, 0.22).save(OUT / "icon-192.png")
    draw_calendar(512, 0.62, 0.22).save(OUT / "icon-512.png")
    # maskable：全出血 + 内容缩到安全区（约 50%）
    draw_calendar(512, 0.50, 0.50).save(OUT / "maskable-512.png")
    # iOS 主屏图标（不支持透明，铺满方形）
    ios = draw_calendar(180, 0.62, 0.00)
    bg = Image.new("RGB", (180, 180), NAVY)
    bg.paste(ios, (0, 0), ios)
    bg.save(OUT / "apple-touch-icon.png")
    for f in sorted(OUT.iterdir()):
        print(f"生成 {f.name} {Image.open(f).size} {f.stat().st_size} bytes")


if __name__ == "__main__":
    main()
