"""Vibe City - she plays mayor in the Vibe City window you have open.

    /vibecity on            connect to the running game (her mayor tools appear)
    /vibecity play          she builds on her own while you're quiet
    /vibecity goal <what>   what to aim for ("reach 2000 people", "a rail line")
    /vibecity pause         stop taking turns
    /vibecity off           disconnect
    /vibecity               status: the goal, what she's done lately

Vibe City has its own MCP server built in (Settings > AI Player). While
that's switched on, the game listens on http://127.0.0.1:47823/mcp and
everything she does happens in your window the way a player would do
it: the tool is picked from the menu, the cursor moves, the road is
dragged out, the camera pans to where she's working, and her `say`
lines show on screen. So you keep the game open and watch.

This plugin connects to that server (it doesn't start the game), and
while it's on the tools are hers in conversation: "how's the city
doing?", "build a road from 10,10 to 30,10", "put the tax at 9".

/vibecity play hands her the mayor's office: whenever nobody has spoken
for step_seconds she takes a turn - looks at the city, makes two to six
moves, narrates with `say` - and reports in one line. Like Minecraft and
Zork, turns are jobs: fresh context, nothing stored in your history,
only her city tools, and her last dozen one-liners as memory. Clicking
or pressing a key in the game takes over; a build that answers "the
player took over" pauses her.

Builds cost in-game money only, so nothing here asks for approval.

    "vibecity": {
        "enabled": false,
        "url": "http://127.0.0.1:47823/mcp",
        "step_seconds": 30,
        "max_steps": 60,
        "speak": false,
        "goal": "",
        "skip_tools": []               # e.g. ["screenshot"] for a model that can't see
    }

screenshot returns a picture of the game window. It reaches her the
same way look_at_screen does - attached to the next message - so a
vision model (an mmproj on llama-server, or a vision model in LM
Studio) sees her city. A text-only model is told it can't.
"""
import threading
import urllib.parse

import config
import logbook

NAME = "vibecity"
SUMMARY = "she plays mayor in your open Vibe City window"

SERVER = "vibecity"
DEFAULT_GOAL = ("grow the town: roads, homes, shops and industry, with power and water, "
                "without running out of money")

DEFAULTS = {"url": "http://127.0.0.1:47823/mcp", "step_seconds": 30, "max_steps": 60,
            "speak": False, "goal": "", "skip_tools": []}

_state = {"model": None, "tools": [], "goal": "", "notes": [], "steps": 0, "playing": False,
          "busy": False, "error": "", "briefed": False}
_stop = threading.Event()
_thread = None
_connected = False


def settings():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in config.plugin_settings(NAME).items() if k in DEFAULTS})
    return s


def _goal():
    return _state["goal"] or str(settings()["goal"] or "") or DEFAULT_GOAL


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def why_unavailable():
    import mcpclient

    if not mcpclient.available():
        return "pip install mcp"

    host = urllib.parse.urlsplit(str(settings()["url"])).hostname or ""

    if host not in ("127.0.0.1", "localhost", "::1"):
        return "the game's AI server only listens on this machine - url must be 127.0.0.1"

    return ""


def available():
    return not why_unavailable()


def running():
    return _connected


def start(model):
    global _thread, _connected
    import mcpclient

    if _connected:
        return True, "vibecity: already connected"

    problem = why_unavailable()

    if problem:
        return False, problem

    s = settings()
    spec = {"url": s["url"], "skip_tools": list(s["skip_tools"] or [])}
    ok, message, names = mcpclient.connect_server(SERVER, spec, timeout=15)

    if not ok:
        _state["error"] = message
        return False, ("couldn't reach Vibe City - is the game open with Settings > AI Player "
                       f"switched on? ({message})")

    _connected = True
    _state.update(model=model, tools=names, error="", briefed=False)
    _stop.clear()
    _thread = threading.Thread(target=_play, daemon=True, name="vibecity")
    _thread.start()

    return True, f"vibecity: {len(names)} tools from your game. /vibecity play hands her the mayor's office."


def stop():
    global _connected
    import mcpclient

    _stop.set()
    _state["playing"] = False
    mcpclient.disconnect_server(SERVER)
    _connected = False

    return True, "vibecity: disconnected (the city is yours again)"


def status():
    s = settings()
    head = f"vibecity: {'connected' if _connected else 'off'}"

    if _state["playing"]:
        head += f" - playing, turn {_state['steps']}/{s['max_steps']}"
    elif _connected:
        head += " - paused"

    lines = [head, f"  goal: {_goal()}"]

    if _state["error"]:
        lines.append(f"  last error: {_state['error']}")

    for note in _state["notes"][-5:]:
        lines.append(f"    · {note}")

    if _connected and not _state["playing"]:
        lines.append("  /vibecity play to let her run the city")

    return "\n".join(lines)


