"""What she's wearing on her portrait, as the page reports it, and how the
conversation changes it.

The portrait does the dressing and undressing (portrait/viewer/outfits.js,
clothes_talk.js): /outfit, a plain request from you, her own *slips her
top off*, or a clothes tag she writes. After every change the page posts
what's on and off to /portrait/outfit, so this side remembers it: for
/outfit with nothing after it, for one situation line (so she knows what
she has on), and for the tags she's offered.

portrait.clothes picks how the conversation changes her clothes, the way
portrait.gestures does for moves:

  gestures  whatever portrait.gestures is: tags gets tags, meaning and
            keywords get keywords, off gets off (the default)
  tags      she picks: [top_off], [undress], [dress]... offered beside the
            gesture tags, only the ones that fit what she has on now, cut
            out before anything is shown or spoken. Keywords as a fallback.
  keywords  only your plain words ("take off your top") and her written
            actions (*slips her top off*), read on the page
  off       nothing from the conversation; /outfit and the pose studio only

Only a model whose clothes are separate pieces reports anything; the robot
has none, and fully dressed is the normal state, so neither puts a line in
her prompt.
"""
import re
import threading
import time

import config

_lock = threading.Lock()
_state = {"wearing": "", "off": [], "pieces": [], "at": 0.0}

WEARING = ("dressed", "underwear", "partly", "none")
MODES = ("gestures", "tags", "keywords", "off")
_LABEL = re.compile(r"^[a-z][a-z0-9 _-]{0,23}$")
# tags she's offered at most, so clothes never crowd out the gestures
TAGS_OFFERED = 4


def _labels(items):
    out = [str(x).strip().lower() for x in (items or [])][:12]
    return [x for x in out if _LABEL.match(x)]


def note(wearing, off=(), pieces=None):
    """The page's report. wearing: dressed, underwear, partly, or none (a
    model without separate clothes). off: the labels of the pieces off.
    pieces: every piece's label (older pages don't send it)."""
    wearing = str(wearing or "").strip().lower()
    if wearing not in WEARING:
        return False
    off = _labels(off)[:8]
    allp = _labels(pieces) if pieces is not None else list(dict.fromkeys(off))
    with _lock:
        _state.update(wearing=wearing, off=off, pieces=allp, at=time.time())
    return True


def current():
    """{'wearing', 'off', 'pieces', 'at'}; wearing is '' before any report."""
    with _lock:
        return dict(_state, off=list(_state["off"]), pieces=list(_state["pieces"]))


def _open():
    """A report only counts while a page is listening: closed, it's stale."""
    try:
        from web import livefeed

        return livefeed.watching()
    except Exception:
        return False


def describe():
    """Her situation line, or "" when there's nothing to say (dressed, a model
    without separate clothes, or no portrait open)."""
    s = current()
    if not _open():
        return ""
    if s["wearing"] == "underwear":
        return "Wearing: just your underwear, your clothes are off"
    if s["wearing"] == "partly" and s["off"]:
        return "Wearing: your clothes, without your " + _join(s["off"])
    return ""


def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# -- how the conversation changes them -----------------------------------
def mode():
    """tags, keywords or off: portrait.clothes, with "gestures" resolved."""
    m = str(getattr(config, "PORTRAIT_CLOTHES", "gestures") or "gestures").lower()
    if m not in MODES:
        m = "gestures"
    if m == "gestures":
        from life import gestures

        m = {"tags": "tags", "off": "off"}.get(gestures.mode(), "keywords")
    return m


def _slug(label):
    return re.sub(r"[^a-z0-9]+", "_", label).strip("_")


def tag_names():
    """Every clothes tag that means something for the pieces she has, so
    one is cut from her reply even if it wasn't offered this turn."""
    s = current()
    names = ["dress", "undress"]
    for p in s["pieces"] or ["top", "tie", "bottoms", "shoes", "socks"]:
        names += [_slug(p) + "_off", _slug(p) + "_on"]
    return names


def offered(private=True):
    """The clothes tags that fit right now, at most TAGS_OFFERED: off for
    what she has on, on for what's off. Taking things off only in a private
    turn and never in tame mode (the page checks again)."""
    if mode() != "tags" or not _open():
        return []
    s = current()
    if s["wearing"] not in ("dressed", "partly", "underwear") or not s["pieces"]:
        return []
    try:
        from mind import mood

        tame = bool(mood.tame())
    except Exception:
        tame = False
    off = set(s["off"]) if s["wearing"] == "partly" else set(s["pieces"]) if s["wearing"] == "underwear" else set()
    out = []
    if off:
        out.append("dress")
    if private and not tame:
        if s["wearing"] != "underwear":
            out.append("undress")
        out += [_slug(p) + "_off" for p in s["pieces"] if p not in off]
    out += [_slug(p) + "_on" for p in s["pieces"] if p in off]
    return out[:TAGS_OFFERED]


def from_tag(name):
    """A clothes tag she wrote -> the page (who: her). False if it isn't one."""
    name = name.lower()
    if name not in tag_names() or mode() == "off":
        return False
    if name in ("dress", "undress"):
        ev = {"wear": "dressed" if name == "dress" else "underwear"}
    else:
        slug, way = name.rsplit("_", 1)
        label = next((p for p in current()["pieces"] if _slug(p) == slug), slug.replace("_", " "))
        ev = {way: [label]}
    try:
        from web import livefeed

        livefeed.emit("outfit", src="tag", **ev)
    except Exception:
        pass
    return True
