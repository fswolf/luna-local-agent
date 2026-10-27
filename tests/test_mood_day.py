"""A recorded day of her moods: the same events, the same answers, every time.

A scripted day goes through everything that moves her - a cold morning,
warming up, compliments, flirting into the lewd row, a stream that keeps
it tame, spanks past the limit, desire fading while you're away,
hostility into a grudge, walking away and making up, errors, games, the
machine busy while you're gone, the day of the week, a restart - and at
every step writes down what she'd show: the label, the dials, desire and
the grudge, her prompt line (private and public), voice, face, idles,
emotes, the portrait's state and every event sent to the UI and the
portrait. It runs at intensity 1, 2 and 0.

The answers are kept in tests/data/mood_day.json and every run must give
exactly the same ones. It exists so mind/mood can be reorganised without
changing who she is by a single decimal. When you change how her moods
work on purpose, record it again and look at the diff:

    MOOD_DAY_RECORD=1 python -m unittest tests.test_mood_day

It uses its own copy of the moods file (tests/data/mood_day_moods.json),
so editing agent/moods.json never breaks it.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime as real_datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from mind import mood  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "data", "mood_day.json")
MOODS = os.path.join(HERE, "data", "mood_day_moods.json")


class Clock:
    """Wall time, monotonic time and the local date, moved by the script."""

    def __init__(self, start):
        self.now = start                 # naive local datetime
        self.mono = 1000.0

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.mono += seconds

    def time(self):
        return (self.now - real_datetime(1970, 1, 1)).total_seconds()


def _mood_modules():
    """Everything her moods are made of, wherever it lives."""
    return [m for name, m in sorted(sys.modules.items())
            if m and (name == "mind.mood" or name.startswith("mind.mood.") or name.startswith("mind.mood_")
                      or name == "mind.appraise")]


class _SyncThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class _NoTimer:
    def __init__(self, *a, **k):
        self.daemon = True

    def start(self):
        pass


# Her state, by its old loose names (they work before and after mind/mood
# became a package): cleared before the day so earlier tests can't colour
# it, and put back after so it can't colour later ones.
FRESH = {"_energy": 0.0, "_warmth": 0.0, "_last_turn": None, "_recent": [], "_busy": [], "_chat_seen": 0,
         "_label": "", "_phrasing": {}, "_clean_run": 0, "_desire": 0.0, "_grudge_until": 0.0,
         "_affection_recent": 0.0, "_last_rating": None, "_last_feeling": None,
         "_spanks": {"n": 0.0, "at": 0.0}, "_tame": set(),
         "_away": {"until": 0.0, "said": False, "hostile": 0, "last": 0.0}}


def _fill(name, value):
    old = getattr(mood, name)
    if isinstance(old, (list, dict, set)):     # the same object others hold: refill it
        old.clear()
        (old.update if not isinstance(old, list) else old.extend)(value)
    else:
        setattr(mood, name, value)


def run_day(intensity):
    clock = Clock(real_datetime(2026, 10, 27, 9, 0))          # a Tuesday morning
    tmp = tempfile.mkdtemp()
    trace, events, appraisals, gpu = [], [], [], [0]

    class FakeDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now

    def appraise(said, answer, model):
        return appraisals.pop(0) if appraisals else (0, 0, 0, None, 0)

    patches = [
        mock.patch("time.time", clock.time),
        mock.patch("time.monotonic", lambda: clock.mono),
        mock.patch("random.choice", lambda seq: seq[0]),
        mock.patch("threading.Thread", _SyncThread),
        mock.patch("threading.Timer", _NoTimer),
        mock.patch("web.livefeed.emit", lambda kind, **d: events.append([kind, d])),
        mock.patch("ui.set_mood", lambda text: events.append(["ui", text])),
        mock.patch("plugins.names", lambda: []),
        mock.patch("core.machine.gpus", lambda: [{"busy": gpu[0]}]),
    ]
    for name, value in {"MOOD_ENABLED": True, "MOOD_INTENSITY": intensity, "MOOD_RECOVERY": 0.25,
                        "MOOD_WARMTH": 0.45, "MOOD_AFFECTION": True, "MOOD_PROMPT": True,
                        "MOOD_VOICE": True, "MOOD_FACE": True, "MOOD_GESTURES": True,
                        "MOOD_EMOTES": True, "MOOD_WALK_AWAY": True, "MOOD_WALK_AWAY_MINUTES": 10,
                        "MOOD_WALK_AWAY_AFTER": 3, "USER": "Ryan"}.items():
        patches.append(mock.patch.object(config, name, value, create=True))
    for module in _mood_modules():
        for name, value in (("datetime", FakeDatetime), ("_appraise", appraise),
                            ("STATE_FILE", os.path.join(tmp, "mood.json")), ("MOODS_FILE", MOODS)):
            if name in vars(module):
                patches.append(mock.patch.object(module, name, value))
        cache = vars(module).get("_moods")
        if isinstance(cache, dict) and "data" in cache:
            patches.append(mock.patch.dict(cache, {"data": None, "mtime": None, "error": ""}))

    def snap(what):
        trace.append({
            "step": what,
            "label": mood.label(),
            "state": mood.state(),
            "layers": mood.layers(),
            "bands": mood.bands(),
            "line": mood.line(),
            "public_line": mood.line(private=False),
            "voice": mood.voice_tint(),
            "face": mood.face(),
            "idle": mood.idle(),
            "emote": mood.emote(),
            "portrait": mood.portrait_state(),
            "away": round(mood.away(), 3),
            "last_rating": mood.last_rating(),
            "last_feeling": mood.last_feeling(),
            "tame": mood.tame(),
            "events": list(events),
        })
        events.clear()

    def turn(seconds, *appraisal, said="hi", what=""):
        clock.advance(seconds)
        if appraisal:
            appraisals.append(tuple(appraisal))
        mood.note_turn()
        mood.note_exchange(said, "an answer", model="m")
        snap(what or f"turn after {seconds}s, appraised {appraisal or 'neutral'}")

    saved = {n: copy.deepcopy(getattr(mood, n)) for n in FRESH}
    for n, v in FRESH.items():
        _fill(n, copy.deepcopy(v))
    for p in patches:
        p.start()
    try:
        mood.reset()
        snap("reset, tuesday 9am")
        mood._sample_machine()

        # a cold, slow morning
        turn(30, 0, 0, 0, None, 0, what="first words")
        turn(20, 0, -1, 0, None, 0)
        turn(600, 1, 0, 1, "curious", 0)
        # warming up: compliments, repeated (they taper)
        for _ in range(4):
            turn(15, 2, 1, 1, "happy", 0)
        turn(40, 3, 1, 1, "touched", 0, what="strong affection")
        # very warm, then flirting builds desire into the lewd row
        mood.set_mood(warmth=0.85)
        snap("set very warm")
        for flirt in (1, 2, 2, 2, 1):
            turn(25, 2, 1, 1, "embarrassed", flirt, what=f"flirt {flirt}")
        # a stream that keeps it tame, then off again
        mood.set_tame("twitch", True)
        snap("tame: twitch live")
        mood.set_tame("twitch", False)
        snap("tame: off")
        # spanks: up to the limit, then one too many
        for i in range(70):
            clock.advance(0.05)
            over = mood.note_spank()
            if i in (0, 59, 60, 61, 69):
                snap(f"spank {i + 1} (too many: {over})")
        # away 25 minutes: desire halves
        turn(1500, 0, 0, 0, None, 0, what="back after 25 minutes")
        # a bad patch: hostility, into a grudge, then she walks away
        turn(20, 0, -1, -1, "annoyed", 0, what="hostile 1")
        turn(20, 0, -1, -1, "annoyed", 0, what="hostile 2")
        turn(20, 0, 0, -1, None, 0, what="hostile 3: walks away")
        snap(f"leaving line: {mood.leaving_line()!r}, then {mood.leaving_line()!r}")
        clock.advance(60)
        snap("a minute into the sulk")
        appraisals.append((2, 0, 1, None, 0))
        snap(f"apology while away, back: {mood.heard_while_away('sorry, I was rude', 'm')}")
        turn(30, 2, 0, 1, "touched", 0, what="made up")
        # cool already, then hostile: a grudge from what was said
        mood.set_mood(warmth=-0.3)
        snap("set cool")
        turn(20, 0, 0, -1, "annoyed", 0, what="hostile while cool: grudge starts")
        turn(60, 0, 0, -1, None, 0, what="hostile again: grudge restarts")
        turn(60, 0, 0, 0, None, 0, what="neutral: still holding it")
        turn(60, 1, 0, 0, None, 0, what="polite but no apology")
        turn(60, 2, 0, 1, "touched", 0, what="an apology: made up")
        # walking away again, and this time just waiting it out
        for i in range(3):
            turn(20, 0, -1, -1, "annoyed", 0, what=f"hostile run {i + 1}")
        clock.advance(601)
        snap("ten minutes later, she's back on her own")
        turn(30, 0, 0, 0, None, 0, what="first turn after the sulk")
        # things going wrong, and other signals
        for i in range(4):
            mood.note_error()
            snap(f"error {i + 1}")
        mood.note_denied()
        mood.note_bargein()
        mood.note_thanks()
        mood.note_play("enjoyed", "Zork")
        mood.note_play("frustrated", "Minecraft")
        snap("denied, talked over, thanked, two games")
        for _ in range(10):
            turn(10, 1, 0, 0, None, 0)
        snap("ten clean turns")
        # gaming for two hours: the machine busy while she waited
        gpu[0] = 85
        for _ in range(60):
            clock.advance(120)
            mood._sample_machine()
        turn(1, 0, 0, 0, None, 0, what="back after two hours of gaming")
        # the day of the week
        clock.now = real_datetime(2026, 10, 30, 18, 30)       # friday evening
        clock.mono += 3 * 86400
        turn(1, 1, 1, 0, None, 0, what="friday evening")
        clock.now = real_datetime(2026, 11, 2, 8, 0)          # monday morning
        clock.mono += 3 * 86400
        turn(1, 0, -1, 0, None, 0, what="monday morning")
        # a grudge set by hand, and running out
        mood.set_mood(grudge_minutes=5)
        snap("grudge set for 5 minutes")
        turn(30, 0, 0, 0, None, 0, what="neutral during the grudge")
        clock.advance(360)
        snap("grudge ran out")
        # a restart: saved, an hour away, restored
        mood._save()
        clock.advance(3600)
        restored = mood._restore()
        snap(f"restored after an hour: {restored}")
        mood.set_mood(energy=-0.9, warmth=-0.9, desire=0.5)
        snap("set cold and tired")
        mood.set_mood(energy=0.9, warmth=0.95, desire=0.95)
        snap("set wired and very warm, desire high")
    finally:
        for p in reversed(patches):
            p.stop()
        for n, v in saved.items():
            _fill(n, v)
        shutil.rmtree(tmp, ignore_errors=True)

    return json.loads(json.dumps(trace))


def record():
    return {f"intensity {k}": run_day(k) for k in (1.0, 2.0, 0.0)}


class MoodDay(unittest.TestCase):
    def test_the_recorded_day(self):
        got = record()
        if os.environ.get("MOOD_DAY_RECORD"):
            with open(GOLDEN, "w") as f:
                json.dump(got, f, indent=1)
            self.skipTest("recorded " + GOLDEN)
        with open(GOLDEN) as f:
            want = json.load(f)
        for day, steps in want.items():
            self.assertEqual(len(got[day]), len(steps), day)
            for a, b in zip(got[day], steps):
                self.assertEqual(a, b, f"{day}: {b['step']}")


if __name__ == "__main__":
    unittest.main()
