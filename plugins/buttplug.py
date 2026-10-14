"""Buttplug - toys of almost any brand, through Intiface Central.

    /buttplug on        connect to Intiface Central
    /buttplug off       stop everything and disconnect
    /buttplug           status: what's connected and what each can do
    /buttplug stop      stop every device now, without asking her
    /buttplug scan      look for devices (turn the toy on first)

Credit where it's due: this plugin is a thin client. The hard part, the
protocols of hundreds of devices, is the work of the Buttplug.io
project (https://buttplug.io) and its Intiface Central app
(https://intiface.com/central/), open source under the BSD 3-Clause
licence. Lovense, Kiiroo, We-Vibe, Satisfyer, The Handy, Magic Motion,
Vorze and many more, plus Xbox gamepads and Switch Joy-Cons, which makes
it easy to test with no toy at all.

How it works: Intiface Central runs on your PC, talks to the devices
over Bluetooth, and serves the Buttplug protocol (v3) on a local
websocket. This plugin connects to it; nothing leaves your machine.

Setup:
    1. Install Intiface Central and press Start Server.
    2. Turn the device on and close its own phone app (a Bluetooth toy
       talks to one thing at a time). Intiface finds it when scanning.
    3. /buttplug on (or "enabled": true to connect at startup):

    "plugins": {
        "buttplug": {
            "enabled": false,
            "url": "ws://127.0.0.1:12345",
            "max_intensity": 100,
            "max_seconds": 60,
            "scan_on_start": true
        }
    }

    max_intensity (0-100) and max_seconds cap whatever she asks for.

Needs websocket-client (installer extra "toys", or pip install
websocket-client).

A stop word in your message ("stop", "red", "enough"...; "stop_words" in
the settings) stops every device before she reads it, and so does
interrupting her (HOME), unless "stop_on_interrupt" is false.

She won't use it in a turn that has read outside content (a web page, an
email, an MCP result such as Minecraft chat) or in a scheduled job:
someone else's words shouldn't be able to switch on something physical.
Stopping is never blocked, and stream chat never sees these tools.
"""
import itertools
import json
import math
import threading
import time

import config
import logbook

from plugins import _toys

NAME = "buttplug"
SUMMARY = "toys of almost any brand through Intiface Central (buttplug.io)"

DEFAULTS = {"url": "ws://127.0.0.1:12345", "max_intensity": 100, "max_seconds": 60,
            "scan_on_start": True}

PATTERNS = ("pulse", "wave", "escalate", "heartbeat", "tease")
SPIN = ("Vibrate", "Oscillate", "Rotate", "Constrict", "Inflate")   # ScalarCmd kinds an intensity drives

_ids = itertools.count(1)
_state = {"ws": None, "connected": False, "error": "", "devices": {}, "server": "", "ping": 0}
_send_lock = threading.Lock()
_waiting = {}          # message id -> [Event, reply]
_run = {"token": 0}    # bumped by every new command: a running pattern or timer sees it and quits


def settings():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in config.plugin_settings(NAME).items() if k in DEFAULTS})
    return s


def _caps():
    """(max intensity 0-1, max seconds) from config, kept sane."""
    s = settings()

    try:
        return max(0.0, min(1.0, float(s["max_intensity"]) / 100.0)), max(1, min(600, int(s["max_seconds"])))
    except (TypeError, ValueError):
        return 1.0, 60


def _client():
    try:
        import websocket  # websocket-client

        return websocket
    except ImportError:
        return None


def available():
    return not why_unavailable()


def why_unavailable():
    return "" if _client() else "websocket-client isn't installed - pip install websocket-client"


def running():
    return _state["connected"]


