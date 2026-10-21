"""The help pane (Tab, once): what it says and how it scrolls.

Part of the ui package (it was one ui.py); see ui/__init__.py.
"""
from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from .shared import _events, _refresh, state, view
from .conversation_pane import WHEEL_LINES
from .text import _keyed, _rendered_lines


# ---------------------------------------------------------------------------
# Scrolling the help window
#
# Same machinery as the conversation, measured from the other end: the
# conversation counts back from the newest line because that is where
# you live, help counts down from the top because it's a document. Both
# route the wheel through their own counter for the reason documented on
# _ConversationControl - Window's own wheel handling is overwritten by
# get_vertical_scroll on every render.
# ---------------------------------------------------------------------------
def _help_line_count():
    return _rendered_lines(_help_fragments())


def _help_height():
    if view.help_window is not None and view.help_window.render_info is not None:
        return max(1, view.help_window.render_info.window_height)

    return 10


def _help_scroll_by(lines):
    """Positive is further down the page."""

    view.help_scroll = max(0, min(
        view.help_scroll + lines,
        max(0, _help_line_count() - _help_height()),
    ))
    _refresh()


def _help_scroll_position(window):
    return view.help_scroll


def _help_cursor():
    return Point(x=0, y=view.help_scroll)


class _HelpControl(FormattedTextControl):
    def mouse_handler(self, mouse_event):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            _events["help_wheel"] += 1
            _help_scroll_by(-WHEEL_LINES)
            return None

        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            _events["help_wheel"] += 1
            _help_scroll_by(WHEEL_LINES)
            return None

        _events["other_mouse"] += 1

        return super().mouse_handler(mouse_event)


# What HOME does depends on the recording mode, so the help says what
# it will actually do right now rather than something generic.
_HOME_BY_MODE = {
    "auto": "start listening - silence ends the turn",
    "manual": "start recording - press again to stop",
    "open": "turn hands-free listening on or off",
}

