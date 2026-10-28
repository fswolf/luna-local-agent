"""A move she describes instead of tagging plays anyway (gestures.from_asides),
and the tag prompt no longer invites stage directions.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from life import gestures  # noqa: E402

ABOUTS = {
    "beckon_kiss": "flirty, teasing: beckons you over, then blows you a kiss",
    "blow_kiss": "blowing a kiss, affection",
    "look_back": "teasing, turns around and bends over, looking back at you",
    "sultry_beckon": "sultry come-hither, teasing, inviting",
    "giggle": "giggling, amused, tickled, a little embarrassed",
    "wave": "hello, goodbye",
    "hug": "affection, comfort",
    "wink": "playful, teasing, a little flirty",
}


class Asides(unittest.TestCase):
    def test_what_she_actually_wrote(self):
        for aside, name in [("beckons you over and blows a kiss", "beckon_kiss"),
                            ("sultry come-hither", "sultry_beckon"),
                            ("blows you a kiss", "blow_kiss"),
                            ("waves hello", "wave"),
                            ("turns around and looks back at you", "look_back")]:
            self.assertEqual(gestures.match_aside(aside, ABOUTS), name, aside)

    def test_ordinary_asides_play_nothing(self):
        for aside in ("poses, shifting smoothly between a few animations",
                      "giggles, realizing what he's doing", "the file is saved", "see the docs", "sighs"):
            self.assertIsNone(gestures.match_aside(aside, ABOUTS), aside)

    def test_each_plays_once_per_turn(self):
        sent = []
        with mock.patch.object(gestures, "_three_d", return_value=True), \
                mock.patch.object(gestures, "_offered_now", return_value=ABOUTS), \
                mock.patch.object(gestures, "mode", return_value="tags"), \
                mock.patch.object(gestures, "_emit", side_effect=lambda n, src: sent.append((n, src))):
            gestures.new_turn()
            text = "Alright, here~ (beckons you over and blows a kiss) ... (sultry come-hither)"
            gestures.from_tags(text)
            gestures.from_tags(text + " more")
        self.assertEqual(sent, [("beckon_kiss", "aside"), ("sultry_beckon", "aside")])

    def test_an_unmatched_aside_doesnt_block_meaning_mode(self):
        with mock.patch.object(gestures, "_three_d", return_value=True), \
                mock.patch.object(gestures, "_offered_now", return_value=ABOUTS), \
                mock.patch.object(gestures, "mode", return_value="meaning"), \
                mock.patch.object(gestures, "_emit"), \
                mock.patch.object(gestures.threading, "Thread") as thread:
            gestures.new_turn()
            gestures.from_tags("Sure thing (checks the logs) all fine.")
            gestures.after_reply("is it ok?", "Sure thing (checks the logs) all fine.")
        thread.assert_called_once()                 # the meaning check still runs

    def test_off_means_off(self):
        with mock.patch.object(gestures, "mode", return_value="off"), \
                mock.patch.object(gestures, "_emit") as emit:
            gestures.from_tags("(waves hello)")
        emit.assert_not_called()

    def _builtin(self, names):
        return {n: {"about": "x", "private": False, "lewd": n in ("bend_over", "touch_self"), "full": False}
                for n in names}

    def _line(self, band, label="", names=None):
        names = names or ["wave", "hug", "shrug", "huff", "sulk", "giggle", "bend_over", "touch_self",
                          "blow_kiss", "wink", "shy", "bounce", "explain", "surprise", "cry"]
        with mock.patch.object(gestures, "mode", return_value="tags"), \
                mock.patch.object(gestures, "_three_d", return_value=True), \
                mock.patch.object(gestures, "builtin", return_value=self._builtin(names)), \
                mock.patch.object(gestures, "clips", return_value=[]), \
                mock.patch.object(gestures, "_band", return_value=(band, label)), \
                mock.patch("mind.mood.tame", return_value=False):
            return gestures.prompt_line()

    def test_a_short_list_of_names_only(self):
        line = self._line("warm")
        self.assertIn("[wave]", line)
        self.assertIn("[hug]", line)
        self.assertNotIn("(x", line)                  # no descriptions to copy
        self.assertLessEqual(line.count("["), 8)
        self.assertLess(len(line) / 4, 70)            # tokens, roughly
        self.assertNotIn("asterisks", line)           # no advice on how to write

    def test_it_fits_her_mood(self):
        self.assertIn("[huff]", self._line("grudge"))
        self.assertNotIn("[hug]", self._line("grudge"))
        self.assertNotIn("[bend_over]", self._line("warm"))
        self.assertIn("[bend_over]", self._line("lewd"))
        import re

        self.assertEqual(re.search(r"\[(\w+)\]", self._line("neutral", "sad")).group(1), "cry")

    def test_the_limit_is_a_setting(self):
        with mock.patch.object(gestures.config, "PORTRAIT_GESTURES_OFFERED", 3, create=True):
            self.assertEqual(self._line("warm").count("["), 3)

if __name__ == "__main__":
    unittest.main()
