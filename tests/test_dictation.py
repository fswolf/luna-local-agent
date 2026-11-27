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
        self.record_audio.assert_called_once_with("auto", on_audio=None, max_seconds=assistant.DICTATION_MAX_SECONDS)
        self.respond.assert_not_called()
        self.ui.add_message.assert_not_called()

    def test_no_speech_is_empty(self):
        self.record_audio.return_value = None
        self.assertEqual(assistant.dictation("auto"), "")
        self.transcribe.assert_not_called()

    def test_stopped_while_recording_is_none(self):
        def stopped(mode, **_kw):
            interrupts.current().stop(speaking=True, generating=True, listening=True)
            return "/tmp/x.wav"
        self.record_audio.side_effect = stopped
        self.assertIsNone(assistant.dictation("manual"))
        self.transcribe.assert_not_called()

    def test_mic_marked_open_only_while_recording(self):
        seen = []
        self.record_audio.side_effect = lambda mode, **_kw: seen.append(interrupts.recording()) or "/tmp/x.wav"
        assistant.dictation("auto")
        self.assertEqual(seen, [True])
        self.assertFalse(interrupts.recording())

    def test_a_failure_is_said_and_none(self):
        self.transcribe.side_effect = RuntimeError("whisper fell over")
        self.assertIsNone(assistant.dictation("auto"))
        self.assertIn("whisper fell over", self.ui.add_message.call_args[0][1])

    def test_longer_than_a_spoken_turn(self):
        assistant.dictation("manual")
        self.assertGreaterEqual(self.record_audio.call_args.kwargs["max_seconds"], 3600)

    def test_words_as_you_talk(self):
        import numpy as np
        from voice import drafts

        said = []

        def recording(mode, on_audio=None, **_kw):
            for _ in range(3):
                on_audio([np.zeros(16000, dtype=np.float32)])
                box.step()
            return "/tmp/x.wav"

        reads = iter(["hello", "hello there", "hello there"])
        box = drafts.Drafts(said.append, read=lambda audio: next(reads))
        with mock.patch.object(drafts, "Drafts", return_value=box), \
             mock.patch.object(box, "start", return_value=box):
            self.record_audio.side_effect = recording
            self.assertEqual(assistant.dictation("auto", on_draft=said.append), "hello there")
        self.assertEqual(said, ["hello", "hello there"])          # each change once, then the final words

    def test_no_drafts_when_live_text_is_off(self):
        from voice import drafts
        with mock.patch.object(drafts, "on", return_value=False):
            assistant.dictation("auto", on_draft=lambda w: None)
        self.assertIsNone(self.record_audio.call_args.kwargs["on_audio"])


class LongDrafts(unittest.TestCase):
    def test_a_long_stretch_is_settled_not_read_again(self):
        import numpy as np
        from voice import drafts

        lengths, said = [], []
        def read(audio):
            lengths.append(len(audio) / 16000)
            return f"part{len(lengths)}"
        box = drafts.Drafts(said.append, read=read)
        box.feed([np.zeros(int(16000 * 25), dtype=np.float32)])    # past WINDOW: settled
        box.step()
        box.feed([np.zeros(16000 * 3, dtype=np.float32)])
        box.step()
        self.assertEqual(lengths, [25.0, 3.0])                       # the second pass reads only what's new
        self.assertEqual(said, ["part1", "part1 part2"])

    def test_starting_over_drops_the_old_part(self):
        import numpy as np
        from voice import drafts

        said = []
        box = drafts.Drafts(said.append, read=lambda audio: f"{len(audio) // 16000}s")
        box.feed([np.zeros(16000 * 3, dtype=np.float32)])
        box.step()
        box.feed(None)                                              # silero failed: the fallback starts afresh
        box.feed([np.zeros(16000 * 2, dtype=np.float32)])
        box.step()
        self.assertEqual(said, ["3s", "2s"])

    def test_a_pass_from_before_a_restart_is_dropped(self):
        import numpy as np
        from voice import drafts

        said = []
        box = drafts.Drafts(said.append, read=lambda audio: box.feed(None) or "old words")
        box.feed([np.zeros(16000 * 25, dtype=np.float32)])
        box.step()
        self.assertEqual((said, box._settled_at, box._settled), ([], 0, ""))


if __name__ == "__main__":
    unittest.main()
