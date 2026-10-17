"""The turn loop every game shares (plugins/_game.py): a turn only when
she's playing, nobody's spoken for a while and none is running; a turn
that fails doesn't stop the loop; stopping ends the session once.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import threading
import time
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from plugins import _game  # noqa: E402


def until(check, seconds=3):
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return False


class Loop(unittest.TestCase):
    def setUp(self):
        self.state, self.turns, self.playing = {}, [], [True]
        self.finished = []
        self.patches = [mock.patch("reflect.idle_seconds", return_value=999),
                        mock.patch("plugins._playlog.finished", side_effect=self.finished.append),
                        mock.patch.object(_game, "ERROR_PAUSE", 0.05)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        self.loop.stop()
        for p in self.patches:
            p.stop()

    def make(self, step=None, **kw):
        self.loop = _game.Loop("game", self.state, step or (lambda: self.turns.append(1)),
                               playing=lambda: self.playing[0], **kw)
        return self.loop

    def test_takes_turns_while_playing(self):
        self.make().start()
        self.loop.wake()
        self.assertTrue(until(lambda: self.turns))
        self.assertFalse(self.state["busy"])

    def test_waits_for_quiet(self):
        with mock.patch("reflect.idle_seconds", return_value=3):
            self.make(quiet=lambda: 10).start()
            self.loop.wake()
            time.sleep(0.2)
            self.assertEqual(self.turns, [])

    def test_a_failed_turn_is_noted_and_the_loop_goes_on(self):
        calls = []

        def step():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("the game went away")

        self.make(step).start()
        self.loop.wake()
        self.assertTrue(until(lambda: len(calls) >= 2, 5))
        self.assertIn("the game went away", self.state["error"])

    def test_stopping_play_ends_the_session(self):
        def step():
            self.playing[0] = False

        self.make(step).start()
        self.loop.wake()
        self.assertTrue(until(lambda: self.finished))
        self.assertEqual(self.finished, ["game"])

    def test_a_game_that_ends_its_own_sessions(self):
        def step():
            self.playing[0] = False

        self.make(step, ends_session=False).start()
        self.loop.wake()
        self.assertTrue(until(lambda: not self.playing[0]))
        time.sleep(0.1)
        self.assertEqual(self.finished, [])

    def test_restarting_never_runs_two_loops(self):
        gate = threading.Event()
        running = []

        def step():
            running.append(1)
            gate.wait(1)

        self.make(step).start()
        self.loop.wake()
        until(lambda: running)
        self.loop.start()               # already going: nothing new
        self.loop.wake()
        time.sleep(0.2)
        self.assertEqual(len(running), 1)
        gate.set()

    def test_session_over_waits_for_a_running_turn(self):
        _game.session_over("game", {"busy": True})
        self.assertEqual(self.finished, [])
        _game.session_over("game", {"busy": False})
        self.assertEqual(self.finished, ["game"])
        self.loop = _game.Loop("x", {}, lambda: None, playing=lambda: False)


if __name__ == "__main__":
    unittest.main()
