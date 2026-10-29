"""The tools pane (Tab, twice): every tool, plugin and feature switch, in
groups, with what each costs in context. Space or Enter flips one.

Part of the ui package (it was one ui.py); see ui/__init__.py.
"""
import threading

from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from .shared import _refresh, view
from .messages import add_message
from .text import _rendered_lines


# Things that aren't tools but are worth switching from the same place.
# Each is (label, config key, dotted setting, note) - the pane shows
# what it costs and flips it through /set's own machinery, so the
# change is saved exactly as if you'd typed it.
_FEATURES = (
    ("mood", "MOOD_ENABLED", "mood.enabled", ""),
    ("mood voice", "MOOD_VOICE", "mood.voice", "tints the TTS"),
    ("warmth sensing", "MOOD_AFFECTION", "mood.affection", "1 call/turn"),
)


# Costs nothing in context - it records what the model already produced
# - so it carries no token figure, just what it does.
_THOUGHT_FEATURES = (
    ("reasoning log", "THOUGHTS_ENABLED", "thoughts.enabled", "/thoughts to read"),
    ("adaptive thinking", "ADAPTIVE_ENABLED", "adaptive.enabled", "llama-server only"),
    ("grounding check", "GROUNDING_ENABLED", "grounding.enabled", "flags unsourced specifics"),
)


# Learning and continuity (mind/reflect.py). Each costs a little context -
# a few lines of lessons and notes - or a model call while she's idle.
_SELF_FEATURES = (
    ("lessons (dream pass)", "SELF_LESSONS", "self.lessons", "/reflect, /lessons"),
    ("episodic memory", "SELF_EPISODES", "self.episodes", "/episodes"),
    ("fact cleanup", "SELF_TIDY_FACTS", "self.tidy_facts", "sqlite memory"),
    ("calibration", "SELF_CALIBRATION", "self.calibration", "says when unsure"),
    ("startup greeting", "SELF_GREET", "self.greet", "after a break"),
    ("skill recipes", "SELF_SKILLS", "self.skills", "/skills"),
    ("ongoing projects", "SELF_PROJECTS", "self.projects", "/projects"),
    ("situation block", "SITUATION_ENABLED", "situation.enabled", "/situation"),
)


# What she may do to your machine, cycled with space and saved to
# config.json. Read and write cover the file tools; execute is the shell
# tool, which always asks when it's on - there's deliberately no
# "allow" for commands.
_PERMS = (
    ("read", "files.read", "FILES_READ", ("allow", "ask", "off"), "list and read files"),
    ("write", "files.write", "FILES_WRITE", ("ask", "allow", "off"), "create and edit files"),
    ("execute", "shell.enabled", "SHELL_ENABLED", ("ask", "off"), "run commands - each one asks"),
    # Smart-home changes: the home plugin's ask_all. "allow" still asks
    # for locks, doors, alarms and valves (its ask_domains).
    ("home", "plugins.home.ask_all", None, ("ask", "allow"), "smart-home changes - locks and doors always ask"),
)


def _perm_value(label):
    import config

    if label == "home":
        return "ask" if config.plugin_settings("home").get("ask_all", False) else "allow"

    for name, _path, key, values, _note in _PERMS:
        if name == label:
            raw = getattr(config, key, None)

            if isinstance(raw, bool):
                return "ask" if raw else "off"

            raw = str(raw or "").lower()

            return raw if raw in values else values[0]

    return ""


def _perm_group():
    try:
        import config  # noqa: F401
    except Exception:
        return None

    members = []

    for name, _path, _key, _values, note in _PERMS:
        value = _perm_value(name)

        if name == "write" and value == "allow":
            note += " - her folder, ~/.config, ~/.local still ask"

        members.append((name, value != "off", True, note, 0, "perm:" + name))

    return ("Permissions", members, 0, 0)


def _self_group():
    try:
        import config
    except Exception:
        return None

    members = [(label, bool(getattr(config, key, False)), True, note, 0, path)
               for label, key, path, note in _SELF_FEATURES]

    return ("Learning", members, 0, 0)


