"""Heavy moments (mind/mood/heavy.py): she notices a really hard time, and
nothing else in her mood changes because of it.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from mind import mood  # noqa: E402
from mind.mood import appraise, heavy  # noqa: E402


class Heavy(unittest.TestCase):
    def setUp(self):
        heavy.reset()
        heavy.listening(True)
        self.away = mock.patch("mind.mood.walkaway.away", lambda: False)
        self.away.start()

    def tearDown(self):
        self.away.stop()
        heavy.reset()
        heavy.listening(True)

    def test_reading_the_word(self):
        self.assertEqual(appraise._parse_heaviness("2 + + laughing 1 normal"), "normal")
        self.assertEqual(appraise._parse_heaviness("<think>maybe heavy</think>0 - = sad 0 heavy"), "heavy")
        self.assertIsNone(appraise._parse_heaviness("0 - = sad 0"))               # an older-style answer
        self.assertEqual(appraise._parse_heaviness("1 = = none rough"), "rough")  # flirt left out
        self.assertIsNone(appraise._parse_heaviness("it feels heavy"))             # not the line's shape
        # the five old fields read exactly as before with the sixth on the end
        feelings = ["sad", "laughing"]
        self.assertEqual(appraise._parse_appraisal("2 + + laughing 1 rough", feelings),
                         appraise._parse_appraisal("2 + + laughing 1", feelings))

    def test_heavy_counts_at_once_rough_needs_two(self):
        heavy.note("rough")
        self.assertEqual(heavy.level(), 0)
        heavy.note("rough")
        self.assertEqual(heavy.level(), 1)
        heavy.reset()
        heavy.note("heavy")
        self.assertEqual(heavy.level(), 2)

    def test_it_fades(self):
        heavy.note("heavy")
        heavy.note("normal")
        self.assertEqual(heavy.level(), 2)
        heavy.note("normal")
        self.assertEqual(heavy.level(), 1)
        heavy.note("normal")
        heavy.note("normal")
        self.assertEqual(heavy.level(), 0)
        heavy.note("heavy", now=1000.0)
        self.assertEqual(heavy.level(now=1000.0 + heavy.FORGET + 1), 0)       # a new day starts fresh

    def test_the_line(self):
        self.assertEqual(heavy.line(), "")
        heavy.note("heavy")
        self.assertIn("really hard time", heavy.line())
        self.assertEqual(heavy.line(private=False), "")                        # stream chat never sees it
        with mock.patch("mind.mood.walkaway.away", lambda: True):
            self.assertEqual(heavy.line(), "")
        with mock.patch.object(heavy, "moods", lambda: {"heavy": {"enabled": False}}):
            self.assertEqual(heavy.line(), "")                                  # off: exactly as before
        for word in ("helpline", "hotline", "crisis", "therapist"):
            self.assertNotIn(word, heavy.line().lower())

    def test_only_your_messages(self):
        heavy.listening(False)                                                  # a guest's turn
        with mock.patch("requests.post") as post:
            post.return_value.json.return_value = {"choices": [{"message": {"content": "0 - = sad 0 heavy"}}]}
            appraise._appraise("worst day ever", "oh no", "m")
        self.assertEqual(heavy.level(), 0)
        heavy.listening(True)
        with mock.patch("requests.post") as post:
            post.return_value.json.return_value = {"choices": [{"message": {"content": "0 - = sad 0 heavy"}}]}
            self.assertEqual(appraise._appraise("worst day ever", "oh no", "m")[3], "sad")
        self.assertEqual(heavy.level(), 2)

    def test_not_in_front_of_a_guest(self):
        from core import turnctx
        heavy.note("heavy")
        with turnctx.begin(speaker="mike"):
            self.assertEqual(heavy.line(), "")
        with turnctx.begin():
            self.assertIn("really hard time", heavy.line())

    def test_a_touch_after_your_turn_doesnt_count(self):
        heavy.listening(True)
        self.assertTrue(heavy.owner_turn())
        self.assertFalse(heavy.owner_turn())                                    # used up: the touch's read

    def test_mood_reset_clears_it(self):
        heavy.note("heavy")
        with mock.patch("mind.mood.saving._save"), mock.patch("mind.mood.show._announce"):
            mood.reset()
        self.assertEqual(heavy.level(), 0)
        self.assertEqual(heavy.describe(), "")

    def test_nothing_else_moves(self):
        before = (mood.S.energy, mood.S.warmth, mood.S.desire, mood.S.label)
        heavy.note("heavy")
        self.assertEqual((mood.S.energy, mood.S.warmth, mood.S.desire, mood.S.label), before)


if __name__ == "__main__":
    unittest.main()
