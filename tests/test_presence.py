"""Presence (senses/presence.py) and the people she knows (senses/people.py), without a
camera: arrivals and absences, where she looks, matching face prints,
and the quiet room. Prints go to a temporary folder.

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

import config  # noqa: E402
from senses import people  # noqa: E402
from senses import presence  # noqa: E402


class Tracker(unittest.TestCase):
    def test_first_sight_is_an_arrival_with_no_gap(self):
        t = presence.Tracker(now=0)
        self.assertEqual(t.update(True, 5), ("arrived", None))
        self.assertIsNone(t.update(True, 6))

    def test_a_blink_away_is_not_leaving(self):
        t = presence.Tracker(now=0)
        t.update(True, 1)
        t.update(False, 3)                       # looked down for 2 s
        self.assertTrue(t.present)
        self.assertIsNone(t.update(True, 4))

    def test_coming_back_reports_how_long_you_were_gone(self):
        t = presence.Tracker(now=0)
        t.update(True, 10)
        t.update(False, 10 + presence.ABSENT_AFTER)
        self.assertFalse(t.present)
        self.assertEqual(t.update(True, 1210), ("arrived", 1200))

    def test_nobody_for_counts_from_start_or_last_seen(self):
        t = presence.Tracker(now=100)
        self.assertEqual(t.nobody_for(160), 60)
        t.update(True, 200)
        self.assertEqual(t.nobody_for(205), 0)
        t.update(False, 200 + presence.ABSENT_AFTER)
        self.assertEqual(t.nobody_for(500), 300)


class Gaze(unittest.TestCase):
    def test_centre_looks_ahead_and_slightly_down(self):
        g = presence.gaze_from((280, 120, 80, 120), 640, 360)   # centred
        self.assertAlmostEqual(g["x"], 0.0, places=2)
        self.assertLess(abs(g["y"]), 0.2)

    def test_picture_left_is_screen_right(self):
        # the webcam faces you: someone on the picture's left sits to
        # the screen's right
        self.assertGreater(presence.gaze_from((20, 100, 80, 100), 640, 360)["x"], 0.5)
        self.assertLess(presence.gaze_from((540, 100, 80, 100), 640, 360)["x"], -0.5)

    def test_clamped(self):
        g = presence.gaze_from((0, 0, 1, 1), 640, 360)
        self.assertLessEqual(g["x"], 1.0)
        self.assertLessEqual(g["y"], 1.0)


class People(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(people, "FOLDER", self.tmp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_enrolled_face_matches_and_a_stranger_doesnt(self):
        people.add_prints("Shannon", "face", [[1, 0, 0, 0], [0.9, 0.1, 0, 0]], pronouns="she/her")
        people.add_prints("Ryan", "face", [[0, 1, 0, 0]])
        self.assertEqual(people.match("face", [0.95, 0.05, 0, 0], 0.36)[0], "Shannon")
        self.assertEqual(people.match("face", [0, 0.9, 0.1, 0], 0.36)[0], "Ryan")
        self.assertIsNone(people.match("face", [0, 0, 0, 1], 0.36)[0])
        self.assertEqual(people.pronouns("Shannon"), "she/her")

    def test_prints_from_another_model_are_ignored(self):
        people.add_prints("Ryan", "face", [[1, 0, 0, 0]])
        self.assertIsNone(people.match("face", [1, 0, 0], 0.1)[0])

    def test_prints_are_bounded(self):
        total = people.add_prints("Ryan", "face", [[1, 0]] * (people.MAX_PRINTS + 5))
        self.assertEqual(total, people.MAX_PRINTS)

    def test_forget_one_kind_or_everything(self):
        people.add_prints("Ryan", "face", [[1, 0]])
        people.add_prints("Ryan", "voice", [[0, 1]])
        self.assertTrue(people.forget("Ryan", "face"))
        self.assertNotIn("face", people.load("Ryan"))
        self.assertIn("voice", people.load("Ryan"))
        self.assertTrue(people.forget("Ryan"))
        self.assertEqual(people.everyone(), {})
        self.assertFalse(people.forget("Ryan"))

    def test_names_cant_escape_the_folder(self):
        people.add_prints("../../etc/passwd", "face", [[1, 0]])
        self.assertEqual(os.listdir(self.tmp), ["etc-passwd.json"])


class Quiet(unittest.TestCase):
    def setUp(self):
        self.saved = presence._tracker
        presence._tracker = presence.Tracker(now=0)

    def tearDown(self):
        presence._tracker = self.saved

    def test_never_quiet_while_presence_is_off(self):
        with mock.patch.object(presence, "running", return_value=False):
            self.assertFalse(presence.nobody_here())
            self.assertIsNone(presence.gaze())

    def test_quiet_after_the_room_has_been_empty(self):
        with mock.patch.object(presence, "running", return_value=True), \
                mock.patch.object(config, "PRESENCE_QUIET", True, create=True), \
                mock.patch.object(config, "PRESENCE_QUIET_AFTER", 5, create=True), \
                mock.patch.object(presence.time, "monotonic", return_value=60):
            self.assertFalse(presence.nobody_here())
        with mock.patch.object(presence, "running", return_value=True), \
                mock.patch.object(config, "PRESENCE_QUIET", True, create=True), \
                mock.patch.object(config, "PRESENCE_QUIET_AFTER", 5, create=True), \
                mock.patch.object(presence.time, "monotonic", return_value=301):
            self.assertTrue(presence.nobody_here())

    def test_quiet_can_be_switched_off(self):
        with mock.patch.object(presence, "running", return_value=True), \
                mock.patch.object(config, "PRESENCE_QUIET", False, create=True), \
                mock.patch.object(presence.time, "monotonic", return_value=10_000):
            self.assertFalse(presence.nobody_here())


class Arrivals(unittest.TestCase):
    def setUp(self):
        self.saved = dict(presence._state)
        presence._state.update(greeted_at=-1e9, model="m", first=None)

    def tearDown(self):
        presence._state.clear()
        presence._state.update(self.saved)

    def _arrive(self, gap, now=10_000):
        from mind import reflect

        with mock.patch.object(presence.threading, "Thread") as thread, \
                mock.patch.object(reflect, "idle_seconds", return_value=1e9), \
                mock.patch.object(presence.time, "monotonic", return_value=now), \
                mock.patch.object(config, "PRESENCE_GREET", True, create=True), \
                mock.patch.object(config, "PRESENCE_GREET_AFTER", 20, create=True):
            presence._arrived(gap)
        return thread

    def test_greets_after_a_long_break_only(self):
        self.assertFalse(self._arrive(60).called)          # a minute away
        self.assertTrue(self._arrive(30 * 60).called)      # half an hour

    def test_one_greeting_per_cooldown(self):
        self.assertTrue(self._arrive(30 * 60, now=10_000).called)
        self.assertFalse(self._arrive(30 * 60, now=10_060).called)

    def test_first_sight_runs_the_held_startup_greeting(self):
        ran = []
        presence.on_first_arrival(lambda: ran.append(1))
        thread = self._arrive(None)
        self.assertTrue(thread.called)
        kw = thread.call_args.kwargs
        kw["target"](*kw["args"])
        self.assertEqual(ran, [1])
        self.assertIsNone(presence._state["first"])


class GreetingRules(unittest.TestCase):
    """The parts of saying hi that went wrong in review."""

    def setUp(self):
        self.saved = dict(presence._state)
        presence._state.update(greeted_at=-1e9, model="m", first=None)

    def tearDown(self):
        presence._state.clear()
        presence._state.update(self.saved)

    def test_talking_to_her_out_of_view_isnt_being_away(self):
        from mind import reflect

        with mock.patch.object(presence.threading, "Thread") as thread, \
                mock.patch.object(reflect, "idle_seconds", return_value=30), \
                mock.patch.object(config, "PRESENCE_GREET", True, create=True), \
                mock.patch.object(config, "PRESENCE_GREET_AFTER", 20, create=True):
            presence._arrived(3 * 3600)          # off camera for hours, but talking 30 s ago
        self.assertFalse(thread.called)

    def test_held_startup_greeting_skips_once_anyone_talked(self):
        from mind import reflect

        greeted = []
        with mock.patch.object(presence, "running", return_value=True), \
                mock.patch.object(presence, "present", return_value=False), \
                mock.patch.object(reflect.time, "sleep"), \
                mock.patch.object(reflect, "_busy", return_value=False), \
                mock.patch.object(reflect, "_transcript", return_value=[]), \
                mock.patch.object(reflect.notebook, "latest_episode",
                                  return_value={"ended": "2000-01-01T00:00:00"}), \
                mock.patch.object(reflect, "datetime") as dt:
            from datetime import datetime as real
            dt.now.return_value = real(2000, 1, 1, 2, 0, 0)
            dt.fromisoformat = real.fromisoformat
            reflect.greet("m")
        held = presence._state["first"]
        self.assertIsNotNone(held)
        reflect.touch()                           # he typed before showing up
        with mock.patch.object(reflect, "greet", side_effect=lambda m: greeted.append(m)):
            held()
        self.assertEqual(greeted, [])

    def test_a_failing_held_greeting_is_quiet(self):
        def boom():
            raise RuntimeError("model gone")
        presence._run_quietly(boom)               # no exception out


if __name__ == "__main__":
    unittest.main()
