import warnings
import os
import sys

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import requests
import threading

import config
from config import AGENT_NAME, VOICE, TTS_URL, LM_URL, LLM_BACKEND
from voice.speech import load_models
from input import start_keyboard
from core import assistant
from core import control
from core import history
from core import interrupts
from core import lmstudio
from core import logbook
from mind import mood
import plugins
from voice import ptt
from life import reminders
from voice import speech
from core import timeutil
from core import transcript
import ui
from senses import vision
from voice import wakeword


def shutdown(code=0):
    """os._exit skips atexit, so every exit path comes through here."""
    control.cleanup()

    # The portrait window is its own process; MCP servers end when their
    # pipes close, but are asked nicely first.
    try:
        from web import portrait_window

        portrait_window.close()
    except Exception:
        pass
    try:
        from core import mcpclient

        mcpclient.stop()
    except Exception:
        pass

    os._exit(code)


# -------------------------
# Startup
# -------------------------
logbook.start()


def _log_crash(kind, value, tb):
    """An uncaught error goes to the log file as well as the console, so a
    crash at startup (where the console window may close) can be read."""
    try:
        import traceback
        logbook.error("crash", "uncaught %s: %s\n%s", kind.__name__, value,
                      "".join(traceback.format_exception(kind, value, tb)))
    except Exception:
        pass
    sys.__excepthook__(kind, value, tb)


sys.excepthook = _log_crash

if transcript.trim():
    logbook.info("transcript", "trimmed past the size cap")

history.load()
reminders.load()

# Imported now, started later - a plugin needs the model name, and
# loading early means a broken one is reported at startup rather than
# the first time someone types its name.
plugins.load()

MODEL = lmstudio.probe()

if not MODEL:
    print(
        f"\nCouldn't reach a model server at {LM_URL}\n"
        "Either open LM Studio, load a model and start its local server "
        "(Developer tab), or start llama.cpp with llama/start.sh.\n"
        if LLM_BACKEND != "llama" else
        f"\nllama-server isn't answering at {LM_URL}\n"
        "Start it with llama/start.sh, or set llm.backend to auto in "
        "config.json to fall back to LM Studio.\n"
    )
    raise SystemExit(1)


def _load_speech():
    """Whisper, Silero and the wake word, off the startup path.

    These take several seconds between them, and they used to run
    before the TUI was drawn - so every launch started with a bare
    terminal saying "Loading models..." while nothing was usable.
    Loading them behind the interface means you can read the
    conversation, scroll, and type immediately; only voice has to wait,
    and it says so if you try it early.
    """
    try:
        load_models()
        ui.set_status("Idle")
        logbook.info("startup", "speech models ready | tts=%s", speech.server_label())

        from senses import voices

        voices.warm_up()      # the speaker model, if anyone has voice prints

        # This check belongs here, not on the startup path. load_models()
        # is what probes the TTS server, and while that was synchronous
        # the caller could read the result immediately. Moving it to a
        # worker meant main.py was asking "is the server up?" a
        # millisecond after starting the thread that finds out - so a
        # perfectly healthy server reported itself offline, with an
        # empty reason, because nothing had looked yet.
        if not speech.tts_ok:
            ui.add_message(
                "system",
                f"No TTS server answering at {TTS_URL} - start one "
                "(kokoro-reader's kokoro_server.py by default) or she'll "
                f"stay silent.{f' ({speech.tts_error})' if speech.tts_error else ''}",
            )

        if wakeword.enabled() and not wakeword.load():
            ui.add_message("system", f"Wake word unavailable: {wakeword.label()}")
    except Exception as e:
        logbook.exception("startup", "speech models failed to load")
        ui.add_message("system", f"Speech models failed to load: {e}")
        ui.set_status("No voice")


threading.Thread(target=_load_speech, daemon=True).start()

ui.init(
    agent_name=AGENT_NAME,
    model=MODEL,
    voice=VOICE,
    voice_server=speech.server_label(),
)

# The Memory row used to say "Loaded" unconditionally. Now it says which
# backend is live and what's in it - and asking runs the json->sqlite
# changeover at startup rather than on the first turn.
from mind import longterm
ui.set_memory(longterm.status())

# Opening mood comes from the clock - 6am and 9pm are not the same
# person. Everything after this is drift off that.
mood.start()

# Her knowledge base: index the folders in the background.
try:
    from mind import knowledge

    knowledge.start()
except Exception as e:
    logbook.warn("knowledge", "couldn't start: %s", e)

from web import livefeed  # noqa: E402

livefeed.start()

# Seed the on-screen conversation with what was loaded from disk, so
# past turns are visible right away instead of starting on a blank screen.
for msg in history.get_messages():
    speaker = "user" if msg["role"] == "user" else AGENT_NAME.lower()
    ui.add_message(speaker, msg["content"])

