#!/usr/bin/env python3
"""Light strips: finds the glowing strips on a VRM model's textures and
writes the maps the portrait lights them up from (portrait/viewer/lights.js).

    python3 portrait/lights.py models/luna/robot_default.vrm
    python3 portrait/lights.py models/luna/robot_default.vrm \\
        --panel chest=source/layers/chest-led-pearl-slot-v4.png \\
        --private chest=source/templates/guide_bra.png \\
        --private groin=source/templates/guide_panties.png

Paths are from where you are, or from portrait/. Writes, next to the model, a lights/
folder:

  <material>.glow.png   white where it glows, grey for dimmer, black for
                        none. Paint on it in GIMP to add or fix strips.
  <material>.zones.png  which part of her each pixel belongs to, as flat
                        colours (the legend is in lights.json). Zones let a
                        part light up on its own, and keep the chest and
                        groin dark on a stream.
  lights.json           the files, the zones, the strips' own colour.

How it finds them:
  strips   the saturated, hot colour on the texture (the model's own LED
           paint). --color picks it (default: hot pink); --tolerance widens it.
  panels   bigger solid lights (chest LEDs, a belly light). A --panel layer
           (the PNG you painted it with in VRoid) names one exactly.
  zones    from the mesh: each pixel goes to the bone that moves it most
           (arms, hands, legs, feet, torso, ears, tail). --private layers
           (a bra or panties template) mark the parts kept dark on a
           stream with lewd off.

Re-run it after a texture changes. Hand edits to the .png files are kept
unless you pass --force. Needs numpy and Pillow.
"""
import argparse
import colorsys
import io
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# zone id -> (name, colour in zones.png). Order is the id the shader sees.
ZONES = [
    ("none", (0, 0, 0)), ("torso", (255, 170, 0)), ("chest", (255, 0, 0)), ("groin", (150, 0, 0)),
    ("navel", (255, 255, 0)), ("neck", (0, 255, 255)), ("arm_l", (0, 128, 255)), ("arm_r", (0, 0, 255)),
    ("hand_l", (128, 0, 255)), ("hand_r", (255, 0, 255)), ("leg_l", (0, 255, 0)), ("leg_r", (0, 120, 0)),
    ("foot_l", (128, 255, 128)), ("foot_r", (0, 80, 40)), ("ears", (255, 255, 255)), ("tail", (128, 128, 128)),
]
ZONE_ID = {name: i for i, (name, _c) in enumerate(ZONES)}
PRIVATE = ("chest", "groin")
SKIP = re.compile(r"face|eye|brow|lash|mouth|hair|outline", re.I)
PANEL_LEVEL = 0.8          # panels a touch under the strips, so she reads as running lights


def bone_zone(name):
    """A VRoid / humanoid bone name -> a zone name."""
    n = name.lower()
    side = "_l" if re.search(r"(^|[_.\s])l([_.\s]|$)|left", n) else "_r" if re.search(r"(^|[_.\s])r([_.\s]|$)|right", n) else ""
    if "catear" in n or re.search(r"(^|_)ear", n):
        return "ears"
    if "tail" in n:
        return "tail"
    if re.search(r"thumb|index|middle|ring|little|hand", n):
        return "hand" + (side or "_l")
    if re.search(r"shoulder|upperarm|lowerarm|arm", n):
        return "arm" + (side or "_l")
    if re.search(r"toe|foot", n):
        return "foot" + (side or "_l")
    if re.search(r"upperleg|lowerleg|leg", n):
        return "leg" + (side or "_l")
    if re.search(r"neck|head|eye|face|hair", n):
        return "neck"
    return "torso"           # hips, spine, chest, bust


