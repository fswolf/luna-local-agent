"""Zork as an MCP server: one game of Zork I behind a few tools.

    python games/zork/zork_server.py [--story FILE] [--saves DIR] [--interpreter PATH]

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

Tools:
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
restarting. Saves live in --saves, and dfrotz is restricted to that
folder (-R): SAVE, RESTORE and SCRIPT can't touch anything else.

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

from mcp.server.fastmcp import FastMCP

HERE = os.path.dirname(os.path.abspath(__file__))
AUTOSAVE = "autosave"
AUTOSAVE_EVERY = 5          # commands
MAX_COMMAND = 120

ap = argparse.ArgumentParser()
ap.add_argument("--story", default=os.path.join(HERE, "zork1.z3"))
ap.add_argument("--saves", default=os.path.join(HERE, "saves"))
ap.add_argument("--interpreter", default="")
ARGS, _ = ap.parse_known_args()


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
        self.proc = subprocess.Popen(
            [dfrotz, "-m", "-p", "-q", "-w", "200", "-R", ARGS.saves, ARGS.story],
            cwd=ARGS.saves, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0)
        threading.Thread(target=self._pump, daemon=True).start()
        intro = self._read()

        if os.path.exists(self._path(AUTOSAVE)):
            back = self._restore(AUTOSAVE)
            if "ok" in back.lower():
                intro = "(Picked up the saved game.)\n" + self._send("look")

        self.last = intro
        transcript("=" * 60 + "\n" + clean(intro))
        return intro

    def _pump(self):
        while True:
            chunk = self.proc.stdout.read(1)
            if not chunk:
                self.out.put(None)
                return
            self.out.put(chunk)

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
        return text

    def _path(self, slot):
        return os.path.join(ARGS.saves, f"{slot}.qzl")

    def _save(self, slot):
        self.proc.stdin.write(b"save\n")
        self.proc.stdin.flush()
        text = self._read()
        if re.search(r":\s*$", text):
            if os.path.exists(self._path(slot)):
                os.remove(self._path(slot))    # no "overwrite?" question
            self.proc.stdin.write((self._path(slot) + "\n").encode())
            self.proc.stdin.flush()
            text += self._read()
        self.since_save = 0
        return text

    def _restore(self, slot):
        self.proc.stdin.write(b"restore\n")
        self.proc.stdin.flush()
        text = self._read()
        if re.search(r":\s*$", text):
            self.proc.stdin.write((self._path(slot) + "\n").encode())
            self.proc.stdin.flush()
            text += self._read()
        return text

    def ensure(self):
        if not self.alive():
            self.start()


game = Game()
mcp = FastMCP("zork")


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


@mcp.tool()
def zork_command(command: str) -> str:
    """Type one command into Zork, the way a player would: 'look', 'north',
    'open mailbox', 'take lamp', 'inventory', 'turn on lamp', 'attack troll
    with sword'. Short verb-noun commands work best. Returns what the game
    says back."""
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
            "(zork_restore), RESTART starts again.]" if game.over else "")
    return clean(reply) + hint


@mcp.tool()
def zork_status() -> str:
    """Where you are, what you're carrying, and the score, in one call
    (LOOK, INVENTORY and SCORE). Use it when you've lost track."""
    with game.lock:
        game.ensure()
        look = clean(game._send("look"))
        inv = clean(game._send("inventory"))
        score = clean(game._send("score"))
    text = f"{look}\n\n{inv}\n\n{score}"
    transcript(f"> look / inventory / score\n{text}")
    return text


@mcp.tool()
def zork_save(slot: str = "slot1") -> str:
    """Save the game to a named slot before something risky."""
    with game.lock:
        game.ensure()
        transcript(f"[saved to {_slot(slot)}]")
        return clean(game._save(_slot(slot)))


@mcp.tool()
def zork_restore(slot: str = AUTOSAVE) -> str:
    """Go back to a saved game. 'autosave' is the one kept every few moves."""
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


@mcp.tool()
def zork_restart() -> str:
    """Start a brand new game from the beginning (the autosave is dropped)."""
    with game.lock:
        game.stop()
        if os.path.exists(game._path(AUTOSAVE)):
            os.remove(game._path(AUTOSAVE))
        game.over = False
        return clean(game.start())


if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        game.stop()
