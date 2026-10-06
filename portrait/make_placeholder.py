"""Build portrait/models/placeholder.vrm - a stand-in Luna, in her colours.

    python portrait/make_placeholder.py

Not the real model: that one comes from VRoid Studio (see
portrait/design/README.md). This exists so the portrait window has
someone in it from day one, and as a test of everything the window
drives - it has every part the animation code looks for:

  * humanoid bones (VRM 1.0), with the eyes as bones so look-at works
  * Ear_L / Ear_R nodes on the head, for the ear twitches
  * morph-target expressions: blink, blinkLeft, blinkRight, the five
    mouth shapes aa ih ou ee oh, happy, sad, angry, relaxed, surprised

Everything is generated from numbers - no art files - and written as a
plain GLB with the VRMC_vrm extension, which is all a .vrm is.
"""
import json
import math
import os
import struct

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "models", "placeholder.vrm")


def hexc(h, a=1.0):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [a]


SKIN = hexc("#f6e4ea")
SKIN_SHADE = hexc("#e8c3cf")
HAIR_TOP = hexc("#1d1638")
HAIR_MID = hexc("#3b2a72")
HAIR_TIP = hexc("#d65fc4")
HAIR_SHINE = hexc("#6a52b8")
EAR_OUT = hexc("#231a40")
EAR_IN = hexc("#f2a7c6")
FUR = hexc("#fbf3f7")
SCLERA = hexc("#fff8fb")
IRIS_RIM = hexc("#8e1f55")
IRIS_MID = hexc("#e2477f")
IRIS_LIGHT = hexc("#ff9cc2")
PUPIL = hexc("#3d0a26")
LASH = hexc("#17101f")
MOUTH = hexc("#6a1f33")
FANG = hexc("#ffffff")
BLUSH = hexc("#ff7aa6", 0.35)
CHOKER = hexc("#141018")
RING = hexc("#c9c4d6")
TOP = hexc("#1a1424")

HEAD_C = np.array([0.0, 1.47, 0.0])
HEAD_R = np.array([0.088, 0.100, 0.092])


# ---------------------------------------------------------------------------
# Mesh building
# ---------------------------------------------------------------------------
class Mesh:
    def __init__(self, name, double=False, blend=False):
        self.name, self.double, self.blend = name, double, blend
        self.pos, self.col, self.idx = [], [], []
        self.morphs = {}   # name -> list of deltas, filled at the end

    def v(self, p, c):
        self.pos.append(list(map(float, p)))
        self.col.append(list(map(float, c)))
        return len(self.pos) - 1

    def tri(self, a, b, c):
        self.idx += [a, b, c]

    def quad(self, a, b, c, d):
        self.tri(a, b, c)
        self.tri(a, c, d)

    def normals(self):
        P = np.array(self.pos)
        N = np.zeros_like(P)
        I = np.array(self.idx).reshape(-1, 3)
        fn = np.cross(P[I[:, 1]] - P[I[:, 0]], P[I[:, 2]] - P[I[:, 0]])
        for k in range(3):
            np.add.at(N, I[:, k], fn)
        n = np.linalg.norm(N, axis=1, keepdims=True)
        n[n == 0] = 1
        return N / n


def head_point(u, v):
    """Lat-long on the head, shaped: rounder on top, tapering to an anime chin."""
    x = math.cos(v) * math.sin(u)
    y = math.sin(v)
    z = math.cos(v) * math.cos(u)
    p = np.array([x, y, z]) * HEAD_R

    if y < 0:
        t = min(1.0, -y)
        p[0] *= 1 - 0.40 * t ** 1.25
        p[2] *= 1 - 0.12 * t
        p[1] *= 1 + 0.18 * t ** 2  # a longer jaw
        if z > 0:  # chin forward a touch
            p[2] += 0.010 * t ** 2 * z

    return p + HEAD_C


def build_head():
    m = Mesh("Face")
    U, V = 72, 48
    grid = {}

    for j in range(V + 1):
        v = -math.pi / 2 + math.pi * j / V
        for i in range(U + 1):
            u = -math.pi + 2 * math.pi * i / U
            p = head_point(u, v)
            grid[i, j] = m.v(p, SKIN)

    for j in range(V):
        for i in range(U):
            m.quad(grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1])

    return m


_front = None


def surface_z(x, y):
    """How far forward the face is at (x, y) - for putting features on it."""
    global _front
    if _front is None:
        pts = []
        for j in range(200):
            v = -math.pi / 2 + math.pi * j / 199
            for i in range(160):
                u = -math.pi / 2 + math.pi * i / 159
                pts.append(head_point(u, v))
        _front = np.array(pts)
    d = (_front[:, 0] - x) ** 2 + (_front[:, 1] - y) ** 2
    k = np.argsort(d)[:4]
    w = 1 / (np.sqrt(d[k]) + 1e-6)
    return float((_front[k, 2] * w).sum() / w.sum())


