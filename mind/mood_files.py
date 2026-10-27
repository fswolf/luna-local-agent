"""Her moods file (agent/moods.json): loading it, checking it, and the
built-in moods used when it's missing or broken. Reloaded when it changes.

Part of mind/mood.py, which re-exports all of this.
"""
import json
import os
from core import logbook
from config import BASE_DIR
MOODS_FILE = os.path.join(BASE_DIR, "agent", "moods.json")


# ---------------------------------------------------------------------------
# The moods file
# ---------------------------------------------------------------------------
# Used when agent/moods.json is missing or broken, so a typo in the file
# costs you your edits, never a working assistant. The shipped file is
# the real list; this is the smallest thing that still makes sense.
_FALLBACK = {
    "energy": {"edges": [-0.20, 0.35], "words": ["tired", "even", "wired"]},
    "warmth": {"edges": [-0.20, 0.35, 0.66], "words": ["cool", "neutral", "warm", "very warm"]},
    "grid": [["sad", "annoyed", "mad"], ["tired", "calm", "focused"],
             ["sleepy", "happy", "excited"], ["cuddly", "loving", "flirty"]],
    "lewd": {"row": ["teasing", "frisky", "heated"], "enter": 0.6},
    "grudge": {"row": ["sulky", "hurt", "furious"], "minutes": 20},
    "states": {},
    "feelings": {},
}
_moods = {"data": None, "mtime": None, "error": ""}


def _check(data):
    """The file's shape, or a ValueError saying what's wrong with it."""
    energy, warmth = data.get("energy") or {}, data.get("warmth") or {}
    e_edges, w_edges = list(energy.get("edges") or []), list(warmth.get("edges") or [])
    grid = data.get("grid") or []

    if len(grid) != len(w_edges) + 1:
        raise ValueError(f"grid has {len(grid)} rows but warmth has {len(w_edges)} edges - "
                         "it needs one more row than edges")

    for row in grid:
        if len(row) != len(e_edges) + 1:
            raise ValueError(f"grid row {row} needs {len(e_edges) + 1} moods, one more "
                             "than energy has edges")

    if e_edges != sorted(e_edges) or w_edges != sorted(w_edges):
        raise ValueError("edges must go from low to high")

    for extra in ("lewd", "grudge"):
        row = (data.get(extra) or {}).get("row")
        if row is not None and len(row) != len(e_edges) + 1:
            raise ValueError(f"{extra}.row needs {len(e_edges) + 1} moods, one per energy band")

    data["energy"] = dict(energy, edges=e_edges)
    data["warmth"] = dict(warmth, edges=w_edges)
    data["states"] = data.get("states") or {}
    data["feelings"] = data.get("feelings") or {}

    return data


def moods():
    """agent/moods.json, re-read whenever it changes on disk."""
    try:
        mtime = os.path.getmtime(MOODS_FILE)
    except OSError:
        mtime = None

    if _moods["data"] is not None and mtime == _moods["mtime"]:
        return _moods["data"]

    _moods["mtime"] = mtime

    try:
        with open(MOODS_FILE, encoding="utf-8") as handle:
            _moods["data"] = _check(json.load(handle))
        _moods["error"] = ""
    except (OSError, ValueError) as e:
        if _moods["data"] is None:     # keep the last good copy if there is one
            _moods["data"] = _FALLBACK
        _moods["error"] = f"agent/moods.json: {e}"
        logbook.warn("mood", "%s - %s", _moods["error"],
                     "keeping the last good version" if _moods["data"] is not _FALLBACK
                     else "using the built-in names")

    return _moods["data"]
