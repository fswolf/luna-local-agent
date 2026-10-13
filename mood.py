"""What sort of shape she's in today.

The persona in agent.json is who she is; this is how she happens to be
feeling right now. It reaches the model as one line in the system
prompt and tints her voice slightly, and that is all. No rules about
how to behave: telling a 9B model to "act tired" gets you a
performance of tiredness in every sentence.

Two dials, both -1..+1:

    energy   tired ......... wired
    warmth   cross ......... fond

Two is enough for twelve distinguishable moods and few enough that every
signal has an obvious place to push. One dial can't tell "tired and
happy" from "awake and fed up", which are the two states that actually
turn up at 4am.

## Where it comes from

Almost all of it is the *shape* of the session, which is free and
turns out to be the more honest signal anyway:

    time of day        the baseline - 6am is not 9pm
    hours at it        a long session wears her down
    gap since you left away for hours, and she's brighter when you're back
    errors             a failed turn is dispiriting, a run of them more so
    a clean run        things going smoothly lifts her
    barge-in           being talked over, repeatedly, is wearing
    tempo              fast short turns read as engaged

plus one small model call after your turn that reads the exchange: how
warm you were, whether it livened her up or wore on her, and a quick
feeling (laughing, embarrassed...) that shows on her face for a moment.

## Three things learned the hard way

**It persists.** Moods that reset on restart aren't moods, they're
decoration - and this app gets restarted a lot. The dials are saved and
come back decayed by however long you were gone, so picking up after
five minutes resumes and picking up tomorrow doesn't.

**The label has hysteresis.** The bands sat close enough to the resting
point that a rounding-error nudge flipped her whole row, and the header
flickered between "warm" and "level" turn after turn. A label now has
to be clearly wrong before it changes.

**The wording varies.** The same sentence every turn is one a model
either stops seeing or starts performing. Each state has a few
phrasings and rotates when the state changes.

## What's data and what's code

The names, the lines she's told, her face, her voice and the idle moves
for each mood live in agent/moods.json, along with the quick feelings
the model can pick after a turn. Edit it and the next turn picks it up.
What stays in code is the engine and the rules below: those aren't a
matter of taste.

Two settings shape all of it: mood.intensity (0 = almost flat, the
ship's-computer end; 1 = as designed; 2 = wears her heart on her
sleeve) and mood.recovery (how fast she settles). mood.prompt,
mood.voice, mood.face and mood.gestures say where it shows.

## What it never does

Moods colour how she sounds, never how much she helps. There is no
state in which she is less useful, only states in which she is drier
about it - and an assistant you have to coax out of a sulk is a worse
assistant than one that never had moods.
"""
import json
import os
import re
import threading
import time
from datetime import datetime

import config
import logbook

from config import BASE_DIR

STATE_FILE = os.path.join(BASE_DIR, "agent", "mood.json")
MOODS_FILE = os.path.join(BASE_DIR, "agent", "moods.json")

_lock = threading.Lock()
_energy = 0.0
_warmth = 0.0
_started = time.monotonic()
_last_turn = None
_recent = []       # (what, when) - the last few nudges, for /mood
_busy = []         # (when, gpu %) while she waits - see _sample_machine
_chat_seen = 0     # chat messages counted at the last turn
_label = ""        # the current label, kept sticky
_phrasing = {}     # per state, which wording to use next time she's in it
_clean_run = 0     # turns since the last thing went wrong


def _clamp(value):
    return max(-1.0, min(1.0, value))


def _intensity():
    """mood.intensity: 0 flat .. 1 as designed .. 2 very visible."""
    try:
        return max(0.0, min(2.0, float(getattr(config, "MOOD_INTENSITY", 1.0))))
    except (TypeError, ValueError):
        return 1.0


