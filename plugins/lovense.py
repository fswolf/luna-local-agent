"""Lovense - she can control Lovense toys connected via the Lovense Remote app.

    /lovense on                  connect to the Remote app on the LAN
    /lovense off                 stop
    /lovense                     status: connected toys, battery
    /lovense stop                stop every toy now, without asking her
    /lovense toys                refresh the list
    /lovense find                look for the Remote app (Game Mode) on your network

How it works: the Lovense Remote app (mobile or PC) exposes a local HTTP API
when Game Mode is on. This plugin posts commands to it. While the plugin is
on, Luna gets tools to vibrate, stop, and check the toys, used when you ask
her ("vibrate for 10 seconds").

A stop word in your message ("stop", "red", "enough"...; "stop_words" in
the settings) stops every toy before she reads it, and so does
interrupting her (HOME), unless "stop_on_interrupt" is false.

She won't use them in a turn that has read outside content (a web page,
an email, an MCP result such as Minecraft chat) or in a scheduled job:
someone else's words shouldn't be able to switch on something physical.
Stream chat never sees these tools at all.

Setup:
    1. Install Lovense Remote on your phone or PC.
    2. Turn on Game Mode in the app (or just leave it running on the same LAN).
    3. Note the IP and port shown in the app (usually something like
       http://192.168.1.x:20010).
    4. Put them in config.json under "plugins", like every other plugin:

    "plugins": {
        "lovense": {
            "enabled": false,
            "host": "192.168.1.50",
            "port": 20010,
            "use_https": false,
            "max_strength": 20,
            "max_seconds": 60,
            "max_motion": 10,
            "ramp_seconds": 3
        }
    }

    max_strength (0-20) and max_seconds cap whatever she asks for.

    Machines (the Mini Sex Machine, the Solace, Gravity's thrusting) move
    with lovense_move, which has its own lower cap, max_motion (0-20,
    default 10), and always builds up from slow over ramp_seconds (default
    3) instead of starting at full speed. A toy that vibrates and thrusts
    can do both at once, and each stops on its own time.

    No developer token needed for local control. The app and this machine
    must be on the same network.
"""
import json
import math
import threading
import time
import urllib.error
import urllib.request

import config
from core import logbook

from plugins import _toys

NAME = "lovense"
SUMMARY = "control Lovense toys via the Remote app on the LAN"

DEFAULTS = {"host": "127.0.0.1", "port": 20010, "use_https": False,
            "max_strength": 20, "max_seconds": 60, "max_motion": 10, "ramp_seconds": 3}

# What machines do, in the Remote app's words (each 0-20). Vibration is
# "Vibrate"; anything here goes through lovense_move instead.
MOTION = ("Thrusting", "Oscillate", "Fingering")

# Lovense's built-in patterns, by the names the Remote app knows.
PRESETS = ("pulse", "wave", "fireworks", "earthquake")

_state = {"model": None, "toys": {}, "error": "", "connected": False}

# What each target is doing: toy id ("" = every toy) -> {"vibe": (level,
# end), "move": (top, end, start, ramp)}. One Function command carries
# both, so vibration and thrusting run together; the driver re-sends it
# as a ramp climbs or one of them runs out, and its timeSec is the
# longest time left, so the app stops the toy itself if Luna goes away.
_plan = {}
_plan_lock = threading.Lock()
_sent = {}
_stop = threading.Event()
_thread = None


def settings():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in config.plugin_settings(NAME).items() if k in DEFAULTS})
    return s


def _caps():
    """(max strength, max seconds) from config, kept inside what the API allows."""
    s = settings()

    try:
        return max(0, min(20, int(s["max_strength"]))), max(1, min(600, int(s["max_seconds"])))
    except (TypeError, ValueError):
        return 20, 60


def _motion_caps():
    """(max motion 0-20, ramp seconds) for machines."""
    s = settings()
    try:
        return max(0, min(20, int(s["max_motion"]))), max(0.0, min(30.0, float(s["ramp_seconds"])))
    except (TypeError, ValueError):
        return 10, 3.0


def stop_all_toys():
    """Stop everything now. No model involved, never blocked."""
    with _plan_lock:
        _plan.clear()
    try:
        _post({"command": "Function", "action": "Stop", "apiVer": 1})
        return True, "lovense: stopped all toys"
    except Exception as e:
        return False, f"lovense: couldn't stop - {e}"


def available():
    return not why_unavailable()


def why_unavailable():
    return ""


def running():
    return _state["connected"]


