"""Zork as an MCP server: one game of Zork I behind a few tools. Any other
Infocom-style Z-machine game works the same way (Luna's Starcross runs on
it): --story picks the game, --name the tools' prefix, --title its name.

    python games/zork/zork_server.py [--story FILE] [--saves DIR] [--interpreter PATH]
                                     [--name zork] [--title "Zork I"]

Speaks MCP over stdio, so anything that talks MCP can play - Luna's zork
plugin starts it for her, but Claude Desktop or any other client works
the same way.

Underneath it's dfrotz, the plain-text build of the Frotz Z-machine
interpreter, run as a child process: commands go in on stdin, the game's
reply comes back on stdout. Install it with
    macOS:          brew install frotz
    Debian/Ubuntu:  sudo apt install frotz        (dfrotz is in /usr/games)
    Fedora:         sudo dnf install frotz        (if that has no dfrotz:
                    git clone https://gitlab.com/DavidGriffith/frotz
                    cd frotz && make dumb         -> ./dfrotz)

Tools (named for --name: starcross_command...):
    zork_command(command)   type one command, get the game's reply
    zork_status()           look + inventory + score in one call
    zork_save(slot) / zork_restore(slot)
    zork_restart()

Everything typed and every reply is also appended to transcript.txt in
the saves folder, so you can watch a game as it's played:
    python games/zork/watch.py [saves folder]
(Luna's /zork watch opens that in a terminal window for you.)

The game autosaves every few commands and when the server stops, and
picks the autosave back up on the next start, so a game survives Luna
restarting. Saves live in --saves, and dfrotz runs in that folder,
restricted to it (-R .): SAVE, RESTORE and SCRIPT can't touch anything else.

Zork I is MIT-licensed (Microsoft, 2025) - see LICENSE-zork1.
"""
import argparse
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

try:
    from mcp.server.fastmcp import FastMCP          # mcp 1.x
except ImportError:
    from mcp.server.mcpserver import MCPServer as FastMCP   # mcp 2.x renamed it

HERE = os.path.dirname(os.path.abspath(__file__))
AUTOSAVE = "autosave"
AUTOSAVE_EVERY = 5          # commands
MAX_COMMAND = 120
# a game waiting for a keypress, not a command: the last thing it said
PRESS_ON = re.compile(r"\b(?:hit|press)\s+(?:return|enter|any\s+key)\b[^\n]*$", re.IGNORECASE)

ap = argparse.ArgumentParser()
ap.add_argument("--story", default=os.path.join(HERE, "zork1.z3"))
ap.add_argument("--saves", default=os.path.join(HERE, "saves"))
ap.add_argument("--interpreter", default="")
ap.add_argument("--name", default="zork")          # the tools' prefix: zork_command
ap.add_argument("--title", default="Zork I")       # what the tools call the game
ARGS, _ = ap.parse_known_args()
P = "".join(c for c in ARGS.name.lower() if c.isalnum() or c == "_") or "zork"
TITLE = ARGS.title


def transcript(text):
    """Append to the watchable transcript. Never fails the game."""
    try:
        path = os.path.join(ARGS.saves, "transcript.txt")
        if os.path.exists(path) and os.path.getsize(path) > 2_000_000:
            with open(path, "rb") as f:
                f.seek(-500_000, 2)
                tail = f.read()
            with open(path, "wb") as f:
                f.write(tail)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n\n")
    except OSError:
        pass


def find_dfrotz():
    for candidate in (ARGS.interpreter, shutil.which("dfrotz"), "/usr/games/dfrotz",
                      "/opt/homebrew/bin/dfrotz", "/usr/local/bin/dfrotz"):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""