# ---------------------------------------------------------------------------
# The moods file
# ---------------------------------------------------------------------------
# Used when agent/moods.json is missing or broken, so a typo in the file
# costs you your edits, never a working assistant. The shipped file is
# the real list; this is the smallest thing that still makes sense.
_FALLBACK = {
    "energy": {"edges": [-0.20, 0.35], "words": ["tired", "even", "wired"]},
    "warmth": {"edges": [-0.20, 0.35, 0.66], "words": ["cool", "neutral", "warm", "very warm"]},
    "grid": [["sad", "annoyed", "mad"], ["tired", "calm", "focused"],
             ["sleepy", "happy", "excited"], ["cuddly", "loving", "flirty"]],
    "states": {},
    "feelings": {},
}
_moods = {"data": None, "mtime": None, "error": ""}


def _check(data):
    """The file's shape, or a ValueError saying what's wrong with it."""
    energy, warmth = data.get("energy") or {}, data.get("warmth") or {}
    e_edges, w_edges = list(energy.get("edges") or []), list(warmth.get("edges") or [])
    grid = data.get("grid") or []

    if len(grid) != len(w_edges) + 1:
        raise ValueError(f"grid has {len(grid)} rows but warmth has {len(w_edges)} edges - "
                         "it needs one more row than edges")

    for row in grid:
        if len(row) != len(e_edges) + 1:
            raise ValueError(f"grid row {row} needs {len(e_edges) + 1} moods, one more "
                             "than energy has edges")

    if e_edges != sorted(e_edges) or w_edges != sorted(w_edges):
        raise ValueError("edges must go from low to high")

    data["energy"] = dict(energy, edges=e_edges)
    data["warmth"] = dict(warmth, edges=w_edges)
    data["states"] = data.get("states") or {}
    data["feelings"] = data.get("feelings") or {}

    return data


def moods():
    """agent/moods.json, re-read whenever it changes on disk."""
    try:
        mtime = os.path.getmtime(MOODS_FILE)
    except OSError:
        mtime = None

    if _moods["data"] is not None and mtime == _moods["mtime"]:
        return _moods["data"]

    _moods["mtime"] = mtime

    try:
        with open(MOODS_FILE, encoding="utf-8") as handle:
            _moods["data"] = _check(json.load(handle))
        _moods["error"] = ""
    except (OSError, ValueError) as e:
        if _moods["data"] is None:     # keep the last good copy if there is one
            _moods["data"] = _FALLBACK
        _moods["error"] = f"agent/moods.json: {e}"
        logbook.warn("mood", "%s - %s", _moods["error"],
                     "keeping the last good version" if _moods["data"] is not _FALLBACK
                     else "using the built-in names")

    return _moods["data"]


def _state(name):
    return (moods().get("states") or {}).get(name) or {}


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
    global _energy, _warmth

    if not config.MOOD_ENABLED:
        return

    k = _intensity()

    with _lock:
        _energy = _clamp(_energy + energy * k)
        _warmth = _clamp(_warmth + warmth * k)

        if why:
            _recent.append((why, time.time()))
            del _recent[:-6]

    _announce()


