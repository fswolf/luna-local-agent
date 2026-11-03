"""Error handling in ui/, voice/, input/, senses/ and tts/: the failures that
used to print over the screen, loop, hang the popup or go quiet, each held
to what it does now. No audio hardware, no network.

    python -m unittest tests.test_errors_ui_voice        (from the repo folder)
"""
import io
import os
import sys
import threading
import time
import types
import unittest
import wave
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import numpy as np  # noqa: E402

import config  # noqa: E402
import ui  # noqa: E402
from ui import approval, tools_pane  # noqa: E402
from ui.shared import view  # noqa: E402
from voice import bargein, listen, playback, ptt, tts  # noqa: E402


class _FakeApp:
    def invalidate(self):
        pass


class Approval(unittest.TestCase):
    """A timeout typed as inf or 1e10 raised OverflowError from the wait,
    left the popup up for good and broke every repaint of its title."""

    def setUp(self):
        self._app = view.app
        view.app = _FakeApp()

    def tearDown(self):
        view.app = self._app
        view.approval = None

    def _ask_and_answer(self, timeout, answer=True):
        result = []
        thread = threading.Thread(
            target=lambda: result.append(approval.ask_approval("t", ["x"], timeout=timeout)), daemon=True)
        thread.start()
        for _ in range(100):
            if view.approval is not None:
                break
            time.sleep(0.01)
        self.assertIsNotNone(view.approval)
        approval._approval_title()                 # must not raise mid-paint
        approval._answer_approval(answer)
        thread.join(2)
        self.assertFalse(thread.is_alive())
        return result[0]

    def test_huge_and_infinite_timeouts(self):
        for timeout in (float("inf"), 1e10, float("nan"), -5):
            with self.subTest(timeout=timeout):
                self.assertTrue(self._ask_and_answer(timeout))
                self.assertIsNone(view.approval)

    def test_popup_comes_down_when_the_wait_fails(self):
        with mock.patch.object(threading.Event, "wait", side_effect=OverflowError("boom")):
            with self.assertRaises(OverflowError):
                approval.ask_approval("t", ["x"], timeout=10)
        self.assertIsNone(view.approval)
        self.assertFalse(ui.approving())

    def test_title_with_an_infinite_deadline(self):
        view.approval = {"deadline": float("inf"), "allow_all": None}
        self.assertIn("Permission", approval._approval_title())


class HandsFreeMic(unittest.TestCase):
    """A dead mic sent hands-free round its loop every 0.6 s for ever."""

    def setUp(self):
        ptt._hands_free = True
        playback.clear_mic_error()

    def tearDown(self):
        ptt._hands_free = False
        playback.clear_mic_error()

    def test_stops_after_a_few_failures_with_one_message(self):
        calls = []

        def failing_turn(model, mode):
            calls.append(mode)
            playback._mic_error[0] = "Error opening InputStream: device unavailable"
            return False

        with mock.patch.object(ptt.wakeword, "available", return_value=False), \
                mock.patch.object(ptt, "assistant_task", failing_turn), \
                mock.patch.object(ptt, "_pause") as paused, \
                mock.patch("ui.add_message") as said, \
                mock.patch("ui.set_status"):
            ptt._hands_free_loop(None)

        self.assertEqual(len(calls), ptt.MIC_FAILURES_TO_STOP)
        self.assertEqual(said.call_count, 1)
        self.assertIn("Hands-free stopped", said.call_args[0][1])
        self.assertIn("device unavailable", said.call_args[0][1])
        self.assertFalse(ptt._hands_free)
        # backed off between tries, longer each time
        waits = [c[0][0] for c in paused.call_args_list]
        self.assertEqual(waits, sorted(waits))
        self.assertGreaterEqual(waits[0], 2.0)

    def test_wake_word_mic_failure_backs_off_too(self):
        with mock.patch.object(ptt.wakeword, "available", return_value=True), \
                mock.patch.object(ptt.speech, "wait_for_wake_word", return_value=None) as waited, \
                mock.patch.object(ptt, "assistant_task") as turn, \
                mock.patch.object(ptt, "_pause"), \
                mock.patch("ui.add_message") as said, \
                mock.patch("ui.set_status"):
            ptt._hands_free_loop(None)

        self.assertEqual(waited.call_count, ptt.MIC_FAILURES_TO_STOP)
        turn.assert_not_called()
        self.assertEqual(said.call_count, 1)

    def test_bad_settle_seconds_doesnt_kill_the_loop(self):
        turns = []

        def turn(model, mode):
            turns.append(1)
            if len(turns) >= 2:
                ptt._hands_free = False
            return False

        with mock.patch.object(config, "STT_SETTLE_SECONDS", float("inf")), \
                mock.patch.object(ptt.wakeword, "available", return_value=False), \
                mock.patch.object(ptt, "assistant_task", turn), \
                mock.patch.object(ptt, "_pause") as paused, \
                mock.patch("ui.add_message"), mock.patch("ui.set_status"):
            ptt._hands_free = True
            ptt._hands_free_loop(None)
        self.assertEqual(len(turns), 2)
        self.assertEqual(paused.call_args_list[0][0][0], 60)

    def test_wake_word_returns_none_when_the_mic_wont_open(self):
        with mock.patch("voice.wakeword.available", return_value=True), \
                mock.patch("voice.wakeword.reset"), \
                mock.patch.object(bargein, "_open_mic", side_effect=OSError("no device")), \
                mock.patch("ui.set_status"), mock.patch("ui.add_message") as said:
            self.assertIsNone(bargein.wait_for_wake_word(lambda: False))
        said.assert_not_called()

    def test_open_mic_remembers_why(self):
        with mock.patch.object(playback.sd, "InputStream", side_effect=OSError("gone")):
            with self.assertRaises(OSError):
                playback._open_mic(512)
        self.assertEqual(playback.mic_error(), "gone")


