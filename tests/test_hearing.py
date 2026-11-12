"""Sending the recording with the words (voice/hearing.py): off by default,
only to a model that says it can hear, and a refusal falls back to words.

    python -m unittest discover tests        (from the repo folder)
"""
import base64
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE as _FAKE  # noqa: E402  (first: no real servers)

import numpy as np  # noqa: E402
from scipy.io import wavfile  # noqa: E402

import config  # noqa: E402
from core import lmstudio, turnctx  # noqa: E402
from voice import hearing  # noqa: E402


def _wav_file(seconds=1.0, rate=16000, dtype="float32"):
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    samples = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    if dtype == "int16":
        samples = (samples * 32767).astype(np.int16)
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    wavfile.write(path, rate, samples)
    return path


class Hearing(unittest.TestCase):
    def setUp(self):
        for k, v in {"STT_SEND_AUDIO": True, "STT_AUDIO_MAX_SECONDS": 30, "SAMPLE_RATE": 16000,
                     "LLM_BACKEND": "llama"}.items():
            p = mock.patch.object(config, k, v, create=True)
            p.start()
            self.addCleanup(p.stop)
        hears = mock.patch.object(lmstudio, "accepts_audio", lambda: True)
        hears.start()
        self.addCleanup(hears.stop)
        self.paths = []

    def tearDown(self):
        for p in self.paths:
            os.remove(p)

    def wav(self, **kw):
        self.paths.append(_wav_file(**kw))
        return self.paths[-1]

    def test_off_by_default(self):
        with mock.patch.object(config, "STT_SEND_AUDIO", False):
            self.assertIsNone(hearing.clip(self.wav()))
            self.assertIn("off", hearing.why_not())

    def test_clip_is_16_bit_mono_at_the_sample_rate(self):
        data = hearing.clip(self.wav(rate=48000, dtype="int16"))
        rate, samples = wavfile.read(io.BytesIO(data))
        self.assertEqual((rate, samples.dtype, samples.ndim), (16000, np.int16, 1))
        self.assertAlmostEqual(len(samples) / rate, 1.0, places=2)
        self.assertGreater(np.abs(samples).max(), 9000)          # still the tone, not silence

    def test_too_long_or_unreadable_goes_as_words(self):
        with mock.patch.object(config, "STT_AUDIO_MAX_SECONDS", 0.5):
            self.assertIsNone(hearing.clip(self.wav()))
        fd, junk = tempfile.mkstemp(suffix=".wav")
        os.write(fd, b"not a wav")
        os.close(fd)
        self.paths.append(junk)
        self.assertIsNone(hearing.clip(junk))

    def test_only_a_model_that_hears_gets_it(self):
        data = hearing.clip(self.wav())
        for answer in (False, None):
            with mock.patch.object(lmstudio, "accepts_audio", lambda a=answer: a):
                self.assertEqual(hearing.content("hi", data), "hi")
        with mock.patch.object(lmstudio, "accepts_audio", lambda: True):
            text, audio = hearing.content("hi", data)
            self.assertTrue(text["text"].endswith("hi"))
            self.assertEqual(base64.b64decode(audio["input_audio"]["data"]), data)
            self.assertEqual(hearing.why_not(), "")

    def test_words_only_and_drop(self):
        with mock.patch.object(lmstudio, "accepts_audio", lambda: True):
            message = {"role": "user", "content": hearing.content("hi", hearing.clip(self.wav()))}
        self.assertEqual(hearing.words_only(message)["content"], "hi")
        payload = {"messages": [{"role": "system", "content": "x"}, message]}
        self.assertFalse(hearing.drop(payload, RuntimeError("context full")))
        with mock.patch.object(lmstudio, "refused_audio") as deaf:
            self.assertTrue(hearing.drop(payload, RuntimeError("audio input is not supported")))
            deaf.assert_called_once()
        self.assertEqual(message["content"], "hi")                # in place

    def test_token_estimate_counts_seconds_not_base64(self):
        with mock.patch.object(lmstudio, "accepts_audio", lambda: True):
            content = hearing.content("hi", hearing.clip(self.wav(seconds=10)))
        used = lmstudio.estimate_tokens({"messages": [{"role": "user", "content": content}]})
        self.assertLess(used, 400)                                 # ~250 for the audio, not ~100k


class ATurnThatHears(unittest.TestCase):
    """A whole spoken turn through llm.ask against a fake llama-server."""

    def run_turn(self, refuse):
        import http.server

        bodies = []

        class Fake(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data":[{"id":"fake"}]}')

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                bodies.append(body)
                heard = "input_audio" in json.dumps(body)
                if refuse and heard:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error":{"message":"audio input is not supported - hint: '
                                     b'if this is unexpected, you may need to provide the mmproj"}}')
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for d in ({"choices": [{"delta": {"content": "You sound tired." if heard else "Okay."}}]},
                          {"choices": [{"delta": {}, "finish_reason": "stop"}]}):
                    self.wfile.write(b"data: " + json.dumps(d).encode() + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n")

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
        _FAKE.append(f"http://127.0.0.1:{srv.server_address[1]}/")
        path = _wav_file()
        self.addCleanup(os.remove, path)

        import llm
        from llm import streaming
        with mock.patch.object(streaming, "LM_URL", url), \
                mock.patch.object(config, "ADAPTIVE_ENABLED", False, create=True), \
                mock.patch.object(config, "STT_SEND_AUDIO", True), \
                mock.patch.dict(lmstudio._senses, {"at": 1e18, "audio": True}), \
                turnctx.begin(source="voice", recording=hearing.clip(path)):
            answer = llm.ask("I'm fine", "fake", context=[], tools_allowed=[], remember=False)
            deaf = lmstudio.accepts_audio()
            vision = lmstudio.accepts_images()
        lmstudio._senses["deaf_until"] = 0.0
        return answer, bodies, deaf, vision

    def test_the_recording_goes_with_the_words(self):
        answer, bodies, _, _ = self.run_turn(refuse=False)
        self.assertEqual(answer, "You sound tired.")
        user = bodies[0]["messages"][-1]["content"]
        self.assertEqual([p["type"] for p in user], ["text", "input_audio"])
        self.assertTrue(user[0]["text"].endswith("I'm fine"))

    def test_a_refusal_sends_the_words_again(self):
        answer, bodies, deaf, vision = self.run_turn(refuse=True)
        self.assertEqual(answer, "Okay.")
        self.assertEqual(len(bodies), 2)
        words = bodies[1]["messages"][-1]["content"]
        self.assertIsInstance(words, str)                          # words only now
        self.assertTrue(words.endswith("I'm fine"))
        self.assertNotIn("recording is attached", words)
        self.assertFalse(deaf)                                     # the rest of the turns go as words
        self.assertEqual(vision, lmstudio._senses["vision"])       # what it says about vision is untouched

    def test_the_recording_is_used_once(self):
        with mock.patch.dict(lmstudio._senses, {"at": 1e18, "audio": True}), \
                turnctx.begin(source="voice", recording=b"RIFF") as turn:
            hearing_content = []
            with mock.patch.object(hearing, "content", lambda t, r: hearing_content.append(r) or t), \
                    mock.patch("llm.turns._generate", lambda *a: "ok"), \
                    mock.patch("llm.turns._tool_rounds", lambda *a: "ok"):
                import llm
                llm.ask("one", "fake", context=[], tools_allowed=[], remember=False)
                llm.ask("two", "fake", context=[], tools_allowed=[], remember=False)
        self.assertEqual(hearing_content, [b"RIFF", None])
        self.assertIsNone(turn.recording)


if __name__ == "__main__":
    unittest.main()
