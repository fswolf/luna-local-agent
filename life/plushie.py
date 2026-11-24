"""Her plushie: Mochi, a little moon-cat she hugs when she's feeling low.

When her mood has been one of portrait.plushie.moods (sad, hurt, sulky by
default) for portrait.plushie.after seconds and her portrait is open, she
picks Mochi up and holds him close to her chest (plush_pickup;
portrait/props/plush.glb, made in portrait/source/props/plush/plush.blend).
Every minute or so she gives him a squeeze (plush_squeeze). Once the mood
has lifted for LET_GO seconds she sets him down (plush_putdown), or after
portrait.plushie.minutes at most, then waits COOLDOWN before reaching for
him again.

Not while she's holding her coffee or book (one thing in her hands at a
time), has walked away, or is asleep (she keeps him if she dozes off with
him). /plushie starts it by hand.
"""
import random
import threading
import time

import config
from core import logbook

NAME = "Mochi"
SQUEEZE_EVERY = (40, 90)      # seconds between squeezes
LET_GO = 20                   # seconds of a better mood before he goes down
COOLDOWN = 20 * 60            # seconds after setting him down before the next time
RECENT = 15 * 60              # seconds she still remembers holding him

_state = {"on": False, "since": 0.0, "next": 0.0, "by_hand": False, "low_since": None, "better_since": None,
          "ended": None, "thread": None}
_lock = threading.Lock()


def enabled():
    return bool(getattr(config, "PORTRAIT_PLUSHIE", True))


def holding():
    return _state["on"]


def _moods():
    return [str(m).lower() for m in (getattr(config, "PORTRAIT_PLUSHIE_MOODS", None) or ("sad", "hurt", "sulky"))]


def _mood():
    try:
        from mind import mood

        return (mood.label() or "").lower()
    except Exception:
        return ""


def _watching():
    from life import reading

    return reading._watching()


def _busy():
    from life import reading

    return reading._busy()


def _walked_away():
    from life import reading

    return reading._walked_away()


def _hands_full():
    """Her coffee or book in hand."""
    try:
        from life import coffee, reading

        return coffee.holding() or reading.holding()
    except Exception:
        return False


def _asleep():
    try:
        from life import dozing

        return dozing.asleep()
    except Exception:
        return False


def _emit(kind, /, **data):
    try:
        from web import livefeed

        livefeed.emit(kind, **data)
    except Exception:
        pass


def begin(now=None, by_hand=True):
    """She picks Mochi up (/plushie; the routine passes by_hand=False). False if she has him."""
    now = time.monotonic() if now is None else now
    with _lock:
        if _state["on"]:
            return False
        _state.update(on=True, since=now, by_hand=by_hand, better_since=None,
                      next=now + random.uniform(*SQUEEZE_EVERY))
    _emit("prop", name="plush", on=True)
    logbook.info("plushie", "she picked up %s", NAME)
    return True


def finish(now=None):
    """She sets him down."""
    with _lock:
        if not _state["on"]:
            return False
        _state["on"] = False
        _state["ended"] = time.monotonic() if now is None else now
    _emit("prop", name="plush", on=False)
    logbook.info("plushie", "she set %s down", NAME)
    return True


def squeeze():
    if not _state["on"]:
        return False
    _emit("gesture", name="plush_squeeze", src="plushie")
    return True


def describe(now=None):
    """A line for her prompt (mind/situation.py)."""
    now = time.monotonic() if now is None else now
    if _state["on"]:
        return (f"In your arms: {NAME}, your little moon-cat plushie, held close because you've been feeling low; "
                "mention him only if it fits")
    if _state["ended"] is not None and now - _state["ended"] < RECENT:
        return f"A little while ago you were hugging {NAME}, your moon-cat plushie; you've set him down since"
    return ""


def tick(now=None):
    """One look around; the loop calls this every few seconds."""
    now = time.monotonic() if now is None else now
    low = _mood() in _moods()
    if low:
        if _state["low_since"] is None:
            _state["low_since"] = now
    else:
        _state["low_since"] = None

    if _state["on"]:
        if low:
            _state["better_since"] = None
        elif _state["better_since"] is None:
            _state["better_since"] = now
        minutes = float(getattr(config, "PORTRAIT_PLUSHIE_MINUTES", 30))
        feeling_better = _state["better_since"] is not None and now - _state["better_since"] >= LET_GO
        if _asleep():
            return                                            # she keeps him while she sleeps
        if (feeling_better and not _state["by_hand"]) or now - _state["since"] >= minutes * 60 or _walked_away():
            finish(now)
        elif now >= _state["next"] and not _busy():
            squeeze()
            _state["next"] = now + random.uniform(*SQUEEZE_EVERY)
        return

    after = float(getattr(config, "PORTRAIT_PLUSHIE_AFTER", 60))
    rested = _state["ended"] is None or now - _state["ended"] >= COOLDOWN
    if (enabled() and low and now - _state["low_since"] >= after and rested and _watching() and not _busy()
            and not _hands_full() and not _walked_away() and not _asleep()):
        begin(now, by_hand=False)


def _loop():
    while True:
        try:
            tick()
        except Exception as e:
            logbook.warn("plushie", "tick failed: %s", e)
        time.sleep(5)


def start():
    if _state["thread"] is None:
        _emit("prop", name="plush", on=False)            # a restart forgets he was in her arms
        _state["thread"] = threading.Thread(target=_loop, daemon=True, name="plushie")
        _state["thread"].start()
