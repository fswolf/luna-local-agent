"""Shared by the toy plugins (lovense.py, buttplug.py): when she may start
a device, the stop words, and the line that tells her one is connected.

Not a plugin itself: the leading underscore keeps the loader away.
"""
import re

import config
import state

# Said by you, any of these stops every device before she even reads the
# message - a stop that depends on a model noticing isn't a stop. Whole
# words, any case. Override with "stop_words" in the plugin's settings.
STOP_WORDS = ["stop", "red", "safeword", "enough", "too much", "pause", "ow", "ouch"]


def blocked():
    """Why a device can't be *started* from this turn, or ''. Stopping is
    never blocked."""
    if getattr(state.job, "name", None):
        return "Not from a scheduled job. Tell him instead."

    seen = getattr(getattr(state, "untrusted", None), "seen", None)

    if seen:
        return (f"Not from this turn - it read outside content ({seen}), and that "
                "can't be what switches this on. Ask him directly.")

    return ""


def says_stop(text, name):
    """Does this message contain one of the plugin's stop words?"""
    words = config.plugin_settings(name).get("stop_words", STOP_WORDS)

    if not isinstance(words, (list, tuple)) or not words:
        return False

    pattern = r"\b(?:" + "|".join(re.escape(str(w).strip()) for w in words if str(w).strip()) + r")\b"

    return bool(re.search(pattern, str(text or ""), re.IGNORECASE))


def stop_on_interrupt(name):
    """Interrupting her (HOME, ai-voice-ctl.py stop) stops the devices too,
    unless the plugin's settings say "stop_on_interrupt": false."""
    return config.plugin_settings(name).get("stop_on_interrupt", True) is not False


def prompt_line(devices, tools):
    """The system prompt's note that a device is connected. Plain and
    practical: what's there, which tools, and that stop means stop."""
    return (f"\nConnected toy: {devices}. You can control it with {tools} - when he asks, "
            "or when it fits what you're doing together. Say what you're doing as you "
            "do it, keep to what he's comfortable with, and the moment he says stop, "
            "stop it. A stop word in his message has already stopped it.\n")
