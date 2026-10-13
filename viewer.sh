#!/usr/bin/env bash
# The portrait on its own, no Luna - for trying models, gestures and the
# hologram. Opens in your browser; everything is picked in the page.
cd "$(dirname "$(realpath "$0")")" || exit 1

for py in "$(python3 -c 'import json;print(json.load(open("install.json")).get("venv_python",""))' 2>/dev/null)" \
          "$VIRTUAL_ENV/bin/python" ~/ai-voice-venv/bin/python ./ai-voice-venv/bin/python ./venv/bin/python ./.venv/bin/python; do
    if [ -n "$py" ] && [ -x "$py" ]; then
        exec "$py" portrait/viewer/view.py
    fi
done

exec python3 portrait/viewer/view.py
