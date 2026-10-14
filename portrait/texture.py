#!/usr/bin/env python3
"""Texture generator: VRoid (or any UV) templates + ComfyUI = new textures.

    python3 portrait/texture.py list
    python3 portrait/texture.py irises "ice blue with silver flecks"
    python3 portrait/texture.py bra "black lace with a pink trim" --count 4
    python3 portrait/texture.py skin "subtle freckles" --base my_body.png
    python3 portrait/texture.py --template shirt.png --paint opaque fill "red tartan"

A template says *where* on the texture a part lives. This script turns it
into a mask, asks ComfyUI for the picture, and puts the result back in
exactly the right place at exactly the template's size, as a PNG with
everything outside the part transparent - ready to drop into VRoid's
texture editor as a layer.

Three ways to fill a part (a preset picks one, --mode overrides):

  fill     generate a material (fabric, lace, latex...) and clip it to the
           shape. Long thin shapes get a square tile, mirror-tiled, so the
           pattern isn't stretched.
  stamp    generate one picture and put a copy in every separate island of
           the template - one iris into both eye circles.
  inpaint  repaint just the shape on top of a base texture you pass with
           --base, so it blends with what's there (skin, panels, wear).

Presets live in portrait/textures/presets.json; add a template there and
it's a new part, no code. ComfyUI is found at http://127.0.0.1:8188 (or
$COMFY_URL, or --comfy). Results go to ~/luna-textures/.

Needs Pillow (pip install pillow). Nothing else: ComfyUI does the rest.
"""
import argparse
import io
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from PIL import Image, ImageChops, ImageFilter, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS = os.path.join(HERE, "textures", "presets.json")
OUT_DIR = os.path.expanduser(os.environ.get("LUNA_TEXTURES", "~/luna-textures"))

DEFAULTS = {
    "checkpoint": "waiIllustriousSDXL_v170.safetensors",
    "steps": 28, "cfg": 5.5, "sampler": "euler_ancestral", "scheduler": "normal",
    "prefix": "masterpiece, best quality, amazing quality, ",
    "negative": ("lowres, worst quality, bad quality, jpeg artifacts, text, watermark, signature, "
                 "logo, person, body, face, hands, 3d, perspective, shadow, frame, border"),
    "paint": "opaque", "mode": "fill", "denoise": 0.75, "feather": 2, "close": 3,
}


# ---------------------------------------------------------------------------
# ComfyUI over HTTP
# ---------------------------------------------------------------------------
class Comfy:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.client = uuid.uuid4().hex

    def _get(self, path, timeout=30):
        with urllib.request.urlopen(self.url + path, timeout=timeout) as r:
            return r.read()

    def _post_json(self, path, data):
        req = urllib.request.Request(self.url + path, data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"ComfyUI refused the workflow: {e.read().decode('utf-8', 'replace')[:800]}") from e

    def ping(self):
        try:
            self._get("/system_stats", timeout=5)
        except Exception as e:
            raise RuntimeError(f"ComfyUI isn't answering at {self.url} - is it running? ({e})") from e

    def checkpoint(self, wanted):
        """The checkpoint's name as ComfyUI knows it (it may sit in a subfolder)."""
        info = json.loads(self._get("/object_info/CheckpointLoaderSimple"))
        names = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]

        for name in names:
            if name == wanted or os.path.basename(name).lower() == os.path.basename(wanted).lower():
                return name

        raise RuntimeError(f"ComfyUI has no checkpoint called {wanted}. It has: {', '.join(names[:12])}")

    def upload(self, image, name):
        buf = io.BytesIO()
        image.save(buf, "PNG")
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
                f"Content-Type: image/png\r\n\r\n").encode() + buf.getvalue() + \
               f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue" \
               f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.url + "/upload/image", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            info = json.loads(r.read())

        return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]

    def run(self, workflow, timeout=900):
        """Queue it, wait for it, return the first output image."""
        pid = self._post_json("/prompt", {"prompt": workflow, "client_id": self.client})["prompt_id"]
        start = time.time()

        while time.time() - start < timeout:
            time.sleep(1.0)
            history = json.loads(self._get(f"/history/{pid}")).get(pid)

            if not history:
                continue

            status = history.get("status") or {}

            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI failed: {json.dumps(status.get('messages', []))[:800]}")

            for node in (history.get("outputs") or {}).values():
                for img in node.get("images") or []:
                    q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                                "type": img.get("type", "output")})
                    return Image.open(io.BytesIO(self._get("/view?" + q))).convert("RGB")

        raise RuntimeError("ComfyUI took too long")


