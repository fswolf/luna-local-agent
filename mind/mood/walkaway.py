"""Walking away (mood.walk_away): treated badly enough for long enough, she
stops talking for a while, and comes back when the time is up or you make up.

Part of mind/mood (see mind/mood/__init__.py).
"""
import random
import threading
import time
import config
from core import logbook
from mind.mood.core import S, _away_lock, _lock, _walk, walk_away_on
from mind.mood import appraise, drift, exchange, show


# ---------------------------------------------------------------------------
# Walking away (mood.walk_away, on by default)
#
# Treated badly enough for long enough, she stops talking for a while:
# one short line the next time she's spoken to, then nothing. While
# she's away no turn reaches the model - stop words still stop toys
# (they're handled before any of this) and alarms and reminders still
# ring (they don't come through here at all). She comes back when the
# time is up, or sooner if what you say reads as making up, and she's
# cool with you for a while after either way.
#
# What counts as "badly" is the appraisal's own warmth reading: "-",
# which it gives only for real hostility, never for bluntness or
# swearing. A warm exchange clears the count; a neutral one leaves it;
# half an hour without another wipes it.
# ---------------------------------------------------------------------------


def away():
    """Seconds until she's talking again, or 0."""
    with _away_lock:
        until = S.away_state["until"]

    if not until:
        return 0

    if not walk_away_on():          # switched off mid-sulk: she's back
        _back("walking away was switched off")
        return 0

    left = until - time.time()

    if left <= 0:
        _back("enough time passed")
        return 0

    return left


def _count_hostility(rating, warmth):
    if not walk_away_on():
        return

    now = time.time()
    minutes = max(1.0, float(getattr(config, "MOOD_WALK_AWAY_MINUTES", 10)))

    with _away_lock:
        if S.away_state["until"]:
            return

        if now - S.away_state["last"] > 30 * 60:
            S.away_state["hostile"] = 0

        if warmth < 0:
            S.away_state.update(hostile=S.away_state["hostile"] + 1, last=now)
        elif warmth > 0 or rating >= 1:
            S.away_state["hostile"] = 0

        # Decided and claimed in one step, so two appraisals finishing
        # together can't both walk her out (two timers, two log lines).
        leaving = S.away_state["hostile"] >= max(1, int(getattr(config, "MOOD_WALK_AWAY_AFTER", 3)))

        if leaving:
            S.away_state.update(until=now + minutes * 60, said=False, hostile=0)

    if leaving:
        _withdraw(minutes)


def _withdraw(minutes):

    with _lock:
        S.warmth = min(S.warmth, -0.35)    # and cool with you when she's back
        S.desire = 0.0

    logbook.info("mood", "walked away for %.0f min", minutes)
    drift._nudge(why="walked away")

    # Come back on the minute, not whenever something next asks: the
    # portrait shouldn't sulk on for an hour because nobody spoke.
    timer = threading.Timer(minutes * 60 + 1, away)
    timer.daemon = True
    timer.start()


def _back(why):
    with _away_lock:
        if not S.away_state["until"]:
            return              # already back (the timer and a turn can both notice)

        S.away_state.update(until=0.0, said=False, hostile=0)

    logbook.info("mood", "back: %s", why)
    show._announce()


def leaving_line():
    """The one thing she says on her way out - the first time she's
    spoken to after walking away - then "" until she's back."""
    with _away_lock:
        if S.away_state["said"]:
            return ""

        S.away_state["said"] = True

    lines = [str(x) for x in (_walk().get("lines") or []) if str(x).strip()]

    return random.choice(lines) if lines else "I'm done talking for now."


def heard_while_away(text, model):
    """You spoke while she's away. If it reads as making up - warm, or
    warming - she comes back now and answers it. One small appraisal
    call, the same one every turn makes; no reply is generated."""
    if not str(text or "").strip() or not model:
        return False

    rating, _energy_, warmth, _feeling, _flirt = appraise._appraise(text, "", model)

    if warmth > 0 or rating >= 1:
        _back("that sounded like making up")
        if warmth > 0 or rating >= 2:       # a grudge wants a real apology, same as in _layers
            exchange._make_up("you made up")
        return True

    return False