def on_face(x, y, lift):
    return np.array([x, y, surface_z(x, y) + lift])


def disc(m, cx, cy, rx, ry, lift, color, edge=None, n=28, rot=0.0):
    c = m.v(on_face(cx, cy, lift), color)
    ring = []
    for k in range(n):
        a = 2 * math.pi * k / n
        dx, dy = rx * math.cos(a), ry * math.sin(a)
        dx, dy = dx * math.cos(rot) - dy * math.sin(rot), dx * math.sin(rot) + dy * math.cos(rot)
        ring.append(m.v(on_face(cx + dx, cy + dy, lift), edge or color))
    for k in range(n):
        m.tri(c, ring[k], ring[(k + 1) % n])
    return c, ring


# Eyes: positions in head space
EYE_Y = 1.452
EYE_X = 0.035
EYE_W = 0.0215
EYE_H = 0.0255


def eye_top(x, side):
    """The upper lid line: a flattened arch, rising towards the outer corner."""
    t = (x - side * EYE_X) / EYE_W
    t = max(-1.0, min(1.0, t))
    outer = t * side  # +1 at the outer corner
    return EYE_Y + EYE_H * (0.95 * math.sqrt(max(0, 1 - t * t)) ** 0.6) * 0.62 + 0.004 * outer


def eye_bottom(x, side):
    t = (x - side * EYE_X) / EYE_W
    t = max(-1.0, min(1.0, t))
    return EYE_Y - EYE_H * 0.55 * math.sqrt(max(0, 1 - t * t)) ** 0.8


def build_sclera():
    m = Mesh("Sclera")
    for side in (1, -1):
        cols = 16
        for i in range(cols):
            x0 = side * EYE_X - EYE_W + 2 * EYE_W * i / cols
            x1 = side * EYE_X - EYE_W + 2 * EYE_W * (i + 1) / cols
            a = m.v(on_face(x0, eye_bottom(x0, side), 0.0012), SCLERA)
            b = m.v(on_face(x1, eye_bottom(x1, side), 0.0012), SCLERA)
            c = m.v(on_face(x1, eye_top(x1, side), 0.0012), SCLERA)
            d = m.v(on_face(x0, eye_top(x0, side), 0.0012), SCLERA)
            m.quad(a, b, c, d)
    return m


def build_iris(side, pivot):
    """In the eye bone's local space: a big anime iris, a slit-ish pupil,
    two highlights. The bone sits behind the face, so turning it slides
    the iris across the eye."""
    m = Mesh("Iris_" + ("L" if side > 0 else "R"))
    depth = surface_z(side * EYE_X, EYE_Y) + 0.0019 - pivot[2]
    rx, ry = 0.0125, 0.0175

    def ring(r_scale, color, z=0.0, n=32, cx=0.0, cy=0.0, ryk=1.0):
        pts = []
        for k in range(n):
            a = 2 * math.pi * k / n
            pts.append(m.v([cx + rx * r_scale * math.cos(a), cy + ry * r_scale * ryk * math.sin(a), depth + z], color))
        return pts

    centre = m.v([0, -0.002, depth], IRIS_LIGHT)
    rings = [ring(0.35, IRIS_LIGHT), ring(0.75, IRIS_MID), ring(1.0, IRIS_RIM)]
    n = 32
    for k in range(n):
        m.tri(centre, rings[0][k], rings[0][(k + 1) % n])
        for r in range(2):
            m.quad(rings[r][k], rings[r + 1][k], rings[r + 1][(k + 1) % n], rings[r][(k + 1) % n])

    # pupil - a tall soft oval
    pc = m.v([0, 0.001, depth + 0.0002], PUPIL)
    pr = []
    for k in range(20):
        a = 2 * math.pi * k / 20
        pr.append(m.v([0.0042 * math.cos(a), 0.001 + 0.0085 * math.sin(a), depth + 0.0002], PUPIL))
    for k in range(20):
        m.tri(pc, pr[k], pr[(k + 1) % 20])

    # highlights
    for (hx, hy, hr) in ((-0.0045 * side, 0.0065, 0.0032), (0.004 * side, -0.007, 0.0016)):
        hc = m.v([hx, hy, depth + 0.0004], FANG)
        hrng = [m.v([hx + hr * math.cos(2 * math.pi * k / 12), hy + hr * math.sin(2 * math.pi * k / 12),
                     depth + 0.0004], FANG) for k in range(12)]
        for k in range(12):
            m.tri(hc, hrng[k], hrng[(k + 1) % 12])
    return m