# ---------------------------------------------------------------------------
# The connection: one socket, a reader thread, replies matched by Id
# ---------------------------------------------------------------------------
def _send(kind, body=None, wait=True, timeout=5):
    """Send one Buttplug message; return the reply's (kind, body), or raise."""
    ws = _state["ws"]

    if ws is None:
        raise RuntimeError("not connected to Intiface")

    mid = next(_ids)
    slot = [threading.Event(), None]

    if wait:
        _waiting[mid] = slot

    with _send_lock:
        ws.send(json.dumps([{kind: dict(body or {}, Id=mid)}]))

    if not wait:
        return None

    if not slot[0].wait(timeout):
        _waiting.pop(mid, None)
        raise RuntimeError(f"Intiface didn't answer {kind}")

    reply_kind, reply = slot[1]

    if reply_kind == "Error":
        raise RuntimeError(reply.get("ErrorMessage") or "Intiface reported an error")

    return reply_kind, reply


def _reader(ws):
    while True:
        try:
            raw = ws.recv()
        except Exception as e:
            if _state["ws"] is ws:
                _state["error"] = f"connection lost: {e}"
                logbook.warn(NAME, "connection to Intiface lost: %s", e)
                _state.update(ws=None, connected=False)
            return

        try:
            messages = json.loads(raw)
        except ValueError:
            continue

        for message in messages if isinstance(messages, list) else []:
            for kind, body in message.items():
                body = body or {}

                if kind == "DeviceAdded":
                    _add_device(body)
                    logbook.info(NAME, "device added: %s", _name(body))
                elif kind == "DeviceRemoved":
                    _state["devices"].pop(body.get("DeviceIndex"), None)
                elif kind == "DeviceList":
                    _state["devices"] = {}
                    for d in body.get("Devices") or []:
                        _add_device(d)

                slot = _waiting.pop(body.get("Id"), None)

                if slot:
                    slot[1] = (kind, body)
                    slot[0].set()


def _pinger(ws, every):
    # Intiface stops every device if a client with a ping time goes quiet,
    # which is the right failsafe; this keeps a live connection alive.
    while _state["ws"] is ws:
        time.sleep(every)

        try:
            _send("Ping", wait=False)
        except Exception:
            return


def _name(d):
    return d.get("DeviceDisplayName") or d.get("DeviceName") or f"device {d.get('DeviceIndex')}"


def _add_device(d):
    msgs = d.get("DeviceMessages") or {}
    _state["devices"][d.get("DeviceIndex")] = {
        "index": d.get("DeviceIndex"),
        "name": _name(d),
        "scalar": [(i, a.get("ActuatorType")) for i, a in enumerate(msgs.get("ScalarCmd") or [])],
        "rotate": len(msgs.get("RotateCmd") or []),
        "linear": len(msgs.get("LinearCmd") or []),
        "battery": "SensorReadCmd" in msgs and any(
            s.get("SensorType") == "Battery" for s in msgs.get("SensorReadCmd") or []),
    }


def _abilities(dev):
    out = sorted({kind.lower() for _i, kind in dev["scalar"]})

    if dev["rotate"]:
        out.append("rotate")

    if dev["linear"]:
        out.append("stroke")

    return out or ["nothing Luna can drive"]


# ---------------------------------------------------------------------------
# Plugin lifecycle
# ---------------------------------------------------------------------------
def start(model):
    if _state["connected"]:
        return True, "buttplug: already connected"

    websocket = _client()

    if websocket is None:
        return False, "buttplug: " + why_unavailable()

    url = settings()["url"]

    try:
        ws = websocket.create_connection(url, timeout=5)
        ws.settimeout(None)
    except Exception as e:
        _state["error"] = str(e)
        return False, (f"buttplug: couldn't reach Intiface Central at {url} - is it running "
                       f"with the server started? ({e})")

    _state.update(ws=ws, error="", devices={})
    threading.Thread(target=_reader, args=(ws,), daemon=True, name="buttplug").start()

    try:
        _kind, info = _send("RequestServerInfo", {"ClientName": "Luna", "MessageVersion": 3})
        _state["server"] = info.get("ServerName") or "Intiface"
        ping = int(info.get("MaxPingTime") or 0)

        if ping > 0:
            threading.Thread(target=_pinger, args=(ws, max(0.2, ping / 2000.0)), daemon=True).start()

        _send("RequestDeviceList")

        if settings()["scan_on_start"]:
            _send("StartScanning")
    except Exception as e:
        _close()
        _state["error"] = str(e)
        return False, f"buttplug: Intiface answered but the handshake failed - {e}"

    _state["connected"] = True
    _register_tools()
    found = ", ".join(d["name"] for d in _state["devices"].values()) or "no devices yet - scanning"

    return True, f"buttplug: connected to {_state['server']} at {url} - {found}"