def start(model):
    global _thread

    if _state["connected"]:
        return True, "lovense: already connected"

    s = settings()
    _state.update(model=model, error="", connected=False)

    # Try an immediate toys check so the user gets feedback.
    ok, msg = _refresh_toys()

    if not ok:
        hint = (" (with use_https the host is usually the app's lovense.club name, not a bare IP)"
                if s["use_https"] and s["host"].replace(".", "").isdigit() else "")
        return False, (f"lovense: couldn't reach the Remote app at {s['host']}:{s['port']} - {msg}{hint}. "
                       "/lovense find looks for it.")

    _state["connected"] = True
    _register_tools()
    # Only now: a failed connect shouldn't leave a watcher running.
    _stop.clear()
    _thread = threading.Thread(target=_watch, daemon=True, name="lovense")
    _thread.start()
    threading.Thread(target=_drive, daemon=True, name="lovense-drive").start()

    return True, f"lovense: connected to {s['host']}:{s['port']} - {msg}"


def stop():
    # Switching off mid-vibration stops the toys too, rather than leaving
    # them running until their timer ends. The tools hide themselves once
    # this is off (available=running), so nothing needs unregistering.
    if _state["connected"]:
        try:
            _post({"command": "Function", "action": "Stop", "apiVer": 1})
        except Exception as e:
            logbook.warn(NAME, "couldn't stop the toys on the way out: %s", e)

    _stop.set()
    _state["connected"] = False
    with _plan_lock:
        _plan.clear()

    return True, "lovense: stopped"


def status():
    s = settings()
    lines = [f"lovense: {'connected' if _state['connected'] else 'off'} - {s['host']}:{s['port']}"]
    if _state["error"]:
        lines.append(f"  last error: {_state['error']}")
    if _state["toys"]:
        for tid, toy in _state["toys"].items():
            bat = toy.get("battery", "?")
            name = toy.get("nickName") or toy.get("name") or tid
            lines.append(f"  {name} ({tid}) - battery {bat}%")
    else:
        lines.append("  no toys seen yet")
    return "\n".join(lines)


def prompt_line(private=True):
    """Tell her a toy is there - only in your own turns."""
    if not private or not _state["connected"]:
        return ""

    names = [t.get("nickName") or t.get("name") or tid for tid, t in _state["toys"].items()]

    return _toys.prompt_line(", ".join(names) or "Lovense (no toy paired in the app yet)",
                             "lovense_vibrate, lovense_move (machines), lovense_pattern and lovense_stop")


def on_user_text(text):
    if _state["connected"] and _toys.says_stop(text, NAME):
        logbook.info(NAME, "stop word - stopping")
        stop_all_toys()


def panic():
    if _state["connected"] and _toys.stop_on_interrupt(NAME):
        stop_all_toys()


def command(text):
    word, _, rest = text.partition(" ")
    word = word.lower()
    if word == "stop":
        return stop_all_toys()[1]
    if word == "toys":
        ok, msg = _refresh_toys()
        return msg if ok else f"couldn't list toys: {msg}"
    if word in ("find", "scan"):
        return _find()
    if word == "use":
        return _use(rest)
    return "lovense: on | off | stop | toys | find"


_found = []


def _find():
    """Look for Lovense Remote in Game Mode on the network; save the one found."""
    from plugins import _toyscan

    _found[:] = _toyscan.find_lovense()
    if not _found:
        return ("lovense: no Remote app found. Is Game Mode on, the app open on screen, and the "
                "phone or tablet on the same Wi-Fi?")
    if len(_found) == 1:
        return _use("1")
    return ("lovense: found " + "; ".join(
        f"{i}. {h}:{p} ({', '.join(t) or 'no toys yet'})" for i, (h, p, _s, t) in enumerate(_found, 1))
        + " - /lovense use <number> picks one.")


def _use(which):
    try:
        host, port, https, toys = _found[int(str(which).strip()) - 1]
    except (ValueError, IndexError):
        return "lovense: /lovense find first, then /lovense use <number>"
    for key, value in (("host", host), ("port", port), ("use_https", https)):
        config._store(f"plugins.{NAME}.{key}", value)
    return (f"lovense: found the Remote app at {host}:{port} ({', '.join(toys) or 'no toys yet'}) "
            "and saved it. /lovense on connects.")


# ---------------------------------------------------------------------------
# Talking to the Remote app
# ---------------------------------------------------------------------------
def _base_url():
    s = settings()
    scheme = "https" if s["use_https"] else "http"
    return f"{scheme}://{s['host']}:{s['port']}"