def build_lids():
    """Upper lids with lashes. Open, the lid is a lash band on the arch;
    each blink morph pulls skin down over the eye and the lashes with it."""
    m = Mesh("Lids")
    open_pos, closed_pos = {}, {}
    cols = 18
    lash = 0.0034

    for side in (1, -1):
        rows = [[], [], [], []]
        for i in range(cols + 1):
            t = i / cols
            # a little past the eye on both ends, more at the outer corner (the wing)
            x = side * EYE_X + (-EYE_W - 0.002 + (2 * EYE_W + 0.009) * t) * side
            xt = max(side * EYE_X - EYE_W, min(side * EYE_X + EYE_W, x)) if side > 0 else \
                min(side * EYE_X + EYE_W, max(side * EYE_X - EYE_W, x))
            top = eye_top(xt, side)
            wing = max(0, (abs(x - side * EYE_X) - EYE_W)) * 0.9
            above = EYE_Y + EYE_H * 0.9
            closed_line = EYE_Y - EYE_H * 0.18 - 0.003 * math.sin(math.pi * t)
            # open: skin rows squashed just above the lash line
            o = [above, top + lash + 0.0004, top + lash + wing, top + wing * 0.6]
            c = [above, closed_line + lash, closed_line + lash, closed_line]
            for r in range(4):
                color = SKIN if r < 2 else LASH
                vi = m.v(on_face(x, o[r], 0.0026 + 0.0004 * r), color)
                open_pos[vi] = on_face(x, o[r], 0.0026 + 0.0004 * r)
                closed_pos[vi] = on_face(x, c[r], 0.0026 + 0.0004 * r)
                rows[r].append((vi, side))
        for i in range(cols):
            for r in (0, 2):
                a, b = rows[r][i][0], rows[r][i + 1][0]
                c, d = rows[r + 1][i + 1][0], rows[r + 1][i][0]
                m.quad(a, b, c, d) if side > 0 else m.quad(b, a, d, c)

    def morph(which_side, amount=1.0, squint=False):
        deltas = []
        for vi in range(len(m.pos)):
            side = 1 if m.pos[vi][0] > 0 else -1
            if which_side not in (0, side):
                deltas.append([0, 0, 0])
                continue
            d = (closed_pos[vi] - open_pos[vi]) * amount
            if squint:  # happy eyes: lids drop and the lash line bows up
                d = d * 0.55
            deltas.append(list(d))
        return deltas

    m.morphs = {"blinkLeft": morph(1), "blinkRight": morph(-1), "happyEyes": morph(0, 1.0, True)}
    return m


def build_mouth():
    m = Mesh("Mouth")
    n = 28
    cx, cy = 0.0, 1.393
    rx = 0.0115
    base_ry = 0.0012
    lift = 0.0016
    centre = m.v(on_face(cx, cy, lift), MOUTH)
    ring = []
    angles = [2 * math.pi * k / n for k in range(n)]
    for a in angles:
        ring.append(m.v(on_face(cx + rx * math.cos(a), cy + base_ry * math.sin(a), lift), MOUTH))
    for k in range(n):
        m.tri(centre, ring[k], ring[(k + 1) % n])

    # the fang: a little white tooth on the left of the upper lip
    fx = -0.0055
    f = [m.v(on_face(fx - 0.0018, cy + base_ry, lift + 0.0004), FANG),
         m.v(on_face(fx + 0.0018, cy + base_ry, lift + 0.0004), FANG),
         m.v(on_face(fx, cy - 0.0032, lift + 0.0004), FANG)]
    m.tri(f[0], f[2], f[1])

    def shape(sx, top, bottom, smile=0.0, frown=0.0, round_=0.0):
        """Deltas for one mouth shape: width scale, how far the top and
        bottom edges open, corners up (smile) or down (frown)."""
        out = []
        for vi in range(len(m.pos)):
            if vi == centre:
                out.append([0.0, (bottom * -0.5 + top * 0.5) * 0.4, 0.0])
                continue
            if vi in f:
                # the fang rides on the upper lip
                up = top
                out.append([0.0, up + smile * 0.3 * (fx / rx) ** 2 * 0.012, 0.0])
                continue
            k = ring.index(vi)
            a = angles[k]
            c, s = math.cos(a), math.sin(a)
            r_round = 1 - round_ * 0.45
            x = rx * c * sx * r_round
            y = (top if s > 0 else bottom) * abs(s) ** (0.8 - round_ * 0.3) * (1 if s > 0 else -1)
            y += smile * 0.006 * c * c - frown * 0.004 * c * c
            new = on_face(cx + x, cy + base_ry * s + y, lift)
            old = np.array(m.pos[vi])
            out.append(list(new - old))
        return out

    m.morphs = {
        "aa": shape(0.85, 0.004, 0.011),
        "ih": shape(1.05, 0.002, 0.004),
        "ou": shape(0.55, 0.003, 0.006, round_=1.0),
        "ee": shape(1.15, 0.0025, 0.005, smile=0.3),
        "oh": shape(0.7, 0.004, 0.009, round_=0.6),
        "smile": shape(1.1, 0.0015, 0.004, smile=1.0),
        "frown": shape(0.9, 0.0, 0.0006, frown=1.0),
        "gasp": shape(0.5, 0.005, 0.008, round_=1.0),
    }
    return m


