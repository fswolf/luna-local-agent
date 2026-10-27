"""Stopping her (core/interrupts.py): what a stop reaches, what it never does,
and how fast it lands. No audio, no model, no UI.

    python -m unittest discover tests        (from the repo folder)
"""
import threading
import time
import unittest
from unittest import mock

import os  # noqa: E402
import sys  # noqa: E402

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401  (first: no real servers)

from core import interrupts  # noqa: E402


class Lifetime(unittest.TestCase):
    def tearDown(self):
        self.assertFalse(interrupts.busy(kinds=("typed", "voice", "chat", "speak")),
                         "a test left a Stop open")

    def test_a_stop_before_the_turn_starts_still_lands(self):
        # Enter (or the key press) opens it; HOME comes while it waits for
        # the last reply to finish; then it runs.
        stop = interrupts.open("typed")
        interrupts.home()
        with interrupts.using(stop) as running:
            self.assertTrue(running.generating.is_set())
            self.assertTrue(running.speaking.is_set())

    def test_a_stop_never_reaches_the_next_turn(self):
        with interrupts.using(kind="typed"):
            interrupts.home()
        with interrupts.using(kind="typed") as next_turn:
            self.assertFalse(next_turn.speaking.is_set())
            self.assertFalse(next_turn.generating.is_set())

    def test_nothing_clears_anyone_elses_stop(self):
        # A reply you interrupted, then a reminder speaking on its own.
        with interrupts.using(kind="typed") as reply:
            reply.stop(speaking=True)
            with interrupts.using(kind="speak") as reminder:
                self.assertFalse(reminder.speaking.is_set())
            self.assertTrue(reply.speaking.is_set())

    def test_inside_a_turn_speaking_shares_its_stop(self):
        with interrupts.using(kind="typed") as turn:
            with interrupts.ensure("speak") as spoken:
                self.assertIs(spoken, turn)

    def test_other_threads_never_inherit_a_stop(self):
        seen = {}
        with interrupts.using(kind="typed") as turn:
            t = threading.Thread(target=lambda: seen.update(s=interrupts.current()))
            t.start()
            t.join()
        self.assertIsNot(seen["s"], turn)

    def test_outside_anything_stoppable_nothing_is_stopped(self):
        interrupts.home()
        self.assertFalse(interrupts.current().speaking.is_set())


class WhatHomeReaches(unittest.TestCase):
    def test_your_turn_stops_entirely_others_only_go_quiet(self):
        with interrupts.using(kind="typed") as yours, interrupts.using(kind="chat") as chat:
            interrupts.home()
            self.assertTrue(yours.generating.is_set() and yours.listening.is_set())
            self.assertTrue(chat.speaking.is_set())
            self.assertFalse(chat.generating.is_set())      # its answer still finishes

    def test_busy_means_one_of_your_turns(self):
        self.assertFalse(interrupts.busy())
        with interrupts.using(kind="job"):
            self.assertFalse(interrupts.busy())             # HOME starts listening, not "stop the game"
        with interrupts.using(kind="voice"):
            self.assertTrue(interrupts.busy())

    def test_busy_for_anything(self):
        with interrupts.using(kind="reminder"):
            self.assertFalse(interrupts.busy())
            self.assertTrue(interrupts.busy(kinds=None))

    def test_alarm_off_cuts_the_line_short(self):
        from life import alarm
        with interrupts.using(kind="alarm") as ringing:
            alarm._ring_stop[0] = ringing
            alarm._ringing.set()
            try:
                self.assertTrue(alarm.dismiss())
                self.assertTrue(ringing.speaking.is_set())
            finally:
                alarm._ringing.clear()
                alarm._ring_stop[0] = None

    def test_recording(self):
        with interrupts.using(kind="voice") as turn:
            self.assertFalse(interrupts.recording())
            turn.recording = True
            self.assertTrue(interrupts.recording())


class Speed(unittest.TestCase):
    def test_a_stop_wakes_a_waiter_at_once(self):
        stop = interrupts.Stop("speak")
        woke = {}

        def wait():
            started = time.monotonic()
            stop.speaking.wait(5)
            woke["after"] = time.monotonic() - started

        t = threading.Thread(target=wait)
        t.start()
        time.sleep(0.05)
        stop.stop(speaking=True)
        t.join(2)
        self.assertLess(woke["after"], 0.5)


class TheModelLoop(unittest.TestCase):
    """A stopped turn makes no new request to the model."""

    def test_no_round_after_a_stop(self):
        from llm import rounds
        payload = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
        with mock.patch.object(rounds, "_chat_completion") as asked:
            with interrupts.using(kind="typed") as turn:
                turn.stop(generating=True)
                self.assertEqual(rounds._tool_rounds(payload, "m", on_text=lambda t: None), "")
                self.assertEqual(rounds._force_prose(payload, on_text=lambda t: None), "")
                self.assertIn("interrupted", rounds._why_empty())
        asked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
