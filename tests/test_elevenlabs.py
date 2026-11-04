"""ElevenLabs as her voice (voice/elevenlabs.py): the request it makes, the
sound it turns the answer into, and what it says when something's missing
or refused. No network: requests is mocked.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

import config
from voice import elevenlabs


class Answer:
    def __init__(self, status=200, content=b"", data=None):
        self.status_code, self.content, self._data = status, content, data
        self.text = "" if data is None else str(data)

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


class ElevenLabs(unittest.TestCase):
    def setUp(self):
        patches = {"TTS_PROVIDER": "elevenlabs", "ELEVENLABS_VOICE_ID": "v123",
                   "ELEVENLABS_MODEL": "eleven_flash_v2_5", "ELEVENLABS_STABILITY": None,
                   "ELEVENLABS_SIMILARITY": None}
        for k, v in patches.items():
            p = mock.patch.object(config, k, v, create=True)
            p.start()
            self.addCleanup(p.stop)
        env = mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret"})
        env.start()
        self.addCleanup(env.stop)

    def test_synthesize(self):
        pcm = np.array([0, 16384, -32768, 32767], dtype="<i2").tobytes()
        with mock.patch("requests.post", return_value=Answer(content=pcm)) as post:
            samples, rate = elevenlabs.synthesize("hi there", speed=3.0)
        self.assertEqual(rate, 24000)
        np.testing.assert_allclose(samples, [0, 0.5, -1.0, 32767 / 32768], atol=1e-6)
        url = post.call_args[0][0]
        kwargs = post.call_args[1]
        self.assertTrue(url.endswith("/v1/text-to-speech/v123"))
        self.assertEqual(kwargs["params"], {"output_format": "pcm_24000"})
        self.assertEqual(kwargs["headers"]["xi-api-key"], "secret")
        self.assertEqual(kwargs["json"]["model_id"], "eleven_flash_v2_5")
        self.assertEqual(kwargs["json"]["voice_settings"], {"speed": 1.2})     # squeezed into 0.7-1.2

    def test_refusals_are_explained(self):
        with mock.patch("requests.post", return_value=Answer(401, data={"detail": {"message": "invalid api key"}})):
            with self.assertRaises(RuntimeError) as caught:
                elevenlabs.synthesize("hi")
        self.assertIn("API key was refused", str(caught.exception))
        self.assertIn("invalid api key", str(caught.exception))

    def test_missing_key_or_voice(self):
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}), \
                mock.patch.object(elevenlabs, "CREDENTIALS_FILE", os.path.join(tempfile.mkdtemp(), "none.json")):
            self.assertIn("no ElevenLabs API key", elevenlabs.why_not())
            self.assertFalse(elevenlabs.health()[0])
        with mock.patch.object(config, "ELEVENLABS_VOICE_ID", ""):
            self.assertIn("/voice", elevenlabs.why_not())

    def test_key_file(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "elevenlabs.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"api_key": " filekey "}')
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}), \
                mock.patch.object(elevenlabs, "CREDENTIALS_FILE", path):
            self.assertEqual(elevenlabs.api_key(), "filekey")

    def test_unreachable_marks_her_voice_offline(self):
        import requests
        from voice import tts

        with mock.patch("requests.post", side_effect=requests.exceptions.ConnectionError("down")), \
                mock.patch.object(tts, "_set_reachable") as reach:
            with self.assertRaises(RuntimeError):
                tts._synthesize("hello")
        reach.assert_called_with(False, mock.ANY)

    def test_not_set_up_reads_as_offline(self):
        from voice import tts

        with mock.patch.object(config, "ELEVENLABS_VOICE_ID", ""), \
                mock.patch("requests.post") as post, mock.patch.object(tts, "_set_reachable") as reach:
            with self.assertRaises(RuntimeError):
                tts._synthesize("hello")
        post.assert_not_called()
        reach.assert_called_with(False, mock.ANY)

    def test_tts_goes_through_elevenlabs_without_kokoro_marks(self):
        from voice import tts

        pcm = np.zeros(10, dtype="<i2").tobytes()
        with mock.patch.object(config, "PRONOUNCE", {"nya": "nja"}, create=True), \
                mock.patch("requests.post", return_value=Answer(content=pcm)) as post, \
                mock.patch.object(tts, "_set_reachable"):
            samples, rate = tts._synthesize("nya nya")
        self.assertEqual(post.call_args[1]["json"]["text"], "nya nya")      # no [nya](/nja/)
        self.assertEqual(rate, 24000)

    def test_voices_and_find(self):
        pages = [Answer(data={"voices": [{"voice_id": "a1", "name": "Rachel", "category": "premade"}],
                              "has_more": True, "next_page_token": "t"}),
                 Answer(data={"voices": [{"voice_id": "b2", "name": "Luna Clone", "category": "cloned"}],
                              "has_more": False, "next_page_token": None})]
        with mock.patch("requests.get", side_effect=pages):
            listed = elevenlabs.voices()
        self.assertEqual([v[1] for v in listed], ["a1", "b2"])
        self.assertEqual(elevenlabs.find("rachel", listed), ("Rachel", "a1"))
        self.assertEqual(elevenlabs.find("luna", listed), ("Luna Clone", "b2"))
        self.assertEqual(elevenlabs.find("b2", listed), ("Luna Clone", "b2"))
        self.assertIsNone(elevenlabs.find("nobody", listed))


if __name__ == "__main__":
    unittest.main()
