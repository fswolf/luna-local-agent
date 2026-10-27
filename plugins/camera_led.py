"""The webcam's light, where the camera lets software switch it.

A starting point for the camera hooks (on_camera_open / on_camera_close):
copy it and change the two marked functions for your own camera or OS.

Most webcams wire the light to the sensor: nothing turns it off, and
that's the honest signal for everyone else in the room. Some (many
Logitech ones) expose it on Linux as a V4L2 control. This plugin finds
it and sets it while she uses the camera:

    sudo dnf install v4l-utils          (apt install v4l-utils)
    v4l2-ctl -d /dev/video0 -l | grep -i led

    "plugins": { "camera_led": { "device": "/dev/video0", "control": "led1_mode",
                                 "while_open": 0, "after": 3 } }

    /camera_led on        off while she looks (0), back to auto (3) after
    /camera_led           what it found

led1_mode is usually 0 off, 1 on, 2 blink, 3 auto. No such control: the
plugin says so and doesn't start (a strip of tape over the light, not
the lens, works on every camera).

The same thing without a plugin: camera.before / camera.after in the
settings run any command around each open.
"""
import shutil
import subprocess
import sys

import config
from core import logbook

NAME = "camera_led"
SUMMARY = "switch the webcam's light while she looks (Linux, cameras with a V4L2 LED control)"

_state = {"running": False, "found": ""}


def settings():
    raw = config.plugin_settings(NAME) or {}
    return {"device": str(raw.get("device", "/dev/video0")),
            "control": str(raw.get("control", "")),
            "while_open": int(raw.get("while_open", 0)),
            "after": int(raw.get("after", 3))}


def _ctl(*args):
    """v4l2-ctl's output, or raises with a reason someone can act on."""
    done = subprocess.run(["v4l2-ctl", *args], capture_output=True, text=True, timeout=3)
    if done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout).strip()[:200] or f"v4l2-ctl exited {done.returncode}")
    return done.stdout


def _find_control(device, wanted=""):
    """The LED control's name on this camera, or ''."""
    names = [line.split()[0] for line in _ctl("-d", device, "-l").splitlines() if line.strip()]
    if wanted:
        return wanted if wanted in names else ""
    return next((n for n in names if "led" in n.lower()), "")


# --- the two functions to change for another camera or OS --------------------
def _light(device, value):
    s = settings()
    _ctl("-d", s["device"], "-c", f"{_state['found']}={value}")


def on_camera_open(device):
    _light(device, settings()["while_open"])


def on_camera_close(device):
    _light(device, settings()["after"])
# ------------------------------------------------------------------------------


def available():
    return sys.platform.startswith("linux") and shutil.which("v4l2-ctl") is not None


def why_unavailable():
    if not sys.platform.startswith("linux"):
        return "Linux only (Windows: the camera maker's app; macOS: the light can't be switched)"
    return "needs v4l2-ctl: sudo dnf install v4l-utils (or apt install v4l-utils)"


def start(model=None):
    s = settings()
    try:
        found = _find_control(s["device"], s["control"])
    except Exception as e:
        return False, f"couldn't ask {s['device']} for its controls: {e}"
    if not found:
        return False, (f"{s['device']} has no LED control{' called ' + s['control'] if s['control'] else ''}: "
                       "its light is wired to the sensor (tape over the light works)")
    _state["found"], _state["running"] = found, True
    logbook.info("camera_led", "using %s on %s", found, s["device"])
    return True, f"camera_led: {found} on {s['device']}, {s['while_open']} while she looks, {s['after']} after"


def stop():
    _state["running"] = False
    return True, "camera_led: off (the light does what the camera does by itself)"


def running():
    return _state["running"]


def status():
    if _state["running"]:
        s = settings()
        return f"camera_led: running, {_state['found']} on {s['device']}"
    return f"camera_led: off{' (' + why_unavailable() + ')' if not available() else ''}"
