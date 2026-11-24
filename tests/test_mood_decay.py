"""Time winds her down (mind/mood/drift.py _decay), every turn of yours drifts
her home whatever it came in by, and the exchange reader rates your message,
not her answer (mind/mood/appraise.py).

    python -m unittest tests.test_mood_decay
"""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from mind import mood  # noqa: E402
from mind.mood import appraise, drift, saving  # noqa: E402
from mind.mood.core import S  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for p in (mock.patch.object(config, "MOOD_ENABLED", True),
                  mock.patch.object(config, "MOOD_INTENSITY", 1.0, create=True),
                  mock.patch.object(config, "MOOD_WARMTH", 0.45, create=True),
                  mock.patch.object(config, "MOOD_FORGIVE", 0.5, create=True),
                  mock.patch.object(config, "MOOD_SETTLE_MINUTES", 45, create=True),
                  mock.patch.object(config, "MOOD_DESIRE_MINUTES", 20, create=True),
                  mock.patch("mind.mood.saving.STATE_FILE", os.path.join(self.tmp.name, "mood.json")),
                  mock.patch("mind.mood.show._announce", lambda: None),
                  mock.patch.object(drift, "_energy_baseline", lambda now=None: 0.2)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        mood.reset()

    def idle(self, minutes):
        with mood._lock:
            return drift._decay(S.decayed_at + minutes * 60)


class WindsDown(Base):
    def test_desire_halves_every_desire_minutes_with_nobody_talking(self):
        mood.set_mood(warmth=0.9, desire=0.8)
        self.idle(20)
        self.assertAlmostEqual(S.desire, 0.4, places=3)
        self.idle(40)
        self.assertAlmostEqual(S.desire, 0.1, places=3)

    def test_extra_warmth_and_energy_settle_by_half_every_settle_minutes(self):
        mood.set_mood(energy=0.9, warmth=0.95)
        self.idle(45)
        self.assertAlmostEqual(S.warmth, 0.45 + 0.25, places=3)
        # energy heads where the turn's step does: the hour's (0.2) plus
        # half her extra warmth, no sitting drag while nobody's here
        target = 0.2 + (0.70 - 0.45) * 0.5
        self.assertAlmostEqual(S.energy, target + (0.9 - target) * 0.5, places=3)

    def test_the_lewd_row_ends_by_itself(self):
        mood.set_mood(energy=0.5, warmth=0.9, desire=0.9)
        self.assertIn(mood.label(), mood._extra("lewd")["row"])
        self.idle(30)
        self.assertNotIn(mood.label(), mood._extra("lewd")["row"])

    def test_hurt_heals_slower_than_warmth_fades(self):
        mood.set_mood(warmth=-0.55)       # 1.0 under rest; forgive 0.5: 90 minutes to halve
        self.idle(90)
        self.assertAlmostEqual(S.warmth, 0.45 - 0.5, places=3)

    def test_a_grudge_keeps_her_below_its_ceiling_while_healing(self):
        mood.set_mood(warmth=-0.9, grudge_minutes=60)
        self.idle(59)
        self.assertLessEqual(S.warmth, mood._ceiling())

    def test_it_only_counts_the_time_once(self):
        mood.set_mood(warmth=0.9, desire=0.8)
        now = S.decayed_at + 1200
        with mood._lock:
            drift._decay(now)
            drift._decay(now)
        self.assertAlmostEqual(S.desire, 0.4, places=3)

    def test_the_minute_tick_shows_and_saves_what_moved(self):
        mood.set_mood(warmth=0.9, desire=0.8)
        S.decayed_at -= 600
        with mock.patch("mind.mood.show._announce") as shown:
            drift._tick()
        shown.assert_called_once()
        with open(saving.STATE_FILE) as f:
            self.assertLess(json.load(f)["desire"], 0.8)

    def test_a_restart_winds_down_the_same_as_staying_idle(self):
        mood.set_mood(energy=0.9, warmth=0.95, desire=0.8)
        saving._save()
        with open(saving.STATE_FILE) as f:
            saved = json.load(f)
        saved["at"] = time.time() - 45 * 60
        with open(saving.STATE_FILE, "w") as f:
            json.dump(saved, f)
        self.assertTrue(saving._restore())
        self.assertAlmostEqual(S.warmth, 0.70, places=2)
        self.assertAlmostEqual(S.desire, 0.8 * 0.5 ** (45 / 20), places=2)

    def test_settings_under_a_minute_dont_divide_by_nothing(self):
        with mock.patch.object(config, "MOOD_DESIRE_MINUTES", 0):
            self.assertEqual(drift.desire_minutes(), 1.0)
        with mock.patch.object(config, "MOOD_SETTLE_MINUTES", "lots"):
            self.assertEqual(drift.settle_minutes(), 45.0)


class SpankBursts(Base):
    def spank(self, at):
        with mock.patch("mind.mood.exchange.time.time", return_value=at):
            return mood.note_spank()

    def test_three_playful_then_each_one_cools_her(self):
        mood.set_mood(energy=0.5, warmth=0.9, desire=0.9)
        self.assertEqual([self.spank(1000 + i) for i in range(3)], [False] * 3)
        self.assertAlmostEqual(S.desire, 0.9)
        self.assertTrue(self.spank(1003))
        self.assertAlmostEqual(S.desire, 0.75)
        self.assertAlmostEqual(S.warmth, 0.85)

    def test_keeping_at_it_takes_her_out_of_the_lewd_row(self):
        mood.set_mood(energy=0.5, warmth=0.9, desire=0.9)
        self.assertIn(mood.label(), mood._extra("lewd")["row"])
        for i in range(6):
            self.spank(1000 + i)
        self.assertNotIn(mood.label(), mood._extra("lewd")["row"])

    def test_thirty_quiet_seconds_start_a_new_burst(self):
        mood.set_mood(warmth=0.9, desire=0.9)
        for i in range(3):
            self.spank(1000 + i)
        self.assertFalse(self.spank(1002 + 31))
        self.assertAlmostEqual(S.desire, 0.9)
        with mock.patch("mind.mood.exchange.time.time", return_value=1033 + 31):
            self.assertEqual(mood.spanking(), 0)

    def test_off_with_moods_off(self):
        with mock.patch.object(config, "MOOD_ENABLED", False):
            self.assertFalse(any(self.spank(1000 + i) for i in range(6)))


class TheSitting(Base):
    """Hours at the keyboard count from when you came back, not from launch."""

    def test_idle_is_rest_not_a_long_sitting(self):
        with mood._lock:
            S.started = S.last_turn = time.monotonic() - 10 * 3600   # launched ten hours ago
            S.warmth = 0.45
            self.assertAlmostEqual(drift._energy_target(), 0.2, places=3)

    def test_a_long_sitting_wears_her_down(self):
        now = time.monotonic()
        with mood._lock:
            S.started, S.last_turn, S.warmth = now - 3 * 3600, now - 60, 0.45
            self.assertAlmostEqual(drift._energy_target(now), 0.2 - 0.18, places=3)

    def test_coming_back_after_a_break_starts_a_new_sitting(self):
        with mood._lock:
            S.started = time.monotonic() - 5 * 3600
            S.last_turn = time.monotonic() - 2 * 3600
        with mock.patch.object(drift, "_machine_shape", return_value=(0, 0, "")), \
                mock.patch.object(drift, "_day_shape", return_value=(0, 0)), \
                mock.patch.object(drift, "_chat_shape", return_value=(0, 0, "")):
            drift.note_turn()
        self.assertLess(time.monotonic() - S.started, 5)


class HandWrittenSettings(unittest.TestCase):
    def test_a_bad_number_says_so_and_uses_the_default(self):
        from config import base
        with mock.patch.object(base, "_complain") as said:
            self.assertEqual(base.number({"settle_minutes": "45m"}, "settle_minutes", 45, 1.0), 45.0)
            self.assertEqual(base.number({"settle_minutes": None}, "settle_minutes", 45, 1.0), 45.0)
            self.assertEqual(base.number({"x": float("nan")}, "x", 2), 2.0)
        self.assertEqual(said.call_count, 3)
        self.assertEqual(base.number({"forgive": 9}, "forgive", 0.5, 0.05, 1.0), 1.0)
        self.assertEqual(base.number({}, "desire_minutes", 20, 1.0), 20.0)


class EveryTurnDrifts(unittest.TestCase):
    """A voice or station turn takes the same step home as a typed one."""

    def test_respond_drifts_after_any_source(self):
        from core import assistant
        for source in ("typed", "voice", "station"):
            with mock.patch.object(assistant, "_respond", return_value="ok"), \
                    mock.patch.object(assistant, "_gone", return_value=None), \
                    mock.patch.object(assistant, "_plugins_hear"), \
                    mock.patch("mind.mood.note_turn") as turned:
                self.assertEqual(assistant.respond("hi", "m", source=source), "ok")
            turned.assert_called_once()


class ReaderRatesYourMessage(unittest.TestCase):
    def test_no_affectionate_example_left_to_copy(self):
        self.assertNotIn("2 + +", appraise._APPRAISE_PROMPT)
        self.assertIn("0 = = none 0 normal", appraise._APPRAISE_PROMPT)
        filled = appraise._APPRAISE_PROMPT.format(name="Luna", user="Ryan", them="him", their="his",
                                                  said="hello", answer="hi", feelings="happy")
        self.assertIn("never raises them", filled)

    def test_recent_exchanges_pairs_your_words_with_her_last_ones(self):
        messages = [
            {"role": "user", "content": "find the captain's log"},
            {"role": "assistant", "content": None, "tool_calls": [{}]},
            {"role": "tool", "content": "results"},
            {"role": "assistant", "content": "It's on the bridge."},
            {"role": "user", "content": [{"type": "text", "text": "and this?"}, {"type": "image_url"}]},
            {"role": "assistant", "content": "A cat."},
        ]
        with mock.patch("core.history.get_messages_full", return_value=messages):
            self.assertEqual(appraise.recent_exchanges(5),
                             [("find the captain's log", "It's on the bridge."), ("and this?", "A cat.")])
            self.assertEqual(appraise.recent_exchanges(1), [("and this?", "A cat.")])

    def test_check_reads_both_prompts_and_counts(self):
        def answer(template, said, reply, model):
            return "2 + + happy 1 normal" if template is appraise._BEFORE_PROMPT else "0 = = none 0 normal"
        lines = []
        with mock.patch.object(appraise, "recent_exchanges", return_value=[("web search a game", "sure~")]), \
                mock.patch.object(appraise, "_ask", side_effect=answer):
            appraise.check("m", 1, say=lines.append)
        self.assertIn("2 + + happy 1", lines[1])
        self.assertIn("0 = = none 0", lines[1])
        self.assertEqual(lines[-2], "before: affectionate 1/1, warmed her 1/1, flirty 1/1")
        self.assertEqual(lines[-1], "   now: affectionate 0/1, warmed her 0/1, flirty 0/1")


if __name__ == "__main__":
    unittest.main()
