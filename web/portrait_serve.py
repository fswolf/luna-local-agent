"""What the portrait page needs from a server: its files, and the part of
the event stream it reads.

Two servers show her portrait. The live monitor (web/livefeed.py) serves
it to this PC at 127.0.0.1:8792/portrait/, and the relay stations
(web/station.py) serve it to paired phones and tablets at /portrait/ on
the station port. Both hand out the same files through portrait_file().

The stream is where they differ. The monitor's /events carries the whole
turn: what you said, her thinking, tool calls, how full the context is.
The portrait reads only a small part of that (her stage, mood, gestures,
voice, clothes...), so a station gets portrait_only(): those kinds and
nothing else, your words and her thinking taken out. What she says out
loud stays in, since the station plays it anyway, and the portrait acts
out her *hugs* from it. Each station stream gets its own PortraitCut,
which also keeps out thinking that arrives inside her reply as
<think>...</think> (LM Studio with its reasoning parsing off).
"""
import json
import os
import re
from urllib.parse import parse_qs, unquote, urlsplit

import config

TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".json": "application/json", ".vrm": "model/gltf-binary", ".glb": "model/gltf-binary",
         ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
         ".moc3": "application/octet-stream", ".vrma": "model/gltf-binary",
         ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav", ".m4a": "audio/mp4"}
SOUNDS = (".mp3", ".ogg", ".wav", ".m4a")
_CACHED = (".vrm", ".glb", ".png", ".jpg", ".webp", ".moc3")


def _json(obj):
    return 200, "application/json", json.dumps(obj).encode(), False


def _sounds():
    """portrait/sounds/: {name: [files]} - a file by its name without the
    extension (touch-self.mp3 -> "touch-self"), a folder by its name
    (gasp/ -> every clip in it, one picked at random), and numbered files
    by their shared name (moan01.mp3, moan02.mp3 -> "moan")."""
    sdir = os.path.join(config.BASE_DIR, "portrait", "sounds")
    found = {}
    for top, _dirs, files in os.walk(sdir):
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() not in SOUNDS:
                continue
            path = os.path.relpath(os.path.join(top, f), os.path.join(config.BASE_DIR, "portrait"))
            url = "/".join(path.split(os.sep))
            stem = os.path.splitext(f)[0].lower()
            found.setdefault(stem, []).append(url)
            base = re.sub(r"[_\- ]?\d+$", "", stem)      # moan-sexy01, moan-sexy02 -> also "moan-sexy"
            if base and base != stem:
                found.setdefault(base, []).append(url)
            if top != sdir:
                found.setdefault(os.path.relpath(top, sdir).replace(os.sep, "/").lower(), []).append(url)
    return found


def portrait_file(rel, query="", station=False):
    """One file of the portrait page: (status, content type, body, cacheable).

    Nothing outside portrait/, whatever the path says. The page and its
    libraries live in portrait/viewer/ (vendor/ inside it); models/ and
    animations/ beside it are served at the same level, so the page finds
    them as models/..., gestures/...

    station=True: for a relay station's portrait, which never casts to a
    hologram fan (the fan is the PC's)."""
    from web.gesture_files import props_list
    from web.portrait_config import portrait_config, portrait_models

    rel = unquote(rel)   # a model folder with spaces or non-latin letters in its name
    if rel == "config.json":
        # ?model=... previews another model without switching to it
        want = (parse_qs(query).get("model") or [""])[0]
        cfg = portrait_config(want if want in portrait_models() else None)
        if station:
            cfg["fan"] = dict(cfg.get("fan") or {}, cast=False)
        return _json(cfg)

    if rel == "gestures/index.json":
        # every gesture file the page should load (portrait/gestures/)
        gdir = os.path.join(config.BASE_DIR, "portrait", "gestures")
        try:
            names = sorted(f[:-3] for f in os.listdir(gdir) if f.endswith(".js") and not f.startswith("_"))
        except OSError:
            names = []
        return _json(names)

    if rel == "props/index.json":
        return _json(props_list())

    if rel == "props/props.json" and not os.path.isfile(
            os.path.join(config.BASE_DIR, "portrait", "props", "props.json")):
        return _json({})     # nothing placed yet: the defaults

    if rel == "sounds/index.json":
        return _json(_sounds())

    if rel == "cards/index.json":
        from web import cards
        return _json(cards.cards())
    if rel == "cards/yours.json":
        from web import cards
        return _json(cards.own_gestures())
    if rel.startswith("cards/thumb/") and rel.endswith(".png"):
        from web import cards
        try:
            return 200, "image/png", cards.picture(rel[12:-4]), False
        except (ValueError, OSError):
            return 404, "text/plain", b"", False

    if rel == "models.json":
        return _json(portrait_models())

    root = os.path.realpath(os.path.join(config.BASE_DIR, "portrait"))
    full = os.path.realpath(os.path.join(root, "viewer", rel or "index.html"))
    if not os.path.isfile(full):
        full = os.path.realpath(os.path.join(root, rel or "index.html"))
    ext = os.path.splitext(full)[1].lower()

    if not full.startswith(root + os.sep) or ext not in TYPES or not os.path.isfile(full):
        return 404, "text/plain", b"", False

    with open(full, "rb") as f:
        # .vrma not cached: you're likely re-recording it
        return 200, TYPES[ext], f.read(), ext in _CACHED and "vendor" not in full


