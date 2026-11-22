"""The permission popup: a tool asks (write this file, run this command),
the question floats over the conversation, Y / N / A answers it.
ask_approval() is safe from any thread and blocks until answered.

Part of the ui package (it was one ui.py); see ui/__init__.py.
"""
import itertools
import threading
import time

from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from core import logbook, safe

from .shared import _approval_lock, _lock, _refresh, state, view
from .conversation_pane import WHEEL_LINES
from .text import vwidth


# ---------------------------------------------------------------------------
# Permission popups
#
# A tool that wants to write a file calls ask_approval() from the worker
# thread and blocks. The TUI floats a box over the conversation with the
# path, what's about to happen, and the content or diff; Y or N on the
# keyboard answers it; no answer before the timeout is a no. It's the one
# place the model's turn waits on you rather than the other way round -
# and the reason it can be trusted with a write tool at all.
# ---------------------------------------------------------------------------
_numbers = itertools.count(1)    # each question's own number, for the chat page to answer by


def ask_approval(title, body, note="", timeout=300, allow_all=None):
    """Show the request and wait. Returns True only on an explicit yes.

    Safe to call from any thread. Headless (no app running) is a no:
    nothing gets written on the strength of a question nobody saw.

    allow_all, when given, is what an A answers ("all file changes this
    session"): the call then returns "all" - truthy, so it reads as a
    yes - and the caller decides what "all" switches on.
    """

    if view.app is None:
        return False

    # A timeout someone typed as "inf" or 99999999999 to mean "never" would
    # raise OverflowError from the wait, leaving the popup up for good and
    # its countdown failing on every repaint. A day is plenty of "never".
    wait = safe.seconds(timeout, 300, lo=5)

    with _approval_lock:
        answered = threading.Event()
        request = {
            "id": next(_numbers),
            "title": title,
            "note": note,
            "body": [str(line) for line in body],
            "answer": None,
            "allow_all": allow_all,
            "event": answered,
            "deadline": time.monotonic() + wait,
        }

        with _lock:
            view.approval = request
            view.approval_scroll = 0
            previous_status = state["status"]
            state["status"] = "Waiting for you"

        _refresh()

        # A ticker so the countdown in the title moves without keypresses.
        def tick():
            while not answered.is_set():
                _refresh()
                answered.wait(1.0)

        try:
            threading.Thread(target=tick, daemon=True).start()
            answered.wait(wait)
        finally:
            # Whatever happened above, the popup comes down: one left up
            # swallows every key and the input box is dead until a restart.
            answered.set()
            with _lock:
                answer = request["answer"]
                if view.approval is request:
                    view.approval = None
                state["status"] = previous_status
            _refresh()

        if answer is None:
            logbook.warn("ui", "approval timed out: %s", title)

        return "all" if answer == "all" else answer is True


def approving():
    return view.approval is not None


def _answer_approval(yes, which=None):
    """Answer the open question. which: the number it was shown with (the
    chat page), so an answer meant for one that already closed can't land on
    the next."""
    with _lock:
        request = view.approval

    if request is None or (which is not None and request.get("id") != which):
        return False

    request["answer"] = yes if yes == "all" else bool(yes)
    request["event"].set()
    return True


def pending():
    """The open question for the chat page, or None."""
    request = view.approval
    if request is None:
        return None
    return {"id": request.get("id"), "title": request["title"], "note": request["note"],
            "body": list(request["body"]), "allow_all": request.get("allow_all") or "",
            "left": safe.whole(request["deadline"] - time.monotonic(), 0, lo=0)}


def _approval_title():
    request = view.approval

    if request is None:
        return "Permission"

    # safe.whole: a deadline that isn't a finite number must not raise in
    # the middle of a repaint, which prompt_toolkit would repeat forever.
    left = safe.whole(request["deadline"] - time.monotonic(), 0, lo=0)

    if request.get("allow_all"):
        return f"Permission - Y allow, A allow {request['allow_all']}, N deny - {left}s"

    return f"Permission - Y to allow, N to deny - {left}s"


