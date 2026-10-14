"""The conversation pane and the status bar above it: wrapping the
messages into lines, scrolling back through them, the wheel.

Part of the ui package (it was one ui.py); see ui/__init__.py.
"""
from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from .shared import _events, _lock, _refresh, conversation, state, view
from .text import _width, _wrap_text


# ---------------------------------------------------------------------------
# Panel contents
# ---------------------------------------------------------------------------
def _status_lines():
    voice_server = state["voice_server"]
    offline = "offline" in voice_server
    server_style = "class:warn" if offline else "class:value"

    # Voice = how you talk to her (the recording mode); TTS = how she
    # talks back, which voice and where it's synthesized. The TTS voice
    # and its server are one fact, not two.
    # Mood rides on the Status row rather than taking one of its own.
    # Two reasons: this window is exactly five lines, so a sixth row
    # pushes Model off the bottom - and mood belongs with "what state
    # is she in", not wedged between storage and the speech server.
    status = [
        ("class:ok" if state["status"] == "Idle" else "class:value",
         state["status"]),
    ]

    if state["mood"]:
        status.append(("class:dim", " \u00b7 "))
        status.append(("class:agent", state["mood"]))

    rows = [
        ("Status", status),
        ("Voice", [("class:value", state["mode"])]),
        ("Memory", [("class:value", state["memory"])]),
        ("TTS", [
            ("class:value", state["voice"]),
            ("class:dim", " - "),
            (server_style, voice_server),
        ]),
        ("Model", [("class:value", state["model"])]),
    ]

    fragments = []

    for index, (label, parts) in enumerate(rows):
        if index:
            fragments.append(("", "\n"))

        fragments.append(("class:label", f" {label:<8}"))
        fragments.append(("class:dim", "│ "))
        fragments.extend(parts)

    return fragments


_line_cache = {"key": None, "lines": []}


def _conversation_lines():
    """The conversation as a list of rendered lines, pre-wrapped so
    continuation lines line up under the first one.

    Cached on (message count, width, last message) because it's needed
    twice per frame - once for the text, once to work out where the
    cursor goes - and re-wrapping a long history twice a frame is waste.
    """
    width = _width()

    # A copy, taken under the lock: workers insert and drop messages while
    # this runs on the UI thread, and an index checked against the live
    # list can be gone by the time it's used.
    with _lock:
        convo = list(conversation)
        streaming = view.streaming

    key = (
        len(convo), width,
        convo[-1] if convo else None,
        convo[streaming] if streaming is not None and 0 <= streaming < len(convo) else None,
    )

    if _line_cache["key"] == key:
        return _line_cache["lines"]

    lines = []

    for index, (speaker, text) in enumerate(convo):
        if speaker == "user":
            label, name_style = "You", "class:user"
        elif speaker == "system":
            label, name_style = "sys", "class:system"
        elif speaker.startswith("chat:"):
            # A stream viewer, not the person sitting here. The column
            # names the source rather than the person, because viewer
            # names are arbitrary length and this one is five wide -
            # truncating a stranger's name is worse than putting it at
            # the front of what they said, where it reads naturally
            # and can't collide.
            label, name_style = speaker[5:][:5], "class:guest"
        else:
            label, name_style = state["agent_name"][:5], "class:agent"

        # Only the name is coloured. Bodies stay in one readable colour -
        # a wall of pink is pretty for one line and tiring for twenty.
        body_style = "class:system" if speaker == "system" else "class:text"

        prefix = f" {label:<5} "
        indent = " " * (len(prefix) + 2)
        limit = max(10, width - len(prefix) - 2)

        # Wrap each line separately so explicit newlines survive - a
        # numbered list from /reminders would otherwise collapse into one
        # run-on paragraph, since _wrap_text splits on all whitespace.
        wrapped = []

        for paragraph in text.split("\n"):
            wrapped.extend(_wrap_text(paragraph, limit))

        if index:
            lines.append([("", "")])  # breathing room between turns

        lines.append([
            (name_style + " bold", prefix),
            ("class:dim", "│ "),
            (body_style, wrapped[0]),
        ])

        for line in wrapped[1:]:
            lines.append([("", indent), (body_style, line)])

    if not lines:
        lines = [[("class:dim", " Say something, or press HOME to talk.")]]

    _line_cache["key"] = key
    _line_cache["lines"] = lines

    return lines


def _conversation_fragments():
    fragments = []

    for line in _conversation_lines():
        fragments.extend(line)
        fragments.append(("", "\n"))

    return fragments


def _window_height():
    """Visible height of the conversation pane, from the last paint."""
    if view.conv_window is not None and view.conv_window.render_info is not None:
        return max(1, view.conv_window.render_info.window_height)

    return 10


def _page_size():
    """One PgUp/PgDn step: a screenful, less two lines of overlap."""
    return max(1, _window_height() - 2)


def _desired_top():
    """Which line should sit at the top of the pane.

    _scrollback is measured from the bottom, so 0 means "show the newest
    screenful" and paging just walks this backwards.
    """
    return max(0, len(_conversation_lines()) - _window_height() - view.scrollback)


def _scroll_position(window):
    return _desired_top()


# One notch of the wheel. Three lines is what terminals and editors
# have settled on; a full page per notch overshoots badly on a trackpad,
# which sends a flurry of these.
WHEEL_LINES = 3


def _scroll_by(lines):
    """Move the view. Positive is backwards in time.

    Clamped at both ends: 0 is pinned to the newest line, and the top
    stop is the oldest line that can still fill the pane. Without the
    upper clamp the wheel happily winds _scrollback into the thousands
    and then needs the same number of notches back before anything
    moves again.
    """

    view.scrollback = max(0, min(
        view.scrollback + lines,
        max(0, len(_conversation_lines()) - _window_height()),
    ))
    _refresh()


def _conversation_cursor():
    """Report the cursor on the same line we're scrolling to.

    Both halves are needed. get_vertical_scroll alone gets overridden:
    Window applies it, then runs a cursor-following pass that drags the
    view back to wherever the cursor is - line 0 by default. And the
    cursor alone isn't enough either, because that pass scrolls
    *minimally*, which makes paging lopsided (the first PgUp does
    nothing, PgDn sticks). Pointing both at the same line leaves the
    library with nothing to correct.
    """
    return Point(x=0, y=_desired_top())


class _ConversationControl(FormattedTextControl):
    """The conversation pane, with a wheel that actually scrolls it.

    Window handles wheel events on its own by nudging `vertical_scroll`
    - which does nothing here, because `get_vertical_scroll` recomputes
    that from `_scrollback` on every render and overwrites it. So the
    wheel was silently dead whenever mouse capture was on.

    Moving `_scrollback` instead puts the wheel and PgUp/PgDn on the
    same mechanism, with the same clamps, so they can't disagree about
    where the view is.
    """

    def mouse_handler(self, mouse_event):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            _events["conv_wheel"] += 1
            _scroll_by(WHEEL_LINES)
            return None

        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            _events["conv_wheel"] += 1
            _scroll_by(-WHEEL_LINES)
            return None

        _events["other_mouse"] += 1

        return super().mouse_handler(mouse_event)
