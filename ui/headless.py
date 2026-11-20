"""Luna without the terminal screen (./start.sh --web): the chat page is her
window instead.

Everything else stays as it is. The conversation, the status and a tool's
question still live in ui.shared, and the chat page (web/chat_web.py) shows
them and answers them. What the screen did is done here by a small stand-in:
a loop on the main thread that runs what's typed in the page, the same way
Enter does in the terminal.

Part of the ui package; see ui/__init__.py.
"""
import asyncio
import os
import sys
import threading
import time
from types import SimpleNamespace

from .shared import view

SIZE = SimpleNamespace(columns=100, rows=40)    # what wraps text where the screen would
DETACHED = bool(os.environ.get("LUNA_DETACHED"))   # started on her own by launch.py: no terminal
QUIT_AFTER = 5     # a window that closes sooner was handed to a browser already open


class _StandIn:
    """What the rest of Luna touches on view.app, with no screen behind it."""

    output = SimpleNamespace(get_size=lambda: SIZE)

    def invalidate(self):
        pass

    def exit(self):
        loop = view.loop
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)


def run_web(on_submit, on_hotkey=None, open_window=True):
    """Run until /quit, Ctrl+C or the chat window closing. on_hotkey: what
    HOME does (push to talk), for the chat page's mic button."""
    import config

    view.on_submit = on_submit
    view.on_hotkey = on_hotkey
    if not getattr(config, "MONITOR_ENABLED", True):
        print("--web needs the live monitor, which serves the chat page: set monitor.enabled "
              "to true in config.json.", file=sys.stderr)
        return
    from web import chat_web, livefeed

    if "chat" not in livefeed.PAGES:
        # the live monitor registers it once its port is open (livefeed.start)
        print(f"Her pages aren't being served, so there's no window to open: is port "
              f"{livefeed.port()} taken (another Luna running)? Her log says why.", file=sys.stderr)
        return

    view.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(view.loop)
    view.app = _StandIn()
    config.STARTED_UI[0] = True          # complaints go to the log, as with the screen up
    url = chat_web.url()
    window = chat_web.open_window() if open_window else None
    tray = _start_tray() if open_window and getattr(config, "MONITOR_TRAY", True) else None
    print(f"Luna is running in her window ({url}).", flush=True)
    if not DETACHED:
        print(("Closing the window quits her (with a tray icon, she stays there), so does /quit there or "
               "Ctrl+C here." if tray else "Closing the window quits her, so does /quit there or Ctrl+C here.")
              if window else "Ctrl+C here or /quit on the page quits her.", flush=True)
    if window is not None:
        threading.Thread(target=_watch, args=(window,), daemon=True, name="chat-window").start()
    try:
        view.loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        view.app = None
        loop, view.loop = view.loop, None
        loop.close()
        if window is not None and window.poll() is None:
            window.terminate()
        if tray is not None and tray.poll() is None:
            tray.terminate()


def _start_tray():
    """Her icon in the system tray (app/tray.py), a process of its own that
    talks to her pages. None when it couldn't start; it says why in its log."""
    import subprocess

    from web import livefeed

    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "tray.py")
    if not os.path.exists(script):
        return None
    try:
        from core import logbook

        log = open(os.path.join(os.path.dirname(logbook.path()), "tray.log"), "a", encoding="utf-8")
    except Exception:
        log = subprocess.DEVNULL
    flags = {"creationflags": 0x08000000} if os.name == "nt" else {"start_new_session": True}   # no console
    try:
        return subprocess.Popen([sys.executable, script, "--url", livefeed.url()], stdin=subprocess.DEVNULL,
                                stdout=log, stderr=log, **flags)
    except OSError:
        return None
    finally:
        if log is not subprocess.DEVNULL:
            log.close()                  # the tray has its own copy now


def _watch(window):
    """The window closing quits her, like any app's. One that closes at once
    was a hand-off to a browser already running: then she carries on."""
    started = time.monotonic()
    window.wait()
    if time.monotonic() - started < QUIT_AFTER:
        print("The window closed straight away (handed to a browser already open?): she's "
              "still running, and /quit on the page quits her.", flush=True)
        return
    from web import chat_web

    if chat_web.tray_up():
        # like any app with a tray icon: the window goes, she stays, Quit there ends her
        print("Her window closed: she's still running in the system tray.", flush=True)
        return
    stand_in = view.app
    if stand_in is not None:
        stand_in.exit()