def _post(payload, timeout=5):
    url = _base_url() + "/command"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "X-platform": "Luna",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            result = json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(str(e.reason)) from e
    except ValueError as e:
        raise RuntimeError("the app's answer wasn't JSON") from e

    # The app answers 200 with an error code inside when it can't do it
    # (no toy, a toy id it doesn't know): that's a failure, not a success.
    code = result.get("code") if isinstance(result, dict) else None

    if code not in (None, 200, "200"):
        raise RuntimeError(f"the Remote app said {code}: {result.get('message') or result.get('type') or 'error'}")

    return result


def _refresh_toys():
    try:
        result = _post({"command": "GetToys"})
    except Exception as e:
        _state["error"] = str(e)
        return False, str(e)

    toys = {}
    data = result.get("data") or {}
    raw = data.get("toys")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    if isinstance(raw, dict):
        toys = raw
    _state["toys"] = toys
    _state["error"] = ""
    if not toys:
        return True, "no toys connected right now"
    names = [f"{t.get('nickName') or t.get('name') or tid} [{tid}]: {', '.join(sorted(_functions(tid))).lower()}"
             for tid, t in toys.items()]
    return True, "toys: " + "; ".join(names)


def _functions(toy_id):
    """What a toy can do, by the app's names; for "" (every toy), what any
    of them can."""
    toys = _state["toys"] if not toy_id else {toy_id: _state["toys"].get(toy_id) or {}}
    found = set()
    for t in toys.values():
        names = t.get("fullFunctionNames") or []
        if isinstance(names, str):
            names = [n for n in names.replace(",", " ").split() if n]
        found.update(str(n).strip().capitalize() for n in names)
    return found or {"Vibrate"}


def _action(key, now):
    """(action, seconds left) for what this target should be doing now, or
    (None, 0) when nothing is."""
    plan = _plan.get(key) or {}
    parts, left = [], 0.0
    vibe = plan.get("vibe")
    if vibe and vibe[1] > now:
        parts.append(f"Vibrate:{vibe[0]}")
        left = max(left, vibe[1] - now)
    move = plan.get("move")
    if move and move[1] > now:
        top, end, start, ramp = move
        level = top if ramp <= 0 else max(1, round(top * min(1.0, max(0.15, (now - start) / ramp))))
        parts += [f"{f}:{level}" for f in MOTION if f in _functions(key)]
        left = max(left, end - now)
    return (",".join(parts), left) if parts else (None, 0.0)


def _apply(key):
    """Send this target's current action (or Stop) if it changed."""
    now = time.monotonic()
    with _plan_lock:
        action, left = _action(key, now)
        if action is None:
            _plan.pop(key, None)
    if action == _sent.get(key):
        return
    payload = ({"command": "Function", "action": action, "timeSec": max(1, math.ceil(left)), "apiVer": 1}
               if action else {"command": "Function", "action": "Stop", "apiVer": 1})
    if key:
        payload["toy"] = key
    _post(payload)
    if action:
        _sent[key] = action
    else:
        _sent.pop(key, None)


def _drive():
    """Keep each target's command current: a ramp climbing, or vibration
    or motion running out while the other carries on."""
    while not _stop.is_set():
        _stop.wait(0.25)
        for key in list(_plan) + [k for k in list(_sent) if k not in _plan]:
            try:
                _apply(key)
            except Exception as e:
                logbook.warn(NAME, "couldn't update a toy: %s", e)


def _watch():
    """Keep the toy list fresh so tools can check availability."""
    while not _stop.is_set():
        _stop.wait(15)
        if _stop.is_set():
            break
        if _state["connected"]:
            try:
                _refresh_toys()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tools she can call
