#!/usr/bin/env python3
"""The studio: Luna's portrait on its own, no Luna, with the control panel and
the pose studio, for trying models, gestures, cards and the hologram.
./studio.sh runs this (portrait/viewer/view.py). Everything else (model, crop,
hologram, demo) is picked in the page.

It opens in a window of its own with no address bar, the way /portrait opens
hers (web/portrait_window.py, on a profile of its own). --tab, or a BROWSER
you've set, opens it in your browser instead. portrait.browser is used for the
window if it's set. Either way it stops by itself about twenty seconds after the
last studio page is closed (studio.sh and studio.cmd run it in the background, so
there's no terminal to close). Port 8793, or LUNA_VIEW_PORT; it runs beside Luna fine."""
import os
import shlex
import subprocess
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config  # noqa: E402

if sys.stdout is None:
    # Run without a console (pythonw.exe, from studio.cmd): what it says goes to
    # a log beside Luna's, like studio.sh's
    from core.logbook import LOG_DIR  # noqa: E402

    os.makedirs(LOG_DIR, exist_ok=True)
    log = os.path.join(LOG_DIR, "studio.log")
    if os.path.isfile(log) and os.path.getsize(log) > 1_000_000:   # kept small: the last run or so
        os.replace(log, log + ".old")
    sys.stdout = sys.stderr = open(log, "a", buffering=1, encoding="utf-8")

config.MONITOR_ENABLED = True
config.MONITOR_PORT = int(os.environ.get("LUNA_VIEW_PORT", 8793))

from web import livefeed, portrait_window  # noqa: E402

W, H = 1600, 960


def window(url):
    """Open the studio in a window of its own and return its process; or open
    it in the browser and return None."""
    if "--tab" in sys.argv[1:] or os.environ.get("BROWSER"):
        webbrowser.open(url)
        return None
    try:
        own = getattr(config, "PORTRAIT_BROWSER", "")
        cmd = (shlex.split(own.format(url=url, w=W, h=H)) if own
               else portrait_window.command(url, W, H, profile="luna-studio"))
    except (OSError, ValueError, KeyError) as e:
        print(f"couldn't set up a window for it ({e}): opening it in your browser")
        cmd = None
    if not cmd:
        portrait_window.quiet_open(url)
        return None
    try:
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        print(f"couldn't start {cmd[0]} ({e}): opening it in your browser")
        portrait_window.quiet_open(url)
        return None


if not livefeed.start():
    # Already running (a studio left open, or Luna's own monitor on this port)?
    # Then just show it rather than failing.
    import urllib.request

    address = f"http://127.0.0.1:{config.MONITOR_PORT}/portrait/?debug=1"
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{config.MONITOR_PORT}/portrait/config.json", timeout=3)
    except Exception:
        sys.exit(f"couldn't serve on port {config.MONITOR_PORT} and nothing there answers as a portrait "
                 "(LUNA_VIEW_PORT=8794 ./studio.sh for another port)")
    print(time.strftime("%Y-%m-%d %H:%M ") + f"the studio is already running: {address}", flush=True)
    window(address)
    sys.exit(0)

address = f"{livefeed.url()}/portrait/?debug=1"
proc = window(address)
print(time.strftime("%Y-%m-%d %H:%M ") + f"studio: {address}  (it stops by itself once its window or tab is closed, or Ctrl+C)",
      flush=True)

# It runs while a studio page is open, however it was opened: its own window, a
# tab, a browser that took the page over, a second window on the same studio.
# The page holds the live feed open, so "nobody watching" for a while means
# every page is closed (a reload is back within a second or two).
GRACE, FIRST = 20, 120
seen, gone = False, None
try:
    while True:
        time.sleep(1)
        now = time.monotonic()
        if livefeed.watching():
            seen, gone = True, None
            continue
        gone = gone or now
        if (seen and now - gone > GRACE) or (not seen and now - gone > FIRST):
            print(time.strftime("%Y-%m-%d %H:%M ") + ("no studio page open any more: stopped" if seen
                  else f"no page opened it in {FIRST} s: stopped"), flush=True)
            break
except KeyboardInterrupt:
    pass
if proc and proc.poll() is None:
    proc.terminate()
