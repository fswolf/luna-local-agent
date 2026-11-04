"""Letting her hear how something was said, not only the words.

Off unless stt.send_audio is true. Whisper still turns what you said into
words, and everything that runs on words (commands, history, memory, the
transcript) keeps doing so. What changes is the message for the model: the
recording goes along with the words, the same way a screenshot goes along
when she looks at the screen. A model that takes audio (an omni model, with
its mmproj, on llama-server) then hears the tone too: a laugh, a tired
voice, sarcasm Whisper writes down as a plain sentence.

Nothing is sent to a model that can't hear. llama-server says in /props
whether the loaded model takes audio; LM Studio doesn't say, so it gets
words only. If a server turns the recording away anyway, the turn is sent
again as words and recordings stay off for ten minutes.

The recording only lives for the turn: it's in the request and nowhere
else, never in history or the transcript.
"""
import base64
import io

import numpy as np

import config
from core import lmstudio, logbook

# The words come first, so a model that ignores the audio still has the turn.
NOTE = "(Said out loud; the recording is attached, so you can hear how it was said.)"


def wanted():
    return bool(getattr(config, "STT_SEND_AUDIO", False))


def model_hears():
    return lmstudio.accepts_audio() is True


def why_not():
    """Why her model isn't getting the recordings, or "" when it is."""
    if not wanted():
        return "off - /set stt.send_audio true to send them"
    if lmstudio.audio_refused():
        return "llama-server refused a recording, so it's words only for a few minutes"
    if getattr(config, "LLM_BACKEND", "") != "llama":
        return "LM Studio doesn't take audio - it needs an omni model on llama-server"
    answer = lmstudio.accepts_audio()
    if answer is None:
        return "llama-server didn't say whether the model can hear"
    if not answer:
        return ("the loaded model can't hear - load an omni model (Qwen3-Omni, Qwen2.5-Omni, "
                "Gemma 4 E2B/E4B) with its mmproj GGUF")
    return ""


def clip(path):
    """A recording read for sending: 16-bit mono WAV bytes at SAMPLE_RATE,
    or None when it's off, her model can't hear, it's too long or it
    can't be read. Read straight away,
    while the file is still there; the desk mic reuses its file."""
    if not wanted() or not path or not model_hears():
        return None
    try:
        from scipy.io import wavfile

        rate, samples = wavfile.read(path)
        samples = np.asarray(samples)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        if samples.dtype.kind in "iu":
            info = np.iinfo(samples.dtype)
            samples = (samples.astype(np.float32) - (info.max + info.min + 1) / 2) / ((info.max - info.min + 1) / 2)
        samples = np.nan_to_num(samples.astype(np.float32))
        if not rate or not len(samples):
            return None

        seconds = len(samples) / rate
        limit = float(getattr(config, "STT_AUDIO_MAX_SECONDS", 30) or 0)
        if limit and seconds > limit:
            logbook.info("hearing", "%.0f s recording, over stt.audio_max_seconds: words only", seconds)
            return None

        target = int(getattr(config, "SAMPLE_RATE", 16000) or 16000)
        if rate != target:
            from math import gcd
            from scipy.signal import resample_poly

            g = gcd(int(rate), target)
            samples = resample_poly(samples, target // g, int(rate) // g)

        out = io.BytesIO()
        wavfile.write(out, target, (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2"))
        return out.getvalue()
    except Exception as e:
        logbook.warn("hearing", "couldn't read the recording, words only: %s", e)
        return None


def content(text, recording):
    """The user message's content: the words alone, or the words and the
    recording when there is one and her model can hear."""
    if not recording or not model_hears():
        return text
    return [{"type": "text", "text": f"{NOTE}\n{text}"},
            {"type": "input_audio",
             "input_audio": {"data": base64.b64encode(recording).decode("ascii"), "format": "wav"}}]


def words_only(message):
    """A message with any recording taken out (what's kept for /good)."""
    body = message.get("content")
    if not isinstance(body, list):
        return message
    text = " ".join(p.get("text", "") for p in body if isinstance(p, dict) and p.get("type") == "text")
    return dict(message, content=text.replace(NOTE + "\n", "", 1))


def drop(payload, error):
    """The server refused a recording: take every one out of the payload and
    say so. True when there was one to take out (send it again), False when
    the error was about something else."""
    if "audio" not in str(error).lower():
        return False
    found = False
    for m in payload.get("messages") or ():
        if isinstance(m.get("content"), list) and any(
                isinstance(p, dict) and p.get("type") == "input_audio" for p in m["content"]):
            m["content"] = words_only(m)["content"]     # in place: the turn's copies share it
            found = True
    if found:
        lmstudio.refused_audio()
        logbook.warn("hearing", "the server refused the recording, words only: %s", error)
    return found
