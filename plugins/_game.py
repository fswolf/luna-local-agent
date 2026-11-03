"""What every game plugin shares: the turn loop, settings, the system
line, guides, and turning a turn into a playlog entry and a memory.

Minecraft, Zork, Vibe City, REALITI and chess each used to carry their
own copy of all of this, and a fix to one (a time limit, a session that
didn't end) had to be made five times. A game now keeps only what makes
it that game: its prompt, its tools, its rules.

    from plugins import _game

    _loop = _game.Loop(NAME, _state, _step, playing=lambda: _state["playing"],
                       quiet=lambda: settings()["step_seconds"])
    _loop.start()    # in start(), once connected
    _loop.stop()     # in stop()

A helper for the game plugins (the leading underscore keeps the loader
from treating it as a plugin).
"""
import threading

import config
from core import logbook

# When a game's "web" is on: stuck on a puzzle or a recipe, she can look
# it up. If that means she reads a walkthrough and wins, she wins.
WEB_TOOLS = ["web_search", "research"]

ERROR_PAUSE = 30        # seconds after a failed turn, so a broken connection doesn't spin
MAX_FAILURES = 3        # failed turns in a row, then she stops and says why once


def settings(name, defaults):
    """The plugin's block from config.json over its defaults; keys it
    doesn't know are ignored."""
    s = dict(defaults)
    s.update({k: v for k, v in config.plugin_settings(name).items() if k in defaults})
    return s


def seconds(value, default, hi=3600):
    """A duration from the plugin's settings, safe to wait on: a typo,
    a negative number, NaN or 1e10 in config.json comes back as the
    default or inside 0..hi, never as an OverflowError in a turn."""
    from core import safe

    return safe.seconds(value, default, 0, hi)


def whole(value, default, lo=1, hi=100000):
    """A count from the settings (max_steps, max_rounds): a whole number
    in lo..hi, or the default when it isn't one."""
    from core import safe

    return safe.whole(value, default, lo, hi)


def turn_limit(value, default):
    """turn_seconds as respond_to_job's time_limit: None for no limit (0,
    or a negative number meant as "no limit"), else at most an hour. A
    negative one passed on would cut every turn off before it started."""
    from core import safe

    limit = safe.number(value, default, 0, 3600)
    return limit or None


def server_problem(server):
    """"" while the game's MCP server is connected, else why not."""
    try:
        from core import mcpclient

        if mcpclient.connected(server):
            return ""
        entry = getattr(mcpclient, "_servers", {}).get(server) or {}
        return str(entry.get("error") or "it stopped")
    except Exception as e:
        return str(e) or "it stopped"


def say(text):
    """A line in the conversation from the game ("paused after 60 turns")."""
    try:
        import ui

        ui.add_message("system", text)
    except Exception:
        pass


def session_over(name, state):
    """She stopped playing, so the session becomes one of her episodes.
    Mid-turn, the turn loop does it once that turn is recorded."""
    if not state.get("busy"):
        from plugins import _playlog

        _playlog.finished(name)


def record(name, title, turn, answer, exchanges=None, **playlog):
    """One turn into the day's playlog and her memory of the session.
    playlog: block / also for _playlog.write, lines for _playlog.remember."""
    from plugins import _playlog

    lines = playlog.pop("lines", None)
    _playlog.write(name, turn, answer, **playlog)
    _playlog.remember(name, title, answer, exchanges or (), lines=lines)


def guide_by_room(folder, here, on=True):
    """What her notes (agent/knowledge/<folder>/) say about the room she's
    in, found by its name, for a turn prompt; "" when off or nothing."""
    if not here or not on:
        return ""
    try:
        from mind import knowledge

        text = knowledge.about(folder, here)
    except Exception:
        return ""
    return f"What your guide (notes on the game you were given) says about {here}:\n{text}\n\n" if text else ""


def guide_by_topic(folder, query, intro="From your guide, on what you're working on"):
    """The passages in agent/knowledge/<folder>/ that best fit what she's
    doing, for a turn prompt; "" when there's no folder or nothing fits."""
    if not folder or not str(query or "").strip():
        return ""
    try:
        from mind import knowledge

        text = knowledge.guide(str(folder), query)
    except Exception:
        return ""
    return f"{intro}:\n{text}\n\n" if text else ""


