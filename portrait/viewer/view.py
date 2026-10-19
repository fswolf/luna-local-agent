#!/usr/bin/env python3
"""The portrait on its own, no Luna: for trying models and gestures.
./viewer.sh runs this (portrait/viewer/view.py). Everything else (model, crop, hologram, demo) is
picked in the page's panel. Port 8793, or LUNA_VIEW_PORT; it runs
beside Luna fine. Ctrl+C stops it."""
import os
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config  # noqa: E402

config.MONITOR_ENABLED = True
config.MONITOR_PORT = int(os.environ.get("LUNA_VIEW_PORT", 8793))

import livefeed  # noqa: E402

if not livefeed.start():
    # Already running (a viewer left open, or Luna's own monitor on this port)?
    # Then just show it rather than failing.
    import urllib.request

    address = f"http://127.0.0.1:{config.MONITOR_PORT}/portrait/?debug=1"
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{config.MONITOR_PORT}/portrait/config.json", timeout=3)
    except Exception:
        sys.exit(f"couldn't serve on port {config.MONITOR_PORT} and nothing there answers as a portrait "
                 "(LUNA_VIEW_PORT=8794 ./viewer.sh for another port)")
    print(f"a viewer is already running: {address}")
    webbrowser.open(address)
    sys.exit(0)

address = f"{livefeed.url()}/portrait/?debug=1"
print(f"portrait viewer: {address}  (Ctrl+C stops)")
webbrowser.open(address)

try:
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    pass
