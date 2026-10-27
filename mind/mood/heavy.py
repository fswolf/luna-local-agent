"""Heavy moments: noticing when you're having a really hard time.

Nothing else in her mood changes because of this. Her dials, the lewd
row, the grudge and walking away all carry on exactly as before; this
only adds one line to her prompt while it lasts, so she knows what's
going on and decides for herself what to do with it.

Where it comes from: the one mood call that already reads every exchange
(appraise.py) answers one more word, how heavy your message was:

    normal   everyday, even annoyed or joking ("this bug is killing me")
    rough    a bad day, stress, feeling down
    heavy    really not okay

Read by meaning, not a word list, and the heaviest thing in the message
counts, even said in passing at the end of a list of small complaints.

    heavy           counts at once
    rough           two in a row (ROUGH_TURNS) before it counts
    normal          two in a row (FADE_TURNS) step it down a level
    six quiet hours and it's gone (a new day starts fresh)

No helplines, no canned safety text, no checklist of questions: one line
about being present, in the same state-of-affairs style as her mood
line. The wording and the switch are in moods.json ("heavy"); off means
she's exactly as she was.
"""
import threading
import time

import config
from core import logbook
from mind.mood.files import moods

LEVELS = {"normal": 0, "rough": 1, "heavy": 2}
ROUGH_TURNS = 2
FADE_TURNS = 2
FORGET = 6 * 3600

DEFAULTS = {
    "enabled": True,
    "rough": ("{user} has had a rough time today. Go a little easier on {them}: warm and "
              "attentive, and let {them} talk it out. You don't need to fix it."),
    "heavy": ("{user} is having a really hard time right now. Be with {them}: gentle, present, "
              "short warm replies. Listen more than you fix, no advice or lectures unless asked, "
              "and don't push anything; follow {their} lead. It's okay to just keep {them} company."),
}

_lock = threading.Lock()
_st = {"level": 0, "rough": 0, "calm": 0, "at": 0.0}
_owner = {"now": False}      # is the turn being read yours? (core/assistant.py sets it)


def listening(owner):
    """Set before the mood read starts: only your own messages count."""
    _owner["now"] = bool(owner)


def owner_turn():
    """Was the read that's starting one of your turns? Used up once read, so a touch's
    or anything else's mood read after it doesn't count as you."""
    yours, _owner["now"] = _owner["now"], False
    return yours


def settings():
    s = dict(DEFAULTS)
    s.update(moods().get("heavy") or {})
    return s


def reset():
    with _lock:
        _st.update(level=0, rough=0, calm=0, at=0.0)


def level(now=None):
    """0 normal, 1 rough, 2 heavy."""
    now = time.time() if now is None else now
    with _lock:
        if _st["level"] and now - _st["at"] > FORGET:
            _st.update(level=0, rough=0, calm=0)
        return _st["level"]


def note(word, now=None):
    """One appraised message's weight: "normal", "rough" or "heavy" (anything else is ignored)."""
    if word not in LEVELS:
        return
    now = time.time() if now is None else now
    level(now)                                  # forget a stale one first
    with _lock:
        before = _st["level"]
        if word == "heavy":
            _st.update(level=2, calm=0)
        elif word == "rough":
            _st["rough"] += 1
            _st["calm"] = 0
            if _st["level"] < 1 and _st["rough"] >= ROUGH_TURNS:
                _st["level"] = 1
        else:
            _st["rough"] = max(0, _st["rough"] - 1)
            if _st["level"]:
                _st["calm"] += 1
                if _st["calm"] >= FADE_TURNS:
                    _st.update(level=_st["level"] - 1, calm=0)
        if word != "normal":
            _st["at"] = now
        after = _st["level"]
    if after != before:
        logbook.info("mood", "heavy: %s -> %s", _name(before), _name(after))


def describe():
    """For /mood: "" when it's normal."""
    n = level()
    if not n:
        return ""
    return "Heavy moment: " + ("really hard time" if n == 2 else "rough day") + (
        "" if settings().get("enabled", True) else " (noticed, but switched off in moods.json)")


def _name(n):
    return next(k for k, v in LEVELS.items() if v == n)


def line(private=True):
    """The prompt line while it lasts, or ""."""
    if not private or not (config.MOOD_ENABLED and getattr(config, "MOOD_PROMPT", True)):
        return ""
    s = settings()
    n = level()
    if not s.get("enabled", True) or not n:
        return ""
    from core import turnctx
    if turnctx.current().speaker:
        return ""                               # a guest is talking: your hard time isn't theirs to hear
    from mind.mood import walkaway
    if walkaway.away():
        return ""                               # she's gone; only alarms and reminders get through
    text = str(s.get("heavy" if n == 2 else "rough") or "").strip()
    if not text:
        return ""
    words = {"user": getattr(config, "USER", "the user"), "them": getattr(config, "USER_THEM", "them"),
             "their": getattr(config, "USER_THEIR", "their")}
    try:
        text = text.format(**words)
    except (KeyError, IndexError, ValueError):
        pass                                    # a hand-edited line with stray braces: use it as written
    return f"\n{text}\n"
