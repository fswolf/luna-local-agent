"""Her morning coffee.

Once a day, in the morning (portrait.coffee.from to .to, 5 to 11 by
default), the first time you're around she picks up her mug: the portrait
gets a "prop" event and plays coffee_pickup, and the mug (portrait/props/
mug.glb) appears in her hand. Every few minutes after that she takes a
sip (coffee_sip), and each sip wakes her up a little (portrait.coffee.wake,
a small nudge to her mood's energy). After portrait.coffee.minutes she's
finished it and puts the mug down (coffee_putdown).

"Around" means her portrait is open and you've talked to her in the last
few minutes, or presence sees you at the desk. A sip waits while she's
in the middle of a turn, so she never drinks over her own words. The day
it happened is kept in agent/coffee.json, so a restart doesn't pour her
a second cup.

Not in the lewd row: she doesn't start a cup while she's teasing, frisky
or heated (it waits until she's out of it, if it's still morning), and a
morning cup in her hand when she gets there goes down. One you asked for
with /coffee stays.
"""
import json
import os
import random
import threading
import time
from datetime import datetime

import config
from core import logbook

STATE_FILE = os.path.join(config.BASE_DIR, "agent", "coffee.json")
AROUND_SECONDS = 300          # talked to her this recently: you're here
FIRST_SIP = (25, 50)          # seconds after picking it up

_state = {"on": False, "since": 0.0, "sip_at": 0.0, "sips": 0, "thread": None}
_lock = threading.Lock()


def enabled():
    return bool(getattr(config, "PORTRAIT_COFFEE", True))


def morning(hour=None):
    """Is it coffee time?"""
    hour = datetime.now().hour if hour is None else hour
    lo = int(getattr(config, "PORTRAIT_COFFEE_FROM", 5))
    hi = int(getattr(config, "PORTRAIT_COFFEE_TO", 11))
    return lo <= hour < hi if lo <= hi else (hour >= lo or hour < hi)


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def had_today():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f).get("date") == _today()
    except (OSError, ValueError):
        return False


def _mark_today():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"date": _today()}, f)
    except OSError as e:
        logbook.warn("coffee", "couldn't note today's cup: %s", e)


def _someone_here():
    try:
        from senses import presence

        if presence.running():
            return presence.present()
    except Exception:
        pass
    try:
        from mind import reflect

        return reflect.idle_seconds() < AROUND_SECONDS
    except Exception:
        return False


def _watching():
    try:
        from web import livefeed

        return livefeed.watching()
    except Exception:
        return False


def _busy():
    try:
        from core import assistant

        return assistant.busy()
    except Exception:
        return False


def _lewd():
    """In the lewd row (teasing, frisky, heated)?"""
    try:
        from mind import mood

        return mood._row_of(mood.label()) == "lewd"
    except Exception:
        return False


def _walked_away():
    try:
        from mind import mood

        return bool(mood.away())
    except Exception:
        return False


def _reading():
    """Reading a book (life/reading.py)? Then the morning cup waits."""
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


def _next_sip(now):
    minutes = max(0.5, float(getattr(config, "PORTRAIT_COFFEE_SIP_MINUTES", 4)))
    return now + minutes * 60 * random.uniform(0.7, 1.3)


def begin(now=None, by_hand=True):
    """Pick up the mug (/coffee; the morning routine passes by_hand=False).
    False if she's already holding it."""
    now = time.monotonic() if now is None else now
    with _lock:
        if _state["on"]:
            return False
    if _reading():                                     # /coffee while she reads: the book goes down first
        from life import reading

        reading.finish(look_up=False)
    with _lock:
        _state.update(on=True, by_hand=by_hand, since=now, sips=0, sip_at=now + random.uniform(*FIRST_SIP))
    _mark_today()
    _emit("prop", name="mug", on=True)
    logbook.info("coffee", "she picked up her coffee")
    return True


def finish():
    """Put the mug down."""
    with _lock:
        if not _state["on"]:
            return False
        _state["on"] = False
    _emit("prop", name="mug", on=False)
    logbook.info("coffee", "she finished her coffee after %d sips", _state["sips"])
    return True


def sip(now=None):
    """One sip: the gesture, and a little more awake."""
    now = time.monotonic() if now is None else now
    with _lock:
        if not _state["on"]:
            return False
        _state["sips"] += 1
        _state["sip_at"] = _next_sip(now)
    _emit("gesture", name="coffee_sip", src="coffee")
    wake = float(getattr(config, "PORTRAIT_COFFEE_WAKE", 0.03))
    if wake:
        try:
            from mind import mood

            mood._nudge(energy=wake, why="a sip of coffee")
        except Exception:
            pass
    return True


def holding():
    return _state["on"]


def describe():
    """A line for her prompt (mind/situation.py) while she has her coffee, or ""."""
    if not _state["on"]:
        return ""
    sips = _state["sips"]
    return ("In your hands: your " + ("morning " if not _state.get("by_hand") else "") + "coffee in your mug"
            + (f", {sips} sip{'s' if sips != 1 else ''} in" if sips else ", just poured"))


def tick(now=None):
    """One look at the clock; the loop calls this every few seconds."""
    now = time.monotonic() if now is None else now

    if _state["on"]:
        minutes = float(getattr(config, "PORTRAIT_COFFEE_MINUTES", 40))
        if (now - _state["since"] >= minutes * 60 or _walked_away()             # walked off: always down
                or (_lewd() and not _state.get("by_hand"))):
            finish()
        elif now >= _state["sip_at"] and not _busy():
            sip(now)
        return

    if (enabled() and morning() and _watching() and not had_today() and _someone_here() and not _busy() and not _lewd()
            and not _reading() and not _walked_away()):
        begin(now, by_hand=False)


def _loop():
    while True:
        try:
            tick()
        except Exception as e:
            logbook.warn("coffee", "tick failed: %s", e)
        time.sleep(15)


def start():
    if _state["thread"] is None:
        # A restart forgets a cup in progress, so tell an open portrait the
        # mug is down: kept as the last prop event, a page that reconnects
        # puts it away instead of holding it all day.
        _emit("prop", name="mug", on=False)
        _state["thread"] = threading.Thread(target=_loop, daemon=True, name="coffee")
        _state["thread"].start()