def build_face_details():
    m = Mesh("FaceDetails")
    # lower lash dots and brows
    for side in (1, -1):
        for i in range(6):
            x = side * (EYE_X - EYE_W * 0.6 + EYE_W * 1.3 * i / 5)
            y = eye_bottom(x, side) - 0.0012
            disc(m, x, y, 0.0009, 0.0005, 0.0014, LASH, n=8)
        # brow: a thin arc, mostly hidden by bangs
        pts = []
        for i in range(10):
            t = i / 9
            x = side * (EYE_X - 0.016 + 0.034 * t)
            y = EYE_Y + 0.030 + 0.004 * math.sin(math.pi * t) - 0.003 * t
            pts.append((x, y))
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            a = m.v(on_face(x0, y0 + 0.0012, 0.0012), HAIR_MID)
            b = m.v(on_face(x1, y1 + 0.0012, 0.0012), HAIR_MID)
            c = m.v(on_face(x1, y1 - 0.0012, 0.0012), HAIR_MID)
            d = m.v(on_face(x0, y0 - 0.0012, 0.0012), HAIR_MID)
            m.quad(a, b, c, d) if side > 0 else m.quad(b, a, d, c)
        # nose hint
    disc(m, 0.0, 1.420, 0.0012, 0.0008, 0.0010, SKIN_SHADE, n=8)
    return m


def build_blush():
    m = Mesh("Blush", blend=True)
    for side in (1, -1):
        c = m.v(on_face(side * 0.047, 1.423, 0.0018), BLUSH)
        ring = [m.v(on_face(side * 0.047 + 0.016 * math.cos(2 * math.pi * k / 24),
                            1.423 + 0.007 * math.sin(2 * math.pi * k / 24), 0.0018),
                    BLUSH[:3] + [0.0]) for k in range(24)]
        for k in range(24):
            m.tri(c, ring[k], ring[(k + 1) % 24]) if side > 0 else m.tri(c, ring[(k + 1) % 24], ring[k])
    return m


# ---------------------------------------------------------------------------
# Hair
# ---------------------------------------------------------------------------
def bezier(p0, p1, p2, p3, t):
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def hair_color(t, shine=0.0):
    """Top-to-tip gradient: near-black indigo, violet, then magenta tips."""
    if t < 0.55:
        k = t / 0.55
        c = [HAIR_TOP[i] * (1 - k) + HAIR_MID[i] * k for i in range(3)]
    else:
        k = (t - 0.55) / 0.45
        k = k ** 1.4
        c = [HAIR_MID[i] * (1 - k) + HAIR_TIP[i] * k for i in range(3)]
    c = [c[i] * (1 - shine) + HAIR_SHINE[i] * shine for i in range(3)]
    return c + [1.0]


def strand(m, ctrl, width, segs=14, out_from=None, tip_t=0.55, shine_at=None):
    """A ribbon along a cubic Bezier, tapering to a point."""
    ctrl = [np.array(c, dtype=float) for c in ctrl]
    pts = [bezier(*ctrl, s / segs) for s in range(segs + 1)]
    left, right = [], []
    for s, p in enumerate(pts):
        t = s / segs
        tan = pts[min(s + 1, segs)] - pts[max(s - 1, 0)]
        tan /= np.linalg.norm(tan) + 1e-9
        out = p - (out_from if out_from is not None else HEAD_C)
        out /= np.linalg.norm(out) + 1e-9
        side = np.cross(tan, out)
        side /= np.linalg.norm(side) + 1e-9
        w = width * (1 - t ** 1.6) * (1 if t < 0.97 else 0.2)
        shine = 0.0
        if shine_at is not None:
            shine = max(0.0, 1 - abs(t - shine_at) / 0.08) * 0.55
        col = hair_color(tip_t * t + (1 - tip_t) * t ** 2.2, shine)
        left.append(m.v(p - side * w, col))
        right.append(m.v(p + side * w, col))
    for s in range(segs):
        m.quad(left[s], right[s], right[s + 1], left[s + 1])