class Game:
    """One dfrotz process and the text coming out of it."""

    def __init__(self):
        self.proc = None
        self.out = queue.Queue()
        self.lock = threading.Lock()
        self.since_save = 0
        self.last = ""
        self.over = False

    # -- process -----------------------------------------------------------
    def start(self):
        dfrotz = find_dfrotz()
        if not dfrotz:
            raise RuntimeError("dfrotz isn't installed - macOS: brew install frotz; "
                               "Debian/Ubuntu: sudo apt install frotz; see games/zork/zork_server.py")
        if not os.path.exists(ARGS.story):
            raise RuntimeError(f"no story file at {ARGS.story}")

        os.makedirs(ARGS.saves, exist_ok=True)
        # A fresh queue for each dfrotz: the last one's end-of-output
        # marker (and anything it said last) would otherwise be read as
        # this one's intro, and every reply after it lands one late.
        self.out = queue.Queue()
        # -R . rather than -R <the saves folder>: it's the same folder (cwd),
        # and dfrotz 2.54 mangles save names that are between half and the
        # whole length of the -R path (autosave.qzl -> "auto", and
        # old-20261028-1530 -> "old-20261" under agent/zork). With "." every
        # name is kept whole, and ../ or a full path still lands in here.
        self.proc = subprocess.Popen(
            [dfrotz, "-m", "-p", "-q", "-w", "200", "-R", ".", ARGS.story],
            cwd=ARGS.saves, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0)
        threading.Thread(target=self._pump, args=(self.proc, self.out), daemon=True).start()
        intro = self._read()

        if os.path.exists(self._path(AUTOSAVE)):
            back = self._restore(AUTOSAVE)
            if "ok" in back.lower():
                intro = "(Picked up the saved game.)\n" + self._send("look")

        self.last = intro
        transcript("=" * 60 + "\n" + clean(intro))
        return intro

    @staticmethod
    def _pump(proc, out):
        """One dfrotz's output into its own queue."""
        while True:
            try:
                chunk = proc.stdout.read(1)
            except (OSError, ValueError):     # closed under it
                chunk = b""
            if not chunk:
                out.put(None)
                return
            out.put(chunk)

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.alive():
            try:
                if not self.over:
                    self._save(AUTOSAVE)
            except Exception:
                pass
            self.proc.kill()
        if self.proc is not None:
            try:
                self.proc.wait(timeout=2)     # reaped, not left a zombie
            except Exception:
                pass
        self.proc = None

    # -- talking to it -----------------------------------------------------
    def _read(self, timeout=8.0):
        """Everything up to the next prompt: '>' for a command, or a
        question ending in ':' or '?' (filenames, restart?)."""
        buf, deadline = b"", time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                chunk = self.out.get(timeout=0.15)
            except queue.Empty:
                text = buf.decode("latin-1")
                if re.search(r"(\n>|^>)\s*$", text) or re.search(r"[:?]\s*$", text.rstrip("\n")[-80:] or "x"):
                    break
                continue
            if chunk is None:
                break
            buf += chunk
        return buf.decode("latin-1")

    def _send(self, line):
        self.proc.stdin.write((line + "\n").encode("latin-1", "replace"))
        self.proc.stdin.flush()
        text = self._read()
        # SAVE / RESTORE / SCRIPT ask for a filename: always ours, in saves/.
        if re.search(r"(file ?name|filename).*:\s*$", text, re.I | re.S):
            self.proc.stdin.write(b"\n")       # take the default, inside -R
            self.proc.stdin.flush()
            text += self._read()
        # "Hit RETURN when ready" (The Hitchhiker's Guide's SCORE): the game
        # waits for a key, and would eat her next command as it. Press it.
        for _ in range(3):
            if not PRESS_ON.search(text[-300:]):
                break
            self.proc.stdin.write(b"\n")
            self.proc.stdin.flush()
            text += "\n" + self._read()
        return text

    def _path(self, slot):
        return os.path.join(ARGS.saves, f"{slot}.qzl")

    @staticmethod
    def _typed(slot):
        """What's typed at the filename prompt: the bare name, which dfrotz
        (run in the saves folder, -R .) keeps in there."""
        return (f"{slot}.qzl\n").encode()

    def _save(self, slot):
        self.proc.stdin.write(b"save\n")
        self.proc.stdin.flush()
        text = self._read()
        if re.search(r":\s*$", text):
            if os.path.exists(self._path(slot)):
                os.remove(self._path(slot))    # no "overwrite?" question
            self.proc.stdin.write(self._typed(slot))
            self.proc.stdin.flush()
            text += self._read()
        self.since_save = 0
        return text

    def _restore(self, slot):
        self.proc.stdin.write(b"restore\n")
        self.proc.stdin.flush()
        text = self._read()
        if re.search(r":\s*$", text):
            self.proc.stdin.write(self._typed(slot))
            self.proc.stdin.flush()
            text += self._read()
        return text

    def ensure(self):
        if not self.alive():
            self.start()


