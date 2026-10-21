"""First start: Luna asks a few things before anything else.

On a fresh install agent/agent.json has no "user" block, so she doesn't
know who she's talking to. The first time she starts, before the model
is even needed, she asks:

    1. what to call you
    2. your pronouns (or skip)
    3. what you mostly want her for: Assistant, Companion or Streamer
       (config/presets.py), or skip to keep the defaults

and writes the answers: your name and pronouns to agent.json's user
block, the preset to config.json. It's scripted, not the model talking,
so it works before the model server is up. /skip at any point ends it
(an empty user block is written, so it doesn't ask again); after that,
agent.json and /settings change anything.
"""
import json
import os

import config

_state = {"step": None, "name": "", "pronouns": ""}

STEPS = ("name", "pronouns", "preset")
_PRONOUNS = {"1": "he/him", "2": "she/her", "3": "they/them", "he": "he/him", "she": "she/her",
             "they": "they/them", "he/him": "he/him", "she/her": "she/her", "they/them": "they/them"}
_PRESETS = {"1": "assistant", "2": "companion", "3": "streamer"}


def needed():
    """True on a first start: agent.json has no user block at all."""
    return "user" not in (config.agent or {})


def active():
    return _state["step"] is not None


def _say(text):
    import ui

    ui.add_message(config.AGENT_NAME.lower(), text)


def _note(text):
    import ui

    ui.add_message("system", text)


def maybe_start():
    """Begin the setup if this is a first start. Returns True if it began."""
    if not needed() or active():
        return False
    _state.update(step="name", name="", pronouns="")
    _say(f"Hi, I'm {config.AGENT_NAME}! Before we start, a few quick things so I know who I'm talking to. "
         "What should I call you?")
    _note("Type your answer and press Enter. /skip skips the setup.")
    return True


def handle(text):
    """A line typed during the setup. True if it was the setup's to take."""
    if not active():
        return False

    text = " ".join(str(text or "").split())

    if text.lower() in ("/skip", "skip setup"):
        _finish(skipped=True)
        return True
    if text.startswith("/"):
        return False                     # other commands still work mid-setup

    import ui

    ui.add_message("user", text)          # your answer, in the conversation like any line
    step = _state["step"]

    if step == "name":
        name = text[:40].strip(" .!")
        if not name:
            _say("Just a name or a nickname is fine. What should I call you?")
            return True
        _state.update(name=name, step="pronouns")
        _say(f"Nice to meet you, {name}! What pronouns do you use?")
        _note("1 he/him   2 she/her   3 they/them   or type your own (like xe/xem/xyr), or skip")
        return True

    if step == "pronouns":
        low = text.lower()
        if low and low not in ("skip", "-", "none"):
            words = [w for w in low.replace(" ", "").split("/") if w]
            _state["pronouns"] = _PRONOUNS.get(low) or ("/".join(words[:3]) if words and all(
                w.isalpha() and len(w) <= 12 for w in words[:3]) else "")
        _state["step"] = "preset"
        _say("Last one: what do you mostly want me for?")
        _note("1 Assistant: calm and to the point, moods turned down\n"
              "2 Companion: me as designed, moods, a voice that follows them, emotes\n"
              "3 Streamer: livelier on camera, nothing lewd while live\n"
              "skip keeps the defaults. You can change it any time with /preset or /settings.")
        return True

    if step == "preset":
        low = text.lower()
        preset = _PRESETS.get(low) or (low if low in _PRESETS.values() else None)
        if low not in ("skip", "-", "none", "") and preset is None:
            _say("Pick 1, 2 or 3, or type skip to keep the defaults.")
            return True
        _finish(preset=preset)
        return True

    return False


def save_user(name, pronouns):
    """Write agent.json's user block (keeping everything else) and apply it
    now: the prompt's who-you're-talking-to line reads these."""
    path = config.AGENT_FILE
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = dict(config.agent or {})

    user = {}
    if name:
        user["name"] = name
    if pronouns:
        user["pronouns"] = pronouns
    data["user"] = user

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)

    config.agent["user"] = user
    _apply_user(user)


def _apply_user(user):
    from config import base

    name, (they, them, their), gave = base._who(user)
    values = {"USER_NAME": name, "USER_THEY": they, "USER_THEM": them, "USER_THEIR": their,
              "_USER_GAVE_PRONOUNS": gave, "USER": name or "the user"}
    for key, value in values.items():
        setattr(base, key, value)                 # user_line() reads these
        if not key.startswith("_"):
            setattr(config, key, value)           # and everything else reads config.USER...


def _finish(preset=None, skipped=False):
    name, pronouns = ("", "") if skipped else (_state["name"], _state["pronouns"])
    _state["step"] = None

    try:
        save_user(name, pronouns)
    except OSError as e:
        _note(f"Couldn't save that to agent/agent.json: {e}")
        return

    if preset:
        try:
            import settings_web

            _ok, said, _entry = settings_web.preset(preset)
            _note(said)
        except Exception as e:
            _note(f"Couldn't apply the preset: {e}")

    if skipped:
        _note("Setup skipped. Your name and pronouns go in agent/agent.json's user block whenever you like.")
        return

    _say(f"All set{', ' + name if name else ''}! Ask me what I can do any time, "
         "and /settings has everything else.")
