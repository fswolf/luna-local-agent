import json
import os

from datetime import datetime as _datetime

# When this run started - config is the first thing everything imports.
# reflect.py uses it to tell this session's turns from the last one's.
STARTED = _datetime.now()

from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LM_URL = "http://localhost:1234/v1/chat/completions"
SAMPLE_RATE = 16000

# ---------------------------------------------------------------------------
# Two files, two jobs.
#
#   agent/agent.json  - who she is. Name, personality, tone, traits, rules.
#   config.json       - how the machine runs. Voice, models, thresholds,
#                       timeouts, theme.
#
# They were one file, which meant tuning a VAD threshold and rewriting her
# personality were the same edit, and you couldn't share either one without
# handing over the other.
#
# config.json wins where both define a key, and agent.json is still read as
# a fallback so an install that never split them keeps working untouched.
# ---------------------------------------------------------------------------
def _load_json(path, on_missing=None):
    """Read a JSON file, or explain why not and carry on.

    A stray comma used to take the whole app down on startup with a bare
    JSONDecodeError - and hand-editing these files is the entire point of
    them being JSON, so a typo shouldn't be fatal.
    """
    try:
        with open(path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {} if on_missing is None else on_missing()
    except (json.JSONDecodeError, OSError) as error:
        print(
            f"\nCouldn't read {path}:\n  {error}\n"
            "Carrying on with defaults. The file has been left alone - "
            "fix the syntax and restart.\n"
        )
        return {}


AGENT_FILE = os.path.join(BASE_DIR, "agent", "agent.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
MEMORY_FILE = os.path.join(BASE_DIR, "agent", "memory.json")

agent = _load_json(AGENT_FILE)
settings = _load_json(CONFIG_FILE)
memory = _load_json(MEMORY_FILE)


def setting(key, default=None):
    """A machine setting: config.json first, then agent.json."""
    if key in settings:
        return settings[key]

    return agent.get(key, default)


AGENT_NAME = agent.get("name") or settings.get("name") or "Luna"

# Persona, kept separate from the machine settings so llm.py doesn't have
# to know which file anything came from.
PERSONALITY = agent.get("personality", "")
TONE = agent.get("tone", "")
TRAITS = agent.get("traits", [])
RULES = agent.get("rules", [])
GENERATION = setting("generation", {})

# -------------------------
# Which model server
# -------------------------
# LM Studio, or llama.cpp's own llama-server (llama/start.sh), checked
# once at startup. Both speak the same OpenAI-style API, so everything
# that talks to the model just uses LM_URL; what differs is what each
# can do beyond it - llama-server exposes token probabilities, control
# vectors and the rest, LM Studio doesn't - and LLM_BACKEND is what
# those features check.
#
#   "llm": { "backend": "auto",
#            "lmstudio_url": "http://localhost:1234/v1/chat/completions",
#            "llama_url":    "http://127.0.0.1:8080/v1/chat/completions" }
#
# auto prefers llama-server when it's running - starting it is a
# deliberate act, LM Studio is the one that's usually just open - and
# falls back to LM Studio. Neither answering keeps LM Studio's address,
# so the startup error names the server most people will have.
_llm_cfg = setting("llm", {})
LM_STUDIO_URL = str(_llm_cfg.get("lmstudio_url", LM_URL))
LLAMA_URL = str(_llm_cfg.get("llama_url",
                             "http://127.0.0.1:8080/v1/chat/completions"))
LLM_BACKEND_WANTED = str(_llm_cfg.get("backend", "auto")).lower()


def _root(url):
    return url.split("/v1/")[0]


# llama/start.sh makes a random key the first time it runs and starts
# the server with it. Every request has to carry it, because a server
# on localhost is reachable by any web page open in the browser - and
# this one can write files (saved slots) and burn the GPU. LM Studio
# never sees it.
LLAMA_KEY_FILE = os.path.join(BASE_DIR, "llama", ".api_key")


def _llama_key():
    try:
        with open(LLAMA_KEY_FILE) as f:
            for line in f:
                line = line.strip()

                if line and not line.startswith("#"):
                    return line
    except OSError:
        pass

    return ""


LLAMA_API_KEY = _llama_key()
_LLAMA_HEADERS = {"Authorization": f"Bearer {LLAMA_API_KEY}"} if LLAMA_API_KEY else {}


def _answers(url, timeout=0.7, headers=None):
    import urllib.request

    try:
        request = urllib.request.Request(url, headers=headers or {})

        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def _pick_backend():
    """(backend, chat url). llama-server answers /props and LM Studio
    answers /api/v0/models; nothing else answers both, so each is
    recognised by the door only it has."""
    llama = ("llama", LLAMA_URL)
    studio = ("lmstudio", LM_STUDIO_URL)

    if LLM_BACKEND_WANTED.startswith("llama"):
        return llama

    if LLM_BACKEND_WANTED.startswith("lm"):
        return studio

    if _answers(_root(LLAMA_URL) + "/props", headers=_LLAMA_HEADERS):
        return llama

    return studio


LLM_BACKEND, LM_URL = _pick_backend()

# Sent with every request to the model server. Empty for LM Studio.
LLM_HEADERS = dict(_LLAMA_HEADERS) if LLM_BACKEND == "llama" else {}

# The embedding server (started by llama/start.sh) for recalling facts by meaning.
# Optional: nothing needs it, and fact recall falls back to matching
# words whenever it isn't answering.
EMBED_URL = str(_llm_cfg.get("embed_url", "http://127.0.0.1:8081/v1/embeddings"))
EMBED_HEADERS = dict(_LLAMA_HEADERS)
# Qwen3-Embedding is trained with an instruction on the query side and
# none on the documents; other embedding models want this empty.
EMBED_QUERY_PREFIX = str(_llm_cfg.get(
    "embed_query_prefix",
    "Instruct: Given something the user just said, retrieve remembered "
    "facts about the user that are relevant to it\nQuery: ",
))
# How alike a fact must be to travel on meaning alone. Cosine, 0-1.
EMBED_MIN_SCORE = float(_llm_cfg.get("embed_min_score", 0.35))

# The reranker (also from llama/start.sh, :8082) re-orders the
# embedding's best matches by reading each one beside what was said.
# Optional too: when it isn't answering the embedding order stands.
# rerank_candidates is how many of the embedding's matches it reads.
RERANK_URL = str(_llm_cfg.get("rerank_url", "http://127.0.0.1:8082/v1/rerank"))
RERANK_CANDIDATES = int(_llm_cfg.get("rerank_candidates", 24))


def llm_backend_label():
    return "llama.cpp" if LLM_BACKEND == "llama" else "LM Studio"

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
VOICE = _tts_env("VOICE", setting("voice", "af_bella"))

# Shown on the UI's TTS line.
TTS_ADDRESS = urlparse(TTS_URL).netloc or TTS_URL

# Old names, kept so nothing outside this file has to change at once.
KOKORO_URL, KOKORO_SPEED = TTS_URL, TTS_SPEED
KOKORO_VOLUME, KOKORO_ADDRESS = TTS_VOLUME, TTS_ADDRESS

# -------------------------
# Control socket (Hyprland / Wayland push-to-talk)
# -------------------------
CONTROL_SOCKET = os.environ.get(
    "AI_VOICE_SOCKET",
    os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "ai-voice.sock"),
)

# -------------------------
# TUI
# -------------------------
# Mouse capture gives wheel scrolling at the cost of text selection -
# the terminal can only hand drags to one of them. Off by default,
# because a window full of log lines you can't copy is worse than one
# you scroll with PgUp.
UI_MOUSE = bool(setting("ui", {}).get("mouse", False))

# -------------------------
# TUI theme
# -------------------------
# MewNix Candy by default. Override any subset in agent.json:
#   "theme": { "accent": "#ff87d7", "user": "#5fd7ff" }
# Values are hex colours; terminals without truecolor get the nearest
# 256-colour match automatically.
_THEME_DEFAULTS = {
    # sfav-style purple
    "accent": "#ff87d7",
    "border": "#b48cff",
    "title": "#ffafd7",
    "label": "#b48cff",

    # Main text
    "text": "#ccd0ea",
    "value": "#ccd0ea",

    # Agent / user
    "agent": "#ff87d7",
    "user": "#5fd7ff",

    # System/status
    "system": "#d9b46a",
    "ok": "#87ffaf",
    "warn": "#ff5f87",

    # Footer / separators
    "footer": "#8787af",
    "dim": "#5a5a78",

    # Prompt
    "prompt": "#ff87d7",

    # Links
    "link": "#b48cff",
}

THEME = dict(_THEME_DEFAULTS)
THEME.update(
    {k: v for k, v in setting("theme", {}).items() if k in _THEME_DEFAULTS}
)

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

# -------------------------
# Logging
# -------------------------
# Writes to ~/.cache/ai-voice/ai-voice.log. Off costs nothing, on costs
# a few kilobytes a day and turns "it broke" into a line you can read.
_log_cfg = setting("logging", {})
LOG_ENABLED = bool(_log_cfg.get("enabled", True))
# debug logs every VAD decision and tool argument, which is a lot; info
# logs the things that went wrong and the choices behind them.
LOG_LEVEL = str(_log_cfg.get("level", "info")).upper()
LOG_MAX_KB = int(_log_cfg.get("max_kb", 1024))
LOG_KEEP = int(_log_cfg.get("keep", 3))

# -------------------------
# Vision
# -------------------------
# Lets her look at your screen. Needs grim, and needs a vision model
# loaded in LM Studio - a text-only model will reject the request and
# the error is shown as-is. Optional "vision" block in agent.json:
#   "vision": { "enabled": true, "scale": 0.5 }
_vision_cfg = setting("vision", {})
VISION_ENABLED = bool(_vision_cfg.get("enabled", False))
# grim's own scale factor. Half a 4K screen is still plenty to read an
# error dialog off, and a quarter of the bytes.
VISION_SCALE = float(_vision_cfg.get("scale", 0.5))
VISION_MAX_BYTES = int(_vision_cfg.get("max_kb", 4096)) * 1024

# -------------------------
# Desktop control
# -------------------------
# Acting on the desktop rather than only looking at it - playback,
# volume, clipboard, window focus. Each tool checks for its own program
# at call time, so a missing playerctl costs that one tool rather than
# all four. Optional "desktop" block in config.json:
#   "desktop": { "enabled": true, "clipboard": true }
_desktop_cfg = setting("desktop", {})
DESKTOP_ENABLED = bool(_desktop_cfg.get("enabled", True))

# Her hands on your files: list_files/read_file are free under ~, minus
# a deny list; write_file/edit_file pop an approval window in the TUI
# and wait. No answer within approval_timeout seconds is a no.
#   "files": { "enabled": true, "approval_timeout": 120 }
# Tools switched off by hand, by name. Not in SETTINGS because it's a
# list rather than a scalar - the tools pane (Tab, twice) edits it, and
# tools.set_enabled writes it back.
TOOLS_DISABLED = list(setting("tools", {}).get("disabled", []))
# The opt-in tools (tools.OPT_IN, the camera) switched on - an on-list,
# so they stay off until you choose them.
TOOLS_ENABLED = list(setting("tools", {}).get("enabled", []))

# The webcam, for look_at_camera. The switch is the tool's row in the
# tools pane; these only say which camera and how big.
#   "camera": { "device": 0, "width": 1280, "warmup": 5 }
_camera_cfg = setting("camera", {})
CAMERA_DEVICE = int(_camera_cfg.get("device", 0))
CAMERA_WIDTH = int(_camera_cfg.get("width", 1280))
CAMERA_WARMUP = int(_camera_cfg.get("warmup", 5))

# How she happens to be feeling - see mood.py. Colours tone only, from
# free signals (clock, session length, errors, barge-ins), never a
# model call.
#   "mood": { "enabled": true, "warmth": 0.4, "recovery": 0.25 }
_mood_cfg = setting("mood", {})
MOOD_ENABLED = bool(_mood_cfg.get("enabled", True))
# Where warmth settles when nothing is pushing it - the resting state
# she drifts back to.
# 0.45 rather than 0.40: the label bands break at 0.35, and resting a
# hair above an edge made the header flicker between two moods.
MOOD_WARMTH = float(_mood_cfg.get("warmth", 0.45))
# How hard each turn pulls both dials home. 0 = moods never fade,
# 1 = nothing persists past a single turn.
MOOD_RECOVERY = float(_mood_cfg.get("recovery", 0.25))
# Whether the mood also tints the voice - a drowsy Luna a few percent
# slower and lower. Small by design; see mood.voice_tint.
MOOD_VOICE = bool(_mood_cfg.get("voice", True))
# Whether being kind to her registers. It's the one mood signal that
# costs a model call - a small one, on a worker, after the turn - so
# it's the one worth being able to switch off.
MOOD_AFFECTION = bool(_mood_cfg.get("affection", True))

_files_cfg = setting("files", {})
FILES_ENABLED = bool(_files_cfg.get("enabled", True))
FILES_APPROVAL_TIMEOUT = float(_files_cfg.get("approval_timeout", 120))
# The Permissions group in the tools pane. read: allow | ask | off,
# write: ask | allow | off. "allow" for write is the saved form of the
# popup's A: her own folder, ~/.config and ~/.local still ask, and the
# deny list still refuses. Execute is shell.enabled (commands always ask).
FILES_READ = str(_files_cfg.get("read", "allow")).lower()
FILES_WRITE = str(_files_cfg.get("write", "ask")).lower()
# Folders a scheduled job (plugins/cron.py) may write in without the
# popup. Yours to set - a plugin can't widen it. The deny list still
# wins, ~ itself and this app's own folder are ignored, and every other
# write still asks.
#   "files": { ..., "job_write_dirs": ["~/luna-jobs"] }
# Remote plugins whose owner turns write without the popup - remote
# access, where nobody is at the desk to answer it. The deny list still
# applies. Empty = every remote write asks (and times out as a no).
#   "files": { ..., "auto_approve_sources": ["discord"] }
FILES_AUTO_APPROVE_SOURCES = [str(s).strip().lower() for s in
                              _files_cfg.get("auto_approve_sources", []) if str(s).strip()]
FILES_JOB_WRITE_DIRS = [os.path.expanduser(str(p)) for p in
                        _files_cfg.get("job_write_dirs", []) if str(p).strip()]
# Separate from the rest, because reading the clipboard means whatever
# you last copied - a password, an API key - can land in the model's
# context and from there in history on disk. On by default, but it is
# the one here worth knowing is a switch.
DESKTOP_CLIPBOARD = bool(_desktop_cfg.get("clipboard", True))

# -------------------------
# Plugins
# -------------------------
# Everything under "plugins" in config.json, keyed by plugin name. The
# core never learns what a plugin's own keys mean - it just hands the
# block over - which is what keeps a plugin droppable.
#
# "chat" is the exception: shared policy for any plugin that feeds her
# live chat from strangers. It lives here rather than in a plugin
# because it is the part that must not be per-plugin. A plugin can ask
# for a wider tool list; chatroom.TOOL_CEILING is what it gets.
#
# API keys are deliberately not in here. config.json is in the repo,
# and a key pasted into it is a key on GitHub - plugins read their own
# from the environment or from ~/.config/ai-voice/.
_plugins_cfg = setting("plugins", {})

_chat_cfg = _plugins_cfg.get("chat") or {}
# Which tools a stranger's question may reach. Everything absent from
# this acts on Ryan's machine or Ryan's data, and a viewer must not be
# able to reach it by asking nicely: the tools are dropped from the
# request, not refused at call time.
CHAT_TOOLS = tuple(_chat_cfg.get(
    "tools", ["get_datetime", "time_until", "web_search"]
))
# Seconds between answers, so she isn't talking over the stream.
CHAT_COOLDOWN_SECONDS = float(_chat_cfg.get("cooldown_seconds", 8))
# And per viewer, so one person can't monopolise her.
CHAT_USER_COOLDOWN_SECONDS = float(_chat_cfg.get("user_cooldown_seconds", 30))
# A very long chat message is a paste, and a paste aimed at her is
# usually an attempt at something.
CHAT_MAX_MESSAGE_CHARS = int(_chat_cfg.get("max_message_chars", 300))
# How much of the room she can see. Memory only, never stored.
CHAT_CONTEXT_LINES = int(_chat_cfg.get("context_lines", 12))


def plugin_settings(name):
    """One plugin's settings, over the shared chat defaults.

    Merged rather than either/or so a chat plugin gets the limits for
    free and overrides only what is genuinely its own - a channel name,
    a list of bots to ignore.
    """
    merged = {
        "tools": list(CHAT_TOOLS),
        "cooldown_seconds": CHAT_COOLDOWN_SECONDS,
        "user_cooldown_seconds": CHAT_USER_COOLDOWN_SECONDS,
        "max_message_chars": CHAT_MAX_MESSAGE_CHARS,
        "context_lines": CHAT_CONTEXT_LINES,
    }

    block = _plugins_cfg.get(name)

    if isinstance(block, dict):
        merged.update(block)

    return merged


def set_plugin_enabled(name, on):
    """Remember that a plugin was switched on, for next launch."""
    _store(f"plugins.{name}.enabled", bool(on))

    block = _plugins_cfg.setdefault(name, {})

    if isinstance(block, dict):
        block["enabled"] = bool(on)

_history_cfg = setting("history", {})
MAX_RAW_MESSAGES = _history_cfg.get("max_raw_messages", 15)
SUMMARIZE_CHUNK = _history_cfg.get("summarize_chunk", 8)
# The running summary is re-compressed once it passes this, rather than
# being appended to forever.
SUMMARY_MAX_CHARS = int(_history_cfg.get("summary_max_chars", 2500))
# A full archive of every turn, which summarization never prunes. It is
# what search_history reads; the prompt never sees it.
TRANSCRIPT_ENABLED = bool(_history_cfg.get("transcript", True))
TRANSCRIPT_MAX_MB = float(_history_cfg.get("transcript_max_mb", 20))

_memory_cfg = setting("long_term_memory", {})
LONG_TERM_MEMORY_ENABLED = _memory_cfg.get("enabled", True)
LONG_TERM_MEMORY_MAX_FACTS = _memory_cfg.get("max_facts", 40)
# How many facts may go into one system prompt. Under this, all of them
# do; over it, the ones relevant to what was just said.
LONG_TERM_MEMORY_CONTEXT_FACTS = _memory_cfg.get("context_facts", 25)
# "json" is the original capped list in memory.json; "sqlite" is the
# experimental permanent table (factstore.py) - uncapped, searched with
# FTS5, and able to retire a fact that stops being true instead of
# keeping both versions. Live: /set long_term_memory.backend json to
# fall back, and nothing is lost in either direction.
LONG_TERM_MEMORY_BACKEND = str(_memory_cfg.get("backend", "json"))

# The reasoning log - see thoughtlog.py. Every turn from the keyboard
# or the mic keeps the model's scratchpad (<think> blocks, or the
# reasoning_content field) in agent/thoughts.db for review with
# /thoughts. Capped by record count; the oldest go first.
#   "thoughts": { "enabled": true, "max_records": 2000 }
_thoughts_cfg = setting("thoughts", {})
THOUGHTS_ENABLED = bool(_thoughts_cfg.get("enabled", True))
THOUGHTS_MAX_RECORDS = int(_thoughts_cfg.get("max_records", 2000))
# On llama-server, keep each token's probability too (and the runners-up
# when it was unsure). Nothing on LM Studio, which doesn't expose them.
THOUGHTS_TOKEN_PROBS = bool(_thoughts_cfg.get("token_probs", True))

# Adaptive thinking (llama-server only): a modest thinking budget for
# every turn, and a second, deeper look only when the reply came out
# shaky by its own token probabilities. See llm._rethink.
#   "adaptive": { "enabled": true, "first_budget": 1024, "deep_budget": -1,
#                 "rethink_below": 0.75, "min_gain": 0.05,
#                 "speak_corrections": true }
_adaptive_cfg = setting("adaptive", {})
ADAPTIVE_ENABLED = bool(_adaptive_cfg.get("enabled", True))
ADAPTIVE_FIRST_BUDGET = int(_adaptive_cfg.get("first_budget", 1024))
ADAPTIVE_DEEP_BUDGET = int(_adaptive_cfg.get("deep_budget", -1))
ADAPTIVE_RETHINK_BELOW = float(_adaptive_cfg.get("rethink_below", 0.75))
ADAPTIVE_MIN_GAIN = float(_adaptive_cfg.get("min_gain", 0.05))
ADAPTIVE_SPEAK_CORRECTIONS = bool(_adaptive_cfg.get("speak_corrections", True))
# "vote": on a shaky reply, ask again `votes` more times and go with what
# most of the answers agree on. "rethink": one deeper second look.
ADAPTIVE_MODE = str(_adaptive_cfg.get("mode", "vote")).lower()
ADAPTIVE_VOTES = int(_adaptive_cfg.get("votes", 2))

# The grounding check (grounding.py): specifics she stated with nothing
# behind them. mode: "flag", "hedge" (default) or "check".
_grounding_cfg = setting("grounding", {})
GROUNDING_ENABLED = bool(_grounding_cfg.get("enabled", True))
GROUNDING_MODE = str(_grounding_cfg.get("mode", "hedge")).lower()
GROUNDING_HEDGE_LINE = str(_grounding_cfg.get(
    "hedge_line", "I haven't checked those details, though, so take them with a grain of salt."))
# "Let me read the file~" and then nothing: run the step she announced.
# Any backend, any of your turns that had tools - not just shaky ones.
FOLLOW_THROUGH = bool(_adaptive_cfg.get("follow_through", True))
ADAPTIVE_PREFIX = str(_adaptive_cfg.get("correction_prefix",
                                        "Hang on, let me correct that."))

# Growing up a little (reflect.py, notebook.py): lessons from her own
# mistakes, notes on each conversation, fact cleanup, saying when she's
# unsure, and picking up where the last session left off.
#   "self": { "lessons": true, "episodes": true, "tidy_facts": true,
#             "calibration": true, "greet": true, ... }
_self_cfg = setting("self", {})
SELF_LESSONS = bool(_self_cfg.get("lessons", True))
SELF_LESSONS_IN_PROMPT = int(_self_cfg.get("lessons_in_prompt", 4))
SELF_MAX_LESSONS = int(_self_cfg.get("max_lessons", 40))
SELF_REFLECT_HOURS = float(_self_cfg.get("reflect_every_hours", 20))
SELF_EPISODES = bool(_self_cfg.get("episodes", True))
SELF_EPISODES_IN_PROMPT = int(_self_cfg.get("episodes_in_prompt", 2))
SELF_IDLE_MINUTES = int(_self_cfg.get("idle_minutes", 30))
SELF_TIDY_FACTS = bool(_self_cfg.get("tidy_facts", True))
SELF_CALIBRATION = bool(_self_cfg.get("calibration", True))
SELF_HEDGE_BELOW = float(_self_cfg.get("hedge_below", 0.6))
SELF_HEDGE_LINE = str(_self_cfg.get("hedge_line",
                                    "I'm not totally sure about that one, though."))
SELF_GREET = bool(_self_cfg.get("greet", True))
# Recipes for multi-step jobs she's done well (skills.py).
SELF_SKILLS = bool(_self_cfg.get("skills", True))
SELF_SKILLS_IN_PROMPT = int(_self_cfg.get("skills_in_prompt", 2))
SELF_MAX_SKILLS = int(_self_cfg.get("max_skills", 60))
# Ongoing projects (projects.py): work that spans sessions.
SELF_PROJECTS = bool(_self_cfg.get("projects", True))
SELF_PROJECTS_IN_PROMPT = int(_self_cfg.get("projects_in_prompt", 3))

# The situation block (situation.py): focused window, music, machine load,
# running plugins, next reminder - a few live lines in every private turn.
_situation_cfg = setting("situation", {})
SITUATION_ENABLED = bool(_situation_cfg.get("enabled", True))
SITUATION_PARTS = {k: bool(_situation_cfg.get(k, True))
                   for k in ("window", "music", "machine", "plugins", "reminders")}

# The portrait window (portrait/, served by the live monitor at
# /portrait/): a VRM model that blinks, looks around, twitches its ears
# and moves its mouth with her voice. /portrait opens it.
#   "portrait": { "model": "models/sigewinne/sigewinne.model3.json", "ear_bones": [],
#                 "browser": "", "size": "420x560" }
_portrait_cfg = setting("portrait", {})
# The Sigewinne Live2D model ships with the repo and is the default, and
# the fallback when portrait.model points at something that isn't there.
_SIGEWINNE = "models/sigewinne/sigewinne.model3.json"
_DEFAULT_PORTRAIT = _SIGEWINNE
PORTRAIT_MODEL = str(_portrait_cfg.get("model") or _DEFAULT_PORTRAIT)
PORTRAIT_EAR_BONES = list(_portrait_cfg.get("ear_bones", []) or [])
PORTRAIT_BROWSER = str(_portrait_cfg.get("browser", ""))
PORTRAIT_SIZE = str(_portrait_cfg.get("size", "420x560"))
# Live2D only: which expression is which (portrait/add_live2d.py fills it
# in), and which parameters are the ears if their names don't say so.
# The hologram look (portrait/hologram.js): off unless "enabled": true, or
# ?holo=1 on the portrait URL. tint, mix (0 = her own colours, 1 = all
# tint), intensity, glitch (how often it tears), base (the projector glow).
#   "hologram": { "enabled": true, "tint": "#c37bff", "mix": 0.8 }
PORTRAIT_HOLOGRAM = dict(_portrait_cfg.get("hologram", {}) or {})
PORTRAIT_HOLOGRAM_ENABLED = bool(PORTRAIT_HOLOGRAM.get("enabled", False))
PORTRAIT_LIVE2D = dict(_portrait_cfg.get("live2d", {}) or {})
if not PORTRAIT_LIVE2D and PORTRAIT_MODEL == _SIGEWINNE:
    # Its three expressions, so moods show on her face out of the box.
    PORTRAIT_LIVE2D = {"expressions": {"sad": "tears", "flustered": "x_eyes", "confused": "spiral_eyes"}}

# MCP servers whose tools she can use (mcpclient.py). Read at startup.
#   "mcp": { "enabled": true, "servers": { "obs": {"command": "...", "args": [...]} } }
_mcp_cfg = setting("mcp", {})
MCP_ENABLED = bool(_mcp_cfg.get("enabled", True))
MCP_SERVERS = dict(_mcp_cfg.get("servers", {}) or {})

# The live monitor (livefeed.py): a page served by the assistant on
# 127.0.0.1, showing each turn as it happens. Read at startup.
#   "monitor": { "enabled": true, "port": 8792 }
_monitor_cfg = setting("monitor", {})
MONITOR_ENABLED = bool(_monitor_cfg.get("enabled", True))
MONITOR_PORT = int(_monitor_cfg.get("port", 8792))

# -------------------------
# Tool calling
# -------------------------
# Lets the model call set_reminder, web_search, remember_fact and so on
# for itself instead of relying on keyword triggers. Needs a model with
# a tool template (Qwen, Llama 3.1+, Mistral, Hermes...); if the server
# rejects the payload we fall back automatically at runtime.
_tools_cfg = setting("tools", {})
TOOLS_ENABLED = _tools_cfg.get("enabled", True)
# How many times the model may call tools before it must answer in prose.
MAX_TOOL_ROUNDS = int(_tools_cfg.get("max_rounds", 4))

# -------------------------
# Alarms
# -------------------------
# An alarm is a reminder that has to actually wake somebody, so it gets
# its own volume, repeats until dismissed, and plays a tone after the
# voice. Speech alone doesn't wake anyone - it is exactly the thing a
# sleeping brain is best at folding into a dream.
_alarm_cfg = setting("alarms", {})
ALARMS_ENABLED = bool(_alarm_cfg.get("enabled", True))
# Independent of tts.volume on purpose: the level you picked for a
# conversation at midnight is not the level that gets you up at seven.
ALARM_VOLUME = float(_alarm_cfg.get("volume", 1.0))
ALARM_REPEATS = int(_alarm_cfg.get("repeats", 5))
ALARM_GAP_SECONDS = float(_alarm_cfg.get("gap_seconds", 25))
# Nine, because every alarm clock ever made used nine.
ALARM_SNOOZE_MINUTES = int(_alarm_cfg.get("snooze_minutes", 9))
# Empty means the bundled assets/alarm.wav, and if that is missing or
# unreadable the tone is synthesized instead - an alarm that fails
# silently is worse than no alarm, because you were relying on it.
ALARM_TONE = str(_alarm_cfg.get("tone", "")).strip()

_reminders_cfg = setting("reminders", {})
REMINDERS_ENABLED = _reminders_cfg.get("enabled", True)
REMINDER_CHECK_INTERVAL_SECONDS = _reminders_cfg.get("check_interval_minutes", 10) * 60

_shell_cfg = setting("shell", {})
# run_command: she runs a shell command, and every one asks first.
SHELL_ENABLED = bool(_shell_cfg.get("enabled", True))
SHELL_TIMEOUT = float(_shell_cfg.get("timeout", 60))
SHELL_MAX_OUTPUT = int(_shell_cfg.get("max_output_chars", 6000))
# Remote sources whose commands run without the popup - for automation
# from Discord. Empty by default: opting in is yours, in core config.
SHELL_AUTO_APPROVE_SOURCES = [str(s).strip().lower() for s in
                              _shell_cfg.get("auto_approve_sources", []) if str(s).strip()]

_web_search_cfg = setting("web_search", {})
WEB_SEARCH_ENABLED = _web_search_cfg.get("enabled", True)
WEB_SEARCH_MAX_RESULTS = _web_search_cfg.get("max_results", 5)
# Opening a page she found, rather than summarizing the search blurb.
PAGE_FETCH_ENABLED = bool(_web_search_cfg.get("fetch_pages", True))
# How much of a page reaches the model. Roughly a thousand tokens per
# 4000 characters, so this is the main cost control.
PAGE_MAX_CHARS = int(_web_search_cfg.get("page_max_chars", 6000))
PAGE_TIMEOUT = float(_web_search_cfg.get("page_timeout", 20))
# read_page and research refuse this machine and the local network
# (your router, llama-server, the monitor) unless this is on. A page
# can ask her to "read" http://192.168.1.1/ as easily as you can.
PAGE_ALLOW_LOCAL = bool(_web_search_cfg.get("allow_local", False))
# research: how many pages it reads, and how much of them in total.
RESEARCH_PAGES = max(1, int(_web_search_cfg.get("research_pages", 3)))
RESEARCH_MAX_CHARS = int(_web_search_cfg.get("research_max_chars", 9000))


# ---------------------------------------------------------------------------
# Changing settings from the terminal
#
# Every value above is read once at import and copied into a constant,
# which is fast and simple and means nothing can be changed at runtime.
# That's fine for most of them - you don't retune a Whisper model size
# mid-conversation - but it's wrong for the handful you actually tune by
# ear, where the loop is "change it, say something, listen, change it
# again" and a restart each time makes it useless.
#
# So: the ones worth tuning live are listed here by their dotted path in
# config.json, and the modules that use them read config.<NAME> at call
# time rather than importing the value. Everything else saves to the file
# and waits for a restart, which /set says plainly.
# ---------------------------------------------------------------------------
SETTINGS = {
    # path in config.json          constant        applies without a restart
    "generation.max_tokens":      (None,                           False),
    "generation.reasoning":       (None,                           False),

    "stt.mode":                   ("STT_MODE",                     True),
    "stt.vad_threshold":          ("STT_VAD_THRESHOLD",            True),
    "stt.sensitivity":            ("STT_SENSITIVITY",              True),
    "stt.silence_seconds":        ("STT_SILENCE_SECONDS",          True),
    "stt.max_seconds":            ("STT_MAX_SECONDS",              True),
    "stt.manual_max_seconds":     ("STT_MANUAL_MAX_SECONDS",       True),
    "stt.no_speech_timeout":      ("STT_NO_SPEECH_TIMEOUT",        True),
    "stt.settle_seconds":         ("STT_SETTLE_SECONDS",           True),
    "stt.barge_in":               ("STT_BARGE_IN",                 True),
    "stt.barge_in_seconds":       ("STT_BARGE_IN_SECONDS",         True),
    "stt.barge_in_margin":        ("STT_BARGE_IN_MARGIN",          True),
    "stt.barge_in_boost":         ("STT_BARGE_IN_BOOST",           True),
    "stt.vad":                    ("STT_VAD",                      False),
    "stt.model":                  ("STT_MODEL",                    False),
    "stt.language":               ("STT_LANGUAGE",                 False),

    "tts.speed":                  ("TTS_SPEED",                    True),
    "tts.volume":                 ("TTS_VOLUME",                   True),
    "tts.player":                 ("TTS_PLAYER",                   True),
    "tts.pitch":                  ("TTS_PITCH",                    True),
    # Live now, where it used to need a restart: speech.py reads
    # config.VOICE per request rather than importing the value, so
    # /voice can audition a blend while she's mid-conversation. The
    # name goes to the server untouched and the server resolves it -
    # nothing here needs to know what a blend is.
    "voice":                      ("VOICE",                        True),
    "tts.url":                    ("TTS_URL",                      False),

    "ui.mouse":                   ("UI_MOUSE",                     True),

    "logging.enabled":            ("LOG_ENABLED",                  False),
    "logging.level":              ("LOG_LEVEL",                    False),

    "vision.enabled":             ("VISION_ENABLED",               True),
    "vision.scale":               ("VISION_SCALE",                 True),
    "camera.device":              ("CAMERA_DEVICE",                True),
    "camera.width":               ("CAMERA_WIDTH",                 True),
    "camera.warmup":              ("CAMERA_WARMUP",                True),

    "desktop.enabled":            ("DESKTOP_ENABLED",              True),
    "desktop.clipboard":          ("DESKTOP_CLIPBOARD",            True),

    "mood.enabled":               ("MOOD_ENABLED",                 True),
    "mood.warmth":                ("MOOD_WARMTH",                  True),
    "mood.recovery":              ("MOOD_RECOVERY",                True),
    "mood.voice":                 ("MOOD_VOICE",                   True),
    "mood.affection":             ("MOOD_AFFECTION",               True),

    "files.enabled":              ("FILES_ENABLED",                True),
    "files.read":                 ("FILES_READ",                   True),
    "files.write":                ("FILES_WRITE",                  True),
    "files.approval_timeout":     ("FILES_APPROVAL_TIMEOUT",       True),

    # Shared by every chat plugin. A plugin's own keys - channels,
    # account ids - are edited in config.json; these are the ones worth
    # turning mid-stream.
    #
    # Marked live, though a ChatRoom copies them when it is built - so
    # "live" here means the next /<plugin> off, /<plugin> on picks them
    # up, rather than a whole restart. Saying "needs a restart" when
    # toggling the plugin is enough sends people the long way round.
    "plugins.chat.cooldown_seconds":      ("CHAT_COOLDOWN_SECONDS",      True),
    "plugins.chat.user_cooldown_seconds": ("CHAT_USER_COOLDOWN_SECONDS", True),
    "plugins.chat.context_lines":         ("CHAT_CONTEXT_LINES",         True),
    "plugins.chat.max_message_chars":     ("CHAT_MAX_MESSAGE_CHARS",     True),

    "wake_word.enabled":          ("WAKE_WORD_ENABLED",            False),
    "wake_word.model":            ("WAKE_WORD_MODEL",              False),
    "wake_word.threshold":        ("WAKE_WORD_THRESHOLD",          True),
    "wake_word.follow_up_seconds": ("WAKE_WORD_FOLLOW_UP_SECONDS", True),

    "tools.enabled":              ("TOOLS_ENABLED",                False),
    "tools.max_rounds":           ("MAX_TOOL_ROUNDS",              True),

    "shell.enabled":              ("SHELL_ENABLED",                True),
    "shell.timeout":              ("SHELL_TIMEOUT",                True),
    "shell.max_output_chars":     ("SHELL_MAX_OUTPUT",             True),

    "web_search.enabled":         ("WEB_SEARCH_ENABLED",           True),
    "web_search.max_results":     ("WEB_SEARCH_MAX_RESULTS",       True),
    "web_search.fetch_pages":     ("PAGE_FETCH_ENABLED",           True),
    "web_search.page_max_chars":  ("PAGE_MAX_CHARS",               True),
    "web_search.allow_local":     ("PAGE_ALLOW_LOCAL",             True),
    "web_search.research_pages":  ("RESEARCH_PAGES",               True),
    "web_search.research_max_chars": ("RESEARCH_MAX_CHARS",        True),

    "reminders.enabled":          ("REMINDERS_ENABLED",            True),

    "alarms.enabled":             ("ALARMS_ENABLED",               True),
    "alarms.volume":              ("ALARM_VOLUME",                 True),
    "alarms.repeats":             ("ALARM_REPEATS",                True),
    "alarms.gap_seconds":         ("ALARM_GAP_SECONDS",            True),
    "alarms.snooze_minutes":      ("ALARM_SNOOZE_MINUTES",         True),
    "alarms.tone":                ("ALARM_TONE",                   True),

    "history.max_raw_messages":   ("MAX_RAW_MESSAGES",             True),
    "history.summarize_chunk":    ("SUMMARIZE_CHUNK",              True),
    "history.summary_max_chars":  ("SUMMARY_MAX_CHARS",            True),
    "history.transcript":         ("TRANSCRIPT_ENABLED",           True),

    "long_term_memory.enabled":   ("LONG_TERM_MEMORY_ENABLED",     True),
    "long_term_memory.max_facts": ("LONG_TERM_MEMORY_MAX_FACTS",   True),
    "long_term_memory.context_facts": ("LONG_TERM_MEMORY_CONTEXT_FACTS", True),
    "long_term_memory.backend":   ("LONG_TERM_MEMORY_BACKEND",      True),

    "thoughts.enabled":           ("THOUGHTS_ENABLED",             True),
    "thoughts.max_records":       ("THOUGHTS_MAX_RECORDS",         True),
    "thoughts.token_probs":       ("THOUGHTS_TOKEN_PROBS",         True),

    "adaptive.enabled":           ("ADAPTIVE_ENABLED",             True),
    "adaptive.first_budget":      ("ADAPTIVE_FIRST_BUDGET",        True),
    "adaptive.deep_budget":       ("ADAPTIVE_DEEP_BUDGET",         True),
    "adaptive.rethink_below":     ("ADAPTIVE_RETHINK_BELOW",       True),
    "adaptive.min_gain":          ("ADAPTIVE_MIN_GAIN",            True),
    "adaptive.speak_corrections": ("ADAPTIVE_SPEAK_CORRECTIONS",   True),
    "adaptive.mode":              ("ADAPTIVE_MODE",                True),
    "adaptive.votes":             ("ADAPTIVE_VOTES",               True),
    "grounding.enabled":          ("GROUNDING_ENABLED",            True),
    "grounding.mode":             ("GROUNDING_MODE",               True),
    "grounding.hedge_line":       ("GROUNDING_HEDGE_LINE",         True),
    "adaptive.follow_through":    ("FOLLOW_THROUGH",               True),

    "self.lessons":               ("SELF_LESSONS",                 True),
    "self.lessons_in_prompt":     ("SELF_LESSONS_IN_PROMPT",       True),
    "self.max_lessons":           ("SELF_MAX_LESSONS",             True),
    "self.reflect_every_hours":   ("SELF_REFLECT_HOURS",           True),
    "self.episodes":              ("SELF_EPISODES",                True),
    "self.episodes_in_prompt":    ("SELF_EPISODES_IN_PROMPT",      True),
    "self.idle_minutes":          ("SELF_IDLE_MINUTES",            True),
    "self.tidy_facts":            ("SELF_TIDY_FACTS",              True),
    "self.calibration":           ("SELF_CALIBRATION",             True),
    "self.hedge_below":           ("SELF_HEDGE_BELOW",             True),
    "self.hedge_line":            ("SELF_HEDGE_LINE",              True),
    "self.greet":                 ("SELF_GREET",                   True),
    "self.skills":                ("SELF_SKILLS",                  True),
    "self.skills_in_prompt":      ("SELF_SKILLS_IN_PROMPT",        True),
    "self.max_skills":            ("SELF_MAX_SKILLS",              True),
    "self.projects":              ("SELF_PROJECTS",                True),
    "self.projects_in_prompt":    ("SELF_PROJECTS_IN_PROMPT",      True),
    "situation.enabled":          ("SITUATION_ENABLED",            True),

    "portrait.model":             ("PORTRAIT_MODEL",               True),
    "portrait.browser":           ("PORTRAIT_BROWSER",             True),
    "portrait.size":              ("PORTRAIT_SIZE",                True),
    "portrait.hologram.enabled":  ("PORTRAIT_HOLOGRAM_ENABLED",    True),
}

_TRUE = ("1", "true", "yes", "on", "y")
_FALSE = ("0", "false", "no", "off", "n")


def current(path):
    """The value in effect right now, whatever file it came from."""
    name = SETTINGS.get(path, (None, False))[0]

    if name and name in globals():
        return globals()[name]

    node = settings

    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None

        node = node[part]

    return node


def _stored(path):
    """The value as it sits in config.json, or None if it isn't there.

    Preferred over the live constant when deciding a type: config.py
    wraps most numbers in float(), so "60" in the file becomes 60.0 in
    memory and writing that back turns every integer setting into a
    decimal for no reason.
    """
    node = settings

    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None

        node = node[part]

    return node


def _coerce(path, raw):
    """Turn terminal text into the type the setting already has."""
    if not isinstance(raw, str):
        return raw

    existing = _stored(path)

    if existing is None:
        existing = current(path)

    text = raw.strip()

    if isinstance(existing, bool):
        if text.lower() in _TRUE:
            return True
        if text.lower() in _FALSE:
            return False

        raise ValueError(f"{path} is on/off - say true or false, not {raw!r}")

    if isinstance(existing, int) and not isinstance(existing, bool):
        try:
            number = float(text)
        except ValueError:
            raise ValueError(f"{path} is a number - {raw!r} isn't one") from None

        # Keep it an int if it still is one, so config.json doesn't
        # gain a decimal point every time you touch it.
        return int(number) if number.is_integer() else number

    if isinstance(existing, float):
        try:
            return float(text)
        except ValueError:
            raise ValueError(f"{path} is a number - {raw!r} isn't one") from None

    return text


def save_setting(path, raw):
    """Write one dotted key into config.json, and apply it if it can be.

    Returns (value, applied_now). Raises ValueError for an unknown key or
    a value of the wrong shape, so /set can say what went wrong.
    """
    if path not in SETTINGS:
        raise ValueError(f"unknown setting {path!r}")

    value = _coerce(path, raw)
    name, live = SETTINGS[path]

    # Write the file first: if saving fails, nothing should look applied.
    _store(path, value)

    if name:
        globals()[name] = value

    return value, live


def _store(path, value):
    """Write one dotted key into config.json, creating the nesting.

    Split out of save_setting because plugin switches aren't in
    SETTINGS and never will be - the core doesn't know what plugins
    exist until it has looked in the folder, and a whitelist it can't
    populate isn't a whitelist.
    """
    stored = _load_json(CONFIG_FILE)
    node = stored
    parts = path.split(".")

    for part in parts[:-1]:
        existing = node.get(part)
        node = node.setdefault(part, {}) if isinstance(existing, (dict, type(None))) else {}

    node[parts[-1]] = value

    with open(CONFIG_FILE, "w") as file:
        json.dump(stored, file, indent=4)
        file.write("\n")

    settings.clear()
    settings.update(stored)