def _thoughts_group():
    try:
        import config
    except Exception:
        return None

    members = [(label, bool(getattr(config, key, False)), True, note, 0, path)
               for label, key, path, note in _THOUGHT_FEATURES]

    return ("Thoughts", members, 0, 0)


def _feature_group():
    """The Mood group: same shape as a tool group, so the cursor, the
    scrolling and the line map don't need to know the difference."""
    try:
        import config
        from mind import mood
    except Exception:
        return None

    members, live, total = [], 0, 0

    for label, key, path, note in _FEATURES:
        on = bool(getattr(config, key, False))
        # Only the mood line itself occupies context; the other two
        # cost a model call and nothing respectively.
        cost = int(len(mood.line() or "") / 3.5) if path == "mood.enabled" else 0

        if path == "mood.enabled" and not on:
            cost = 81  # what it would cost switched back on

        members.append((label, on, True, note, cost, path))
        total += cost
        live += cost if on else 0

    return ("Mood", members, live, total)


def _tool_groups():
    """Every switchable row, tools first. Members are six-tuples: the
    last field is a setting path for a feature, or None for a tool."""
    groups = []

    try:
        import tools

        groups = [(label, [tuple(m) + (None,) for m in members], live, total)
                  for label, members, live, total in tools.grouped()]
    except Exception:
        groups = []

    groups = _with_plugin_switches(groups)
    groups = _with_ask_switches(groups)
    # the portrait's settings live in the settings pane (Tab three times), not here
    extra = [g for g in (_feature_group(), _thoughts_group(), _self_group()) if g]
    perms = _perm_group()

    return ([perms] if perms else []) + groups + extra


def _with_ask_switches(groups):
    """The ask plugin isn't an MCP plugin, so it gets its switches here, at
    the top of its tool group: the plugin itself, and asking on her own
    (with what its prompt line costs while it's on)."""
    try:
        import config
        import plugins

        plugin = plugins.get("ask")
        if plugin is None:
            return groups
        from plugins import ask
    except Exception:
        return groups

    s = config.plugin_settings("ask")
    running = plugin.running()
    saved = bool(s.get("enabled"))
    ready = running or saved or plugin.available()
    if running:
        why = "on - asks only when you tell her to, unless on her own is on"
    elif saved:
        why = "on, but not running - space switches it off"
    else:
        why = plugin.why_unavailable() if not ready else "off - space starts it"
    alone = s.get("auto") is True
    line = ask.ALONE_LINE + (ask.SEARCH_FIRST if ask._can_search() else "")
    cost = int(len(line.format(label="Claude")) / 3.5)
    try:
        daily = int(s.get("auto_daily", 5))
    except (TypeError, ValueError):
        daily = 5
    note = (f"stuck on a script or server problem, {daily} a day"
            + ("" if running else " - only while the plugin is on"))
    rows = [("ask plugin", running or saved, ready, why, 0, "plugin:ask"),
            ("on her own", alone, True, note, cost, "pluginset:plugins.ask.auto")]
    live = cost if alone and running else 0

    out = list(groups)
    for i, (glabel, members, glive, total) in enumerate(out):
        if glabel == "Ask a bigger model":
            out[i] = (glabel, rows + list(members), glive + live, total + cost)
            break
    else:
        out.append(("Ask a bigger model", rows, live, cost))
    return out