class Numbers(unittest.TestCase):
    """Typed settings that reached int(), sleep or 2 ** x as inf or NaN."""

    def test_pitch_is_clamped(self):
        samples = np.linspace(-0.5, 0.5, 2400, dtype=np.float32)
        for semitones in (1e5, float("inf"), float("nan"), -1e5):
            with self.subTest(semitones=semitones):
                out = tts._shift_pitch(samples, semitones)
                self.assertTrue(np.isfinite(out).all())
                self.assertGreater(len(out), 1)

    def test_decode_drops_nan(self):
        buffer = io.BytesIO()
        from scipy.io.wavfile import write

        write(buffer, 24000, np.array([0.1, np.nan, -0.2], dtype=np.float32))
        samples, rate = tts._decode(buffer.getvalue())
        self.assertTrue(np.isfinite(samples).all())

    def test_silero_iterator_gets_finite_numbers(self):
        made = {}

        class FakeIterator:
            def __init__(self, model, **kw):
                made.update(kw)

            def reset_states(self):
                pass

        fake = types.ModuleType("silero_vad")
        fake.VADIterator = FakeIterator
        with mock.patch.dict(sys.modules, {"silero_vad": fake}), \
                mock.patch.object(config, "STT_SILENCE_SECONDS", float("inf")), \
                mock.patch.object(config, "STT_VAD_THRESHOLD", float("nan")), \
                mock.patch.object(listen, "_open_mic", side_effect=OSError("stop here")):
            with self.assertRaises(OSError):
                listen._record_silero("auto")
        self.assertEqual(made["min_silence_duration_ms"], 60000)
        self.assertTrue(0.1 <= made["threshold"] <= 0.9)


class TtsServerAnswers(unittest.TestCase):
    """A 4xx/5xx is the server saying no, not the server being offline."""

    def _post(self, status, body=b"", text=""):
        response = mock.Mock(status_code=status, content=body, text=text)
        return mock.patch("requests.post", return_value=response)

    def test_refusal_isnt_unreachable(self):
        with self._post(422, text='{"error": "no such voice"}'), mock.patch("ui.set_voice_server"):
            with self.assertRaises(RuntimeError) as caught:
                tts._synthesize("hello")
        self.assertIn("refused", str(caught.exception))
        self.assertIn("422", str(caught.exception))
        self.assertNotIn("unreachable", str(caught.exception))
        self.assertTrue(tts.tts_ok)

    def test_speed_sent_is_clamped(self):
        for speed in (0.0, -1.0, float("inf"), float("nan")):
            with self.subTest(speed=speed), self._post(500, text="x") as posted, \
                    mock.patch.object(config, "TTS_SPEED", speed), mock.patch("ui.set_voice_server"):
                with self.assertRaises(RuntimeError):
                    tts._synthesize("hello")
                sent = posted.call_args.kwargs["json"]["speed"]
                self.assertTrue(0.25 <= sent <= 4.0)