# ---------------------------------------------------------------------------
def _register_tools():
    import tools

    def vibrate(strength=10, seconds=5, toy=None):
        why = _toys.blocked()
        if why:
            logbook.info(NAME, "vibrate refused: %s", why)
            return why

        top, longest = _caps()

        try:
            strength = max(0, min(top, int(strength)))
            seconds = max(1, min(longest, int(seconds)))
        except (TypeError, ValueError):
            return "strength and seconds must be numbers"
        key = str(toy or "")
        with _plan_lock:
            _plan.setdefault(key, {})["vibe"] = (strength, time.monotonic() + seconds)
        try:
            _apply(key)
            who = f"toy {toy}" if toy else "all toys"
            return f"vibrating {who} at {strength}/20 for {seconds}s"
        except Exception as e:
            return f"couldn't vibrate: {e}"

    def move(speed=5, seconds=10, toy=None):
        why = _toys.blocked()
        if why:
            logbook.info(NAME, "move refused: %s", why)
            return why

        key = str(toy or "")
        if not _functions(key) & set(MOTION):
            return ("No connected toy thrusts or strokes (lovense_toys lists what each can do) - "
                    "lovense_vibrate is for vibrating.")
        top, ramp = _motion_caps()
        try:
            speed = max(0, min(top, int(speed)))
            seconds = max(1, min(_caps()[1], int(seconds)))
        except (TypeError, ValueError):
            return "speed and seconds must be numbers"
        now = time.monotonic()
        with _plan_lock:
            _plan.setdefault(key, {})["move"] = (speed, now + seconds, now, ramp)
        try:
            _apply(key)
            who = f"toy {toy}" if toy else "all toys"
            return (f"moving {who} at {speed}/20 for {seconds}s"
                    + (f", building up over {ramp:g}s" if ramp else ""))
        except Exception as e:
            return f"couldn't move: {e}"

    def stop_toys(toy=None):
        with _plan_lock:
            if toy:
                _plan.pop(str(toy), None)
            else:
                _plan.clear()
        payload = {"command": "Function", "action": "Stop", "apiVer": 1}
        if toy:
            payload["toy"] = toy
        try:
            _post(payload)
            return "stopped" + (f" {toy}" if toy else "")
        except Exception as e:
            return f"couldn't stop: {e}"

    def pattern(name="pulse", seconds=10, toy=None):
        why = _toys.blocked()
        if why:
            logbook.info(NAME, "pattern refused: %s", why)
            return why

        name = str(name or "pulse").strip().lower()
        if name not in PRESETS:
            return "pattern must be one of: " + ", ".join(PRESETS)

        try:
            seconds = max(1, min(_caps()[1], int(seconds)))
        except (TypeError, ValueError):
            return "seconds must be a number"

        with _plan_lock:
            _plan.pop(str(toy or ""), None)      # a preset replaces whatever the toy was doing
        _sent.pop(str(toy or ""), None)
        payload = {"command": "Preset", "name": name, "timeSec": seconds, "apiVer": 1}
        if toy:
            payload["toy"] = toy
        try:
            _post(payload)
            return f"{name} on {f'toy {toy}' if toy else 'all toys'} for {seconds}s"
        except Exception as e:
            return f"couldn't start the pattern: {e}"

    def list_toys():
        ok, msg = _refresh_toys()
        return msg

    tools.register_external(
        "lovense_vibrate",
        "Vibrate a Lovense toy at a steady level. strength is 0-20, seconds is how long. "
        "Leave toy blank to hit every connected toy.",
        {"strength": {"type": "integer", "description": "0-20"},
         "seconds": {"type": "integer", "description": "how long, 1-60"},
         "toy": {"type": "string", "description": "toy id, or omit for all"}},
        required=("strength",), run=vibrate, group="Lovense",
        available=running, why=lambda: "lovense plugin is off - /lovense on",
    )
    tools.register_external(
        "lovense_move",
        "Thrust or stroke with a Lovense machine (Mini Sex Machine, Solace, Gravity...), building up "
        "from slow. speed is 0-20 and capped lower than vibration. Runs alongside vibration on toys "
        "that do both.",
        {"speed": {"type": "integer", "description": "0-20"},
         "seconds": {"type": "integer", "description": "how long"},
         "toy": {"type": "string", "description": "toy id, or omit for all"}},
        required=("speed",), run=move, group="Lovense",
        available=running, why=lambda: "lovense plugin is off - /lovense on",
    )
    tools.register_external(
        "lovense_pattern",
        "Run one of the Lovense app's built-in patterns instead of a steady level: "
        "pulse, wave, fireworks or earthquake.",
        {"name": {"type": "string", "enum": list(PRESETS), "description": "Which pattern"},
         "seconds": {"type": "integer", "description": "How long"},
         "toy": {"type": "string", "description": "toy id, or omit for all"}},
        required=("name",), run=pattern, group="Lovense",
        available=running, why=lambda: "lovense plugin is off - /lovense on",
    )
    tools.register_external(
        "lovense_stop",
        "Stop a Lovense toy, vibration and motion (or all of them).",
        {"toy": {"type": "string", "description": "toy id, or omit for all"}},
        required=(), run=stop_toys, group="Lovense",
        available=running, why=lambda: "lovense plugin is off - /lovense on",
    )
    tools.register_external(
        "lovense_toys",
        "List the Lovense toys currently connected to the Remote app.",
        {},
        required=(), run=list_toys, group="Lovense",
        available=running, why=lambda: "lovense plugin is off - /lovense on",
    )

