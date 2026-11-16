"""tts.enabled off keeps her quiet (voice/speech.py): nothing is made or
played, the reply stays on screen, and it switches mid-conversation.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from voice import speech  # noqa: E402


class VoiceOff(unittest.TestCase):
    def test_player_stays_quiet(self):
        with mock.patch("config.TTS_ENABLED", False, create=True), \
                mock.patch.object(speech, "speak_queue") as spoke:
            player = speech.Player(barge_in=False)
            player.say("Hello there.")
            player.wait()
        self.assertFalse(player.started)
        spoke.assert_not_called()

    def test_speak_stays_quiet(self):
        with mock.patch("config.TTS_ENABLED", False, create=True), \
                mock.patch.object(speech, "speak_queue") as spoke:
            speech.speak("Reminder: stretch.")
        spoke.assert_not_called()

    def test_on_speaks(self):
        with mock.patch("config.TTS_ENABLED", True, create=True), \
                mock.patch.object(speech, "speak_queue") as spoke:
            speech.speak("Reminder: stretch.")
        spoke.assert_called_once()

    def test_a_setting_you_can_flip(self):
        from config import schema
        import config
        self.assertIn("tts.enabled", schema.BASIC)
        self.assertEqual(config.SETTINGS["tts.enabled"], ("TTS_ENABLED", True))   # no restart

    def test_switched_off_mid_reply(self):
        import queue

        inbox = queue.Queue()
        for line in ("One.", "Two.", None):
            inbox.put(line)
        played = []

        def play(samples, rate, stop):
            played.append(samples)
            speech.config.TTS_ENABLED = False      # flipped while the first sentence plays
            return True

        with mock.patch("config.TTS_ENABLED", True, create=True), \
                mock.patch.object(speech, "_synthesize", return_value=([0.0], 24000)), \
                mock.patch.object(speech, "_play", side_effect=play):
            speech.speak_queue(inbox, speech.interrupts.Stop())
        self.assertEqual(len(played), 1)

    def test_header_says_so(self):
        from ui import conversation_pane as pane

        def text():
            return "".join(t for _s, t in pane._status_lines())

        with mock.patch("config.TTS_ENABLED", False, create=True):
            self.assertIn("voice off", text())
        with mock.patch("config.TTS_ENABLED", True, create=True):
            self.assertNotIn("voice off", text())


if __name__ == "__main__":
    unittest.main()
