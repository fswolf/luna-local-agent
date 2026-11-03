"""Where everything is read from: config.json and agent/agent.json, and
who she is (name, personality, rules).

Part of the config package (it was one config.py); see config/__init__.py.
"""
import json
import os
from datetime import datetime as _datetime

# When this run started - config is the first thing everything imports.
# mind/reflect.py uses it to tell this session's turns from the last one's.
STARTED = _datetime.now()


# The repo folder: this file is config/base.py.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
# Before the screen is up a problem can be printed; after, print() would
# paint over it, so the log and the conversation carry it instead.
STARTED_UI = [False]


def _load_json(path, on_missing=None, strict=False):
    """Read a JSON file, or explain why not and carry on.

    A stray comma used to take the whole app down on startup with a bare
    JSONDecodeError - and hand-editing these files is the entire point of
    them being JSON, so a typo shouldn't be fatal.
    """
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return {} if on_missing is None else on_missing()
    except (json.JSONDecodeError, OSError) as error:
        if strict:
            raise ValueError(f"{os.path.basename(path)} can't be read ({error}) - "
                             "fix it first, nothing was changed") from None
        _complain(f"Couldn't read {path}: {error}. Carrying on with defaults. The file has "
                  "been left alone - fix the syntax and restart.")
        return {}
    if not isinstance(data, dict):
        if strict:
            raise ValueError(f"{os.path.basename(path)} should hold a {{...}} block, not a "
                             f"{type(data).__name__} - fix it first, nothing was changed")
        _complain(f"{path} should hold a {{...}} block, not a {type(data).__name__}. "
                  "Carrying on with defaults.")
        return {}
    return data


def _complain(text):
    if not STARTED_UI[0]:
        print(f"\n{text}\n")
        return
    try:
        from core import logbook

        logbook.warn("config", "%s", text)
        logbook.tell(text)
    except Exception:
        pass


AGENT_FILE = os.path.join(BASE_DIR, "agent", "agent.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
MEMORY_FILE = os.path.join(BASE_DIR, "agent", "memory.json")

agent = _load_json(AGENT_FILE)
settings = _load_json(CONFIG_FILE)
memory = _load_json(MEMORY_FILE)


def flag(value):
    """An on/off setting as written by hand: "false", "off", "no" and "0"
    are off, as they read. bool() alone would call the text "false" on,
    which for a server that listens on the network is the wrong way round."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes", "y")
    return bool(value)


def setting(key, default=None):
    """A machine setting: config.json first, then agent.json. A block
    (default {}) that's been set to something else, like null, reads as
    the default rather than breaking every .get() after it."""
    value = settings[key] if key in settings else agent.get(key, default)
    if isinstance(default, dict) and not isinstance(value, dict):
        if value is not None:
            _complain(f"config.json: \"{key}\" should be a {{...}} block, not {value!r} - using the defaults")
        return dict(default)
    return value


AGENT_NAME = agent.get("name") or settings.get("name") or "Luna"

# Persona, kept separate from the machine settings so llm.py doesn't have
# to know which file anything came from.
PERSONALITY = agent.get("personality", "")
TONE = agent.get("tone", "")
TRAITS = agent.get("traits", [])
RULES = agent.get("rules", [])

# How her voice says the words Kokoro gets wrong ("nya" spelled out N-Y-A):
# agent.json "pronounce": {"nya": "/njˈɑ/"}, phonemes in Kokoro's own set.
# voice/speech.py sends them as Kokoro's [word](/phonemes/) override; the screen
# never sees it.
PRONOUNCE = agent.get("pronounce", {}) if isinstance(agent.get("pronounce"), dict) else {}

# Who she's talking to, from agent.json's "user" block:
#
#     "user": {"name": "Shannon", "pronouns": "she/her"}
#
# Every prompt that talks about you ("when she asks", "Tell her instead")
# reads these rather than assuming. pronouns: "he", "she" or "they"
# (anything after a slash is ignored: "she/her" is "she"), or three
# words of your own, "xe/xem/xyr" - subject, object, possessive. No name
# means "the user"; no pronouns, or ones it can't read, mean he/him.
_PRONOUNS = {"he": ("he", "him", "his"), "she": ("she", "her", "her"), "they": ("they", "them", "their")}


def _who(block):
    """(name, (they, them, their), understood) from the user block. understood:
    the pronouns were given and made sense - only then are they stated to her
    as yours; he/him as a fallback is just how the prompts word things."""
    block = block if isinstance(block, dict) else {}
    name = " ".join(str(block.get("name") or "").split())[:40]
    words = [w.strip().lower() for w in str(block.get("pronouns") or "").split("/") if w.strip()]
    if len(words) >= 3 and all(w.isalpha() and len(w) <= 12 for w in words[:3]):
        return name, tuple(words[:3]), True
    if words and words[0] in _PRONOUNS:
        return name, _PRONOUNS[words[0]], True
    return name, _PRONOUNS["he"], False


USER_NAME, (USER_THEY, USER_THEM, USER_THEIR), _USER_GAVE_PRONOUNS = _who(agent.get("user"))
USER = USER_NAME or "the user"          # the subject of a prompt line: "when {USER} asks"
# Others in the house (senses/people.py): [{"name": "Shannon", "pronouns": "she/her"}]
PEOPLE = [p for p in (agent.get("people") or []) if isinstance(p, dict) and p.get("name")]


def user_line():
    """The system prompt's line on who she's talking to, or '' when
    agent.json says nothing about them."""
    if not USER_NAME and not _USER_GAVE_PRONOUNS:
        return ""
    who = USER_NAME or "the user"
    if not _USER_GAVE_PRONOUNS:
        return f"You're talking with {who}.\n"
    return f"You're talking with {who} ({USER_THEY}/{USER_THEM}/{USER_THEIR}).\n"


GENERATION = setting("generation", {})

