"""Her morning coffee (coffee.py) and the pose studio's prop placement
(livefeed.prop_entry, the gesture file's prop fields). Nothing real is
touched: the day's cup is kept in a temporary file and the portrait events
are caught instead of sent.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import coffee  # noqa: E402
import config  # noqa: E402
import livefeed  # noqa: E402


class Coffee(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.events = []
        self.nudges = []
        coffee._state.update(on=False, since=0.0, sip_at=0.0, sips=0)
        self.patches = [
            mock.patch.object(coffee, "STATE_FILE", os.path.join(self.tmp, "coffee.json")),
            mock.patch.object(coffee, "_emit", lambda kind, **d: self.events.append((kind, d))),
            mock.patch.object(coffee, "_watching", lambda: True),
            mock.patch.object(coffee, "_someone_here", lambda: True),
            mock.patch.object(coffee, "_busy", lambda: False),
            mock.patch.object(coffee, "morning", lambda hour=None: True),
            mock.patch("mood._nudge", lambda **kw: self.nudges.append(kw)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        coffee._state.update(on=False)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_morning_window(self):
        self.patches[5].stop()
        try:
            with mock.patch.object(config, "PORTRAIT_COFFEE_FROM", 5, create=True), \
                 mock.patch.object(config, "PORTRAIT_COFFEE_TO", 11, create=True):
                self.assertTrue(coffee.morning(5))
                self.assertTrue(coffee.morning(10))
                self.assertFalse(coffee.morning(11))
                self.assertFalse(coffee.morning(3))
            # a window over midnight (a night owl's coffee)
            with mock.patch.object(config, "PORTRAIT_COFFEE_FROM", 22, create=True), \
                 mock.patch.object(config, "PORTRAIT_COFFEE_TO", 2, create=True):
                self.assertTrue(coffee.morning(23))
                self.assertTrue(coffee.morning(1))
                self.assertFalse(coffee.morning(12))
        finally:
            self.patches[5].start()

    def test_once_a_day(self):
        coffee.tick(now=100)
        self.assertTrue(coffee.holding())
        self.assertEqual(self.events[0], ("prop", {"name": "mug", "on": True}))
        self.assertTrue(coffee.had_today())
        coffee.finish()
        self.events.clear()
        coffee.tick(now=200)
        self.assertFalse(coffee.holding())            # already had one today
        self.assertEqual(self.events, [])

    def test_waits_for_someone(self):
        with mock.patch.object(coffee, "_someone_here", lambda: False):
            coffee.tick(now=100)
        self.assertFalse(coffee.holding())
        with mock.patch.object(coffee, "_watching", lambda: False):
            coffee.tick(now=100)
        self.assertFalse(coffee.holding())
        with mock.patch.object(config, "PORTRAIT_COFFEE", False, create=True):
            coffee.tick(now=100)
        self.assertFalse(coffee.holding())

    def test_sips_and_finishes(self):
        with mock.patch.object(config, "PORTRAIT_COFFEE_MINUTES", 10, create=True), \
             mock.patch.object(config, "PORTRAIT_COFFEE_WAKE", 0.05, create=True):
            coffee.begin(now=0)
            coffee.tick(now=10)                          # too soon for the first sip
            self.assertEqual(coffee._state["sips"], 0)
            coffee.tick(now=60)
            self.assertEqual(coffee._state["sips"], 1)
            self.assertIn(("gesture", {"name": "coffee_sip", "src": "coffee"}), self.events)
            self.assertEqual(self.nudges[0]["energy"], 0.05)
            with mock.patch.object(coffee, "_busy", lambda: True):
                coffee.tick(now=500)                     # mid-turn: no sip over her words
            self.assertEqual(coffee._state["sips"], 1)
            coffee.tick(now=601)                         # ten minutes: done
        self.assertFalse(coffee.holding())
        self.assertEqual(self.events[-1], ("prop", {"name": "mug", "on": False}))

    def test_start_clears_a_stale_mug(self):
        with mock.patch("threading.Thread"):
            coffee._state["thread"] = None
            coffee.start()
            coffee._state["thread"] = None
        self.assertEqual(self.events[0], ("prop", {"name": "mug", "on": False}))

    def test_begin_twice(self):
        self.assertTrue(coffee.begin(now=0))
        self.assertFalse(coffee.begin(now=1))
        self.assertTrue(coffee.finish())
        self.assertFalse(coffee.finish())
        self.assertFalse(coffee.sip())


class PropPlacement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "portrait", "props"))
        open(os.path.join(self.tmp, "portrait", "props", "mug.glb"), "wb").close()
        self.p = mock.patch.object(config, "BASE_DIR", self.tmp)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_entry(self):
        name, e = livefeed.prop_entry({"name": "mug", "hand": "left", "at": [0.01, -2, 0.03],
                                       "turn": [1.5, 3.1, 0], "scale": 0.74})
        self.assertEqual(name, "mug")
        self.assertEqual(e, {"hand": "left", "at": [0.01, -0.5, 0.03], "turn": [1.5, 3.1, 0], "scale": 0.74})

    def test_refused(self):
        for bad in ({"name": "cup", "at": [0, 0, 0], "turn": [0, 0, 0]},              # no cup.glb
                    {"name": "../mug", "at": [0, 0, 0], "turn": [0, 0, 0]},
                    {"name": "mug", "hand": "foot", "at": [0, 0, 0], "turn": [0, 0, 0]},
                    {"name": "mug", "at": [0, 0], "turn": [0, 0, 0]},
                    {"name": "mug", "at": ["x", 0, 0], "turn": [0, 0, 0]},
                    "mug"):
            with self.assertRaises((ValueError, TypeError)):
                livefeed.prop_entry(bad)

    def test_list(self):
        open(os.path.join(self.tmp, "portrait", "props", "Bad Name.glb"), "wb").close()
        self.assertEqual(livefeed.props_list(), ["mug"])

    def test_gesture_fields(self):
        _name, text = livefeed.gesture_file({"name": "pick", "keys": [[0, {"rightHand": [0, 0, 0]}]],
                                             "prop": "mug", "prop_at": 0.9, "hold": True})
        self.assertIn('prop: "mug"', text)
        self.assertIn("prop_at: 0.9", text)
        self.assertIn("hold: true", text)
        _name, text = livefeed.gesture_file({"name": "pick", "keys": [[0, {"rightHand": [0, 0, 0]}]],
                                             "hold": "yes"})
        self.assertNotIn("hold", text)                   # only a real true
        with self.assertRaises(ValueError):
            livefeed.gesture_file({"name": "pick", "keys": [[0, {"rightHand": [0, 0, 0]}]], "prop": "a b"})


if __name__ == "__main__":
    unittest.main()
