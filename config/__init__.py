"""Every setting, as one namespace: config.LM_URL, config.MOOD_ENABLED...

config.json (how the machine runs) and agent/agent.json (who she is) are
read once, at import, into the constants below. The sections that compute
them are separate files, one job each:

  base.py         where things are read from, and her persona
  server.py       the model server, embeddings, reranking
  voice.py        the TTS server and her voice
  desk.py         the control socket, the TUI and its theme
  listening.py    speech-to-text, voice activity, barge-in, the wake word
  abilities.py    logging, vision, the desktop, tool switches, knowledge, ComfyUI, the camera
  moods.py        her moods
  permissions.py  what needs asking: email, files, job folders, the clipboard
  chat.py         plugins and the shared stream-chat policy
  mind.py         history, memory, the thought log, adaptive thinking, lessons, skills...
  portrait.py     her portrait, MCP servers, the live monitor
  actions.py      tool calling, alarms, reminders, the shell, the web

This file is the namespace itself. Every section's values are pulled in
here, in that order, and the functions that run later - /set (current,
save_setting), plugin_settings - live here too, so the value they read or
change is the one everyone else reads as config.X. Read settings as
config.X (or `from config import X` for ones that never change at run
time); never from a section module, which keeps its import-time value.
"""
import json

from .base import *  # noqa: F401,F403
from .server import *  # noqa: F401,F403
from .voice import *  # noqa: F401,F403
from .desk import *  # noqa: F401,F403
from .listening import *  # noqa: F401,F403
from .abilities import *  # noqa: F401,F403
from .moods import *  # noqa: F401,F403
from .permissions import *  # noqa: F401,F403
from .chat import *  # noqa: F401,F403
from .mind import *  # noqa: F401,F403
from .portrait import *  # noqa: F401,F403
from .actions import *  # noqa: F401,F403
from .base import CONFIG_FILE, _load_json, settings  # noqa: F401 - used below
from .chat import CHAT_CONTEXT_LINES, CHAT_COOLDOWN_SECONDS, CHAT_MAX_MESSAGE_CHARS, CHAT_TOOLS  # noqa: F401
from .chat import CHAT_USER_COOLDOWN_SECONDS, _plugins_cfg  # noqa: F401


# -------------------------
# Plugins: each one's settings at run time
# -------------------------
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
    "tts.strip_tilde":            ("TTS_STRIP_TILDE",              True),
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
    "knowledge.enabled":          ("KNOWLEDGE_ENABLED",            True),
    "knowledge.folders":          ("KNOWLEDGE_FOLDERS",            True),
    "knowledge.auto":             ("KNOWLEDGE_AUTO",               True),
    "knowledge.auto_passages":    ("KNOWLEDGE_AUTO_PASSAGES",      True),
    "knowledge.min_score":        ("KNOWLEDGE_MIN_SCORE",          True),

    "comfyui.url":                ("COMFY_URL",                    True),

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
    "mood.intensity":             ("MOOD_INTENSITY",               True),
    "mood.prompt":                ("MOOD_PROMPT",                  True),
    "mood.face":                  ("MOOD_FACE",                    True),
    "mood.gestures":              ("MOOD_GESTURES",                True),
    "mood.emotes":                ("MOOD_EMOTES",                  True),
    "mood.walk_away":             ("MOOD_WALK_AWAY",               True),
    "mood.walk_away_after":       ("MOOD_WALK_AWAY_AFTER",         True),
    "mood.walk_away_minutes":     ("MOOD_WALK_AWAY_MINUTES",       True),

    "email.enabled":              ("EMAIL_ENABLED",                True),
    "email.send":                 ("EMAIL_SEND",                   True),
    "email.max":                  ("EMAIL_MAX",                    True),

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
    "tools.routing":              ("TOOLS_ROUTING",                True),
    "tools.route_groups":         ("TOOLS_ROUTE_GROUPS",           True),
    "tools.sticky_turns":         ("TOOLS_STICKY_TURNS",           True),

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
    "adaptive.job_budget":        ("ADAPTIVE_JOB_BUDGET",          True),
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
    "portrait.frame":             ("PORTRAIT_FRAME",               True),
    "portrait.touch_talk":        ("PORTRAIT_TOUCH_TALK",          True),
    "portrait.touch_talk_cooldown": ("PORTRAIT_TOUCH_TALK_COOLDOWN", True),
    "portrait.hologram.enabled":  ("PORTRAIT_HOLOGRAM_ENABLED",    True),
    "portrait.gestures":          ("PORTRAIT_GESTURES",            True),
    "portrait.chat_gestures":     ("PORTRAIT_CHAT_GESTURES",       True),
    "portrait.meaning_margin":    ("PORTRAIT_MEANING_MARGIN",      True),
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

    if path == "portrait.frame":
        if text.lower() not in ("bust", "full", "face"):
            raise ValueError(f"portrait.frame is bust, full or face, not {raw!r}")
        return text.lower()

    if path == "camera.device":   # a number, a /dev path or a URL
        return int(text) if text.lstrip("-").isdigit() else text

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

    # plugin_settings reads this; keep it pointing at the fresh block
    global _plugins_cfg
    _plugins_cfg = settings.get("plugins", {})
