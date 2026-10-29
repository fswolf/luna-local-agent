"""While you were out: what happened while you were away, for the hello
when you come back.

Things she did or that came up on their own get noted here as they
happen: a reminder that went off, an alarm that rang, a scheduled job
that ran (and how it went). When presence sees you come back after a
while and she greets you (senses/presence.py), the ones from while you
were gone ride along in that greeting, so "welcome back" can come with
"your 3 o'clock reminder went off, and the backup job ran fine".

Only for you: a greeting to someone else (a guest the camera knows)
gets none of it. Each thing is mentioned once, then dropped. Kept in
memory only, for a day at most: a restart starts clean (nothing runs
while she's closed, and reminders due then are raised on their own).

No camera, or you came back and just started typing? Then it rides
along on your next own turn instead (line(), in her prompt), but only
the things that happened while you weren't there: nobody in view when
the camera's watching, else nobody had talked to her for QUIET. A
reminder she just said to your face isn't news. What it told you stays to
hand for FOLLOW_UP minutes after (her hello keeps it in history instead),
so "what went wrong?" has an answer. In the lewd row, a heavy moment or
while she's walked away, the news waits (offers' same holds).

An offer she's holding (life/offers.py) can ride along in the same
greeting; that's offers' own rules.
"""
import threading
import time

import config

KEEP = 30                 # at most this many waiting
MAX_AGE = 24 * 3600       # and none older than a day
QUIET = 10 * 60           # nobody had talked to her this long: you weren't there for it
FOLLOW_UP = 15 * 60       # what line() told you stays to hand this long, for "what failed?"
SOURCES = ("typed", "voice", "station")   # your own turns (line())

_lock = threading.Lock()
_items = []               # {"at": time.time(), "kind": str, "text": str, "quiet": bool}
_said = []                # what line() told you, with "said": time.time(), for follow-ups


def _nobody_around():
    """Were you away when it happened? With the camera watching, it knows: nobody in
    view. Without it, a guess: nobody had talked to her for QUIET. False when she
    can't tell."""
    try:
        from senses import presence
        if presence.running():
            return bool(presence.nobody_here())
    except Exception:
        pass
    try:
        from mind import reflect
        return reflect.idle_seconds() >= QUIET
    except Exception:
        return False


def note(kind, text, now=None, quiet=None):
    """Something worth telling you about if you weren't there for it."""
    text = " ".join(str(text or "").split())[:240]
    if not text:
        return
    now = time.time() if now is None else now
    quiet = _nobody_around() if quiet is None else bool(quiet)
    with _lock:
        _items.append({"at": now, "kind": str(kind), "text": text, "quiet": quiet})
        _items[:] = [i for i in _items if now - i["at"] < MAX_AGE][-KEEP:]


def since(start, now=None):
    """What's been noted since start (time.time()), oldest first."""
    now = time.time() if now is None else now
    with _lock:
        return [dict(i) for i in _items if i["at"] >= start and now - i["at"] < MAX_AGE]


def clear(upto=None):
    """Drop everything noted up to upto (default: now): it's been said (in her hello,
    which keeps it in history itself)."""
    upto = time.time() if upto is None else upto
    with _lock:
        _items[:] = [i for i in _items if i["at"] > upto]
        _said.clear()


def _clock(at, now=None):
    """"3:10 pm", or "yesterday 11:40 pm" for one from before today."""
    now = time.time() if now is None else now
    t = time.localtime(at)
    when = time.strftime("%I:%M %p", t).lstrip("0").lower()
    return when if t[:3] == time.localtime(now)[:3] else f"yesterday {when}"


def facts(items, now=None):
    """The items as plain lines ("- 3:10 pm: ..."), for a prompt or for history."""
    return "\n".join(f"- {_clock(i['at'], now)}: {i['text']}" for i in items)


def block(start, now=None):
    """The greeting's lines about what happened since start, or ""."""
    items = since(start, now)
    if not items:
        return ""
    return ("While they were away:\n" + facts(items[-8:], now) + "\n"
            "After the hello, mention what's worth knowing, briefly and in your own words; "
            "something that went wrong comes first. Skip what doesn't matter.")


def line(private=True):
    """The prompt line for your own turn, when things happened while you were away
    and no greeting has told you yet; "" otherwise. Said once."""
    try:
        return _line(private)
    except Exception:
        return ""


def _line(private):
    from core import turnctx

    if not private:
        return ""
    turn = turnctx.current()
    if hasattr(turn, "away_said"):              # the same turn building its prompt again
        return turn.away_said
    if turn.source not in SOURCES or not turn.private or turn.speaker or turn.remote or turn.job:
        return ""
    from life import offers
    if offers._quiet_now():                     # lewd row, a heavy moment, walked away: it keeps
        return ""
    now = time.time()
    with _lock:
        items = [i for i in _items if i.get("quiet") and now - i["at"] < MAX_AGE][-8:]
        if items:
            last = items[-1]["at"]
            _items[:] = [i for i in _items if not (i.get("quiet") and i["at"] <= last)]
        # the prompt line isn't kept in history: what she told you in the last
        # FOLLOW_UP minutes stays to hand, so "what went wrong?" has an answer
        _said[:] = [i for i in _said if now - i["said"] < FOLLOW_UP][-8:]
        told = [dict(i) for i in _said]
        _said.extend(dict(i, said=now) for i in items)
    user = getattr(config, "USER", "the user")
    text = ""
    if items:
        text = (f"\nWhile {user} was away:\n" + facts(items, now)
                + "\nMention what's worth knowing, briefly and once, if it fits; something that "
                  "went wrong comes first. Answer what they said first.\n")
    elif told:
        text = (f"\nWhat you told {user} happened while they were away (don't bring it up again; "
                "it's here in case they ask):\n" + facts(told, now) + "\n")
    if turnctx.active():
        turn.away_said = text
    return text
