"""Full-screen TUI built on prompt_toolkit.

Replaces the old "clear the screen and print()" dashboard. Three things
that bought us:

  * No flicker. prompt_toolkit diffs the screen and redraws only what
    changed, instead of wiping and repainting every frame.
  * Keys work while this window is focused - HOME for push-to-talk, ESC
    to quit - because the app reads keys as they arrive rather than
    blocking in input() waiting for a newline. No evdev, no compositor
    bind, no permissions, same behaviour on Linux/macOS/Windows.
  * Real panels, and a conversation you can scroll back through.

Public API is unchanged for callers: set_status, add_message, init,
set_controls, set_voice_server. Instead of ui.prompt() in a loop, main
calls ui.run(on_submit=...) once and the app owns the main thread.

The package, one job per file:

  shared.py             the conversation, the status fields, where the view is
  messages.py           what the rest of Luna calls: add_message, set_status...
  text.py               widths, wrapping, frames
  conversation_pane.py  the conversation pane and the status bar
  help.py               the help pane
  tools_pane.py         the tools pane: switches, groups, permissions
  approval.py           the permission popup (ask_approval)
  app.py                the application itself: style, keys, run(), stop()

A submodule never takes the name of something ui exports: importing
ui.conversation (a module) would replace ui.conversation (the list).
"""
from .shared import conversation, state, view  # noqa: F401
from .messages import (  # noqa: F401
    add_message, begin_message, clear, drop_empty_message, end_message, extend_message, init,
    mouse_enabled, render, replace_message, set_controls, set_memory, set_mode, set_model, set_mood,
    set_status, set_voice, set_voice_server, toggle_mouse,
)
from .approval import approving, ask_approval  # noqa: F401
from .app import run, scroll_report, stop  # noqa: F401