def note_turn():
    """One exchange finished. Applies the drift, then reads the tempo."""
    global _energy, _warmth, _last_turn, _clean_run

    if not config.MOOD_ENABLED:
        return

    now = time.monotonic()

    with _lock:
        gap = None if _last_turn is None else now - _last_turn
        _last_turn = now
        _clean_run += 1

        # Drift home first, so every signal below is a nudge off
        # baseline rather than an argument with the last one.
        pull = max(0.0, min(1.0, float(getattr(config, "MOOD_RECOVERY", 0.25))))

        # Hours at the keyboard wear her down - capped, so a marathon
        # session bottoms out rather than going through the floor. This
        # belongs in the drift *target*, not as its own subtraction:
        # taken off every turn it compounded, and six hours in energy
        # pinned near -0.94 with nothing able to lift it again for the
        # rest of the session.
        hours = (now - _started) / 3600.0
        drag = min(0.35, hours * 0.06)

        # Being fond of the company takes some of the edge off being
        # tired. Enough to move a cell, never enough to fake wide awake
        # at five in the morning.
        lift = max(0.0, _warmth - _warmth_baseline()) * 0.5

        k = _intensity()
        target = _clamp((_energy_baseline() - drag + lift) * min(1.0, k))
        _energy += (target - _energy) * pull

        # Warmth drifts home asymmetrically. Coming back UP from a cold
        # patch is fast, because an assistant you have to coax out of a
        # sulk is a worse assistant. Coming back DOWN from warmth you
        # earned is slow, because otherwise the pull eats every kind
        # word on the turn after it lands - which is exactly what it was
        # doing: +0.045 of affection against -0.045 of drift, net zero.
        home = _warmth_baseline()
        _warmth += (home - _warmth) * (pull * 0.4 if _warmth > home else pull)

        # A long stretch where nothing broke is its own small signal.
        # Only counted in runs of ten so it can't outpace the drift.
        if _clean_run and _clean_run % 10 == 0:
            _warmth = _clamp(_warmth + 0.05 * k)
            _energy = _clamp(_energy + 0.03 * k)
            _recent.append(("it's been going smoothly", time.time()))

        if gap is not None:
            energy_delta, warmth_delta, why = _returning(gap)
            _energy = _clamp(_energy + energy_delta * k)
            _warmth = _clamp(_warmth + warmth_delta * k)

            if why:
                _recent.append((why, time.time()))

        del _recent[:-6]

    machine_energy, machine_warmth, machine_why = _machine_shape(gap)

    if machine_why or machine_energy or machine_warmth:
        _nudge(machine_energy, machine_warmth, why=machine_why)

    # Read off the world rather than the conversation - these are the
    # ones that still say something when nobody has typed for hours.
    _nudge(*_day_shape(), why="")
    _nudge(*_chat_shape())

    with _lock:
        del _recent[:-6]

    _save()
    _announce()


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
        import machine

        cards = machine.gpus() or []
        busy = max((c.get("busy") or 0) for c in cards) if cards else 0
    except Exception:
        return

    with _lock:
        _busy.append((time.time(), busy))
        # Four hours of samples is plenty to characterise an absence.
        cutoff = time.time() - 4 * 3600
        _busy[:] = [(t, b) for t, b in _busy if t >= cutoff][-240:]


def _machine_shape(gap):
    """(energy, warmth, why) for how busy the machine was while away."""
    if gap is None or gap < 1800:
        return 0.0, 0.0, ""

    since = time.time() - gap

    with _lock:
        window = [b for t, b in _busy if t >= since]

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
    global _chat_seen

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
        fresh = max(0, total - _chat_seen)
        _chat_seen = total

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
    global _clean_run

    with _lock:
        streak = _clean_run
        _clean_run = 0

    steeper = 1.0 if streak > 2 else 1.6
    _nudge(energy=-0.12 * steeper, warmth=-0.06 * steeper,
           why="something went wrong" if streak > 2 else "that keeps failing")


def note_denied():
    """A write she asked for and didn't get."""
    _nudge(energy=-0.05, warmth=-0.04, why="a request was turned down")


def note_bargein():
    """Talked over mid-sentence. Once is nothing; a run of it isn't."""
    _nudge(energy=0.04, warmth=-0.07, why="you talked over her")


# ---------------------------------------------------------------------------
# Being nice to her
#
# The one signal that asks the model rather than reading the session,
# and the only one that costs anything. It started as a word list and
# that was the wrong shape for a project other people clone: the
# vocabulary of affection is personal. "good kitty" is one household's
# phrase, "awsome" is one person's spelling, and neither belongs baked
# into someone else's assistant. A model knows warmth in any wording
# and any language, which is the whole job.
#
# It reports a 0-3 rating of how warm the *user's message* was. Not the
# exchange - whether she was nice back is not the question.
#
# Nothing here darkens her. Bluntness rates 0 and 0 does nothing. An
# assistant that cools when you're terse is one you have to manage, and
# she drifts back to warm on her own regardless - you never have to be
# nice to her to get a pleasant assistant, it just registers when you
# are.
# ---------------------------------------------------------------------------
# These were an order of magnitude too small. At a resting warmth of
# +0.63 the drift pull takes -0.045 off every turn, and a rating of 2
# used to put +0.045 back: a clear compliment moved the dial by
# +0.0002 and the header never budged. A kind word should be worth
# more than one turn of drift, or the signal is decorative.
_RATING = {1: 0.08, 2: 0.18, 3: 0.30}

