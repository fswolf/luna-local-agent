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

## Past the edges of the grid

Two rows sit outside the warmth bands, each with its own way in and out:

    lewd     very warm AND desire past moods.json lewd.enter. Desire
             (0..1) only builds while she's warm - flirting, intimacy,
             touch - fades turn by turn and while you're away, and is
             wiped by hostility or by warmth falling below warm.
    grudge   real hostility while she's already cool. Holds for
             grudge.minutes (another insult restarts it); warmth can't
             climb out until you make up (an apology, clear warmth) or
             the time runs out.

Both are rows of three like the grid, picked by energy.

## What it never does

Moods colour how she sounds, not whether things get done. Outside a
grudge there is no state in which she is less useful. In a grudge she
grumbles and may turn down what isn't urgent until you make up -
never alarms, reminders, safety or anything urgent - and the walk-away
(three strikes) is still the only thing that stops her talking.
"""
import json
import os
import random
import re
import threading
import time
from datetime import datetime

import config
from core import logbook

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
_desire = 0.0      # 0..1, the lewd row's dial: builds only while she's warm
_grudge_until = 0.0  # time.time() a grudge ends, or 0


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
    "lewd": {"row": ["teasing", "frisky", "heated"], "enter": 0.6},
    "grudge": {"row": ["sulky", "hurt", "furious"], "minutes": 20},
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

    for extra in ("lewd", "grudge"):
        row = (data.get(extra) or {}).get("row")
        if row is not None and len(row) != len(e_edges) + 1:
            raise ValueError(f"{extra}.row needs {len(e_edges) + 1} moods, one per energy band")

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


def preview_list():
    """Every mood, top to bottom (lewd, very warm ... cool, grudge), each with
    dials in the middle of its cell and its face, idle moves and emote, as the
    portrait gets them: for the debug viewer's mood menu."""
    m = moods()
    grid = m.get("grid") or []
    words = (m.get("warmth") or {}).get("words") or []

    def middle(edges, i, n):
        lo = edges[i - 1] if i > 0 else -1.0
        hi = edges[i] if i < len(edges) else 1.0
        if i == 0:
            lo = max(-1.0, hi - 0.6)
        if i == n - 1:
            hi = min(1.0, lo + 0.6)
        return round((lo + hi) / 2, 2)

    e_edges = (m.get("energy") or {}).get("edges") or [-0.2, 0.35]
    w_edges = (m.get("warmth") or {}).get("edges") or [-0.2, 0.35, 0.66]
    energies = [middle(e_edges, j, len(e_edges) + 1) for j in range(len(e_edges) + 1)]
    rows = [("lewd", _extra("lewd")["row"], 0.95, "lewd")]
    for i in range(len(grid) - 1, -1, -1):
        rows.append((words[i] if i < len(words) else f"row {i}", grid[i], middle(w_edges, i, len(grid)), ""))
    rows.append(("grudge", _extra("grudge")["row"], -0.6, "grudge"))

    out = []
    for group, names, warmth, row in rows:
        for j, name in enumerate(names):
            spec = _state(name)
            out.append({"name": name, "group": group, "row": row, "warmth": warmth,
                        "energy": energies[min(j, len(energies) - 1)],
                        "face": dict(spec.get("face") or {}), "idle": [str(g) for g in spec.get("idle") or []],
                        "emote": str(spec.get("emote") or "")})
    return out


def _extra(name):
    """moods.json lewd / grudge, falling back to the built-in names."""
    spec = dict(_FALLBACK[name])
    spec.update(moods().get(name) or {})
    return spec


def _grudging():
    """Seconds of grudge left, or 0. Caller holds _lock or doesn't care."""
    return max(0.0, _grudge_until - time.time()) if _grudge_until else 0.0


def _ceiling():
    """While she holds a grudge her warmth stays in the cool band."""
    return moods()["warmth"]["edges"][0] - 0.05


def _row_of(name):
    """'lewd' or 'grudge' if the mood is in one of those rows, else ''."""
    for row in ("lewd", "grudge"):
        if name in _extra(row)["row"]:
            return row
    return ""


