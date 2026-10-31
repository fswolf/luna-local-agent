"""Surviving a restart: the dials saved after every turn, and restored faded by
however long she was closed.

Part of mind/mood (see mind/mood/__init__.py).
"""
import json
import os
import time
from core import logbook
from config import BASE_DIR
from mind.mood.core import S, _clamp, _lock, _settle
from mind.mood import drift


STATE_FILE = os.path.join(BASE_DIR, "agent", "mood.json")


# ---------------------------------------------------------------------------
# Surviving a restart
# ---------------------------------------------------------------------------
def _save():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

        with open(STATE_FILE, "w", encoding="utf-8") as handle:
            json.dump({"energy": round(S.energy, 3),
                       "warmth": round(S.warmth, 3),
                       "desire": round(S.desire, 3),
                       "grudge_until": round(S.grudge_until),
                       "at": time.time()}, handle)
    except OSError:
        pass  # a mood is not worth failing a turn over


def _restore():
    """Pick up where we left off, faded by however long that was.

    Closing the app for five minutes shouldn't wipe the evening; closing
    it overnight shouldn't have last night's mood leak into the morning.
    So the saved dials are pulled toward today's baseline in proportion
    to the gap, and are gone entirely after about four hours.
    """

    try:
        with open(STATE_FILE, encoding="utf-8") as handle:
            saved = json.load(handle)

        away = max(0.0, time.time() - float(saved["at"]))
        faded = min(1.0, away / (4 * 3600))
        energy, warmth = float(saved["energy"]), float(saved["warmth"])
        desire, grudge = float(saved.get("desire", 0)), float(saved.get("grudge_until", 0))
    except (OSError, ValueError, KeyError, TypeError):
        return False

    with _lock:
        S.energy = _clamp(energy + (drift._energy_baseline() - energy) * faded)
        S.warmth = _clamp(warmth + (drift._warmth_baseline() - warmth) * faded)
        S.desire = max(0.0, desire * 0.5 ** (away / 1200.0))
        S.grudge_until = grudge if grudge > time.time() else 0.0
        _settle()

    logbook.info("mood", "restored after %.1f min away (%.0f%% faded)",
                 away / 60, faded * 100)

    return True
