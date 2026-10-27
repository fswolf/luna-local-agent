"""Her voice, in and out: the front door to the voice package.

This file keeps the parts everything else calls (load_models, transcribe,
speak, speak_queue, Player) and re-exports the rest, so `speech.X` works
for anything that used to live here. The pieces:

    voice/listen.py     recording you, the room calibration, VAD
    voice/tts.py        turning her words into sound (Kokoro), lip sync
    voice/playback.py   the mic and speakers (PortAudio, afplay on a Mac)
    voice/bargein.py    cutting her off while she talks, the wake word
"""
import queue
import threading
import requests
import sounddevice as sd  # noqa: F401  (speech.sd: tests and /mic reach the device layer through here)
from core import interrupts
from core import logbook
import ui
from concurrent.futures import ThreadPoolExecutor
from faster_whisper import WhisperModel
from collections import deque
from config import TTS_URL, STT_MODEL, STT_LANGUAGE
from voice.bargein import _watch_for_barge_in, barge_in_available
from voice.listen import _load_vad
from voice.playback import _play
from voice.tts import _set_reachable, _speakable, _split_chunks, _synthesize
from voice import tts
from voice.tts import (  # noqa: F401  re-exported: speech.X keeps working
    MAX_TTS_CHARS,
    _decode,
    _lip_stop,
    _lip_sync,
    _mood_pitch,
    _mood_speed,
    _pronounce,
    _shift_pitch,
    server_label,
)
from voice.playback import (  # noqa: F401  re-exported: speech.X keeps working
    AFPLAY,
    _afplay,
    _afplay_once,
    _afplay_rate,
    _audio_devices,
    _audio_warned,
    _close_mic,
    _device_rate,
    _mic_lock,
    _mic_streams,
    _native_rate,
    _open_mic,
    _play_afplay,
    _resample,
    _reset_portaudio,
    _start_playback,
    _use_afplay,
)
from voice.listen import (  # noqa: F401  re-exported: speech.X keeps working
    ABSOLUTE_FLOOR,
    BLOCK_SIZE,
    CALIBRATION_SECONDS,
    CONTINUE_MULTIPLIER,
    MIN_SPEECH_SECONDS,
    NOISE_CEILING,
    PRE_ROLL_SECONDS,
    SMOOTHING,
    START_MULTIPLIER,
    VAD_BLOCK_SIZE,
    _INPUT_WAV,
    _calibrate,
    _record_energy,
    _record_silero,
    _rms,
    levels,
    record_audio,
)
from voice.bargein import (  # noqa: F401  re-exported: speech.X keeps working
    BARGE_IN_ARM_TIMEOUT,
    BARGE_IN_CALIBRATION_SECONDS,
    BARGE_IN_FLOOR,
    _playing,
    _speech_probability,
    wait_for_wake_word,
)
from voice import playback, listen, bargein  # noqa: F401

# The rest are deliberately NOT imported by value. /set can change them
# mid-session, and `from config import X` takes a copy that never hears
# about it - so the values you actually tune by ear are read off the
# config module each time they're used.

whisper = None

# Whisper takes a few seconds to load. It used to happen before the TUI
# existed, so every launch began with a blank terminal; now it loads on
# a worker and this says whether it has finished.
models_ready = False

# One worker: synthesize the next chunk while the current one plays.
_pool = ThreadPoolExecutor(max_workers=1)


def ready():
    return models_ready


def load_models():
    global whisper, models_ready

    whisper = WhisperModel(STT_MODEL, device="cpu", compute_type="int8")

    _load_vad()

    models_ready = True

    try:
        response = requests.get(f"{TTS_URL}/health", timeout=5)
        response.raise_for_status()
        _set_reachable(bool(response.json().get("ok")))
    except Exception as e:
        _set_reachable(False, str(e))

    return tts.tts_ok


# Whisper emits these over near-silence. Harmless when you press a key
# to talk; in open mode the mic is always armed, so without this Luna
# would answer a room tone every few seconds.
_HALLUCINATIONS = {
    "you", "thank you.", "thanks for watching!", "thank you for watching!",
    "bye.", "bye bye.", ".", "..", "...", "okay.", "oh.", "uh", "um",
    "please subscribe", "subtitles by the amara.org community",
}


