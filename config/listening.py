"""Hearing you: speech-to-text, voice activity, barge-in, the wake word.

Part of the config package (it was one config.py); see config/__init__.py.
"""
from .base import setting

# -------------------------
# Speech-to-text / voice activity detection
# -------------------------
# Optional "stt" block in agent.json:
#   "stt": { "model": "small", "language": "en", "sensitivity": 1.0,
#            "silence_seconds": 1.2, "max_seconds": 60,
#            "no_speech_timeout": 8 }
_stt_cfg = setting("stt", {})

# How push-to-talk behaves:
#   auto   - HOME starts listening, silence ends it (the default)
#   manual - HOME starts, HOME stops. Silence is ignored, so you can
#            pause mid-thought without it cutting you off
#   open   - hands free. The mic stays armed, recording starts when you
#            speak and ends on silence, then it re-arms. HOME toggles
#            the whole loop on and off.
STT_MODE = str(_stt_cfg.get("mode", "auto")).strip().lower()

if STT_MODE not in ("auto", "manual", "open"):
    STT_MODE = "auto"

# Which voice-activity detector decides when you're talking.
#   silero - a real speech/not-speech model (~1MB, CPU, already in the
#            requirements). Knows your voice from a fan, so it can
#            trigger fast without also triggering on room noise.
#   energy - plain RMS level. No dependencies, but it can only measure
#            loudness, so it is late to start and cuts off quiet
#            syllables. Kept as a fallback.
#   auto   - silero if importable, else energy.
STT_VAD = str(_stt_cfg.get("vad", "auto")).strip().lower()

if STT_VAD not in ("auto", "silero", "energy"):
    STT_VAD = "auto"

# Silero speech probability above which a frame counts as speech. Lower
# picks up sooner and is more forgiving of a quiet mic; higher ignores
# more background. Speech only *ends* below (threshold - 0.15), which is
# the hysteresis that stops it cutting you off mid-sentence.
STT_VAD_THRESHOLD = float(_stt_cfg.get("vad_threshold", 0.4))

STT_MODEL = _stt_cfg.get("model", "small")
# None lets Whisper auto-detect, which is unreliable on short clips.
STT_LANGUAGE = _stt_cfg.get("language", "en") or None
# >1 makes it easier to trigger on a quiet mic, <1 harder in a noisy room.
STT_SENSITIVITY = float(_stt_cfg.get("sensitivity", 1.0))
# Silence after speech before we stop recording and transcribe.
STT_SILENCE_SECONDS = float(_stt_cfg.get("silence_seconds", 1.2))
# Hard cap on one recording.
STT_MAX_SECONDS = float(_stt_cfg.get("max_seconds", 60))
# Give up if you never started talking (auto mode only - manual waits
# for you, and open mode waits indefinitely by design).
STT_NO_SPEECH_TIMEOUT = float(_stt_cfg.get("no_speech_timeout", 8))
# Backstop for manual mode, where nothing else stops the recording.
STT_MANUAL_MAX_SECONDS = float(_stt_cfg.get("manual_max_seconds", 300))
# Pause after Luna finishes speaking before the mic re-arms in open
# mode, so the tail of her own voice doesn't retrigger it.
STT_SETTLE_SECONDS = float(_stt_cfg.get("settle_seconds", 0.6))

# -------------------------
# Barge-in
# -------------------------
# Listen while Luna is speaking, and cut her off when you start
# talking. Needs Silero - the energy detector can't tell your voice
# from her own coming back through the speakers.
#
# That bleed is the whole problem with barge-in and there is no
# acoustic echo cancellation here, so the mic level during playback is
# measured and used as the baseline: you have to be noticeably louder
# than she is at the microphone. On headphones that's trivially true.
# On speakers, turn the volume down or raise the margin.
STT_BARGE_IN = bool(_stt_cfg.get("barge_in", True))
# How long you have to keep talking before she stops. Too low and a
# cough cuts her off; too high and you're talking over her for a
# second before she notices.
STT_BARGE_IN_SECONDS = float(_stt_cfg.get("barge_in_seconds", 0.35))
# How much louder than her own bleed you have to be. Lower it on
# headphones, raise it if she keeps interrupting herself.
STT_BARGE_IN_MARGIN = float(_stt_cfg.get("barge_in_margin", 2.5))
# Added to the normal VAD threshold while she's talking - a higher bar
# for "that's speech" when we already know speech is playing.
STT_BARGE_IN_BOOST = float(_stt_cfg.get("barge_in_boost", 0.25))

# -------------------------
# Wake word
# -------------------------
# Replaces HOME in open mode: say her name and she listens. Optional
# "wake_word" block in agent.json:
#
#   "wake_word": {
#       "enabled": true,
#       "model": "~/models/hey_luna.onnx",
#       "threshold": 0.5,
#       "follow_up_seconds": 12
#   }
#
# model is either a path to one you trained with openWakeWord, or the
# name of one of theirs (hey_jarvis, alexa, hey_mycroft, hey_rhasspy).
# There is no pretrained "hey Luna" - see wakeword.py.
_wake_cfg = setting("wake_word", {})
WAKE_WORD_ENABLED = bool(_wake_cfg.get("enabled", False))
WAKE_WORD_MODEL = _wake_cfg.get("model", "hey_jarvis")
# Raise if it fires at the television, lower if it ignores you.
WAKE_WORD_THRESHOLD = float(_wake_cfg.get("threshold", 0.5))
# After answering, how long she keeps listening without the wake word,
# so a follow-up question doesn't need her name again.
WAKE_WORD_FOLLOW_UP_SECONDS = float(_wake_cfg.get("follow_up_seconds", 12))
# Deaf period right after a detection, so the tail of "hey Luna" isn't
# heard as a second one.
WAKE_WORD_COOLDOWN = float(_wake_cfg.get("cooldown_seconds", 1.0))