def _close():
    ws = _state["ws"]
    _state.update(ws=None, connected=False)

    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass


def stop():
    # Everything stops before the socket closes, never left running.
    if _state["connected"]:
        stop_all_devices()

    _close()

    return True, "buttplug: stopped"


def stop_all_devices():
    """Stop everything now. No model involved, never blocked."""
    _run["token"] += 1

    try:
        _send("StopAllDevices")
        return True, "buttplug: stopped all devices"
    except Exception as e:
        return False, f"buttplug: couldn't stop - {e}"


def status():
    s = settings()
    lines = [f"buttplug: {'connected to ' + _state['server'] if _state['connected'] else 'off'} - {s['url']}"]

    if _state["error"]:
        lines.append(f"  last error: {_state['error']}")

    for dev in _state["devices"].values():
        lines.append(f"  [{dev['index']}] {dev['name']} - {', '.join(_abilities(dev))}")

    if _state["connected"] and not _state["devices"]:
        lines.append("  no devices - turn one on and /buttplug scan")

    lines.append("  Device support by Buttplug.io and Intiface Central (buttplug.io)")

    return "\n".join(lines)


def prompt_line(private=True):
    """Tell her what's connected - only in your own turns."""
    if not private or not _state["connected"] or not _state["devices"]:
        return ""

    names = ", ".join(f"{d['name']} ({'/'.join(_abilities(d))})" for d in _state["devices"].values())

    return _toys.prompt_line(names, "toy_vibrate, toy_pattern, toy_stroke and toy_stop")


def on_user_text(text):
    if _state["connected"] and _toys.says_stop(text, NAME):
        logbook.info(NAME, "stop word - stopping")
        stop_all_devices()


def panic():
    if _state["connected"] and _toys.stop_on_interrupt(NAME):
        stop_all_devices()


def command(text):
    word = text.strip().split(" ", 1)[0].lower()

    if word == "stop":
        return stop_all_devices()[1]

    if word == "scan":
        try:
            _send("StartScanning")
            return "buttplug: scanning - turn the device on; /buttplug shows what's found"
        except Exception as e:
            return f"buttplug: couldn't scan - {e}"

    if word in ("devices", "list"):
        return status()

    return "buttplug: on | off | stop | scan | devices"


# ---------------------------------------------------------------------------
# Driving devices
# ---------------------------------------------------------------------------
def _targets(device):
    """The devices a command is for: one by number or name, or all of them."""
    devices = list(_state["devices"].values())

    if device in (None, "", "all"):
        return devices

    text = str(device).strip().lower()

    return [d for d in devices if str(d["index"]) == text or text in d["name"].lower()]


def _set_level(devs, level):
    """Every vibrate/oscillate/rotate-type motor on these devices at `level` (0-1)."""
    for dev in devs:
        scalars = [{"Index": i, "Scalar": round(level, 3), "ActuatorType": kind}
                   for i, kind in dev["scalar"] if kind in SPIN]

        if scalars:
            _send("ScalarCmd", {"DeviceIndex": dev["index"], "Scalars": scalars}, wait=False)

        if dev["rotate"]:
            _send("RotateCmd", {"DeviceIndex": dev["index"], "Rotations": [
                {"Index": i, "Speed": round(level, 3), "Clockwise": True} for i in range(dev["rotate"])]},
                wait=False)


