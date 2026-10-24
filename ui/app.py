"""The application itself: the style, the keys, laying the panes out, and
run() / stop(). run() owns the main thread until she quits.

Part of the ui package (it was one ui.py); see ui/__init__.py.
"""
import os
import sys

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import (
    ConditionalContainer, Float, FloatContainer, HSplit, Layout, Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from config import THEME

from .shared import _events, _panes, _refresh, state, view
from .approval import (
    _ApprovalControl, _answer_approval, _approval_body, _approval_cursor, _approval_header,
    _approval_height, _approval_scroll_by, _approval_scroll_position, _approval_size,
    _approval_title, approving,
)
from .conversation_pane import (
    _ConversationControl, _conversation_cursor, _conversation_fragments, _conversation_lines,
    _page_size, _scroll_by, _scroll_position, _status_lines, _window_height,
)
from .help import (
    _HelpControl, _help_cursor, _help_fragments, _help_height, _help_line_count,
    _help_scroll_by, _help_scroll_position,
)
from .messages import add_message, toggle_mouse
from .text import _HORIZONTAL, _framed, _keyed, _rule
from . import settings_pane
from .tools_pane import (
    _ToolControl, _tool_cursor_point, _tool_fragments, _tool_group_toggle, _tool_header,
    _routing_toggle, _tool_height, _tool_move, _tool_scroll_position, _tool_toggle,
)


def scroll_report():
    """Everything /scroll needs to say where the wheel is getting lost."""
    import os
    import prompt_toolkit

    conv_lines = len(_conversation_lines())

    return (
        f"prompt_toolkit {prompt_toolkit.__version__} | TERM={os.environ.get('TERM', '?')} "
        f"| mouse capture: {'ON' if view.mouse else 'OFF (F2)'}\n"
        f"conversation: {conv_lines} lines, pane {_window_height()} tall, "
        f"scrollback {view.scrollback} (max {max(0, conv_lines - _window_height())})\n"
        f"help: {_help_line_count()} lines, pane {_help_height()} tall, "
        f"scroll {view.help_scroll}, pane={view.pane}\n"
        f"events since start: conversation wheel {_events['conv_wheel']}, "
        f"help wheel {_events['help_wheel']}, other mouse {_events['other_mouse']}, "
        f"PgUp/PgDn {_events['page_keys']}, arrows {_events['arrow_keys']}"
    )


# ---------------------------------------------------------------------------
# The tools pane (Tab, twice)
#
# Every tool schema sits in the context window on every single turn,
# whether or not it is ever called - a few hundred tokens each, a few
# thousand in total. That is invisible until the day a request stops
# fitting, which is a bad day to find out. So this lists them with what
# they cost, lets you switch the situational ones off, and shows the
# total moving as you do it.
#
# Off is not the same as unavailable: a tool with no `grim` installed
# says so and can't be switched on, because the switch wouldn't be the
# thing standing in the way.
# ---------------------------------------------------------------------------
def _next_pane():
    return _panes[(_panes.index(view.pane) + 1) % len(_panes)]


# What the next Tab will do, on the input frame. Tab used to open one
# thing, so a fixed "tab for help" was honest; now it cycles, and a
# label that names the next stop beats making you remember the ring.
_TAB_HINT = {None: "tab for help", "help": "tab for tools",
             "tools": "tab for settings", "settings": "tab to close"}


def _tab_hint():
    return _TAB_HINT.get(view.pane, "tab for help")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
def _build_style():
    return Style.from_dict({
        "frame.border": THEME["border"],
        "frame.label": f"{THEME['title']} bold",
        "label": THEME["label"],
        "text": THEME["text"],
        "value": THEME["value"],
        "agent": THEME["agent"],
        "user": THEME["user"],
        # Viewers get the link colour rather than the user colour: at a
        # glance it should be obvious which lines came from the room
        # and which came from you.
        "guest": f"{THEME['link']} bold",
        "system": THEME["system"],
        "ok": THEME["ok"],
        "warn": f"{THEME['warn']} bold",
        "footer": THEME["footer"],
        "key": f"{THEME['accent']} bold",
        "dim": THEME["dim"],
        "prompt": f"{THEME['prompt']} bold",
        "link": f"{THEME['link']} underline",
        # The help scrollbar: track in the theme's dim, thumb in the
        # border purple, so it reads as part of the frame.
        "scrollbar.background": f"bg:{THEME['dim']}",
        "scrollbar.button": f"bg:{THEME['border']}",
        # The permission popup: title in the warning colour so it can't
        # be mistaken for a chat message, diff lines the way diffs read.
        "approval.title": f"{THEME['warn']} bold",
        "diff.add": THEME["ok"],
        "diff.del": THEME["warn"],
        "diff.hunk": THEME["dim"],
    })


def _build_keys():
    keys = KeyBindings()

    @keys.add("home")
    def _(event):
        # Push-to-talk. Overrides "cursor to start of line" in the input
        # box, which is what we want - Ctrl+A still does that.
        if view.on_hotkey:
            view.on_hotkey()

    @keys.add("f2")
    def _(event):
        # Mouse capture on means the wheel scrolls; off means the
        # terminal can select text again. You can't have both, because
        # the terminal hands drags to whoever asked for them.
        on = toggle_mouse()
        add_message(
            "system",
            "Mouse capture on - the wheel scrolls the conversation. Most "
            "terminals still let you select with Shift held down. F2 "
            "again to swap back."
            if on else
            "Mouse capture off - select and copy normally. PgUp/PgDn "
            "scroll; F2 to get the wheel back.",
        )

    # While a permission popup is up, the keyboard belongs to it. Y/N
    # (and Enter/Esc) answer; the scroll keys scroll it; everything else
    # is swallowed so a half-typed message can't leak into the input
    # box while you're reading a diff. Exact keys beat Keys.Any in
    # prompt_toolkit, so the swallow doesn't eat the answers.
    asking = Condition(approving)

    @keys.add("y", filter=asking)
    @keys.add("Y", filter=asking)
    @keys.add("enter", filter=asking)
    def _(event):
        _answer_approval(True)

    @keys.add("n", filter=asking)
    @keys.add("N", filter=asking)
    def _(event):
        _answer_approval(False)

    # Only on a popup that offers it; anywhere else A is swallowed below.
    offers_all = Condition(lambda: bool(view.approval and view.approval.get("allow_all")))

    @keys.add("a", filter=asking & offers_all)
    @keys.add("A", filter=asking & offers_all)
    def _(event):
        _answer_approval("all")

    @keys.add(Keys.Any, filter=asking)
    def _(event):
        pass

    # The settings pane: space flips or steps, enter edits, / filters,
    # x goes back to the default. Not while its edit box is open: then
    # the keys are the box's.
    in_settings = Condition(lambda: view.pane == "settings" and not approving()
                            and view.set_editing is None)

    def _open_editor(event):
        if view.set_editing is not None and view.set_editor is not None:
            view.set_editor.text = view.set_editing.get("text", "")
            view.set_editor.buffer.cursor_position = len(view.set_editor.text)
            event.app.layout.focus(view.set_editor)

    @keys.add(" ", filter=in_settings)
    def _(event):
        settings_pane.flip()
        _open_editor(event)

    @keys.add("enter", filter=in_settings)
    def _(event):
        settings_pane.edit()
        _open_editor(event)

    @keys.add("/", filter=in_settings)
    def _(event):
        settings_pane.start_filter()
        _open_editor(event)

    @keys.add("x", filter=in_settings)
    def _(event):
        settings_pane.reset()

    @keys.add("a", filter=in_settings)
    def _(event):
        settings_pane.toggle_all()

    @keys.add(" ", filter=Condition(lambda: view.pane == "tools" and not approving()))
    def _(event):
        _tool_toggle()

    @keys.add("a", filter=Condition(lambda: view.pane == "tools" and not approving()))
    def _(event):
        _tool_group_toggle()

    @keys.add("r", filter=Condition(lambda: view.pane == "tools" and not approving()))
    def _(event):
        _routing_toggle()

    @keys.add("tab")
    def _(event):

        if approving() or view.set_editing is not None:
            return

        view.pane = _next_pane()

        if view.pane == "help":
            view.help_scroll = 0  # always open at the top

        _refresh()

    @keys.add("escape", eager=True)
    def _(event):
        # Esc answers a permission popup with no, closes the help window
        # if it's open, quits otherwise - same as sfav's notes popup.

        if approving():
            _answer_approval(False)
            return

        if view.set_editing is not None:
            settings_pane.cancel_edit()
            event.app.layout.focus(view.input_area)
            return

        if view.pane == "settings" and settings_pane.clear_filter():
            return

        if view.pane is not None:
            view.pane = None
            _refresh()
            return

        event.app.exit()

    @keys.add("c-c")
    @keys.add("c-q")
    def _(event):
        event.app.exit()

    @keys.add("pageup")
    def _(event):
        # A page, not a few lines: the view only moves once the cursor
        # leaves the viewport, so nudging it 5 lines looks like nothing
        # happened. The keys drive whichever pane is showing.
        _events["page_keys"] += 1

        if approving():
            _approval_scroll_by(-max(1, _approval_height() - 2))
        elif view.set_editing is not None:
            pass
        elif view.pane == "settings":
            settings_pane.move(-max(1, settings_pane._height() - 2))
        elif view.pane == "tools":
            _tool_move(-max(1, _tool_height() - 3))
        elif view.pane == "help":
            _help_scroll_by(-max(1, _help_height() - 2))
        else:
            _scroll_by(_page_size())

    @keys.add("pagedown")
    def _(event):
        _events["page_keys"] += 1

        if approving():
            _approval_scroll_by(max(1, _approval_height() - 2))
        elif view.set_editing is not None:
            pass
        elif view.pane == "settings":
            settings_pane.move(max(1, settings_pane._height() - 2))
        elif view.pane == "tools":
            _tool_move(max(1, _tool_height() - 3))
        elif view.pane == "help":
            _help_scroll_by(max(1, _help_height() - 2))
        else:
            _scroll_by(-_page_size())

    # With mouse capture off, terminals don't drop wheel events on the
    # floor - in a full-screen app they translate each notch into a few
    # Up/Down arrow presses ("alternate scroll" mode). Those landed in
    # the input box, which read them as "recall the last thing I typed".
    # Routing the arrows to the visible pane means the wheel scrolls
    # with capture OFF as well as on, which is the better default: you
    # keep text selection and get the wheel for free. One line per key
    # because a notch is already several keys.
    @keys.add("up")
    def _(event):
        _events["arrow_keys"] += 1

        if approving():
            _approval_scroll_by(-1)
        elif view.set_editing is not None:
            pass
        elif view.pane == "settings":
            settings_pane.move(-1)
        elif view.pane == "tools":
            _tool_move(-1)
        elif view.pane == "help":
            _help_scroll_by(-1)
        else:
            _scroll_by(1)

    @keys.add("down")
    def _(event):
        _events["arrow_keys"] += 1

        if approving():
            _approval_scroll_by(1)
        elif view.set_editing is not None:
            pass
        elif view.pane == "settings":
            settings_pane.move(1)
        elif view.pane == "tools":
            _tool_move(1)
        elif view.pane == "help":
            _help_scroll_by(1)
        else:
            _scroll_by(-1)

    @keys.add("end")
    def _(event):
        # Back to the resting position of whichever pane is showing:
        # the top of the help, the newest line of the conversation.

        if view.pane == "help":
            view.help_scroll = 0
        else:
            view.scrollback = 0

        _refresh()

    return keys


def run(on_submit, on_hotkey=None):
    """Build and run the TUI. Blocks until the user quits.

    on_submit(text) is called on the UI thread - it must not block, so
    anything slow belongs on a worker thread.
    """

    view.on_submit = on_submit
    view.on_hotkey = on_hotkey

    def accept(buffer):
        text = buffer.text.strip()

        if text and view.on_submit:
            view.on_submit(text)

        return False  # clear the input box

    input_area = TextArea(
        height=1,
        prompt=[("class:prompt", "> ")],
        multiline=False,
        wrap_lines=False,
        accept_handler=accept,
    )

    # The explicit Dimension matters: without it, Window asks the control
    # how tall it wants to be, FormattedTextControl answers "as tall as
    # the whole conversation", and the frame shoves the header off the
    # top of the screen and the input box off the bottom. Giving it a
    # weight instead makes it take the leftover space and scroll.
    conversation_window = Window(
        content=_ConversationControl(
            _conversation_fragments,
            get_cursor_position=_conversation_cursor,
        ),
        height=Dimension(min=3, weight=1),
        wrap_lines=False,
        get_vertical_scroll=_scroll_position,
        always_hide_cursor=True,
    )

    view.conv_window = conversation_window

    # Same shape as the conversation window, plus a scrollbar - the help
    # outgrew one screen the day alarms landed, and a pane that cuts off
    # silently reads as "that's all there is".
    help_window = Window(
        content=_HelpControl(
            _help_fragments,
            get_cursor_position=_help_cursor,
        ),
        height=Dimension(min=3, weight=1),
        wrap_lines=False,
        get_vertical_scroll=_help_scroll_position,
        always_hide_cursor=True,
        right_margins=[ScrollbarMargin()],
    )

    view.help_window = help_window

    tools_list = Window(
        content=_ToolControl(
            _tool_fragments,
            get_cursor_position=_tool_cursor_point,
        ),
        height=Dimension(min=3, weight=1),
        wrap_lines=False,
        get_vertical_scroll=_tool_scroll_position,
        always_hide_cursor=True,
        right_margins=[ScrollbarMargin()],
    )

    view.tool_window = tools_list

    settings_list = Window(
        content=settings_pane.SettingsControl(
            settings_pane._fragments,
            get_cursor_position=settings_pane._cursor_point,
        ),
        height=Dimension(min=3, weight=1),
        wrap_lines=False,
        get_vertical_scroll=settings_pane._scroll_position,
        always_hide_cursor=True,
        right_margins=[ScrollbarMargin()],
    )

    view.set_window = settings_list

    settings_window = HSplit([
        Window(
            content=FormattedTextControl(settings_pane._header),
            height=Dimension.exact(2),
        ),
        _rule(_HORIZONTAL),
        settings_list,
    ])

    # The settings pane's edit box: one line, over the pane. Enter saves
    # (or keeps the filter), Esc cancels; the filter narrows as you type.
    def _edited(buffer):
        settings_pane.finish_edit(buffer.text)
        view.app.layout.focus(input_area)
        return False

    editor = TextArea(height=1, multiline=False, wrap_lines=False,
                      prompt=[("class:prompt", "> ")], accept_handler=_edited)

    def _typing(_buffer):
        if (view.set_editing or {}).get("mode") == "filter":
            view.set_filter = editor.text.strip()
            view.set_cursor = view.set_scroll = 0

    editor.buffer.on_text_changed += _typing
    view.set_editor = editor
    view.input_area = input_area

    editor_box = ConditionalContainer(
        _framed(
            HSplit([
                Window(content=FormattedTextControl(lambda: [("class:dim", " " + settings_pane.editor_help())]),
                       height=1),
                editor,
            ]),
            title=settings_pane.editor_title,
        ),
        filter=Condition(lambda: view.set_editing is not None),
    )

    tools_window = HSplit([
        Window(
            content=FormattedTextControl(_tool_header),
            height=Dimension.exact(2),
        ),
        _rule(_HORIZONTAL),
        tools_list,
    ])

    # Help replaces the conversation panel rather than floating over it.
    # A float has to be full width anyway - a 2-cell emoji whose first
    # half falls outside the float still gets drawn in full and shunts
    # the border a column right, and Luna uses emoji constantly - and a
    # full-width float left the conversation's leftover rows and bottom
    # border poking out underneath. Swapping is exact and artifact-free.
    showing_help = Condition(lambda: view.pane == "help")

    body = HSplit([
        _framed(
            Window(
                content=FormattedTextControl(_status_lines),
                height=Dimension.exact(5),
            ),
            title=lambda: f"{state['agent_name']} AI Assistant",
        ),
        ConditionalContainer(
            _framed(conversation_window, title="Conversation"),
            filter=Condition(lambda: view.pane is None),
        ),
        ConditionalContainer(
            _framed(help_window, title="Help"),
            filter=showing_help,
        ),
        ConditionalContainer(
            _framed(tools_window, title="Tools"),
            filter=Condition(lambda: view.pane == "tools"),
        ),
        ConditionalContainer(
            _framed(settings_window, title="Settings"),
            filter=Condition(lambda: view.pane == "settings"),
        ),
        _framed(input_area, title=_tab_hint),
    ])

    # The permission popup floats over everything, centred, most of the
    # screen but not all of it. Its body scrolls the same way the other
    # panes do.
    approval_body = Window(
        content=_ApprovalControl(
            _approval_body,
            get_cursor_position=_approval_cursor,
        ),
        wrap_lines=False,
        get_vertical_scroll=_approval_scroll_position,
        always_hide_cursor=True,
        right_margins=[ScrollbarMargin()],
    )
    view.approval_window = approval_body

    approval_box = ConditionalContainer(
        _framed(
            HSplit([
                Window(
                    content=FormattedTextControl(_approval_header),
                    height=Dimension(min=1, max=3),
                    dont_extend_height=True,
                ),
                _rule(_HORIZONTAL),
                approval_body,
                _rule(_HORIZONTAL),
                Window(
                    content=FormattedTextControl(lambda: _keyed(
                        " (Y) allow  (A) allow all this session  (N) deny  (PgUp/PgDn) scroll"
                        if view.approval and view.approval.get("allow_all") else
                        " (Y) allow  (N) deny  (PgUp/PgDn) scroll  (Esc) deny"
                    )),
                    height=1,
                ),
            ]),
            title=_approval_title,
        ),
        filter=Condition(approving),
    )

    root = FloatContainer(
        content=body,
        floats=[
            Float(
                content=editor_box,
                width=lambda: min(100, max(30, _cols() - 8)),
                height=4,
            ),
            Float(
                content=approval_box,
                width=lambda: _approval_size()[0],
                height=lambda: _approval_size()[1],
            ),
        ],
    )

    layout = Layout(root, focused_element=input_area)

    view.app = Application(
        layout=layout,
        key_bindings=_build_keys(),
        style=_build_style(),
        full_screen=True,
        # A filter, not a flag, so it can be toggled without a restart.
        #
        # The tools pane turns capture on for as long as it's open,
        # whatever F2 says. Capture costs you terminal text selection,
        # which is why it's off by default - but there is nothing to
        # select in a menu, and without it the terminal converts each
        # wheel notch into three arrow keys and the selection jumps
        # three switches at a time. Derived rather than saved and
        # restored, so it can't get stuck on.
        mouse_support=Condition(lambda: view.mouse or view.pane in ("tools", "settings")),
    )

    # First paint has no render_info, so the scroll lands at line one and
    # nothing would move it until the next keystroke - which is how a
    # freshly loaded history ends up showing its oldest messages. Repaint
    # once more, then get out of the way.
    primed = []

    def _prime(_sender):
        if not primed:
            primed.append(True)
            _refresh()

    view.app.after_render += _prime

    saved = _stderr_to_file()
    try:
        view.app.run()
    finally:
        _stderr_back(saved)


# Libraries write to the terminal from native code, past Python entirely:
# OpenCV's "[ WARN:0@0.4] ...", ALSA, ffmpeg, a browser started from here,
# a C++ crash message. Any of it lands on top of the screen and in the
# input line. While the screen is up, the process's stderr (file
# descriptor 2, which those write to, and Python's sys.stderr with it) goes
# to a file instead; it comes back when the app closes, so a crash on the
# way out is still printed.
STDERR_FILE = "stderr.log"
STDERR_MAX = 1024 * 1024          # bytes; a bigger file starts over


def stderr_path():
    import logbook

    return os.path.join(logbook.LOG_DIR, STDERR_FILE)


def _stderr_to_file():
    """Point fd 2 at stderr.log. The saved fd to restore, or None."""
    import time

    try:
        where = stderr_path()
        os.makedirs(os.path.dirname(where), exist_ok=True)
        mode = "w" if os.path.exists(where) and os.path.getsize(where) > STDERR_MAX else "a"
        log = open(where, mode, buffering=1, encoding="utf-8", errors="replace")
        log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} Luna started ===\n")
        log.flush()
        try:
            sys.stderr.flush()
        except Exception:
            pass
        saved = os.dup(2)
        os.dup2(log.fileno(), 2)
        log.close()                  # fd 2 holds the file open now
        return saved
    except Exception:
        return None                  # no file: things print as before, nothing breaks


def _stderr_back(saved):
    if saved is None:
        return
    try:
        sys.stderr.flush()
    except Exception:
        pass
    try:
        os.dup2(saved, 2)
        os.close(saved)
    except OSError:
        pass


def _cols():
    if view.app is None:
        return 80
    return view.app.output.get_size().columns


def stop():
    if view.app is not None:
        try:
            view.app.exit()
        except Exception:
            pass
