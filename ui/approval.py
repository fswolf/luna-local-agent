"""The permission popup: a tool asks (write this file, run this command),
the question floats over the conversation, Y / N / A answers it.
ask_approval() is safe from any thread and blocks until answered.

Part of the ui package (it was one ui.py); see ui/__init__.py.
"""
import threading
import time

from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from core import logbook

from .shared import _approval_lock, _lock, _refresh, state, view
from .conversation_pane import WHEEL_LINES


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
def ask_approval(title, body, note="", timeout=120, allow_all=None):
    """Show the request and wait. Returns True only on an explicit yes.

    Safe to call from any thread. Headless (no app running) is a no:
    nothing gets written on the strength of a question nobody saw.

    allow_all, when given, is what an A answers ("all file changes this
    session"): the call then returns "all" - truthy, so it reads as a
    yes - and the caller decides what "all" switches on.
    """

    if view.app is None:
        return False

    with _approval_lock:
        answered = threading.Event()
        request = {
            "title": title,
            "note": note,
            "body": [str(line) for line in body],
            "answer": None,
            "allow_all": allow_all,
            "event": answered,
            "deadline": time.monotonic() + max(5, float(timeout)),
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

        threading.Thread(target=tick, daemon=True).start()
        answered.wait(max(5, float(timeout)))

        with _lock:
            answer = request["answer"]
            view.approval = None
            state["status"] = previous_status

        if answer is None:
            logbook.warn("ui", "approval timed out: %s", title)

        _refresh()

        return "all" if answer == "all" else answer is True


def approving():
    return view.approval is not None


def _answer_approval(yes):
    with _lock:
        request = view.approval

    if request is None:
        return

    request["answer"] = yes if yes == "all" else bool(yes)
    request["event"].set()


def _approval_title():
    request = view.approval

    if request is None:
        return "Permission"

    left = max(0, int(request["deadline"] - time.monotonic()))

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


def _approval_body():
    """The content or diff, coloured the way a diff reads."""
    request = view.approval

    if request is None:
        return []

    fragments = []

    for line in request["body"]:
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

        fragments.append((style, f" {line}\n"))

    return fragments or [("class:footer", " (nothing to show)\n")]


def _approval_lines():
    return len(view.approval["body"]) if view.approval else 0


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
