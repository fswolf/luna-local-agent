"""Every /command typed at the desk, one module per area.

    app        /clear /keys /mode /scroll /mouse /log /help
    reminders  /reminders /cancel /alarms /alarm /snooze /when /repair
    settings   /settings /preset /set /tools /tooltest /context /allow /mcp /plugins
    voice      /look /mic /voice /barge /wake
    life       /mood /coffee /read /situation
    portrait   /monitor /holo /outfit /lights /portrait ...
    memory     /facts /thoughts /memory /reflect /lessons /skills /projects /knowledge /episodes
    people     /camera /presence /people
    patches    /good /fix /examples (examples for her patches)
    plugins    /<plugin name> ... (last, so a core command always wins)

Each module has handle(text) -> True when the text was one of its
commands. main.handle_input asks them in turn; anything none of them takes
is a message for her.

They were one 1,400-line function in main.py. That shape had a trap in
it: a module imported anywhere inside the function was local to all of it,
and /settings crashed on a variable the /camera branch had shadowed.
"""
from types import SimpleNamespace

# What main.py knows that the commands need: set once, by setup().
ctx = SimpleNamespace(model=None, socket_path=None)


def setup(model, socket_path=None):
    ctx.model = model
    ctx.socket_path = socket_path


def handle(text):
    """True if text was a command (it has run). Never for a plain message."""
    from . import app, life, memory, patches, people, plugins, portrait, reminders, settings, voice

    for area in (app, reminders, settings, voice, life, portrait, memory, people, patches, plugins):
        if area.handle(text):
            return True
    return False