def transcribe(filename):
    if not filename:
        return ""

    segments, _info = whisper.transcribe(
        filename,
        language=STT_LANGUAGE,
        vad_filter=True,
        # Without this, Whisper carries its previous output forward as
        # context and can loop the same phrase on a noisy clip.
        condition_on_previous_text=False,
    )

    text = "".join(segment.text for segment in segments).strip()

    if text.lower().strip(" .!?,") in {
        h.strip(" .!?,") for h in _HALLUCINATIONS
    }:
        return ""

    return text


def speak(text):
    """Speak a complete string. Used where the whole reply is already
    in hand - reminders, startup notices."""
    pieces = _split_chunks(text or "")

    if not pieces:
        return

    inbox = queue.Queue()

    for piece in pieces:
        inbox.put(piece)

    inbox.put(None)

    # Inside a turn (an approval question) it's the turn's to stop; on
    # its own (a reminder, the greeting) it gets a Stop of its own, so
    # HOME stops it and nothing it does touches anyone else's.
    with interrupts.ensure("speak") as stop:
        speak_queue(inbox, stop)


def speak_queue(inbox, stop=None):
    """Speak sentences as they arrive on a queue, terminated by None.

    This is the streaming path. The producer is the model itself, still
    generating, so the first sentence usually reaches the speaker while
    the rest of the reply is still being written - which is the whole
    difference between a voice assistant that answers and one that
    pauses first.

    Synthesis runs on the pool while the previous chunk is still
    playing, so the gap between sentences stays inaudible.

    stop: the interrupts.Stop that silences it (default: this thread's).
    """
    stop = stop or interrupts.current()
    pending = deque()
    done = False

    try:
        while True:
            # Keep one synthesis in flight ahead of playback. More than
            # one gains nothing: the server renders them serially.
            while not done and len(pending) < 2:
                try:
                    item = inbox.get(timeout=0.05)
                except queue.Empty:
                    break

                if item is None:
                    done = True
                    break

                for piece in _split_chunks(_speakable(item)):
                    if _speakable(piece):
                        pending.append(_pool.submit(_synthesize, piece))

            if stop.speaking.is_set():
                return

            if not pending:
                if done:
                    return

                continue

            future = pending.popleft()

            try:
                samples, rate = future.result()
            except RuntimeError as e:
                # Server down mid-reply. Say so once and stop; the text
                # is already on screen, so nothing is actually lost.
                ui.add_message("system", str(e))
                return
            except Exception as e:
                logbook.warn("tts", "a chunk couldn't be made or decoded, skipped: %s", e)
                continue

            if stop.speaking.is_set() or not _play(samples, rate, stop):
                return
    finally:
        for future in pending:
            future.cancel()


class Player:
    """A speaker you can hand sentences to while they're still being
    written, and stop mid-word.

    main.py holds one of these for the length of a turn. Playback runs
    on its own thread so the model can keep generating into it.
    """

    def __init__(self, barge_in=True, stop=None):
        # Whose stop silences it: the turn's (interrupts.Stop). Barge-in
        # sets this one, and only this one.
        self._stop = stop or interrupts.current()
        self._inbox = queue.Queue()
        self._thread = None
        self._listener = None
        self._stop_listener = threading.Event()
        self._barge_in = barge_in

    def say(self, sentence):
        if self._stop.speaking.is_set():
            return

        if self._thread is None:
            ui.set_status("Speaking...")
            self._thread = threading.Thread(
                target=speak_queue, args=(self._inbox, self._stop), daemon=True,
            )
            self._thread.start()

            if self._barge_in and barge_in_available():
                self._listener = threading.Thread(
                    target=_watch_for_barge_in, args=(self._stop_listener, self._stop),
                    daemon=True,
                )
                self._listener.start()

        self._inbox.put(sentence)

    def wait(self):
        """Block until everything queued has been spoken."""
        if self._thread is None:
            return

        self._inbox.put(None)
        self._thread.join()
        self._thread = None

        self._stop_listener.set()

        if self._listener is not None:
            self._listener.join(timeout=1.0)
            self._listener = None

    @property
    def started(self):
        return self._thread is not None


# Values the pieces reassign while running, read live from where they're kept
# (a copy taken at import would never change).
_LIVE = {'_vad_model': listen, 'tts_error': tts, 'tts_ok': tts, 'vad_backend': listen}


def __getattr__(name):
    if name in _LIVE:
        return getattr(_LIVE[name], name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
