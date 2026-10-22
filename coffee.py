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
"""
import json
import os
import random
import threading
import time
from datetime import datetime

import config
import logbook

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
        with open(STATE_FILE) as f:
            return json.load(f).get("date") == _today()
    except (OSError, ValueError):
        return False


def _mark_today():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({"date": _today()}, f)
    except OSError as e:
        logbook.warn("coffee", "couldn't note today's cup: %s", e)


def _someone_here():
    try:
        import presence

        if presence.running():
            return presence.present()
    except Exception:
        pass
    try:
        import reflect

        return reflect.idle_seconds() < AROUND_SECONDS
    except Exception:
        return False


def _watching():
    try:
        import livefeed

        return livefeed.watching()
    except Exception:
        return False


def _busy():
    try:
        import assistant

        return assistant.busy()
    except Exception:
        return False


def _emit(kind, **data):
    try:
        import livefeed

        livefeed.emit(kind, **data)
    except Exception:
        pass


def _next_sip(now):
    minutes = max(0.5, float(getattr(config, "PORTRAIT_COFFEE_SIP_MINUTES", 4)))
    return now + minutes * 60 * random.uniform(0.7, 1.3)


def begin(now=None):
    """Pick up the mug (also /coffee). False if she's already holding it."""
    now = time.monotonic() if now is None else now
    with _lock:
        if _state["on"]:
            return False
        _state.update(on=True, since=now, sips=0, sip_at=now + random.uniform(*FIRST_SIP))
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
            import mood

            mood._nudge(energy=wake, why="a sip of coffee")
        except Exception:
            pass
    return True


def holding():
    return _state["on"]


def tick(now=None):
    """One look at the clock; the loop calls this every few seconds."""
    now = time.monotonic() if now is None else now

    if _state["on"]:
        minutes = float(getattr(config, "PORTRAIT_COFFEE_MINUTES", 40))
        if now - _state["since"] >= minutes * 60:
            finish()
        elif now >= _state["sip_at"] and not _busy():
            sip(now)
        return

    if (enabled() and morning() and _watching() and not had_today() and _someone_here() and not _busy()):
        begin(now)


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