def build_hair():
    m = Mesh("Hair", double=True)

    # Cap: a shell over the head, open at the face.
    U, V = 60, 36
    grid = {}
    for j in range(V + 1):
        v = -0.25 + (math.pi / 2 + 0.25) * j / V
        for i in range(U + 1):
            u = -math.pi + 2 * math.pi * i / U
            x = math.cos(v) * math.sin(u)
            y = math.sin(v)
            z = math.cos(v) * math.cos(u)
            p = HEAD_C + np.array([x, y, z]) * (HEAD_R + 0.011)
            p[1] += 0.004
            shine = max(0.0, 1 - abs(y - 0.62) / 0.06) * 0.6 if z > -0.3 else 0.0
            grid[i, j] = m.v(p, hair_color(0.1 + 0.25 * (1 - y), shine))
    for j in range(V):
        for i in range(U):
            u = -math.pi + 2 * math.pi * (i + 0.5) / U
            v = -0.25 + (math.pi / 2 + 0.25) * (j + 0.5) / V
            front = math.cos(u) > 0.25 and math.sin(v) < 0.55
            if front:
                continue
            m.quad(grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1])

    # Long back hair: a curtain of strands down past the shoulders.
    for k in range(17):
        a = -1.25 + 2.5 * k / 16           # around the back of the head
        r = 0.105
        top = HEAD_C + np.array([r * math.sin(a) * 0.95, 0.055, -r * math.cos(a) * 0.9])
        length = 0.42 + 0.05 * math.sin(k * 1.7)
        bottom = np.array([top[0] * 1.45, HEAD_C[1] - length, -0.06 - 0.03 * math.cos(a)])
        strand(m, [top, top + [top[0] * 0.3, -0.12, -0.03], bottom + [0, 0.15, -0.02], bottom],
               0.026, segs=18, out_from=np.array([0, top[1] - 0.1, 0.1]), tip_t=0.9)

    # Side locks framing the face, pink at the ends.
    for side in (1, -1):
        for k, (dx, dz, ln) in enumerate(((0.0, 0.035, 0.27), (0.012, 0.010, 0.32), (0.02, -0.01, 0.30))):
            top = HEAD_C + [side * (0.080 + dx), 0.040, dz]
            bot = HEAD_C + [side * (0.098 + dx * 1.5), -ln, dz + 0.02]
            strand(m, [top, top + [side * 0.018, -0.06, 0.012], bot + [side * 0.004, 0.10, 0.0], bot],
                   0.016 - 0.002 * k, segs=16, tip_t=0.85)

    # Bangs: hime-ish, straight across at the brows, a gap at each eye.
    tips = [-0.075, -0.058, -0.040, -0.022, -0.008, 0.008, 0.022, 0.040, 0.058, 0.075]
    for k, tx in enumerate(tips):
        ty = EYE_Y + 0.022 - 0.006 * (abs(tx) > 0.06) + 0.003 * math.sin(k * 2.3)
        tip = on_face(tx, ty, 0.010)
        root = HEAD_C + np.array([tx * 0.35, 0.098, 0.03])
        mid1 = root + np.array([tx * 0.4, 0.010, 0.07])
        mid2 = on_face(tx * 0.98, ty + 0.035, 0.016)
        strand(m, [root, mid1, mid2, tip], 0.0125, segs=14, tip_t=0.25, shine_at=0.32)

    return m