class SpeakQueueSaysSo(unittest.TestCase):
    """Every chunk failing the same way used to be silent on screen."""

    def test_one_message_for_a_failing_voice(self):
        import queue

        from voice import speech

        inbox = queue.Queue()
        for line in ("One.", "Two.", "Three."):
            inbox.put(line)
        inbox.put(None)
        stop = types.SimpleNamespace(speaking=threading.Event())
        with mock.patch.object(speech, "_synthesize", side_effect=ValueError("not a wav")), \
                mock.patch("core.logbook.tell") as told:
            speech.speak_queue(inbox, stop)
        self.assertTrue(told.called)
        self.assertIn("Couldn't play her voice", told.call_args[0][0])


def _wav(seconds=0.2, rate=8000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x01\x00" * int(seconds * rate))
    return buffer.getvalue()


class QwenStretch(unittest.TestCase):
    """A speed of 0 or less sent the frame loop round for ever."""

    def test_bad_speeds_finish(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                        "tts", "qwen3"))
        try:
            import qwen_server
        except Exception as e:                    # its own dependencies aren't here
            self.skipTest(f"qwen_server didn't import: {e}")
        finally:
            sys.path.pop(0)
        audio = _wav()
        for speed in (0, -1, "fast", float("nan"), float("inf"), None):
            with self.subTest(speed=speed):
                out = qwen_server.stretch(audio, speed)
                self.assertTrue(out.startswith(b"RIFF"))


class ToolsPaneGuards(unittest.TestCase):
    """A plugin that raised in a repaint broke the pane on every frame."""

    def test_raising_plugin_still_draws(self):
        class Bad:
            name = "bad"
            module = types.SimpleNamespace(SERVER="x")

            def running(self):
                raise RuntimeError("socket gone")

            def available(self):
                raise RuntimeError("socket gone")

            def why_unavailable(self):
                raise RuntimeError("socket gone")

        fake = types.SimpleNamespace(names=lambda: ["bad"], get=lambda n: Bad() if n == "bad" else None)
        with mock.patch.dict(sys.modules, {"plugins": fake}), \
                mock.patch.object(config, "plugin_settings", return_value={}):
            groups = tools_pane._with_plugin_switches([])
        rows = [row for _label, members, _l, _t in groups for row in members]
        self.assertEqual(rows[0][0], "bad plugin")
        self.assertEqual(rows[0][3], "unavailable")

    def test_plugin_start_error_is_reported(self):
        class Bad:
            name = "bad"

            def running(self):
                return False

            def start(self, model):
                raise RuntimeError("no game")

        fake = types.SimpleNamespace(get=lambda n: Bad())
        threads = []
        real_thread = threading.Thread

        def capture(*a, **kw):
            t = real_thread(*a, **kw)
            threads.append(t)
            return t

        with mock.patch.dict(sys.modules, {"plugins": fake}), \
                mock.patch.object(tools_pane.threading, "Thread", capture), \
                mock.patch.object(tools_pane, "add_message") as said:
            tools_pane._toggle_plugin("bad", False)
            for t in threads:
                t.join(2)
        texts = [c[0][1] for c in said.call_args_list]
        self.assertTrue(any("couldn't connect: no game" in t for t in texts), texts)


class Keyboard(unittest.TestCase):
    """os._exit from the global Esc left the terminal in raw mode."""

    def test_escape_leaves_a_running_window_alone(self):
        try:
            from input import linux_keyboard
        except Exception as e:
            self.skipTest(f"no linux keyboard module here: {e}")
        old = view.app
        view.app = _FakeApp()
        try:
            with mock.patch.object(linux_keyboard.os, "_exit") as exited:
                linux_keyboard._escape()
            exited.assert_not_called()
        finally:
            view.app = old

    def test_lost_keyboard_is_reopened_then_given_up(self):
        try:
            from input import linux_keyboard
        except Exception as e:
            self.skipTest(f"no linux keyboard module here: {e}")
        with mock.patch.object(linux_keyboard, "_find_keyboards_evdev", side_effect=[["kb"], RuntimeError("none")] + [RuntimeError("none")] * 20), \
                mock.patch.object(linux_keyboard, "_listen", side_effect=OSError(19, "No such device")), \
                mock.patch.object(linux_keyboard.time, "sleep") as slept, \
                mock.patch("ui.set_controls") as said:
            linux_keyboard._run_evdev(None)
        self.assertTrue(said.called)
        self.assertGreaterEqual(slept.call_count, 1)


class Senses(unittest.TestCase):
    def test_desktop_run_survives_undecodable_output(self):
        from senses import desktop

        ok, text = desktop._run([sys.executable, "-c",
                                 "import sys; sys.stdout.buffer.write(b'caf\\xe9')"])
        self.assertTrue(ok)
        self.assertTrue(text.startswith("caf"))


if __name__ == "__main__":
    unittest.main()