def _stop_devices(devs):
    for dev in devs:
        _send("StopDeviceCmd", {"DeviceIndex": dev["index"]}, wait=False)


def _shape(name, t, seconds):
    """A pattern's level (0-1) at t seconds."""
    if name == "pulse":
        return 1.0 if (t % 1.0) < 0.5 else 0.0
    if name == "wave":
        return 0.5 - 0.5 * math.cos(2 * math.pi * t / 4.0)
    if name == "escalate":
        return min(1.0, 0.15 + 0.85 * t / max(1.0, seconds))
    if name == "heartbeat":
        beat = t % 1.2
        return 1.0 if beat < 0.12 or 0.25 <= beat < 0.37 else 0.0
    if name == "tease":
        return 0.7 if (t % 5.0) < 2.0 else 0.15

    return 0.5


def _play(devs, seconds, level_at, every=0.15):
    """Run on a worker: drive the devices until done or interrupted, then stop them."""
    _run["token"] += 1
    token = _run["token"]

    def run():
        start = time.monotonic()
        last = None

        try:
            while _run["token"] == token and _state["connected"]:
                t = time.monotonic() - start

                if t >= seconds:
                    break

                level = level_at(t)

                if level != last:
                    _set_level(devs, level)
                    last = level

                time.sleep(every)
        except Exception as e:
            logbook.warn(NAME, "pattern stopped: %s", e)
        finally:
            if _run["token"] == token:
                try:
                    _stop_devices(devs)
                except Exception:
                    pass

    threading.Thread(target=run, daemon=True, name="buttplug-play").start()


def _stroke(devs, seconds, speed):
    """Strokers: back and forth, faster with speed (0-1)."""
    _run["token"] += 1
    token = _run["token"]
    stroke_ms = int(1500 - 1250 * speed)          # 1.5 s per stroke slow, 0.25 s fast

    def run():
        start, up = time.monotonic(), True

        try:
            while _run["token"] == token and _state["connected"] and time.monotonic() - start < seconds:
                for dev in devs:
                    _send("LinearCmd", {"DeviceIndex": dev["index"], "Vectors": [
                        {"Index": i, "Duration": stroke_ms, "Position": 0.9 if up else 0.1}
                        for i in range(dev["linear"])]}, wait=False)
                up = not up
                time.sleep(stroke_ms / 1000.0)
        except Exception as e:
            logbook.warn(NAME, "stroke stopped: %s", e)
        finally:
            if _run["token"] == token:
                try:
                    _stop_devices(devs)
                except Exception:
                    pass

    threading.Thread(target=run, daemon=True, name="buttplug-stroke").start()


# ---------------------------------------------------------------------------
# Tools she can call
# ---------------------------------------------------------------------------
def _seconds(value, default=10):
    try:
        return max(1, min(_caps()[1], int(value if value not in (None, "") else default)))
    except (TypeError, ValueError):
        return None