def _base_nodes(o, ckpt, prompt):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": o["prefix"] + prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": o["negative"], "clip": ["1", 1]}},
    }


def _sampler(o, seed, latent, denoise):
    return {"class_type": "KSampler", "inputs": {
        "seed": seed, "steps": int(o["steps"]), "cfg": float(o["cfg"]), "sampler_name": o["sampler"],
        "scheduler": o["scheduler"], "denoise": float(denoise),
        "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": latent}}


def txt2img(o, ckpt, prompt, seed, width, height):
    wf = _base_nodes(o, ckpt, prompt)
    wf["4"] = {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
    wf["5"] = _sampler(o, seed, ["4", 0], 1.0)
    wf["6"] = {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}}
    wf["7"] = {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "luna_texture"}}
    return wf


def inpaint(o, ckpt, prompt, seed, image_name, mask_name):
    # VAEEncode + SetLatentNoiseMask: works with any checkpoint and any
    # ComfyUI version, and lets denoise keep some of what was there.
    wf = _base_nodes(o, ckpt, prompt)
    wf["8"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    wf["9"] = {"class_type": "LoadImageMask", "inputs": {"image": mask_name, "channel": "red"}}
    wf["10"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["1", 2]}}
    wf["11"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["10", 0], "mask": ["9", 0]}}
    wf["5"] = _sampler(o, seed, ["11", 0], o["denoise"])
    wf["6"] = {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}}
    wf["7"] = {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "luna_texture"}}
    return wf


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
def mask_of(template, paint="opaque", close=3):
    """White where the part is. VRoid's clothing templates are the shape in
    opaque black on transparency ("opaque"); its eye template is the
    reverse, circles cut out of black ("transparent"). Thin guide lines
    (the eye's wireframe) are closed over so they don't leave gaps."""
    rgba = template.convert("RGBA")
    alpha = rgba.getchannel("A")

    if paint == "transparent":
        mask = alpha.point(lambda a: 255 if a < 128 else 0)
    elif paint == "white":
        mask = ImageOps.grayscale(rgba).point(lambda v: 255 if v > 200 else 0)
        mask = ImageChops.multiply(mask, alpha.point(lambda a: 255 if a >= 128 else 0))
    elif paint == "black":
        mask = ImageOps.grayscale(rgba).point(lambda v: 255 if v < 64 else 0)
        mask = ImageChops.multiply(mask, alpha.point(lambda a: 255 if a >= 128 else 0))
    else:   # opaque
        mask = alpha.point(lambda a: 255 if a >= 128 else 0)

    if close:
        size = int(close) * 2 + 1
        mask = mask.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.MinFilter(size))

    return mask


