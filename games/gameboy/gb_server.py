"""A Game Boy as an MCP server: one game, through PyBoy, behind a few tools.

    python games/gameboy/gb_server.py --rom FILE [--saves DIR] [--window] [--sound]

Speaks MCP over stdio, so anything that talks MCP can play: Luna's gameboy
plugin starts it for her, but Claude Desktop or any other client works the
same way. The ROM is yours: nothing here ships or fetches one.

Tools:
    gb_press(buttons)   press buttons, like "a", "up 3", "down, down, a"; returns gb_look
    gb_wait(seconds)    let the game run (text scrolling, an animation), then gb_look
    gb_look()           what's going on: the game's state as text when there's a reader
                        for it (readers/), and the screen saved as screen.png
    gb_save(slot) / gb_load(slot)

Two ways to run. Headless (the default), the game only moves while a tool
runs: nothing happens while she thinks, which suits slow games. --window
opens the Game Boy screen and runs it in real time, to watch (and hear,
with --sound) as she plays; her presses are slipped in between frames.

The game autosaves (a full emulator snapshot) every few presses and when the
server stops, and picks it back up on the next start. The cartridge's own
battery save is PyBoy's <rom>.ram beside the ROM: put a save dumped from a
real cartridge there (rename .sav to <rom>.ram) and she carries on your game.

Every press and what came of it is appended to transcript.txt in the saves
folder, the way Zork's is.
"""
import argparse
import io
import os
import queue
import re
import sys
import threading
import time

try:
    from mcp.server.fastmcp import FastMCP          # mcp 1.x
except ImportError:
    from mcp.server.mcpserver import MCPServer as FastMCP   # mcp 2.x renamed it

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import readers  # noqa: E402

BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")
ALIASES = {"u": "up", "d": "down", "l": "left", "r": "right", "enter": "start", "ok": "a", "back": "b"}
HOLD, SETTLE = 10, 22           # frames a press is held, then left to play out (a walking step is 16)
MAX_PRESSES = 12                # per gb_press, so a turn can't be a blind run of thirty
MAX_WAIT = 10                   # seconds
AUTOSAVE_EVERY = 10             # presses

ap = argparse.ArgumentParser()
ap.add_argument("--rom", default="")
ap.add_argument("--saves", default=os.path.join(HERE, "saves"))
ap.add_argument("--window", action="store_true")
ap.add_argument("--sound", action="store_true")
ap.add_argument("--scale", type=int, default=4)
ARGS, _ = ap.parse_known_args()


def parse(spec):
    """'up 3, a, wait 2' -> [("up", 3), ("a", 1), ("wait", 2)]; ValueError on a word
    that isn't a button. Commas, spaces or "then" between presses; "x3" works too."""
    out = []
    text = re.sub(r"\s*[x*]\s*(\d+)", r" \1", str(spec or "").strip().lower())   # "up x3" = "up 3"
    words = re.split(r"\s*(?:,|;|\bthen\b|\band\b)\s*|\s+(?=[a-z])", text)
    for word in filter(None, (w.strip() for w in words)):
        m = re.fullmatch(r"([a-z]+)\s*(\d+)?", word)
        if not m:
            raise ValueError(f"not a button: {word!r}")
        name, count = m.group(1), int(m.group(2) or 1)
        name = ALIASES.get(name, name)
        if name == "wait":
            out.append(("wait", min(count, MAX_WAIT)))
            continue
        if name not in BUTTONS:
            raise ValueError(f"not a button: {name!r} (the buttons are {', '.join(BUTTONS)}, and wait N)")
        out.append((name, max(1, min(count, MAX_PRESSES))))
    if not out:
        raise ValueError("no buttons given")
    if sum(n for b, n in out if b != "wait") > MAX_PRESSES:
        raise ValueError(f"at most {MAX_PRESSES} presses at a time - press a few, then look")
    return out


