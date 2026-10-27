"""Stopping her: HOME, talking over her, a new message, Discord's !stop.

Each thing she does that can be stopped - a turn, a reminder, an alarm,
a line spoken on its own - gets a Stop of its own, opened when it's asked
for and closed when it ends. It has three switches:

    speaking     stop the audio (the reply still finishes on screen)
    generating   stop pulling tokens from the model
    listening    stop recording

Before this they were three module globals that every turn cleared when
it started. That had three faults:

- A HOME pressed just before a turn started was wiped by its own reset.
- One thread could clear another's stop: a reminder speaking cleared the
  stop on the reply you'd just interrupted.
- Loops slept between checks, so a stop landed up to a sleep late.

Now nothing is ever cleared. A new turn gets a new Stop, so an old stop
can't leak into it and it can't erase one meant for something else, and
the loops wait on the switch itself, so they wake the moment it's set.

    stop = interrupts.open("typed")     # HOME reaches it from here on,
    with interrupts.using(stop):        # even while it waits its turn
        ...                             # interrupts.current() is `stop`
                                        # closed when the block ends

HOME is home(): everything she's saying stops, and your own turn stops
entirely. Barge-in and "a new message cuts the old reply short" set one
Stop only, the reply's own.
"""
import contextvars
import threading
from contextlib import contextmanager


class Stop:
    """One stoppable thing's switches. Set, never cleared."""

    def __init__(self, kind="turn"):
        self.kind = kind
        self.speaking = threading.Event()
        self.generating = threading.Event()
        self.listening = threading.Event()
        self.barged_in = False      # you talked over her (voice/speech.py sets it)
        self.recording = False      # the mic is open for this turn

    def stop(self, speaking=True, generating=False, listening=False):
        if speaking:
            self.speaking.set()
        if generating:
            self.generating.set()
        if listening:
            self.listening.set()

    def __repr__(self):
        on = [n for n in ("speaking", "generating", "listening") if getattr(self, n).is_set()]
        return f"<Stop {self.kind} {'stopped: ' + ', '.join(on) if on else 'running'}>"


_lock = threading.Lock()
_open = []                                     # every Stop HOME can reach right now
_current = contextvars.ContextVar("luna_stop", default=None)


def open(kind="turn"):      # noqa: A001 - interrupts.open reads right
    """A new Stop, reachable by stop_all() from now until close()."""
    stop = Stop(kind)

    with _lock:
        _open.append(stop)

    return stop


def close(stop):
    with _lock:
        if stop in _open:
            _open.remove(stop)


@contextmanager
def using(stop=None, kind="turn"):
    """Run the block as `stop` (a new one if not given): current() is it,
    on this thread, and it's closed when the block ends."""
    stop = stop or open(kind)
    token = _current.set(stop)

    try:
        yield stop
    finally:
        _current.reset(token)
        close(stop)


@contextmanager
def ensure(kind="turn"):
    """The running Stop if there is one (a turn speaking an approval
    question), else a new one for the block."""
    stop = _current.get()

    if stop is not None:
        yield stop
        return

    with using(kind=kind) as stop:
        yield stop


def current():
    """The Stop for what's running on this thread. Outside anything
    stoppable, a fresh one that nothing will set."""
    return _current.get() or Stop("none")


# Your own turns: typed at the desk, or spoken.
YOURS = ("typed", "voice")


def stop_all(speaking=True, generating=True, listening=True, kinds=None):
    """Stop everything open (or only these kinds). Returns how many."""
    with _lock:
        stops = [s for s in _open if kinds is None or s.kind in kinds]

    for stop in stops:
        stop.stop(speaking=speaking, generating=generating, listening=listening)

    return len(stops)


def home():
    """HOME, or stopping hands-free: everything she's saying goes quiet,
    and your own turn stops entirely. Anything else she's working on (a
    stream-chat reply, a game step) still finishes on screen: stopping
    should cost the audio, never somebody else's answer."""
    stop_all(generating=False, listening=False)
    stop_all(kinds=YOURS)


def busy(kinds=YOURS):
    """Is one of your turns running? kinds: these kinds instead, None for
    anything at all (a reminder speaking, an alarm, a chat reply...)."""
    with _lock:
        return any(kinds is None or s.kind in kinds for s in _open)


def recording():
    """Is a turn's mic open right now?"""
    with _lock:
        return any(s.recording for s in _open)
