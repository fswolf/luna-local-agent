"""Experimental ESPHome satellites (satellites.py): when she decides you've
stopped talking, and one request from start to reply against a fake device.
No hardware here: the device and her thinking are faked.

    python -m unittest discover tests        (from the repo folder)
"""
import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import numpy as np  # noqa: E402

import config  # noqa: E402
import satellites  # noqa: E402

CHUNK = 0.032                                     # seconds per chunk, as ESPHome sends


def _chunk(loud):
    t = np.arange(int(16000 * CHUNK))
    a = (3000 * np.sin(t / 3) if loud else 40 * np.sin(t)).astype("<i2")
    return a.tobytes()


class Listening(unittest.TestCase):
    def test_ends_after_a_pause(self):
        listen, now = satellites.Listen(), 0.0
        listen.started = 0.0
        for _ in range(30):                                    # about a second of talking
            now += CHUNK
            self.assertFalse(listen.add(_chunk(True), now))
        quiet = 0
        while not listen.add(_chunk(False), now):
            now += CHUNK
            quiet += 1
        self.assertAlmostEqual(quiet * CHUNK, satellites.SILENCE_END, delta=0.1)
        self.assertTrue(listen.wav().startswith(b"RIFF"))

    def test_nothing_said(self):
        listen = satellites.Listen()
        listen.started = 0.0
        listen.add(_chunk(False), 1.0)
        self.assertFalse(listen.nothing_said(1.0))
        self.assertTrue(listen.nothing_said(satellites.NO_SPEECH + 0.1))

    def test_never_listens_forever(self):
        listen = satellites.Listen()
        listen.started = 0.0
        self.assertTrue(listen.add(_chunk(True), satellites.MAX_LISTEN))


class FakeClient:
    def __init__(self):
        self.events = []

    def send_voice_assistant_event(self, kind, data):
        self.events.append((kind.name.replace("VOICE_ASSISTANT_", ""), data))


@unittest.skipUnless(satellites.available(), "needs aioesphomeapi")
class OneRequest(unittest.TestCase):
    def test_from_wake_word_to_reply(self):
        device = satellites.Device({"name": "kitchen", "host": "192.0.2.5", "key": "k"})
        device.client = FakeClient()

        async def go():
            self.assertEqual(await device._start("c1", 0, None, None), 0)       # audio over the API
            for _ in range(20):
                await device._audio(_chunk(True))
            await device._stop(False)                                              # the device ends it

        with mock.patch.object(satellites, "answer", return_value=("hi", "Hello!", b"RIFFwav")), \
             mock.patch.object(satellites, "_publish", return_value="http://pc:8794/sat/x.wav"):
            asyncio.run(go())
        kinds = [k for k, _d in device.client.events]
        self.assertEqual(kinds, ["RUN_START", "STT_START", "STT_VAD_END", "STT_END", "INTENT_START",
                                 "INTENT_END", "TTS_START", "TTS_END", "RUN_END"])
        data = dict(device.client.events)
        self.assertEqual(data["STT_END"], {"text": "hi"})
        self.assertEqual(data["TTS_END"], {"url": "http://pc:8794/sat/x.wav"})

    def test_silence_ends_quietly(self):
        device = satellites.Device({"host": "192.0.2.5"})
        device.client = FakeClient()

        async def go():
            await device._start("c1", 0, None, None)
            await device._audio(_chunk(False))
            await device._stop(False)

        with mock.patch.object(satellites, "answer") as answer:
            asyncio.run(go())
        answer.assert_not_called()
        self.assertEqual([k for k, _d in device.client.events][-2:], ["STT_END", "RUN_END"])


class Config(unittest.TestCase):
    def test_configured_and_keys_hidden(self):
        sats = [{"name": "kitchen", "host": "192.0.2.5", "key": "secret-key"}, {"name": "no host"}]
        with mock.patch.dict(config.settings, {"station": {"satellites": sats}}):
            self.assertEqual([d["name"] for d in satellites.configured()], ["kitchen"])
        from ui import settings_pane

        self.assertNotIn("secret-key", settings_pane._show("station.satellites", sats, "dict"))

    def test_stop_hangs_up(self):
        loop = asyncio.new_event_loop()
        import threading
        threading.Thread(target=loop.run_forever, daemon=True).start()
        device = satellites.Device({"name": "kitchen", "host": "192.0.2.5"})
        device.client = mock.Mock()

        async def disconnect():
            device.hung_up = True
        device.client.disconnect = disconnect
        satellites._state.update(loop=loop, thread=True, devices={"kitchen": device})
        satellites.stop()
        self.assertTrue(getattr(device, "hung_up", False))
        self.assertTrue(device.stopping)
        self.assertEqual(satellites._state["devices"], {})

    def test_clips_expire(self):
        satellites._clips["x"] = (b"RIFF", 0)
        self.assertIsNone(satellites.clip("x"))


if __name__ == "__main__":
    unittest.main()
