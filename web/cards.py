"""Luna cards: a picture of her that is also her look (docs/portrait.md, Cards).

A card is a PNG with a zip on the end. A picture viewer reads a file from
the start and stops at the PNG's end; a zip reader reads from the end. So
the same file is a normal picture of her and an archive you can open with
unzip:

    card.json       what it carries, and her look and voice settings
    model.vrm       the model itself (left out of a "light" card)
    outfits.json    the model's clothes map, when it has one
    gestures/*.json gestures that belong to the look (the undress ones...)

Cards are saved in portrait/cards/ from the pose studio's Cards tab, and
loaded from there. Loading one checks everything the way the studio's own
save does: gestures go in as data through web/gesture_files.py, never as
code, and a gesture you already have isn't overwritten. A card never holds
her memory, your facts, people's prints, secrets or tool settings: only
the keys listed below can be in it, and only those are applied.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import time
import zipfile

import config
from web.gesture_files import gesture_file

FORMAT = "luna-card"
VERSION = 1
PNG_SIG = b"\x89PNG\r\n\x1a\n"
MAX_CARD = 96 * 1024 * 1024          # a full card carries a 16-22 MB model
MAX_IMAGE = 8 * 1024 * 1024
MAX_GESTURES = 40

# Everything a card may set, and nothing else.
LOOK = ("portrait.background", "portrait.frame", "portrait.match_light",
        "portrait.hologram.enabled", "portrait.hologram.tint", "portrait.hologram.mix",
        "portrait.hologram.intensity", "portrait.hologram.glitch", "portrait.hologram.base",
        "portrait.lights.enabled", "portrait.lights.color", "portrait.lights.brightness",
        "portrait.lights.voice", "portrait.lights.private", "portrait.lights.style")
VOICE = ("voice", "tts.speed")
PARTS = ("model", "look", "clothes", "gestures", "voice")

_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def folder():
    return os.path.join(config.BASE_DIR, "portrait", "cards")


def _portrait():
    return os.path.join(config.BASE_DIR, "portrait")


def slug(name):
    s = re.sub(r"[^a-z0-9_-]+", "-", str(name or "").strip().lower()).strip("-")[:40]
    if not _NAME.match(s):
        raise ValueError("a card's name: letters, numbers, - and _")
    return s


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _model_path(rel):
    """portrait.model (models/luna/human.vrm) -> the file, inside portrait/models only."""
    root = os.path.realpath(os.path.join(_portrait(), "models"))
    full = os.path.realpath(os.path.join(_portrait(), str(rel or "")))
    if not full.startswith(root + os.sep) or not full.lower().endswith((".vrm", ".glb")):
        raise ValueError("only a .vrm or .glb in portrait/models can go on a card")
    return full


# -- making one -----------------------------------------------------------
def pack(name, image, carry, gestures=(), model=None):
    """Write portrait/cards/<name>.png. image: the PNG bytes of the picture;
    carry: {part: bool}; gestures: [gesture data, as the studio has them].
    Returns {"name", "file", "carries", "skipped": [why...]}."""
    name = slug(name)
    if not isinstance(image, (bytes, bytearray)) or not image.startswith(PNG_SIG) or len(image) > MAX_IMAGE:
        raise ValueError("the picture has to be a PNG under 8 MB")
    carry = {p: bool((carry or {}).get(p)) for p in PARTS}
    model = model or getattr(config, "PORTRAIT_MODEL", "")
    skipped = []
    card = {"format": FORMAT, "version": VERSION, "name": name, "made": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": {"path": model}, "carries": [], "look": {}, "voice": {}, "gestures": []}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        mfile = None
        try:
            mfile = _model_path(model)
            card["model"]["sha256"] = _sha(mfile)
            card["model"]["file"] = os.path.basename(mfile)
        except (ValueError, OSError) as e:
            if carry["model"] or carry["clothes"]:
                skipped.append(f"model: {e}")
            carry["model"] = carry["clothes"] = False
        if carry["model"] and mfile:
            z.write(mfile, "model.vrm", compress_type=zipfile.ZIP_STORED)    # a VRM is already packed
            card["carries"].append("model")
        if carry["clothes"] and mfile:
            side = os.path.splitext(mfile)[0] + ".outfits.json"
            if os.path.isfile(side):
                with open(side, encoding="utf-8") as f:
                    z.writestr("outfits.json", json.dumps(_outfits_map(json.load(f))))
                card["carries"].append("clothes")
            else:
                skipped.append("clothes map: this model doesn't have one (its pieces are guessed)")
        if carry["look"]:
            card["look"] = {k: config.current(k) for k in LOOK if config.current(k) is not None}
            card["carries"].append("look")
        if carry["voice"]:
            card["voice"] = {k: config.current(k) for k in VOICE if config.current(k) is not None}
            card["carries"].append("voice")
        if carry["gestures"]:
            for g in list(gestures or [])[:MAX_GESTURES]:
                try:
                    gname, _text = gesture_file(g)         # checked now, so a card never carries junk
                except (ValueError, TypeError, KeyError, AttributeError) as e:
                    skipped.append(f"gesture {str((g or {}).get('name', '?'))[:30]}: {str(e)[:80]}")
                    continue
                z.writestr(f"gestures/{gname}.json", json.dumps(dict(g, name=gname)))
                card["gestures"].append(gname)
            if card["gestures"]:
                card["carries"].append("gestures")
        z.writestr("card.json", json.dumps(card, indent=1, default=str))

    os.makedirs(folder(), exist_ok=True)
    path = os.path.join(folder(), name + ".png")
    with open(path + ".tmp", "wb") as f:
        f.write(bytes(image) + buf.getvalue())
    os.replace(path + ".tmp", path)
    return {"name": name, "file": "cards/" + name + ".png", "carries": card["carries"], "skipped": skipped}


def _outfits_map(data):
    """outfits.json, rebuilt: {"pieces": {part of a material name: label}} and nothing else."""
    pieces = (data or {}).get("pieces") if isinstance(data, dict) else None
    out = {}
    for k, v in (pieces or {}).items():
        k, v = str(k)[:60], str(v).strip().lower()[:24]
        if re.match(r"^[A-Za-z0-9_ .()-]+$", k) and re.match(r"^[a-z][a-z0-9 _-]*$", v):
            out[k] = v
    return {"pieces": out}


# -- reading them -----------------------------------------------------------
def _open(path):
    """The zip inside a card, or ValueError."""
    with open(path, "rb") as f:
        head = f.read(8)
    if head != PNG_SIG:
        raise ValueError("not a PNG")
    try:
        z = zipfile.ZipFile(path)
        card = json.loads(_read(z, "card.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise ValueError("a picture, but not a Luna card") from e
    if not isinstance(card, dict) or card.get("format") != FORMAT:
        raise ValueError("a picture, but not a Luna card")
    return z, card


def info(path):
    """What a card carries, for the studio: {name, file, carries, model, made, gestures, size}."""
    z, card = _open(path)
    z.close()
    return {"name": os.path.splitext(os.path.basename(path))[0], "file": "cards/" + os.path.basename(path),
            "carries": [p for p in card.get("carries", []) if p in PARTS],
            "model": str((card.get("model") or {}).get("path") or ""),
            "made": str(card.get("made") or ""), "gestures": [str(g) for g in card.get("gestures", [])][:MAX_GESTURES],
            "size": os.path.getsize(path)}


def cards():
    """Every card in portrait/cards/, newest first."""
    try:
        files = [f for f in os.listdir(folder()) if f.lower().endswith(".png")]
    except OSError:
        return []
    out = []
    for f in sorted(files, key=lambda f: -os.path.getmtime(os.path.join(folder(), f))):
        try:
            out.append(info(os.path.join(folder(), f)))
        except (ValueError, OSError):
            continue
    return out


def picture(name):
    """Just the picture of a card (the PNG up to its end), for the grid: a few
    hundred KB instead of the whole card with her model in it."""
    path = os.path.join(folder(), slug(name) + ".png")
    with open(path, "rb") as f:
        if f.read(8) != PNG_SIG:
            raise ValueError("not a PNG")
        while True:
            head = f.read(8)
            if len(head) < 8:
                raise ValueError("a broken PNG")
            size, kind = int.from_bytes(head[:4], "big"), head[4:]
            f.seek(size + 4, 1)                           # the chunk and its checksum
            if kind == b"IEND":
                end = f.tell()
                break
            if f.tell() > MAX_IMAGE:
                raise ValueError("the picture is too big")
        f.seek(0)
        return f.read(end)


def remove(name):
    """Delete a card. A model it put in portrait/models/cards/ stays: she may be wearing it."""
    path = os.path.join(folder(), slug(name) + ".png")
    if not os.path.isfile(path):
        raise ValueError(f"no card called {name!r}")
    os.remove(path)


def own_gestures():
    """The gestures you made: files in portrait/gestures/ that aren't in Luna's git.
    The ones that ship with her, everyone has already. None when git can't say
    (a copy without git): then every gesture is offered."""
    gdir = os.path.join(_portrait(), "gestures")
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--", "."], cwd=gdir, capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    shipped = {os.path.basename(f) for f in out.stdout.decode("utf-8", "replace").split("\0") if f}
    try:
        files = os.listdir(gdir)
    except OSError:
        return []
    return sorted(f[:-3] for f in files if f.endswith(".js") and not f.startswith("_") and f not in shipped)


def add(data, name=None):
    """A card from somewhere else (dropped on the studio): checked, then kept in
    portrait/cards/ under a name that isn't taken. Returns info()."""
    if not isinstance(data, (bytes, bytearray)) or not data.startswith(PNG_SIG) or len(data) > MAX_CARD:
        raise ValueError("not a card (a PNG, at most 96 MB)")
    tmp = os.path.join(folder(), ".incoming.png")
    os.makedirs(folder(), exist_ok=True)
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        _z, card = _open(tmp)
        _z.close()
        base = slug(name or card.get("name") or "card")
        final, n = base, 2
        while os.path.exists(os.path.join(folder(), final + ".png")):
            final, n = f"{base}-{n}", n + 1
        os.replace(tmp, os.path.join(folder(), final + ".png"))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return info(os.path.join(folder(), final + ".png"))


