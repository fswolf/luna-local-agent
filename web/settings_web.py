"""The settings page: every setting, in a browser.

    http://127.0.0.1:8792/settings/      (or /settings in the terminal)

The terminal's settings pane keeps the everyday ones; this page has all
of them, with switches, sliders, drop-downs, search and presets. Both
stand on the same three things, so they can't disagree: config/schema.py
says what a setting is, config.save_any() checks and saves it, and
ui.settings_pane._after() applies the ones that need more than a new
value (the mic mode, presence, the portrait's frame...).

Served by livefeed, so it inherits its guard: localhost only, and a
request whose Host or Origin isn't this server is refused. Changing a
setting also needs this session's key, which is only in the page itself:
another site open in your browser can send a request here, but can't
read the page to learn the key. Passwords and tokens are never sent to
the page, only whether one is set.
"""
import json
import os
import re
import secrets

import config
from core import logbook

NAME = "settings"
KEY = secrets.token_urlsafe(24)       # this session's; a restart makes a new one


def _pane():
    from ui import settings_pane

    return settings_pane


# Sliders for the numbers people drag rather than type: (min, max, step).
RANGES = {
    "tts.speed": (0.5, 2, 0.05), "tts.volume": (0, 2, 0.05), "tts.pitch": (-6, 6, 0.5),
    "stt.sensitivity": (0.2, 3, 0.05), "stt.silence_seconds": (0.4, 4, 0.1),
    "alarms.volume": (0, 2, 0.05), "portrait.sound_volume": (0, 1, 0.05),
    "portrait.match_light": (0, 1, 0.05),
    "portrait.lights.brightness": (0, 2, 0.05),
    "camera.presence.fps": (1, 10, 0.5), "camera.presence.greet_after_minutes": (5, 240, 5),
    "camera.presence.quiet_after_minutes": (1, 60, 1),
}


def _range(kind, line, path=""):
    """A slider's (min, max, step) for the numbers whose line gives a
    0-1 or 0..2 style range, or that RANGES names; None for a plain box."""
    if kind not in ("float", "int"):
        return None
    if path in RANGES:
        return RANGES[path]
    if re.search(r"\b0\s*-\s*1\b", line):
        return (0, 1, 0.01)
    m = re.search(r"\b0 [^,]*, 1 [^,]*, 2\b", line)       # "0 almost flat, 1 as designed, 2 very emotional"
    if m:
        return (0, 2, 0.05)
    return None


def entry(path):
    """One setting, as the page sees it."""
    pane = _pane()
    kind, line, choices = pane.describe(path)
    value, is_set = pane._value(path)
    group, title = pane._section(path)
    from config.schema import BASIC

    out = {"path": path, "name": pane._short(path, group), "group": group, "kind": kind,
           "help": line, "choices": list(choices), "set": is_set,
           "live": bool(config.SETTINGS.get(path, (None, False))[1]),
           "basic": path in BASIC, "range": _range(kind, line, path)}

    if path == "portrait.background":
        # its own control on the page: default / see-through / a colour / a picture
        out["kind"], out["choices"] = "background", config.backgrounds()

    if kind == "secret":
        out["value"] = None
        out["has"] = bool(value)                  # never the secret itself
    elif kind == "dict":
        out["value"] = None                       # a nested block can hold logins (mcp.servers' headers)
        out["has"] = len(value) if isinstance(value, (dict, list)) else 0
    else:
        out["value"] = value

    rng = out["range"]
    if rng and isinstance(value, (int, float)) and not isinstance(value, bool):
        # a value set outside the usual range by hand: widen it rather than clamp
        out["range"] = (min(rng[0], value), max(rng[1], value), rng[2])

    return out


def listing():
    """Every setting, grouped, plus the presets."""
    from config.presets import PRESETS

    pane = _pane()
    groups, where = [], {}

    for path in pane._all_paths():
        group, title = pane._section(path)

        if group not in where:
            where[group] = len(groups)
            groups.append({"key": group, "title": title, "settings": []})

        groups[where[group]]["settings"].append(entry(path))

    presets = [{"name": n, "kind": p.get("kind", "use"), "label": p["label"], "about": p["about"], "count": len(p["values"]),
                "values": p["values"],
                "active": all(pane._value(path)[0] == v for path, v in p["values"].items())}
               for n, p in PRESETS.items()]

    return {"groups": groups, "presets": presets, "station": _station_panel()}


