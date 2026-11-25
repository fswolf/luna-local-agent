"""Adventure - her library of text adventures: Infocom's and any other
Z-machine game, played the way she plays Zork.

    /adventure games          the library, numbered (which one is loaded, which is playing)
    /adventure game <n|name>  pick one ("2", "planetfall"); loads it if she's on
    /adventure on             load the game you picked (her tools for it appear)
    /adventure play           she plays it on her own while you're quiet
    /adventure pause          stop taking turns
    /adventure watch          a terminal window showing the game as she plays
    /adventure new            start that game over (the old one is kept as old-<date>)
    /adventure off            put it away (saved, picked up next time)
    /adventure                what's loaded, score, what she's been up to

A game is a folder in games/ with one story file in it (.z3, .z5, .z8...):
games/planetfall/planetfall.z3. Its folder name is its name everywhere: her
tools (planetfall_command...), her saves (agent/games/planetfall/),
her notes (agent/knowledge/planetfall/), its project. Drop a folder in and
it's in the library; nothing to register.

An about.json beside the story file tells her about the game, for each
turn's prompt (all optional; without it she gets a plain "a classic text
adventure"):

    {"title": "Planetfall", "goal": "...", "intro": "You're playing ...",
     "examples": "'north', 'take kit'", "feel": "...", "start_at": "Deck Nine"}

Zork I (games/zork/, MIT) and Starcross (games/starcross/) ship in it.
Saves from before (agent/zork/, agent/starcross/: the old /zork and
/starcross; agent/adventures/<game>/: the library's first days) move into
agent/games/ at startup (plugins/_game.py tidy).

She asks for one herself with play_adventure ("go play some Planetfall").
She plays one text adventure at a time: starting one pauses the others.

    "adventure": {
        "enabled": false,
        "game": "",             # the one you picked (/adventure game sets it)
        ...                     # the rest as zork's: step_seconds, max_steps, speak, web,
    }                           # interpreter, watch, terminal, guide, turn_seconds
"""
import json
import os
import re

import config
from core import logbook
from plugins import _game, _zgame

NAME = "adventure"
SUMMARY = "her library of text adventures (Zork, Starcross, Planetfall...): /adventure games"

GAMES = os.path.join(_zgame.HERE, "games")
SAVES = os.path.join(_zgame.HERE, "agent", "games")      # gitignored, one folder per game (chess's too)

_on = {"model": None, "running": False}


def _id(folder):
    """A game's name from its folder: lower case, letters, digits and _ (a tool prefix)."""
    return re.sub(r"[^a-z0-9_]+", "_", folder.lower()).strip("_")


def library():
    """[(name, folder)] for every games/<folder>/ with exactly one story file, by name."""
    out, seen = [], set()
    try:
        folders = sorted(os.listdir(GAMES))
    except OSError:
        return out
    for folder in folders:
        name = _id(folder)
        if name and name not in seen and os.path.isdir(os.path.join(GAMES, folder)) and _zgame.find_story(folder):
            seen.add(name)          # (zork-2 and zork_2 would be one name: the first folder wins)
            out.append((name, folder))
    return out


