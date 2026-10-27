"""How her dials move on their own and from the shape of the session: the
baselines by hour, drifting home every turn, being away, the machine busy
while you were gone, stream chat, the day of the week, errors and the rest
of the small signals. Also reset, /mood set and start.

Part of mind/mood (see mind/mood/__init__.py).
"""
import threading
import time
from datetime import datetime
import config
from mind.mood.core import S, _away_lock, _ceiling, _clamp, _grudging, _intensity, _lock, _settle
from mind.mood import exchange, saving, show


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------
# Anchors, interpolated between. Deliberately not a tidy sine wave: the
# small hours are their own thing, awake but running down, and that is
# when this app gets used most.
_BY_HOUR = {
    0: 0.25, 2: 0.05, 4: -0.35, 6: -0.55, 8: -0.15,
    10: 0.20, 13: 0.30, 16: 0.35, 19: 0.45, 22: 0.40, 24: 0.25,
}


def _energy_baseline(now=None):
    now = now or datetime.now()
    hour = now.hour + now.minute / 60.0
    points = sorted(_BY_HOUR)

    for left, right in zip(points, points[1:]):
        if left <= hour <= right:
            span = right - left
            along = (hour - left) / span if span else 0

            return _BY_HOUR[left] + (_BY_HOUR[right] - _BY_HOUR[left]) * along

    return 0.0


def _warmth_baseline():
    """mood.warmth, pulled toward plain neutral as intensity drops: at 0
    she rests calm, not happy - the flat end has no fondness to show."""
    home = float(getattr(config, "MOOD_WARMTH", 0.45))

    return 0.1 + (home - 0.1) * min(1.0, _intensity())


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
def _nudge(energy=0.0, warmth=0.0, why=""):

    if not config.MOOD_ENABLED:
        return

    k = _intensity()

    with _lock:
        S.energy = _clamp(S.energy + energy * k)
        S.warmth = _clamp(S.warmth + warmth * k)
        _settle()

        if why:
            S.recent.append((why, time.time()))
            del S.recent[:-6]

    show._announce()


def note_turn():
    """One exchange finished. Applies the drift, then reads the tempo."""

    if not config.MOOD_ENABLED:
        return

    now = time.monotonic()

    with _lock:
        gap = None if S.last_turn is None else now - S.last_turn
        S.last_turn = now
        S.clean_run += 1

        # Drift home first, so every signal below is a nudge off
        # baseline rather than an argument with the last one.
        pull = max(0.0, min(1.0, float(getattr(config, "MOOD_RECOVERY", 0.25))))

        # Hours at the keyboard wear her down - capped, so a marathon
        # session bottoms out rather than going through the floor. This
        # belongs in the drift *target*, not as its own subtraction:
        # taken off every turn it compounded, and six hours in energy
        # pinned near -0.94 with nothing able to lift it again for the
        # rest of the session.
        hours = (now - S.started) / 3600.0
        drag = min(0.35, hours * 0.06)

        # Being fond of the company takes some of the edge off being
        # tired. Enough to move a cell, never enough to fake wide awake
        # at five in the morning.
        lift = max(0.0, S.warmth - _warmth_baseline()) * 0.5

        k = _intensity()
        target = _clamp((_energy_baseline() - drag + lift) * min(1.0, k))
        S.energy += (target - S.energy) * pull

        # Warmth drifts home asymmetrically. Coming back UP from a cold
        # patch is fast, because an assistant you have to coax out of a
        # sulk is a worse assistant. Coming back DOWN from warmth you
        # earned is slow, because otherwise the pull eats every kind
        # word on the turn after it lands - which is exactly what it was
        # doing: +0.045 of affection against -0.045 of drift, net zero.
        home = min(_warmth_baseline(), _ceiling()) if _grudging() else _warmth_baseline()
        S.warmth += (home - S.warmth) * (pull * 0.4 if S.warmth > home else pull)

        # Desire fades on its own: a little every turn, and halves for
        # every twenty minutes you were gone.
        S.desire = max(0.0, S.desire - exchange.DESIRE_FADE)
        if gap:
            S.desire *= 0.5 ** (gap / 1200.0)

        # A long stretch where nothing broke is its own small signal.
        # Only counted in runs of ten so it can't outpace the drift.
        if S.clean_run and S.clean_run % 10 == 0:
            S.warmth = _clamp(S.warmth + 0.05 * k)
            S.energy = _clamp(S.energy + 0.03 * k)
            S.recent.append(("it's been going smoothly", time.time()))

        if gap is not None:
            energy_delta, warmth_delta, why = _returning(gap)
            S.energy = _clamp(S.energy + energy_delta * k)
            S.warmth = _clamp(S.warmth + warmth_delta * k)

            if why:
                S.recent.append((why, time.time()))

        _settle()
        del S.recent[:-6]

    machine_energy, machine_warmth, machine_why = _machine_shape(gap)

    if machine_why or machine_energy or machine_warmth:
        _nudge(machine_energy, machine_warmth, why=machine_why)

    # Read off the world rather than the conversation - these are the
    # ones that still say something when nobody has typed for hours.
    _nudge(*_day_shape(), why="")
    _nudge(*_chat_shape())

    with _lock:
        del S.recent[:-6]

    saving._save()
    show._announce()


