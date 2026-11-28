"""Underwear sets for human.vrm, both pieces drawn in code on the model's own UV shapes.

python3 make_set2.py sets2/<name>.json out2
Trim follows the real outline (as her white set's does), except on the edges that meet
on her body (the two ends at the back, the front tab's end), so nothing doubles up there.
A little garment feel: darker toward the edges, a stitch line inside the trim, a faint grain.
"""
import json, math, random, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import distance_transform_edt

SS = 2
HERE = sys.path[0]
sys.path.insert(0, HERE)
from make_set import blossom, daisy, emblem, hexc, moon, scatter, sparkle, star  # noqa: E402


def seam_region(A, edge, keep, tab):
    """Pixels near the edges that meet another edge on her body."""
    ys, xs = np.where(A)
    reg = np.zeros(A.shape, bool)
    for x in list(range(xs.min(), xs.min() + edge)) + list(range(xs.max() - edge + 1, xs.max() + 1)):
        col = np.where(A[:, x])[0]
        if len(col):
            reg[col.min() + keep:col.max() - keep + 1, x] = True
    if tab:
        low = ys.max()
        cols = np.where(A[low - 2 * SS])[0]
        reg[low - edge + 1:low + 1, cols.min() + keep:cols.max() - keep + 1] = True
    return reg


def make(piece, spec, out):
    src = Image.open(f"{HERE}/cur_{piece}.png").convert("RGBA")
    alpha = np.array(src.getchannel("A"))
    W = alpha.shape[0] * SS
    A = np.array(Image.fromarray(alpha).resize((W, W), Image.NEAREST)) > 8
    # the edges that meet another edge on her (the ends at the back, the front tab's end) carry
    # on past themselves: no trim, no stitches, no darkening there, so the two sides match
    ext = A.copy()
    ys, xs = np.where(A)
    x0, x1, n = xs.min(), xs.max(), 40 * SS
    ext[:, max(0, x0 - n):x0] |= A[:, x0:x0 + 1]
    ext[:, x1 + 1:x1 + 1 + n] |= A[:, x1:x1 + 1]
    if piece == "panties":
        low = ys.max()
        ext[low + 1:low + 1 + n, :] |= A[low:low + 1, :]
    inside = distance_transform_edt(ext)                     # px to the outline, inside

    base = np.array(hexc(spec["base"])[:3], np.float32)
    img = np.empty((W, W, 3), np.float32)
    img[:] = base
    # darker toward the edges: the cups and the waistband read as rounded, not cut out
    shade = 1 - spec.get("edge_shade", 0.10) * np.exp(-inside / (14 * SS))
    img *= shade[..., None]
    # a faint grain
    rnd = np.random.default_rng(spec.get("seed", 1))
    grain = Image.fromarray((rnd.random((W // 2, W // 2)) * 255).astype(np.uint8)).resize((W, W), Image.BILINEAR)
    img *= (1 + (np.array(grain, np.float32) / 255 - 0.5) * spec.get("grain", 0.03))[..., None]

    pim = Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(pim)

    # motifs, whole, clear of the trim and the emblem
    r = spec.get("motif_size", 10) * SS
    pw = spec.get("piping", 4) * SS
    room = Image.fromarray(((inside > r * 1.15 + pw) * 255).astype(np.uint8))
    clear = [(x * SS, y * SS, s * SS * 0.8) for x, y, s in spec.get(f"emblem_{piece}", [])]
    spots = [p for p in scatter(room, spec.get("spacing", 56) * SS, spec.get("seed", 1))
             if all(math.hypot(p[0] - ex, p[1] - ey) > er + r for ex, ey, er in clear)]
    m = spec["motif"]
    for x, y, t in spots:
        col = hexc(spec["motif_color"])
        if m == "blossom":
            blossom(d, x, y, r, col, hexc(spec.get("motif_centre", spec["trim"])))
        elif m == "daisy":
            daisy(d, x, y, r, col, hexc(spec.get("motif_centre", "#f2c94c")))
        elif m == "moon":
            moon(d, x, y, r, col, tuple(int(v) for v in img[int(y), int(x)]) + (255,))
        elif m == "sparkle":
            sparkle(d, x, y, r * (0.55 + 0.6 * t), col)
        elif m == "star":
            star(d, x, y, r * (0.6 + 0.5 * t), col)
    out_rgb = np.array(pim)[..., :3].astype(np.float32)

    # trim round the outline, but not where two edges meet on her
    seams = np.zeros_like(A)
    trim = (inside <= pw) & A & ~seams
    tcol = np.array(hexc(spec["trim"])[:3], np.float32)
    out_rgb[trim] = tcol * shade[trim][:, None] ** 0.5
    # the seam edges carry the plain fabric right to the edge
    out_rgb[seams & (inside <= pw)] = base * shade[seams & (inside <= pw)][:, None]
    # stitches: a dashed line just inside the trim
    sw = spec.get("stitch", 1.2) * SS
    stitch = A & ~seams & (np.abs(inside - (pw + 4 * SS)) < sw / 2)
    yy, xx = np.mgrid[:W, :W]
    stitch &= ((xx + yy) // (6 * SS)) % 2 == 0
    scol = np.array(hexc(spec.get("stitch_color", spec["trim"]))[:3], np.float32)
    out_rgb[stitch] = out_rgb[stitch] * 0.45 + scol * 0.55

    # away from the shape, one flat colour: the grain everywhere made each picture megabytes
    far = distance_transform_edt(~A) > 12 * SS
    out_rgb[far] = base
    im = Image.fromarray(out_rgb.clip(0, 255).astype(np.uint8)).resize(src.size, Image.LANCZOS).convert("RGBA")
    for x, y, size in spec.get(f"emblem_{piece}", []):
        im.alpha_composite(emblem(size, **spec.get("emblem_colors", {})), (int(x - size / 2), int(y - size / 2)))
    # alpha: the outline, solid 4 px past it (the material is a 0.5 cutout)
    a = alpha > 8
    im.putalpha(Image.fromarray(((distance_transform_edt(~a) <= 4) * 255).astype(np.uint8)))
    im.save(out, optimize=True)


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    for piece in ("bra", "panties"):
        make(piece, spec, f"{sys.argv[2]}/{spec['name']}-{piece}.png")
