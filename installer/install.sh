#!/usr/bin/env bash
# Install Luna on Linux or macOS:   ./installer/install.sh   [--yes] [options]
# Finds a suitable Python (3.10-3.13, 3.12 preferred), offers to install
# one if there isn't, then hands over to installer/install.py.
set -euo pipefail
cd "$(dirname "$0")/.."

pick() {
    for v in 3.12 3.11 3.13 3.10; do
        command -v "python$v" >/dev/null 2>&1 && { echo "python$v"; return; }
    done
    if command -v python3 >/dev/null 2>&1 &&
       python3 -c 'import sys; sys.exit(not (3,10) <= sys.version_info[:2] <= (3,13))'; then
        echo python3
    fi
}

PY=$(pick)
if [ -z "$PY" ]; then
    echo "Luna needs Python 3.10-3.13 (3.12 is best) and none was found."
    if command -v dnf >/dev/null; then cmd="sudo dnf install -y python3.12 python3.12-devel"
    elif command -v apt-get >/dev/null; then cmd="sudo apt-get install -y python3 python3-venv python3-dev"
    elif command -v pacman >/dev/null; then cmd="sudo pacman -S --needed python"
    elif command -v brew >/dev/null; then cmd="brew install python@3.12"
    else echo "Install Python 3.12 and run this again."; exit 1; fi
    read -r -p "Run: $cmd ? [Y/n] " yn
    case "${yn:-y}" in [Yy]*) $cmd ;; *) exit 1 ;; esac
    PY=$(pick)
    [ -n "$PY" ] || { echo "Still no suitable Python - install 3.12 and run this again."; exit 1; }
fi

exec "$PY" installer/install.py "$@"