def command(text):
    word, _, rest = text.strip().partition(" ")
    word = word.lower()

    if word in ("play", "resume", "go"):
        return _set_playing(True)

    if word == "pause":
        return _set_playing(False)

    if word == "goal":
        return _set_goal(rest)

    return "vibecity: on | off | play | pause | goal <what>"


def _set_playing(on, goal=""):
    if on and not _connected:
        return "vibecity: connect first - open the game, Settings > AI Player on, then /vibecity on"

    if goal:
        _set_goal(goal)

    _state["playing"] = bool(on)

    if on:
        _state["steps"] = 0
        return f"vibecity: she's the mayor now - goal: {_goal()}. /vibecity pause stops."

    return "vibecity: paused."


def _set_goal(goal):
    goal = " ".join(str(goal or "").split())[:300]

    if not goal or goal.lower() in ("none", "clear", "default"):
        _state["goal"] = ""
        return f"vibecity: back to the default goal - {_goal()}"

    _state.update(goal=goal, notes=[], steps=0)
    logbook.info(NAME, "goal: %s", goal)

    return f"vibecity: goal set - {goal}"


# ---------------------------------------------------------------------------
# Playing on her own
# ---------------------------------------------------------------------------
STEP_PROMPT = (
    "(You're the mayor of a city in Vibe City, an isometric city builder, using your vibecity "
    "tools. The player is watching the game window, so narrate with the say tool.\n"
    "Your goal: {goal}\n"
    "{brief}"
    "What you've done so far, oldest first:\n{notes}\n\n"
    "Take your next turn: check get_city (and get_map around where you'll build), then make two "
    "to six moves towards the goal. Before building somewhere, look_at it with zoom about 1.2 so "
    "the player can see it. Keep funds above zero. If a build fails, read why and fix that, not "
    "the same build again. Now and then, take a screenshot to see how the town actually looks. If a "
    "call says the player took over, stop and end with PAUSED. Close any window you opened "
    "(set_tax, open_window...) with close_windows before ending your turn.\n"
    "End with ONE short line: what you built or changed and what you'll do next.)"
)

BRIEF = ("This is your first turn this session: call how_to_play first, then list_tools, so you "
         "know the coordinates, the prices and the house rules.\n")


def _step():
    import assistant

    s = settings()
    notes = "\n".join(f"- {n}" for n in _state["notes"][-12:]) or "- nothing yet"
    prompt = STEP_PROMPT.format(goal=_goal(), brief="" if _state["briefed"] else BRIEF, notes=notes)
    allowed = list(_state["tools"]) + ["play_vibe_city"]

    answer = assistant.respond_to_job(prompt, _state["model"], "vibecity", allowed,
                                      speak=bool(s["speak"])) or ""
    _state["briefed"] = True
    lines = [ln.strip() for ln in answer.strip().splitlines() if ln.strip()]
    line = lines[-1][:200] if lines else "(no report)"
    _state["notes"] = (_state["notes"] + [line])[-30:]
    _state["steps"] += 1

    if "PAUSED" in line.upper() or "took over" in answer.lower():
        _state["playing"] = False
        _say("Vibe City: you took over, so she's paused. /vibecity play hands it back.")
    elif _state["steps"] >= int(s["max_steps"]):
        _state["playing"] = False
        _say(f"Vibe City: {_state['steps']} turns - paused. /vibecity play to keep going.")


def _say(text):
    try:
        import ui

        ui.add_message("system", text)
    except Exception:
        pass


def _play():
    import reflect

    while not _stop.is_set():
        _stop.wait(2)
        s = settings()

        if (not _connected or not _state["playing"] or _state["busy"]
                or reflect.idle_seconds() < float(s["step_seconds"])):
            continue

        _state["busy"] = True

        try:
            _step()
        except Exception as e:
            _state["error"] = str(e)[:200]
            logbook.exception(NAME, "turn failed")
            _stop.wait(30)
        finally:
            _state["busy"] = False


# ---------------------------------------------------------------------------
# Her side: "go build me a town" starts her playing by herself.
# ---------------------------------------------------------------------------
def _register_tool():
    import tools

    def run(on=True, goal=""):
        return _set_playing(bool(on), goal)

    tools.register_external(
        "play_vibe_city",
        "Start or stop running the city in Vibe City on your own, a few moves at a time while "
        "the user is quiet. Use it when the user asks you to go play or build in Vibe City. "
        "goal sets what to aim for; on=false stops.",
        {"on": {"type": "boolean", "description": "true to play, false to stop."},
         "goal": {"type": "string", "description": "Optional: what to aim for, concrete."}},
        required=(), run=run, group="MCP: vibecity",
        available=running, why=lambda: "the vibecity plugin is off - /vibecity on",
    )


_register_tool()
