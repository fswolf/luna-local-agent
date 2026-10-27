"""Turning her words into sound: the Kokoro server, chunking, pronunciation,
mood speed and pitch, and the lip-sync events.

Part of the voice package; voice/speech.py is the front door.
"""
import io
import re
import unicodedata
import requests
import numpy as np
from core import logbook
import ui
from scipy.io.wavfile import read as read_wav
import config
from config import TTS_URL, TTS_ADDRESS

# Set by load_models(); main.py surfaces it in the UI so a dead TTS
# server is obvious at startup instead of on the first reply.
tts_ok = False
tts_error = ""


def server_label():
    """The VServer line: address, plus whether it answered."""
    return TTS_ADDRESS if tts_ok else f"{TTS_ADDRESS} [offline]"


def _set_reachable(ok, error=""):
    """Track reachability so the header reflects reality mid-session -
    if the server dies (or comes back) you see it on the next reply."""
    global tts_ok, tts_error

    changed = ok != tts_ok
    tts_ok = ok
    tts_error = error

    if changed:
        try:
            ui.set_voice_server(server_label())
        except Exception:
            pass

# The server truncates at 1200 chars, so split below that and stitch
# the pieces back together on playback.
MAX_TTS_CHARS = 1000


# ---------------------------------------------------------------------------
# Text-to-speech over HTTP
#
# The client speaks a three-endpoint contract and nothing more:
#
#   POST /tts   {"text", "voice", "speed"}  -> WAV bytes
#   GET  /health                            -> {"ok": true}
#   GET  /voices                            -> the available voices
#
# kokoro-reader is what it talks to by default, but any server
# answering that works - point tts.url somewhere else and nothing here
# needs to know.
# ---------------------------------------------------------------------------
def _split_chunks(text):
    """Break text into <= MAX_TTS_CHARS pieces on sentence boundaries."""
    pieces = []

    for sentence in re.split(r"(?<=[.!?…])\s+|\n+", text.strip()):
        sentence = sentence.strip()

        if not sentence:
            continue

        # A single monster sentence still has to be cut somewhere.
        while len(sentence) > MAX_TTS_CHARS:
            cut = sentence.rfind(" ", 0, MAX_TTS_CHARS)

            if cut <= 0:  # rfind returns -1 when there's no space to break on
                cut = MAX_TTS_CHARS

            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()

        if not pieces or len(pieces[-1]) + len(sentence) + 1 > MAX_TTS_CHARS:
            pieces.append(sentence)
        else:
            pieces[-1] = f"{pieces[-1]} {sentence}"

    return [p for p in pieces if p]


def _decode(payload):
    """WAV bytes -> (float32 samples in [-1, 1], sample rate).

    Deliberately not assuming 16-bit PCM. Python's `wave` module can't
    even open a float32 WAV - it raises "unknown format: 3" - and most
    PyTorch speech models emit float32 natively, so hardcoding <i2 meant
    the client only worked with servers that converted on the way out.
    Reading the dtype and scaling by it costs three lines and means any
    server answering the contract works, whatever it hands back.
    """
    rate, data = read_wav(io.BytesIO(payload))

    # Read the type *before* downmixing: averaging channels promotes
    # ints to float, and then the scaling below would treat a 16-bit
    # sample of 16383 as a float amplitude of 16383 and clip it to a
    # square wave.
    dtype = data.dtype
    kind = dtype.kind

    # Mono. Two speakers talking at once is not what anybody wanted.
    if data.ndim > 1:
        data = data.mean(axis=1)

    if kind == "f":
        samples = data.astype(np.float32)
    elif kind == "u":
        # 8-bit WAV is unsigned, centred on 128.
        samples = (data.astype(np.float32) - 128.0) / 128.0
    elif kind == "i":
        # Scale by the width of whatever integer type it came in as.
        samples = data.astype(np.float32) / float(
            1 << (8 * dtype.itemsize - 1)
        )
    else:
        raise RuntimeError(f"unsupported audio format from the TTS server: {dtype}")

    return np.clip(samples, -1.0, 1.0), rate


# How she's feeling nudges how she sounds - a few percent, on top of
# whatever tts.speed and tts.pitch are set to. Imported lazily and
# wrapped: mood is decoration, and nothing here may be the reason she
# stops speaking.
def _mood_speed():
    try:
        from mind import mood

        return mood.voice_tint()[0]
    except Exception:
        return 1.0


def _mood_pitch():
    try:
        from mind import mood

        return mood.voice_tint()[1]
    except Exception:
        return 0.0


