"""What a turn did to her: the side question's answer turned into warmth and
energy, desire (the lewd row's dial) and the grudge, a quick feeling on her
face, a compliment's emote - and spanks.

Part of mind/mood (see mind/mood/__init__.py).
"""
import threading
import time
import config
from core import logbook
from mind.mood.core import S, _extra, _grudging, _intensity, _lock, _settle, _warm_enough
from mind.mood.files import moods
from mind.mood import appraise, drift, show, walkaway


# ---------------------------------------------------------------------------
# Being nice to her: the one model call that reads each exchange, and why,
# is in mind/appraise.py. What it does to her dials is below.
# ---------------------------------------------------------------------------

# The lewd row's dial. Desire builds from flirting while she's warm,
# fades a little every turn, and one hostile exchange wipes it: quick to
# warm up, quicker to kill.
DESIRE_FLIRT = {1: 0.12, 2: 0.22}   # per flirtatious message (field 5)
DESIRE_AFFECTION = 0.04            # a clearly affectionate message adds a little
DESIRE_FADE = 0.02                 # every turn
HOSTILE_HIT = 0.27                 # warmth, on top of the exchange's own -0.08



def _apply_exchange(said, answer, model):

    rating, energy, warmth, feeling, flirt = appraise._appraise(said, answer, model)

    with _lock:
        # Repeats fade: the fifth kind word in a row shouldn't land like
        # the first, which is both truer and stops the dial being a
        # button. Everything decays as turns pass, so affection spread
        # through a conversation keeps its value.
        #
        # The taper used to be 1/(1+n), which halved the second kind
        # word and quartered the fourth - so a conversation where you
        # were consistently warm registered less than a single stray
        # "thanks". It tapers now, it doesn't collapse.
        scaled = appraise._RATING.get(rating, 0.0) / (1.0 + S.affection_recent * 0.4)

        if rating >= 1:
            S.affection_recent += 1.0

        S.last_rating = rating
        S.last_feeling = feeling

    if scaled:
        drift._nudge(energy=scaled * 0.45, warmth=scaled, why=f"you were warm with her ({rating})")

    # The exchange itself: small, and a cold one smaller than a warm one
    # - she bounces back from a rough moment on her own anyway.
    if energy or warmth:
        drift._nudge(energy=0.06 * energy, warmth=0.05 * warmth if warmth > 0 else 0.08 * warmth,
               why="that " + ("livened her up" if energy > 0 else "wore on her" if energy < 0
                              else "warmed her" if warmth > 0 else "stung a bit"))

    if feeling:
        _feel(feeling)

    _layers(rating, warmth, flirt)
    _compliment(rating, feeling)
    walkaway._count_hostility(rating, warmth)


def _layers(rating, warmth, flirt):
    """Desire and the grudge, from one appraised exchange."""

    if warmth < 0:
        # Hostile: desire gone at once, a real dent in warmth, and if
        # that leaves her cool, a grudge (another insult restarts it).
        with _lock:
            S.desire = 0.0
        drift._nudge(warmth=-HOSTILE_HIT, why="that was hostile")

        with _lock:
            cool = S.warmth < moods()["warmth"]["edges"][0]
            if cool or _grudging():
                minutes = float(_extra("grudge").get("minutes", 20))
                started = not _grudging()
                S.grudge_until = time.time() + minutes * 60
                _settle()
            else:
                started = None
        if started is not None:
            logbook.info("mood", "grudge %s (%.0f min)", "started" if started else "restarted", minutes)
            drift._nudge(why="holding a grudge")
        return

    with _lock:
        if _grudging():
            # Making up: an apology or clear warmth ends it here and now.
            if rating >= 2 or warmth > 0:
                made_up = True          # _make_up clears it, outside the lock
            else:
                return
        else:
            made_up = False
            gain = DESIRE_FLIRT.get(flirt, 0.0) + (DESIRE_AFFECTION if rating >= 2 else 0.0)

            if gain and _warm_enough():
                S.desire = min(1.0, S.desire + gain / (1.0 + S.affection_recent * 0.2))
            else:
                gain = 0.0

    if made_up:
        _make_up("you made up")
    elif gain:
        show._announce()