def build_ear(side):
    """A cat ear in the Ear node's local space, base at the origin."""
    m = Mesh("Ear_" + ("L" if side > 0 else "R"), double=True)
    w, h, d = 0.032, 0.072, 0.014
    base = [np.array([-w, 0, 0.004]), np.array([w, 0, 0.004]), np.array([0, 0, -d])]
    tip = np.array([0.006 * side, h, -0.002])
    inner_tip = tip * 0.82 + np.array([0, -0.004, 0.006])
    # back of the ear
    b = [m.v(p, EAR_OUT) for p in base] + [m.v(tip, EAR_OUT)]
    m.tri(b[0], b[2], b[3])
    m.tri(b[2], b[1], b[3])
    # front (inside of the ear): dark rim, pink inside
    rim = [m.v(base[0], EAR_OUT), m.v(base[1], EAR_OUT), m.v(tip, EAR_OUT)]
    ins = [m.v(base[0] * 0.72 + [0, 0.006, 0.004], EAR_IN), m.v(base[1] * 0.72 + [0, 0.006, 0.004], EAR_IN),
           m.v(inner_tip, EAR_IN)]
    m.quad(rim[0], rim[1], ins[1], ins[0])
    m.quad(rim[1], rim[2], ins[2], ins[1])
    m.quad(rim[2], rim[0], ins[0], ins[2])
    m.tri(ins[0], ins[1], ins[2])
    # fur tufts
    for fx in (-0.012, -0.002, 0.009):
        a = m.v([fx - 0.006, 0.004, 0.009], FUR)
        b2 = m.v([fx + 0.006, 0.004, 0.009], FUR)
        c = m.v([fx * 1.4 + 0.002 * side, 0.036 + 0.006 * (fx == -0.002), 0.010], FUR[:3] + [1.0])
        m.tri(a, b2, c)
    return m


def build_body():
    m = Mesh("Body")
    # neck
    for j in range(8):
        for i in range(24):
            pass
    ring = lambda y, r, c, n=24, zoff=0.0: [m.v([r * math.sin(2 * math.pi * k / n), y,
                                                 zoff + r * 0.9 * math.cos(2 * math.pi * k / n)], c) for k in range(n)]
    rings = [ring(1.30, 0.031, SKIN), ring(1.33, 0.029, SKIN), ring(1.40, 0.027, SKIN)]
    for a, b in zip(rings, rings[1:]):
        for k in range(24):
            m.quad(a[k], a[(k + 1) % 24], b[(k + 1) % 24], b[k])
    # choker
    ch = [ring(1.333, 0.0302, CHOKER), ring(1.347, 0.0295, CHOKER)]
    for k in range(24):
        m.quad(ch[0][k], ch[0][(k + 1) % 24], ch[1][(k + 1) % 24], ch[1][k])
    rc = m.v([0, 1.329, 0.031], RING)
    rr = [m.v([0.004 * math.cos(2 * math.pi * k / 10), 1.329 + 0.004 * math.sin(2 * math.pi * k / 10), 0.0305], RING)
          for k in range(10)]
    for k in range(10):
        m.tri(rc, rr[k], rr[(k + 1) % 10])
    # shoulders and chest: an ellipsoid cut at the bottom, dark top below the collarbones
    U, V = 48, 20
    grid = {}
    for j in range(V + 1):
        v = -0.7 + 1.6 * j / V
        for i in range(U + 1):
            u = -math.pi + 2 * math.pi * i / U
            x, y, z = math.cos(v) * math.sin(u), math.sin(v), math.cos(v) * math.cos(u)
            p = np.array([0.0, 1.21, -0.01]) + np.array([x * 0.175, y * 0.11, z * 0.085])
            if y > 0.55:
                p[0] *= 0.6 + 0.4 * (1 - (y - 0.55) / 0.45)
            col = TOP if p[1] < 1.205 and abs(p[0]) < 0.13 else SKIN
            grid[i, j] = m.v(p, col)
    for j in range(V):
        for i in range(U):
            m.quad(grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1])
    return m


# ---------------------------------------------------------------------------
# glTF / VRM writing
# ---------------------------------------------------------------------------
class GLB:
    def __init__(self):
        self.bin = bytearray()
        self.views, self.accessors = [], []

    def _add(self, data, target=None):
        while len(self.bin) % 4:
            self.bin += b"\0"
        off = len(self.bin)
        self.bin += data
        view = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target:
            view["target"] = target
        self.views.append(view)
        return len(self.views) - 1

    def acc(self, arr, kind, comp=5126, target=34962, minmax=False):
        arr = np.ascontiguousarray(arr)
        view = self._add(arr.tobytes(), target)
        a = {"bufferView": view, "componentType": comp, "count": len(arr), "type": kind}
        if minmax:
            a["min"] = arr.min(axis=0).tolist()
            a["max"] = arr.max(axis=0).tolist()
        self.accessors.append(a)
        return len(self.accessors) - 1


