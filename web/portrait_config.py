"""What the portrait page is told when it loads: which model, its clips and
sidecar, the gesture mode, moods, light strips and the rest of its config.

Part of the web package; web/livefeed.py is the front door.
"""
import json
import os
import re
import config
from core import logbook
from web import livefeed


def portrait_models():
    """Every model in portrait/models, as paths portrait.model takes:
    a folder's .model3.json (Live2D), and any .vrm / .glb (3D)."""
    root = os.path.join(config.BASE_DIR, "portrait", "models")
    found = []

    for dirpath, _dirs, files in sorted(os.walk(root)):
        if dirpath[len(root):].count(os.sep) > 2:      # not deep inside a model's own folders
            continue

        for f in sorted(files):
            if f.endswith((".model3.json", ".vrm", ".glb")):
                found.append(os.path.relpath(os.path.join(dirpath, f), os.path.dirname(root)).replace(os.sep, "/"))

    return found


def portrait_clips():
    """The animation clips in portrait/animations: every .vrma, with its
    settings from clips.json (keyed by file name, without .vrma).

    A clip plays as the gesture it's named after - wave.vrma replaces the
    built-in wave, wave-2.vrma is a second one to pick from at random -
    or as whatever "as" says. Anything in animations/private/ is private:
    never played from chat, and only offered to her in your own turns.
    """
    base = os.path.join(config.BASE_DIR, "portrait")
    root = os.path.join(base, "animations")
    settings = {}

    for sub in ("", "private"):
        try:
            with open(os.path.join(root, sub, "clips.json"), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                settings.update({k: v for k, v in data.items() if isinstance(v, dict)})
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            logbook.warn("monitor", "ignoring %s/clips.json: %s", sub or "animations", e)

    found = []

    for dirpath, _dirs, files in sorted(os.walk(root)):
        if dirpath[len(root):].count(os.sep) > 1:
            continue

        for f in sorted(files):
            if not f.lower().endswith(".vrma"):
                continue

            stem = f[:-5]
            opts = dict(settings.get(stem, {}))
            name = str(opts.pop("as", "") or re.sub(r"[-_ ]?\d+$", "", stem) or stem).strip().lower().replace(" ", "_")
            rel = os.path.relpath(os.path.join(dirpath, f), base).replace(os.sep, "/")
            private = bool(opts.get("private", "/private/" in "/" + rel + "/"))
            found.append(dict(opts, name=name, file=rel, private=private))

    return found


def _model_sidecar(path):
    """The luna.json beside a model, or {} - a broken one is a log line,
    not a portrait that won't load."""
    side = os.path.join(os.path.dirname(path), "luna.json")

    try:
        with open(side, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logbook.warn("monitor", "ignoring %s: %s", side, e)
        return {}


def _gesture_mode():
    try:
        from life import gestures

        return gestures.mode()
    except Exception:
        return "keywords"


def _clothes_mode():
    try:
        from life import clothes

        return clothes.mode()
    except Exception:
        return "keywords"


def gesture_mode_changed():
    """Tell an open portrait the gesture (and clothes) settings changed."""
    livefeed.emit("gesture_mode", mode=_gesture_mode(), clothes=_clothes_mode(),
         chat=bool(getattr(config, "PORTRAIT_CHAT_GESTURES", True)))


def _mood_list():
    """Every mood, for the debug viewer's mood menu ([] if moods.json won't load)."""
    try:
        from mind import mood

        return mood.preview_list()
    except Exception as e:
        logbook.warn("monitor", "mood list for the portrait: %s", e)
        return []


def lights_config():
    """portrait.lights, as the page's lights.js takes it."""
    return {"enabled": bool(getattr(config, "PORTRAIT_LIGHTS_ENABLED", False)),
            "color": str(getattr(config, "PORTRAIT_LIGHTS_COLOR", "") or ""),
            "brightness": float(getattr(config, "PORTRAIT_LIGHTS_BRIGHTNESS", 1.0)),
            "voice": bool(getattr(config, "PORTRAIT_LIGHTS_VOICE", True)),
            "private": bool(getattr(config, "PORTRAIT_LIGHTS_PRIVATE", True)),
            "style": str(getattr(config, "PORTRAIT_LIGHTS_STYLE", "neon"))}


def lights_changed():
    """Tell an open portrait the light strip settings changed."""
    livefeed.emit("lights", lights=lights_config())


def portrait_config(preview=None):
    """What the portrait page needs from config.json: which model, and
    which nodes are her ears if their names don't say so. A model that
    isn't there falls back to Luna's robot model, then Sigewinne; with
    neither, the page says so."""
    root = os.path.join(config.BASE_DIR, "portrait")
    model = str(preview or getattr(config, "PORTRAIT_MODEL", "") or "")
    missing = ""

    if not model or not os.path.isfile(os.path.join(root, model)):
        missing = model
        model = ""
        for fallback in (getattr(config, "_LUNA_ROBOT", "models/luna/robot_default.vrm"),
                         getattr(config, "_SIGEWINNE", "models/sigewinne/sigewinne.model3.json")):
            if os.path.isfile(os.path.join(root, fallback)):
                model = fallback
                break

    # The live2d block belongs to one model, so it travels with it: a
    # luna.json in the model's folder (framing, expressions, credit).
    # Without one, what config.json says, else Sigewinne's expressions
    # for Sigewinne and nothing for anything else.
    sidecar = _model_sidecar(os.path.join(root, model)) if model else {}
    live2d = sidecar.get("live2d") or (config._stored("portrait.live2d")
                                       if model == getattr(config, "PORTRAIT_MODEL", "") else None) or {}
    if not live2d and model == getattr(config, "_SIGEWINNE", ""):
        live2d = {"expressions": {"sad": "tears", "flustered": "x_eyes", "confused": "spiral_eyes"}}

    return {"model": model, "missing": missing,
            "ear_bones": list(getattr(config, "PORTRAIT_EAR_BONES", []) or []),
            "live2d": live2d, "credit": str(sidecar.get("credit") or ""),
            "vrm": dict(sidecar.get("vrm") or {}),
            "gestures": _gesture_mode(),
            "clothes": _clothes_mode(),
            "chat_gestures": bool(getattr(config, "PORTRAIT_CHAT_GESTURES", True)),
            "sounds": bool(getattr(config, "PORTRAIT_SOUNDS", True)),
            "sound_volume": float(getattr(config, "PORTRAIT_SOUND_VOLUME", 0.8)),
            "frame": str(getattr(config, "PORTRAIT_FRAME", "bust")),
            "lights": lights_config(),
            "moods": _mood_list(),
            "background": str(getattr(config, "PORTRAIT_BACKGROUND", "") or ""),
            "match_light": float(getattr(config, "PORTRAIT_MATCH_LIGHT", 0.6)),
            "seasonal": config.seasonal_backgrounds(),
            "fan": dict(getattr(config, "PORTRAIT_FAN", {}) or {},
                        cast=bool(getattr(config, "PORTRAIT_FAN_CAST", False))),
            "clips": portrait_clips(),
            "hologram": dict(getattr(config, "PORTRAIT_HOLOGRAM", {}) or {},
                             enabled=bool(getattr(config, "PORTRAIT_HOLOGRAM_ENABLED", False)))}


def portrait_url(transparent=False):
    return livefeed.url() + "/portrait/" + ("?bg=transparent" if transparent else "")
