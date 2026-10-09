"""Zork - she plays Zork I, the 1980 text adventure.

    /zork on          load the game (her Zork tools appear)
    /zork play        she plays on her own while you're quiet
    /zork pause       stop taking turns (the game stays where it is)
    /zork watch       open a terminal window showing the game as she plays
    /zork off         put it away (saved, picked up next time)
    /zork             status: score, moves, what she's been up to

The game runs in games/zork/zork_server.py, a small MCP server around
dfrotz (the plain-text Frotz interpreter). While this plugin is on, the
game is hers in conversation too: "what's in the mailbox?", "try going
north", "how many points have you got?".

/zork play hands her the controls: whenever nobody has spoken for
step_seconds she takes a turn - a few commands - and says in one line
what happened. Like Minecraft, those turns are jobs: fresh context,
nothing stored in your history, only her Zork tools, and the last dozen
of her one-liners as her memory of the game so far. Talking to her
pauses play until you stop.

The game autosaves every few commands and when the plugin stops, so a
playthrough survives restarts. /zork play again carries on; the
zork_restart tool starts over.

Zork I is MIT-licensed (Microsoft, 2025); the story file ships in
games/zork/. dfrotz has to be installed:
    macOS:          brew install frotz
    Debian/Ubuntu:  sudo apt install frotz
    Fedora:         sudo dnf install frotz  (or build it: see zork_server.py)

    "zork": {
        "enabled": false,
        "step_seconds": 30,     # quiet needed before her next turn
        "max_steps": 80,        # turns per /zork play, then she pauses
        "speak": false,         # read each turn's line aloud
        "interpreter": "",      # path to dfrotz if it's somewhere odd
        "watch": false,         # open the watch window with /zork play
        "terminal": ""          # e.g. "kitty" or "gnome-terminal --"; "" = find one
    }

/zork watch opens a terminal running games/zork/watch.py, which follows
the game's transcript: her commands and the game's replies, the way a
player would see the screen. It looks for kitty, foot, alacritty,
wezterm, konsole, gnome-terminal or xterm (Terminal.app on a Mac);
"terminal" picks one. Closing it doesn't stop the game.
"""
import os
import shlex
import shutil
import subprocess
import sys
import threading

import config
import logbook

NAME = "zork"
SUMMARY = "she plays Zork I, the classic text adventure"

SERVER = "zork"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_SCRIPT = os.path.join(HERE, "games", "zork", "zork_server.py")
WATCH_SCRIPT = os.path.join(HERE, "games", "zork", "watch.py")
SAVES = os.path.join(HERE, "agent", "zork")      # gitignored, like her other state

DEFAULTS = {"step_seconds": 30, "max_steps": 80, "speak": False, "interpreter": "",
            "watch": False, "terminal": ""}

_state = {"model": None, "tools": [], "notes": [], "steps": 0, "playing": False,
          "busy": False, "error": ""}
_stop = threading.Event()
_thread = None
_connected = False


def settings():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in config.plugin_settings(NAME).items() if k in DEFAULTS})
    return s


def _dfrotz():
    for candidate in (settings()["interpreter"], shutil.which("dfrotz"), "/usr/games/dfrotz",
                      "/opt/homebrew/bin/dfrotz", "/usr/local/bin/dfrotz"):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def why_unavailable():
    import mcpclient

    if not mcpclient.available():
        return "pip install mcp"

    if not _dfrotz():
        return ("needs dfrotz - macOS: brew install frotz; Debian/Ubuntu: sudo apt install frotz; "
                "Fedora: sudo dnf install frotz")

    if not os.path.exists(SERVER_SCRIPT):
        return f"missing {SERVER_SCRIPT}"

    return ""


def available():
    return not why_unavailable()


def running():
    return _connected


def start(model):
    global _thread, _connected
    import mcpclient

    if _connected:
        return True, "zork: already loaded"

    problem = why_unavailable()

    if problem:
        return False, problem

    spec = {"command": sys.executable,
            "args": [SERVER_SCRIPT, "--saves", SAVES, "--interpreter", _dfrotz()]}
    ok, message, names = mcpclient.connect_server(SERVER, spec, timeout=30)

    if not ok:
        _state["error"] = message
        return False, f"couldn't start Zork: {message}"

    _connected = True
    _state.update(model=model, tools=names, error="")
    _stop.clear()
    _thread = threading.Thread(target=_play, daemon=True, name="zork")
    _thread.start()

    resumed = " (a saved game is waiting)" if os.path.exists(os.path.join(SAVES, "autosave.qzl")) else ""

    return True, f"zork: {len(names)} tools{resumed}. /zork play lets her play on her own."


def stop():
    global _connected
    import mcpclient

    _stop.set()
    _state["playing"] = False
    mcpclient.disconnect_server(SERVER)      # the server autosaves on its way out
    _connected = False

    return True, "zork: put away (saved for next time)"


