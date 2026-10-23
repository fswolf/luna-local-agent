"""EXPERIMENTAL, UNTESTED ON REAL HARDWARE: ESPHome voice satellites as
relay stations, with no Home Assistant in between.

Devices like FutureProofHomes' Satellite1, Home Assistant's Voice Preview
Edition or a ReSpeaker Lite run ESPHome, which serves a small API on port
6053. Home Assistant is only a program that connects to it and asks for
the audio; Luna does the same here, with the library Home Assistant uses
(aioesphomeapi):

    the device hears its wake word itself (and cancels its own echo)
    -> streams 16 kHz audio to Luna -> she notices you stopped talking
    -> transcribes, knows whose voice it was, answers like any spoken turn
    -> speaks it with Kokoro and hands the device a link to play it from
       (served on the stations' setup port, home network only)

Switched on by listing devices in config.json, beside the stations:

    "station": {"enabled": true,
                "satellites": [{"name": "kitchen", "host": "192.168.0.50",
                                "key": "<the device's API encryption key>"}]}

A device answers one controller: take it out of Home Assistant (or don't
let Home Assistant use its voice) while Luna has it. Needs the satellites
extra (installer --extras satellites, pip install aioesphomeapi).

Written from aioesphomeapi's API and Home Assistant's own satellite code,
not yet run against a device: expect rough edges.
"""
import asyncio
import os
import secrets
import sys
import tempfile
import threading
import time

import config
import logbook

PORT = 6053
SILENCE_END = 0.8          # seconds of quiet after speech that end what you said
MAX_LISTEN = 15.0          # never listen longer than this
NO_SPEECH = 6.0            # nothing said at all after the wake word: give up
LOUD = 500                 # 16-bit RMS that counts as speech (a quiet room is ~50-150)
CLIP_KEEP = 300            # seconds a reply stays fetchable

_clips = {}                # id -> (wav bytes, made at)
_state = {"loop": None, "thread": None, "devices": {}}


def available():
    try:
        import aioesphomeapi  # noqa: F401

        return True
    except ImportError:
        return False


def configured():
    """The satellites listed in config.json (station.satellites)."""
    found = (config.settings.get("station") or {}).get("satellites") or []
    return [d for d in found if isinstance(d, dict) and d.get("host")]


# ---------------------------------------------------------------------------
# Her reply, for the device to fetch
# ---------------------------------------------------------------------------
def clip(cid):
    """A reply's WAV by id (the stations' setup server serves it), or None."""
    now = time.time()
    for k in [k for k, (_w, t) in _clips.items() if now - t > CLIP_KEEP]:
        _clips.pop(k, None)
    got = _clips.get(cid)
    return got[0] if got else None


def _publish(wav):
    cid = secrets.token_urlsafe(12)
    _clips[cid] = (wav, time.time())
    import station

    return station.setup_url().rstrip("/") + f"/sat/{cid}.wav"


