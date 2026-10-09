"""Home - your smart home, through Home Assistant on your own network.

    /home on          connect (her home tools appear in the tools pane)
    /home off         disconnect
    /home             status: where it's pointed, what she can see, what asks
    /home refresh     re-read the device list (after you expose something new)

Home Assistant (home-assistant.io) runs on a machine of yours and talks
to your lights, plugs, sensors and the rest over your own network. It has
an MCP server built in; this plugin connects Luna to it, so "turn off the
living room lights", "is the back door locked?" or "what's the
temperature upstairs?" become tool calls.

Local only, on purpose:
  * The address must be on your own network - localhost, a 192.168.x /
    10.x / 172.16-31.x address, or a name that resolves to one
    (homeassistant.local). Anything else is refused, so a typo or a
    copied cloud URL can't send your home's state off the box.
  * Nothing goes through Nabu Casa or any other cloud. Luna talks to
    Home Assistant directly; Home Assistant talks to your devices.

What she can touch is decided in Home Assistant, not here: Settings ->
Voice assistants -> Expose. She only sees and controls what's ticked
there. Start with a few lights.

Some things always ask first, even from Discord in auto mode: anything
in the ask_domains below (locks, garage doors and covers, alarms,
valves, sirens), and a sweep with no device named ("turn everything off
upstairs") while any of those are exposed. ask_all makes every change
ask. Reading state never asks.

Setup:
    1. In Home Assistant: Settings -> Devices & services -> Add
       integration -> "Model Context Protocol Server".
    2. Your profile (bottom left) -> Security -> Long-lived access
       tokens -> Create token. Copy it.
    3. Put it outside the repo:
           ~/.config/ai-voice/homeassistant.json
           {"token": "eyJhbGciOi..."}
       (or HASS_TOKEN in the environment)
    4. pip install mcp, then /home on.

    "home": {
        "enabled": false,
        "url": "http://localhost:8123",    # later: http://192.168.1.50:8123
        "ask_all": false,
        "ask_domains": ["lock", "cover", "alarm_control_panel", "valve", "siren"],
        "skip_tools": [...]                 # HA's own timers - she has reminders
    }
"""
import ipaddress
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import logbook

NAME = "home"
SUMMARY = "your smart home, through Home Assistant on your own network"

SERVER = "home"
CREDENTIALS_FILE = os.path.expanduser("~/.config/ai-voice/homeassistant.json")

# Timers duplicate her reminders and cost prompt space; broadcast talks
# out of your speakers. Both off unless you clear this list.
SKIP_TOOLS = ["HassStartTimer", "HassCancelTimer", "HassCancelAllTimers", "HassIncreaseTimer",
              "HassDecreaseTimer", "HassPauseTimer", "HassUnpauseTimer", "HassTimerStatus",
              "HassBroadcast"]

DEFAULTS = {"url": "http://localhost:8123", "ask_all": False,
            "ask_domains": ["lock", "cover", "alarm_control_panel", "valve", "siren"],
            "skip_tools": SKIP_TOOLS}

# Reading never asks. Everything else is a change.
READ_ONLY = {"GetLiveContext", "GetDateTime", "HassGetState", "HassGetWeather",
             "HassGetCurrentDate", "HassGetCurrentTime", "todo_get_items"}
# Garage, gate and door covers are the ones worth asking about; blinds
# share the domain, so device_class decides when it's given.
RISKY_CLASSES = {"garage", "gate", "door"}
# The ones that can sweep a whole area or floor of mixed devices. The
# rest (HassLightSet, HassClimateSetTemperature, media...) name their kind.
SWEEP_TOOLS = {"HassTurnOn", "HassTurnOff", "HassToggle", "HassSetPosition"}

_state = {"connected": False, "tools": [], "error": "", "risky": {}, "entities": 0,
          "read_at": 0.0, "url": ""}
_lock = threading.Lock()


def settings():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in config.plugin_settings(NAME).items() if k in DEFAULTS})
    return s


# ---------------------------------------------------------------------------
# Token and address
# ---------------------------------------------------------------------------
def _token():
    token = ""

    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, encoding="utf-8") as f:
            token = str(json.load(f).get("token") or "")   # a broken file raises: say so

    token = (token or os.environ.get("HASS_TOKEN", "")).strip()

    if token.lower().startswith(("your", "paste", "put", "eyjhbgcioi...")):
        return ""

    return token


def _local_only(url):
    """'' when the address is on this machine or your own network, else
    why not. Every address the name resolves to has to pass."""
    parts = urllib.parse.urlsplit(url)

    if parts.scheme not in ("http", "https") or not parts.hostname:
        return f"{url!r} isn't an http:// address"

    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 8123, proto=socket.IPPROTO_TCP)
    except OSError as e:
        return f"can't find {parts.hostname} on your network ({e})"

    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])

        if not (ip.is_loopback or ip.is_private or ip.is_link_local) or ip.is_multicast:
            where = parts.hostname if parts.hostname == str(ip) else f"{parts.hostname} ({ip})"
            return (f"{where} isn't on your own network - "
                    "this plugin only talks to a Home Assistant you run")

    return ""


def _base():
    return str(settings()["url"]).rstrip("/").removesuffix("/api/mcp")


