"""What the rest of Luna calls to put things on screen: messages (a
reply streams in through begin/extend/replace/end_message), the status
bar's fields, /clear. All thread-safe; all just repaint.

Part of the ui package (it was one ui.py); see ui/__init__.py.
"""
from .shared import _lock, _refresh, conversation, state, view


def set_status(status: str):
    with _lock:
        state["status"] = status
    _refresh()

    # The live monitor's stage pill follows the same status line.
    try:
        from web import livefeed

        livefeed.emit("stage", status=status)
    except Exception:
        pass


def set_voice_server(label: str):
    """Update the server shown beside the TTS voice name."""
    with _lock:
        if state["voice_server"] == label:
            return
        state["voice_server"] = label
    _refresh()


def set_mode(mode: str):
    """Recording mode - shown on the Voice row."""
    with _lock:
        if state["mode"] == mode:
            return
        state["mode"] = mode
    _refresh()


def set_controls(text: str):
    """A note shown at the bottom of the launcher pane (Tab).

    Was the footer line; the footer is gone, but the keyboard listener
    still uses this to report when no global hotkey is available.
    """
    with _lock:
        if state["controls"] == text:
            return
        state["controls"] = text
    _refresh()


def add_message(speaker: str, text: str):
    """Add a finished message.

    If a streamed reply is open, this goes *above* it rather than at
    the end. Tool logs arrive while she's mid-sentence, and they
    describe something that already happened, so they belong before
    her answer - and putting them after would leave the open message
    no longer last, which is what extend_message relies on.
    """

    with _lock:
        if view.streaming is not None and 0 <= view.streaming < len(conversation):
            conversation.insert(view.streaming, (speaker, text))
            view.streaming += 1
        else:
            conversation.append((speaker, text))

        view.scrollback = 0  # a new message pulls you back to the bottom
    _refresh()


def begin_message(speaker: str):
    """Open an empty message for extend_message() to fill in."""

    with _lock:
        conversation.append((speaker, ""))
        view.streaming = len(conversation) - 1
        view.scrollback = 0
    _refresh()


def extend_message(text: str):
    """Append to the open message as tokens arrive."""

    if not text:
        return

    with _lock:
        if view.streaming is None or not 0 <= view.streaming < len(conversation):
            return

        speaker, existing = conversation[view.streaming]
        conversation[view.streaming] = (speaker, existing + text)
        view.scrollback = 0
    _refresh()


def replace_message(text: str):
    """Swap the streamed text for the final cleaned-up version.

    Worth doing even though they're usually identical: the streamed
    text is raw, and the final one has had stray timestamps and
    leftover think-tags stripped out of it.
    """

    with _lock:
        if view.streaming is None or not 0 <= view.streaming < len(conversation):
            return

        speaker, existing = conversation[view.streaming]

        if existing == text:
            return

        conversation[view.streaming] = (speaker, text)
        view.scrollback = 0
    _refresh()


def end_message():
    """Close the open message, dropping it if nothing arrived in it."""

    with _lock:
        index, view.streaming = view.streaming, None

        if index is None or not 0 <= index < len(conversation):
            return

        if not conversation[index][1].strip():
            conversation.pop(index)
    _refresh()


# Older name, kept so nothing breaks if it's still called somewhere.
drop_empty_message = end_message


def clear():
    """/clear: an empty conversation, and no open message pointing into it."""

    with _lock:
        conversation.clear()
        view.streaming = None
        view.scrollback = 0
    _refresh()


def mouse_enabled():
    return view.mouse


def toggle_mouse(on=None):
    """Swap between wheel scrolling and being able to select text."""

    view.mouse = (not view.mouse) if on is None else bool(on)
    _refresh()

    return view.mouse


def set_voice(name: str):
    """Update the Voice row. /voice can change this mid-session, and a
    header still showing the old name is worse than no header."""
    with _lock:
        state["voice"] = name
    _refresh()


def set_model(label: str):
    """Update the Model row - it now shows health, not just a name."""
    with _lock:
        state["model"] = label
    _refresh()


def set_mood(text: str):
    """The Mood row. Empty hides the row entirely, so turning moods off
    doesn't leave a blank line behind."""
    with _lock:
        if state["mood"] == text:
            return
        state["mood"] = text
    _refresh()


def set_memory(text: str):
    """The Memory row: which backend, how many facts. longterm.status()
    writes it whenever the table changes, so it's never a stale label."""
    with _lock:
        if state["memory"] == text:
            return
        state["memory"] = text
    _refresh()


def init(agent_name, model, voice, memory_status="Loaded", voice_server="unknown"):
    with _lock:
        state["agent_name"] = agent_name
        state["model"] = model
        state["voice"] = voice
        state["voice_server"] = voice_server
        state["memory"] = memory_status
    _refresh()


def render():
    """Kept so older call sites don't break - repainting is automatic."""
    _refresh()