def _with_plugin_switches(groups):
    """Each MCP plugin (home, vibecity, minecraft, zork) gets a switch at
    the top of its MCP group, and keeps the group while it's off - so
    connecting is a space press here, not a /command you have to know.
    Its server's own tools join the group once it's connected.

    The switch shows the saved setting (on at launch or not), not only
    whether it's connected: one that's on but couldn't connect (the game
    isn't open) still shows on, so space switches it off."""
    try:
        import config
        import plugins
    except Exception:
        return groups

    out = list(groups)

    for name in plugins.names():
        plugin = plugins.get(name)

        if not plugin or not getattr(plugin.module, "SERVER", None):
            continue

        running = plugin.running()
        saved = bool(config.plugin_settings(plugin.name).get("enabled"))
        ready = running or saved or plugin.available()
        if running:
            why = "connected"
        elif saved:
            why = "on, but not connected - space switches it off"
        else:
            why = plugin.why_unavailable() if not ready else f"space connects - /{name} on"
        row = (f"{name} plugin", running or saved, ready, why, 0, "plugin:" + name)
        label = f"MCP: {name}"

        for i, (glabel, members, live, total) in enumerate(out):
            if glabel == label:
                out[i] = (glabel, [row] + list(members), live, total)
                break
        else:
            out.append((label, [row], 0, 0))

    # and every server of your own (config.json's mcp.servers) gets one too:
    # off disconnects it and takes its tools out of the prompt, saved
    try:
        from core import mcpclient

        servers = getattr(config, "MCP_SERVERS", {}) or {}
    except Exception:
        servers = {}

    for name, spec in servers.items():
        if not isinstance(spec, dict) or plugins.get(name):
            continue

        saved = spec.get("enabled", True) is not False
        live = mcpclient.connected(name)
        if live:
            why = "connected - space disconnects it"
        elif saved:
            why = "on, but not connected (/mcp says why) - space switches it off"
        else:
            why = "off - space connects it"
        row = (f"{name} server", live or saved, True, why, 0, "mcpserver:" + name)
        label = f"MCP: {name}"

        for i, (glabel, members, glive, total) in enumerate(out):
            if glabel == label:
                # while it's off its tools cost nothing: they aren't sent
                out[i] = (glabel, [row] + list(members), glive if live else 0, total)
                break
        else:
            out.append((label, [row], 0, 0))

    return out


def _tool_rows():
    """Every tool, flat, in the order the pane draws them - this is what
    the cursor indexes. Group headers are drawn between them but can't
    be selected, so the two orderings must be derived from one source."""
    return [row for _label, members, _live, _total in _tool_groups()
            for row in members]


def _tool_line_of(index):
    """Which printed line a given tool sits on - headers included, so
    scrolling can follow the selection."""
    # The list is its own window now, so the first group header is
    # line 0 and nothing sits above it.
    line = 0
    seen = 0

    for position, (_label, members, _live, _total) in enumerate(_tool_groups()):
        if position:
            line += 1  # the blank separating this group from the last

        line += 1  # the group header

        for _row in members:
            if seen == index:
                return line

            seen += 1
            line += 1

    return line


def _tool_header():
    """Routing and what it cost, pinned above the list.

    It used to be the first lines of the scrolling area, which meant
    selecting the top tool scrolled it off and nothing could bring it
    back - the one number the pane exists to show, unreachable.
    """
    import config

    try:
        import tools

        live, _possible = tools.budget()
        groups = {label: g_live for label, _m, g_live, _t in tools.grouped()}
        last, up = tools.routing.last(), tools.routing.server_up()
    except Exception:
        live, groups, last, up = 0, {}, {}, None

    if not getattr(config, "TOOLS_ROUTING", True):
        line, style = f" routing off · every tool sent: {live} tokens a turn", "class:dim bold"
    elif up is False or (last.get("why") == "server" and not up):
        # checked first: a server that stopped answering since your last
        # turn means the next one goes unrouted, whatever the last one did
        line, style = (f" routing off · no embedding server · every tool sent: {live} tokens a turn",
                       "class:warn bold")
    elif last.get("routed"):
        sent = sum(groups.get(g, 0) for g in last["sent"] | last.get("pulled", set()))
        line, style = (f" routing on · embedding server up · last turn sent {sent} of {live} tokens",
                       "class:label bold")
    elif last.get("why") == "few":
        line, style = f" routing on · few enough tools that all went: {live} tokens", "class:label bold"
    else:
        server = "embedding server up" if up else "embedding server not tried yet"
        line, style = f" routing on · {server} · {live} tokens with every tool", "class:label bold"

    return [
        (style, line + "\n"),
        ("class:footer", " (space) toggle  (a) whole group  (r) routing  (up/down or wheel) choose"),
    ]


