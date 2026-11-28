"""Underwear sets for human.vrm, drawn in code and cut to the model's own UV shapes.

python3 make_set.py <set.json> <out_dir>
The shapes (alpha) come from the textures already in the model (cur_bra.png,
cur_panties.png), so every set fits exactly the way the current one does.
"""
import json, math, random, sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter

SS = 2                          # drawn at 2x, scaled down: smooth edges
HERE = sys.path[0]


def hexc(c, a=255):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def blossom(d, x, y, r, petal, centre):
    for k in range(5):
        a = -math.pi / 2 + k * 2 * math.pi / 5
        px, py = x + math.cos(a) * r * 0.55, y + math.sin(a) * r * 0.55
        d.ellipse([px - r * 0.5, py - r * 0.5, px + r * 0.5, py + r * 0.5], fill=petal)
    d.ellipse([x - r * 0.22, y - r * 0.22, x + r * 0.22, y + r * 0.22], fill=centre)


def star(d, x, y, r, col):
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.42
        pts.append((x + math.cos(a) * rr, y + math.sin(a) * rr))
    d.polygon(pts, fill=col)


def moon(d, x, y, r, col, bg):
    d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    d.ellipse([x - r * 0.45, y - r * 1.05, x + r * 1.35, y + r * 0.75], fill=bg)


def sparkle(d, x, y, r, col):
    k = 0.18
    d.polygon([(x, y - r), (x + r * k, y - r * k), (x + r, y), (x + r * k, y + r * k),
               (x, y + r), (x - r * k, y + r * k), (x - r, y), (x - r * k, y - r * k)], fill=col)


def daisy(d, x, y, r, petal, centre):
    for k in range(8):
        a = k * math.pi / 4
        px, py = x + math.cos(a) * r * 0.6, y + math.sin(a) * r * 0.6
        d.ellipse([px - r * 0.32, py - r * 0.32, px + r * 0.32, py + r * 0.32], fill=petal)
    d.ellipse([x - r * 0.3, y - r * 0.3, x + r * 0.3, y + r * 0.3], fill=centre)


def emblem(size, violet="#2e2350", mark=None, dot="#ec6fa8"):
    """The Luna emblem as a decal: a crescent opening right, >_ inside, a pink dot."""
    n = size * 4
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = n * 0.42
    cx = cy = n / 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=hexc(violet))
    cut = Image.new("L", (n, n), 0)
    ImageDraw.Draw(cut).ellipse([cx - r * 0.35, cy - r * 0.95, cx + r * 1.45, cy + r * 0.85], fill=255)
    im.putalpha(ImageChops.subtract(im.getchannel("A"), cut))
    w = max(2, int(n * 0.07))
    gx, gy = cx + r * 0.05, cy + r * 0.1                       # >_ in the opening
    mark = hexc(mark or violet)
    d.line([(gx - r * 0.18, gy - r * 0.2), (gx + r * 0.08, gy), (gx - r * 0.18, gy + r * 0.2)],
           fill=mark, width=w, joint="curve")
    d.line([(gx + r * 0.18, gy + r * 0.22), (gx + r * 0.5, gy + r * 0.22)], fill=mark, width=w)
    dr = r * 0.13
    d.ellipse([cx + r * 0.62 - dr, cy - r * 0.62 - dr, cx + r * 0.62 + dr, cy - r * 0.62 + dr], fill=hexc(dot))
    return im.resize((size, size), Image.LANCZOS)


def scatter(mask, spacing, seed):
    """Jittered grid of points inside the mask."""
    rnd = random.Random(seed)
    w, h = mask.size
    px = mask.load()
    out = []
    row = 0
    for y in range(0, h, spacing):
        off = spacing // 2 if row % 2 else 0
        for x in range(off, w, spacing):
            jx, jy = x + rnd.uniform(-.25, .25) * spacing, y + rnd.uniform(-.25, .25) * spacing
            if 0 <= jx < w and 0 <= jy < h and px[int(jx), int(jy)] > 0:
                out.append((jx, jy, rnd.uniform(0, 1)))
        row += 1
    return out


def erode(mask, k):
    """mask shrunk by k pixels (a distance transform: MinFilter is far too slow at this size)."""
    import numpy as np
    from scipy.ndimage import distance_transform_edt
    d = distance_transform_edt(np.array(mask) > 0)
    return Image.fromarray(((d > k) * 255).astype("uint8"))


def make(piece, spec, out):
    src = Image.open(f"{HERE}/cur_{piece}.png").convert("RGBA")
    alpha = src.getchannel("A")
    W = src.size[0] * SS
    mask = alpha.resize((W, W), Image.NEAREST).point(lambda v: 255 if v > 8 else 0)
    base = hexc(spec["base"])
    im = Image.new("RGBA", (W, W), base)
    d = ImageDraw.Draw(im)
    motif = spec.get("motif")
    r = spec.get("motif_size", 11) * SS
    room = erode(mask, r * 1.2)     # whole motifs only, clear of the piping
    clear = [(x * SS, y * SS, size * SS * 0.9) for x, y, size in spec.get(f"emblem_{piece}", [])]
    spots = [p for p in scatter(room, spec.get("spacing", 56) * SS, spec.get("seed", 1))
             if all(math.hypot(p[0] - ex, p[1] - ey) > er + r for ex, ey, er in clear)]
    for x, y, t in spots:
        if motif == "blossom":
            blossom(d, x, y, r, hexc(spec["motif_color"]), hexc(spec.get("motif_centre", spec["trim"])))
        elif motif == "star":
            star(d, x, y, r * (0.6 + 0.6 * t), hexc(spec["motif_color"]))
        elif motif == "moon":
            moon(d, x, y, r, hexc(spec["motif_color"]), base)
        elif motif == "sparkle":
            sparkle(d, x, y, r * (0.6 + 0.6 * t), hexc(spec["motif_color"]))
        elif motif == "daisy":
            daisy(d, x, y, r, hexc(spec["motif_color"]), hexc(spec.get("motif_centre", "#f2c94c")))
    # piping round the edge, like the current set
    pw = spec.get("piping", 5) * SS
    inner = erode(mask, pw)
    edge = ImageChops.subtract(mask, inner)
    if spec.get("piping_edges") == "top":     # only edges with the outside above them (waistband, cup tops)
        import numpy as np
        m = np.array(mask) > 0
        seen = np.cumsum(m, axis=0)          # mask pixels at or above, per column
        top = m & (seen <= pw)               # the first pw pixels from the top of each column
        edge = Image.fromarray((top * 255).astype("uint8"))
    im.paste(Image.new("RGBA", (W, W), hexc(spec["trim"])), (0, 0), edge)
    im = im.resize(src.size, Image.LANCZOS)
    for x, y, size in spec.get(f"emblem_{piece}", []):
        e = emblem(size, **spec.get("emblem_colors", {}))
        im.alpha_composite(e, (int(x - size / 2), int(y - size / 2)))
    im.putalpha(alpha)                       # the model's own outline, untouched
    im.save(out)


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    for piece in spec.get("pieces", ("bra", "panties")):
        make(piece, spec, f"{sys.argv[2]}/{spec['name']}-{piece}.png")
