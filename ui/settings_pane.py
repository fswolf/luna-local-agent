"""The settings pane (Tab, three times): the everyday settings, grouped by
section, each with its value, a line saying what it does and whether a
change applies now or on a restart. `a` shows every setting config.json
can hold; a filter always searches all of them. The full list is nicer
in a browser: the settings page (settings_web.py, /settings).

    up/down, PgUp/PgDn   pick a setting
    space                flip an on/off, step through a choice
    enter                the same, or type a new value (numbers, text, lists)
    /                    filter: only the settings whose name or line matches
    x                    back to the default (takes it out of config.json)
    a                    everyday settings / all of them

What a setting is comes from config/schema.py; which ones apply live comes
from config.SETTINGS, the same table /set uses, so the pane and /set can
never disagree. Values you haven't set show the default dimmed.

Part of the ui package; see ui/__init__.py.
"""
import json
import os
import re

from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from .shared import _refresh, view
from .messages import add_message
from .text import _rendered_lines, _width, vwidth

_HIDDEN = "••••"
_example = None


def _example_values():
    """config.example.json, flattened: the defaults to show for keys the
    user hasn't set and the table doesn't know."""
    global _example

    if _example is None:
        import config

        try:
            with open(os.path.join(config.BASE_DIR, "config.example.json")) as file:
                _example = dict(_leaves(json.load(file)))
        except (OSError, ValueError):
            _example = {}

    return _example


def _leaves(node, prefix=""):
    from config.schema import SCHEMA

    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key

        # a nested block that is one setting (mcp.servers) stays whole
        if isinstance(value, dict) and value and SCHEMA.get(path, ("",))[0] != "dict":
            yield from _leaves(value, path)
        else:
            yield path, value


def _all_paths():
    """Every setting: the schema, the table, the example and whatever is
    in the user's own config.json, in the schema's order first."""
    import config
    from config.schema import SCHEMA

    seen = dict.fromkeys(SCHEMA)
    for path in list(config.SETTINGS) + list(_example_values()) + [p for p, _ in _leaves(config.settings)]:
        seen.setdefault(path, None)

    return list(seen)


def _section(path):
    """The heading a setting sits under. Plugins get one each."""
    from config.schema import SECTIONS

    parts = path.split(".")

    if parts[0] == "plugins" and len(parts) > 2:
        return f"plugins.{parts[1]}", f"Plugin: {parts[1]}"

    return parts[0], SECTIONS.get(parts[0], parts[0].replace("_", " ").title())


def describe(path):
    """(kind, explanation, choices) for a setting, guessed for unknown keys."""
    from config.schema import SCHEMA

    entry = SCHEMA.get(path)

    if entry:
        return entry[0], entry[1], tuple(entry[2]) if len(entry) > 2 and entry[2] else ()

    value = _value(path)[0]

    # a key the schema doesn't know whose name says it's a login: hide it
    if re.search(r"(token|password|passwd|secret|api_?key|auth|cookie)", path.split(".")[-1], re.I) \
            and not isinstance(value, (bool, int, float)):
        return "secret", "", ()

    kind = ("bool" if isinstance(value, bool) else "int" if isinstance(value, int)
            else "float" if isinstance(value, float) else "list" if isinstance(value, list)
            else "dict" if isinstance(value, dict) else "text")

    return kind, "", ()


def _value(path):
    """(value, is_set): what's in effect, and whether config.json sets it."""
    import config

    stored = config._stored(path)

    if stored is not None:
        return stored, True

    if path in config.SETTINGS:
        return config.current(path), False

    return _example_values().get(path), False


def _rows():
    """The settings shown, in order, after the filter: (path, group key, title)."""
    from config.schema import BASIC

    needle = (view.set_filter or "").lower().strip()
    rows = []

    for path in _all_paths():
        if not needle and not view.set_all and path not in BASIC:
            continue
        if needle:
            _kind, line, _choices = describe(path)

            if needle not in path.lower() and needle not in line.lower():
                continue

        key, title = _section(path)
        rows.append((path, key, title))

    # keep each section together, in the order its first member appears
    order = {}
    for _path, key, _title in rows:
        order.setdefault(key, len(order))

    return sorted(rows, key=lambda row: order[row[1]])


def _groups():
    groups = []

    for path, key, title in _rows():
        if not groups or groups[-1][0] != key:
            groups.append((key, title, []))

        groups[-1][2].append(path)

    return groups


def _line_of(index):
    """The printed line a row sits on, headers and gaps included."""
    line = seen = 0

    for position, (_key, _title, paths) in enumerate(_groups()):
        if position:
            line += 1

        line += 1

        for _path in paths:
            if seen == index:
                return line

            seen += 1
            line += 1

    return line