def _route_mark(label):
    """What routing did with this group on your last turn, or "" when it
    wasn't routed (routing off, no embedding server) or the group isn't
    one of the tools' (features, permissions)."""
    try:
        import config
        import tools

        last = tools.routing.last()
    except Exception:
        return ""
    if (not getattr(config, "TOOLS_ROUTING", True) or not last.get("routed")
            or tools.routing.server_up() is False):
        return ""
    if label in last.get("pulled", ()):
        return "pulled in"
    if label in last.get("core", ()):
        return "always"
    if label in last.get("sent", ()):
        return "sent"
    if label in last.get("held", ()):
        return "held back"
    return ""


# Sent and pulled in are the news; always and held back are the usual.
_MARK_STYLE = {"always": "class:dim", "sent": "class:ok", "pulled in": "class:ok bold",
               "held back": "class:dim"}


def _spent(label, live, total):
    """A group header's cost: the subtotal is the point of grouping, it
    turns "which of these 22 do I not need" into "do I need the desktop ones"."""
    if label == "Permissions":
        return "space cycles, saved"
    return f"{live} tok" if live == total else f"{live} of {total} tok"


def _routing_toggle():
    """(r): routing on or off, saved like /set tools.routing."""
    import config

    on = bool(getattr(config, "TOOLS_ROUTING", True))
    config.save_setting("tools.routing", "false" if on else "true")
    add_message("system", "Tool routing off - every tool that's on goes with every turn." if on else
                "Tool routing on - each turn gets the tool groups that fit it (needs the embedding server).")
    _refresh()


def _tool_fragments():
    fragments = []

    if not _tool_rows():
        return [("class:footer", "  no tools registered\n")]

    index = 0
    groups = _tool_groups()
    # The routing marks line up in one column, after the widest header.
    marks = {label: _route_mark(label) for label, _m, _l, _t in groups}
    column = max((len(f" {label}   {_spent(label, live, total)}")
                  for label, _m, live, total in groups if marks[label]), default=0) + 3

    for position, (label, members, group_live, group_total) in enumerate(groups):
        # A blank line separates groups. Only between them: a trailing
        # one is a line the view can never scroll onto, which leaves
        # the scrollbar stranded a notch short of the bottom.
        if position:
            fragments.append(("", "\n"))

        # The subtotal is the point of grouping: it turns "which of
        # these 22 do I not need" into "do I need the desktop ones".
        spent = _spent(label, group_live, group_total)
        fragments.append(("class:label bold", f" {label}"))
        mark = marks[label]
        if mark:
            fragments.append(("class:dim", f"   {spent}".ljust(column - len(label) - 1)))
            fragments.append((_MARK_STYLE[mark], f"{mark}\n"))
        else:
            fragments.append(("class:dim", f"   {spent}\n"))

        for name, on, ready, why, cost, setting in members:
            selected = index == view.tool_cursor
            pointer = " >" if selected else "  "

            if setting and setting.startswith("perm:"):
                mark = _perm_value(name)
                mark_style = {"allow": "class:warn", "ask": "class:ok"}.get(mark, "class:dim")
                name_style = "class:agent bold" if selected else "class:agent"
                fragments.append(("class:key" if selected else "class:dim", pointer))
                fragments.append((mark_style, f" {mark:<5} "))
                fragments.append((name_style, f"{name:<14}"))
                fragments.append(("class:dim", f"  {why}\n"))
                index += 1
                continue

            if not ready:
                mark, mark_style = "--", "class:dim"
            elif on:
                mark, mark_style = "on", "class:ok"
            else:
                mark, mark_style = "off", "class:warn"

            name_style = "class:agent" if (on and ready) else "class:dim"

            if selected:
                name_style += " bold"

            fragments.append(("class:key" if selected else "class:dim", pointer))
            fragments.append((mark_style, f" {mark} "))
            fragments.append((name_style, f"{name:<16}"))
            fragments.append(("class:footer", f"{cost:>5} tok"))

            if why:
                fragments.append(("class:dim", f"   {why}"))

            fragments.append(("", "\n"))
            index += 1

    # No newline after the final row: it would open one more line than
    # the list has, and the scrollbar would stop a notch short of the
    # bottom for ever.
    if fragments and fragments[-1][1].endswith("\n"):
        style, text = fragments[-1]
        fragments[-1] = (style, text[:-1])

    return fragments