def _warm_enough():
    """Desire only lives at warm and above."""
    edges = moods()["warmth"]["edges"]
    return _warmth >= edges[-2] if len(edges) >= 2 else _warmth > 0


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
        _settle()

        if why:
            _recent.append((why, time.time()))
            del _recent[:-6]

    _announce()


def _settle():
    """After any change: the grudge's ceiling, and desire dies below warm.
    Caller holds _lock."""
    global _warmth, _desire, _grudge_until

    if _grudge_until and not _grudging():
        _grudge_until = 0.0

    if _grudge_until:
        _warmth = min(_warmth, _ceiling())
        _desire = 0.0
    elif not _warm_enough():
        _desire = 0.0


def note_turn():
    """One exchange finished. Applies the drift, then reads the tempo."""
    global _energy, _warmth, _last_turn, _clean_run, _desire

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
        home = min(_warmth_baseline(), _ceiling()) if _grudging() else _warmth_baseline()
        _warmth += (home - _warmth) * (pull * 0.4 if _warmth > home else pull)

        # Desire fades on its own: a little every turn, and halves for
        # every twenty minutes you were gone.
        _desire = max(0.0, _desire - DESIRE_FADE)
        if gap:
            _desire *= 0.5 ** (gap / 1200.0)

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

        _settle()
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
        from core import machine

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
    "Read this moment from a conversation between {user} and {their} assistant, {name}.\n\n"
    "User: {said}\n{name}: {answer}\n\n"
    "Answer with one line of four fields separated by spaces, nothing else:\n"
    "1. how warm or affectionate the USER's message is toward her: 0 neutral, businesslike "
    "or blunt (swearing is not unfriendly by itself), 1 polite warmth (thanks, a friendly "
    "greeting), 2 clear affection or praise of her, 3 strong affection\n"
    "2. how the exchange leaves her energy: - (draining), = (no change), + (lively, fun)\n"
    "3. how it leaves her warmth toward {them}: - (only if the user was clearly hostile or hurtful "
    "to her), =, +\n"
    "4. the one feeling she shows right now, from: none {feelings}\n"
    "5. how flirtatious or intimate the USER's message is: 0 not at all, 1 flirting or "
    "suggestive, 2 openly intimate or sexual\n"
    "When unsure: 0 = = none 0\n"
    "Example: 2 + + laughing 1"
)

# The lewd row's dial. Desire builds from flirting while she's warm,
# fades a little every turn, and one hostile exchange wipes it: quick to
# warm up, quicker to kill.
DESIRE_FLIRT = {1: 0.12, 2: 0.22}   # per flirtatious message (field 5)
DESIRE_AFFECTION = 0.04            # a clearly affectionate message adds a little
DESIRE_FADE = 0.02                 # every turn
HOSTILE_HIT = 0.27                 # warmth, on top of the exchange's own -0.08

_affection_recent = 0.0
_last_rating = None    # what the last message scored, for /mood
_last_feeling = None   # the last quick feeling, for /mood