def _show(path, value, kind):
    if kind == "secret":
        return _HIDDEN if value else "not set"
    if value is None:
        return "-"
    if kind == "dict":
        # a nested block (MCP servers, satellites) can hold logins: only how many
        return f"{{{len(value)} entries}}" if isinstance(value, (dict, list)) and value else "{}"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return ", ".join(map(str, value)) or "(none)"
    if isinstance(value, dict):
        return f"{{{len(value)} entries}}" if value else "{}"
    if value == "":
        return '""'

    return str(value)


def _clip(text, width):
    if width <= 1:
        return ""
    if vwidth(text) <= width:
        return text

    out = ""
    for ch in text:
        if vwidth(out + ch) > width - 1:
            break
        out += ch

    return out + "…"


def _short(path, group_key):
    """The name within its section: 'mode' under Listening, not 'stt.mode'."""
    return path[len(group_key) + 1:] if path.startswith(group_key + ".") else path


def _fragments():
    import config

    width = _width()
    rows = [path for _g in _groups() for path in _g[2]]
    fragments = []
    index = 0

    if not rows:
        return [("class:dim", f" Nothing matches \"{view.set_filter}\". / to change the filter, Esc to clear it.")]

    for position, (key, title, paths) in enumerate(_groups()):
        if position:
            fragments.append(("", "\n"))

        fragments.append(("class:label bold", f" {title}\n"))

        for path in paths:
            kind, line, _choices = describe(path)
            value, is_set = _value(path)
            live = config.SETTINGS.get(path, (None, False))[1]
            here = index == view.set_cursor

            name = _clip(_short(path, key), 24)
            shown = _clip(_show(path, value, kind), 18)
            mark = "" if live else " ↻"

            fragments.append(("class:key" if here else "", " >" if here else "  "))
            # a switch is green when it's on, grey when it's off, wherever the
            # value came from; • marks one you've set yourself in config.json
            fragments.append(("class:ok" if is_set else "", " • " if is_set else "   "))
            fragments.append(("class:value bold" if here else "class:value", f"{name:<24} "))
            if kind == "bool":
                style = "class:ok" if value else "class:dim"
            else:
                style = "class:ok" if is_set else "class:dim"
            fragments.append((style, f"{shown:<18}"))
            fragments.append(("class:warn" if here and not live else "class:dim", f"{mark:<3}"))
            rest = width - 52

            if rest > 8 and line:
                fragments.append(("class:text" if here else "class:dim", _clip(line, rest)))

            fragments.append(("", "\n"))
            index += 1

    if fragments and fragments[-1][1] == "\n":
        fragments.pop()

    return fragments


def _web():
    import config

    if not getattr(config, "MONITOR_ENABLED", True):
        return ""
    try:
        import settings_web

        return settings_web.url()
    except Exception:
        return ""


def _header():
    shown = len(_rows())
    total = len(_all_paths())
    count = (f"{shown} of {total}" if view.set_filter else
             f"all {total} settings" if view.set_all else f"{shown} everyday settings")
    flt = f'  filter: "{view.set_filter}" (Esc clears)' if view.set_filter else ""
    web = _web()

    return [
        ("class:label", f" {count}"), ("class:dim", flt),
        ("class:dim", "   • = set in config.json (no dot: default) · switches: green on, grey off · ↻ = after a restart\n"),
        ("class:key", " space"), ("class:dim", " flip/step  "),
        ("class:key", "enter"), ("class:dim", " edit  "),
        ("class:key", "/"), ("class:dim", " filter  "),
        ("class:key", "x"), ("class:dim", " default  "),
        ("class:key", "a"), ("class:dim", " everyday/all  "),
        ("class:dim", view.set_status or (f"every setting, with sliders: {web}" if web else "")),
    ]


def toggle_all():
    """a: the everyday settings, or every one of them."""
    view.set_all = not view.set_all
    view.set_cursor = view.set_scroll = 0
    _refresh()


def _height():
    window = view.set_window
    if window is not None and window.render_info is not None:
        return max(1, window.render_info.window_height)

    return 10


def _selected():
    rows = _rows()
    return rows[view.set_cursor][0] if 0 <= view.set_cursor < len(rows) else None


def move(step):
    rows = len(_rows())

    if not rows:
        return

    view.set_cursor = max(0, min(view.set_cursor + step, rows - 1))
    line, height = _line_of(view.set_cursor), _height()

    if line - 1 < view.set_scroll:
        view.set_scroll = max(0, line - 1)
    elif line >= view.set_scroll + height:
        view.set_scroll = line - height + 1

    _refresh()


def _status(text):
    view.set_status = text
    _refresh()


def _save(path, raw):
    """Save through config, apply what has to be told, and say so."""
    import config

    try:
        value, live = config.save_any(path, raw)
    except ValueError as e:
        return _status(f"  {e}")
    except OSError as e:
        return _status(f"  couldn't write config.json: {e}")

    _after(path, value)
    kind = describe(path)[0]
    _status(f"  {path} = {_show(path, value, kind)}{'' if live else ' (after a restart)'}")


