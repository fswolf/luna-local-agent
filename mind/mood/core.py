"""Her state, in one place (S), the locks around it, and the small rules every other
piece leans on: the grudge's ceiling, desire only living at warm and up, which
row a mood belongs to.

Part of mind/mood (see mind/mood/__init__.py).
"""
import threading
import time
import config
from mind.mood.files import _FALLBACK, moods


class State:
    """Everything her mood is, right now. One of it (S), shared by every piece;
    read and change it holding _lock (away_state: _away_lock)."""

    def __init__(self):
        self.energy = 0.0
        self.warmth = 0.0
        self.started = time.monotonic()
        self.last_turn = None
        self.recent = []            # (what, when) - the last few nudges, for /mood
        self.busy = []              # (when, gpu %) while she waits - see drift._sample_machine
        self.chat_seen = 0          # chat messages counted at the last turn
        self.label = ""             # the current label, kept sticky
        self.phrasing = {}          # per state, which wording to use next time she's in it
        self.clean_run = 0          # turns since the last thing went wrong
        self.desire = 0.0           # 0..1, the lewd row's dial: builds only while she's warm
        self.grudge_until = 0.0     # time.time() a grudge ends, or 0
        self.affection_recent = 0.0
        self.last_rating = None     # what the last message scored, for /mood
        self.last_feeling = None    # the last quick feeling, for /mood
        self.spanks = {"n": 0.0, "at": 0.0}
        # Plugins live somewhere lewd isn't allowed (show.set_tame)
        self.tamed_by = set()
        # Walking away (walkaway.py)
        self.away_state = {"until": 0.0, "said": False, "hostile": 0, "last": 0.0}


S = State()

_lock = threading.Lock()

# Walking away has its own lock: it's touched from the appraisal worker (one
# per turn, so two can finish together), the come-back timer and the turn
# itself. Nothing slow or re-entrant (logging, _announce) runs while it's held.
_away_lock = threading.Lock()


def _clamp(value):
    return max(-1.0, min(1.0, value))


def _intensity():
    """mood.intensity: 0 flat .. 1 as designed .. 2 very visible."""
    try:
        return max(0.0, min(2.0, float(getattr(config, "MOOD_INTENSITY", 1.0))))
    except (TypeError, ValueError):
        return 1.0


def _state(name):
    return (moods().get("states") or {}).get(name) or {}


def _extra(name):
    """moods.json lewd / grudge, falling back to the built-in names."""
    spec = dict(_FALLBACK[name])
    spec.update(moods().get(name) or {})
    return spec


def _grudging():
    """Seconds of grudge left, or 0. Caller holds _lock or doesn't care."""
    return max(0.0, S.grudge_until - time.time()) if S.grudge_until else 0.0


def _ceiling():
    """While she holds a grudge her warmth stays in the cool band."""
    return moods()["warmth"]["edges"][0] - 0.05


def _row_of(name):
    """'lewd' or 'grudge' if the mood is in one of those rows, else ''."""
    for row in ("lewd", "grudge"):
        if name in _extra(row)["row"]:
            return row
    return ""


def _warm_enough():
    """Desire only lives at warm and above."""
    edges = moods()["warmth"]["edges"]
    return S.warmth >= edges[-2] if len(edges) >= 2 else S.warmth > 0


def _settle():
    """After any change: the grudge's ceiling, and desire dies below warm.
    Caller holds _lock."""

    if S.grudge_until and not _grudging():
        S.grudge_until = 0.0

    if S.grudge_until:
        S.warmth = min(S.warmth, _ceiling())
        S.desire = 0.0
    elif not _warm_enough():
        S.desire = 0.0


# Walking away's switch and lines; walkaway.py has the rest (and why).
def _walk():
    return moods().get("walk_away") or {}


def walk_away_on():
    return bool(config.MOOD_ENABLED and getattr(config, "MOOD_WALK_AWAY", True))