# The one model call moods make. It used to rate only how warm your
# message was; it now reads the whole exchange - your message and her
# answer - and returns four small things on one line, which a 9B model
# manages reliably where a free-form "how does she feel?" would not:
#
#   warmth of YOUR message, 0-3      the old rating, same rules
#   energy  - = +                    did the exchange liven her up or wear her down
#   warmth  - = +                    "-" only for real hostility: bluntness is not it
#   a feeling from moods.json        shown on her face for a few seconds
#
# Still one call, still off the turn's path, still off with
# mood.affection false.
_APPRAISE_PROMPT = (
    "Read this moment from a conversation between a user and his assistant, {name}.\n\n"
    "User: {said}\n{name}: {answer}\n\n"
    "Answer with one line of four fields separated by spaces, nothing else:\n"
    "1. how warm or affectionate the USER's message is toward her: 0 neutral, businesslike "
    "or blunt (swearing is not unfriendly by itself), 1 polite warmth (thanks, a friendly "
    "greeting), 2 clear affection or praise of her, 3 strong affection\n"
    "2. how the exchange leaves her energy: - (draining), = (no change), + (lively, fun)\n"
    "3. how it leaves her warmth toward him: - (only if he was clearly hostile or hurtful "
    "to her), =, +\n"
    "4. the one feeling she shows right now, from: none {feelings}\n"
    "When unsure: 0 = = none\n"
    "Example: 2 + + laughing"
)

_affection_recent = 0.0
_last_rating = None    # what the last message scored, for /mood
_last_feeling = None   # the last quick feeling, for /mood


def _appraise(said, answer, model):
    """(rating 0-3, energy -1/0/1, warmth -1/0/1, feeling or None).
    (0, 0, 0, None) on anything unexpected - a mood is never worth an error."""
    import requests

    from config import LM_URL, LLM_HEADERS

    feelings = list((moods().get("feelings") or {}).keys())

    try:
        import lmstudio

        name = getattr(config, "AGENT_NAME", "the assistant")
        prompt = _APPRAISE_PROMPT.format(name=name, said=str(said)[:600],
                                         answer=str(answer or "(no answer)")[:600],
                                         feelings=" ".join(feelings))
        response = requests.post(LM_URL, headers=LLM_HEADERS, json=lmstudio.chore({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }, max_tokens=200), timeout=30)
        reply = response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logbook.info("mood", "couldn't read the exchange: %s", e)

        return 0, 0, 0, None

    return _parse_appraisal(reply, feelings)


def _parse_appraisal(reply, feelings):
    # A reasoning model thinks out loud first; the answer is the last
    # line that has the right shape, not the first thing it mentions.
    reply = re.sub(r"<think>.*?</think>", "", str(reply or ""), flags=re.DOTALL)
    signs = {"-": -1, "=": 0, "+": 1}
    shape = re.compile(r"\b([0-3])\s+([-=+])\s+([-=+])\s+([A-Za-z_]+)")
    found = shape.findall(reply)

    if found:
        rating, energy, warmth, feeling = found[-1]
        feeling = feeling.lower()

        return (int(rating), signs[energy], signs[warmth],
                feeling if feeling in feelings else None)

    # A model that only managed the digit still gets its warmth counted.
    digits = re.findall(r"\b([0-3])\b", reply)

    return (int(digits[-1]) if digits else 0), 0, 0, None