def _register_tools():
    import tools

    def toy_vibrate(intensity=50, seconds=10, device=None):
        why = _toys.blocked()
        if why:
            logbook.info(NAME, "vibrate refused: %s", why)
            return why

        devs = [d for d in _targets(device) if any(k in SPIN for _i, k in d["scalar"]) or d["rotate"]]
        if not devs:
            return "No connected device can do that - toy_list shows what's there."

        secs = _seconds(seconds)
        if secs is None:
            return "intensity and seconds must be numbers"

        try:
            level = min(_caps()[0], max(0.0, float(intensity) / 100.0))
        except (TypeError, ValueError):
            return "intensity and seconds must be numbers"

        _play(devs, secs, lambda t: level)
        return f"{', '.join(d['name'] for d in devs)} at {round(level * 100)}% for {secs}s"

    def toy_pattern(name="wave", seconds=15, intensity=100, device=None):
        why = _toys.blocked()
        if why:
            logbook.info(NAME, "pattern refused: %s", why)
            return why

        name = str(name or "wave").strip().lower()
        if name not in PATTERNS:
            return "pattern must be one of: " + ", ".join(PATTERNS)

        devs = [d for d in _targets(device) if any(k in SPIN for _i, k in d["scalar"]) or d["rotate"]]
        if not devs:
            return "No connected device can do that - toy_list shows what's there."

        secs = _seconds(seconds, 15)
        try:
            peak = min(_caps()[0], max(0.0, float(intensity) / 100.0))
        except (TypeError, ValueError):
            secs = None
        if secs is None:
            return "intensity and seconds must be numbers"

        _play(devs, secs, lambda t: round(peak * _shape(name, t, secs), 2))
        return f"{name} on {', '.join(d['name'] for d in devs)} for {secs}s, peak {round(peak * 100)}%"

    def toy_stroke(speed=50, seconds=10, device=None):
        why = _toys.blocked()
        if why:
            logbook.info(NAME, "stroke refused: %s", why)
            return why

        devs = [d for d in _targets(device) if d["linear"]]
        if not devs:
            return "No connected device strokes - toy_vibrate is for vibrating ones."

        secs = _seconds(seconds)
        try:
            pace = min(_caps()[0], max(0.0, float(speed) / 100.0))
        except (TypeError, ValueError):
            secs = None
        if secs is None:
            return "speed and seconds must be numbers"

        _stroke(devs, secs, pace)
        return f"{', '.join(d['name'] for d in devs)} stroking at {round(pace * 100)}% for {secs}s"

    def toy_stop(device=None):
        if device in (None, "", "all"):
            return stop_all_devices()[1]

        devs = _targets(device)
        if not devs:
            return "No device by that name."

        _run["token"] += 1
        _stop_devices(devs)
        return "stopped " + ", ".join(d["name"] for d in devs)

    def toy_list():
        if not _state["devices"]:
            return "No devices connected. Ask him to turn one on - /buttplug scan looks for it."

        return "\n".join(f"[{d['index']}] {d['name']}: {', '.join(_abilities(d))}"
                         for d in _state["devices"].values())

    off = lambda: "buttplug plugin is off - /buttplug on"   # noqa: E731
    dev = {"type": "string", "description": "Device number or name from toy_list; omit for all"}
    secs = {"type": "integer", "description": "How long"}

    tools.register_external(
        "toy_vibrate",
        "Set a connected toy to a steady intensity for a while: vibration, and rotation or "
        "oscillation on toys that do that. intensity is 0-100.",
        {"intensity": {"type": "integer", "description": "0-100"}, "seconds": secs, "device": dev},
        required=("intensity",), run=toy_vibrate, group="Toys", available=running, why=off)
    tools.register_external(
        "toy_pattern",
        "Run a pattern instead of a steady level: pulse, wave, escalate (builds up), heartbeat "
        "or tease. intensity is the peak, 0-100.",
        {"name": {"type": "string", "enum": list(PATTERNS)}, "seconds": secs,
         "intensity": {"type": "integer", "description": "Peak, 0-100"}, "device": dev},
        required=("name",), run=toy_pattern, group="Toys", available=running, why=off)
    tools.register_external(
        "toy_stroke",
        "For stroker toys (The Handy and similar): move back and forth. speed is 0-100.",
        {"speed": {"type": "integer", "description": "0-100"}, "seconds": secs, "device": dev},
        required=("speed",), run=toy_stroke, group="Toys", available=running, why=off)
    tools.register_external(
        "toy_stop",
        "Stop a toy, or all of them.",
        {"device": dev}, required=(), run=toy_stop, group="Toys", available=running, why=off)
    tools.register_external(
        "toy_list",
        "Which toys are connected and what each can do.",
        {}, required=(), run=toy_list, group="Toys", available=running, why=off)
