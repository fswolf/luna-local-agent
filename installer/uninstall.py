"""Undo what installer/install.py added. Your data stays.

    python installer/uninstall.py [--yes]

Removes the launchers it made (the 'luna' command, the app-launcher
entry, the Start menu shortcut, luna.cmd / Luna.command), and - after
asking - the virtual environments it created inside this folder and the
kokoro-reader it cloned. Never touched: agent/ (memory, mood, lessons),
history/, reminders/, config.json, your models. Delete the folder
yourself if you want those gone too.
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "install.json")
YES = "--yes" in sys.argv or "-y" in sys.argv


def ask(q, default=False):
    if YES:
        return default
    a = input(f"{q} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not a else a.startswith("y")


def gone(path, what):
    try:
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            return
        print(f"  removed {what}: {path}")
    except OSError as e:
        print(f"  couldn't remove {path}: {e}")


def main():
    try:
        with open(STATE, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    cmd = s.get("command")
    if cmd and os.path.islink(cmd) and os.path.realpath(cmd).startswith(ROOT):
        gone(cmd, "the luna command")
    for key, what in (("desktop", "app launcher entry"), ("shortcut", "Start menu shortcut")):
        if s.get(key):
            gone(s[key], what)
    gone(os.path.join(ROOT, "luna.cmd"), "launcher")
    gone(os.path.join(ROOT, "Luna.command"), "launcher")

    v = s.get("venv")
    if v and os.path.realpath(v).startswith(ROOT + os.sep):
        if ask(f"Remove Luna's Python environment ({v}, a few GB)?", True):
            gone(v, "environment")
    elif v:
        print(f"  left alone: {v} (it was there before the installer)")

    k = s.get("kokoro_dir")
    if k and os.path.isdir(k) and s.get("voice", {}).get("mode") == "managed":
        if ask(f"Remove kokoro-reader ({k})? Other apps may use it.", False):
            gone(k, "kokoro-reader")

    gone(STATE, "install record")
    print("Done. Your memory, history and settings are still in", ROOT)


if __name__ == "__main__":
    main()
