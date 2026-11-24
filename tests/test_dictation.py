"""core.assistant.dictation: the chat page's mic records and transcribes,
then hands the words back instead of answering them."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.offline  # noqa: F401,E402

from core import assistant, interrupts  # noqa: E402


class Dictation(unittest.TestCase):
    def setUp(self):
        for target, value in (("speech.ready", True), ("record_audio", "/tmp/x.wav"), ("transcribe", " hello there ")):
            p = mock.patch.object(assistant, target.split(".")[-1], return_value=value) if "." not in target \
                else mock.patch.object(assistant.speech, "ready", return_value=value)
            self.addCleanup(p.stop)
            setattr(self, target.replace(".", "_"), p.start())
        for name in ("respond", "ui"):
            p = mock.patch.object(assistant, name)
            self.addCleanup(p.stop)
            setattr(self, name, p.start())

    def test_words_back_never_answered(self):
        self.assertEqual(assistant.dictation("auto"), "hello there")
        self.record_audio.assert_called_once_with("auto")
        self.respond.assert_not_called()
        self.ui.add_message.assert_not_called()

    def test_no_speech_is_empty(self):
        self.record_audio.return_value = None
        self.assertEqual(assistant.dictation("auto"), "")
        self.transcribe.assert_not_called()

    def test_stopped_while_recording_is_none(self):
        def stopped(mode):
            interrupts.current().stop(speaking=True, generating=True, listening=True)
            return "/tmp/x.wav"
        self.record_audio.side_effect = stopped
        self.assertIsNone(assistant.dictation("manual"))
        self.transcribe.assert_not_called()

    def test_mic_marked_open_only_while_recording(self):
        seen = []
        self.record_audio.side_effect = lambda mode: seen.append(interrupts.recording()) or "/tmp/x.wav"
        assistant.dictation("auto")
        self.assertEqual(seen, [True])
        self.assertFalse(interrupts.recording())

    def test_a_failure_is_said_and_none(self):
        self.transcribe.side_effect = RuntimeError("whisper fell over")
        self.assertIsNone(assistant.dictation("auto"))
        self.assertIn("whisper fell over", self.ui.add_message.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