class Console:
    """The emulator, on a thread of its own: every frame comes from here, so the
    window (when there is one) keeps running and her presses wait their turn."""

    def __init__(self, rom, saves, window=False, sound=False, scale=4):
        from pyboy import PyBoy

        self.saves = saves
        os.makedirs(saves, exist_ok=True)
        self.realtime = window
        self.pyboy = PyBoy(rom, window="SDL2" if window else "null", scale=scale,
                           sound_emulated=bool(window and sound), sound_volume=60 if sound else 0)
        self.pyboy.set_emulation_speed(1 if window else 0)
        self.title = (self.pyboy.cartridge_title or os.path.splitext(os.path.basename(rom))[0]).strip()
        self.reader = readers.find(self.title)
        self.jobs = queue.Queue()
        self.presses = 0
        self.alive = True
        if os.path.exists(self._slot("autosave")):
            try:
                with open(self._slot("autosave"), "rb") as f:
                    self.pyboy.load_state(f)
            except Exception:
                pass
        else:
            self._frames(60)          # past the first black frames
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # -- the emulator thread -------------------------------------------------
    def _frames(self, n):
        for i in range(n):
            if not self.pyboy.tick(1, i == n - 1):
                self.alive = False      # the window was closed
                return

    def _run(self):
        while self.alive:
            try:
                job = self.jobs.get(timeout=1 / 60 if self.realtime else None)
            except queue.Empty:
                self._frames(1)         # real time: the game keeps going between her moves
                continue
            fn, done = job
            try:
                done["result"] = fn()
            except Exception as e:      # reported back to the tool, never kills the thread
                done["error"] = e
            done["event"].set()

    def do(self, fn, timeout=120):
        done = {"event": threading.Event()}
        self.jobs.put((fn, done))
        if not done["event"].wait(timeout):
            raise TimeoutError("the emulator didn't answer")
        if "error" in done:
            raise done["error"]
        return done.get("result")

    # -- what the tools do (on the emulator thread) ----------------------------
    def press(self, steps):
        for name, count in steps:
            if name == "wait":
                self._frames(60 * count)
                continue
            for _ in range(count):
                self.pyboy.button_press(name)
                self._frames(HOLD)
                self.pyboy.button_release(name)
                self._frames(SETTLE)
                self.presses += 1
        if self.presses >= AUTOSAVE_EVERY:
            self.presses = 0
            self._save("autosave")

    def wait(self, seconds):
        self._frames(int(60 * max(0.1, min(float(seconds), MAX_WAIT))))

    def look(self):
        path = os.path.join(self.saves, "screen.png")
        image = self.pyboy.screen.image
        if image is not None:
            # three times the Game Boy's 160x144, pixels kept sharp: a vision model
            # makes far more of the little people at this size
            from PIL import Image

            image.convert("RGB").resize((160 * 3, 144 * 3), Image.NEAREST).save(path + ".tmp", "PNG")
            os.replace(path + ".tmp", path)
        state = ""
        if self.reader:
            try:
                state = self.reader.describe(self.pyboy.memory)
            except Exception as e:
                state = f"(the {self.reader.NAME} reader couldn't read this moment: {e})"
        return state, path

    def _slot(self, slot):
        return os.path.join(self.saves, re.sub(r"[^A-Za-z0-9_-]", "_", str(slot or "autosave"))[:40] + ".state")

    def _save(self, slot):
        buf = io.BytesIO()
        self.pyboy.save_state(buf)
        with open(self._slot(slot) + ".tmp", "wb") as f:
            f.write(buf.getvalue())
        os.replace(self._slot(slot) + ".tmp", self._slot(slot))

    def _load(self, slot):
        with open(self._slot(slot), "rb") as f:
            self.pyboy.load_state(f)
        self._frames(2)

    def stop(self):
        try:
            if self.alive and self.thread.is_alive():
                self.do(lambda: self._save("autosave"), timeout=10)
            else:
                self._save("autosave")      # the window was closed: the thread is done, save here
        except Exception:
            pass
        self.alive = False
        try:
            self.pyboy.stop(save=True)      # the cartridge's battery save, beside the ROM
        except Exception:
            pass


def _log(text):
    try:
        with open(os.path.join(ARGS.saves, "transcript.txt"), "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n\n")
    except OSError:
        pass


def _report(console):
    state, path = console.do(console.look)
    head = f"[{console.title}]"
    if state:
        return f"{head}\n{state}\n(the screen is saved as {path})"
    return (f"{head}\nNo reader for this game, so there's no text to go on: look at the screen "
            f"({path}).")


def build():
    if not ARGS.rom or not os.path.isfile(ARGS.rom):
        sys.exit(f"no Game Boy ROM at {ARGS.rom!r} (--rom FILE)")
    console = Console(ARGS.rom, ARGS.saves, ARGS.window, ARGS.sound, ARGS.scale)
    mcp = FastMCP("gameboy")

    @mcp.tool()
    def gb_press(buttons: str) -> str:
        """Press Game Boy buttons, then see what happened. buttons: one or more of a, b,
        start, select, up, down, left, right, with a count ("up 3") and "wait N" (seconds)
        between them, separated by commas: "down, down, a". At most 12 presses."""
        try:
            steps = parse(buttons)
        except ValueError as e:
            return f"Error: {e}"
        if not console.alive:
            return "Error: the Game Boy is off (its window was closed)"
        console.do(lambda: console.press(steps))
        out = _report(console)
        _log(f"> {buttons}\n{out}")
        return out

    @mcp.tool()
    def gb_wait(seconds: float = 2) -> str:
        """Let the game run without pressing anything (text scrolling, an animation,
        a battle playing out), up to 10 seconds, then see what happened."""
        console.do(lambda: console.wait(seconds))
        out = _report(console)
        _log(f"> (wait {seconds}s)\n{out}")
        return out

    @mcp.tool()
    def gb_look() -> str:
        """What's on the Game Boy right now, without pressing anything."""
        return _report(console)

    @mcp.tool()
    def gb_save(slot: str = "quick") -> str:
        """Save the whole game as it is right now to a named slot."""
        console.do(lambda: console._save(slot))
        return f"[saved to {slot}]"

    @mcp.tool()
    def gb_load(slot: str = "quick") -> str:
        """Go back to a slot saved with gb_save ("autosave" is the last automatic one)."""
        try:
            console.do(lambda: console._load(slot))
        except FileNotFoundError:
            return f"Error: there's no save called {slot}"
        out = _report(console)
        _log(f"[loaded {slot}]\n{out}")
        return f"[loaded {slot}]\n{out}"

    return mcp, console


if __name__ == "__main__":
    server, console = build()
    _log("=" * 60 + f"\n[{console.title} - {time.strftime('%Y-%m-%d %H:%M')}]")
    try:
        server.run()
    finally:
        console.stop()
