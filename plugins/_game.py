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
import logbook

# When a game's "web" is on: stuck on a puzzle or a recipe, she can look
# it up. If that means she reads a walkthrough and wins, she wins.
WEB_TOOLS = ["web_search", "research"]

ERROR_PAUSE = 30        # seconds after a failed turn, so a broken connection doesn't spin


def settings(name, defaults):
    """The plugin's block from config.json over its defaults; keys it
    doesn't know are ignored."""
    s = dict(defaults)
    s.update({k: v for k, v in config.plugin_settings(name).items() if k in defaults})
    return s


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
    """What her notes (luna-knowledge/<folder>/) say about the room she's
    in, found by its name, for a turn prompt; "" when off or nothing."""
    if not here or not on:
        return ""
    try:
        import knowledge

        text = knowledge.about(folder, here)
    except Exception:
        return ""
    return f"What your guide (notes on the game you were given) says about {here}:\n{text}\n\n" if text else ""


def guide_by_topic(folder, query, intro="From your guide, on what you're working on"):
    """The passages in luna-knowledge/<folder>/ that best fit what she's
    doing, for a turn prompt; "" when there's no folder or nothing fits."""
    if not folder or not str(query or "").strip():
        return ""
    try:
        import knowledge

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
    """

    def __init__(self, name, state, step, playing, quiet=None, after=None, ends_session=True):
        self.name, self.state, self.step = name, state, step
        self.playing, self.quiet, self.after = playing, quiet, after
        self.ends_session = ends_session
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
        if self.quiet is None:
            return True
        import reflect

        return reflect.idle_seconds() >= float(self.quiet() or 0)

    def _run(self, stop):
        while not stop.is_set():
            self._wake.wait(2)
            self._wake.clear()
            if stop.is_set() or not self._due():
                continue
            self.state["busy"] = True
            try:
                self.step()
            except Exception as e:
                self.state["error"] = str(e)[:200]
                logbook.exception(self.name, "turn failed")
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
