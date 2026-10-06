#!/usr/bin/env bash
# Open her thoughts in your browser - on Luna's own server if she's
# running (http://127.0.0.1:8792/thoughts/), otherwise one is started
# that also serves her memory, the live monitor and the portrait.
# The viewer still runs entirely on its own: python thought-viewer/viewer.py
cd "$(dirname "$(realpath "$0")")/.." || exit 1

if [ -z "$VIRTUAL_ENV" ]; then
    for venv in ~/ai-voice-venv ./ai-voice-venv ./venv ./.venv; do
        if [ -f "$venv/bin/activate" ]; then
            # shellcheck disable=SC1090
            source "$venv/bin/activate"
            break
        fi
    done
fi

exec python3 livefeed.py --open thoughts "$@"
