"""The app itself: /clear, /keys, /mode, /scroll, /mouse, /log, /help.

Part of the commands package; see commands/__init__.py.
"""
import os

import config
from core import history
from core import logbook
from web import portrait_window
from voice import ptt
import ui

from . import ctx


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text == "/clear":
        ui.clear()
        history.clear()
        ui.render()
        return True

    if text == "/keys":
        ui.add_message(
            "system",
            "socket={} | session={} | hotkey=HOME (in-window)".format(
                ctx.socket_path or "none",
                os.environ.get("XDG_SESSION_TYPE", "?"),
            ),
        )
        return True

    if text.startswith("/mode"):
        parts = text.split()

        if len(parts) == 1:
            ui.add_message(
                "system",
                f"Mode: {ptt.mode()}. "
                "auto = HOME starts, silence stops. "
                "manual = HOME starts, HOME stops. "
                "open = hands free, mic stays armed. "
                "Change with /mode <name>.",
            )
            return True

        applied = ptt.set_mode(parts[1])

        ui.add_message(
            "system",
            f"Mode: {applied}" if applied
            else f"Unknown mode {parts[1]!r} - use auto, manual or open.",
        )
        return True

    if text == "/scroll":
        ui.add_message("system", ui.scroll_report())
        return True

    if text.startswith("/mouse"):
        argument = text[6:].strip().lower()
        wanted = {"on": True, "true": True, "yes": True,
                  "off": False, "false": False, "no": False}.get(argument)

        on = ui.toggle_mouse(wanted)

        try:
            config.save_setting("ui.mouse", on)
            saved = " (saved)"
        except Exception:
            saved = ""

        ui.add_message(
            "system",
            ("Mouse capture on - the wheel scrolls the conversation. Hold "
             "Shift to select text." if on else
             "Mouse capture off - select and copy normally; PgUp/PgDn "
             "scroll.") + saved,
        )
        return True

    if text.startswith("/log stderr"):
        # what libraries printed past Python (OpenCV, ALSA, a browser...),
        # caught in a file so it doesn't scribble on the screen (ui/app.py)
        from ui import app as ui_app

        where = ui_app.stderr_path()
        try:
            with open(where, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()[-40:]
        except OSError:
            lines = ["(nothing caught yet)"]
        ui.add_message("system", "{}\n{}".format(where, "\n".join("  " + l[:300] for l in lines)))
        return True

    if text.startswith("/log"):
        count = text[4:].strip()
        count = int(count) if count.isdigit() else 20

        lines = logbook.tail(min(count, 200))

        ui.add_message(
            "system",
            "{}\n{}".format(logbook.path(), "\n".join("  " + l for l in lines)),
        )
        return True

    if text == "/help":
        if config.MONITOR_ENABLED:
            from web import help_web

            portrait_window.quiet_open(help_web.url())
            ui.add_message("system", f"Help: {help_web.url()} (every command and key). "
                           f"Mode is {ptt.mode()} - /mode auto|manual|open to change it.")
        else:
            ui.add_message("system", "The help page needs the live monitor (monitor.enabled). "
                           f"Mode is {ptt.mode()} - /mode auto|manual|open; docs/controls.md has every key.")
        return True

    return False