def _returning(gap):
    """(energy, warmth, why) for a gap of `gap` seconds since you spoke.

    The old version was a flat bump for anything over three hours, so
    back-after-lunch and back-after-a-week landed identically. Being
    away is most of how this assistant actually gets used, which makes
    it worth more than one branch.
    """
    hours = gap / 3600.0

    if hours < 25 / 3600:
        # Rapid back-and-forth reads as being in it together.
        return 0.06, 0.04, ""

    if hours < 0.5:
        return 0.0, 0.0, ""

    if hours < 3:
        return 0.05, 0.05, ""

    if hours < 9:
        return 0.15, 0.12, "you'd been gone a few hours"

    # Long enough that it's probably a night's sleep or a working day.
    # Overnight is a fresh start rather than a reunion, so the lift
    # goes to energy; a whole day away goes to warmth instead.
    if hours < 20:
        return 0.25, 0.12, "you'd been gone most of the day"

    if hours < 72:
        return 0.20, 0.28, "you'd been gone a day or more"

    return 0.15, 0.35, "you'd been gone for days"


# ---------------------------------------------------------------------------
# What happened while she was waiting
#
# Both of these read the world rather than the conversation, which is
# the only thing that still says anything when nobody has typed for
# hours. Both are wrapped and both degrade to "nothing happened": a
# mood is decoration and must never be the reason a turn fails.
# ---------------------------------------------------------------------------
def _sample_machine():
    """Note how hard the GPU is working. Called on a slow timer.

    A card pinned at 90% for six hours means you were *here* - gaming,
    rendering - just not talking to her. That is a different kind of
    absence from being out, and it is free to notice.
    """
    try:
        from core import machine

        cards = machine.gpus() or []
        busy = max((c.get("busy") or 0) for c in cards) if cards else 0
    except Exception:
        return

    with _lock:
        S.busy.append((time.time(), busy))
        # Four hours of samples is plenty to characterise an absence.
        cutoff = time.time() - 4 * 3600
        S.busy[:] = [(t, b) for t, b in S.busy if t >= cutoff][-240:]


def _machine_shape(gap):
    """(energy, warmth, why) for how busy the machine was while away."""
    if gap is None or gap < 1800:
        return 0.0, 0.0, ""

    since = time.time() - gap

    with _lock:
        window = [b for t, b in S.busy if t >= since]

    if len(window) < 3:
        return 0.0, 0.0, ""

    average = sum(window) / len(window)

    if average >= 55:
        # Around, but elsewhere. A touch livelier and a touch less fond.
        return 0.08, -0.05, "you were on the machine, just not here"

    if average <= 5:
        return 0.0, 0.03, ""

    return 0.0, 0.0, ""


