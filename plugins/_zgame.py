"""One text adventure: Zork I, Starcross, or any other Z-machine game. Given
what names the game (story file, title, goal, what to tell her about it),
this does the rest: the MCP server (games/zork/zork_server.py, run with the
game's story file and tool names), the commands, her turns and the watch
window. plugins/adventure.py makes one for each game in her library.

    game = _zgame.ZGame("starcross", "Starcross", story=..., goal=..., intro=..., feel=...)
    game.start(model); game.command("play")

A helper, not a plugin (the leading underscore).
"""
import json
import os
import re
import shutil
import sys

from plugins import _game

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_SCRIPT = os.path.join(HERE, "games", "zork", "zork_server.py")
WATCH_SCRIPT = os.path.join(HERE, "games", "zork", "watch.py")
STORY_TYPES = (".z3", ".z4", ".z5", ".z8", ".dat")

DEFAULTS = {"step_seconds": 8, "max_steps": 200, "speak": True, "web": True, "interpreter": "",
            "watch": False, "terminal": "", "guide": True,
            "turn_seconds": 150}

STEP_PROMPT = (
    "({intro}\n"
    "Your notes on this playthrough (yours - kept between sessions):\n{project}\n\n"
    "{guide}"
    "Your last moves and what the game said, oldest first:\n{notes}\n\n"
    "The game screen right now (your last command and what the game said):\n"
    "-----\n{screen}\n-----\n\n"
    "Read the screen, think about what it tells you, then make ONE move: a single {p}_command, "
    "short and verb-noun like {examples}. Then stop - you'll see what "
    "it did next turn. Don't repeat a move that just failed or changed nothing; try something "
    "new instead (another direction, another object). You only need {p}_status if the screen "
    "above is empty. Save with {p}_save before anything dangerous; {p}_restore if you die.\n"
    "When you learn something worth remembering - a room and its exits, a puzzle, an item and "
    "what it's for, what killed you - write it down with game_note, and update your plan. "
    "Read your notes before moving; don't repeat what they say failed.\n"
    "Only {p}_command sends a move and only game_note keeps a note: writing a command or a "
    "note in your reply does nothing. If the game didn't understand a command ('I don't know "
    "the word...'), that didn't use up your move - say it another way.\n"
    "Then talk to the player watching, in your own voice, 2 to 4 sentences: what you see, what "
    "you make of it, why you chose this move, how you feel about it ({feel}). Just talk - no "
    "commands, no game text, no headings.)"
)

# One move per turn, enforced rather than asked for: the model was told
# "ONE command" and still sent three or four. During a play turn the
# first <game>_command goes through; any more in the same turn are turned
# back, and she sees the result of the one she made next turn. In
# conversation (not a play turn) there's no limit.
ONE_MOVE = ("You've already made your move this turn - that command wasn't sent. Don't send "
            "more: say what you did and why, write a game_note if you learned something, and "
            "stop. You'll see what your move did next turn.")

# The game didn't understand the command, so nothing happened in it: that
# doesn't use up her move, and she can say it another way this turn.
NOT_UNDERSTOOD = re.compile(
    r"I don't know the word|That sentence isn't one I recognize|There was no verb in that "
    r"sentence|There were too many nouns|You must tell me how to do that|I beg your pardon|"
    r"I don't understand|You used the word .* in a way that I don't understand", re.IGNORECASE)

REGISTRY = {}           # name -> ZGame: every text adventure made so far

# dfrotz's status line: the room, then the score and moves (Zork, Starcross)
# or the score and the time (Planetfall's in-game clock)
STATUS = re.compile(r"^\s*(\S.*?)\s{2,}Score:\s*(-?\d+)\s+(Moves|Turns|Time):\s*(\d+)\s*$")


def dfrotz(interpreter=""):
    for candidate in (interpreter, shutil.which("dfrotz"), "/usr/games/dfrotz",
                      "/opt/homebrew/bin/dfrotz", "/usr/local/bin/dfrotz"):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""


def room(screen):
    """The room she's in: the last status line on the screen, or ""."""
    rooms = [m.group(1).strip() for m in map(STATUS.match, screen.splitlines()) if m]
    return rooms[-1] if rooms else ""


