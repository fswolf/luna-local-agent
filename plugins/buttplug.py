"""Buttplug - toys of almost any brand, through Intiface Central.

    /buttplug on        connect to Intiface Central
    /buttplug off       stop everything and disconnect
    /buttplug           status: what's connected and what each can do
    /buttplug stop      stop every device now, without asking her
    /buttplug scan      look for devices (turn the toy on first)
    /buttplug find      look for Intiface Central on this PC and your network

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
            "max_motion": 50,
            "ramp_seconds": 3,
            "scan_on_start": true
        }
    }

    max_intensity (0-100) and max_seconds cap whatever she asks for.
    Machines and strokers (thrusting machines, the Solace, The Handy) have
    their own lower cap, max_motion (default 50), and always build up from
    slow over ramp_seconds (default 3) instead of starting at full speed.

A toy that vibrates and strokes can do both at once: vibration (and
rotation or oscillation) and stroking each run on their own, and each
turns off only its own motor when its time is up.

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
            "max_motion": 50, "ramp_seconds": 3, "scan_on_start": True}

PATTERNS = ("pulse", "wave", "escalate", "heartbeat", "tease")
SPIN = ("Vibrate", "Rotate", "Constrict", "Inflate")   # ScalarCmd kinds toy_vibrate drives
# Motion: what machines and strokers do (a thrusting machine, the Solace and
# their kind report "Oscillate"). These go through toy_stroke, with their own,
# lower cap (max_motion) and a ramp up from slow (ramp_seconds), never
# through a vibration command at a vibration's intensity.
MOTION = ("Oscillate",)

_ids = itertools.count(1)
_state = {"ws": None, "connected": False, "error": "", "devices": {}, "server": "", "ping": 0}
_send_lock = threading.Lock()
_waiting = {}          # message id -> [Event, reply]
# What's running, per channel: "spin" (vibrate, oscillate, rotate - toy_vibrate
# and toy_pattern) and "stroke" (toy_stroke). Each has its own job, so a
# toy that does both can vibrate and stroke at once, and one finishing
# turns off only its own motor. token: bumped when a job is replaced or
# stopped, so its worker quits. devs: the device indexes it's driving.
_jobs = {"spin": {"token": 0, "devs": set()}, "stroke": {"token": 0, "devs": set()}}
_jobs_lock = threading.Lock()


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


def _motion_caps():
    """(max motion speed 0-1, ramp seconds) for machines and strokers."""
    s = settings()

    try:
        return max(0.0, min(1.0, float(s["max_motion"]) / 100.0)), max(0.0, min(30.0, float(s["ramp_seconds"])))
    except (TypeError, ValueError):
        return 0.5, 3.0


def _moves(dev):
    """Can it thrust, stroke or oscillate?"""
    return bool(dev["linear"]) or any(k in MOTION for _i, k in dev["scalar"])


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

    if dev["linear"] or any(k in MOTION for _i, k in dev["scalar"]):
        out.append("stroke/thrust (toy_stroke)")

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
                       f"with the server started? ({e}) /buttplug find looks for it.")

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
    with _jobs_lock:
        for job in _jobs.values():
            job["token"] += 1
            job["devs"].clear()

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

    if word == "find":
        return _find()

    if word == "use":
        return _use(text.strip().split(" ", 1)[1] if " " in text.strip() else "")

    return "buttplug: on | off | stop | scan | find | devices"


_found = []


def _find():
    """Look for Buttplug servers here and on the network; save the one found."""
    from plugins import _toyscan

    if _client() is None:
        return "buttplug: " + why_unavailable()
    _found[:] = _toyscan.find_intiface()
    note = (" (Luna is connected to one already, and Intiface takes one client at a time, "
            "so that one may not show)") if _state["connected"] else ""
    if not _found:
        return ("buttplug: no Intiface server found. Is it running with the server started? On "
                "another device (a phone), turn on 'listen on all interfaces' in its settings." + note)
    if len(_found) == 1:
        return _use("1")
    return ("buttplug: found " + "; ".join(f"{i}. {u} ({n})" for i, (u, n) in enumerate(_found, 1))
            + " - /buttplug use <number> picks one." + note)


def _use(which):
    try:
        url, name = _found[int(which) - 1]
    except (ValueError, IndexError):
        return "buttplug: /buttplug find first, then /buttplug use <number>"
    if url == settings()["url"]:
        return f"buttplug: found {name} at {url}, already set. /buttplug on connects."
    config._store(f"plugins.{NAME}.url", url)
    return f"buttplug: found {name} at {url} and saved it. /buttplug on connects."


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


def _set_motion(devs, level):
    """The oscillating motors (thrusting machines, the Solace...) at `level` (0-1)."""
    for dev in devs:
        scalars = [{"Index": i, "Scalar": round(level, 3), "ActuatorType": kind}
                   for i, kind in dev["scalar"] if kind in MOTION]
        if scalars:
            _send("ScalarCmd", {"DeviceIndex": dev["index"], "Scalars": scalars}, wait=False)


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


def _quiet(indexes, channel):
    """Turn off one channel's motor on these devices, leaving the other
    channel running if it's busy with them; a device nothing else is
    using gets a full stop."""
    other = "stroke" if channel == "spin" else "spin"
    for i in indexes:
        dev = _state["devices"].get(i)
        if dev is None:
            continue
        if i in _jobs[other]["devs"]:
            if channel == "spin":
                _set_level([dev], 0.0)       # the stroker keeps going
            else:
                _set_motion([dev], 0.0)      # a machine stops; the vibration keeps going
        else:
            _stop_devices([dev])


def _begin(channel, devs):
    """A new job on a channel: the devices the old job drove and this one
    doesn't are turned off now (nothing else would), then the old job's
    worker is told to quit. Returns the new job's token."""
    new = {d["index"] for d in devs}
    with _jobs_lock:
        job = _jobs[channel]
        left = job["devs"] - new
        job["token"] += 1
        job["devs"] = set(new)
        token = job["token"]
    try:
        _quiet(left, channel)
    except Exception as e:
        logbook.warn(NAME, "couldn't stop a replaced job: %s", e)
    return token