def write(nodes, meshes_on, out):
    """nodes: list of dicts {name, t, children, mesh?}; meshes_on: {node index: Mesh}."""
    g = GLB()
    materials = [
        {"name": "toon", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 1}},
        {"name": "toon_double", "doubleSided": True,
         "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 1}},
        {"name": "blush", "alphaMode": "BLEND",
         "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 1}},
    ]
    gl_meshes, morph_index = [], {}

    for node_i, (mesh, offset) in meshes_on.items():
        P = np.array(mesh.pos, dtype=np.float32) - np.array(offset, dtype=np.float32)
        N = mesh.normals().astype(np.float32)
        C = np.array(mesh.col, dtype=np.float32)
        I = np.array(mesh.idx, dtype=np.uint32)
        prim = {"attributes": {"POSITION": g.acc(P, "VEC3", minmax=True), "NORMAL": g.acc(N, "VEC3"),
                               "COLOR_0": g.acc(C, "VEC4")},
                "indices": g.acc(I, "SCALAR", comp=5125, target=34963),
                "material": 2 if mesh.blend else (1 if mesh.double else 0)}
        names = list(mesh.morphs)
        if names:
            prim["targets"] = [{"POSITION": g.acc(np.array(mesh.morphs[n], dtype=np.float32), "VEC3", minmax=True)}
                               for n in names]
            for k, n in enumerate(names):
                morph_index[n] = (node_i, k)
        gm = {"name": mesh.name, "primitives": [prim]}
        if names:
            gm["extras"] = {"targetNames": names}
            gm["weights"] = [0.0] * len(names)
        gl_meshes.append(gm)
        nodes[node_i]["mesh"] = len(gl_meshes) - 1

    def bind(*pairs):
        return [{"node": morph_index[n][0], "index": morph_index[n][1], "weight": w} for n, w in pairs if n in morph_index]

    def expr(*pairs, binary=False, block_blink="none", block_mouth="none"):
        return {"morphTargetBinds": bind(*pairs), "isBinary": binary,
                "overrideBlink": block_blink, "overrideLookAt": "none", "overrideMouth": block_mouth}

    expressions = {
        "blink": expr(("blinkLeft", 1.0), ("blinkRight", 1.0)),
        "blinkLeft": expr(("blinkLeft", 1.0)),
        "blinkRight": expr(("blinkRight", 1.0)),
        "aa": expr(("aa", 1.0)), "ih": expr(("ih", 1.0)), "ou": expr(("ou", 1.0)),
        "ee": expr(("ee", 1.0)), "oh": expr(("oh", 1.0)),
        "happy": expr(("happyEyes", 1.0), ("smile", 1.0), block_blink="blend"),
        "relaxed": expr(("happyEyes", 0.4), ("smile", 0.5)),
        "sad": expr(("frown", 1.0), ("blinkLeft", 0.2), ("blinkRight", 0.2)),
        "angry": expr(("frown", 0.6), ("blinkLeft", 0.35), ("blinkRight", 0.35)),
        "surprised": expr(("gasp", 1.0)),
    }

    human = {n["human"]: {"node": i} for i, n in enumerate(nodes) if n.get("human")}
    gltf_nodes = []
    for n in nodes:
        gn = {"name": n["name"], "translation": [float(x) for x in n["t"]]}
        if n.get("children"):
            gn["children"] = n["children"]
        if "mesh" in n:
            gn["mesh"] = n["mesh"]
        if "rotation" in n:
            gn["rotation"] = [float(x) for x in n["rotation"]]
        gltf_nodes.append(gn)

    rng = {"inputMaxValue": 90.0, "outputScale": 9.0}
    gltf = {
        "asset": {"version": "2.0", "generator": "luna-local-agent make_placeholder.py"},
        "extensionsUsed": ["VRMC_vrm"],
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": gltf_nodes, "meshes": gl_meshes, "materials": materials,
        "accessors": g.accessors, "bufferViews": g.views,
        "buffers": [{"byteLength": len(g.bin)}],
        "extensions": {"VRMC_vrm": {
            "specVersion": "1.0",
            "meta": {"name": "Luna (placeholder)", "version": "1", "authors": ["luna-local-agent"],
                     "licenseUrl": "https://vrm.dev/licenses/1.0/", "avatarPermission": "onlyAuthor",
                     "allowExcessivelyViolentUsage": False, "allowExcessivelySexualUsage": False,
                     "commercialUsage": "personalNonProfit", "allowPoliticalOrReligiousUsage": False,
                     "allowAntisocialOrHateUsage": False, "creditNotation": "required",
                     "allowRedistribution": False, "modification": "prohibited"},
            "humanoid": {"humanBones": human},
            "lookAt": {"type": "bone", "offsetFromHeadBone": [0.0, 0.035, 0.08],
                       "rangeMapHorizontalInner": rng, "rangeMapHorizontalOuter": rng,
                       "rangeMapVerticalDown": rng, "rangeMapVerticalUp": rng},
            "expressions": {"preset": expressions},
        }},
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    binb = bytes(g.bin)
    while len(binb) % 4:
        binb += b"\0"
    total = 12 + 8 + len(js) + 8 + len(binb)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(binb), 0x004E4942) + binb)


