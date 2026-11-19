"""Sticky notes for her reminders, on the portrait.

When she sets a reminder (life/reminders.py add), she writes it down on a
little yellow sticky note (note_write); when it comes due, she holds the
note up beside her face so you can read it (note_show) while she says it.
The note is drawn in the portrait (portrait/viewer/props.js) with the
reminder's words on it. Not for alarms (they ring). The portrait skips it
while her hands are full or she's asleep. portrait.sticky_notes turns it off.
"""
import config

MAX_WORDS = 60            # characters on a note; longer ones are cut with "..."


def enabled():
    return bool(getattr(config, "PORTRAIT_STICKY_NOTES", True))


def _short(text):
    text = " ".join(str(text or "").split())
    return text if len(text) <= MAX_WORDS else text[:MAX_WORDS - 1].rsplit(" ", 1)[0] + "..."


def _emit(kind, **data):
    try:
        from web import livefeed

        livefeed.emit(kind, **data)
    except Exception:
        pass


def wrote(text):
    """She just set a reminder: she writes it down."""
    if enabled() and text:
        _emit("note", mode="write", text=_short(text))


def show(texts):
    """A reminder came due: she holds the note up (the first, if several)."""
    texts = [t for t in (texts or []) if t]
    if enabled() and texts:
        _emit("note", mode="show", text=_short(texts[0] + (f" (+{len(texts) - 1})" if len(texts) > 1 else "")))
