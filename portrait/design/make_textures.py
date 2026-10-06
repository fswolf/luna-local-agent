"""Textures for Luna's model, drawn from numbers in her wallpaper's colours.

    python portrait/design/make_textures.py

Writes portrait/textures/*.png. Each is a starting point: swap any of
them for a hand-painted or AI-made one of the same size and layout and
re-run the Blender build (portrait/blender/build_luna.py).

  iris.png   the whole visible eye inside the lids: the pink iris with
             its darker rim, a soft glow low down, the pupil, and two
             catchlights. Square; the iris fills it.
"""
import os

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "textures")


def rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def mix(a, b, t):
    t = np.clip(t, 0, 1)[..., None]
    return a * (1 - t) + b * t


def iris(size=512):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    u = (x + 0.5) / size * 2 - 1          # -1..1, left to right
    v = (y + 0.5) / size * 2 - 1          # -1..1, top to bottom
    r = np.sqrt(u * u + v * v)
    ang = np.arctan2(v, u)

    top, mid, low = rgb("#6e0f45"), rgb("#e83b8c"), rgb("#ffb0d8")
    # vertical gradient: dark under the lid, bright pink, a glow at the bottom
    col = mix(top, mid, (v + 0.95) / 0.9)
    col = mix(col, low, (v - 0.15) / 0.75 * (1 - r * 0.5))

    # fine radial streaks, the way anime irises are painted
    streak = (np.sin(ang * 46) * 0.5 + 0.5) * np.clip((r - 0.35) / 0.5, 0, 1) * 0.18
    col = col * (1 - streak[..., None]) + rgb("#ffd6ea") * streak[..., None] * 0.6

    # a dark limbal ring
    ring = np.clip((r - 0.80) / 0.14, 0, 1)
    col = mix(col, rgb("#3a0624"), ring * 0.9)

    # pupil: a tall soft oval a touch above centre, with a magenta edge
    pr = np.sqrt((u / 0.20) ** 2 + ((v + 0.06) / 0.34) ** 2)
    col = mix(col, rgb("#c0206a"), np.clip((1.35 - pr) / 0.3, 0, 1) * 0.5)
    col = mix(col, rgb("#25031a"), np.clip((1.05 - pr) / 0.1, 0, 1))

    # catchlights: a big soft one up-left, a small sharp one down-right
    h1 = np.sqrt(((u + 0.30) / 0.17) ** 2 + ((v + 0.38) / 0.22) ** 2)
    h2 = np.sqrt(((u - 0.32) / 0.07) ** 2 + ((v - 0.40) / 0.07) ** 2)
    col = mix(col, rgb("#ffffff"), np.clip((1.0 - h1) / 0.12, 0, 1))
    col = mix(col, rgb("#fff4fa"), np.clip((1.0 - h2) / 0.15, 0, 1))

    # outside the circle: the eye white, so the disc's edge never shows
    col = mix(col, rgb("#fbf4f8"), np.clip((r - 0.97) / 0.02, 0, 1))

    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), "RGB")

    return img.filter(ImageFilter.GaussianBlur(0.7))


def main():
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "iris.png")
    iris().save(path)
    print("wrote", path)


if __name__ == "__main__":
    main()
