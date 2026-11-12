#!/usr/bin/env bash
# Install Luna on Linux or macOS:   ./installer/install.sh   [--yes] [options]
# Finds a suitable Python (3.10-3.13, 3.12 preferred), offers to install
# one if there isn't, then hands over to installer/install.py.
#
# Distros that have moved on to 3.14 (Arch, CachyOS, Fedora 44) get 3.12
# from uv instead: a standalone Python in uv's own folder, no AUR build
# and nothing in the system replaced.
set -euo pipefail
cd "$(dirname "$0")/.."

YES=""
for a in "$@"; do [ "$a" = --yes ] || [ "$a" = -y ] && YES=1; done

pick() {
    for v in 3.12 3.11 3.13 3.10; do
        command -v "python$v" >/dev/null 2>&1 && { echo "python$v"; return; }
    done
    if command -v python3 >/dev/null 2>&1 &&
       python3 -c 'import sys; sys.exit(not (3,10) <= sys.version_info[:2] <= (3,13))'; then
        echo python3
        return
    fi
    # one uv already fetched, on an earlier run or by hand
    if command -v uv >/dev/null 2>&1; then
        env -u VIRTUAL_ENV uv python find --managed-python --no-project '>=3.10,<3.14' 2>/dev/null || true
    fi
}

# offer "command" -> asks (yes with --yes), then runs it. Everything it
# prints goes to stderr, so with_uv's answer (a path on stdout) stays clean.
offer() {
    local yn=y
    if [ -n "$YES" ]; then echo "Running: $1" >&2
    else read -r -p "Run: $1 ? [Y/n] " yn || return 1
    fi
    case "${yn:-y}" in [Yy]*) $1 >&2 ;; *) return 1 ;; esac
}

with_uv() {
    if ! command -v uv >/dev/null; then
        if command -v pacman >/dev/null; then offer "sudo pacman -S --needed uv" || return 1
        elif command -v dnf >/dev/null; then offer "sudo dnf install -y uv" || return 1
        else
            echo "Install uv (https://docs.astral.sh/uv/) or Python 3.12, then run this again." >&2
            return 1
        fi
    fi
    echo "This system's Python is too new for some of Luna's speech packages." >&2
    echo "uv can fetch a separate Python 3.12 for her, without touching the system's." >&2
    offer "uv python install 3.12" || return 1
    env -u VIRTUAL_ENV uv python find --managed-python --no-project 3.12
}

PY=$(pick)
if [ -z "$PY" ]; then
    echo "Luna needs Python 3.10-3.13 (3.12 is best) and none was found."
    if command -v brew >/dev/null; then
        offer "brew install python@3.12" || exit 1
    elif command -v dnf >/dev/null; then
        offer "sudo dnf install -y python3.12 python3.12-devel" || true
    elif command -v apt-get >/dev/null; then
        offer "sudo apt-get install -y python3 python3-venv python3-dev" || true
    fi
    PY=$(pick)
    # still nothing: the distro's own Python is 3.14 or newer (always so with pacman)
    [ -n "$PY" ] || PY=$(with_uv) || true
    [ -n "$PY" ] || { echo "Still no suitable Python - install 3.12 and run this again."; exit 1; }
fi

exec "$PY" installer/install.py "$@"
