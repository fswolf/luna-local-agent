#!/usr/bin/env bash
# Start Luna from anywhere - see launch.py. It starts her voice server
# too, if installer/install.py set one up, and stops it when she exits.
cd "$(dirname "$(realpath "$0")")" || exit 1

for py in "$(python3 -c 'import json;print(json.load(open("install.json")).get("venv_python",""))' 2>/dev/null)" \
          "$VIRTUAL_ENV/bin/python" ~/ai-voice-venv/bin/python ./ai-voice-venv/bin/python ./venv/bin/python ./.venv/bin/python; do
    if [ -n "$py" ] && [ -x "$py" ]; then
        exec "$py" launch.py "$@"
    fi
done

echo "No virtualenv found - run ./installer/install.sh first (trying system python3)." >&2
exec python3 launch.py "$@"
