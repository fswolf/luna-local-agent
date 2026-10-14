"""Where everything is read from: config.json and agent/agent.json, and
who she is (name, personality, rules).

Part of the config package (it was one config.py); see config/__init__.py.
"""
import json
import os
from datetime import datetime as _datetime

# When this run started - config is the first thing everything imports.
# reflect.py uses it to tell this session's turns from the last one's.
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