# Whatever was chosen last time - the setting exists so the preference
# survives a restart, not just the session.
ui.toggle_mouse(config.UI_MOUSE)

ui.set_mode(ptt.mode())
ui.set_status("Loading speech...")
ui.set_model(lmstudio.label())

# Keep the header honest between turns, so an unloaded model shows up
# straight away rather than on the next thing you say.
lmstudio.watch()

# -------------------------
# Input paths:
#   * the TUI itself - HOME while this window is focused, everywhere
#   * control socket - optional, for scripting or a compositor bind
#   * evdev hotkey   - HOME from any window, X11/TTY only
# -------------------------
socket_path = control.start(
    MODEL,
    {
        "ptt": ptt.toggle,
        "stop": ptt.stop,
        "quit": lambda _model: shutdown(),
    },
)

threading.Thread(target=start_keyboard, args=(MODEL,), daemon=True).start()
threading.Thread(target=reminders.run_scanner, args=(MODEL,), daemon=True).start()

# Optional add-ons from plugins/. Anything switched on comes back up
# here, and anything that failed says so - "why isn't she answering
# chat" should be answerable from the first screen rather than by
# remembering whether you turned it on.
for _line in plugins.start_enabled(MODEL):
    ui.add_message("system", _line)

# Tools from MCP servers in config.json. Connecting can take a few
# seconds per server (npx/uvx may download on first run), so it happens
# on its own thread; tools appear in the pane as each server answers.
def _start_mcp():
    from core import mcpclient

    for _l in mcpclient.start():
        ui.add_message("system", _l)


threading.Thread(target=_start_mcp, daemon=True, name="mcp-start").start()

# Lessons, session notes and fact cleanup while she's idle - and first,
# notes on the last session, so she can pick up where it left off.
from mind import reflect  # noqa: E402
from life import touches  # noqa: E402

reflect.start(MODEL, show=lambda line: ui.add_message("system", line))
touches.start(MODEL)          # the portrait's touches, answered out loud (life/touches.py)

from life import coffee  # noqa: E402

coffee.start()                # her morning coffee (life/coffee.py), on the portrait

from life import reading  # noqa: E402

reading.start()               # she reads while you're quiet (life/reading.py), on the portrait

# Relay stations (web/station.py): an old phone or tablet in another room,
# when switched on in the settings
from web import station  # noqa: E402

if config.STATION_ENABLED:
    _ok, _said = station.start()
    if not _ok:
        logbook.warn("station", "relay stations: %s", _said)

# The webcam watching for someone in front of it (senses/presence.py): greets on
# arrival, looks at you, keeps quiet in an empty room.
from senses import presence  # noqa: E402

presence.set_model(MODEL)

if getattr(config, "PRESENCE_ENABLED", False) and not presence.start():
    ui.add_message("system", "Presence didn't start: " + " ".join(presence.status()))

# The face check (senses/facecheck.py, people.face_check): start the face models
# loading now, so the first typed turn doesn't find them missing.
from senses import facecheck  # noqa: E402

facecheck.warm()


# -------------------------
# Turn handling
# -------------------------
def _process(text, stop):
    """One typed turn. Runs on a worker so the TUI stays responsive
    while the model thinks and Luna speaks. `stop` was opened when you
    pressed Enter (interrupts), so a HOME pressed while it waits for the
    last reply to finish still cancels it."""
    try:
        with interrupts.using(stop):        # closed however this ends
            from senses import people

            speaker = people.typed_speaker()     # you, unless the face check sees someone else
            ui.add_message("user", f"[{speaker}] {text}" if speaker else text)
            assistant.respond(text, MODEL, source="typed", speaker=speaker)
        ui.set_status("Idle")
        mood.note_turn()
    except Exception as e:
        # Without this, an LM Studio error (context overflow, bad param,
        # connection drop, etc.) would kill the worker silently instead
        # of just this one turn.
        logbook.exception("turn", "typed turn failed")
        ui.add_message("system", f"Error: {e}")
        ui.set_status("Idle")
        mood.note_error()




def handle_input(text):
    """Called on the UI thread - dispatch fast, never block here."""
    if text in ("/quit", "/exit"):
        ui.stop()
        return

    if firstrun.handle(text):           # the first-start questions (core/firstrun.py)
        return

    if commands.handle(text):           # every /command (commands/)
        return

    threading.Thread(target=_process, args=(text, interrupts.open("typed")), daemon=True).start()


from core import firstrun  # noqa: E402

firstrun.maybe_start()          # a fresh install: her name for you, pronouns, a preset

import commands  # noqa: E402

commands.setup(MODEL, socket_path)
ui.run(on_submit=handle_input, on_hotkey=lambda: ptt.toggle(MODEL))

shutdown()
