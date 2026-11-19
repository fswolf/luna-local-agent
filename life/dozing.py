"""She dozes off late at night when you've gone quiet.

Between portrait.dozing.from and .to (22 to 6 by default), when nobody has
talked to her for portrait.dozing.after minutes (20) and her portrait is
open, she settles (sleepy_lean), pulls her blanket round her shoulders
(portrait/props/blanket.glb, worn: portrait/viewer/props.js) and drifts off:
the portrait gets a "doze" event and closes her eyes, drops her head, slows
her breathing, nods now and then and floats a zzz off her head.

The moment a turn happens - you talk or type to her, or presence sees you
come back - she wakes with a start (wake_startle), stretches, and the
blanket comes off a few seconds later. After portrait.dozing.minutes she
wakes on her own, gently (no start).

If she's reading when it's time, she puts the book down without looking up
first: she fell asleep over it. Not while she's in the lewd or grudge row,
has walked away, or has her coffee. /doze starts it by hand, at any hour.
"""
import random
import threading
import time
from datetime import datetime

import config
from core import logbook

SETTLE = 3.0                  # seconds of sleepy_lean before her eyes close
STRETCH_AFTER = 2.0           # seconds: the start, then the stretch
BLANKET_OFF_AFTER = 9.0       # seconds after waking: the blanket comes off
RECENT = 15 * 60              # seconds she still remembers she dozed off

_state = {"on": False, "since": 0.0, "by_hand": False, "quiet_from": None, "spent": None,
          "away": False, "ended": None, "startled": False, "thread": None, "token": 0, "blanket": False}
_lock = threading.Lock()


def enabled():
    return bool(getattr(config, "PORTRAIT_DOZING", True))


def asleep():
    return _state["on"]


def night(hour=None):
    """Is it late enough to doze off?"""
    hour = datetime.now().hour if hour is None else hour
    lo = int(getattr(config, "PORTRAIT_DOZING_FROM", 22))
    hi = int(getattr(config, "PORTRAIT_DOZING_TO", 6))
    return lo <= hour < hi if lo <= hi else (hour >= lo or hour < hi)


# What's around her, the same questions life/reading.py asks
def _idle():
    from life import reading

    return reading._idle()


def _present():
    from life import reading

    return reading._present()


def _watching():
    from life import reading

    return reading._watching()


def _busy():
    from life import reading

    return reading._busy()


def _walked_away():
    from life import reading

    return reading._walked_away()


def _not_now():
    from life import reading

    return reading._not_now()


def _coffee():
    from life import reading

    return reading._coffee()


def _reading():
    try:
        from life import reading

        return reading.holding()
    except Exception:
        return False


def _emit(kind, **data):
    try:
        from web import livefeed

        livefeed.emit(kind, **data)
    except Exception:
        pass


def _blanket_on():
    """Is her blanket already on by hand (/blanket)? Then it stays when she wakes."""
    try:
        from commands import portrait

        return bool(portrait._blanket["on"])
    except Exception:
        return False


def _later(seconds, fn):
    t = threading.Timer(seconds, fn)
    t.daemon = True
    t.start()


def begin(now=None, by_hand=True):
    """She settles, pulls her blanket round her and drifts off (/doze; the
    routine passes by_hand=False). False if she's already asleep."""
    now = time.monotonic() if now is None else now
    with _lock:
        if _state["on"]:
            return False
        _state["token"] += 1
        token = _state["token"]
        _state.update(on=True, since=now, by_hand=by_hand, away=_present() is False, quiet_from=now - _idle())
    if _reading():                                     # fell asleep over her book: no look up
        from life import reading

        reading.finish(look_up=False)
    if _coffee():
        from life import coffee

        coffee.finish()
    _emit("gesture", name="sleepy_lean", src="dozing")
    _state["blanket"] = not _blanket_on()              # ours to take off again
    if _state["blanket"]:
        _emit("prop", name="blanket", on=True)
    # (unless you woke her in those few seconds)
    _later(SETTLE, lambda: _state["on"] and _state["token"] == token and _emit("doze", on=True))
    logbook.info("dozing", "she dozed off")
    return True


def wake(startle=True):
    """Wake her: a start (you woke her) or a gentle wake (she slept her fill),
    a stretch, then the blanket comes off."""
    with _lock:
        if not _state["on"]:
            return False
        _state["on"] = False
        _state["spent"] = _state["quiet_from"]         # this quiet stretch is used up
        _state["ended"], _state["startled"] = time.monotonic(), startle
        _state["token"] += 1
        token = _state["token"]
    _emit("doze", on=False)
    if startle:
        _emit("gesture", name="wake_startle", src="dozing")
    _later(STRETCH_AFTER if startle else 0.8, lambda: _state["token"] == token and _emit("gesture", name="stretch", src="dozing"))
    if _state["blanket"] and not _blanket_on():
        _later(BLANKET_OFF_AFTER, lambda: _state["token"] == token and _emit("prop", name="blanket", on=False))
    logbook.info("dozing", "she woke up")
    return True


def describe(now=None):
    """A line for her prompt (mind/situation.py): asleep, just woken, or ""."""
    now = time.monotonic() if now is None else now
    if _state["on"]:
        mins = int((now - _state["since"]) // 60)
        long = f"about {mins} minutes ago" if mins >= 2 else "just now"
        return (f"You dozed off {long}, wrapped in your blanket, it being late and quiet. He just spoke and "
                "woke you: you're groggy and blinking awake - you can say so, sleepily")
    if _state["ended"] is not None and now - _state["ended"] < RECENT:
        how = "when he woke you" if _state["startled"] else "on your own"
        return f"A little while ago you dozed off under your blanket; you woke {how}"
    return ""


def tick(now=None):
    """One look around; the loop calls this every few seconds."""
    now = time.monotonic() if now is None else now
    idle = _idle()

    if _state["on"]:
        here = _present()
        back = idle < now - _state["since"]                   # a turn since she dozed off
        if here and _state["away"]:
            back = True                                       # presence: you walked back in
        _state["away"] = _state["away"] or here is False
        minutes = float(getattr(config, "PORTRAIT_DOZING_MINUTES", 90))
        if back:
            wake(startle=True)
        elif (now - _state["since"] >= minutes * 60 or _walked_away()
              or (_not_now() and not _state["by_hand"])):
            wake(startle=False)
        return

    after = float(getattr(config, "PORTRAIT_DOZING_AFTER", 20)) * 60
    quiet_from = now - idle
    fresh = _state["spent"] is None or quiet_from > _state["spent"] + 1   # not the stretch she already slept through
    if (enabled() and night() and idle >= after and fresh and _watching() and not _busy() and not _not_now()
            and not _coffee()):
        begin(now, by_hand=False)


def _loop():
    while True:
        try:
            tick()
        except Exception as e:
            logbook.warn("dozing", "tick failed: %s", e)
        time.sleep(2 if _state["on"] else 15)          # asleep: wake quickly, before her reply's gestures


def start():
    if _state["thread"] is None:
        # a restart forgets she was asleep: an open portrait wakes her and takes the blanket off
        _emit("doze", on=False)
        _emit("prop", name="blanket", on=False)
        _state["thread"] = threading.Thread(target=_loop, daemon=True, name="dozing")
        _state["thread"].start()