def _appraise(said, answer, model):
    """(rating 0-3, energy -1/0/1, warmth -1/0/1, feeling or None, flirt 0-2).
    (0, 0, 0, None, 0) on anything unexpected - a mood is never worth an error."""
    import requests

    from config import LM_URL, LLM_HEADERS

    feelings = list((moods().get("feelings") or {}).keys())

    try:
        from core import lmstudio

        name = getattr(config, "AGENT_NAME", "the assistant")
        prompt = _APPRAISE_PROMPT.format(name=name, said=str(said)[:600],
                                         user=getattr(config, "USER", "the user"),
                                         them=getattr(config, "USER_THEM", "them"),
                                         their=getattr(config, "USER_THEIR", "their"),
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

        return 0, 0, 0, None, 0

    return _parse_appraisal(reply, feelings)


def _parse_appraisal(reply, feelings):
    # A reasoning model thinks out loud first; the answer is the last
    # line that has the right shape, not the first thing it mentions.
    reply = re.sub(r"<think>.*?</think>", "", str(reply or ""), flags=re.DOTALL)
    signs = {"-": -1, "=": 0, "+": 1}
    shape = re.compile(r"\b([0-3])\s+([-=+])\s+([-=+])\s+([A-Za-z_]+)(?:\s+([0-2])\b)?")
    found = shape.findall(reply)

    if found:
        rating, energy, warmth, feeling, flirt = found[-1]
        feeling = feeling.lower()

        return (int(rating), signs[energy], signs[warmth],
                feeling if feeling in feelings else None, int(flirt or 0))

    # A model that only managed the digit still gets its warmth counted.
    digits = re.findall(r"\b([0-3])\b", reply)

    return (int(digits[-1]) if digits else 0), 0, 0, None, 0


def _apply_exchange(said, answer, model):
    global _affection_recent, _last_rating, _last_feeling

    rating, energy, warmth, feeling, flirt = _appraise(said, answer, model)

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

    _layers(rating, warmth, flirt)
    _compliment(rating, feeling)
    _count_hostility(rating, warmth)


def _layers(rating, warmth, flirt):
    """Desire and the grudge, from one appraised exchange."""
    global _desire, _grudge_until

    if warmth < 0:
        # Hostile: desire gone at once, a real dent in warmth, and if
        # that leaves her cool, a grudge (another insult restarts it).
        with _lock:
            _desire = 0.0
        _nudge(warmth=-HOSTILE_HIT, why="that was hostile")

        with _lock:
            cool = _warmth < moods()["warmth"]["edges"][0]
            if cool or _grudging():
                minutes = float(_extra("grudge").get("minutes", 20))
                started = not _grudging()
                _grudge_until = time.time() + minutes * 60
                _settle()
            else:
                started = None
        if started is not None:
            logbook.info("mood", "grudge %s (%.0f min)", "started" if started else "restarted", minutes)
            _nudge(why="holding a grudge")
        return

    with _lock:
        if _grudging():
            # Making up: an apology or clear warmth ends it here and now.
            if rating >= 2 or warmth > 0:
                made_up = True          # _make_up clears it, outside the lock
            else:
                return
        else:
            made_up = False
            gain = DESIRE_FLIRT.get(flirt, 0.0) + (DESIRE_AFFECTION if rating >= 2 else 0.0)

            if gain and _warm_enough():
                _desire = min(1.0, _desire + gain / (1.0 + _affection_recent * 0.2))
            else:
                gain = 0.0

    if made_up:
        _make_up("you made up")
    elif gain:
        _announce()


def _make_up(why):
    """An apology landed: the grudge is over and she softens a little."""
    global _grudge_until

    with _lock:
        if not _grudge_until:
            return
        _grudge_until = 0.0

    logbook.info("mood", "grudge over: %s", why)
    _nudge(warmth=0.10, why=why)


def _emote(name, sulking=False):
    """An emote name the portrait may show, or "" when emotes are off.
    While she's walked away only the sulk's own (walk_away.emote) shows:
    no hearts or question marks mid-sulk."""
    if not (config.MOOD_ENABLED and getattr(config, "MOOD_EMOTES", True)) or _intensity() <= 0:
        return ""

    if away() and not sulking:
        return ""

    return str(name or "")


def _compliment(rating, feeling):
    """A clear compliment (moods.json "compliment": its rating and up)
    shows its emote, unless the feeling it raised already shows one."""
    spec = moods().get("compliment") or {}
    name = _emote(spec.get("emote"))

    if not name or rating < int(spec.get("rating", 2)):
        return

    if feeling and ((moods().get("feelings") or {}).get(feeling) or {}).get("emote"):
        return

    try:
        from web import livefeed

        livefeed.emit("emote", name=name)
    except Exception:
        pass


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
        from web import livefeed

        face = {f: round(float(v) * k, 3) for f, v in (spec.get("face") or {}).items()} \
            if getattr(config, "MOOD_FACE", True) else {}
        gesture = spec.get("gesture") if getattr(config, "MOOD_GESTURES", True) else None
        livefeed.emit("feeling", name=feeling, face=face, gesture=gesture or "",
                      emote=_emote(spec.get("emote")), seconds=float(spec.get("seconds", 6)))
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


# Spanks (the portrait, in her top two rows): fun up to a point, then a
# punishment, tamagotchi style. Each one counts; they're forgotten one every
# SPANK_FORGET seconds; every SPANK_LIMIT knocks her down a notch - warmth and
# desire - so keeping at it takes her out of the mood.
SPANK_LIMIT = 60
SPANK_FORGET = 10.0
SPANK_WARMTH = -0.10
SPANK_DESIRE = -0.20
_spanks = {"n": 0.0, "at": 0.0}


def note_spank():
    """One spank on the portrait. True if it was one too many (a notch down)."""
    global _desire

    if not config.MOOD_ENABLED:
        return False

    now = time.time()

    with _lock:
        before = max(0.0, _spanks["n"] - (now - _spanks["at"]) / SPANK_FORGET) if _spanks["at"] else 0.0
        _spanks.update(n=before + 1.0, at=now)
        over = int(_spanks["n"] // SPANK_LIMIT) > int(before // SPANK_LIMIT)
        if over:
            _desire = max(0.0, _desire + SPANK_DESIRE)

    if over:
        logbook.info("mood", "spanked %d times: a notch down", int(_spanks["n"]))
        _nudge(warmth=SPANK_WARMTH, energy=-0.03, why="too many spanks")

    return over


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

    lewd, grudge = _extra("lewd"), _extra("grudge")
    if _label in lewd["row"]:
        current_row = len(grid) - 1        # lewd sits on very warm: keep that band sticky
    elif _label in grudge["row"]:
        current_row = 0

    warmth_band = _band(_warmth, data["warmth"]["edges"], current_row)
    row = grid[warmth_band]

    if _grudging():
        row = list(grudge["row"])
    elif warmth_band == len(grid) - 1:
        enter = float(lewd.get("enter", 0.6))
        if _desire >= enter or (_label in lewd["row"] and _desire >= enter - 0.1):
            row = list(lewd["row"])

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


# Plugins live somewhere lewd isn't allowed (twitch, youtube with
# "lewd": false). While any is, the lewd row shows as the row below it -
# teasing / frisky / heated as cuddly / loving / flirty - in her face,
# idles, voice, portrait and mood line. The dials and desire keep going
# underneath, so she's back where she was when the stream ends.
_tame = set()


def set_tame(source, on):
    """A plugin saying lewd is (not) allowed where it's live."""
    with _lock:
        (_tame.add if on else _tame.discard)(source)

    _announce()


def tame():
    """The plugins holding the lewd row back right now, or an empty list."""
    return sorted(_tame)


def _view():
    """_cell(), as she shows it: the lewd row stepped down while tame."""
    name, described = _cell()
    lewd = _extra("lewd")["row"]

    if _tame and name in lewd:
        name = moods()["grid"][-1][lewd.index(name)]
        described = (_state(name).get("lines") or [name])[0]

    return name, described


def label():
    """One word for the header: 'happy', 'mad'."""
    if not config.MOOD_ENABLED:
        return ""

    if away():
        return str(_walk().get("label") or "withdrawn")

    with _lock:
        return _view()[0]


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

    # Walked away: the only turns that get here are the ones that ring on
    # their own - an alarm, a reminder. She delivers them, in character.
    if away():
        said = str(_walk().get("prompt") or "").strip()

        if said:
            return f"\n{said}\n"

    with _lock:
        name, described = _view()

    if not private and _public(name) != name:
        lines = _state(_public(name)).get("lines") or [_public(name)]
        described = lines[0]

    user = getattr(config, "USER", "the user")

    row = _row_of(name)

    if row == "grudge":
        return (
            f"\nRight now you feel {described}: {user} was hostile and hasn't made up, and you're "
            "holding a grudge. Let it show - short, prickly, not warm. Grumble at requests; you "
            "may refuse what isn't urgent until you get an apology, but alarms, reminders, safety "
            "and anything urgent always get done. A real apology ends it: let it go.\n"
        )

    if row == "lewd":
        return (
            f"\nRight now you feel {described}. Let that colour how you sound and what you're "
            f"in the mood for. Don't announce it unasked. Practical requests still get done.\n"
        )

    not_now = ("" if name in moods()["grid"][-1] else
               " Pushed for sex or intimate roleplay now, you're not in the mood: say so your "
               "own way and hint at what would change that. No lecture.")

    return (
        f"\nRight now you feel {described}. Let that colour how you "
        "sound - length, warmth, how playful you are - and nothing "
        f"else. Don't announce it or explain it unasked; if {user} asks how "
        "you are, answer honestly and briefly. Never let it make you "
        f"less helpful or less careful.{not_now}\n"
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
        name = _view()[0]

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
        name = _view()[0]

    k = min(1.0, _intensity())

    return {f: round(float(v) * k, 3) for f, v in (_state(name).get("face") or {}).items()}


def idle():
    """Gestures she drifts into now and then in this mood."""
    if not (config.MOOD_ENABLED and getattr(config, "MOOD_GESTURES", True)) or _intensity() <= 0:
        return []

    with _lock:
        name = _view()[0]

    return [str(g) for g in (_state(name).get("idle") or [])]


def emote():
    """An emote this mood shows now and then (loving, flirty: hearts)."""
    with _lock:
        name = _view()[0]

    return _emote(_state(name).get("emote"))


def state():
    """(label, energy, warmth, [recent reasons]) for /mood."""
    with _lock:
        return (
            _view()[0],
            round(_energy, 2),
            round(_warmth, 2),
            [why for why, _when in _recent[-4:]],
        )


def layers():
    """{"desire": 0..1, "grudge": seconds left} for /mood and tests."""
    with _lock:
        return {"desire": round(_desire, 2), "grudge": round(_grudging())}


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
        row = _row_of(_view()[0])
        return word("energy", _energy), row or word("warmth", _warmth)


def set_mood(energy=None, warmth=None, desire=None, grudge_minutes=None):
    """Put her where you want her - /mood set, and tests."""
    global _energy, _warmth, _desire, _grudge_until

    with _lock:
        if energy is not None:
            _energy = _clamp(float(energy))

        if warmth is not None:
            _warmth = _clamp(float(warmth))

        if desire is not None:
            _desire = max(0.0, min(1.0, float(desire)))

        if grudge_minutes is not None:
            _grudge_until = time.time() + float(grudge_minutes) * 60 if grudge_minutes else 0.0
            _settle()

    _announce()


def reset():
    """Back to baseline for the hour."""
    global _energy, _warmth, _started, _clean_run, _desire, _grudge_until

    with _lock:
        _energy = _energy_baseline()
        _warmth = _warmth_baseline()
        _desire = 0.0
        _grudge_until = 0.0
        _started = time.monotonic()
        _clean_run = 0
        _recent.clear()

    with _away_lock:
        _away.update(until=0.0, said=False, hostile=0)
    _save()
    _announce()


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
_away = {"until": 0.0, "said": False, "hostile": 0, "last": 0.0}

# Its own lock: it's touched from the appraisal worker (one per turn, so
# two can finish together), the come-back timer and the turn itself.
# Nothing slow or re-entrant (logging, _announce) runs while it's held.
_away_lock = threading.Lock()


def _walk():
    return moods().get("walk_away") or {}


def walk_away_on():
    return bool(config.MOOD_ENABLED and getattr(config, "MOOD_WALK_AWAY", True))


def away():
    """Seconds until she's talking again, or 0."""
    with _away_lock:
        until = _away["until"]

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
        if _away["until"]:
            return

        if now - _away["last"] > 30 * 60:
            _away["hostile"] = 0

        if warmth < 0:
            _away.update(hostile=_away["hostile"] + 1, last=now)
        elif warmth > 0 or rating >= 1:
            _away["hostile"] = 0

        # Decided and claimed in one step, so two appraisals finishing
        # together can't both walk her out (two timers, two log lines).
        leaving = _away["hostile"] >= max(1, int(getattr(config, "MOOD_WALK_AWAY_AFTER", 3)))

        if leaving:
            _away.update(until=now + minutes * 60, said=False, hostile=0)

    if leaving:
        _withdraw(minutes)


def _withdraw(minutes):
    global _warmth, _desire

    with _lock:
        _warmth = min(_warmth, -0.35)    # and cool with you when she's back
        _desire = 0.0

    logbook.info("mood", "walked away for %.0f min", minutes)
    _nudge(why="walked away")

    # Come back on the minute, not whenever something next asks: the
    # portrait shouldn't sulk on for an hour because nobody spoke.
    timer = threading.Timer(minutes * 60 + 1, away)
    timer.daemon = True
    timer.start()


def _back(why):
    with _away_lock:
        if not _away["until"]:
            return              # already back (the timer and a turn can both notice)

        _away.update(until=0.0, said=False, hostile=0)

    logbook.info("mood", "back: %s", why)
    _announce()


def leaving_line():
    """The one thing she says on her way out - the first time she's
    spoken to after walking away - then "" until she's back."""
    with _away_lock:
        if _away["said"]:
            return ""

        _away["said"] = True

    lines = [str(x) for x in (_walk().get("lines") or []) if str(x).strip()]

    return random.choice(lines) if lines else "I'm done talking for now."


def heard_while_away(text, model):
    """You spoke while she's away. If it reads as making up - warm, or
    warming - she comes back now and answers it. One small appraisal
    call, the same one every turn makes; no reply is generated."""
    if not str(text or "").strip() or not model:
        return False

    rating, _energy_, warmth, _feeling, _flirt = _appraise(text, "", model)

    if warmth > 0 or rating >= 1:
        _back("that sounded like making up")
        if warmth > 0 or rating >= 2:       # a grudge wants a real apology, same as in _layers
            _make_up("you made up")
        return True

    return False


# ---------------------------------------------------------------------------
# Surviving a restart
# ---------------------------------------------------------------------------
def _save():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

        with open(STATE_FILE, "w") as handle:
            json.dump({"energy": round(_energy, 3),
                       "warmth": round(_warmth, 3),
                       "desire": round(_desire, 3),
                       "grudge_until": round(_grudge_until),
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
    global _energy, _warmth, _desire, _grudge_until

    try:
        with open(STATE_FILE) as handle:
            saved = json.load(handle)

        away = max(0.0, time.time() - float(saved["at"]))
        faded = min(1.0, away / (4 * 3600))
        energy, warmth = float(saved["energy"]), float(saved["warmth"])
        desire, grudge = float(saved.get("desire", 0)), float(saved.get("grudge_until", 0))
    except (OSError, ValueError, KeyError, TypeError):
        return False

    with _lock:
        _energy = _clamp(energy + (_energy_baseline() - energy) * faded)
        _warmth = _clamp(warmth + (_warmth_baseline() - warmth) * faded)
        _desire = max(0.0, desire * 0.5 ** (away / 1200.0))
        _grudge_until = grudge if grudge > time.time() else 0.0
        _settle()

    logbook.info("mood", "restored after %.1f min away (%.0f%% faded)",
                 away / 60, faded * 100)

    return True


def portrait_state():
    """What the live monitor and the portrait get: the mood, the dials,
    its face and idle moves. With mood.face off she shows nothing - the
    dials go out as neutral so nothing else reads a mood off them."""
    name, energy, warmth, _why = state()
    show = config.MOOD_ENABLED and getattr(config, "MOOD_FACE", True) and _intensity() > 0

    if away():
        spec = _walk()
        moves = config.MOOD_GESTURES and _intensity() > 0
        return {"label": str(spec.get("label") or "withdrawn"), "row": "", "energy": energy if show else 0.0,
                "warmth": warmth if show else 0.0,
                "face": dict(spec.get("face") or {}) if show else {}, "idle": [],
                "hold": str(spec.get("hold") or "") if moves else "",
                "emote": _emote(spec.get("emote"), sulking=True)}

    return {"label": name, "row": _row_of(name), "energy": energy if show else 0.0,
            "warmth": warmth if show else 0.0, "face": face() if show else {}, "idle": idle(),
            "hold": "", "emote": emote(), "tame": bool(_tame)}


def _announce():
    try:
        import ui

        ui.set_mood(label())
    except Exception:
        pass  # headless, or the UI isn't up yet

    try:
        from web import livefeed

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
