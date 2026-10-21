"""What every part of the TUI shares: the conversation, the status bar's
fields, and where the view is (scroll positions, which pane is up, the
pending approval). One place, so a module that moves the view doesn't
need `global` and every other module sees the same thing.

Written by worker threads (a reply streaming in, a tool's approval) and
read by the UI thread as it paints: writers hold `_lock`, and a painter
that indexes into the conversation copies it under the lock first.
"""
import threading
from types import SimpleNamespace

try:
    from wcwidth import wcswidth
except ImportError:  # pragma: no cover - fallback if wcwidth isn't installed
    wcswidth = None

_lock = threading.Lock()

# The status bar (mutated by assistant/keyboard threads, read on render).
state = {
    "agent_name": "Luna",
    "model": "unknown",
    "voice": "af_bella",
    "voice_server": "unknown",
    "status": "Idle",
    "memory": "Loaded",
    "mood": "",
    "controls": "",
    "mode": "auto",
}
conversation = []  # list of (speaker, text) tuples

# Which overlay can be up: None, "help", "tools" or "settings". Tab
# cycles through them and back to the conversation.
_panes = (None, "help", "tools", "settings")

view = SimpleNamespace(
    app=None,             # the running prompt_toolkit Application, or None (headless)
    on_submit=None,       # what Enter calls
    on_hotkey=None,       # what HOME calls
    conv_window=None,
    scrollback=0,         # lines scrolled up from the bottom; 0 = pinned to latest
    pane=None,            # the overlay that's up: None, "help" or "tools"
    help_scroll=0,        # lines scrolled down from the top of the help text
    help_window=None,
    tool_cursor=0,        # selected row in the tools pane
    tool_scroll=0,
    tool_window=None,
    set_cursor=0,         # the settings pane (ui/settings_pane.py)
    set_scroll=0,
    set_window=None,
    set_filter="",        # only settings matching this, "" for all
    set_all=False,        # every setting, not just the everyday ones (config.schema.BASIC)
    set_editing=None,     # the edit box: {"mode": "value"|"filter", "path", "text"}
    set_status="",        # the last change, in the pane's header
    set_editor=None,      # the edit box's TextArea, and the main input box
    input_area=None,
    approval=None,        # the pending permission request, or None
    approval_scroll=0,
    approval_window=None,
    # The open message extend_message() fills, by index. A streamed reply
    # is one message that grows while other messages may arrive around it.
    # Its position is tracked explicitly rather than assumed to be last,
    # because a tool call logs a system message in the middle of her
    # sentence - and appending to conversation[-1] then put her whole
    # reply inside the system row, labelled "sys".
    streaming=None,
    # Mouse capture is off by default, and that is a deliberate trade.
    # prompt_toolkit's mouse support gives you wheel scrolling, but it
    # turns on terminal mouse reporting - which means the terminal hands
    # drags to the application instead of doing its own text selection.
    # You lose copy and paste entirely, which matters far more in a window
    # full of log lines and error messages than scrolling does, especially
    # when PgUp/PgDn/End already scroll.
    mouse=False,
)

_approval_lock = threading.Lock()  # one question at a time

# Counters for /scroll, so "the wheel doesn't work" can be split into
# "the terminal never sent it" and "it arrived and nothing moved".
_events = {"conv_wheel": 0, "help_wheel": 0, "other_mouse": 0,
           "page_keys": 0, "arrow_keys": 0}


def _refresh():
    """Repaint. Safe from any thread; a no-op before the app runs."""
    if view.app is not None:
        try:
            view.app.invalidate()
        except Exception:
            pass  # app not running yet, or already torn down
