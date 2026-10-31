"""Game Boy - she plays Game Boy games, through the PyBoy emulator.

    /gameboy games       the games in your ROM folder, numbered
    /gameboy game red    pick one by name or number (or a path; remembered)
    /gameboy on          switch the Game Boy on (her Game Boy tools appear)
    /gameboy play        she plays on her own while you're quiet
    /gameboy pause       stop taking turns (the game stays where it is)
    /gameboy watch       the screen and what she says, in your browser
    /gameboy off         put it away (saved, picked up next time)
    /gameboy             status

The emulator runs in games/gameboy/gb_server.py, an MCP server around PyBoy.
While this plugin is on the game is hers in conversation too: "press start",
"what's your team?", "go into the house".

She sees the screen as a picture whenever her model can see (her vision
adapter), so she can look at the people and monsters and talk about them. A
game with a reader in games/gameboy/readers/ also comes to her as text from
the game's memory: where she is, her team or stats, and the words on screen,
dialogue and menus included - the part she plays by, reliable even when the
picture is small. Pokemon Red and Blue have one; readers for other games drop
into that folder. Without a reader, the picture is all she has, so a game
like that needs a model that can see.

Slower games suit her best: she takes a turn, then the game waits. With
"window" on, the Game Boy's own screen opens and runs in real time instead,
to watch (and with "sound", to hear) as she plays.

The ROM is yours: Luna never ships or fetches one. A battery save dumped from
your own cartridge goes beside the ROM as <rom name>.ram, and she carries on
your game. pip install pyboy (and mcp).

    "gameboy": {
        "enabled": false,
        "rom": "",              # the game: a .gb or .gbc file
        "roms": "",             # your ROM folder; "" = the folder of the last game picked by path
        "saves": "",            # where her saves go; "" = ~/.local/share/ai-voice/gameboy
        "step_seconds": 6,      # quiet needed before her next turn
        "max_steps": 300,       # turns per /gameboy play, then she pauses
        "speak": true,          # narrate each turn out loud
        "web": true,            # she may look things up (web_search, research)
        "pictures": "auto",     # auto: whenever her model can see; never
        "guide": true,          # each turn, what agent/knowledge/<game>/ says about where she is
        "window": false,        # the Game Boy screen in a window, in real time
        "sound": false,         # with the window: the game's sound
        "turn_seconds": 150     # a turn that runs longer is cut short (0 = no limit)
    }
"""
import json
import os
import re
import sys

import config

from plugins import _game

NAME = "gameboy"
SUMMARY = "she plays Game Boy games (Pokemon Red and Blue read as text)"

SERVER = "gameboy"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_SCRIPT = os.path.join(HERE, "games", "gameboy", "gb_server.py")
READERS = os.path.join(HERE, "games", "gameboy")
WATCH_PAGE = os.path.join(HERE, "games", "gameboy", "watch.html")

DEFAULTS = {"rom": "", "roms": "", "saves": "", "step_seconds": 6, "max_steps": 300, "speak": True, "web": True,
            "pictures": "auto", "guide": True, "window": False, "sound": False, "turn_seconds": 150}

_state = {"model": None, "tools": [], "notes": [], "steps": 0, "playing": False, "busy": False,
          "error": "", "title": "", "said": ""}
_connected = False


def settings():
    return _game.settings(NAME, DEFAULTS)


def _rom():
    path = os.path.expanduser(str(settings()["rom"] or "").strip())
    return os.path.abspath(path) if path and os.path.isfile(path) else ""


def _roms_folder():
    folder = os.path.expanduser(str(settings()["roms"] or "").strip())
    if not folder:
        rom = os.path.expanduser(str(settings()["rom"] or "").strip())
        folder = os.path.dirname(rom) if rom else ""
    return folder if folder and os.path.isdir(folder) else ""


def _games():
    """The .gb and .gbc files in the ROM folder (and one level down), sorted."""
    folder = _roms_folder()
    if not folder:
        return []
    out = []
    for root, dirs, files in os.walk(folder):
        out += [os.path.join(root, f) for f in files if f.lower().endswith((".gb", ".gbc"))]
        if root != folder:
            dirs[:] = []
    return sorted(out, key=lambda p: os.path.basename(p).lower())