# ---------------------------------------------------------------------------
# One spoken request, from wake word to reply
# ---------------------------------------------------------------------------
class Listen:
    """Collects the device's audio and decides when you've stopped talking."""

    def __init__(self):
        self.pcm = bytearray()
        self.started = time.monotonic()
        self.heard_at = None
        self.quiet_since = None
        self.done = False

    def add(self, chunk, now=None):
        """Take a chunk of 16-bit mono PCM. True once you've finished."""
        import numpy as np

        now = time.monotonic() if now is None else now
        self.pcm += chunk
        samples = np.frombuffer(bytes(chunk[: len(chunk) // 2 * 2]), dtype="<i2").astype(np.float32)
        loud = samples.size and float(np.sqrt(np.mean(samples * samples))) > LOUD
        if loud:
            self.heard_at = self.heard_at or now
            self.quiet_since = None
        elif self.heard_at and self.quiet_since is None:
            self.quiet_since = now
        if (self.heard_at and self.quiet_since and now - self.quiet_since >= SILENCE_END) \
                or now - self.started >= MAX_LISTEN:
            self.done = True
        return self.done

    def nothing_said(self, now=None):
        now = time.monotonic() if now is None else now
        return not self.heard_at and now - self.started >= NO_SPEECH

    def wav(self):
        import io
        import wave

        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(bytes(self.pcm))
        return out.getvalue()


def _no_screen(kind, title, lines, warn=False):
    """Permission questions: a satellite has no screen to ask on, so no."""
    logbook.info("satellite", "declined %s (%s): no screen to ask on", kind, title)
    return False


def answer(name, wav):
    """Transcribe, answer and speak one request. Returns (heard, reply, reply WAV or None)."""
    import assistant
    import people
    import speech
    import station
    import ui

    fd, path = tempfile.mkstemp(suffix=".wav", prefix="luna-satellite-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(wav)
        heard = {}
        assistant._whose_voice(path, heard)
        if heard.get("enroll"):
            return "", "A voice enrolment is running at the PC. Read its lines there.", None
        text = speech.transcribe(path)
        if not text:
            return "", "", None
        speaker = people.decide(heard.get("name"), voice_checked=heard.get("score") is not None,
                                at_desk=False)      # another room: the desk camera can't tell
        who = f"{speaker}, " if speaker else ""
        logbook.info("turn", "satellite %s%s: %s", name, f" ({speaker})" if speaker else "", text[:200])
        ui.add_message("user", f"[{who}{name}] {text}")
        said = []
        assistant.respond(text, getattr(sys.modules.get("__main__"), "MODEL", None),
                          source="station", speaker=speaker, sink=said.append, approver=_no_screen)
        reply = " ".join(s.strip() for s in said if s and s.strip())
        if not reply:
            return text, "", None
        samples, rate = speech._synthesize(reply)
        return text, reply, station._wav(samples, rate)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# A device: connect, listen, reconnect
# ---------------------------------------------------------------------------
class Device:
    def __init__(self, spec):
        self.name = str(spec.get("name") or spec["host"])[:30]
        self.host = str(spec["host"])
        self.key = spec.get("key") or None
        self.port = int(spec.get("port") or PORT)
        self.client = None
        self.status = "starting"
        self.listen = None
        self.stopping = False

    def _event(self, kind, data=None):
        from aioesphomeapi import VoiceAssistantEventType as E

        try:
            self.client.send_voice_assistant_event(getattr(E, "VOICE_ASSISTANT_" + kind), data)
        except Exception as e:
            logbook.warn("satellite", "%s: couldn't send %s: %s", self.name, kind, e)

    async def _start(self, conversation_id, flags, audio_settings, wake_word):
        self.listen = Listen()
        self._event("RUN_START")
        self._event("STT_START")
        return 0                       # 0: send the audio over the API connection

    async def _audio(self, data, _second=None):
        listen = self.listen
        if listen is None or listen.done:
            return
        if listen.add(data) or listen.nothing_said():
            await self._finish()

    async def _stop(self, abort):
        if abort:
            self.listen = None
            return
        if self.listen is not None and not self.listen.done:
            self.listen.done = True
            await self._finish()

    async def _finish(self):
        listen, self.listen = self.listen, None
        if listen is None:
            return
        listen.done = True
        self._event("STT_VAD_END")
        if not listen.heard_at:
            self._event("STT_END", {"text": ""})
            self._event("RUN_END")
            return
        loop = asyncio.get_running_loop()
        try:
            heard, reply, wav = await loop.run_in_executor(None, answer, self.name, listen.wav())
        except Exception as e:
            logbook.exception("satellite", "%s: the turn failed", self.name)
            self._event("ERROR", {"code": "luna", "message": str(e)[:200]})
            self._event("RUN_END")
            return
        self._event("STT_END", {"text": heard})
        self._event("INTENT_START")
        self._event("INTENT_END", {"conversation_id": "", "continue_conversation": "0"})
        if wav:
            self._event("TTS_START", {"text": reply})
            self._event("TTS_END", {"url": _publish(wav)})
        self._event("RUN_END")

    async def run(self):
        from aioesphomeapi import APIClient

        while not self.stopping:
            gone = asyncio.Event()
            self.client = APIClient(self.host, self.port, None, noise_psk=self.key, client_info="Luna")

            async def on_stop(expected):
                gone.set()

            try:
                await self.client.connect(on_stop=on_stop, login=True)
                self.client.subscribe_voice_assistant(handle_start=self._start, handle_stop=self._stop,
                                                      handle_audio=self._audio)
                self.status = "connected"
                logbook.info("satellite", "%s (%s) connected", self.name, self.host)
                await gone.wait()
                self.status = "disconnected, retrying"
            except Exception as e:
                self.status = f"not connected: {e}"[:120]
                logbook.info("satellite", "%s: %s", self.name, self.status)
            try:
                await self.client.disconnect()
            except Exception:
                pass
            for _ in range(30):                   # try again in half a minute
                if self.stopping:
                    return
                await asyncio.sleep(1)


def start():
    """Connect every satellite in config.json. Returns (ok, message)."""
    found = configured()
    if not found:
        return False, "no satellites in config.json (station.satellites)"
    if not available():
        return False, "needs aioesphomeapi: python3 installer/install.py --extras satellites"
    if _state["thread"] is not None:
        return True, "already running"
    loop = asyncio.new_event_loop()
    _state["loop"] = loop
    threading.Thread(target=loop.run_forever, daemon=True, name="satellites").start()
    _state["thread"] = True
    for spec in found:
        device = Device(spec)
        _state["devices"][device.name] = device
        asyncio.run_coroutine_threadsafe(device.run(), loop)
    logbook.info("satellite", "experimental satellites: %s", ", ".join(_state["devices"]))
    return True, f"{len(found)} satellite(s), experimental"


def stop():
    """Hang up on every device (so it's free for the next start, or for Home
    Assistant), then stop the loop."""
    devices, _state["devices"] = list(_state["devices"].values()), {}
    loop, _state["loop"], _state["thread"] = _state["loop"], None, None
    for device in devices:
        device.stopping = True
    if loop is None:
        return

    async def hang_up():
        for device in devices:
            if device.client is not None:
                try:
                    await asyncio.wait_for(device.client.disconnect(), 3)
                except Exception:
                    pass

    try:
        asyncio.run_coroutine_threadsafe(hang_up(), loop).result(timeout=10)
    except Exception:
        pass
    loop.call_soon_threadsafe(loop.stop)


def status():
    return [{"name": d.name, "host": d.host, "status": d.status} for d in _state["devices"].values()]