def _still(channel, token, devs):
    """This job's devices, while it's still the current job (a device
    stopped on its own drops out); [] once it's been replaced."""
    job = _jobs[channel]
    if job["token"] != token or not _state["connected"]:
        return []
    return [d for d in devs if d["index"] in job["devs"]]


def _end(channel, token):
    """The job ran its time: turn off its motors, if it's still current."""
    with _jobs_lock:
        job = _jobs[channel]
        if job["token"] != token:
            return
        mine, job["devs"] = set(job["devs"]), set()
    try:
        _quiet(mine, channel)
    except Exception:
        pass


def _play(devs, seconds, level_at, every=0.15):
    """Run on a worker: drive the devices until done or interrupted, then
    turn their vibration off (a stroke on the same toy carries on)."""
    token = _begin("spin", devs)

    def run():
        start = time.monotonic()
        last = None

        try:
            while True:
                now = _still("spin", token, devs)
                t = time.monotonic() - start
                if not now or t >= seconds:
                    break

                level = level_at(t)

                if level != last:
                    _set_level(now, level)
                    last = level

                time.sleep(every)
        except Exception as e:
            logbook.warn(NAME, "pattern stopped: %s", e)
        finally:
            _end("spin", token)

    threading.Thread(target=run, daemon=True, name="buttplug-play").start()


def _stroke(devs, seconds, speed):
    """Machines and strokers, at speed (0-1), building up from slow over
    ramp_seconds rather than starting at full speed: strokers move back
    and forth, oscillating machines get a speed. Vibration on the same toy
    is left alone."""
    token = _begin("stroke", devs)
    ramp = _motion_caps()[1]

    def pace(t):
        return speed if ramp <= 0 else speed * min(1.0, max(0.15, t / ramp))

    def run():
        start, up, last = time.monotonic(), True, None

        try:
            while True:
                t = time.monotonic() - start
                now = _still("stroke", token, devs)
                if not now or t >= seconds:
                    break
                level = round(pace(t), 2)
                if level != last:
                    _set_motion(now, level)
                    last = level
                stroke_ms = int(1500 - 1250 * level)          # 1.5 s per stroke slow, 0.25 s fast
                strokers = [d for d in now if d["linear"]]
                for dev in strokers:
                    _send("LinearCmd", {"DeviceIndex": dev["index"], "Vectors": [
                        {"Index": i, "Duration": stroke_ms, "Position": 0.9 if up else 0.1}
                        for i in range(dev["linear"])]}, wait=False)
                up = not up
                time.sleep(stroke_ms / 1000.0 if strokers else 0.25)
        except Exception as e:
            logbook.warn(NAME, "stroke stopped: %s", e)
        finally:
            _end("stroke", token)

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

        devs = [d for d in _targets(device) if _moves(d)]
        if not devs:
            return "No connected device strokes or thrusts - toy_vibrate is for vibrating ones."

        secs = _seconds(seconds)
        try:
            pace = min(_motion_caps()[0], max(0.0, float(speed) / 100.0))
        except (TypeError, ValueError):
            secs = None
        if secs is None:
            return "speed and seconds must be numbers"

        _stroke(devs, secs, pace)
        ramp = _motion_caps()[1]
        return (f"{', '.join(d['name'] for d in devs)} moving at {round(pace * 100)}% for {secs}s"
                + (f", building up over {ramp:g}s" if ramp else ""))

    def toy_stop(device=None):
        if device in (None, "", "all"):
            return stop_all_devices()[1]

        devs = _targets(device)
        if not devs:
            return "No device by that name."

        gone = {d["index"] for d in devs}
        with _jobs_lock:
            for job in _jobs.values():
                job["devs"] -= gone           # a job driving others carries on with them
        _stop_devices(devs)
        return "stopped " + ", ".join(d["name"] for d in devs)

    def toy_list():
        if not _state["devices"]:
            return f"No devices connected. Ask {config.USER_THEM} to turn one on - /buttplug scan looks for it."

        return "\n".join(f"[{d['index']}] {d['name']}: {', '.join(_abilities(d))}"
                         for d in _state["devices"].values())

    off = lambda: "buttplug plugin is off - /buttplug on"   # noqa: E731
    dev = {"type": "string", "description": "Device number or name from toy_list; omit for all"}
    secs = {"type": "integer", "description": "How long"}

    tools.register_external(
        "toy_vibrate",
        "Set a connected toy to a steady intensity for a while: vibration, and rotation on toys "
        "that do that. Machines and strokers use toy_stroke instead. intensity is 0-100.",
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
        "For strokers and machines (The Handy, the Solace, thrusting machines): move at a speed, "
        "building up from slow. speed is 0-100; it's capped lower than vibration.",
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