# ---------------------------------------------------------------------------
# Reading the model
# ---------------------------------------------------------------------------
class Model:
    def __init__(self, path):
        with open(path, "rb") as f:
            data = f.read()
        if data[:4] != b"glTF":
            raise ValueError(f"{path} isn't a VRM / glb file")
        size = struct.unpack("<I", data[12:16])[0]
        self.gltf = json.loads(data[20:20 + size])
        self.bin = data[20 + size + 8:]

    def view(self, index):
        bv = self.gltf["bufferViews"][index]
        start = bv.get("byteOffset", 0)
        return self.bin[start:start + bv["byteLength"]]

    def accessor(self, index):
        import numpy as np

        a = self.gltf["accessors"][index]
        kinds = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        dtype = np.dtype(kinds[a["componentType"]])
        bv = self.gltf["bufferViews"][a["bufferView"]]
        raw = self.view(a["bufferView"])
        stride = bv.get("byteStride") or dtype.itemsize * width
        off = a.get("byteOffset", 0)
        rows = np.lib.stride_tricks.as_strided(
            np.frombuffer(raw, dtype=np.uint8)[off:], shape=(a["count"], dtype.itemsize * width), strides=(stride, 1))
        out = np.ascontiguousarray(rows).view(dtype).reshape(a["count"], width)
        if a.get("normalized") and dtype.kind in "iu":
            out = out.astype(np.float32) / np.iinfo(dtype).max
        return out

    def image(self, texture):
        from PIL import Image

        img = self.gltf["images"][self.gltf["textures"][texture]["source"]]
        return Image.open(io.BytesIO(self.view(img["bufferView"]))).convert("RGB")

    def materials(self):
        """(index, name, base texture index) for each textured material."""
        for i, m in enumerate(self.gltf.get("materials", [])):
            tex = (m.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
            if tex is not None:
                yield i, m.get("name", f"material{i}"), tex["index"]

    def primitives(self, material):
        """(primitive, skin) pairs drawn with this material."""
        skins = {}
        for node in self.gltf.get("nodes", []):
            if "mesh" in node:
                skins.setdefault(node["mesh"], node.get("skin"))
        for mi, mesh in enumerate(self.gltf.get("meshes", [])):
            for p in mesh["primitives"]:
                if p.get("material") == material:
                    yield p, skins.get(mi)


# ---------------------------------------------------------------------------
# Strips, panels, zones
# ---------------------------------------------------------------------------
def hot(rgb, color, tolerance):
    """Pixels painted in the strips' colour: near its hue, saturated, bright."""
    import numpy as np

    px = rgb.astype(np.float32) / 255
    mx, mn = px.max(2), px.min(2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    d = mx - mn + 1e-6
    hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6
    want = colorsys.rgb_to_hsv(*[c / 255 for c in color])[0]
    off = np.minimum(abs(hue - want), 1 - abs(hue - want))
    return (off < 0.09 * tolerance) & (sat > 0.32 / tolerance) & (mx > 0.58 / tolerance)


def components(mask):
    """Label 4-connected pieces. Returns (labels, sizes, boxes)."""
    import numpy as np

    try:
        from scipy import ndimage

        labels, n = ndimage.label(mask)
        boxes = ndimage.find_objects(labels)
        sizes = np.bincount(labels.ravel())[1:]
        return labels, sizes, boxes
    except ImportError:
        pass
    h, w = mask.shape
    labels = np.zeros((h, w), np.int32)
    sizes, boxes, n = [], [], 0
    flat = mask.ravel()
    lab = labels.ravel()
    for s in np.flatnonzero(flat):
        if lab[s]:
            continue
        n += 1
        stack, cells = [s], 0
        lab[s] = n
        x0 = x1 = s % w
        y0 = y1 = s // w
        while stack:
            k = stack.pop()
            cells += 1
            x, y = k % w, k // w
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for q in (k + 1 if x + 1 < w else -1, k - 1 if x else -1, k + w, k - w):
                if 0 <= q < h * w and flat[q] and not lab[q]:
                    lab[q] = n
                    stack.append(q)
        sizes.append(cells)
        boxes.append((slice(y0, y1 + 1), slice(x0, x1 + 1)))
    return labels, np.array(sizes), boxes


def grow(mask, px):
    """Thicken a mask by px pixels (thin strips stay continuous when shrunk)."""
    import numpy as np

    out = mask.copy()
    for _ in range(px):
        m = out.copy()
        m[1:] |= out[:-1]; m[:-1] |= out[1:]; m[:, 1:] |= out[:, :-1]; m[:, :-1] |= out[:, 1:]
        out = m
    return out


def glow_map(rgb, color, tolerance, panels):
    """0..1 glow: strips full, panels at PANEL_LEVEL. panels: {name: mask}."""
    import numpy as np

    lit = hot(rgb, color, tolerance)
    labels, sizes, boxes = components(lit)
    glow = np.zeros(lit.shape, np.float32)
    named = np.zeros(lit.shape, bool)
    for m in panels.values():
        named |= m
    for i, (n, box) in enumerate(zip(sizes, boxes), 1):
        if box is None or n < 3:
            continue                                    # specks: noise, not a strip
        hgt, wid = box[0].stop - box[0].start, box[1].stop - box[1].start
        piece = labels[box] == i
        panel = (named[box] & piece).any() or (n > 120 and n / (hgt * wid) > 0.45 and min(hgt, wid) > 6)
        glow[box][piece] = PANEL_LEVEL if panel else 1.0
    # strips a little thicker, so they stay whole on a small portrait
    thick = grow(glow >= 1.0, 1) & ~(glow > 0)
    glow[thick] = 0.7
    return glow


def zone_map(model, material, size, private):
    """Each texel's zone, from the bones that move the triangles over it."""
    import numpy as np
    from PIL import Image, ImageDraw

    w, h = size
    zones = np.zeros((h, w), np.uint8)
    nodes = model.gltf.get("nodes", [])
    for prim, skin in model.primitives(material):
        attrs = prim["attributes"]
        if "TEXCOORD_0" not in attrs:
            continue
        uv = model.accessor(attrs["TEXCOORD_0"]).astype(np.float64)
        idx = (model.accessor(prim["indices"]).ravel() if "indices" in prim
               else np.arange(len(uv))).reshape(-1, 3)
        if skin is not None and "JOINTS_0" in attrs:
            joints = model.gltf["skins"][skin]["joints"]
            j = model.accessor(attrs["JOINTS_0"]).astype(np.int64)
            wt = model.accessor(attrs["WEIGHTS_0"]).astype(np.float32)
            top = j[np.arange(len(j)), wt.argmax(1)]
            names = [nodes[joints[k]].get("name", "") if k < len(joints) else "" for k in range(len(joints))]
            vzone = np.array([ZONE_ID[bone_zone(names[k])] for k in top], np.uint8)
        else:
            vzone = np.full(len(uv), ZONE_ID["torso"], np.uint8)
        layer = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(layer)
        for tri in idx:
            z = np.bincount(vzone[tri], minlength=len(ZONES)).argmax()   # the triangle's majority
            pts = [(float(uv[k, 0] % 1.0001) * w, float(uv[k, 1] % 1.0001) * h) for k in tri]
            draw.polygon(pts, fill=int(z), outline=int(z))
        got = np.asarray(layer)
        zones = np.where(got > 0, got, zones)
    # a few pixels past each island's edge, for the glow around strips on a seam
    for _ in range(6):
        empty = zones == 0
        if not empty.any():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(zones, (dy, dx), (0, 1))
            zones = np.where(empty & (src > 0), src, zones)
            empty = zones == 0
    # private parts: inside a bra / panties template, on the torso only
    torso = (zones == ZONE_ID["torso"]) | (zones == ZONE_ID["navel"])
    for name, mask in private.items():
        zones[mask & torso] = ZONE_ID[name]
    return zones


def layer_mask(path, size, threshold=30):
    """A painted layer (RGBA, or black on white) -> where it's painted, at size.
    VRoid stretches a layer to the texture, so a 2000 px layer fits 2048."""
    import numpy as np
    from PIL import Image

    img = Image.open(path)
    if img.mode in ("RGBA", "LA") or "transparency" in img.info:
        a = np.asarray(img.convert("RGBA").resize(size, Image.BILINEAR))[..., 3]
        return a > threshold
    g = np.asarray(img.convert("L").resize(size, Image.BILINEAR))
    return g < 128 if (g > 128).mean() > 0.5 else g > 128      # dark on light, or light on dark


def own_colour(rgb, glow):
    import numpy as np

    px = rgb[glow >= 1.0]
    if not len(px):
        return "#ff4fb4"
    r, g, b = np.median(px, 0)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    r, g, b = colorsys.hsv_to_rgb(h, max(s, 0.65), 1.0)          # the light, not the paint
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def slug(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", re.sub(r"\s*\(Instance\)", "", name)).strip("_")


def build(model_path, panels=(), private=(), color="#ff4fb4", tolerance=1.0, force=False, quiet=False):
    import numpy as np
    from PIL import Image

    model = Model(model_path)
    out_dir = os.path.join(os.path.dirname(model_path), "lights")
    os.makedirs(out_dir, exist_ok=True)
    want = tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    manifest = {"version": 1, "zones": [n for n, _c in ZONES],
                "zone_colors": {n: "#%02x%02x%02x" % c for n, c in ZONES}, "private": list(PRIVATE),
                "materials": {}}
    seen = set()
    found = [(mi, name, tex) for mi, name, tex in model.materials() if not SKIP.search(name)]
    biggest = max((model.image(t).size[0] * model.image(t).size[1], t) for _m, _n, t in found)[1] if found else None
    for mi, name, tex in found:
        if tex in seen:
            continue
        rgb = np.asarray(model.image(tex))
        h, w = rgb.shape[:2]
        if hot(rgb, want, tolerance).sum() < 40:
            continue                                    # nothing that looks like a strip
        seen.add(tex)
        body = tex == biggest                           # layers and templates are for the body texture
        pmask = {n: layer_mask(p, (w, h)) for n, p in panels} if body else {}
        glow = glow_map(rgb, want, tolerance, pmask)
        privates = {n: layer_mask(p, (w, h)) for n, p in private} if body else {}
        zones = zone_map(model, mi, (w, h), privates)
        for n, m in pmask.items():                      # a named panel is its own zone
            if n in ZONE_ID:
                zones[m & (glow > 0)] = ZONE_ID[n]
        used = sorted({ZONES[z][0] for z in np.unique(zones[glow > 0]) if z})
        base = slug(name)
        files = {"glow": f"{base}.glow.png", "zones": f"{base}.zones.png"}
        for kind, arr in (("glow", (glow * 255).astype(np.uint8)),
                          ("zones", np.array([c for _n, c in ZONES], np.uint8)[zones])):
            path = os.path.join(out_dir, files[kind])
            if os.path.exists(path) and not force:
                if not quiet:
                    print(f"  kept {files[kind]} (yours; --force replaces it)")
                continue
            Image.fromarray(arr).save(path, optimize=True)
        manifest["materials"][re.sub(r"\s*\(Instance\)", "", name)] = dict(
            files, color=own_colour(rgb, glow), size=[w, h], lit=used)
        if not quiet:
            print(f"  {name}: {int((glow >= 1).sum())} strip px, zones {', '.join(used)}")
    if not manifest["materials"]:
        raise SystemExit("no light strips found (try --color with the strips' colour, or --tolerance 1.3)")
    with open(os.path.join(out_dir, "lights.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    return manifest


def _find(path):
    """A path as given (from where you are), else under portrait/."""
    return path if os.path.isabs(path) or os.path.exists(path) else os.path.join(HERE, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("model", help="the .vrm, relative to portrait/ or absolute")
    ap.add_argument("--panel", action="append", default=[], metavar="ZONE=PNG",
                    help="a painted LED layer, and the zone it lights (chest, navel, groin...)")
    ap.add_argument("--private", action="append", default=[], metavar="ZONE=PNG",
                    help="a template whose shape is kept dark on a stream (chest=bra, groin=panties)")
    ap.add_argument("--color", default="#ff4fb4", help="the strips' paint colour (default hot pink)")
    ap.add_argument("--tolerance", type=float, default=1.0, help="above 1 catches more, below 1 less")
    ap.add_argument("--force", action="store_true", help="replace hand-edited maps too")
    a = ap.parse_args(argv)

    def pairs(items, allowed):
        out = []
        for item in items:
            zone, _, path = item.partition("=")
            if zone not in allowed or not path:
                ap.error(f"{item!r}: give ZONE=file.png, ZONE one of {', '.join(allowed)}")
            path = _find(path)
            if not os.path.isfile(path):
                ap.error(f"{path} isn't there")
            out.append((zone, path))
        return out

    model = _find(a.model)
    if not os.path.isfile(model):
        ap.error(f"{model} isn't there")
    build(model, pairs(a.panel, [n for n, _c in ZONES[1:]]), pairs(a.private, PRIVATE),
          a.color, a.tolerance, a.force)
    print(f"wrote {os.path.join(os.path.dirname(model), 'lights')}")


if __name__ == "__main__":
    sys.exit(main())