def _chat_shape():
    """(energy, warmth) from stream chat, when a chat plugin is running.

    A busy room is company and a bit of performing; a dead one is a
    quiet night. Read off the counter the room already keeps, so this
    costs nothing and works for any chat plugin, not just pomf.
    """

    try:
        import plugins

        total = 0

        for name in plugins.names():
            plugin = plugins.get(name)

            if not (plugin and plugin.running()):
                continue

            room = getattr(plugin.module, "_room", None)
            total += getattr(room, "seen", 0) or 0
    except Exception:
        return 0.0, 0.0

    with _lock:
        fresh = max(0, total - S.chat_seen)
        S.chat_seen = total

    if fresh >= 12:
        return 0.10, 0.08
    if fresh >= 3:
        return 0.05, 0.04

    return 0.0, 0.0


def _day_shape():
    """A small shove from what day and hour it is.

    Friday evening and Monday morning are not the same person, and the
    clock is free. Deliberately small - it tilts the resting point
    rather than deciding anything.
    """
    now = datetime.now()
    weekend = now.weekday() >= 5
    energy = warmth = 0.0

    if weekend:
        warmth += 0.04            # less to be got through

    if now.weekday() == 4 and now.hour >= 17:
        energy += 0.05            # friday evening
    elif now.weekday() == 0 and now.hour < 11:
        energy -= 0.05            # monday morning
        warmth -= 0.02

    return energy, warmth


def note_error():
    """A turn that failed - a 500, a dead model, a tool that blew up.

    A run of them compounds: the third failure in a row lands harder
    than the first, which is both true to life and stops a single
    blip from mattering.
    """

    with _lock:
        streak = S.clean_run
        S.clean_run = 0

    steeper = 1.0 if streak > 2 else 1.6
    _nudge(energy=-0.12 * steeper, warmth=-0.06 * steeper,
           why="something went wrong" if streak > 2 else "that keeps failing")


def note_denied():
    """A write she asked for and didn't get."""
    _nudge(energy=-0.05, warmth=-0.04, why="a request was turned down")


def note_bargein():
    """Talked over mid-sentence. Once is nothing; a run of it isn't."""
    _nudge(energy=0.04, warmth=-0.07, why="you talked over her")


# Older name, still called by anything that knows an explicit thank-you.
def note_thanks():
    _nudge(warmth=0.12, why="you were kind about it")


def note_play(verdict, title="a game"):
    """A game session she's just finished, as she summed it up (mind/reflect.py):
    an enjoyed one lifts her a little, a frustrating one takes the shine
    off, a mixed one leaves her as she was."""
    if verdict == "enjoyed":
        _nudge(energy=0.10, warmth=0.06, why=f"enjoyed {title}")
    elif verdict == "frustrated":
        _nudge(energy=-0.08, warmth=-0.04, why=f"frustrated by {title}")


def set_mood(energy=None, warmth=None, desire=None, grudge_minutes=None):
    """Put her where you want her - /mood set, and tests."""

    with _lock:
        if energy is not None:
            S.energy = _clamp(float(energy))

        if warmth is not None:
            S.warmth = _clamp(float(warmth))

        if desire is not None:
            S.desire = max(0.0, min(1.0, float(desire)))

        if grudge_minutes is not None:
            S.grudge_until = time.time() + float(grudge_minutes) * 60 if grudge_minutes else 0.0
            _settle()

    show._announce()


def reset():
    """Back to baseline for the hour."""

    with _lock:
        S.energy = _energy_baseline()
        S.warmth = _warmth_baseline()
        S.desire = 0.0
        S.grudge_until = 0.0
        S.started = time.monotonic()
        S.clean_run = 0
        S.recent.clear()

    with _away_lock:
        S.away_state.update(until=0.0, said=False, hostile=0)
    saving._save()
    show._announce()


def _watch_machine(interval=120):
    """Sample the GPU every couple of minutes, for as long as we run.

    A thread rather than sampling on each turn, because the whole point
    is to know what happened during the hours when there were no turns.
    """
    while True:
        if config.MOOD_ENABLED:
            _sample_machine()

        time.sleep(interval)


def start():
    """Opening mood: where we left off, faded, or the clock."""

    with _lock:
        S.started = time.monotonic()
        S.clean_run = 0
        S.recent.clear()

    if not saving._restore():
        reset()

    _sample_machine()
    threading.Thread(target=_watch_machine, daemon=True).start()
    show._announce()
