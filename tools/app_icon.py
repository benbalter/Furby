#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Draw the iPhone remote's app icon: the show's pink and blue Furbies peeking up
under a Halloween moon.

The icon is drawn here rather than by hand so it can be changed and redrawn.
It's drawn at twice the size and scaled down, which smooths the edges, and has
no transparency, which iOS requires of app icons.

USAGE (from the repo root):
    uv run tools/app_icon.py           # ios/FurbyRemote/Assets.xcassets/AppIcon.appiconset/icon-1024.png
    uv run tools/app_icon.py --out x.png
"""

import argparse
import math

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
SCALE = 2  # draw big, then scale down for smooth edges
OUT = "ios/FurbyRemote/Assets.xcassets/AppIcon.appiconset/icon-1024.png"

SKY_TOP, SKY_BOTTOM = (58, 22, 92), (16, 6, 28)
MOON = (255, 214, 120)
PINK, PINK_DARK = (240, 110, 180), (190, 70, 140)
BLUE, BLUE_DARK = (80, 160, 240), (45, 105, 190)
BEAK = (255, 170, 40)


def gradient(size, top, bottom):
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        draw.line([(0, y), (size, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)))
    return img


def fuzzy(draw, cx, cy, r, color, tufts=72, depth=0.07):
    """A round body with a spiky, furry edge."""
    points = []
    for i in range(tufts * 2):
        a = math.pi * i / tufts
        rr = r * (1 + depth if i % 2 else 1 - depth / 2)
        points.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    draw.polygon(points, fill=color)


def creature(draw, cx, cy, r, color, dark, look):
    """One Furby: ear tufts, a fuzzy head, two big eyes looking `look` (-1 left, 1 right), and a beak."""
    for side in (-1, 1):  # ears
        base = (cx + side * r * 0.55, cy - r * 0.6)
        tip = (cx + side * r * 0.9, cy - r * 1.3)
        draw.polygon([(base[0] - r * 0.28, base[1]), tip, (base[0] + r * 0.28, base[1])], fill=dark)
    fuzzy(draw, cx, cy, r, color)
    fuzzy(draw, cx, cy + r * 0.62, r * 0.55, dark, tufts=48, depth=0.05)  # belly
    eye_r = r * 0.3
    for side in (-1, 1):
        ex, ey = cx + side * r * 0.36, cy - r * 0.12
        draw.ellipse([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r], fill=(255, 255, 255))
        px, pr = ex + look * eye_r * 0.32, eye_r * 0.55
        draw.ellipse([px - pr, ey - pr, px + pr, ey + pr], fill=(25, 15, 35))
        hr = pr * 0.35
        hx, hy = px - pr * 0.35, ey - pr * 0.4
        draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 255, 255))
    by = cy + r * 0.2
    draw.polygon([(cx - r * 0.13, by), (cx + r * 0.13, by), (cx, by + r * 0.22)], fill=BEAK)


def draw_icon(size=SIZE):
    big = size * SCALE
    img = gradient(big, SKY_TOP, SKY_BOTTOM)

    glow = Image.new("L", (big, big), 0)  # the moon's halo
    mx, my, mr = big * 0.5, big * 0.27, big * 0.15
    ImageDraw.Draw(glow).ellipse([mx - mr * 1.5, my - mr * 1.5, mx + mr * 1.5, my + mr * 1.5], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(big * 0.04))
    img.paste(Image.new("RGB", (big, big), MOON), (0, 0), glow)

    draw = ImageDraw.Draw(img)
    draw.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=MOON)
    for dx, dy, cr in ((-0.35, -0.2, 0.18), (0.3, 0.25, 0.12), (0.05, 0.45, 0.08)):  # craters
        x, y, c = mx + dx * mr, my + dy * mr, cr * mr
        draw.ellipse([x - c, y - c, x + c, y + c], fill=(235, 190, 100))

    r = big * 0.2
    creature(draw, big * 0.27, big * 0.8, r, PINK, PINK_DARK, look=1)
    creature(draw, big * 0.73, big * 0.8, r, BLUE, BLUE_DARK, look=-1)

    return img.resize((size, size), Image.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=OUT, help="where to write the PNG (default: %(default)s)")
    args = parser.parse_args()
    draw_icon().save(args.out)
    print("Wrote", args.out)


if __name__ == "__main__":
    main()
