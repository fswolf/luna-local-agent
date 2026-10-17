"""Lovense: machines thrust through their own tool, capped and building up
from slow; a toy that vibrates and thrusts does both in one command, and
each part stops on its own time. A fake Remote app; no toy.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import time
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from plugins import lovense as lv  # noqa: E402

TOYS = {"g1": {"name": "gravity", "fullFunctionNames": ["Vibrate", "Thrusting"]},
        "l1": {"name": "lush", "fullFunctionNames": ["Vibrate"]}}


class Plan(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.patches = [mock.patch.dict(lv._state, {"toys": TOYS, "connected": True}),
                        mock.patch.object(lv, "_post", side_effect=self.sent.append)]
        for p in self.patches:
            p.start()
        lv._plan.clear()
        lv._sent.clear()

    def tearDown(self):
        lv._plan.clear()
        lv._sent.clear()
        for p in self.patches:
            p.stop()

    def test_what_each_toy_can_do(self):
        self.assertEqual(lv._functions("g1"), {"Vibrate", "Thrusting"})
        self.assertEqual(lv._functions(""), {"Vibrate", "Thrusting"})
        self.assertEqual(lv._functions("l1"), {"Vibrate"})

    def test_vibrate_and_thrust_in_one_command(self):
        now = time.monotonic()
        lv._plan["g1"] = {"vibe": (12, now + 5), "move": (8, now + 10, now - 10, 3)}
        self.assertEqual(lv._action("g1", now), ("Vibrate:12,Thrusting:8", 10))

    def test_motion_builds_up(self):
        now = time.monotonic()
        lv._plan["g1"] = {"move": (10, now + 10, now, 4)}
        start = lv._action("g1", now)[0]
        middle = lv._action("g1", now + 2)[0]
        full = lv._action("g1", now + 5)[0]
        self.assertEqual((start, middle, full), ("Thrusting:2", "Thrusting:5", "Thrusting:10"))

    def test_one_part_ending_leaves_the_other(self):
        now = time.monotonic()
        lv._plan["g1"] = {"vibe": (12, now + 1), "move": (8, now + 10, now - 10, 0)}
        self.assertEqual(lv._action("g1", now + 2)[0], "Thrusting:8")
        lv._plan["g1"] = {"vibe": (12, now + 10), "move": (8, now + 1, now - 10, 0)}
        self.assertEqual(lv._action("g1", now + 2)[0], "Vibrate:12")

    def test_a_toy_that_cant_thrust_isnt_asked_to(self):
        now = time.monotonic()
        lv._plan["l1"] = {"vibe": (5, now + 5), "move": (8, now + 5, now - 10, 0)}
        self.assertEqual(lv._action("l1", now)[0], "Vibrate:5")

    def test_sent_with_a_safety_timer_then_stopped(self):
        now = time.monotonic()
        lv._plan["g1"] = {"move": (8, now + 2.2, now - 10, 0)}
        lv._apply("g1")
        self.assertEqual(self.sent[-1]["action"], "Thrusting:8")
        self.assertEqual(self.sent[-1]["timeSec"], 3)                  # the app stops it even if Luna doesn't
        lv._plan["g1"] = {"move": (8, now - 1, now - 10, 0)}           # time's up
        lv._apply("g1")
        self.assertEqual(self.sent[-1]["action"], "Stop")
        self.assertNotIn("g1", lv._plan)

    def test_stop_all_clears_everything(self):
        lv._plan["g1"] = {"vibe": (5, time.monotonic() + 30)}
        lv.stop_all_toys()
        self.assertEqual(lv._plan, {})
        self.assertEqual(self.sent[-1]["action"], "Stop")

    def test_motion_has_its_own_lower_cap(self):
        with mock.patch.object(lv, "settings", return_value=dict(lv.DEFAULTS)):
            self.assertEqual(lv._motion_caps(), (10, 3.0))


if __name__ == "__main__":
    unittest.main()
