"""Opening a terminal window running a command - for the games' watch
windows (/zork watch, /realiti watch). A helper, not a plugin: the
leading underscore keeps the loader away.

Looks for kitty, foot, alacritty, wezterm, konsole, gnome-terminal or
xterm (kitty or Terminal.app on a Mac). A plugin's "terminal" setting,
e.g. "kitty" or "gnome-terminal --", picks one instead.
"""
import os
import shlex
import shutil
import subprocess
import sys


def command(inner, title, chosen=""):
    """argv that opens a window titled `title` running `inner`, or None."""
    chosen = str(chosen or "").strip()

    if chosen:
        from core.machine import split_command

        return split_command(chosen) + inner

    if sys.platform == "darwin":
        kitty = shutil.which("kitty") or "/Applications/kitty.app/Contents/MacOS/kitty"
        if os.path.exists(kitty):
            return [kitty, "--title", title] + inner
        script = " ".join(shlex.quote(a) for a in inner)
        return ["osascript", "-e", f'tell application "Terminal" to do script "{script}"',
                "-e", 'tell application "Terminal" to activate']

    styles = [("kitty", ["--title", title]), ("foot", ["--title", title]),
              ("alacritty", ["--title", title, "-e"]), ("wezterm", ["start", "--"]),
              ("konsole", ["-e"]), ("gnome-terminal", ["--title", title, "--"]),
              ("xterm", ["-T", title, "-e"])]

    for name, flags in styles:
        path = shutil.which(name)
        if path:
            return [path] + flags + inner

    return None


def open_window(inner, title, chosen="", plugin=""):
    """Open it. Returns a line for the user: what opened, or how to run
    it by hand when no terminal could be found."""
    argv = command(inner, title, chosen)

    if argv is None:
        return (f"{plugin}: no terminal found to open - run it yourself:\n  "
                + " ".join(shlex.quote(a) for a in inner)
                + f'\n  (or set "terminal" under plugins.{plugin} in config.json)')

    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        return f"{plugin}: couldn't open a terminal ({e})"

    return f"{plugin}: opened a window to watch in ({os.path.basename(argv[0])})"