def main():
    # Skeleton: world positions, then made local.
    world = {}
    spec = [  # name, human bone, parent, world position
        ("Root", None, None, (0, 0, 0)),
        ("Hips", "hips", "Root", (0, 0.92, 0)),
        ("Spine", "spine", "Hips", (0, 1.02, 0)),
        ("Chest", "chest", "Spine", (0, 1.14, 0)),
        ("UpperChest", "upperChest", "Chest", (0, 1.24, 0)),
        ("Neck", "neck", "UpperChest", (0, 1.31, 0)),
        ("Head", "head", "Neck", (0, 1.40, 0)),
        ("Eye_L", "leftEye", "Head", (EYE_X, EYE_Y, 0.045)),
        ("Eye_R", "rightEye", "Head", (-EYE_X, EYE_Y, 0.045)),
        ("Ear_L", None, "Head", (0.060, 1.535, -0.010)),
        ("Ear_R", None, "Head", (-0.060, 1.535, -0.010)),
        ("Shoulder_L", "leftShoulder", "UpperChest", (0.03, 1.29, 0)),
        ("UpperArm_L", "leftUpperArm", "Shoulder_L", (0.15, 1.27, 0)),
        ("LowerArm_L", "leftLowerArm", "UpperArm_L", (0.17, 1.02, 0)),
        ("Hand_L", "leftHand", "LowerArm_L", (0.18, 0.80, 0)),
        ("Shoulder_R", "rightShoulder", "UpperChest", (-0.03, 1.29, 0)),
        ("UpperArm_R", "rightUpperArm", "Shoulder_R", (-0.15, 1.27, 0)),
        ("LowerArm_R", "rightLowerArm", "UpperArm_R", (-0.17, 1.02, 0)),
        ("Hand_R", "rightHand", "LowerArm_R", (-0.18, 0.80, 0)),
        ("UpperLeg_L", "leftUpperLeg", "Hips", (0.08, 0.88, 0)),
        ("LowerLeg_L", "leftLowerLeg", "UpperLeg_L", (0.08, 0.48, 0)),
        ("Foot_L", "leftFoot", "LowerLeg_L", (0.08, 0.08, 0)),
        ("UpperLeg_R", "rightUpperLeg", "Hips", (-0.08, 0.88, 0)),
        ("LowerLeg_R", "rightLowerLeg", "UpperLeg_R", (-0.08, 0.48, 0)),
        ("Foot_R", "rightFoot", "LowerLeg_R", (-0.08, 0.08, 0)),
    ]
    index = {name: i for i, (name, *_r) in enumerate(spec)}
    nodes = []
    for name, human, parent, pos in spec:
        world[name] = np.array(pos, dtype=float)
        local = world[name] - (world[parent] if parent else 0)
        nodes.append({"name": name, "human": human, "t": local, "children": []})
    for name, human, parent, pos in spec:
        if parent:
            nodes[index[parent]]["children"].append(index[name])

    def attach(mesh, bone, name=None):
        nodes.append({"name": name or mesh.name, "t": [0, 0, 0], "children": []})
        nodes[index[bone]]["children"].append(len(nodes) - 1)
        return len(nodes) - 1, world[bone]

    meshes_on = {}
    for mesh in (build_head(), build_sclera(), build_lids(), build_mouth(), build_face_details(),
                 build_blush(), build_hair()):
        i, origin = attach(mesh, "Head")
        meshes_on[i] = (mesh, origin)
    body = build_body()
    i, origin = attach(body, "UpperChest")
    meshes_on[i] = (body, origin)
    for side, eye in ((1, "Eye_L"), (-1, "Eye_R")):
        mesh = build_iris(side, world[eye])
        i, origin = attach(mesh, eye)
        meshes_on[i] = (mesh, (0, 0, 0))
    for side, ear in ((1, "Ear_L"), (-1, "Ear_R")):
        mesh = build_ear(side)
        i, origin = attach(mesh, ear)
        meshes_on[i] = (mesh, (0, 0, 0))

    # Ears sit tilted outwards and a little back, like the wallpaper's.
    def quat(axis, angle):
        s = math.sin(angle / 2)
        return np.array([axis[0] * s, axis[1] * s, axis[2] * s, math.cos(angle / 2)])

    def qmul(a, b):
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                         aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])

    for side, ear in ((1, "Ear_L"), (-1, "Ear_R")):
        nodes[index[ear]]["rotation"] = qmul(quat((0, 0, 1), -side * 0.38), quat((1, 0, 0), -0.12))

    write(nodes, meshes_on, OUT)
    print(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