class ZGame:
    """One text adventure: its server, its turns, its commands.

    name     the plugin's name and the tools' prefix (zork -> zork_command)
    title    what it's called ("Zork I")
    story    the story file's path, or a function finding it (a game you bring)
    goal     her project's goal ("350 points: ...")
    intro    the first lines of each turn's prompt: the game, its goal, how it plays
    examples sample commands for the prompt, quoted
    feel     how she might feel about it, for the prompt ("grues are scary...")
    start_at what /<name> new says she's back at
    missing  what to say when there's no story file
    saves    its saves folder (agent/<name>/ unless given)
    config   whose settings it plays by (plugins.<config> in config.json; its name unless given)
    cmd      its slash command, for what's said back (/zork; /adventure for the library's)
    play     her tool for starting and stopping play (play_<name>); register=False when
             someone else registers it (/adventure's play_adventure, for all its games)

    She plays one text adventure at a time: starting one pauses any other.
    """

    def __init__(self, name, title, story, goal, intro, examples, feel, start_at="the beginning",
                 missing="", saves=None, config=None, play=None, register=True, cmd=None):
        self.name, self.title, self.goal = name, title, goal
        self.intro, self.examples, self.feel = intro, examples, feel
        self.start_at, self.missing = start_at, missing
        self._story = story
        self.server = name
        self.saves = saves or os.path.join(HERE, "agent", "games", name)      # gitignored, like her other state
        self.config = config or name
        self.play_tool = play or f"play_{name}"
        self.cmd = cmd or name              # the command she's driven with: /zork, /adventure
        self.watch_title = f"Luna plays {title}"
        self.state = {"model": None, "tools": [], "notes": [], "steps": 0, "playing": False,
                      "busy": False, "error": ""}
        self.connected = False
        self.turn = {"active": False, "moves": 0}
        self.loop = _game.Loop(name, self.state, self.step,
                               playing=lambda: self.connected and self.state["playing"],
                               quiet=lambda: self.settings()["step_seconds"], server=self.server,
                               pause=lambda: self.state.update(playing=False), title=title)
        if register:
            self._register_tool()
        REGISTRY[name] = self

    # -- setup ------------------------------------------------------------
    def settings(self):
        return _game.settings(self.config, DEFAULTS)

    def project(self):
        """What her project for it is filed under: the game's own name where
        projects knows it ("Zork playthrough"), else its title."""
        from mind import projects

        return self.name if self.name in projects.GAME_TITLES else self.title

    def story(self):
        return self._story() if callable(self._story) else self._story

    def interpreter(self):
        return dfrotz(self.settings()["interpreter"])

    def tool(self, suffix):
        """Her name for one of this game's tools (zork__zork_command), or None."""
        return next((t for t in self.state["tools"] if t.endswith(f"{self.name}_{suffix}")), None)

    # -- the plugin interface ----------------------------------------------
    def why_unavailable(self):
        from core import mcpclient

        if not mcpclient.available():
            return "pip install mcp"
        if not self.interpreter():
            return ("needs dfrotz - macOS: brew install frotz; Debian/Ubuntu: sudo apt install frotz; "
                    "Fedora: sudo dnf install frotz")
        if not os.path.exists(SERVER_SCRIPT):
            return f"missing {SERVER_SCRIPT}"
        story = self.story()
        if not story or not os.path.isfile(story):
            return self.missing or f"no story file for {self.title}"
        return ""

    def available(self):
        return not self.why_unavailable()

    def running(self):
        return self.connected

    def start(self, model):
        from core import mcpclient

        if self.connected:
            return True, f"{self.name}: already loaded"
        problem = self.why_unavailable()
        if problem:
            return False, problem

        spec = {"command": sys.executable,
                "args": [SERVER_SCRIPT, "--story", self.story(), "--saves", self.saves,
                         "--interpreter", self.interpreter(), "--name", self.name, "--title", self.title]}
        ok, message, names = mcpclient.connect_server(self.server, spec, timeout=30)
        if not ok:
            self.state["error"] = message
            return False, f"couldn't start {self.title}: {message}"

        self.connected = True
        self.state.update(model=model, tools=names, error="")
        self.loop.start()
        resumed = " (a saved game is waiting)" if os.path.exists(os.path.join(self.saves, "autosave.qzl")) else ""
        return True, f"{self.name}: {len(names)} tools{resumed}. /{self.cmd} play lets her play on her own."

    def stop(self):
        from core import mcpclient

        self.loop.stop()
        self.state["playing"] = False
        mcpclient.disconnect_server(self.server)      # the server autosaves on its way out
        _game.session_over(self.name, self.state)
        self.connected = False
        return True, f"{self.name}: put away (saved for next time)"

    def status(self):
        s, st = self.settings(), self.state
        lines = [f"{self.name}: {'loaded' if self.connected else 'off'}"
                 + (f" - playing, turn {st['steps']}/{s['max_steps']}" if st["playing"] else
                    " - paused" if self.connected else "")]
        if st["error"]:
            lines.append(f"  last error: {st['error']}")
        for note in st["notes"][-5:]:
            lines.append(f"    · {note}")
        if self.connected and not st["playing"]:
            lines.append(f"  /{self.cmd} play to let her play on her own")
        return "\n".join(lines)

    def command(self, text):
        word = text.strip().lower()
        if word in ("play", "resume", "go"):
            return self.set_playing(True)
        if word in ("pause", "stop playing"):
            return self.set_playing(False)
        if word == "watch":
            return self.open_watch()
        if word in ("new", "restart", "new game"):
            return self.new_game()
        return f"{self.name}: on | off | play | pause | watch | new"

    def new_game(self):
        """Start over from the beginning, and forget the old game's notes so
        she doesn't play the new one from memories of the last. The old game
        is kept first, in a save named old-<date>-<time>."""
        import tools
        from datetime import datetime

        name, saver = self.tool("restart"), self.tool("save")
        if not name:
            return f"{self.name}: load the game first - /{self.cmd} on"

        kept = ""
        if saver:
            slot = f"old-{datetime.now():%Y%m%d-%H%M}"
            if not tools.call(saver, {"slot": slot}).startswith("Error"):
                kept = f" The old game is saved as {slot} - ask her to restore {slot} to go back to it."

        reply = tools.call(name, {})
        if reply.startswith("Error"):
            return f"{self.name}: couldn't restart ({reply})"

        self.state.update(notes=[], steps=0)
        try:
            from mind import projects

            projects.new_game(self.project(), self.goal)     # fresh notes; the old ones are retired, not lost
        except Exception:
            pass
        try:
            with open(os.path.join(self.saves, "transcript.txt"), "a", encoding="utf-8") as f:
                f.write("\n" + "=" * 60 + "\n[a new game]\n")
        except OSError:
            pass
        return f"{self.name}: new game - back at {self.start_at}. /{self.cmd} play to start." + kept

    # -- a window to watch her play in -------------------------------------
    def open_watch(self):
        from plugins import _terminal

        os.makedirs(self.saves, exist_ok=True)
        return _terminal.open_window([sys.executable, WATCH_SCRIPT, self.saves, self.watch_title],
                                     self.watch_title, self.settings()["terminal"], self.name)

    def set_playing(self, on):
        if on and not self.connected:
            return f"{self.name}: load it first - /{self.cmd} on"
        self.state["playing"] = bool(on)
        if on:
            for other in REGISTRY.values():              # one game at a time
                if other is not self and other.state["playing"]:
                    other.set_playing(False)
            self.state["steps"] = 0
            extra = "\n" + self.open_watch() if self.settings()["watch"] else ""
            return (f"{self.name}: she's playing - she takes a turn whenever you're quiet. "
                    f"/{self.cmd} pause stops, /{self.cmd} watch shows the game." + extra)
        _game.session_over(self.name, self.state)
        return f"{self.name}: paused."

    # -- her turns ---------------------------------------------------------
    def screen(self, lines=30):
        """The tail of the game's transcript, without her own comments - what
        a player would be looking at before typing the next command."""
        path = os.path.join(self.saves, "transcript.txt")
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 12000))
                text = f.read().decode("utf-8", "replace")
        except OSError:
            return "(nothing yet - a new game)"

        # Only this game: from the last "[a new game]" or the game starting up.
        starts = [m.end() for m in re.finditer(r"^(?:\[a new game\]|={20,}).*$", text, re.MULTILINE)]
        if starts:
            text = text[starts[-1]:]

        keep, skipping = [], False
        for line in text.splitlines():
            if line.startswith("[") and not line.startswith(("[saved", "[restored")):
                skipping = True          # her words (_playlog.said_marked): run to the next blank line
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

    def pretty_turn(self, turn, said, width=78):
        """This move laid out like the watch window, as plain text for the
        playlog: her command, a status bar, the game's reply wrapped, then
        what she said about it."""
        import textwrap
        from datetime import datetime

        from plugins import _playlog

        screen = self.screen(lines=40)
        starts = [i for i, ln in enumerate(screen.splitlines()) if ln.startswith("> ")]
        lines = screen.splitlines()[starts[-1]:] if starts else screen.splitlines()

        out = [f"=== move {turn}  {datetime.now():%H:%M:%S} " + "=" * max(3, width - 22)]
        blank = False
        for line in lines:
            status = STATUS.match(line)
            if status:
                here, score, kind, n = status.groups()
                label = f" {here}  ·  score {score}  ·  {'time' if kind == 'Time' else 'move'} {n} "
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

    def moves_made(self, exchanges):
        """This turn's commands that reached the game, as "north -> Forest Path",
        or one line saying she didn't move."""
        from plugins import _playlog

        out = []
        for x in exchanges:
            if not str(x.get("name", "")).endswith(f"{self.name}_command"):
                continue
            result = _playlog._FRAMING.sub("", str(x.get("result", ""))).strip()
            if ONE_MOVE in result:
                continue
            args = x.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except ValueError:
                    args = {}
            said = next((ln.strip() for ln in result.splitlines()
                         if ln.strip() and not STATUS.match(ln) and not ln.startswith(">")), "")
            out.append(f"{args.get('command', '?')} -> {said[:150] or '(no reply)'}")
        return out or ["(no move this turn)"]

    def one_move_per_turn(self):
        import tools

        name = self.tool("command")
        entry = tools._REGISTRY.get(name) if name else None
        if not entry or getattr(entry["run"], "_one_move", False):
            return
        inner, turn = entry["run"], self.turn

        def run(**kwargs):
            if turn["active"]:
                if turn["moves"] >= 1:
                    return ONE_MOVE
                turn["moves"] += 1
            reply = inner(**kwargs)
            if turn["active"] and NOT_UNDERSTOOD.search(str(reply)):
                turn["moves"] -= 1          # nothing happened: her move is still hers
            return reply

        run._one_move = True
        entry["run"] = run

    def prompt(self, notes, screen, guide, project):
        return STEP_PROMPT.format(intro=self.intro, notes=notes, screen=screen, guide=guide,
                                  project=project, p=self.name, examples=self.examples, feel=self.feel)

    def step(self):
        from core import assistant
        from mind import projects

        s, st = self.settings(), self.state
        notes = "\n".join(f"- {n}" for n in st["notes"][-20:]) or "- nothing yet: a new game"
        allowed = list(st["tools"]) + [self.play_tool, "game_note"] + (_game.WEB_TOOLS if s["web"] else [])
        pid = projects.game_project(self.project(), self.goal)
        screen = self.screen()
        here = room(screen)

        self.one_move_per_turn()
        self.turn.update(active=True, moves=0)
        exchanges = []
        try:
            # A move, a note, maybe a status check - more rounds than that is
            # her trying to play several moves blind.
            answer = assistant.respond_to_job(
                self.prompt(notes, screen, _game.guide_by_room(self.name, here, s["guide"]),
                            projects.game_block(pid, here=here)),
                st["model"], self.name, allowed, speak=bool(s["speak"]), project_id=pid,
                max_rounds=4 if s["web"] else 3, exchanges=exchanges,
                time_limit=_game.turn_limit(s["turn_seconds"], DEFAULTS["turn_seconds"])) or ""
        finally:
            self.turn["active"] = False
        # Her memory of the last moves is what she sent and what the game said,
        # not her own words: fed back, those taught her to write "Move: north"
        # instead of making the move.
        st["notes"] = (st["notes"] + self.moves_made(exchanges))[-30:]
        st["steps"] += 1

        _game.record(self.name, self.title, st["steps"], answer, exchanges,
                     block=self.pretty_turn(st["steps"], answer),
                     also=[os.path.join(self.saves, "transcript.txt")])

        if st["steps"] >= _game.whole(s["max_steps"], DEFAULTS["max_steps"]):
            st["playing"] = False
            _game.say(f"{self.title}: {st['steps']} turns - paused. /{self.cmd} play to keep going.")

    # -- her side: "go play some Zork" starts her playing by herself --------
    def _register_tool(self):
        import tools

        tools.register_external(
            self.play_tool,
            f"Start or stop playing {self.title} on your own, a few moves at a time while the user "
            f"is quiet. Use it when the user asks you to go play {self.title}. on=false stops.",
            {"on": {"type": "boolean", "description": "true to play, false to stop."}},
            required=(), run=lambda on=True: self.set_playing(bool(on)), group=f"MCP: {self.name}",
            available=self.running, why=lambda: f"{self.title} isn't loaded - /{self.cmd} on",
        )


def find_story(folder, *names):
    """A story file in games/<folder>/: one of names if it's there, else the
    only .z3/.z5... in it. "" when there's none (or several and none named)."""
    where = os.path.join(HERE, "games", folder)
    for n in names:
        if os.path.isfile(os.path.join(where, n)):
            return os.path.join(where, n)
    try:
        found = sorted(f for f in os.listdir(where) if f.lower().endswith(STORY_TYPES))
    except OSError:
        return ""
    return os.path.join(where, found[0]) if len(found) == 1 else ""
