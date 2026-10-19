"""The rows past the grid: lewd (very warm + desire) and grudge (hostile
while cool). The appraisal is faked - no model calls.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
import mood  # noqa: E402


def appraised(rating=0, energy=0, warmth=0, feeling=None, flirt=0):
    return mock.patch.object(mood, "_appraise", return_value=(rating, energy, warmth, feeling, flirt))


class Layers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(config, "MOOD_ENABLED", True),
            mock.patch.object(config, "MOOD_INTENSITY", 1.0, create=True),
            mock.patch.object(config, "MOOD_WALK_AWAY", False, create=True),
            mock.patch.object(mood, "STATE_FILE", os.path.join(self.tmp.name, "mood.json")),
            mock.patch.object(mood, "_announce", lambda: None),
            mock.patch.object(mood, "_feel", lambda f: None),
            mock.patch.object(mood, "_compliment", lambda r, f: None),
        ]
        for p in self.patches:
            p.start()
        mood.reset()
        mood._label = ""
        mood._affection_recent = 0.0

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def exchange(self, **kw):
        with appraised(**kw):
            mood._apply_exchange("hi", "hello", "model")

    # -- lewd ---------------------------------------------------------------
    def test_lewd_needs_very_warm_and_desire(self):
        mood.set_mood(energy=0.0, warmth=0.8, desire=0.7)
        self.assertEqual(mood.label(), "frisky")
        mood.set_mood(energy=-0.6)
        self.assertEqual(mood.label(), "teasing")
        mood.set_mood(energy=0.8)
        self.assertEqual(mood.label(), "heated")

    def test_a_tame_stream_shows_the_row_below(self):
        mood.set_mood(energy=0.0, warmth=0.8, desire=0.7)
        self.assertEqual(mood.label(), "frisky")
        mood.set_tame("twitch", True)
        try:
            grid = mood.moods()["grid"]
            self.assertEqual(mood.label(), grid[-1][1])
            self.assertTrue(mood.portrait_state()["tame"])
            self.assertFalse(mood.portrait_state()["row"])
            self.assertNotIn("in the mood for", mood.line())
            self.assertEqual(mood.layers()["desire"], 0.7)      # still there underneath
        finally:
            mood.set_tame("twitch", False)
        self.assertEqual(mood.label(), "frisky")

    def test_desire_alone_isnt_enough(self):
        mood.set_mood(energy=0.0, warmth=0.5, desire=0.9)       # warm, not very warm
        self.assertNotIn(mood.label(), ("teasing", "frisky", "heated"))

    def test_flirting_builds_desire_only_when_warm(self):
        mood.set_mood(warmth=0.0)
        self.exchange(flirt=2)
        self.assertEqual(mood.layers()["desire"], 0.0)
        mood.set_mood(warmth=0.8)
        for _ in range(4):
            self.exchange(rating=2, flirt=2)
        self.assertGreaterEqual(mood.layers()["desire"], 0.6)

    def test_hostility_kills_it_at_once(self):
        mood.set_mood(energy=0.0, warmth=0.8, desire=0.9)
        self.exchange(warmth=-1)
        self.assertEqual(mood.layers()["desire"], 0.0)
        self.assertNotIn(mood.label(), ("teasing", "frisky", "heated"))
        self.assertLess(mood.state()[2], 0.5)

    def test_desire_dies_below_warm(self):
        mood.set_mood(warmth=0.8, desire=0.8)
        mood._nudge(warmth=-0.6)
        self.assertEqual(mood.layers()["desire"], 0.0)

    def test_desire_fades_each_turn(self):
        mood.set_mood(warmth=0.8, desire=0.5)
        mood.note_turn()
        self.assertLess(mood.layers()["desire"], 0.5)

    # -- grudge -------------------------------------------------------------
    def test_one_insult_while_warm_is_no_grudge(self):
        mood.set_mood(warmth=0.6)
        self.exchange(warmth=-1)
        self.assertEqual(mood.layers()["grudge"], 0)

    def test_insult_while_cool_starts_a_grudge(self):
        mood.set_mood(energy=0.8, warmth=-0.1)
        self.exchange(warmth=-1)
        self.assertGreater(mood.layers()["grudge"], 0)
        self.assertEqual(mood.label(), "furious")
        mood.set_mood(energy=0.0)
        self.assertEqual(mood.label(), "hurt")

    def test_grudge_holds_against_drift_and_kindness_short_of_making_up(self):
        mood.set_mood(warmth=-0.5, grudge_minutes=20)
        for _ in range(10):
            mood.note_turn()
        mood._nudge(warmth=0.5)
        self.assertLess(mood.state()[2], -0.2)
        self.exchange(rating=1)                 # polite isn't an apology
        self.assertGreater(mood.layers()["grudge"], 0)

    def test_apology_ends_it(self):
        mood.set_mood(warmth=-0.5, grudge_minutes=20)
        self.exchange(rating=2, warmth=1)
        self.assertEqual(mood.layers()["grudge"], 0)

    def test_grudge_runs_out(self):
        mood.set_mood(warmth=-0.5, grudge_minutes=20)
        mood._grudge_until = 1.0                 # long past
        self.assertEqual(mood.layers()["grudge"], 0)
        self.assertNotIn(mood.label(), ("sulky", "hurt", "furious"))

    def test_making_up_lifts_her_a_little(self):
        mood.set_mood(warmth=-0.5, grudge_minutes=20)
        before = mood.state()[2]
        self.exchange(rating=2, warmth=1)
        self.assertGreater(mood.state()[2], before)

    def test_making_up_while_shes_away_ends_the_grudge(self):
        mood.set_mood(warmth=-0.5, grudge_minutes=20)
        with appraised(rating=2, warmth=1), mock.patch.object(mood, "_back", lambda why: None):
            self.assertTrue(mood.heard_while_away("I'm sorry, Luna", "model"))
        self.assertEqual(mood.layers()["grudge"], 0)

    def test_lewd_doesnt_flicker_at_the_warmth_edge(self):
        mood.set_mood(energy=0.0, warmth=0.8, desire=0.8)
        self.assertEqual(mood.label(), "frisky")
        mood.set_mood(warmth=0.63)               # a hair under very warm
        self.assertEqual(mood.label(), "frisky")
        mood.set_mood(warmth=0.5)                # clearly out
        self.assertNotEqual(mood.label(), "frisky")

    def test_blunt_isnt_hostile(self):
        mood.set_mood(warmth=0.8, desire=0.8)
        self.exchange(rating=0, energy=-1, warmth=0)
        self.assertEqual(mood.layers()["desire"], 0.8)

    def test_a_polite_hello_brings_her_back_but_doesnt_end_the_grudge(self):
        mood.set_mood(warmth=-0.5, grudge_minutes=20)
        with appraised(rating=1), mock.patch.object(mood, "_back", lambda why: None):
            self.assertTrue(mood.heard_while_away("hi", "model"))
        self.assertGreater(mood.layers()["grudge"], 0)

    # -- what everything else sees ------------------------------------------
    def test_portrait_and_log_see_the_row(self):
        mood.set_mood(energy=0.0, warmth=0.8, desire=0.8)
        self.assertEqual(mood.portrait_state()["row"], "lewd")
        self.assertEqual(mood.bands()[1], "lewd")
        mood.set_mood(warmth=-0.5, grudge_minutes=20)
        self.assertEqual(mood.portrait_state()["row"], "grudge")
        self.assertEqual(mood.bands()[1], "grudge")
        mood.set_mood(warmth=0.45, grudge_minutes=0, desire=0)
        self.assertEqual(mood.portrait_state()["row"], "")
        self.assertEqual(mood.bands()[1], "warm")

    # -- what she's told ----------------------------------------------------
    def test_lines(self):
        mood.set_mood(warmth=0.45, energy=0.0)
        self.assertIn("not in the", mood.line())
        mood.set_mood(warmth=0.8, desire=0.8)
        self.assertNotIn("not in the", mood.line())
        mood.set_mood(warmth=-0.5, grudge_minutes=20)
        line = mood.line()
        self.assertIn("grudge", line)
        self.assertIn("alarms", line)

    def test_parse_with_and_without_flirt(self):
        feelings = ["playful"]
        self.assertEqual(mood._parse_appraisal("2 + + playful 1", feelings), (2, 1, 1, "playful", 1))
        self.assertEqual(mood._parse_appraisal("0 = - none", feelings), (0, 0, -1, None, 0))
        self.assertEqual(mood._parse_appraisal("3", feelings), (3, 0, 0, None, 0))

    def test_survives_a_restart(self):
        mood.set_mood(warmth=-0.5, grudge_minutes=20)
        mood._save()
        mood.set_mood(grudge_minutes=0)          # forget it in memory only
        self.assertEqual(mood.layers()["grudge"], 0)
        mood._restore()
        self.assertGreater(mood.layers()["grudge"], 0)


if __name__ == "__main__":
    unittest.main()