def _about(folder):
    try:
        with open(os.path.join(GAMES, folder, "about.json"), encoding="utf-8") as f:
            about = json.load(f)
        return about if isinstance(about, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logbook.info("adventure", "games/%s/about.json can't be read: %s", folder, e)
        return {}


def game(name):
    """The ZGame for a game in the library, made the first time it's asked for."""
    folder = dict(library()).get(name)
    if not folder:
        return None
    if name in _zgame.REGISTRY:
        return _zgame.REGISTRY[name]
    # _move_old_saves(name)       # (plugins/_game.py tidy does it for every game, at startup)
    a = _about(folder)
    title = str(a.get("title") or folder.replace("_", " ").replace("-", " ").title())
    return _zgame.ZGame(
        name, title,
        story=lambda: _zgame.find_story(folder),
        goal=str(a.get("goal") or "finish the game with the best score you can"),
        intro=str(a.get("intro") or
                  f"You're playing {title}, a classic text adventure, with your {name} tools. Explore, "
                  "read everything, pick up what looks useful and work out its puzzles; SCORE tells you "
                  "how you're doing."),
        examples=str(a.get("examples") or "'look', 'north', 'open door'"),
        feel=str(a.get("feel") or "what surprises you, what you're curious about, what scares you"),
        start_at=str(a.get("start_at") or "the beginning"),
        missing=f"no story file in games/{folder}/",
        saves=os.path.join(SAVES, name), config=NAME, play="play_adventure", register=False,
        cmd=NAME)


# Replaced by plugins/_game.py tidy(), which moves every game's old folder
# into agent/games/ at startup instead of one game at a time when picked.
# OLD_SAVES = ("zork", "starcross")      # games that had plugins (and agent/<name>/ saves) of their own
#
#
# def _move_old_saves(name):
#     """agent/zork/ -> agent/adventures/zork/, once: a playthrough from the
#     old /zork carries on. Only those two: agent/ holds much else."""
#     old, new = os.path.join(_zgame.HERE, "agent", name), os.path.join(SAVES, name)
#     if name not in OLD_SAVES or not os.path.isdir(old) or os.path.exists(new):
#         return
#     try:
#         os.makedirs(SAVES, exist_ok=True)
#         os.replace(old, new)
#         logbook.info("adventure", "moved %s's saves to %s", name, new)
#     except OSError as e:
#         logbook.info("adventure", "couldn't move %s to %s: %s", old, new, e)


def _picked():
    name = str(config.plugin_settings(NAME).get("game") or "").strip().lower()
    return name if name in dict(library()) else ""


def _current():
    name = _picked()
    return game(name) if name else None


def _match(what):
    """A game by number in the list, or by name or title (or the start of one)."""
    games = library()
    what = what.strip().lower()
    if what.isdigit() and 1 <= int(what) <= len(games):
        return games[int(what) - 1][0]
    names = [n for n, _ in games]
    if _id(what) in names:
        return _id(what)
    for n, _folder in games:
        title = game(n).title.lower()
        if title == what or n.startswith(_id(what)) or (title and title.startswith(what)):
            return n
    return ""


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def why_unavailable():
    from core import mcpclient

    if not mcpclient.available():
        return "pip install mcp"
    if not _zgame.dfrotz(_game.settings(NAME, _zgame.DEFAULTS)["interpreter"]):
        return ("needs dfrotz - macOS: brew install frotz; Debian/Ubuntu: sudo apt install frotz; "
                "Fedora: sudo dnf install frotz")
    if not library():
        return "no games yet: put a folder with a story file (.z3, .z5...) in games/"
    return ""


def available():
    return not why_unavailable()


def running():
    return _on["running"]


def start(model):
    _on.update(model=model, running=True)
    g = _current()
    if not g:
        return True, "adventure: on. Pick a game: /adventure games, then /adventure game <number or name>."
    ok, said = g.start(model)
    # the library is on either way: a game that won't load leaves the others to pick
    return True, said if ok else f"adventure: on, but {g.title} didn't load ({said}). /adventure games to pick another."


def stop():
    g = _current()
    _on["running"] = False
    if g and g.running():
        return g.stop()
    return True, "adventure: off"


def status():
    g = _current()
    if not g:
        return "adventure: " + ("on" if _on["running"] else "off") + " - no game picked.\n" + _list()
    return g.status() + "\n  /adventure games for the library"


def _list():
    games = library()
    if not games:
        return "No games yet: put a folder with a story file (.z3, .z5...) in games/."
    picked = _picked()
    lines = ["The library (/adventure game <number or name>):"]
    for i, (name, _folder) in enumerate(games, 1):
        g = game(name)
        mark = " - playing" if g.state["playing"] else " - loaded" if g.running() else ""
        lines.append(f"  {i}. {g.title} [{name}]{' <' if name == picked else ''}{mark}")
    return "\n".join(lines)


def _pick(what):
    name = _match(what)
    if not name:
        return f"adventure: no game matching {what!r}.\n" + _list()
    old = _current()
    try:
        config.save_any(f"plugins.{NAME}.game", name)
    except (ValueError, OSError) as e:
        return f"adventure: couldn't save that ({e})"
    g = game(name)
    note = ""
    if _on["running"]:
        if old and old is not g and old.running():
            old.stop()
        ok, note = g.start(_on["model"])
        note = "\n" + note
    return f"adventure: the game is {g.title}." + note


def command(text):
    word, _, rest = text.strip().partition(" ")
    word, whole = word.lower(), " ".join(text.lower().split())
    if word in ("games", "list", "library") or (word in ("game", "load", "pick") and not rest.strip()):
        return _list()
    if word in ("game", "load", "pick"):
        return _pick(rest)
    g = _current()
    if not g:
        return "adventure: pick a game first.\n" + _list()
    if whole in ("play", "resume", "go", "pause", "stop playing", "watch", "new", "restart", "new game"):
        return g.command(whole)
    return "adventure: games | game <number or name> | on | off | play | pause | watch | new"


# ---------------------------------------------------------------------------
# Her side: "go play some Planetfall"
# ---------------------------------------------------------------------------
def _play(game_name="", on=True):
    if not on:
        playing = [g for g in _zgame.REGISTRY.values() if g.state["playing"]]
        return "\n".join(g.set_playing(False) for g in playing) or "Not playing anything."
    if game_name:
        name = _match(game_name)
        if not name:
            return f"There's no {game_name!r} in the library. " + _list()
        busy = next((g for g in _zgame.REGISTRY.values() if g.turn["active"]), None)
        if busy and busy.name != name:
            # from inside a turn of one game: switching would put it away under her
            return (f"You're in the middle of a turn of {busy.title}. Finish it; switching games "
                    "is for when you're not playing.")
        if name != _picked():
            _pick(name)               # (she's on: this loads it)
    g = _current()
    if not g:
        return "No game picked yet. " + _list()
    if not g.running():
        ok, said = g.start(_on["model"])
        if not ok:
            return said
    return g.set_playing(True)


def _register_tool():
    import tools

    tools.register_external(
        "play_adventure",
        "Start or stop playing one of the text adventures in your library (Zork, Starcross, "
        "Planetfall...) on your own, a few moves at a time while the user is quiet. Use it when "
        "the user asks you to go play one. game: its name (empty for the one already picked); "
        "on=false stops.",
        {"game": {"type": "string", "description": "Which game, like 'planetfall'. Empty: the one already picked."},
         "on": {"type": "boolean", "description": "true to play, false to stop."}},
        required=(), run=lambda game="", on=True: _play(game, on), group="MCP: adventure",
        available=running, why=lambda: "the adventure plugin is off - /adventure on",
    )


_register_tool()