def _tool_line_count():
    return _rendered_lines(_tool_fragments())


def _tool_height():
    if view.tool_window is not None and view.tool_window.render_info is not None:
        return max(1, view.tool_window.render_info.window_height)

    return 10


def _tool_move(step):
    """Move the selection, and keep it on screen."""

    rows = len(_tool_rows())

    if not rows:
        return

    view.tool_cursor = max(0, min(view.tool_cursor + step, rows - 1))

    line = _tool_line_of(view.tool_cursor)
    height = _tool_height()

    # One line of slack, so arrowing up onto the first tool of a group
    # brings its heading into view rather than stopping flush under it.
    if line - 1 < view.tool_scroll:
        view.tool_scroll = max(0, line - 1)
    elif line >= view.tool_scroll + height:
        view.tool_scroll = line - height + 1

    _refresh()


def _tool_toggle():
    """Flip the selected tool, unless its dependencies are missing."""
    rows = _tool_rows()

    if not 0 <= view.tool_cursor < len(rows):
        return

    name, on, ready, why, _cost, setting = rows[view.tool_cursor]

    if not ready:
        add_message("system", f"{name} can't be switched on - {why}")

        return

    try:
        if setting and setting.startswith("plugin:"):
            _toggle_plugin(setting[len("plugin:"):], on)
        elif setting and setting.startswith("mcpserver:"):
            _toggle_server(setting[len("mcpserver:"):], on)
        elif setting and setting.startswith("pluginset:"):
            import config

            path = setting[len("pluginset:"):]
            config.save_any(path, not on)
            add_message("system", f"{name}: {'off' if on else 'on'} (saved)")
        elif setting and setting.startswith("perm:"):
            import config

            for label, path, _key, values, _note in _PERMS:
                if label == name:
                    now = _perm_value(label)
                    nxt = values[(values.index(now) + 1) % len(values)]
                    if label == "home":
                        # a plugin setting, so _store rather than save_setting, and
                        # the plugin reads the refreshed block on its next call
                        config._store(path, nxt == "ask")
                        config._plugins_cfg = config.settings.get("plugins", {})
                        break
                    stored = ("true" if nxt != "off" else "false") if path == "shell.enabled" else nxt
                    config.save_setting(path, stored)
                    if label == "write" and nxt == "allow":
                        add_message("system", "Write: allow - file changes won't ask, now or after a "
                                    "restart. Her own folder, ~/.config and ~/.local still ask; the "
                                    "deny list still refuses. Space again to go back to off/ask.")
                    break
        elif setting:
            import config

            config.save_setting(setting, "false" if on else "true")

            # The mood line leaves the prompt with it, and the header
            # row goes with it too.
            if setting.startswith("mood."):
                from mind import mood

                mood._announce()
        else:
            import tools

            tools.set_enabled(name, not on)
    except Exception as e:
        add_message("system", f"Couldn't change {name}: {e}")

    _refresh()


def _plugin_off(plugin):
    """Off: disconnected if it's connected, and either way not started at
    the next launch. One that never connected has nothing to stop."""
    if plugin.running():
        return plugin.stop()
    return True, f"{plugin.name}: off"


def _toggle_plugin(name, on):
    """Connect or disconnect a plugin from the tools pane, saved like
    /<name> on|off. In a thread: connecting can take a few seconds."""
    import sys

    import config
    import plugins

    plugin = plugins.get(name)

    if plugin is None:
        return

    def go():
        model = getattr(sys.modules.get("__main__"), "MODEL", None)
        ok, message = _plugin_off(plugin) if on else plugin.start(model)

        if ok:
            try:
                config.set_plugin_enabled(plugin.name, not on)
                message += " (saved)"
            except Exception:
                pass

        add_message("system", message)
        _refresh()

    add_message("system", f"{'Disconnecting' if on else 'Connecting'} {name}...")
    threading.Thread(target=go, daemon=True, name=f"plugin-{name}").start()