def _after(path, value):
    """The settings that need more than a new value: the same side effects
    /set and the tools pane have."""
    try:
        if path == "stt.mode":
            import ptt

            ptt.set_mode(value)
        elif path.startswith("mood."):
            import mood

            mood._announce()
        elif path == "portrait.hologram.enabled":
            import livefeed

            livefeed.emit("holo", on=bool(value))
        elif path.startswith("portrait.lights."):
            import livefeed

            livefeed.lights_changed()
        elif path == "portrait.frame":
            import livefeed

            livefeed.emit("frame", frame=value)
        elif path == "station.enabled":
            import station

            if value:
                ok, said = station.start()
                add_message("system", f"Relay stations: {said}" if ok else f"Relay stations didn't start: {said}")
            else:
                station.stop()
                add_message("system", "Relay stations: off")
        elif path == "portrait.background":
            import livefeed

            livefeed.emit("background", value=value)
        elif path == "portrait.model":
            import livefeed

            livefeed.emit("reload")
        elif path in ("portrait.gestures", "portrait.chat_gestures"):
            import livefeed

            livefeed.gesture_mode_changed()
        elif path == "camera.presence.enabled":
            import presence

            if value:
                if not presence.start():
                    add_message("system", "Presence didn't start: " + " ".join(presence.status()))
            else:
                presence.stop()
    except Exception as e:  # the value is saved either way
        add_message("system", f"{path} saved, but applying it now failed: {e}")


def flip():
    """Space: on/off flips, a choice steps on, anything else opens the editor."""
    path = _selected()

    if path is None:
        return

    kind, _line, choices = describe(path)
    value = _value(path)[0]

    if kind == "bool":
        return _save(path, "false" if value else "true")

    if kind == "choice" and choices:
        now = str(value).lower() if value is not None else None
        names = [str(c).lower() for c in choices]
        nxt = choices[(names.index(now) + 1) % len(choices)] if now in names else choices[0]

        return _save(path, str(nxt))

    edit()


def edit():
    """Enter: open the editor on the selected setting."""
    path = _selected()

    if path is None:
        return

    kind, _line, choices = describe(path)

    if kind == "bool" or (kind == "choice" and choices):
        return flip()

    if kind == "dict":
        return _status(f"  {path} is a nested block - edit it in config.json")

    value = _value(path)[0]
    text = "" if kind == "secret" or value is None else (
        ", ".join(map(str, value)) if isinstance(value, list) else str(value))
    view.set_editing = {"mode": "value", "path": path, "text": text}
    _refresh()


def start_filter():
    view.set_editing = {"mode": "filter", "path": None, "text": view.set_filter or ""}
    _refresh()


def editor_title():
    editing = view.set_editing or {}

    if editing.get("mode") == "filter":
        return "Filter settings (Enter keeps it, Esc cancels)"

    path = editing.get("path") or ""
    kind, _line, _choices = describe(path)
    hint = {"list": "comma-separated", "secret": "hidden once saved, empty to clear",
            "int": "a whole number", "float": "a number"}.get(kind, "")

    return f"{path}{' (' + hint + ')' if hint else ''}  Enter saves, Esc cancels"


def editor_help():
    editing = view.set_editing or {}
    if editing.get("mode") == "filter":
        return ""

    return describe(editing.get("path") or "")[1]


def finish_edit(text):
    """The editor's Enter."""
    editing = view.set_editing or {}
    view.set_editing = None

    if editing.get("mode") == "filter":
        view.set_filter = text.strip()
        view.set_cursor = view.set_scroll = 0
        return _refresh()

    _save(editing["path"], text)


def cancel_edit():
    view.set_editing = None
    _refresh()


def clear_filter():
    """Esc with a filter on clears it; returns False when there was none."""
    if not view.set_filter:
        return False

    view.set_filter = ""
    view.set_cursor = view.set_scroll = 0
    _refresh()

    return True


def reset():
    """x: back to the default, by taking it out of config.json."""
    import config

    path = _selected()

    if path is None:
        return

    try:
        removed = config.reset_setting(path)
    except OSError as e:
        return _status(f"  couldn't write config.json: {e}")

    _status(f"  {path}: back to the default after a restart" if removed
            else f"  {path} isn't set in config.json - already the default")


def _scroll_position(window):
    return view.set_scroll


def _cursor_point():
    return Point(x=0, y=view.set_scroll)


def line_count():
    return _rendered_lines(_fragments())


class SettingsControl(FormattedTextControl):
    """The wheel steps the selection, like the tools pane."""

    def mouse_handler(self, mouse_event):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            move(-1)
            return None

        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            move(1)
            return None

        return super().mouse_handler(mouse_event)
