"""Reading the portrait's gesture and prop files for the pages that list them:
names, bones, words, idle bands and touch zones, without running any JS.

Part of the web package; web/livefeed.py is the front door.
"""
import json
import os
import re
import config


# -- the pose studio's gesture files ------------------------------------------
_GNAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_BONE = re.compile(r"^\+?[A-Za-z][A-Za-z0-9]{0,40}$")
_WORD = re.compile(r"^[A-Za-z0-9_\- ]{1,40}$")
_IDLE_BANDS = {"grudge", "cool", "neutral", "warm", "loving", "lewd"}
_ZONES = {"head", "nose", "mouth", "chest", "tummy", "groin", "legs", "neck", "arms", "back", "butt", "tail"}


def _num(v, lo=-1e4, hi=1e4):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise ValueError(f"not a number: {v!r}")
    return round(max(lo, min(hi, float(v))), 4)


def _words(v, limit=40, pattern=_WORD):
    if not isinstance(v, list):
        raise ValueError("expected a list")
    out = [str(w).strip() for w in v if str(w).strip()][:limit]
    for w in out:
        if not pattern.match(w):
            raise ValueError(f"not allowed: {w!r}")
    return out


def _text(v, limit=200):
    return " ".join(str(v).split())[:limit]


def gesture_file(data):
    """(name, file text) for a gesture from the pose studio. Everything is
    checked and rebuilt here - names, numbers, words - so what's written is
    always plain data in the gesture-file shape, whatever was sent."""
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    name = str(data.get("name", "")).strip().lower()
    if not _GNAME.match(name):
        raise ValueError("name: lower-case letters, numbers and _ only, starting with a letter")
    g = {}
    if data.get("chain") is not None:
        g["chain"] = _words(data["chain"], 12, _GNAME)
        if not g["chain"]:
            raise ValueError("a chain needs at least one gesture")
    else:
        keys = []
        for item in data.get("keys") or []:
            t, pose = item
            bones = {}
            for b, v in pose.items():
                if not _BONE.match(b) or not isinstance(v, list) or not 3 <= len(v) <= 4:
                    raise ValueError(f"bad bone: {b!r}")
                bones[b] = [_num(x, -7, 7) for x in v]
            keys.append([_num(t, 0, 600), bones])
        if not keys:
            raise ValueError("no keyframes")
        keys.sort(key=lambda k: k[0])
        g["dur"] = _num(data.get("dur", keys[-1][0] or 1), 0.1, 600)
        fade = data.get("fade") or [0.4, 0.5]
        g["fade"] = [_num(fade[0], 0, 10), _num(fade[1], 0, 10)]
        g["keys"] = keys
        expr = {}
        for ch, v in (data.get("expr") or {}).items():
            if not _WORD.match(ch):
                raise ValueError(f"bad face channel: {ch!r}")
            expr[ch] = _num(v, 0, 1) if not isinstance(v, list) else [[_num(t, 0, 600), _num(x, 0, 1)] for t, x in v]
        if expr:
            g["expr"] = expr
    if data.get("about"):
        g["about"] = _text(data["about"])
    if data.get("keywords"):
        g["keywords"] = [_text(k, 60) for k in data["keywords"] if _text(k, 60)][:20]
    for flag in ("private", "lewd", "full"):
        if data.get(flag):
            g[flag] = True
    idle = data.get("idle")
    if isinstance(idle, list):       # only in these mood bands
        bands = [b for b in _words(idle, 6) if b in _IDLE_BANDS]
        if bands:
            g["idle"] = bands
    elif idle:
        g["idle"] = True
    if data.get("touch"):
        g["touch"] = [z for z in _words(data["touch"], 12) if z in _ZONES]
    if data.get("moods"):
        g["moods"] = _words(data["moods"], 20)
    snd = data.get("sound")
    if isinstance(snd, str) and snd.strip():
        g["sound"] = _words([snd.strip()], 1)[0]
    elif isinstance(snd, dict) and snd.get("name"):
        s = {"name": _words([str(snd["name"])], 1)[0]}
        if snd.get("from") == "random":
            s["from"] = "random"
        elif snd.get("from") not in (None, ""):
            s["from"] = _num(snd["from"], 0, 3600)
        if snd.get("len"):
            s["len"] = _num(snd["len"], 0.1, 600)
        g["sound"] = s
    emotes = []
    for e in (data.get("emote") or [])[:6]:
        emotes.append({"name": _words([str(e["name"])], 1)[0], "at": _num(e.get("at", 0), 0, 600)})
    if emotes:
        g["emote"] = emotes if len(emotes) > 1 else emotes[0]
    for k in ("wag", "tail_up"):
        if data.get(k):
            g[k] = _num(data[k], 0, 1)
    # carried through from a gesture loaded into the studio, checked the same way
    if data.get("then"):
        g["then"] = _words([str(data["then"])], 1, _GNAME)[0]
    if data.get("left"):
        g["left"] = True
    if data.get("osc"):
        g["osc"] = [[b, int(_num(ax, 0, 3)), _num(a, -7, 7), _num(hz, 0, 60)]
                    for b, ax, a, hz in data["osc"][:12] if _BONE.match(str(b))]
    # a prop it picks up or puts down (props.js): which, when in it the prop
    # appears or goes, and whether her last pose is held while she carries it
    if data.get("prop"):
        g["prop"] = _words([str(data["prop"])], 1, _GNAME)[0]
    if data.get("prop_at") not in (None, ""):
        g["prop_at"] = _num(data["prop_at"], 0, 600)
    if data.get("hold") is True:
        g["hold"] = True
    if isinstance(data.get("lights"), list):        # her light strips' throb: [[seconds, level], ...]
        g["lights"] = [[_num(t, 0, 600), _num(v, 0, 2)] for t, v in data["lights"][:40]]
    if data.get("face") in ("away", "me"):           # turned square to/away from the camera (gestures.js)
        g["face"] = data["face"]
    if data.get("add"):
        g["add"] = {b: [_num(x, -7, 7) for x in v[:4]] for b, v in data["add"].items() if _BONE.match(str(b)) and isinstance(v, list)}

    lines = [f"// {name}: made in the pose studio (portrait/viewer/studio.js).",
             f"// {g['about']}" if g.get("about") else "// (no description yet)",
             "export default {"]
    for k, v in g.items():
        if k == "keys":
            lines.append("  keys: [")
            lines += [f"    [{t}, {json.dumps(p)}]," for t, p in v]
            lines.append("  ],")
        else:
            lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)},")
    lines.append("};")
    return name, "\n".join(lines) + "\n"