def _apply_exchange(said, answer, model):
    global _affection_recent, _last_rating, _last_feeling

    rating, energy, warmth, feeling = _appraise(said, answer, model)

    with _lock:
        # Repeats fade: the fifth kind word in a row shouldn't land like
        # the first, which is both truer and stops the dial being a
        # button. Everything decays as turns pass, so affection spread
        # through a conversation keeps its value.
        #
        # The taper used to be 1/(1+n), which halved the second kind
        # word and quartered the fourth - so a conversation where you
        # were consistently warm registered less than a single stray
        # "thanks". It tapers now, it doesn't collapse.
        scaled = _RATING.get(rating, 0.0) / (1.0 + _affection_recent * 0.4)

        if rating >= 1:
            _affection_recent += 1.0

        _last_rating = rating
        _last_feeling = feeling

    if scaled:
        _nudge(energy=scaled * 0.45, warmth=scaled, why=f"you were warm with her ({rating})")

    # The exchange itself: small, and a cold one smaller than a warm one
    # - she bounces back from a rough moment on her own anyway.
    if energy or warmth:
        _nudge(energy=0.06 * energy, warmth=0.05 * warmth if warmth > 0 else 0.08 * warmth,
               why="that " + ("livened her up" if energy > 0 else "wore on her" if energy < 0
                              else "warmed her" if warmth > 0 else "stung a bit"))

    if feeling:
        _feel(feeling)


def _feel(feeling):
    """A quick feeling: on her face for a few seconds, a gesture if it has
    one, and a small push on the slow dials."""
    spec = (moods().get("feelings") or {}).get(feeling) or {}
    nudge = list(spec.get("nudge") or [0, 0]) + [0, 0]

    if nudge[0] or nudge[1]:
        _nudge(float(nudge[0]), float(nudge[1]))

    if not config.MOOD_ENABLED:
        return

    k = min(1.0, _intensity())

    if k <= 0:
        return

    try:
        import livefeed

        face = {f: round(float(v) * k, 3) for f, v in (spec.get("face") or {}).items()} \
            if getattr(config, "MOOD_FACE", True) else {}
        gesture = spec.get("gesture") if getattr(config, "MOOD_GESTURES", True) else None
        livefeed.emit("feeling", name=feeling, face=face, gesture=gesture or "",
                      seconds=float(spec.get("seconds", 6)))
    except Exception:
        pass


def note_exchange(said, answer, model=None):
    """Notice what that exchange did to her. Fire and forget.

    On a worker because it is a model call and a mood must never be
    something a turn waits for.
    """
    global _affection_recent

    with _lock:
        _affection_recent *= 0.6

    if not (config.MOOD_ENABLED and config.MOOD_AFFECTION and model):
        return

    if not str(said or "").strip():
        return

    threading.Thread(target=_apply_exchange, args=(said, answer, model),
                     daemon=True).start()


def note_affection(text, model=None):
    """Older name: just your message, no answer to read."""
    note_exchange(text, "", model)


def last_feeling():
    with _lock:
        return _last_feeling


# Older name, still called by anything that knows an explicit thank-you.
def note_thanks():
    _nudge(warmth=0.12, why="you were kind about it")


# ---------------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------------
# Hysteresis: a value has to clear the boundary by this much to change
# the band it's in. Without it the resting warmth sat a whisker above an
# edge and the header flickered between two labels every single turn.
_STICK = 0.07


def _band(value, edges, current=None):
    edges = list(edges)

    if current is not None:
        # Widen whichever band we are already in, so leaving one costs
        # more than staying in it. Band `current` sits between edge
        # `current - 1` below and edge `current` above: push every edge
        # at or above us up, and every edge below us down.
        for i, edge in enumerate(edges):
            edges[i] = edge + (_STICK if i >= current else -_STICK)

    for i, edge in enumerate(edges):
        if value < edge:
            return i

    return len(edges)