game = Game()
mcp = FastMCP(P)


def clean(text):
    """The game's words, without dfrotz's prompt furniture."""
    text = re.sub(r"\n?>\s*$", "", text.replace("\r", ""))
    text = re.sub(r"(?m)^\s*Please enter a filename[^\n]*:\s*$", "", text)
    text = re.sub(r"(?m)^\s*>\s*$", "", text)
    text = re.sub(r"^\s*>\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or "(no reply)"


def _slot(name):
    name = re.sub(r"[^A-Za-z0-9_-]+", "", str(name or ""))[:32]
    return name or "slot1"


def zork_command(command: str) -> str:
    command = " ".join(str(command or "").split())[:MAX_COMMAND].lstrip("\\")
    if not command:
        return "No command given."

    with game.lock:
        game.ensure()
        reply = game._send(command)
        game.over = bool(re.search(r"(restart, restore, or quit|RESTART|you have died)", reply, re.I))
        game.since_save += 1
        if game.since_save >= AUTOSAVE_EVERY and not game.over:
            game._save(AUTOSAVE)
        game.last = reply

    transcript(f"> {command}\n{clean(reply)}")
    hint = ("\n[The game is over or you died. RESTORE goes back to the last save "
            f"({P}_restore), RESTART starts again.]" if game.over else "")
    return clean(reply) + hint


def zork_status() -> str:
    with game.lock:
        game.ensure()
        look = clean(game._send("look"))
        inv = clean(game._send("inventory"))
        score = clean(game._send("score"))
    text = f"{look}\n\n{inv}\n\n{score}"
    transcript(f"> look / inventory / score\n{text}")
    return text


def zork_save(slot: str = "slot1") -> str:
    with game.lock:
        game.ensure()
        transcript(f"[saved to {_slot(slot)}]")
        return clean(game._save(_slot(slot)))


def zork_restore(slot: str = AUTOSAVE) -> str:
    slot = _slot(slot)
    with game.lock:
        game.ensure()
        if not os.path.exists(game._path(slot)):
            have = sorted(f[:-4] for f in os.listdir(ARGS.saves) if f.endswith(".qzl"))
            return f"No save called {slot}. Saves: {', '.join(have) or 'none'}"
        reply = game._restore(slot)
        game.over = False
        text = clean(reply + "\n" + game._send("look"))
        transcript(f"[restored {slot}]\n{text}")
        return text


def zork_restart() -> str:
    with game.lock:
        game.stop()
        if os.path.exists(game._path(AUTOSAVE)):
            os.remove(game._path(AUTOSAVE))
        game.over = False
        return clean(game.start())


# Registered under the game's own names (starcross_command for Starcross),
# described for the game they're playing.
for _fn, _about in (
        (zork_command, f"Type one command into {TITLE}, the way a player would: 'look', 'north', "
                       "'open door', 'take it', 'inventory'. Short verb-noun commands work best. "
                       "Returns what the game says back."),
        (zork_status, f"Where you are in {TITLE}, what you're carrying, and the score, in one call "
                      "(LOOK, INVENTORY and SCORE). Use it when you've lost track."),
        (zork_save, f"Save {TITLE} to a named slot before something risky."),
        (zork_restore, f"Go back to a saved game of {TITLE}. 'autosave' is the one kept every few moves."),
        (zork_restart, f"Start a brand new game of {TITLE} from the beginning (the autosave is dropped).")):
    mcp.tool(name=P + _fn.__name__[len("zork"):], description=_about)(_fn)


if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        game.stop()