def _make_up(why):
    """An apology landed: the grudge is over and she softens a little."""

    with _lock:
        if not S.grudge_until:
            return
        S.grudge_until = 0.0

    logbook.info("mood", "grudge over: %s", why)
    drift._nudge(warmth=0.10, why=why)


def _compliment(rating, feeling):
    """A clear compliment (moods.json "compliment": its rating and up)
    shows its emote, unless the feeling it raised already shows one."""
    spec = moods().get("compliment") or {}
    name = show._emote(spec.get("emote"))

    if not name or rating < int(spec.get("rating", 2)):
        return

    if feeling and ((moods().get("feelings") or {}).get(feeling) or {}).get("emote"):
        return

    try:
        from web import livefeed

        livefeed.emit("emote", name=name)
    except Exception:
        pass


def _feel(feeling):
    """A quick feeling: on her face for a few seconds, a gesture if it has
    one, and a small push on the slow dials."""
    spec = (moods().get("feelings") or {}).get(feeling) or {}
    nudge = list(spec.get("nudge") or [0, 0]) + [0, 0]

    if nudge[0] or nudge[1]:
        drift._nudge(float(nudge[0]), float(nudge[1]))

    if not config.MOOD_ENABLED:
        return

    k = min(1.0, _intensity())

    if k <= 0:
        return

    try:
        from web import livefeed

        face = {f: round(float(v) * k, 3) for f, v in (spec.get("face") or {}).items()} \
            if getattr(config, "MOOD_FACE", True) else {}
        gesture = spec.get("gesture") if getattr(config, "MOOD_GESTURES", True) else None
        livefeed.emit("feeling", name=feeling, face=face, gesture=gesture or "",
                      emote=show._emote(spec.get("emote")), seconds=float(spec.get("seconds", 6)))
    except Exception:
        pass


def note_exchange(said, answer, model=None):
    """Notice what that exchange did to her. Fire and forget.

    On a worker because it is a model call and a mood must never be
    something a turn waits for.
    """

    with _lock:
        S.affection_recent *= 0.6

    if not (config.MOOD_ENABLED and config.MOOD_AFFECTION and model):
        return

    if not str(said or "").strip():
        return

    threading.Thread(target=_apply_exchange, args=(said, answer, model),
                     daemon=True).start()


def note_affection(text, model=None):
    """Older name: just your message, no answer to read."""
    note_exchange(text, "", model)


def last_feeling():
    with _lock:
        return S.last_feeling


# Spanks (the portrait, in her top two rows): fun up to a point, then a
# punishment, tamagotchi style. Each one counts; they're forgotten one every
# SPANK_FORGET seconds; every SPANK_LIMIT knocks her down a notch - warmth and
# desire - so keeping at it takes her out of the mood.
SPANK_LIMIT = 60
SPANK_FORGET = 10.0
SPANK_WARMTH = -0.10
SPANK_DESIRE = -0.20


def note_spank():
    """One spank on the portrait. True if it was one too many (a notch down)."""

    if not config.MOOD_ENABLED:
        return False

    now = time.time()

    with _lock:
        before = max(0.0, S.spanks["n"] - (now - S.spanks["at"]) / SPANK_FORGET) if S.spanks["at"] else 0.0
        S.spanks.update(n=before + 1.0, at=now)
        over = int(S.spanks["n"] // SPANK_LIMIT) > int(before // SPANK_LIMIT)
        if over:
            S.desire = max(0.0, S.desire + SPANK_DESIRE)

    if over:
        logbook.info("mood", "spanked %d times: a notch down", int(S.spanks["n"]))
        drift._nudge(warmth=SPANK_WARMTH, energy=-0.03, why="too many spanks")

    return over
