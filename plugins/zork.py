"""Zork - she plays Zork I, the 1980 text adventure.

    /zork on          load the game (her Zork tools appear)
    /zork play        she plays on her own while you're quiet
    /zork pause       stop taking turns (the game stays where it is)
    /zork watch       open a terminal window showing the game as she plays
    /zork new         start over from the beginning (the old game is kept as old-<date>)
    /zork off         put it away (saved, picked up next time)
    /zork             status: score, moves, what she's been up to

The game runs in games/zork/zork_server.py, a small MCP server around
dfrotz (the plain-text Frotz interpreter). While this plugin is on, the
game is hers in conversation too: "what's in the mailbox?", "try going
north", "how many points have you got?".

/zork play hands her the controls: whenever nobody has spoken for
step_seconds she takes a turn - one move: she reads the screen, types one
command, and says in a line what she did and why - then waits to see
what it did. Like Minecraft, those turns are jobs: fresh context,
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
        "step_seconds": 8,      # quiet needed before her next move
        "max_steps": 200,       # moves per /zork play, then she pauses
        "speak": true,          # narrate each turn out loud
        "web": true,            # she may look things up (web_search, research)
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
import re
import shutil
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

DEFAULTS = {"step_seconds": 8, "max_steps": 200, "speak": True, "web": True, "interpreter": "",
            "watch": False, "terminal": ""}

# When "web" is on: stuck on a puzzle or a recipe, she can look it up.
# If that means she reads a walkthrough and wins, she wins.
WEB_TOOLS = ["web_search", "research"]

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

    if not _state["busy"]:
        from plugins import _playlog

        _playlog.finished(NAME)   # mid-turn, the turn loop does it once the turn is recorded
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

    if word in ("new", "restart", "new game"):
        return _new_game()

    return "zork: on | off | play | pause | watch | new"


def _new_game():
    """Start Zork over from the beginning, and forget the old game's notes
    so she doesn't play the new one from memories of the last. The old
    game is kept first, in a save named old-<date>-<time>."""
    import tools
    from datetime import datetime

    name = next((t for t in _state["tools"] if t.endswith("zork_restart")), None)
    saver = next((t for t in _state["tools"] if t.endswith("zork_save")), None)
    if not name:
        return "zork: load the game first - /zork on"

    kept = ""
    if saver:
        slot = f"old-{datetime.now():%Y%m%d-%H%M}"
        if not tools.call(saver, {"slot": slot}).startswith("Error"):
            kept = f" The old game is saved as {slot} - ask her to restore {slot} to go back to it."

    reply = tools.call(name, {})
    if reply.startswith("Error"):
        return f"zork: couldn't restart ({reply})"

    _state.update(notes=[], steps=0)
    try:
        import projects

        projects.new_game(NAME, GOAL)     # fresh notes; the old ones are retired, not lost
    except Exception:
        pass
    try:
        with open(os.path.join(SAVES, "transcript.txt"), "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 60 + "\n[a new game]\n")
    except OSError:
        pass
    return "zork: new game - back at West of House. /zork play to start." + kept


# ---------------------------------------------------------------------------
# A window to watch her play in
# ---------------------------------------------------------------------------
TITLE = "Luna plays Zork"


def _open_watch():
    from plugins import _terminal

    os.makedirs(SAVES, exist_ok=True)

    return _terminal.open_window([sys.executable, WATCH_SCRIPT, SAVES], TITLE,
                                 settings()["terminal"], NAME)


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

    if not _state["busy"]:
        from plugins import _playlog

        _playlog.finished(NAME)   # mid-turn, the turn loop does it once the turn is recorded

    return "zork: paused."


# ---------------------------------------------------------------------------
# Playing on her own
# ---------------------------------------------------------------------------
GOAL = "350 points: every treasure in the trophy case"


STEP_PROMPT = (
    "(You're playing Zork I, the classic text adventure, with your Zork tools. The goal is "
    "treasure and points: 350 is a perfect score. Explore, pick up anything useful, read what "
    "you find, and keep a light source once you go underground - the dark has a grue in it.\n"
    "Your notes on this playthrough (yours - kept between sessions):\n{project}\n\n"
    "Your last moves, oldest first:\n{notes}\n\n"
    "The game screen right now (your last command and what the game said):\n"
    "-----\n{screen}\n-----\n\n"
    "Read the screen, think about what it tells you, then make ONE move: a single zork_command, "
    "short and verb-noun like 'north', 'open mailbox', 'take lamp'. Then stop - you'll see what "
    "it did next turn. Don't repeat a move that just failed or changed nothing; try something "
    "new instead (another direction, another object). You only need zork_status if the screen "
    "above is empty. Save with zork_save before anything dangerous; zork_restore if you die.\n"
    "When you learn something worth remembering - a room and its exits, a puzzle, an item and "
    "what it's for, what killed you - write it down with game_note, and update your plan. "
    "Read your notes before moving; don't repeat what they say failed.\n"
    "Then talk to the player watching, in your own voice, 2 to 4 sentences: what you see, what "
    "you make of it, why you chose this move, how you feel about it (grues are scary; treasure "
    "is exciting). Make your last sentence a plain summary: what you did and what you'll try "
    "next.)"
)


_STATUS = re.compile(r"^\s*(\S.*?)\s{2,}Score:\s*(-?\d+)\s+Moves:\s*(\d+)\s*$")


def _pretty_turn(turn, said, width=78):
    """This move laid out like the watch window, as plain text for the
    playlog: her command, a status bar, the game's reply wrapped, then
    what she said about it."""
    import textwrap
    from datetime import datetime

    from plugins import _playlog

    screen = _screen(lines=40)
    starts = [i for i, ln in enumerate(screen.splitlines()) if ln.startswith("> ")]
    lines = screen.splitlines()[starts[-1]:] if starts else screen.splitlines()

    out = [f"=== move {turn}  {datetime.now():%H:%M:%S} " + "=" * max(3, width - 22)]
    blank = False
    for line in lines:
        status = _STATUS.match(line)
        if status:
            room, score, moves = status.groups()
            label = f" {room}  ·  score {score}  ·  move {moves} "
            out.append("--" + label + "-" * max(2, width - len(label) - 2))
        elif line.startswith(("[saved", "[restored")):
            continue
        elif not line.strip():
            if not blank:
                out.append("")
            blank = True
            continue
        else:
            indent = line[:len(line) - len(line.lstrip())]
            out += textwrap.wrap(line.strip(), width, initial_indent=indent, subsequent_indent=indent) or [""]
        blank = False

    if said:
        out += ["", _playlog.said_block(said, width)]
    return "\n".join(out)



def _last_sentence(answer, limit=200):
    """Her turn's last sentence - the what-I-did-and-what's-next that goes
    into her one-liner notes. The rest is commentary for the player."""
    text = " ".join((answer or "").split())
    parts = [p for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    return (parts[-1] if parts else "(no report)")[:limit]

def _screen(lines=30):
    """The tail of the game's transcript, without her own comments - what
    a player would be looking at before typing the next command."""
    path = os.path.join(SAVES, "transcript.txt")
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 12000))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return "(nothing yet - a new game)"

    keep, skipping = [], False
    for line in text.splitlines():
        if line.startswith("[") and not line.startswith(("[saved", "[restored")):
            skipping = True          # her comment: runs to the next blank line
            continue
        if skipping and line.strip():
            continue
        skipping = False
        # dfrotz pads its status line to 200 columns; squeeze it
        keep.append(re.sub(r"\s{3,}", "   ", line.rstrip()))

    # from the start of the last two commands, at most `lines` lines
    starts = [i for i, ln in enumerate(keep) if ln.startswith("> ")]
    tail = keep[starts[-2]:] if len(starts) >= 2 else keep
    tail = "\n".join(tail[-lines:]).strip()
    return re.sub(r"\n{3,}", "\n\n", tail) or "(nothing yet - a new game)"


# One move per turn, enforced rather than asked for: the model was told
# "ONE command" and still sent three or four. During a play turn the
# first zork_command goes through; any more in the same turn are turned
# back, and she sees the result of the one she made next turn. In
# conversation (not a play turn) there's no limit.
_turn = {"active": False, "moves": 0}

ONE_MOVE = ("You've already made your move this turn - that command wasn't sent. Don't send "
            "more: say what you did and why, write a game_note if you learned something, and "
            "stop. You'll see what your move did next turn.")


def _one_move_per_turn():
    import tools

    name = next((t for t in _state["tools"] if t.endswith("zork_command")), None)
    entry = tools._REGISTRY.get(name) if name else None

    if not entry or getattr(entry["run"], "_one_move", False):
        return

    inner = entry["run"]

    def run(**kwargs):
        if _turn["active"]:
            if _turn["moves"] >= 1:
                return ONE_MOVE
            _turn["moves"] += 1
        return inner(**kwargs)

    run._one_move = True
    entry["run"] = run


def _step():
    import assistant

    s = settings()
    notes = "\n".join(f"- {n}" for n in _state["notes"][-20:]) or "- nothing yet: a new game"
    allowed = list(_state["tools"]) + ["play_zork", "game_note"] + (WEB_TOOLS if s["web"] else [])

    import projects

    pid = projects.game_project(NAME, GOAL)

    _one_move_per_turn()
    _turn.update(active=True, moves=0)
    exchanges = []

    try:
        # A move, a note, maybe a status check - more rounds than that is
        # her trying to play several moves blind.
        answer = assistant.respond_to_job(
            STEP_PROMPT.format(notes=notes, screen=_screen(), project=projects.game_block(pid)),
            _state["model"], "zork", allowed, speak=bool(s["speak"]), project_id=pid,
            max_rounds=4 if s["web"] else 3, exchanges=exchanges) or ""
    finally:
        _turn["active"] = False
    lines = [ln.strip() for ln in answer.strip().splitlines() if ln.strip()]
    line = _last_sentence(answer) if lines else "(no report)"
    _state["notes"] = (_state["notes"] + [line])[-30:]
    _state["steps"] += 1

    from plugins import _playlog

    _playlog.write(NAME, _state["steps"], answer, block=_pretty_turn(_state["steps"], answer),
                   also=[os.path.join(SAVES, "transcript.txt")])
    _playlog.remember(NAME, "Zork I", answer, exchanges)

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

            if _stop.is_set() or not _state["playing"]:
                from plugins import _playlog

                _playlog.finished(NAME)   # she stopped: the session is over


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