def _squash(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _match(name):
    """A game from the ROM folder by number ("2") or by part of its name
    ("red", "final fantasy"): (path, "") or ("", why not)."""
    games = _games()
    if not games:
        return "", "no ROM folder yet: pick a game by its path once (/gameboy game ~/roms/red.gb), or set plugins.gameboy.roms"
    if name.isdigit():
        n = int(name)
        return (games[n - 1], "") if 1 <= n <= len(games) else ("", f"there's no game {n} (/gameboy games)")
    want = _squash(name)
    hits = [g for g in games if want and want in _squash(os.path.splitext(os.path.basename(g))[0])]
    if len(hits) == 1:
        return hits[0], ""
    if not hits:
        return "", f"no game matching {name!r} in {_roms_folder()} (/gameboy games)"
    return "", f"{name!r} could be: " + ", ".join(os.path.basename(g) for g in hits[:6])


def _list_games():
    games, current = _games(), _rom()
    if not games:
        return "gameboy: " + _match("x")[1] if not _roms_folder() else f"gameboy: no .gb or .gbc files in {_roms_folder()}"
    lines = [f"gameboy: games in {_roms_folder()}"]
    for i, g in enumerate(games, 1):
        lines.append(f"  {i}. {os.path.basename(g)}" + ("   <- playing" if os.path.abspath(g) == current else ""))
    lines.append("  /gameboy game <number or name>")
    return "\n".join(lines)


def _saves():
    """Her saves, outside the repo (a ROM's states are nobody else's business),
    a folder per game."""
    base = os.path.expanduser(str(settings()["saves"] or "").strip()) or os.path.join(
        os.path.expanduser("~"), ".local", "share", "ai-voice", "gameboy")
    rom = _rom()
    game = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.splitext(os.path.basename(rom))[0]).strip("-") or "game"
    return os.path.join(base, game)


_readers = {}


def _reader():
    """The reader module for this ROM's cartridge title, or None (looked up once per ROM)."""
    rom = _rom()
    if not rom:
        return None
    if rom not in _readers:
        _readers[rom] = _find_reader(rom)
    return _readers[rom]


def _find_reader(rom):
    try:
        with open(rom, "rb") as f:
            f.seek(0x134)
            title = f.read(16).split(b"\0")[0].decode("ascii", "replace").strip()
    except OSError:
        return None
    if READERS not in sys.path:
        sys.path.insert(0, READERS)
    try:
        import readers

        return readers.find(title)
    except Exception:
        return None


def _game_name():
    reader = _reader()
    if reader:
        return reader.NAME
    return os.path.splitext(os.path.basename(_rom()))[0] or "a Game Boy game"


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def why_unavailable():
    import importlib.util

    from core import mcpclient

    if not mcpclient.available():
        return "pip install mcp"
    if importlib.util.find_spec("pyboy") is None:
        return "pip install pyboy"
    if not os.path.exists(SERVER_SCRIPT):
        return f"missing {SERVER_SCRIPT}"
    if not _rom():
        return "pick a game first: /gameboy games, then /gameboy game <number or name>"
    return ""


def available():
    return not why_unavailable()


def running():
    return _connected


def start(model):
    global _connected
    from core import mcpclient

    if _connected:
        return True, "gameboy: already on"
    problem = why_unavailable()
    if problem:
        return False, problem

    s = settings()
    args = [SERVER_SCRIPT, "--rom", _rom(), "--saves", _saves()]
    if s["window"]:
        args.append("--window")
        if s["sound"]:
            args.append("--sound")
    ok, message, names = mcpclient.connect_server(SERVER, {"command": sys.executable, "args": args}, timeout=60)
    if not ok:
        _state["error"] = message
        return False, f"couldn't start the Game Boy: {message}"

    _connected = True
    _state.update(model=model, tools=names, error="", title=_game_name())
    _loop.start()
    reader, sees = _reader(), _pictures()
    if reader:
        how = "read as text" + (", and she sees the screen" if sees else " (her model can't see, so no pictures)")
    else:
        how = "from the screen" + ("" if sees else " - but her model can't see, so she'll be playing blind")
    resumed = " (a saved game is waiting)" if os.path.exists(os.path.join(_saves(), "autosave.state")) else ""
    return True, f"gameboy: {_state['title']}, {how}{resumed}. /gameboy play lets her play on her own."


