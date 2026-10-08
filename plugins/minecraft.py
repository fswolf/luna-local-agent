"""Minecraft - she joins your world as a player and works towards a goal.

    /minecraft on                 join (connects the bot, adds her Minecraft tools)
    /minecraft goal <what>        give her something to do - or just ask her
    /minecraft pause | resume     stop taking steps / carry on
    /minecraft off                leave the world
    /minecraft                    status: where she's at with the goal

How it works: a Minecraft MCP server (yuniko-software/minecraft-mcp-server,
built on Mineflayer) logs a bot into the world and gives her tools to move,
look, dig, place, craft and chat. While this plugin is on, those tools are
hers in conversation too ("come here", "what have you got on you?").

With a goal set, she plays on her own: whenever nobody has spoken for a
little while she takes a step - looks at where she is and what she has,
does one to three things towards the goal, and says in one line what she
did. Those steps are job turns: fresh context, nothing stored in your
history, only her Minecraft tools. What she remembers between steps is the
last few of those lines. Talking to her pauses play until you stop; she
picks up again after step_seconds of quiet.

It's a language model taking turns, not a reflex player: seconds per
action, good at "gather wood and make a crafting table", hopeless at
fighting. That's the honest shape of it.

Setup:
    Node.js 20+, then once:  npm install -g github:yuniko-software/minecraft-mcp-server
    (without that it falls back to npx, which is slow the first time)
    Minecraft Java, a world opened to LAN or a server with online-mode=false.
    The LAN port is shown in chat when you open it - put it in "port".

    "minecraft": {
        "enabled": false,
        "host": "localhost",
        "port": 25565,
        "username": "Luna",
        "step_seconds": 20,     # quiet needed before she takes the next step
        "max_steps": 60,        # per goal, then she pauses and asks
        "speak": false          # say each step out loud
    }
"""
import json
import os
import shutil
import threading
import time

import config
import logbook

NAME = "minecraft"
SUMMARY = "she joins your world and plays towards a goal"

SERVER = "minecraft"
PACKAGE = "github:yuniko-software/minecraft-mcp-server"

# The tools she gets. The server has 22; every schema rides along in every
# prompt, and a 9B model picks better from a dozen. These cover moving,
# gathering, building, crafting and talking.
CORE_TOOLS = ["get-position", "move-to-position", "look-at", "find-blocks", "dig-block",
              "place-block", "list-inventory", "equip-item", "craft-item", "can-craft",
              "find-entity", "send-chat", "read-chat",
              # for when something's unclear: what is that block, what does
              # this recipe need, creative or survival?
              "get-block-info", "get-recipe", "detect-gamemode"]

DEFAULTS = {"host": "localhost", "port": 25565, "username": "Luna", "step_seconds": 20,
            "max_steps": 60, "speak": False, "mc_tools": CORE_TOOLS, "command": ""}

# Places she pinned with remember_minecraft_spot - kept across restarts,
# per world, because "the base" is the same place tomorrow.
SPOTS_FILE = os.path.join(config.BASE_DIR, "agent", "minecraft.json")

_state = {"model": None, "tools": [], "goal": "", "notes": [], "steps": 0,
          "paused": False, "busy": False, "error": "", "last": ""}
_stop = threading.Event()
_thread = None
_connected = False


def settings():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in config.plugin_settings(NAME).items() if k in DEFAULTS})
    return s


def _command_line(s):
    """The MCP server to start: the installed one, else npx."""
    args = ["--host", str(s["host"]), "--port", str(s["port"]), "--username", str(s["username"])]

    if s.get("command"):
        return str(s["command"]), args

    if shutil.which("minecraft-mcp-server"):
        return "minecraft-mcp-server", args

    return "npx", ["-y", PACKAGE] + args


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def available():
    return not why_unavailable()


def why_unavailable():
    import mcpclient

    if not mcpclient.available():
        return "pip install mcp"

    if not (shutil.which("minecraft-mcp-server") or shutil.which("npx")):
        return "needs Node.js 20+ (npm install -g " + PACKAGE + ")"

    return ""


def running():
    return _connected


