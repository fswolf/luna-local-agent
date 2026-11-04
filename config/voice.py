"""Her voice: the TTS server (kokoro-reader), voice, speed, pitch, volume.

Part of the config package (it was one config.py); see config/__init__.py.
"""
import os
from urllib.parse import urlparse

from .base import setting

# -------------------------
# TTS (kokoro-reader server)
# -------------------------
# Speech is synthesized by the standalone kokoro-reader server
# (github.com/fswolf/kokoro-reader), not by an in-process KPipeline.
# Start it once and every app that speaks shares the same loaded model.
#
# Optional "tts" block in agent.json:
#   "tts": { "url": "http://127.0.0.1:8899", "speed": 1.0, "volume": 1.0 }
# Named for the job, not the server. kokoro-reader is what this speaks
# to today, but the client only needs POST /tts, GET /health and GET
# /voices - anything answering that contract works, so the constants
# shouldn't be called KOKORO_*.
#
# The KOKORO_* environment variables still work, because kokoro-reader
# uses those names and it would be rude to break someone's shell.
_tts_cfg = setting("tts", {})


def _tts_env(name, fallback):
    return os.environ.get(f"TTS_{name}") or os.environ.get(f"KOKORO_{name}") \
        or fallback


TTS_URL = str(_tts_env("URL", _tts_cfg.get("url", "http://127.0.0.1:8899"))).rstrip("/")
TTS_SPEED = float(_tts_env("SPEED", _tts_cfg.get("speed", 1.0)))
TTS_VOLUME = float(_tts_env("VOLUME", _tts_cfg.get("volume", 1.0)))
# Semitones. Positive is higher and younger-sounding, negative lower and
# older. Applied here rather than in the speech server, so it works with
# whichever engine is on the port - Kokoro today, something else later.
#
# Deliberately shifts the formants along with the pitch, which is what a
# naive resample does. A formant-preserving shift keeps the same person
# sounding like themselves an octave up; moving them together is what
# reads as a different age of person, which is the point here.
TTS_PITCH = float(_tts_env("PITCH", _tts_cfg.get("pitch", 0.0)))
# How her voice reaches the speakers: "auto" is PortAudio everywhere except
# macOS, where it's afplay (PortAudio loses Bluetooth headphones there);
# "afplay" or "portaudio" forces one.
TTS_PLAYER = str(_tts_cfg.get("player", "auto")).lower()
# Drop the ~ of "Mrrp~" before speaking. Kokoro reads it out as "tilde";
# some other voices stretch the word instead, which is what she means -
# switch this off for one of those. Emoji are always left unspoken.
TTS_STRIP_TILDE = bool(_tts_cfg.get("strip_tilde", True))
VOICE = _tts_env("VOICE", setting("voice", "af_bella"))

# Where her voice comes from: "kokoro" is the speech server at tts.url
# (kokoro-reader, or anything speaking the same three endpoints);
# "elevenlabs" is ElevenLabs' cloud voices (voice/elevenlabs.py), with its
# own block below and the key in ~/.config/ai-voice/elevenlabs.json.
TTS_PROVIDER = str(_tts_cfg.get("provider", "kokoro") or "kokoro").strip().lower()
_eleven_cfg = _tts_cfg.get("elevenlabs") if isinstance(_tts_cfg.get("elevenlabs"), dict) else {}
ELEVENLABS_VOICE_ID = str(_eleven_cfg.get("voice_id", "") or "")
ELEVENLABS_MODEL = str(_eleven_cfg.get("model", "eleven_flash_v2_5") or "eleven_flash_v2_5")
ELEVENLABS_STABILITY = _eleven_cfg.get("stability")      # None: the voice's own setting
ELEVENLABS_SIMILARITY = _eleven_cfg.get("similarity_boost")

# Shown on the UI's TTS line.
TTS_ADDRESS = "ElevenLabs" if TTS_PROVIDER == "elevenlabs" else (urlparse(TTS_URL).netloc or TTS_URL)

# Old names, kept so nothing outside this file has to change at once.
KOKORO_URL, KOKORO_SPEED = TTS_URL, TTS_SPEED
KOKORO_VOLUME, KOKORO_ADDRESS = TTS_VOLUME, TTS_ADDRESS

