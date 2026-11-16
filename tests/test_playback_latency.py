"""Her voice plays with a roomy buffer (tts.latency, voice/playback.py): with
PortAudio's "low" the first seconds crackled while the reply was still
streaming to the screen.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

import numpy as np  # noqa: E402

from voice import playback  # noqa: E402


class Latency(unittest.TestCase):
    def _latency(self, value):
        with mock.patch("config.TTS_LATENCY", value, create=True):
            return playback._latency()

    def test_values(self):
        self.assertEqual(self._latency("high"), "high")
        self.assertEqual(self._latency(" LOW "), "low")
        self.assertEqual(self._latency("0.2"), 0.2)
        self.assertEqual(self._latency("5"), 1.0)          # held to a second
        self.assertEqual(self._latency("loud"), "high")    # nonsense falls back
        self.assertEqual(self._latency(""), "high")

    def test_play_gets_it(self):
        with mock.patch("config.TTS_LATENCY", "high", create=True), \
                mock.patch.object(playback, "_native_rate", [False]), \
                mock.patch.object(playback.sys, "platform", "linux"), \
                mock.patch.object(playback.sd, "play", create=True) as play:
            self.assertTrue(playback._start_playback(np.zeros(10, dtype=np.float32), 24000))
        self.assertEqual(play.call_args.kwargs.get("latency"), "high")


if __name__ == "__main__":
    unittest.main()
