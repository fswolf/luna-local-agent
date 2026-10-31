"""Where she looks: the window or point on screen her eyes follow.

Part of the web package; web/livefeed.py is the front door.
"""
import json
import os
import re
import time
from web import livefeed


# ---------------------------------------------------------------------------
# Where the portrait should look
#
# On Hyprland the portrait window and Luna's terminal both have a place
# on screen, so the portrait can turn towards the conversation instead
# of staring at the middle of its own window. The direction goes out as
# a "gaze" event: x and y from -1 to 1, x towards the right of the
# screen, y up. Anywhere else (another compositor, OBS, the terminal on
# another workspace) it sends {"none": true} and the portrait looks
# ahead, as it always did.
# ---------------------------------------------------------------------------
# How far away, in screen pixels, counts as "as far to the side as she
# can look". Roughly a monitor's width from the portrait.
_GAZE_REACH = 1100.0


def _own_pids():
    pids, pid = set(), os.getpid()

    for _ in range(12):
        if pid <= 1 or pid in pids:
            break

        pids.add(pid)

        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break

    return pids


def gaze_target():
    """{"x", "y"} from the portrait window towards Luna's terminal, or
    None when either can't be found."""
    import shutil
    import subprocess

    if not shutil.which("hyprctl"):
        return None

    try:
        out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True,
                             text=True, timeout=2)
        clients = json.loads(out.stdout) if out.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return None

    ours = _own_pids()
    terminal = next((c for c in clients if c.get("pid") in ours), None)
    # The portrait page's <title> is "Luna"; Chromium's --app window
    # takes the page title as its own.
    # Firefox and friends append their own name: "Luna — Mozilla Firefox".
    portrait = next((c for c in clients if c is not terminal
                     and re.match(r"^Luna(\s+[-—–]\s+.*)?$", str(c.get("title", "")).strip())),
                    None)

    if not terminal or not portrait:
        return None

    if (terminal.get("workspace") or {}).get("id") != (portrait.get("workspace") or {}).get("id"):
        return None  # she can't see it from here

    try:
        (tx, ty), (tw, th) = terminal["at"], terminal["size"]
        (px, py), (pw, ph) = portrait["at"], portrait["size"]
    except (KeyError, TypeError, ValueError):
        return None

    # Her face sits in the upper third of the window; the conversation
    # is wherever the terminal's middle is.
    dx = (tx + tw / 2) - (px + pw / 2)
    dy = (ty + th / 2) - (py + ph * 0.3)
    clamp = lambda v: max(-1.0, min(1.0, v))

    return {"x": round(clamp(dx / _GAZE_REACH), 3), "y": round(clamp(-dy / _GAZE_REACH), 3)}


def _gaze_loop():
    """Twice a second while a page is open: tell the portrait where the
    terminal is, when that changes. Costs nothing with no page open."""
    last = object()

    while True:
        time.sleep(0.5)

        if not livefeed._subs:
            last = object()  # a page that opens later gets a fresh answer
            continue

        from senses import presence

        # Someone in front of the webcam: look at them. Otherwise at the
        # terminal, where the conversation is.
        target = presence.gaze() or gaze_target()

        if target is None:
            if last is not None:
                livefeed.emit("gaze", none=True)
                last = None
            continue

        if (not isinstance(last, dict) or abs(target["x"] - last["x"]) > 0.02
                or abs(target["y"] - last["y"]) > 0.02):
            livefeed.emit("gaze", **target)
            last = target