def _station_panel():
    try:
        from web import station

        return station.panel()
    except Exception as e:
        return {"error": f"relay stations: {e}"}


def _raw(value):
    """What the page sent -> the text config's checks expect."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(map(str, value))
    if value is None:
        return ""
    return str(value)


def change(path, value):
    """Save one setting and apply it. Returns (ok, message, entry or None)."""
    if not isinstance(path, str) or not path or len(path) > 120:
        return False, "no such setting", None
    if path not in _pane()._all_paths():
        return False, f"unknown setting {path!r}", None

    try:
        saved, live = config.save_any(path, _raw(value))
    except ValueError as e:
        return False, str(e), None
    except OSError as e:
        return False, f"couldn't write config.json: {e}", None

    _pane()._after(path, saved)
    logbook.info("settings", "web: %s changed", path)
    return True, "saved" + ("" if live else ", applies after a restart"), entry(path)


def reset(path):
    if path not in _pane()._all_paths():
        return False, f"unknown setting {path!r}", None
    try:
        removed = config.reset_setting(path)
    except OSError as e:
        return False, f"couldn't write config.json: {e}", None
    return True, ("back to the default after a restart" if removed else "already the default"), entry(path)


def preset(name):
    from config import presets

    try:
        done = presets.apply(name)
    except KeyError:
        return False, f"no preset {name!r}", None
    except (ValueError, OSError) as e:
        return False, str(e), None

    for path, value, _live in done:
        _pane()._after(path, value)

    later = sum(1 for _p, _v, live in done if not live)
    label = presets.PRESETS[name]["label"]
    logbook.info("settings", "web: preset %s", name)
    return True, (f"{label}: {len(done)} settings changed"
                  + (f", {later} after a restart" if later else "")), None


# ---------------------------------------------------------------------------
# The page (livefeed.add_page)
# ---------------------------------------------------------------------------
def handle(method, sub, body, key=None):
    """(status, content type, body) for /settings/<sub>."""
    sub = sub or "/"

    if method == "GET" and sub == "/":
        return 200, "text/html; charset=utf-8", PAGE.replace("__KEY__", KEY)

    if method == "GET" and sub == "/api":
        return 200, "application/json", json.dumps(listing())

    if method == "POST" and sub == "/api":
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = None
        if not isinstance(data, dict) or not secrets.compare_digest(str(data.get("key", "")), KEY):
            return 403, "application/json", json.dumps({"ok": False, "message": "this page is out of date - reload it"})

        action = data.get("action")
        if action == "set":
            ok, message, item = change(data.get("path"), data.get("value"))
        elif action == "reset":
            ok, message, item = reset(data.get("path"))
        elif action == "preset":
            ok, message, item = preset(str(data.get("name", "")))
        elif action in ("station_pair", "station_forget"):
            return 200, "application/json", json.dumps(_station_action(action, data))
        else:
            ok, message, item = False, "unknown action", None

        return (200 if ok else 400), "application/json", json.dumps({"ok": ok, "message": message, "entry": item})

    return 404, "text/plain; charset=utf-8", "not found"


def _station_action(action, data):
    """Pair a phone or tablet (a one-time code and its QR), or unpair one."""
    from web import station

    if action == "station_forget":
        ok = station.forget(str(data.get("device", "")))
        return {"ok": ok, "message": "unpaired" if ok else "no such device", "station": station.panel()}
    if not station.running():
        return {"ok": False, "message": "switch relay stations on first" if not getattr(config, "STATION_ENABLED", False)
                else (station.panel().get("error") or "the stations aren't running")}
    code, url = station.new_pairing(data.get("name") or "station")
    return {"ok": True, "message": f"scan it within {station.PAIR_MINUTES} minutes", "url": url,
            "qr": station.qr_svg(url), "station": station.panel()}


def register():
    from web import livefeed

    livefeed.add_page(NAME, "settings", lambda method, sub, body: handle(method, sub, body))


def url():
    from web import livefeed

    return livefeed.url() + "/settings/"


def _web_page(name):
    """A page's HTML from web/ (kept out of the code so each side reads as what it is)."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name), encoding="utf-8") as f:
        return f.read()


PAGE = _web_page("settings.html")   # the page itself: web/settings.html