def _shift_pitch(samples, semitones):
    """Move the pitch, and the formants with it.

    Deliberately the naive version: resample the audio, then declare the
    result to be at the original rate. That moves pitch and formants
    together, which is what makes a voice read as a *different person* -
    younger or older - rather than the same person singing higher.

    A formant-preserving shift is the more sophisticated tool and the
    wrong one here. It keeps the speaker's identity and only moves the
    note, which is what you want for music and not at all what you want
    for "give me a younger-sounding character".

    Linear interpolation rather than a windowed resampler: this runs on
    every chunk in the streaming path, the shifts in use are small, and
    at 24 kHz the aliasing it introduces sits above anything the voice
    is doing.
    """
    if abs(semitones) < 0.01 or len(samples) < 2:
        return samples

    # Twelve semitones to an octave; an octave is a doubling.
    ratio = 2.0 ** (semitones / 12.0)
    wanted = int(len(samples) / ratio)

    if wanted < 2:
        return samples

    position = np.linspace(0, len(samples) - 1, wanted)

    return np.interp(position, np.arange(len(samples)), samples).astype(np.float32)


def _speakable(text):
    """What's left of a sentence once the things meant for the eye are
    gone: emoji, markdown asterisks and backticks, and the ~ of "Mrrp~"
    (tts.strip_tilde - Kokoro says "tilde", some voices stretch the word
    instead). Kokoro reads emoji out loud otherwise ("crescent moon",
    "sparkles", "paw prints"). The screen keeps them; only the voice
    loses them. Returns "" when nothing speakable is left."""
    out = []

    for ch in str(text or ""):
        code = ord(ch)
        if (unicodedata.category(ch) in ("So", "Sk", "Cs", "Co")
                or 0x1F000 <= code <= 0x1FAFF          # emoji and pictographs
                or 0x2600 <= code <= 0x27BF             # symbols, dingbats (sparkles)
                or code in (0x200D, 0xFE0E, 0xFE0F, 0x20E3)):   # joiners, variation selectors
            out.append(" ")
        elif ch in "*_`#|<>^" or (ch == "~" and getattr(config, "TTS_STRIP_TILDE", True)):
            out.append(" ")
        else:
            out.append(ch)

    text = re.sub(r"\s+", " ", "".join(out))
    text = re.sub(r"\s+([,.!?;:])", r"\1", text).strip()

    return text if re.search(r"[0-9A-Za-z\u00C0-\uFFFF]", text) else ""


def _pronounce(text):
    """agent.json "pronounce" applied for the voice: each word (any case, its
    last letter stretched - "nyaaa" counts as "nya") becomes Kokoro's
    [word](/phonemes/) override, so she says her cat sounds instead of
    spelling them out. Only the voice gets this; the screen keeps the word."""
    for word, phonemes in (getattr(config, "PRONOUNCE", None) or {}).items():
        word, phonemes = str(word).strip(), str(phonemes).strip().strip("/")
        if not word or not phonemes:
            continue
        pattern = rf"(?<![\w\[])({re.escape(word)}{re.escape(word[-1])}*)(?![\w\]])"
        text = re.sub(pattern, lambda m: f"[{m.group(1)}](/{phonemes}/)", text, flags=re.IGNORECASE)

    return text


def _synthesize(text):
    """POST one chunk to /tts and decode the WAV it returns."""
    text = _pronounce(text)
    try:
        response = requests.post(
            f"{TTS_URL}/tts",
            json={"text": text, "voice": config.VOICE,
                  "speed": config.TTS_SPEED * _mood_speed()},
            timeout=180,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        _set_reachable(False, str(e))
        logbook.error("tts", "POST %s/tts failed: %s", TTS_URL, e)

        raise RuntimeError(
            f"TTS server unreachable at {TTS_URL}: {e}"
        ) from e

    _set_reachable(True)

    samples, rate = _decode(response.content)
    samples = _shift_pitch(samples, config.TTS_PITCH + _mood_pitch())

    return np.clip(samples * config.TTS_VOLUME, -1.0, 1.0), rate


def _lip_sync(samples, rate, fps=30):
    """What the portrait's mouth needs for one chunk: loudness and
    hissiness (zero-crossing rate) per frame. Sent only while a page is
    watching - with none open it's skipped entirely."""
    try:
        from web import livefeed

        if not livefeed.watching():
            return

        hop = max(1, int(rate / fps))
        n = len(samples) // hop
        frames = np.asarray(samples[:n * hop], dtype=np.float32).reshape(n, hop)
        rms = np.sqrt((frames ** 2).mean(axis=1))
        env = np.clip(rms / 0.12, 0, 1) ** 0.7
        zcr = (np.abs(np.diff(np.signbit(frames).astype(np.int8), axis=1)).sum(axis=1) / hop)
        livefeed.emit("voice", fps=fps, env=[round(float(x), 2) for x in env],
                      zcr=[round(float(x), 3) for x in zcr])
    except Exception:
        pass  # decoration - never the reason she goes quiet


def _lip_stop():
    try:
        from web import livefeed

        livefeed.emit("voice", stop=True)
    except Exception:
        pass