# A row is (command, description); a bare string renders as a dim note
# line, which is how sections get sentences instead of staying terse.
_HELP_SECTIONS = [
    ("Just say it", [
        "Most of what she can do has no command - asking is the command.",
        "These all trigger real tool calls:",
        "",
        '  "remind me in 20 minutes to stretch"',
        '  "wake me up at 7:30" - or "every weekday at 6"',
        '  "remember that I stream on tuesdays"',
        '  "what do you remember about my gpu?"',
        '  "search for the LM Studio 0.4 changelog"',
        '  "what time is it?" / "how long until friday?"',
        '  "turn the music down" / "what\'s on my clipboard?"',
        '  "how much vram have I got free?"',
        '  "what\'s on my screen?" - needs vision on and a vision model',
        '  "write me a bash script in ~/scripts that backs up my configs"',
        '  "open ~/notes.txt and fix the typo in the second line"',
    ]),
    ("Keys", [
        ("(HOME)", None),  # filled in from the current mode
        ("(Enter)", "send message"),
        ("(PgUp/PgDn)", "scroll the pane - conversation or this help"),
        ("(wheel)", "same - arrow keys too"),
        ("(F2)", "mouse capture: wheel scroll vs selecting text"),
        ("(End)", "back to newest / top of help"),
        ("(Tab)", "cycle: conversation, help, tools, settings"),
        ("(ESC)", "quit"),
    ]),
    ("Voice modes", [
        ("/mode", None),  # gets the (now: ...) suffix
        "auto:   HOME arms the mic, silence ends the turn",
        "manual: HOME starts recording, HOME again stops it",
        "open:   hands-free - she listens continuously",
        "",
        ("/mic", "levels from the last recording - is she hearing you?"),
        ("/barge", "talk-over-her diagnostics, with the thresholds"),
        ("/wake", "wake word status and live scores (openwakeword)"),
    ]),
    ("Her voice", [
        ("/voice", "list what the TTS server offers, current first"),
        ("/voice bella", "switch - partial names match, saved to config"),
        ("/voice luna", "blends work too, if the server defines them"),
        "pitch is a setting, not a voice: /set tts.pitch 3 reads",
        "younger, -3 older, and it applies to the next sentence.",
    ]),
    ("Reminders", [
        ("/reminders", "list what's scheduled, numbered, with countdowns"),
        ("/cancel N", "cancel by number - alarms live in the same list"),
        ("/when ...", "dry-run the time parser, schedules nothing"),
        "repeats all work: \"every monday at 9\", \"daily at 7:30\",",
        "\"every 30 minutes\", \"weekdays at 8\". Said or typed.",
    ]),
    ("Alarms", [
        ("/alarm 7:30am", "set one - any time phrase works"),
        ("/alarm every weekday at 6", ""),
        ("/alarms", "list them (cancel with /cancel)"),
        ("/snooze [n]", "ring again in n minutes - bare /snooze uses the default"),
        ("/alarm off", "stop one that's ringing - talking over it also works"),
        ("/alarm test", "hear the tone at alarm volume"),
        ("/when alarm 6", "how an alarm reads a time - bare hours mean morning"),
        "she speaks a line written for the alarm, plays the tone, and",
        "repeats until dismissed - louder and less charming each round.",
        "one due while the app was closed is skipped, not rung at noon.",
    ]),
    ("Mood", [
        ("/mood", "how she's feeling, both dials, and what moved it"),
        ("/mood reset", "back to baseline for the hour"),
        "shown on the Status row - 'Idle - sleepy', and it tints her",
        "voice a few percent. Survives a restart, faded by how long you",
        "were gone. She drifts with the",
        "clock, how long you've been at it, errors",
        "being talked over, and whether you're kind to her - tone only,",
        "never how much she helps.",
        "/set mood.enabled false turns it off.",
    ]),
    ("Memory", [
        ("/facts", "what she remembers, and which backend holds it"),
        ("/facts all", "the whole table, not just the newest"),
        ("/facts retired", "superseded facts - kept, hidden from her"),
        "json backend: the original capped list in memory.json.",
        "sqlite backend (experimental): permanent, searched, and a new",
        "fact can retire the old one it contradicts. Switch live with",
        "/set long_term_memory.backend sqlite|json - loses nothing.",
        ("/memory", "the memory editor in your browser"),
        "",
        ("/thoughts", "her reasoning, turn by turn, in the browser"),
        ("/monitor", "watch her think live - stages, tokens, tools, mood"),
        ("/portrait", "her animated portrait in its own window (again closes it)"),
        ("/portrait models", "list the models in portrait/models; /portrait use <n> switches"),
        ("/portrait obs", "the see-through URL for an OBS browser source"),
        ("/portrait wave", "act it out: wave hug jump bounce shrug stretch look_hand tuck_hair (3D models)"),
        ("/portrait gestures", "how her replies set them off: tags, meaning, keywords, off"),
        ("/portrait frame", "bust (head and shoulders) or full (all of her); click her to touch"),
        "/set thoughts.enabled false stops recording it.",
        "",
        ("/reflect", "dream pass now: lessons, session notes, fact cleanup"),
        ("/lessons", "what she's learned - /lessons forget|restore <n>"),
        ("/episodes", "her notes on conversations and games, how she feels about each game - /episodes forget <n>"),
        ("/skills", "recipes she's saved - /skills show|forget|restore <n>"),
        ("/projects", "ongoing work - /projects show|done|pause|resume|drop <n>"),
        ("/situation", "the live lines she sees each turn (window, music, load...)"),
        "the Learning group in the tools pane switches each part.",
    ]),
    ("Tools", [
        "Tab twice opens the tools pane: every tool, what its schema",
        "costs in tokens, and space to switch it on or off. Those",
        "schemas ride along in every single prompt, so switching off",
        "the ones you rarely ask for buys back context. Saved to",
        "config.json; a tool whose dependencies are missing says so",
        "and can't be switched on.",
        "",
        ("/tools", "the same list, printed into the conversation"),
        ("/tooltest", "canned requests, two ways each: does this model"),
        "                actually pick the right tool? Run it after changing models.",
        ("/repair", "rewrite old keyword-rescued reminders as the tool"),
        "                calls they should have been - teaches by example.",
    ]),
    ("Files", [
        "she can list and read anything under ~ (minus keys, credentials",
        "and shell startup files), and write or edit with your say-so:",
        "every write pops a permission window with the content or the",
        "diff. Y or Enter allows, N or Esc denies, PgUp/PgDn scrolls.",
        "A allows all file changes until you restart (her own folder,",
        "~/.config and ~/.local still ask) - /allow off ends it early.",
        "Permissions, at the top of the tools pane, sets read / write /",
        "execute for good: allow, ask or off, saved to config.json.",
        "No answer in files.approval_timeout seconds is a no.",
        "/set files.enabled false turns the whole thing off.",
    ]),
    ("Commands", [
        "\"check if the kokoro service is running\", \"what's using port",
        "8080?\", \"run my test script\" - she can run shell commands,",
        "and every one asks first: the popup shows the command and the",
        "folder. There is no allow-all for commands. Output is capped,",
        "commands time out (shell.timeout), and sudo can't prompt.",
        "/set shell.enabled false takes the tool away.",
    ]),
    ("Plugins", [
        ("/plugins", "list add-ons and whether each is running"),
        ("/mcp", "MCP servers: connected or not, and their tools"),
        ("/pomf on", "stream chat - /<name> on|off|status for any plugin"),
        "chat-triggered turns get a restricted tool set and never",
        "touch conversation history.",
    ]),
    ("Session", [
        ("/look", "list windows, or test a screenshot"),
        ("/holo", "portrait hologram look on/off (live, saved)"),
        ("/camera", "webcam on/off, list cameras, take a test picture"),
        ("/presence", "notice who's at the desk: on/off, status"),
        ("/people", "who she knows: enroll face|voice <name>, forget <name>"),
        ("/allow", "is allow-all on for file changes? /allow off ends it"),
        ("/log", "tail the debug log without leaving the app"),
        ("/context", "how big every prompt is vs the model's context"),
        ("/scroll", "why the wheel isn't scrolling, if it isn't"),
        "",
        "in the tools pane: up/down or the wheel choose, space toggles, a the whole group, r tool routing.",
        "the Mood group at the bottom switches moods, her voice tint",
        "and warmth sensing from the same place; Thoughts switches the",
        "reasoning log; Learning switches lessons, episodes, fact cleanup,",
        "calibration and the startup greeting.",
        "the pane grabs the mouse while it's open so one notch is one",
        "option - F2 and text selection go back to normal on the way out.",
        ("/mouse", "same as F2, and saves the choice"),
        ("/set", "alone lists every setting with its value; /set a.b x"),
        ("/settings", "every setting in your browser: switches, sliders, search, presets"),
        ("/preset", "assistant, companion or streamer: several settings at once"),
        "                changes one, saved to config.json, most apply live.",
        "the settings pane (Tab three times) lists every setting there is,",
        "grouped, each with what it does: space flips or steps, enter edits,",
        "/ filters, x puts one back to its default; ↻ marks after-a-restart.",
        ("/keys", "hotkey + socket diagnostics"),
        ("/clear", "wipe conversation and saved history - not memory"),
        ("/quit", "exit"),
    ]),
]


def _help_fragments():
    mode = state.get("mode", "auto")
    fragments = [("", "\n")]  # breathing room under the title

    for section, rows in _HELP_SECTIONS:
        fragments.append(("class:label bold", f" {section}\n"))

        for entry in rows:
            # A bare string is a note line - dim, indented, no column.
            if isinstance(entry, str):
                fragments.append(
                    ("class:footer", f"   {entry}\n" if entry else "\n")
                )
                continue

            key, description = entry

            if key == "(HOME)":
                description = _HOME_BY_MODE.get(mode, _HOME_BY_MODE["auto"])
            elif key == "/mode":
                description = f"auto | manual | open   (now: {mode})"

            style = "class:key" if key.startswith("(") else "class:agent"
            # Pad to the column, but never glue a long command straight
            # onto its description.
            fragments.append((style, f"   {key:<15}"))
            fragments.append(
                ("class:text", f" {description}\n" if description else "\n")
            )

        fragments.append(("", "\n"))

    note = state.get("controls")

    if note:
        fragments.extend(_keyed(f" {note}", "class:footer"))
        fragments.append(("", "\n"))

    return fragments