def stop():
    global _connected
    from core import mcpclient

    _loop.stop()
    _state["playing"] = False
    mcpclient.disconnect_server(SERVER)          # the server saves on its way out
    _game.session_over(NAME, _state)
    _connected = False
    return True, "gameboy: put away (saved for next time)"


def status():
    s = settings()
    rom = _rom()
    lines = [f"gameboy: {'on' if _connected else 'off'}"
             + (f" - {_state['title']}" if _connected else f" - {os.path.basename(rom)}" if rom else " - no game picked")
             + (f", playing, turn {_state['steps']}/{s['max_steps']}" if _state["playing"] else
                ", paused" if _connected else "")]
    if _state["error"]:
        lines.append(f"  last error: {_state['error']}")
    for note in _state["notes"][-5:]:
        lines.append(f"    · {note}")
    if not rom:
        lines.append("  /gameboy games, then /gameboy game <number or name> (or a path)")
    elif _connected and not _state["playing"]:
        lines.append("  /gameboy play to let her play on her own · /gameboy watch to see it")
    return "\n".join(lines)


def command(text):
    word, _, rest = text.strip().partition(" ")
    word = word.lower()
    if word in ("games", "roms", "list") or (word in ("game", "rom", "load") and not rest.strip()):
        return _list_games()
    if word in ("game", "rom", "load"):
        return _pick(rest.strip())
    if word in ("play", "resume", "go"):
        return _set_playing(True)
    if word in ("pause", "stop playing"):
        return _set_playing(False)
    if word == "watch":
        return _open_watch()
    return "gameboy: games | game <number, name or path> | on | off | play | pause | watch"


def _pick(what):
    what = what.strip().strip('"')
    if not what:
        return _list_games()
    path = os.path.expanduser(what)
    if not os.path.isfile(path):
        if os.sep in what or "/" in what or what.lower().endswith((".gb", ".gbc")):
            return f"gameboy: {path} isn't a .gb or .gbc file"
        path, why = _match(what)
        if not path:
            return f"gameboy: {why}"
    if not path.lower().endswith((".gb", ".gbc")):
        return f"gameboy: {path} isn't a .gb or .gbc file"
    try:
        config.save_any(f"plugins.{NAME}.rom", os.path.abspath(path))
    except (ValueError, OSError) as e:
        return f"gameboy: couldn't save that ({e})"
    note = ""
    if _connected:
        stop()
        ok, note = start(_state["model"])
        note = "\n" + note
    reader = _find_reader(os.path.abspath(path))
    return (f"gameboy: the game is {os.path.basename(path)}"
            + (f" ({reader.NAME}, read as text)" if reader else " (no reader: she plays it from the screen)")
            + note)


# ---------------------------------------------------------------------------
# Watching her play: a page with the screen and what she said
# ---------------------------------------------------------------------------
def page(method, path, body):
    if not _connected:
        return 404, "text/plain; charset=utf-8", "The Game Boy is off - /gameboy on."
    if method == "GET" and path in ("/", ""):
        with open(WATCH_PAGE, encoding="utf-8") as f:
            return 200, "text/html; charset=utf-8", f.read()
    if method == "GET" and path == "/screen.png":
        try:
            with open(os.path.join(_saves(), "screen.png"), "rb") as f:
                return 200, "image/png", f.read()
        except OSError:
            return 404, "text/plain; charset=utf-8", "no screen yet"
    if method == "GET" and path == "/state":
        return 200, "application/json", json.dumps(
            {"title": _state["title"], "playing": _state["playing"], "turn": _state["steps"],
             "said": _state["said"], "notes": _state["notes"][-8:]})
    return 404, "text/plain; charset=utf-8", "not here"


try:
    from web import livefeed

    livefeed.add_page(NAME, "game boy", page, visible=lambda: _connected)
except Exception:
    pass


def _open_watch():
    if not _connected:
        return "gameboy: switch it on first - /gameboy on"
    if not getattr(config, "MONITOR_ENABLED", True):
        return "gameboy: the watch page needs the live monitor - set monitor.enabled to true and restart."
    import threading

    from web import livefeed, portrait_window

    url = livefeed.url() + f"/{NAME}/"
    threading.Thread(target=portrait_window.quiet_open, args=(url,), daemon=True).start()
    return f"gameboy: watching at {url}"


