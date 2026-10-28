"""The launcher pane (Tab, once): her pages, one key away.

Portrait, settings, the live monitor, her thoughts, her memory, the help
and any page a plugin adds (the chess board). Up/down or the wheel pick
one, Enter or space or a click opens it, and the pane closes so you see
what happened. Each entry runs the same slash command you could type
(/portrait, /settings...), so there's one way of opening each page.

Part of the ui package; see ui/__init__.py.
"""
from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from .shared import _refresh, state, view
from .text import vwidth

# (label, what it is, command, address). The address is filled in from livefeed.
_FIXED = (
    ("Portrait", "her animated portrait in a window of its own (again closes it)", "/portrait", "portrait/"),
    ("Portrait for OBS", "the see-through address for a browser source", "/portrait obs", "portrait/?bg=transparent"),
    ("Pose studio", "the debug viewer: make and try gestures, touches and moods", "open:", "portrait/?debug=1"),
    ("Settings", "every setting, with switches, sliders, search and presets", "/settings", "settings/"),
    ("Live monitor", "watch her think: stages, tokens, tools, mood", "/monitor", ""),
    ("Thoughts", "her reasoning, turn by turn", "/thoughts", "thoughts/"),
    ("Memory", "the facts she keeps, to add, edit or delete", "/memory", "memory/"),
    ("Help", "every command and key", "/help", "help/"),
)
_HEAD = 3          # lines above the first entry


def entries():
    """[(label, what, command, address)] in order, with any page a plugin
    added (livefeed.add_page) that isn't listed already."""
    try:
        from web import livefeed

        base = livefeed.url()
        pages = list(livefeed.PAGES.items())
    except Exception:
        base, pages = "", []
    out = [(label, what, cmd, f"{base}/{path}" if base else "") for label, what, cmd, path in _FIXED]
    # "open:" alone: open its own address in the browser (no slash command for it)
    out = [(label, what, f"open:{address}" if cmd == "open:" else cmd, address) for label, what, cmd, address in out
           if cmd != "open:" or address]
    known = {path.split("/")[0] for *_x, path in _FIXED if path}
    for name, (label, _handler, visible) in pages:
        try:
            shown = visible()
        except Exception:
            shown = False
        if shown and name not in known:
            out.append((label.capitalize(), "a page a plugin added", f"open:{base}/{name}/", f"{base}/{name}/"))
    return out


def move(step):
    count = len(entries())
    view.launch_cursor = max(0, min(count - 1, view.launch_cursor + step)) if count else 0
    _refresh()


def launch(index=None):
    """Open the selected page, then close the pane so its message shows."""
    items = entries()
    index = view.launch_cursor if index is None else index
    if not 0 <= index < len(items):
        return
    _label, _what, command, address = items[index]
    view.pane = None
    _refresh()
    if command.startswith("open:"):
        try:
            from web import portrait_window

            portrait_window.quiet_open(command[5:])
            from .messages import add_message

            add_message("system", f"Opened {address}")
        except Exception as e:
            from .messages import add_message

            add_message("system", f"Couldn't open {address}: {e}")
        return
    if view.on_submit:
        view.on_submit(command)


def fragments():
    width = max(40, _width())
    items = entries()
    picked = items[view.launch_cursor][3] if 0 <= view.launch_cursor < len(items) else ""
    out = [("class:dim", " up/down pick, enter or click opens it in your browser\n"),
           ("class:footer", _clip(f" {picked}", width) + "\n\n")]
    for i, (label, what, _command, _address) in enumerate(items):
        here = i == view.launch_cursor
        out.append(("class:key" if here else "class:dim", " > " if here else "   "))
        out.append(("class:agent bold" if here else "class:agent", f"{label:<18}"))
        out.append(("class:text" if here else "class:dim", _clip(f" {what}", width - 22) + "\n"))
    if state.get("controls"):                     # e.g. no global hotkey on this desktop
        out.append(("class:footer", "\n " + state["controls"] + "\n"))
    return out


def _clip(text, width):
    if vwidth(text) <= width:
        return text
    out = ""
    for ch in text:
        if vwidth(out + ch) > width - 1:
            break
        out += ch
    return out + "…"


def _width():
    try:
        return view.app.output.get_size().columns - 4
    except Exception:
        return 80


def cursor():
    return Point(x=0, y=_HEAD + view.launch_cursor)


class LauncherControl(FormattedTextControl):
    def mouse_handler(self, mouse_event):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            move(-1)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            move(1)
            return None
        if mouse_event.event_type == MouseEventType.MOUSE_UP:
            row = mouse_event.position.y - _HEAD
            if 0 <= row < len(entries()):
                view.launch_cursor = row
                launch(row)
            return None
        return super().mouse_handler(mouse_event)
