#!/bin/bash
# macOS: double-click to start Luna (the first time: right-click > Open,
# since it isn't from the App Store). This window can close once she's up.
exec "$(dirname "$0")/luna.sh" "$@"