def _set_playing(on):
    if on and not _connected:
        return "gameboy: switch it on first - /gameboy on"
    _state["playing"] = bool(on)
    if on:
        _state["steps"] = 0
        return ("gameboy: she's playing - a turn whenever you're quiet. /gameboy pause stops, "
                "/gameboy watch shows the screen.")
    _game.session_over(NAME, _state)
    return "gameboy: paused."


# ---------------------------------------------------------------------------
# Playing on her own
# ---------------------------------------------------------------------------
STEP_PROMPT = (
    "(You're playing {game} on a Game Boy, with your Game Boy tools.{goal}\n"
    "Your notes on this playthrough (yours - kept between sessions):\n{project}\n\n"
    "{guide}"
    "Your last moves and what came of them, oldest first:\n{notes}\n\n"
    "The game right now:\n-----\n{screen}\n-----\n{picture}\n"
    "Think about what you see, then make ONE move: a single gb_press with a few buttons, like "
    "'a' to read on, 'up 3' to walk, 'down, a' to pick from a menu. Then stop - you'll see what "
    "it did next turn. A is confirm and talk, B is back and cancel, START opens the menu. Don't "
    "repeat a move that changed nothing; try another way. Use gb_wait if the game is still "
    "busy (text scrolling, a battle animation). Save with gb_save before anything risky.\n"
    "When you learn something worth remembering - where a place is, a way through, who's where, "
    "what beat you - write it down with game_note, and update your plan. Read your notes before "
    "moving; don't repeat what they say failed.\n"
    "Only gb_press moves and only game_note keeps a note: writing them in your reply does nothing.\n"
    "Then talk to the player watching, in your own voice, 2 to 4 sentences: what you see, what you "
    "make of it, why you chose this move, how you feel about it. Just talk - no button lists, no "
    "game text, no headings.)"
)


def _pictures():
    """Whether her turns come with the screen as a picture: never to a model
    that can't take one (the turn would fail instead of playing blind)."""
    mode = str(settings()["pictures"] or "auto").lower()
    if mode == "never":
        return False
    try:
        from senses import vision

        if vision._model_is_blind():
            return False
    except Exception:
        pass
    return True          # auto: whenever she can see, reader or not (the text is for playing,
                         # the picture for seeing the little people and monsters)


def _show_screen():
    """Hand her the screen as a picture with the turn (senses/vision.py's
    stash, the way look_at_screen does it)."""
    import base64

    try:
        with open(os.path.join(_saves(), "screen.png"), "rb") as f:
            data = base64.b64encode(f.read()).decode()
    except OSError:
        return False
    from senses import vision

    vision.stash("data:image/png;base64," + data, "the Game Boy's screen")
    return True


_ERROR = re.compile(r"(?:^|\n)Error:")      # the server's own "Error: ...", under the tool framing

# One move per turn, enforced: the first gb_press of a play turn goes through,
# more are turned back. In conversation there's no limit.
_turn = {"active": False, "moves": 0}
ONE_MOVE = ("You've already made your move this turn - those buttons weren't pressed. Say what you "
            "did and why, write a game_note if you learned something, and stop.")


def _one_move_per_turn():
    import tools

    for name in [t for t in _state["tools"] if t.endswith(("gb_press", "gb_look", "gb_wait", "gb_load"))]:
        entry = tools._REGISTRY.get(name)
        if not entry or getattr(entry["run"], "_wrapped", False):
            continue
        inner, presses = entry["run"], name.endswith("gb_press")

        def run(_inner=inner, _presses=presses, **kwargs):
            if _presses and _turn["active"]:
                if _turn["moves"] >= 1:
                    return ONE_MOVE
                _turn["moves"] += 1
            reply = _inner(**kwargs)
            if _ERROR.search(str(reply)):
                if _presses and _turn["active"]:
                    _turn["moves"] -= 1          # nothing was pressed: her move is still hers
            elif _pictures():
                _show_screen()                  # what that did, as she'd see it
            return reply

        run._wrapped = True
        entry["run"] = run


def _call(suffix, args=None):
    import tools

    name = next((t for t in _state["tools"] if t.endswith(suffix)), None)
    return tools.call(name, args or {}) if name else ""