def split_path(path):
    """'/portrait/models/x.vrm?y=1' -> ('models/x.vrm', 'y=1')."""
    url = urlsplit(path)
    return url.path[len("/portrait/"):], url.query


# ---------------------------------------------------------------------------
# The portrait's part of the stream
# ---------------------------------------------------------------------------
# Every kind portrait.js and live2d.js act on (their handle() switch);
# tests/test_portrait_serve.py checks the two stay in step.
PORTRAIT_KINDS = frozenset((
    "background", "chat", "done", "doze", "emote", "feeling", "flags", "frame", "gaze", "gesture",
    "gesture_mode", "holo", "lights", "match_light", "mood", "note", "outfit", "prop", "reload",
    "sounds", "stage", "tok", "tool", "turn", "voice",
))


def portrait_only(event):
    """The event as a station's portrait gets it, or None to leave it out.
    Stateless; a stream uses PortraitCut, which adds the <think> check.

    - turn: who it was and whether they're a guest, never what was said
    - tok: what she says (p "a"), never her thinking (p "t")
    - tool, done: that it happened, not what was called or how sure she was
    """
    kind = event.get("t")
    if kind not in PORTRAIT_KINDS:
        return None
    if kind == "turn":
        return {"t": kind, "at": event.get("at"), "source": event.get("source"), "guest": event.get("guest")}
    if kind == "tok":
        return dict(event) if event.get("p") == "a" else None
    if kind in ("tool", "done"):
        return {"t": kind, "at": event.get("at")}
    return dict(event)


_THINK = re.compile(r"<think>.*?</think>", re.S)
_THINK_MAX = 20000          # a reply longer than this is passed on as it comes


def _spoken(raw):
    """Her reply so far without any <think>...</think> in it, and without
    the end of an open one or the first letters of a tag still arriving."""
    out = _THINK.sub("", raw)
    open_at = out.find("<think>")
    if open_at >= 0:
        out = out[:open_at]
    for k in range(min(len("<think>") - 1, len(out)), 0, -1):
        if "<think>".startswith(out[-k:]):
            return out[:-k]
    return out


class PortraitCut:
    """portrait_only() for one stream, plus inline thinking kept out of her
    reply tokens. Her reply is gathered per turn; each token passes on only
    the part of it that's new and not thinking."""

    def __init__(self):
        self.raw = ""
        self.sent = 0

    def __call__(self, event):
        cut = portrait_only(event)
        if cut is None:
            return None
        if cut["t"] == "turn":
            self.raw, self.sent = "", 0
        elif cut["t"] == "tok" and len(self.raw) < _THINK_MAX:
            self.raw += str(cut.get("s") or "")
            shown = _spoken(self.raw)
            new, self.sent = shown[self.sent:], max(self.sent, len(shown))
            if not new:
                return None
            cut["s"] = new
        return cut
