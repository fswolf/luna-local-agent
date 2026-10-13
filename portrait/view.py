#!/usr/bin/env python3
"""The portrait on its own, no Luna: for trying models and gestures.
./viewer.sh runs this. Everything else (model, crop, hologram, demo) is
picked in the page's panel. Port 8793, or LUNA_VIEW_PORT; it runs
beside Luna fine. Ctrl+C stops it."""
import os
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

config.MONITOR_ENABLED = True
config.MONITOR_PORT = int(os.environ.get("LUNA_VIEW_PORT", 8793))

import livefeed  # noqa: E402

if not livefeed.start():
    sys.exit(f"couldn't serve on port {config.MONITOR_PORT} - is a viewer already open? "
             "(LUNA_VIEW_PORT=8794 ./viewer.sh for another)")

address = f"{livefeed.url()}/portrait/?debug=1"
print(f"portrait viewer: {address}  (Ctrl+C stops)")
webbrowser.open(address)

try:
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    pass