def islands(mask, scale=4):
    """Bounding boxes (l, t, r, b) of each separate shape in the mask,
    biggest first. Worked out on a small copy; boxes come back full size."""
    small = mask.resize((max(1, mask.width // scale), max(1, mask.height // scale)), Image.NEAREST)
    w, h = small.size
    px = small.load()
    seen = bytearray(w * h)
    boxes = []

    for y in range(h):
        for x in range(w):
            if px[x, y] < 128 or seen[y * w + x]:
                continue

            stack, l, t, r, b, n = [(x, y)], x, y, x, y, 0
            seen[y * w + x] = 1

            while stack:
                cx, cy = stack.pop()
                n += 1
                l, t, r, b = min(l, cx), min(t, cy), max(r, cx), max(b, cy)

                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and px[nx, ny] >= 128:
                        seen[ny * w + nx] = 1
                        stack.append((nx, ny))

            if n >= 16:     # specks aren't parts
                boxes.append((n, (l * scale, t * scale, min(mask.width, (r + 1) * scale),
                                  min(mask.height, (b + 1) * scale))))

    return [box for _n, box in sorted(boxes, reverse=True)]


def _sdxl_size(aspect, pixels=1024 * 1024):
    """A width/height near a million pixels, multiples of 64."""
    aspect = max(1 / 2.5, min(2.5, aspect))
    h = (pixels / aspect) ** 0.5
    return int(round(h * aspect / 64) * 64), int(round(h / 64) * 64)


def _mirror_tile(tile, width, height):
    """Cover width x height with the tile, every other copy mirrored, so
    joins line up instead of showing a seam."""
    tile = tile.resize((max(1, round(tile.width * height / tile.height)), height), Image.LANCZOS)
    flipped = ImageOps.mirror(tile)
    out = Image.new("RGB", (width, height))
    x, n = 0, 0

    while x < width:
        out.paste(flipped if n % 2 else tile, (x, 0))
        x += tile.width
        n += 1

    return out


def _feathered(mask, feather):
    return mask.filter(ImageFilter.GaussianBlur(feather)) if feather else mask


# ---------------------------------------------------------------------------
# The three modes
# ---------------------------------------------------------------------------
def make(template, prompt, o, comfy, seed, base=None, log=print):
    """The finished texture, template-sized RGBA."""
    mask = mask_of(template, o["paint"], o["close"])
    boxes = islands(mask)

    if not boxes:
        raise RuntimeError("the template has nothing to paint - check \"paint\" (opaque/transparent/black/white)")

    ckpt = comfy.checkpoint(o["checkpoint"])
    size = template.size
    layer = Image.new("RGB", size)
    mode = o["mode"]

    if mode == "inpaint":
        if base is None:
            raise RuntimeError("inpaint needs a base texture: --base your_texture.png")

        base = base.convert("RGB").resize(size, Image.LANCZOS)
        layer = base.copy()

        for box in boxes:
            pad = 32
            l, t, r, b = max(0, box[0] - pad), max(0, box[1] - pad), min(size[0], box[2] + pad), min(size[1], box[3] + pad)
            crop, crop_mask = base.crop((l, t, r, b)), mask.crop((l, t, r, b))
            w, h = _sdxl_size((r - l) / (b - t))
            log(f"  inpainting {r - l}x{b - t} at {w}x{h}")
            img = comfy.upload(crop.resize((w, h), Image.LANCZOS), f"luna_base_{uuid.uuid4().hex[:8]}.png")
            msk = comfy.upload(crop_mask.resize((w, h), Image.LANCZOS).convert("RGB"), f"luna_mask_{uuid.uuid4().hex[:8]}.png")
            out = comfy.run(inpaint(o, ckpt, prompt, seed, img, msk)).resize((r - l, b - t), Image.LANCZOS)
            layer.paste(out, (l, t), _feathered(crop_mask, o["feather"]))

    elif mode == "stamp":
        log("  generating one picture for every island")
        patch = comfy.run(txt2img(o, ckpt, prompt, seed, 1024, 1024))

        for n, box in enumerate(boxes):
            w, h = box[2] - box[0], box[3] - box[1]
            piece = patch.resize((w, h), Image.LANCZOS)

            if o.get("mirror") and n % 2:
                piece = ImageOps.mirror(piece)

            layer.paste(piece, box[:2])

    else:   # fill
        l = min(b[0] for b in boxes); t = min(b[1] for b in boxes)
        r = max(b[2] for b in boxes); bot = max(b[3] for b in boxes)
        w, h = r - l, bot - t

        if w / h > 2.5 or h / w > 2.5:
            log(f"  long shape ({w}x{h}): one square tile, mirror-tiled")
            tile = comfy.run(txt2img(o, ckpt, prompt, seed, 1024, 1024))
            area = _mirror_tile(tile, w, h) if w >= h else _mirror_tile(tile.rotate(90, expand=True), h, w).rotate(-90, expand=True)
        else:
            gw, gh = _sdxl_size(w / h)
            log(f"  generating {gw}x{gh} for a {w}x{h} shape")
            area = comfy.run(txt2img(o, ckpt, prompt, seed, gw, gh)).resize((w, h), Image.LANCZOS)

        layer.paste(area, (l, t))

    result = layer.convert("RGBA")
    alpha = _feathered(mask, o["feather"]) if mode != "inpaint" else Image.new("L", size, 255)
    result.putalpha(alpha)

    return result


# ---------------------------------------------------------------------------
# Presets and the command line
# ---------------------------------------------------------------------------
def presets():
    try:
        with open(PRESETS, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}

    return {k: v for k, v in data.items() if not k.startswith("_")}


def options(preset=None, **overrides):
    o = dict(DEFAULTS)
    o.update(preset or {})
    o.update({k: v for k, v in overrides.items() if v is not None})
    return o


def full_prompt(o, prompt):
    """The preset's own words around yours: "{you}" marks where yours go."""
    shape = o.get("prompt") or ""

    if "{you}" in shape:
        return shape.replace("{you}", prompt)

    return f"{shape}, {prompt}" if shape else prompt


def generate(name, prompt, count=1, seed=None, base=None, comfy_url=None, out_dir=OUT_DIR,
             template=None, log=print, **overrides):
    """Make `count` textures. Returns the saved paths. Used by the command
    line and by Luna's make_texture tool."""
    preset = presets().get(name) if name else None

    if name and preset is None and template is None:
        raise RuntimeError(f"no preset called {name!r} - `list` shows them")

    o = options(preset, **overrides)
    path = template or os.path.join(HERE, "textures", "templates", o["template"])
    tmpl = Image.open(path)
    base_img = Image.open(base) if base else None
    comfy = Comfy(comfy_url or os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    comfy.ping()
    os.makedirs(out_dir, exist_ok=True)
    text = full_prompt(o, prompt)
    saved = []

    for i in range(max(1, int(count))):
        s = (int(seed) + i) if seed is not None else random.randint(0, 2**31 - 1)
        log(f"{name or os.path.basename(path)} #{i + 1}: seed {s}")
        result = make(tmpl, text, o, comfy, s, base_img, log=log)
        out = os.path.join(out_dir, f"{name or 'texture'}-{time.strftime('%Y%m%d-%H%M%S')}-{s}.png")
        result.save(out)
        log(f"  saved {out}")
        saved.append(out)

    return saved


def main(argv=None):
    p = argparse.ArgumentParser(description="Textures from UV templates through ComfyUI.")
    p.add_argument("preset", help="a preset name, or 'list'")
    p.add_argument("prompt", nargs="*", help="what you want, in your words")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--seed", type=int)
    p.add_argument("--base", help="a texture to paint on (inpaint mode)")
    p.add_argument("--template", help="a template file instead of the preset's")
    p.add_argument("--paint", choices=["opaque", "transparent", "black", "white"])
    p.add_argument("--mode", choices=["fill", "stamp", "inpaint"])
    p.add_argument("--checkpoint")
    p.add_argument("--steps", type=int)
    p.add_argument("--cfg", type=float)
    p.add_argument("--denoise", type=float)
    p.add_argument("--comfy", help="ComfyUI address (default $COMFY_URL or http://127.0.0.1:8188)")
    p.add_argument("--out", default=OUT_DIR)
    a = p.parse_args(argv)

    if a.preset == "list":
        for name, pr in presets().items():
            print(f"  {name:12} {pr.get('mode', DEFAULTS['mode']):8} {pr.get('about', '')}")
        return 0

    name = None if a.template and a.preset in ("fill", "stamp", "inpaint") else a.preset

    if name is None:
        a.mode = a.mode or a.preset

    try:
        generate(name, " ".join(a.prompt), a.count, a.seed, a.base, a.comfy, a.out, a.template,
                 paint=a.paint, mode=a.mode, checkpoint=a.checkpoint, steps=a.steps, cfg=a.cfg,
                 denoise=a.denoise)
    except Exception as e:
        print(f"texture: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