def status():
    s = settings()
    lines = [f"zork: {'loaded' if _connected else 'off'}"
             + (f" - playing, turn {_state['steps']}/{s['max_steps']}" if _state["playing"] else
                " - paused" if _connected else "")]

    if _state["error"]:
        lines.append(f"  last error: {_state['error']}")

    for note in _state["notes"][-5:]:
        lines.append(f"    · {note}")

    if _connected and not _state["playing"]:
        lines.append("  /zork play to let her play on her own")

    return "\n".join(lines)


def command(text):
    word = text.strip().lower()

    if word in ("play", "resume", "go"):
        return _set_playing(True)

    if word in ("pause", "stop playing"):
        return _set_playing(False)

    if word == "watch":
        return _open_watch()

    return "zork: on | off | play | pause | watch"


# ---------------------------------------------------------------------------
# A window to watch her play in
# ---------------------------------------------------------------------------
TITLE = "Luna plays Zork"


def _terminal_command(inner):
    """argv that opens a terminal window running `inner`, or None."""
    chosen = str(settings()["terminal"] or "").strip()

    if chosen:
        return shlex.split(chosen) + inner

    if sys.platform == "darwin":
        kitty = shutil.which("kitty") or "/Applications/kitty.app/Contents/MacOS/kitty"
        if os.path.exists(kitty):
            return [kitty, "--title", TITLE] + inner
        script = " ".join(shlex.quote(a) for a in inner)
        return ["osascript", "-e", f'tell application "Terminal" to do script "{script}"',
                "-e", 'tell application "Terminal" to activate']

    styles = [("kitty", ["--title", TITLE]), ("foot", ["--title", TITLE]),
              ("alacritty", ["--title", TITLE, "-e"]), ("wezterm", ["start", "--"]),
              ("konsole", ["-e"]), ("gnome-terminal", ["--title", TITLE, "--"]),
              ("xterm", ["-T", TITLE, "-e"])]

    for name, flags in styles:
        path = shutil.which(name)
        if path:
            return [path] + flags + inner

    return None


def _open_watch():
    inner = [sys.executable, WATCH_SCRIPT, SAVES]
    argv = _terminal_command(inner)

    if argv is None:
        return ("zork: no terminal found to open - run it yourself:\n  "
                + " ".join(shlex.quote(a) for a in inner)
                + '\n  (or set "terminal" under plugins.zork in config.json)')

    try:
        os.makedirs(SAVES, exist_ok=True)
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        return f"zork: couldn't open a terminal ({e})"

    return f"zork: opened a window to watch in ({os.path.basename(argv[0])})"


def _set_playing(on):
    if on and not _connected:
        return "zork: load it first - /zork on"

    _state["playing"] = bool(on)

    if on:
        _state["steps"] = 0
        extra = ""
        if settings()["watch"]:
            extra = "\n" + _open_watch()
        return ("zork: she's playing - she takes a turn whenever you're quiet. "
                "/zork pause stops, /zork watch shows the game." + extra)

    return "zork: paused."


# ---------------------------------------------------------------------------
# Playing on her own
# ---------------------------------------------------------------------------
STEP_PROMPT = (
    "(You're playing Zork I, the classic text adventure, with your Zork tools. The goal is "
    "treasure and points: 350 is a perfect score. Explore, pick up anything useful, read what "
    "you find, and keep a light source once you go underground - the dark has a grue in it.\n"
    "What you've done so far, oldest first:\n{notes}\n\n"
    "Take your next turn: two to five commands with zork_command, short verb-noun ones like "
    "'north', 'open mailbox', 'take lamp'. If you've lost track, start with zork_status. "
    "Save with zork_save before anything dangerous. If you die, zork_restore goes back. If a "
    "command fails twice, try something different.\n"
    "End with ONE short line: where you are, what just happened, what you'll try next.)"
)


def _step():
    import assistant

    s = settings()
    notes = "\n".join(f"- {n}" for n in _state["notes"][-12:]) or "- nothing yet: a new game"
    allowed = list(_state["tools"]) + ["play_zork"]

    answer = assistant.respond_to_job(STEP_PROMPT.format(notes=notes), _state["model"], "zork",
                                      allowed, speak=bool(s["speak"])) or ""
    lines = [ln.strip() for ln in answer.strip().splitlines() if ln.strip()]
    line = lines[-1][:200] if lines else "(no report)"
    _state["notes"] = (_state["notes"] + [line])[-30:]
    _state["steps"] += 1

    if _state["steps"] >= int(s["max_steps"]):
        _state["playing"] = False
        _say(f"Zork: {_state['steps']} turns - paused. /zork play to keep going.")


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
# Her side: "go play some Zork" starts her playing by herself.
# ---------------------------------------------------------------------------
def _register_tool():
    import tools

    def run(on=True):
        return _set_playing(bool(on))

    tools.register_external(
        "play_zork",
        "Start or stop playing Zork on your own, a few moves at a time while the user is "
        "quiet. Use it when the user asks you to go play Zork. on=false stops.",
        {"on": {"type": "boolean", "description": "true to play, false to stop."}},
        required=(), run=run, group="MCP: zork",
        available=running, why=lambda: "the zork plugin is off - /zork on",
    )


_register_tool()
