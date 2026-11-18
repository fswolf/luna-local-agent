"""Her game notes checked against the game itself.

A wrong note is worse than none: she wrote "Oak's lab door is at x=1, y=3"
in her bedroom, it came back every turn, and she spent 27 turns pressing A
at a wall while the turn note said the stairs were at x 7, y 1. These read
the game's own "Where: ..." and "Ways out ...: to X at x 7, y 1" lines (any
reader that writes them), so a note that puts a door or stairs where the
game shows none is turned back when she writes it, and an old one is taken
out of what she sees.

Notes are stamped with the place they were written in, "[your house
(upstairs)] ...", so a note is only checked against the map it's about.
"""
import re

_WHERE = re.compile(r"^Where: (.+?), x (\d+), y (\d+)", re.MULTILINE)
_EXITS = re.compile(r"^Ways out[^:]*:(.*)$", re.MULTILINE)
_EXIT = re.compile(r"\bto (.+?) at x (\d+), y (\d+)")
_XY = re.compile(r"(?<![a-z])x\s*[=:]?\s*(\d{1,3})\s*[,;/]?\s*(?:and\s+)?y\s*[=:]?\s*(\d{1,3})\b", re.IGNORECASE)
_DOORISH = re.compile(r"\b(doors?|doorway|stairs?|staircase|ladder|exit|entrance|way out|warp|enter|leave|outside)\b",
                      re.IGNORECASE)
_STAMP = re.compile(r"^\[([^\]]+)\]\s*")
NEAR = 1        # a step off still counts: "the door" is often the tile in front of it
LISTED = 8      # readers list at most the 8 nearest ways out: a full list may be missing the one a note means


def where(screen):
    """(place, x, y) from the game's Where line, or None."""
    m = _WHERE.search(screen or "")
    return (m.group(1).strip(), int(m.group(2)), int(m.group(3))) if m else None


def exits(screen):
    """[(to, x, y)] from the Ways out line; None when the game said nothing about them."""
    m = _EXITS.search(screen or "")
    if not m:
        return None
    return [(to.strip(), int(x), int(y)) for to, x, y in _EXIT.findall(m.group(1))]


def stamp(text, screen):
    """The note with the place she's in in front, once."""
    w = where(screen)
    text = str(text or "").strip()
    return f"[{w[0]}] {text}" if w and text and not _STAMP.match(text) else text


def stamped(text):
    m = _STAMP.match(text or "")
    return m.group(1) if m else ""


def _names(text, place):
    words = [place] + re.findall(r"\(([^)]+)\)", place)
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text, re.IGNORECASE) for w in words if len(w) > 3)


def _about_here(text, place, now, places):
    """Whether a note is about the map she's on. Stamped: the stamp says.
    Otherwise: when it names this place (or its "(upstairs)" part); not when
    it names another known place; when it names none, only if it was just
    written here (now) - a plan counts as now."""
    at = stamped(text)
    if at:
        return at.lower() == place.lower()
    if _names(text, place):
        return True
    if any(p.lower() != place.lower() and _names(text, p) for p in places):
        return False
    return now


def problem(text, screen, now=False, places=()):
    """Why this note can't be right on the map she's on, or "" when it may be.
    Only notes that put a door, stairs or exit at a spot are checked: wrong
    when none of the spots it names is at (or a step from) a way out.
    now: just written, or her plan. places: the game's place names, so a note
    about another map is left alone."""
    w, out = where(screen), exits(screen)
    if not w or out is None or len(out) >= LISTED or not _DOORISH.search(text or ""):
        return ""
    spots = [(int(x), int(y)) for x, y in _XY.findall(_STAMP.sub("", text))]
    places = list(places) + [to for to, _x, _y in out]
    if not spots or not _about_here(text, w[0], now, places):
        return ""
    if any(abs(x - ex) + abs(y - ey) <= NEAR for x, y in spots for _to, ex, ey in out):
        return ""
    shown = "; ".join(f"to {to} at x {x}, y {y}" for to, x, y in out) or "none on this map"
    there = ", ".join(f"x {x}, y {y}" for x, y in spots)
    return f"the game shows no way out at {there} in {w[0]} - the ways out are: {shown}"
