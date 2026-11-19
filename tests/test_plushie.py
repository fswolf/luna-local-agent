"""She hugs her plushie when she's low (life/plushie.py). The clock, her mood
and the portrait are faked and the portrait events caught.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from life import plushie  # noqa: E402


class Plushie(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.mood = "calm"
        self.full = False
        self.asleep = False
        plushie._state.update(on=False, since=0.0, next=0.0, by_hand=False, low_since=None, better_since=None, ended=None)
        self.patches = [
            mock.patch.object(plushie, "_emit", lambda kind, **d: self.events.append((kind, d))),
            mock.patch.object(plushie, "_mood", lambda: self.mood),
            mock.patch.object(plushie, "_watching", lambda: True),
            mock.patch.object(plushie, "_busy", lambda: False),
            mock.patch.object(plushie, "_walked_away", lambda: False),
            mock.patch.object(plushie, "_hands_full", lambda: self.full),
            mock.patch.object(plushie, "_asleep", lambda: self.asleep),
            mock.patch.object(plushie.random, "uniform", lambda a, b: a),
            mock.patch.object(config, "PORTRAIT_PLUSHIE", True, create=True),
            mock.patch.object(config, "PORTRAIT_PLUSHIE_MOODS", ["sad", "hurt", "sulky"], create=True),
            mock.patch.object(config, "PORTRAIT_PLUSHIE_AFTER", 60, create=True),
            mock.patch.object(config, "PORTRAIT_PLUSHIE_MINUTES", 30, create=True),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        plushie._state.update(on=False)

    def props(self):
        return [d["on"] for k, d in self.events if k == "prop" and d["name"] == "plush"]

    def test_low_for_a_minute(self):
        plushie.tick(now=100)
        self.mood = "sad"
        plushie.tick(now=110)
        plushie.tick(now=160)
        self.assertFalse(plushie.holding())
        plushie.tick(now=171)
        self.assertTrue(plushie.holding())
        self.assertEqual(self.props(), [True])
        self.assertIn("Mochi", plushie.describe(now=200))

    def test_squeezes_then_down_when_better(self):
        self.mood = "hurt"
        plushie.tick(now=0)
        plushie.tick(now=60)
        plushie.tick(now=101)                     # 40 s on: a squeeze
        self.assertIn(("gesture", {"name": "plush_squeeze", "src": "plushie"}), self.events)
        self.mood = "happy"
        plushie.tick(now=110)
        self.assertTrue(plushie.holding())        # not straight away
        plushie.tick(now=131)
        self.assertFalse(plushie.holding())
        self.assertEqual(self.props(), [True, False])
        # and not again soon, even if she's low again
        self.mood = "sad"
        plushie.tick(now=200)
        plushie.tick(now=300)
        self.assertFalse(plushie.holding())
        plushie.tick(now=131 + 20 * 60)
        self.assertTrue(plushie.holding())

    def test_not_with_her_hands_full(self):
        self.full = True
        self.mood = "sad"
        plushie.tick(now=0)
        plushie.tick(now=100)
        self.assertFalse(plushie.holding())

    def test_keeps_him_asleep(self):
        self.mood = "sad"
        plushie.tick(now=0)
        plushie.tick(now=60)
        self.asleep = True
        self.mood = "sleepy"
        plushie.tick(now=200)
        plushie.tick(now=400)
        self.assertTrue(plushie.holding())

    def test_by_hand(self):
        self.assertTrue(plushie.begin(now=5))
        self.assertFalse(plushie.begin(now=6))
        plushie.tick(now=100)                     # she's fine, but you gave him to her
        self.assertTrue(plushie.holding())
        self.assertTrue(plushie.squeeze())
        self.assertTrue(plushie.finish())
        self.assertFalse(plushie.squeeze())

    def test_her_coffee_puts_him_down(self):
        from life import coffee

        plushie.begin(now=1)
        with mock.patch.object(coffee, "_emit"), mock.patch.object(coffee, "_reading", lambda: False):
            coffee.begin(now=2)
            coffee._state.update(on=False)
        self.assertFalse(plushie.holding())

    def test_command(self):
        from commands import life

        with mock.patch("ui.add_message") as said:
            self.assertTrue(life.handle("/plushie"))
            self.assertTrue(life.handle("/plushie off"))
        self.assertIn("Mochi", said.call_args_list[0][0][1])
        self.assertEqual(self.props(), [True, False])


if __name__ == "__main__":
    unittest.main()