# -- loading one -------------------------------------------------------------
def _read(z, member, limit=1 << 20):
    """One small file from a card, refused if it would unpack bigger than it should."""
    if z.getinfo(member).file_size > limit:
        raise ValueError(f"{member} is too big")
    return z.read(member)


def apply(name):
    """Put a card on: its model, clothes map, gestures, look and voice. Returns
    {"model", "done": [...], "skipped": [...]}; the page reloads after."""
    path = os.path.join(folder(), slug(name) + ".png")
    if not os.path.isfile(path):
        raise ValueError(f"no card called {name!r}")
    z, card = _open(path)
    done, skipped = [], []
    carries = set(card.get("carries") or [])
    model_rel = str((card.get("model") or {}).get("path") or "")
    want_sha = str((card.get("model") or {}).get("sha256") or "")

    with z:
        # the model: the one you have, if it's the same file; otherwise the card's own copy
        target = None
        try:
            local = _model_path(model_rel)
            if os.path.isfile(local) and (not want_sha or _sha(local) == want_sha):
                target = model_rel
        except ValueError:
            pass
        if target is None and "model" in carries:
            fname = re.sub(r"[^A-Za-z0-9_.-]", "_", str((card.get("model") or {}).get("file") or "model.vrm"))
            if not fname.lower().endswith((".vrm", ".glb")):
                fname += ".vrm"
            dest_dir = os.path.join(_portrait(), "models", "cards", slug(name))
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, fname)
            if z.getinfo("model.vrm").file_size > MAX_CARD:
                raise ValueError("the model in this card is too big")
            if not (os.path.isfile(dest) and want_sha and _sha(dest) == want_sha):   # put on before
                with z.open("model.vrm") as src, open(dest + ".tmp", "wb") as out:
                    while block := src.read(1 << 20):
                        out.write(block)
                os.replace(dest + ".tmp", dest)
            target = f"models/cards/{slug(name)}/{fname}"
            done.append("model (from the card)")
        if target is None:
            skipped.append(f"model: you don't have {model_rel or 'its model'} and the card doesn't carry it")
        else:
            config.save_any("portrait.model", target)
            done.append(f"model {target}")
            if "clothes" in carries:
                try:
                    clothes = _outfits_map(json.loads(_read(z, "outfits.json")))
                    side = os.path.splitext(_model_path(target))[0] + ".outfits.json"
                    mine = None
                    if os.path.isfile(side):
                        with open(side, encoding="utf-8") as f:
                            mine = _outfits_map(json.load(f))
                    if mine is not None and mine != clothes:
                        skipped.append("clothes: this model has its own outfits.json, kept yours")
                    else:
                        with open(side, "w", encoding="utf-8") as f:
                            json.dump(clothes, f, indent=1)
                        done.append("clothes map")
                except (KeyError, ValueError, OSError) as e:
                    skipped.append(f"clothes: {e}")

        if "gestures" in carries:
            gdir = os.path.join(_portrait(), "gestures")
            for g in [str(x) for x in card.get("gestures", [])][:MAX_GESTURES]:
                try:
                    gname, text = gesture_file(json.loads(_read(z, f"gestures/{g}.json")))
                    gpath = os.path.join(gdir, gname + ".js")
                    if os.path.exists(gpath):
                        with open(gpath, encoding="utf-8") as f:
                            same = f.read() == text
                        if not same:
                            skipped.append(f"gesture {gname}: you have your own, kept yours")
                        continue
                    with open(gpath, "w", encoding="utf-8") as f:
                        f.write(text)
                    done.append(f"gesture {gname}")
                except (KeyError, ValueError, TypeError, AttributeError, OSError) as e:
                    skipped.append(f"gesture {g}: {str(e)[:80]}")

        for part, keys in (("look", LOOK), ("voice", VOICE)):
            if part not in carries:
                continue
            values = card.get(part) or {}
            for k in keys:
                if k not in values or values[k] is None:
                    continue
                v = values[k]
                raw = ("true" if v else "false") if isinstance(v, bool) else str(v)
                try:
                    config.save_any(k, raw)
                except ValueError as e:
                    skipped.append(f"{k}: {e}")
            done.append(part)

    return {"model": target, "done": done, "skipped": skipped}