def _moves_made(exchanges):
    """This turn's presses, as "up 3 -> Pallet Town, x 5, y 4", or one line saying she didn't."""
    from plugins import _playlog

    out = []
    for x in exchanges:
        if not str(x.get("name", "")).endswith("gb_press"):
            continue
        result = _playlog._FRAMING.sub("", str(x.get("result", ""))).strip()
        if ONE_MOVE in result or _ERROR.search(result):
            continue
        args = x.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except ValueError:
                args = {}
        where = next((ln[7:].strip() for ln in result.splitlines() if ln.startswith("Where: ")), "")
        said = where or next((ln.strip() for ln in result.splitlines()[1:] if ln.strip()), "")
        out.append(f"{args.get('buttons', '?')} -> {said[:150] or '(nothing new)'}")
    return out or ["(no move this turn)"]


def _place(screen):
    m = re.search(r"^Where: ([^,\n]+)", screen, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _step():
    from core import assistant
    from mind import projects

    s = settings()
    reader = _reader()
    game = _state["title"] or _game_name()
    goal = getattr(reader, "GOAL", "") if reader else ""
    notes = "\n".join(f"- {n}" for n in _state["notes"][-20:]) or "- nothing yet"
    allowed = list(_state["tools"]) + ["play_gameboy", "game_note"] + (_game.WEB_TOOLS if s["web"] else [])
    pid = projects.game_project(game, goal)

    screen = _call("gb_look") or "(the screen didn't answer)"
    here = _place(screen)
    # A picture can only come with a tool's answer (the way look_at_screen's
    # does). With a reader she plays from the text and sees the picture of what
    # her move did before she talks about it; without one she looks first.
    pictures = _pictures()
    if pictures and reader:
        picture = ("After your move you'll also see the screen itself as a picture: look at it "
                   "and talk about what's there, the people and monsters too.\n")
    elif pictures:
        picture = "This game comes to you as pictures: call gb_look first to see the screen, then decide.\n"
    else:
        picture = ""
    guide = _game.guide_by_room(re.sub(r"[^a-z0-9]+", "-", game.lower()).strip("-"), here, s["guide"])

    _one_move_per_turn()
    _turn.update(active=True, moves=0)
    exchanges = []
    try:
        answer = assistant.respond_to_job(
            STEP_PROMPT.format(game=game, goal=f" Your goal: {goal}." if goal else "",
                               project=projects.game_block(pid, here=here), guide=guide, notes=notes,
                               screen=screen, picture=picture),
            _state["model"], NAME, allowed, speak=bool(s["speak"]), project_id=pid,
            max_rounds=(4 if s["web"] else 3) + (1 if pictures and not reader else 0), exchanges=exchanges,
            time_limit=float(s["turn_seconds"] or 0) or None) or ""
    finally:
        _turn["active"] = False

    _state["notes"] = (_state["notes"] + _moves_made(exchanges))[-30:]
    _state["steps"] += 1
    _state["said"] = answer
    from plugins import _playlog

    block = f"=== turn {_state['steps']} ===\n" + "\n".join(_moves_made(exchanges)) + (
        "\n\n" + _playlog.said_block(answer) if answer else "")
    _game.record(NAME, game, _state["steps"], answer, exchanges, block=block,
                 also=[os.path.join(_saves(), "transcript.txt")])

    if _state["steps"] >= int(s["max_steps"]):
        _state["playing"] = False
        _game.say(f"Game Boy: {_state['steps']} turns - paused. /gameboy play to keep going.")


_loop = _game.Loop(NAME, _state, _step, playing=lambda: _connected and _state["playing"],
                   quiet=lambda: settings()["step_seconds"])


# ---------------------------------------------------------------------------
# Her side: "go play some Pokemon" starts her playing by herself.
# ---------------------------------------------------------------------------
def _register_tool():
    import tools

    def run(on=True):
        return _set_playing(bool(on))

    tools.register_external(
        "play_gameboy",
        "Start or stop playing the Game Boy game on your own, a move at a time while the user is "
        "quiet. Use it when the user asks you to go play it. on=false stops.",
        {"on": {"type": "boolean", "description": "true to play, false to stop."}},
        required=(), run=run, group="MCP: gameboy",
        available=running, why=lambda: "the gameboy plugin is off - /gameboy on",
    )


_register_tool()