class Loop:
    """The thread that takes her turns.

    Every couple of seconds (or at once on wake()): if playing() and no
    turn is running, and nobody has spoken for quiet() seconds (when
    given), it runs step(). A turn that raises is logged and the loop
    waits ERROR_PAUSE before the next. When she stops playing, or the
    plugin stops, the session is written up as an episode
    (session_over) - unless ends_session is False because the game does
    that itself (chess, when a game ends).

    state is the plugin's own dict: the loop keeps state["busy"] and
    state["error"] there, so status() and the plugin read them as before.
    after() runs once each turn is over, playing or not.

    Giving up: MAX_FAILURES failed turns in a row, or (with server given)
    the game's MCP server gone, and pause() is called (the plugin stops
    playing) and the reason is said once. Without that, a dead game got a
    "Job:" turn every few seconds until max_steps, each one about errors.
    title is the game's name in that line.
    """

    def __init__(self, name, state, step, playing, quiet=None, after=None, ends_session=True,
                 server=None, pause=None, title=None):
        self.name, self.state, self.step = name, state, step
        self.playing, self.quiet, self.after = playing, quiet, after
        self.ends_session = ends_session
        self.server, self.pause, self.title = server, pause, title or name
        self.failures = 0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        state.setdefault("busy", False)
        state.setdefault("error", "")

    def start(self):
        """Start taking turns (again). A loop from an earlier start keeps
        its own stop flag, so it can't come back to life alongside this one."""
        if self._thread and self._thread.is_alive() and not self._stop.is_set():
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop,), daemon=True, name=self.name)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def wake(self):
        """Check now rather than in up to two seconds (chess, after your move)."""
        self._wake.set()

    def stopped(self):
        return self._stop.is_set()

    def wait(self, seconds):
        """Sleep inside a turn, cut short if the plugin stops. True if it did."""
        return self._stop.wait(seconds)

    def _due(self):
        if self.state.get("busy") or not self.playing():
            return False
        if self.server:
            problem = server_problem(self.server)
            if problem:
                self._give_up(f"the game's server is gone ({problem[:150]}). "
                              f"/{self.name} off, then /{self.name} on to start it again.")
                return False
        if self.quiet is None:
            return True
        from mind import reflect

        return reflect.idle_seconds() >= seconds(self.quiet(), 20, hi=86400)

    def _give_up(self, why):
        """Stop playing and say why, once (the next play starts afresh)."""
        self.failures = 0
        self.state["error"] = why[:200]
        logbook.warn(self.name, "stopped playing: %s", why)
        if self.pause:
            try:
                self.pause()
            except Exception:
                logbook.exception(self.name, "pausing")
        else:
            self._stop.set()
        say(f"{self.title}: stopped playing - {why}")

    def _run(self, stop):
        while not stop.is_set():
            self._wake.wait(2)
            self._wake.clear()
            if stop.is_set():
                continue
            try:
                # A setting that isn't a number (step_seconds "20s") used
                # to end this thread here, silently, with "playing" on.
                if not self._due():
                    continue
            except Exception:
                logbook.exception(self.name, "checking for a turn")
                stop.wait(ERROR_PAUSE)
                continue
            self.state["busy"] = True
            try:
                self.step()
                self.failures = 0
            except Exception as e:
                self.state["error"] = str(e)[:200]
                logbook.exception(self.name, "turn failed")
                self.failures += 1
                if self.failures >= MAX_FAILURES:
                    self._give_up(f"{MAX_FAILURES} turns in a row failed ({str(e)[:150] or type(e).__name__}).")
                else:
                    stop.wait(ERROR_PAUSE)
            finally:
                self.state["busy"] = False
                if self.after:
                    try:
                        self.after()
                    except Exception:
                        logbook.exception(self.name, "after a turn")
                if self.ends_session and (stop.is_set() or not self.playing()):
                    from plugins import _playlog

                    _playlog.finished(self.name)   # she stopped: the session is over