def start(model):
    global _thread, _connected
    import mcpclient

    if _connected:
        return True, "minecraft: already in the world"

    problem = why_unavailable()

    if problem:
        return False, problem

    s = settings()
    command, args = _command_line(s)
    spec = {"command": command, "args": args, "tools": list(s["mc_tools"] or CORE_TOOLS)}
    # npx fetches and builds the package the first time, which takes a while.
    ok, message, names = mcpclient.connect_server(SERVER, spec, timeout=180 if command == "npx" else 45)

    if not ok:
        _state["error"] = message
        return False, f"couldn't start the Minecraft bot: {message}"

    _connected = True
    _state.update(model=model, tools=names, error="")
    _stop.clear()
    _thread = threading.Thread(target=_play, daemon=True, name="minecraft")
    _thread.start()

    goal = f" Goal: {_state['goal']}" if _state["goal"] else " No goal yet - ask her, or /minecraft goal <what>."

    return True, (f"minecraft: {len(names)} tools, joining {s['host']}:{s['port']} as "
                  f"{s['username']} on her first move.{goal}")


def stop():
    global _connected
    import mcpclient

    _stop.set()
    mcpclient.disconnect_server(SERVER)
    _connected = False

    return True, "minecraft: left the world (the goal is kept for next time)"


def status():
    s = settings()
    lines = [f"minecraft: {'in the world' if _connected else 'off'} - "
             f"{s['host']}:{s['port']} as {s['username']}"]

    if _state["error"]:
        lines.append(f"  last error: {_state['error']}")

    if _state["goal"]:
        flag = " (paused)" if _state["paused"] else ""
        lines.append(f"  goal{flag}: {_state['goal']}  - step {_state['steps']}/{s['max_steps']}")
    else:
        lines.append("  no goal - /minecraft goal <what>, or just ask her")

    for name, spot in _spots().items():
        lines.append(f"  pinned {name}: {spot['x']}, {spot['y']}, {spot['z']}"
                     + (f" - {spot['note']}" if spot.get("note") else ""))

    for note in _state["notes"][-4:]:
        lines.append(f"    · {note}")

    return "\n".join(lines)


def command(text):
    word, _, rest = text.partition(" ")
    word = word.lower()

    if word == "goal":
        return _set_goal(rest)

    if word == "pause":
        _state["paused"] = True
        return "minecraft: paused - she'll stay put. /minecraft resume carries on."

    if word == "resume":
        _state["paused"] = False
        _state["steps"] = 0
        return "minecraft: carrying on."

    return "minecraft: on | off | goal <what> | pause | resume"


def _set_goal(goal):
    goal = " ".join(str(goal or "").split())[:300]

    if not goal or goal.lower() in ("none", "stop", "clear"):
        _state.update(goal="", notes=[], steps=0)
        return "minecraft: goal cleared - she'll just hang around."

    _state.update(goal=goal, notes=[], steps=0, paused=False)
    logbook.info(NAME, "goal: %s", goal)

    return f"minecraft: goal set - {goal}"


# ---------------------------------------------------------------------------
# Playing on her own
# ---------------------------------------------------------------------------
STEP_PROMPT = (
    "(You're playing Minecraft as {username}, in a world the user opened for you. "
    "Your goal: {goal}\n"
    "Places you pinned: {spots}\n"
    "What you've done so far, oldest first:\n{notes}\n\n"
    "Take the next step. Check your position or inventory if you need to, find what you "
    "need, then do one to three actions towards the goal with your Minecraft tools. If a "
    "player may have said something, read the game chat and answer there. If something "
    "fails, check before retrying: look at the block's info, or get the recipe. If the "
    "goal is unclear (which way, what size, what material), ask in the game chat "
    "instead of guessing, and look for the answer next step. Pin places you'll need "
    "again (base, chest, the build site) with remember_minecraft_spot. If something "
    "fails twice, try a different way. End with ONE short line: what you just did and "
    "what's next. If the goal is complete, start that line with DONE. If you're truly "
    "stuck, start it with STUCK and say why.)"
)