# ---------------------------------------------------------------------------
# What's risky: read once from HA's own state list (same token, same box)
# ---------------------------------------------------------------------------
def _read_entities():
    request = urllib.request.Request(_base() + "/api/states",
                                     headers={"Authorization": f"Bearer {_token()}"})
    with urllib.request.urlopen(request, timeout=10) as r:
        states = json.load(r)

    domains = {str(d) for d in settings()["ask_domains"]}
    risky = {}

    for s in states:
        entity = str(s.get("entity_id", ""))
        domain, _, object_id = entity.partition(".")

        if domain not in domains:
            continue

        attrs = s.get("attributes") or {}

        if domain == "cover" and attrs.get("device_class") and attrs["device_class"] not in RISKY_CLASSES:
            continue   # a blind or a curtain

        label = f"{attrs.get('friendly_name') or object_id} ({entity})"

        for key in (entity, object_id, object_id.replace("_", " "), attrs.get("friendly_name")):
            if key:
                risky[str(key).strip().lower()] = label

    with _lock:
        _state.update(risky=risky, entities=len(states), read_at=time.time())

    return len(states), len(set(risky.values()))


def _check(tool, args):
    """'' = go ahead; anything else is the reason to ask first."""
    if tool in READ_ONLY or tool.startswith(("HassGet", "Get")):
        return ""

    s = settings()

    if s["ask_all"]:
        return "ask_all is on"

    if time.time() - _state["read_at"] > 600:
        try:
            _read_entities()
        except Exception as e:
            logbook.warn(NAME, "couldn't refresh the device list: %s", e)

    domains = {str(d) for d in s["ask_domains"]}
    asked = {str(d).lower() for d in _as_list(args.get("domain"))}
    classes = {str(c).lower() for c in _as_list(args.get("device_class"))}

    if asked & domains:
        if asked == {"cover"} and classes and not classes & RISKY_CLASSES:
            return ""
        return f"it's a {', '.join(sorted(asked & domains))}"

    if classes & RISKY_CLASSES:
        return f"it's a {', '.join(sorted(classes & RISKY_CLASSES))}"

    name = str(args.get("name") or "").strip().lower()
    risky = _state["risky"]

    if name:
        hit = risky.get(name) or next((v for k, v in risky.items() if name in k or k in name), "")
        return f"{hit} always asks" if hit else ""

    # No device named: an area or floor sweep. If it could reach a lock or
    # a garage door, ask.
    if risky and not asked and tool in SWEEP_TOOLS:
        return "it's a sweep with no device named, and locks or doors are exposed"

    return ""


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, (list, tuple)) else [value]


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def why_unavailable():
    import mcpclient

    if not mcpclient.available():
        return "pip install mcp"

    try:
        token = _token()
    except ValueError as e:
        return f"{CREDENTIALS_FILE} is broken: {e}"

    if not token:
        return f"no token - create one in Home Assistant and put it in {CREDENTIALS_FILE}"

    return ""


def available():
    return not why_unavailable()


def running():
    return _state["connected"]


def start(model):
    import mcpclient

    if _state["connected"]:
        return True, "home: already connected"

    problem = why_unavailable() or _local_only(_base())

    if problem:
        _state["error"] = problem
        return False, problem

    base = _base()

    try:
        count, risky = _read_entities()
    except urllib.error.HTTPError as e:
        why = "the token was refused" if e.code == 401 else f"HTTP {e.code}"
        _state["error"] = why
        return False, f"Home Assistant at {base}: {why}"
    except Exception as e:
        _state["error"] = str(e)[:200]
        return False, f"can't reach Home Assistant at {base}: {e}"

    spec = {"url": base + "/api/mcp", "headers": {"Authorization": f"Bearer {_token()}"},
            "skip_tools": list(settings()["skip_tools"] or []), "check": _check}
    ok, message, names = mcpclient.connect_server(SERVER, spec, timeout=20)

    if not ok:
        _state["error"] = message
        hint = " (is the Model Context Protocol Server integration added?)" if "404" in message else ""
        return False, f"Home Assistant's MCP server didn't answer: {message}{hint}"

    _state.update(connected=True, tools=names, error="", url=base)
    logbook.info(NAME, "connected to %s: %d tools, %d entities, %d ask first",
                 base, len(names), count, risky)

    return True, (f"home: {len(names)} tools from {base} - {risky} device(s) that always ask"
                  if names else f"home: connected to {base}, but it offered no tools - "
                  "check Settings -> Voice assistants -> Expose")


def stop():
    import mcpclient

    mcpclient.disconnect_server(SERVER)
    _state["connected"] = False

    return True, "home: disconnected"


def status():
    s = settings()
    lines = [f"home: {'connected' if _state['connected'] else 'off'} - {_base()}"]

    if _state["error"]:
        lines.append(f"  last error: {_state['error']}")

    if _state["connected"]:
        lines.append(f"  {len(_state['tools'])} tools, {_state['entities']} entities in Home Assistant")

    asks = sorted(set(_state["risky"].values()))
    lines.append("  every change asks (ask_all)" if s["ask_all"] else
                 f"  always ask: {', '.join(asks[:8])}{' ...' if len(asks) > 8 else ''}" if asks else
                 f"  always ask: anything in {', '.join(s['ask_domains'])} (none exposed)")
    lines.append("  what she can see: Home Assistant -> Settings -> Voice assistants -> Expose")

    return "\n".join(lines)


def command(text):
    word = text.strip().lower()

    if word == "refresh":
        try:
            count, risky = _read_entities()
        except Exception as e:
            return f"home: couldn't read the device list: {e}"
        return f"home: {count} entities, {risky} always ask"

    return "home: on | off | refresh"