def _approval_header():
    request = view.approval

    if request is None:
        return []

    fragments = [("class:approval.title", f" {request['title']}\n")]

    if request["note"]:
        fragments.append(("class:footer", f" {request['note']}\n"))

    return fragments


def _body_width():
    """Columns the body has to fill: the window's own once it's drawn,
    else the float's width less its frame, padding and scrollbar."""
    window = view.approval_window
    if window is not None and window.render_info is not None:
        return max(20, window.render_info.window_width - 2)
    return max(20, _approval_size()[0] - 6)


def _wrap(line, width):
    """One body line as the lines it takes at this width: word-wrapped,
    the continuation indented like the line itself so code and diffs
    still read, and a word longer than the width (a URL) cut where it
    must. A line that fits is left exactly as it is."""
    if vwidth(line) <= width:
        return [line]

    indent = line[:len(line) - len(line.lstrip())]
    if vwidth(indent) > width // 2:
        indent = ""
    room = max(10, width - vwidth(indent))
    out, current = [], ""

    for word in line.split(" "):
        while vwidth(word) > room:                   # too long for any line: cut it
            if current.strip():
                out.append(current)
                current = ""
            cut = room
            while cut > 1 and vwidth(word[:cut]) > room:
                cut -= 1
            out.append(word[:cut])
            word = word[cut:]
        candidate = f"{current} {word}" if current else word
        if vwidth(candidate) > room and current.strip():
            out.append(current)
            current = word
        else:
            current = candidate
    if current or not out:
        out.append(current)

    first = out[0] if out[0].startswith(indent) else indent + out[0].lstrip(" ")
    return [first] + [indent + part.lstrip(" ") for part in out[1:]]


def _wrapped_body():
    """The body as it's drawn: [(style of its line, text)], long lines wrapped."""
    request = view.approval

    if request is None:
        return []

    width = _body_width()
    return [(line, part) for line in request["body"] for part in _wrap(line, width)]


def _approval_body():
    """The content or diff, coloured the way a diff reads, long lines
    wrapped to the window (an email's paragraph is one long line)."""
    request = view.approval

    if request is None:
        return []

    fragments = []

    for line, part in _wrapped_body():
        if line.startswith(("+++", "---")):
            style = "class:footer"
        elif line.startswith("@@"):
            style = "class:diff.hunk"
        elif line.startswith("+"):
            style = "class:diff.add"
        elif line.startswith("-"):
            style = "class:diff.del"
        else:
            style = "class:text"

        fragments.append((style, f" {part}\n"))

    return fragments or [("class:footer", " (nothing to show)\n")]


def _approval_lines():
    return len(_wrapped_body()) if view.approval else 0


def _approval_height():
    if view.approval_window is not None and view.approval_window.render_info is not None:
        return max(1, view.approval_window.render_info.window_height)

    return 10


def _approval_scroll_by(lines):

    view.approval_scroll = max(0, min(
        view.approval_scroll + lines,
        max(0, _approval_lines() - _approval_height()),
    ))
    _refresh()


def _approval_scroll_position(window):
    return view.approval_scroll


def _approval_cursor():
    return Point(x=0, y=view.approval_scroll)


class _ApprovalControl(FormattedTextControl):
    def mouse_handler(self, mouse_event):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            _approval_scroll_by(-WHEEL_LINES)
            return None

        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            _approval_scroll_by(WHEEL_LINES)
            return None

        return super().mouse_handler(mouse_event)


def _approval_size():
    """(width, height) for the float: most of the screen, not all of
    it, so it reads as a window over the conversation."""
    try:
        size = view.app.output.get_size()
        columns, rows = size.columns, size.rows
    except Exception:
        columns, rows = 100, 30

    return max(40, int(columns * 0.8)), max(10, int(rows * 0.7))