def _step():
    import assistant

    s = settings()
    notes = "\n".join(f"- {n}" for n in _state["notes"][-6:]) or "- nothing yet, you just arrived"
    spots = "; ".join(f"{k} at {v['x']}, {v['y']}, {v['z']}" + (f" ({v['note']})" if v.get("note") else "")
                      for k, v in _spots().items()) or "none yet"
    prompt = STEP_PROMPT.format(username=s["username"], goal=_state["goal"], notes=notes, spots=spots)
    allowed = list(_state["tools"]) + ["set_minecraft_goal", "remember_minecraft_spot"]

    answer = assistant.respond_to_job(prompt, _state["model"], "minecraft", allowed,
                                      speak=bool(s["speak"])) or ""
    lines = [ln.strip() for ln in answer.strip().splitlines() if ln.strip()]
    line = lines[-1][:200] if lines else "(no report)"
    _state["notes"] = (_state["notes"] + [line])[-12:]
    _state["steps"] += 1
    _state["last"] = line

    if line.upper().startswith("DONE"):
        logbook.info(NAME, "goal done: %s", _state["goal"])
        _say(f"Minecraft: done - {_state['goal']}")
        _state.update(goal="", steps=0)
    elif line.upper().startswith("STUCK"):
        _state["paused"] = True
        _say(f"Minecraft: she's stuck and paused - {line}. /minecraft resume to let her try again.")
    elif _state["steps"] >= int(s["max_steps"]):
        _state["paused"] = True
        _say(f"Minecraft: {_state['steps']} steps on this goal - paused. /minecraft resume to keep going.")


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

        if (not _connected or not _state["goal"] or _state["paused"] or _state["busy"]
                or reflect.idle_seconds() < float(s["step_seconds"])):
            continue

        _state["busy"] = True

        try:
            _step()
        except Exception as e:
            _state["error"] = str(e)[:200]
            logbook.exception(NAME, "step failed")
            _stop.wait(30)  # don't spin on a broken connection
        finally:
            _state["busy"] = False


# ---------------------------------------------------------------------------
# Her side: "go build a house in minecraft" sets the goal by itself.
# ---------------------------------------------------------------------------
def _register_goal_tool():
    import tools

    def run(goal):
        return _set_goal(goal) + (" She'll start working on it when the conversation goes quiet."
                                  if _state["goal"] else "")

    tools.register_external(
        "set_minecraft_goal",
        "Give yourself a goal to work on in Minecraft on your own, step by step, while "
        "the user is quiet - 'gather 10 logs', 'build a small hut by the river'. Use it "
        "when the user asks you to do something in Minecraft that takes more than a "
        "couple of actions. 'clear' stops.",
        {"goal": {"type": "string", "description": "The goal, concrete and checkable."}},
        required=("goal",), run=run, group="MCP: minecraft",
        available=running, why=lambda: "the minecraft plugin is off - /minecraft on",
    )


# ---------------------------------------------------------------------------
# Pinned spots: a few named coordinates that outlive her six-line notes.
# ---------------------------------------------------------------------------
def _world():
    s = settings()
    return f"{s['host']}:{s['port']}"


def _load():
    try:
        with open(SPOTS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _spots():
    return dict(_load().get(_world(), {}))


def _save_spots(spots):
    data = _load()
    data[_world()] = spots
    os.makedirs(os.path.dirname(SPOTS_FILE), exist_ok=True)
    tmp = SPOTS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, SPOTS_FILE)


def _register_spot_tool():
    import tools

    def run(name, x=None, y=None, z=None, note=""):
        name = " ".join(str(name or "").split())[:40].lower()
        if not name:
            return "Needs a name, like 'base' or 'iron cave'."
        spots = _spots()
        if x is None and y is None and z is None:
            if spots.pop(name, None) is None:
                return f"No spot called {name}."
            _save_spots(spots)
            return f"Forgot {name}."
        try:
            spot = {"x": round(float(x)), "y": round(float(y)), "z": round(float(z))}
        except (TypeError, ValueError):
            return "x, y and z need to be numbers - get-position gives yours."
        if note:
            spot["note"] = " ".join(str(note).split())[:80]
        if name not in spots and len(spots) >= 12:
            return "You already have 12 spots pinned - forget one first (name only, no coordinates)."
        spots[name] = spot
        _save_spots(spots)
        return f"Pinned {name} at {spot['x']}, {spot['y']}, {spot['z']}."

    tools.register_external(
        "remember_minecraft_spot",
        "Pin a place in the Minecraft world by name so you can find it again - your base, "
        "a chest, the build site, a cave with iron. Pinned spots are shown to you every step "
        "and kept across sessions. Give just the name with no coordinates to forget one.",
        {"name": {"type": "string", "description": "Short name, e.g. 'base'."},
         "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
         "note": {"type": "string", "description": "Optional: what's there."}},
        required=("name",), run=run, group="MCP: minecraft",
        available=running, why=lambda: "the minecraft plugin is off - /minecraft on",
    )


_register_goal_tool()
_register_spot_tool()