def prop_entry(data):
    """(name, entry) for portrait/props/props.json from the pose studio's prop
    tab: where a prop sits in her hand. Numbers only, clamped; the prop must
    be a .glb in portrait/props/."""
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    name = str(data.get("name", "")).strip().lower()
    if not _GNAME.match(name):
        raise ValueError("name: lower-case letters, numbers and _ only")
    if not os.path.isfile(os.path.join(config.BASE_DIR, "portrait", "props", name + ".glb")):
        raise ValueError(f"there's no portrait/props/{name}.glb")
    hand = str(data.get("hand", "right"))
    if hand not in ("right", "left"):
        raise ValueError("hand: right or left")
    at, turn = list(data.get("at") or []), list(data.get("turn") or [])
    if len(at) != 3 or len(turn) != 3:
        raise ValueError("at and turn are three numbers each")
    return name, {"hand": hand, "at": [_num(v, -0.5, 0.5) for v in at],
                  "turn": [_num(v, -7, 7) for v in turn],
                  "scale": _num(data.get("scale", 1), 0.05, 5)}


def props_list():
    """Every prop model in portrait/props/ (a .glb by its name)."""
    try:
        return sorted(f[:-4] for f in os.listdir(os.path.join(config.BASE_DIR, "portrait", "props"))
                      if f.endswith(".glb") and _GNAME.match(f[:-4]))
    except OSError:
        return []