def _toggle_server(name, on):
    """Connect or disconnect one of your own MCP servers, saved. In a
    thread, like a plugin: connecting can take a few seconds."""
    from core import mcpclient

    def go():
        _ok, message = mcpclient.set_server(name, not on)
        add_message("system", message)
        _refresh()

    add_message("system", f"{'Disconnecting' if on else 'Connecting'} {name}...")
    threading.Thread(target=go, daemon=True, name=f"mcp-{name}").start()


def _tool_group_toggle():
    """Switch every row in the selected row's group at once: all off if
    they're all on, otherwise all on. Rows that cycle (Permissions) are
    left alone."""
    position = 0

    for label, members, _live, _total in _tool_groups():
        if position <= view.tool_cursor < position + len(members):
            break
        position += len(members)
    else:
        return

    rows = [m for m in members if m[2] and not (m[5] or "").startswith(("perm:", "plugin:", "mcpserver:", "pluginset:"))]

    if not rows:
        add_message("system", f"{label}: nothing here switches as a group")
        return

    turn_on = not all(m[1] for m in rows)

    try:
        import config
        import tools

        for name, on, _ready, _why, _cost, setting in rows:
            if on == turn_on:
                continue
            if setting:
                config.save_setting(setting, "true" if turn_on else "false")
                if setting.startswith("mood."):
                    from mind import mood

                    mood._announce()
            else:
                tools.set_enabled(name, turn_on)
    except Exception as e:
        add_message("system", f"Couldn't switch {label}: {e}")

    add_message("system", f"{label}: all {'on' if turn_on else 'off'}")
    _refresh()


def _tool_scroll_by(lines):
    """Move the view. The selection comes along only as far as it must.

    Letting the cursor drift off-screen would mean (space) toggling a
    tool you can't see, which is the kind of surprise a pane about
    switching things off should not have.
    """

    view.tool_scroll = max(0, min(
        view.tool_scroll + lines,
        max(0, _tool_line_count() - _tool_height()),
    ))
    _keep_cursor_visible()
    _refresh()


def _keep_cursor_visible():

    rows = len(_tool_rows())

    if not rows:
        return

    top, bottom = view.tool_scroll, view.tool_scroll + _tool_height() - 1
    line = _tool_line_of(view.tool_cursor)

    if line < top:
        # Walk down to the first tool actually in view.
        for index in range(view.tool_cursor, rows):
            if _tool_line_of(index) >= top:
                view.tool_cursor = index
                return
    elif line > bottom:
        for index in range(view.tool_cursor, -1, -1):
            if _tool_line_of(index) <= bottom:
                view.tool_cursor = index
                return


def _clamp():
    """Keep the selection and the scroll inside the list. It can shrink
    under them while the pane is open: a server switched off or a plugin
    disconnecting takes its tools with it, and a scroll left past the new
    last line crashed the renderer (list index out of range)."""
    rows = len(_tool_rows())
    view.tool_cursor = max(0, min(view.tool_cursor, rows - 1))
    view.tool_scroll = max(0, min(view.tool_scroll, _tool_line_count() - _tool_height()))


def _tool_scroll_position(window):
    _clamp()
    return view.tool_scroll


def _tool_cursor_point():
    _clamp()
    return Point(x=0, y=view.tool_scroll)


class _ToolControl(FormattedTextControl):
    """One notch, one option.

    The conversation and the help are documents, where three lines a
    notch is the right feel. This is a menu of 22 switches, and there
    three at a time means overshooting whatever you were aiming at. So
    the wheel steps the selection rather than nudging the view, which
    also makes it do the same thing as the arrow keys instead of
    something subtly different.
    """

    def mouse_handler(self, mouse_event):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            _tool_move(-1)
            return None

        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            _tool_move(1)
            return None

        return super().mouse_handler(mouse_event)
