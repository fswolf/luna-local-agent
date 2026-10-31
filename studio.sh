#!/usr/bin/env bash
# The studio: Luna's portrait on its own, no Luna, with the control panel and the
# pose studio - for trying models, gestures, cards and the hologram. Opens in a
# window of its own (no address bar) and runs in the background: no terminal to
# keep open, and it stops by itself once its window is closed.
#   --tab   open it in your usual browser instead
#   --fg    keep it in this terminal (Ctrl+C stops it), to watch what it says
cd "$(dirname "$(realpath "$0" 2>/dev/null || echo "$0")")" || exit 1   # realpath: macOS 13+, else as given

python=python3
for py in "$(python3 -c 'import json;print(json.load(open("install.json")).get("venv_python",""))' 2>/dev/null)" \
          "$VIRTUAL_ENV/bin/python" ~/ai-voice-venv/bin/python ./ai-voice-venv/bin/python ./venv/bin/python ./.venv/bin/python; do
    if [ -n "$py" ] && [ -x "$py" ]; then
        python="$py"
        break
    fi
done

fg=0
args=()
for a in "$@"; do
    if [ "$a" = "--fg" ]; then fg=1; else args+=("$a"); fi
done
if [ "$fg" = 1 ]; then
    exec "$python" portrait/viewer/view.py "${args[@]}"
fi

log="${XDG_CACHE_HOME:-$HOME/.cache}/ai-voice/studio.log"
mkdir -p "$(dirname "$log")"
# added to, not replaced: a second run while one is open mustn't cut the first one's log short
if [ -f "$log" ] && [ "$(wc -c <"$log")" -gt 1000000 ]; then mv -f "$log" "$log.old"; fi
if command -v setsid >/dev/null; then
    setsid -f "$python" portrait/viewer/view.py "${args[@]}" >>"$log" 2>&1 </dev/null
else
    nohup "$python" portrait/viewer/view.py "${args[@]}" >>"$log" 2>&1 </dev/null &
fi
echo "Studio opening. It stops by itself when you close it. (what it says: $log)"
