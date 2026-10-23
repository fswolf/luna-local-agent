"""She reads a book while you're quiet.

When nobody has talked to her for portrait.reading.after minutes (10 by
default) and her portrait is open, she brings up an open book (the portrait
gets a "prop" event and plays book_open_pickup; the book is
portrait/props/book_open.glb). Every minute or so she turns a page
(book_read_turn) or looks up at you over it (book_read_lookup). The moment
a turn happens - you talk or type to her, or presence sees you come back
after being away - she looks up and puts the book down. After
portrait.reading.minutes she puts it down on her own, and waits for the
next quiet stretch.

Not while she's in the lewd or grudge row or has walked away, and not while
she's having her coffee (coffee.py waits for the book the same way). /read
starts it by hand.
"""
import random
import threading
import time

import config
import logbook

PAGE_EVERY = (35, 80)         # seconds between page turns and glances
LOOKUP_SHARE = 0.3            # of those, how many are a look up at you
PUT_DOWN_AFTER = 2.6          # seconds: she looks up, then the book goes down

_state = {"on": False, "since": 0.0, "next": 0.0, "by_hand": False, "quiet_from": None,
          "spent": None, "away": False, "ended": None, "thread": None}

# What she's reading, so she can talk about it (situation.py puts it in her
# prompt). It's the book on the portrait: portrait/props/book_open.glb, its
# pages drawn by portrait/source/props/book/pages.py - change the story
# there and here together.
BOOK = {"title": "The Moonlit Library", "author": "E. V. Hollow", "chapter": "Chapter Seven, The Cat Who Kept the Lamps",
        "pages": "112-113", "short": "chapter seven, about Ink the library cat",
        "story": ("a small black cat named Ink lights the library's lamps every night so the books won't dream "
                  "of being forgotten; tonight one lamp won't light, beside a lonely little blue book who asks Ink "
                  "to leave it dark because it's the only time anyone sits with it - so Ink curls up and stays, "
                  "and the book reads Ink a poem about the moon")}
RECENT = 15 * 60              # seconds she still remembers she was reading
_lock = threading.Lock()


def enabled():
    return bool(getattr(config, "PORTRAIT_READING", True))


def holding():
    return _state["on"]


def _idle():
    try:
        import reflect

        return reflect.idle_seconds()
    except Exception:
        return 0.0


def _present():
    """True / False from presence, or None when presence isn't running."""
    try:
        import presence

        return presence.present() if presence.running() else None
    except Exception:
        return None


def _watching():
    try:
        import livefeed

        return livefeed.watching()
    except Exception:
        return False


def _busy():
    try:
        import assistant

        return assistant.busy()
    except Exception:
        return False


def _walked_away():
    try:
        import mood

        return bool(mood.away())
    except Exception:
        return False


def _not_now():
    """Her mood says no: the lewd or grudge row, or she's walked away."""
    try:
        import mood

        return mood.away() or mood._row_of(mood.label()) in ("lewd", "grudge")
    except Exception:
        return False


def _coffee():
    try:
        import coffee

        return coffee.holding()
    except Exception:
        return False


def _emit(kind, **data):
    try:
        import livefeed

        livefeed.emit(kind, **data)
    except Exception:
        pass


def begin(now=None, by_hand=True):
    """Bring up the book (/read; the routine passes by_hand=False). False if she's already reading."""
    now = time.monotonic() if now is None else now
    with _lock:
        if _state["on"]:
            return False
    if _coffee():                                      # /read with her coffee in hand: the mug goes down first
        import coffee

        coffee.finish()
    with _lock:
        _state.update(on=True, since=now, by_hand=by_hand, next=now + random.uniform(*PAGE_EVERY),
                      away=_present() is False, quiet_from=now - _idle())
    _emit("prop", name="book_open", on=True)
    logbook.info("reading", "she picked up her book")
    return True


def finish(look_up=True):
    """Put the book down: a look up first (she noticed you), then down."""
    with _lock:
        if not _state["on"]:
            return False
        _state["on"] = False
        _state["spent"] = _state["quiet_from"]        # this quiet stretch is used up
        _state["ended"], _state["back"] = time.monotonic(), look_up
    if look_up:
        _emit("gesture", name="book_read_lookup", src="reading")
        # (unless she's picked it up again meanwhile: /read straight after)
        threading.Timer(PUT_DOWN_AFTER, lambda: _state["on"] or _emit("prop", name="book_open", on=False)).start()
    else:
        _emit("prop", name="book_open", on=False)
    logbook.info("reading", "she put her book down")
    return True


def page(lookup=None):
    """One page turn, or a glance up at you (lookup=True)."""
    if not _state["on"]:
        return False
    if lookup is None:
        lookup = random.random() < LOOKUP_SHARE
    _emit("gesture", name="book_read_lookup" if lookup else "book_read_turn", src="reading")
    return True


def describe(now=None):
    """A line for her prompt (situation.py): what she's reading, or was, or ""."""
    now = time.monotonic() if now is None else now
    b = BOOK
    book = f"{b['title']} by {b['author']}, {b['chapter']} (pages {b['pages']}): {b['story']}"
    if _state["on"]:
        mins = int((now - _state["since"]) // 60)
        long = f"for {mins} minutes" if mins >= 2 else "for a moment"
        return (f"In your hands: a book you've been reading {long}, {book}. He just spoke to you, so you're "
                "looking up from it and putting it down - mention it only if it fits")
    if _state["ended"] is not None and now - _state["ended"] < RECENT:
        why = "when he came back" if _state.get("back") else "a little while ago"
        return f"A few minutes ago you were reading {b['title']} ({b['short']}); you put it down {why}"
    return ""


def tick(now=None):
    """One look around; the loop calls this every few seconds."""
    now = time.monotonic() if now is None else now
    idle = _idle()

    if _state["on"]:
        here = _present()
        back = idle < now - _state["since"]                   # a turn since she started
        if here and _state["away"]:
            back = True                                       # presence: you walked back in
        _state["away"] = _state["away"] or here is False
        minutes = float(getattr(config, "PORTRAIT_READING_MINUTES", 60))
        if back:
            finish(look_up=True)
        elif (now - _state["since"] >= minutes * 60 or _walked_away()           # walked off: always down
              or (_not_now() and not _state["by_hand"])):
            finish(look_up=False)
        elif now >= _state["next"] and not _busy():
            page()
            _state["next"] = now + random.uniform(*PAGE_EVERY)
        return

    after = float(getattr(config, "PORTRAIT_READING_AFTER", 10)) * 60
    quiet_from = now - idle
    fresh = _state["spent"] is None or quiet_from > _state["spent"] + 1   # not the stretch she already read through
    if (enabled() and idle >= after and fresh and _watching() and not _busy() and not _not_now()
            and not _coffee()):
        begin(now, by_hand=False)


def _loop():
    while True:
        try:
            tick()
        except Exception as e:
            logbook.warn("reading", "tick failed: %s", e)
        time.sleep(2 if _state["on"] else 10)        # reading: notice you quickly, before her reply's gestures


def start():
    if _state["thread"] is None:
        # a restart forgets a book in progress: an open portrait puts it away
        _emit("prop", name="book_open", on=False)
        _state["thread"] = threading.Thread(target=_loop, daemon=True, name="reading")
        _state["thread"].start()