def _cell():
    """(label, phrasings) for where the dials are, sticky about changing."""
    global _label, _phrasing

    data = moods()
    grid = data["grid"]
    current_row = next((i for i, row in enumerate(grid) if _label in row), None)

    warmth_band = _band(_warmth, data["warmth"]["edges"], current_row)
    row = grid[warmth_band]
    energy_band = _band(_energy, data["energy"]["edges"],
                        row.index(_label) if _label in row else None)
    name = row[energy_band]
    phrases = list(_state(name).get("lines") or []) or [name]

    if name != _label:
        # Rotate on arrival, so a mood she returns to doesn't sound the
        # same twice running. A random pick would have been simpler and
        # is worse: it can hand you the same sentence five times, which
        # is exactly the staleness the phrasings exist to avoid.
        _label = name
        _phrasing[name] = _phrasing.get(name, -1) + 1

    return name, phrases[_phrasing.get(name, 0) % len(phrases)]


def label():
    """One word for the header: 'happy', 'mad'."""
    if not config.MOOD_ENABLED:
        return ""

    with _lock:
        return _cell()[0]


def _public(name):
    """A mood marked private never colours a stream or Discord turn: the
    nearest one in the same row that isn't, or the middle of the grid."""
    if not _state(name).get("private"):
        return name

    grid = moods()["grid"]

    for row in grid:
        if name in row:
            at = row.index(name)
            for other in sorted(row, key=lambda n: abs(row.index(n) - at)):
                if not _state(other).get("private"):
                    return other

    middle = grid[len(grid) // 2]
    return middle[len(middle) // 2]


def line(private=True):
    """The line that goes into the system prompt, or "" when off.

    Phrased as a state of affairs rather than an instruction. "You are
    tired, act tired" produces a model narrating its own tiredness;
    "right now you feel tired and glad of the company" colours the
    voice and then gets out of the way.
    """
    if not (config.MOOD_ENABLED and getattr(config, "MOOD_PROMPT", True)):
        return ""

    with _lock:
        name, described = _cell()

    if not private and _public(name) != name:
        lines = _state(_public(name)).get("lines") or [_public(name)]
        described = lines[0]

    return (
        f"\nRight now you feel {described}. Let that colour how you "
        "sound - length, warmth, how playful you are - and nothing "
        "else. Don't announce it or explain it unasked; if he asks how "
        "you are, answer honestly and briefly. Never let it make you "
        "less helpful or less careful.\n"
    )


def voice_tint():
    """(speed multiplier, pitch shift in semitones) for the TTS.

    Small on purpose. The point is that a sleepy Luna sounds a little
    slower, not that the voice audibly breaks - anything past a few
    percent reads as a misconfigured setting rather than a mood.
    """
    if not (config.MOOD_ENABLED and config.MOOD_VOICE):
        return 1.0, 0.0

    with _lock:
        energy = _energy
        name = _cell()[0]

    # The mood's own tint from moods.json if it has one, else a little
    # slower when tired and quicker when wired, straight off the dial.
    voice = _state(name).get("voice") or {}
    speed = float(voice.get("speed", 1.0 + 0.07 * energy)) - 1.0
    pitch = float(voice.get("pitch", 0.45 * energy))
    k = _intensity()

    return 1.0 + max(-0.07, min(0.07, speed * k)), max(-0.45, min(0.45, pitch * k))


def face():
    """What the portrait shows for the current mood, scaled by intensity."""
    if not (config.MOOD_ENABLED and getattr(config, "MOOD_FACE", True)):
        return {}

    with _lock:
        name = _cell()[0]

    k = min(1.0, _intensity())

    return {f: round(float(v) * k, 3) for f, v in (_state(name).get("face") or {}).items()}


def idle():
    """Gestures she drifts into now and then in this mood."""
    if not (config.MOOD_ENABLED and getattr(config, "MOOD_GESTURES", True)) or _intensity() <= 0:
        return []

    with _lock:
        name = _cell()[0]

    return [str(g) for g in (_state(name).get("idle") or [])]


def state():
    """(label, energy, warmth, [recent reasons]) for /mood."""
    with _lock:
        return (
            _cell()[0],
            round(_energy, 2),
            round(_warmth, 2),
            [why for why, _when in _recent[-4:]],
        )


def last_rating():
    """What the last message you sent scored, 0-3, or None.

    So "is the warmth sensing even firing?" is something you can look
    at rather than infer from a dial that barely moved.
    """
    with _lock:
        return _last_rating


def bands():
    """(energy word, warmth word) - which band each dial is sitting in.

    /mood printed bare numbers, which is no help: '+0.66' does not tell
    you whether being nice to her is landing. Knowing it reads as 'fond,
    one band short of the top' does.
    """
    data = moods()

    def word(dial, value):
        words = list(data[dial].get("words") or [])
        band = _band(value, data[dial]["edges"])
        return words[band] if band < len(words) else f"band {band + 1}"

    with _lock:
        return word("energy", _energy), word("warmth", _warmth)


def set_mood(energy=None, warmth=None):
    """Put her where you want her - /mood set, and tests."""
    global _energy, _warmth

    with _lock:
        if energy is not None:
            _energy = _clamp(float(energy))

        if warmth is not None:
            _warmth = _clamp(float(warmth))

    _announce()


def reset():
    """Back to baseline for the hour."""
    global _energy, _warmth, _started, _clean_run

    with _lock:
        _energy = _energy_baseline()
        _warmth = _warmth_baseline()
        _started = time.monotonic()
        _clean_run = 0
        _recent.clear()

    _save()
    _announce()


# ---------------------------------------------------------------------------
# Surviving a restart
# ---------------------------------------------------------------------------
def _save():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

        with open(STATE_FILE, "w") as handle:
            json.dump({"energy": round(_energy, 3),
                       "warmth": round(_warmth, 3),
                       "at": time.time()}, handle)
    except OSError:
        pass  # a mood is not worth failing a turn over


def _restore():
    """Pick up where we left off, faded by however long that was.

    Closing the app for five minutes shouldn't wipe the evening; closing
    it overnight shouldn't have last night's mood leak into the morning.
    So the saved dials are pulled toward today's baseline in proportion
    to the gap, and are gone entirely after about four hours.
    """
    global _energy, _warmth

    try:
        with open(STATE_FILE) as handle:
            saved = json.load(handle)

        away = max(0.0, time.time() - float(saved["at"]))
        faded = min(1.0, away / (4 * 3600))
        energy, warmth = float(saved["energy"]), float(saved["warmth"])
    except (OSError, ValueError, KeyError, TypeError):
        return False

    with _lock:
        _energy = _clamp(energy + (_energy_baseline() - energy) * faded)
        _warmth = _clamp(warmth + (_warmth_baseline() - warmth) * faded)

    logbook.info("mood", "restored after %.1f min away (%.0f%% faded)",
                 away / 60, faded * 100)

    return True


def portrait_state():
    """What the live monitor and the portrait get: the mood, the dials,
    its face and idle moves. With mood.face off she shows nothing - the
    dials go out as neutral so nothing else reads a mood off them."""
    name, energy, warmth, _why = state()
    show = config.MOOD_ENABLED and getattr(config, "MOOD_FACE", True) and _intensity() > 0

    return {"label": name, "energy": energy if show else 0.0,
            "warmth": warmth if show else 0.0, "face": face() if show else {}, "idle": idle()}


def _announce():
    try:
        import ui

        ui.set_mood(label())
    except Exception:
        pass  # headless, or the UI isn't up yet

    try:
        import livefeed

        livefeed.emit("mood", **portrait_state())
    except Exception:
        pass


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
    global _started, _clean_run

    with _lock:
        _started = time.monotonic()
        _clean_run = 0
        _recent.clear()

    if not _restore():
        reset()

    _sample_machine()
    threading.Thread(target=_watch_machine, daemon=True).start()
    _announce()
