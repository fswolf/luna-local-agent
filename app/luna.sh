#!/usr/bin/env bash
# Luna, download and go (Linux and macOS). Nothing to set up first: the
# first run fetches uv (a small tool from astral.sh) into Luna's own folder,
# uv fetches a private Python 3.12, and app/bootstrap.py does the rest in a
# setup window. Nothing is installed system-wide and nothing asks for a
# password. Later runs start her straight away.
#
#   app/luna.sh            start Luna (setting her up first if needed)
#   app/luna.sh --setup    run the setup again (repair)
set -u
root="$(cd "$(dirname "$(realpath "$0" 2>/dev/null || echo "$0")")/.." && pwd)"

if [ "$(uname -s)" = Darwin ]; then
    data="$HOME/Library/Application Support/Luna"
else
    data="${XDG_DATA_HOME:-$HOME/.local/share}/luna"
fi
mkdir -p "$data"
# uv keeps its Python and its downloads in Luna's folder too, never anywhere else
export UV_PYTHON_INSTALL_DIR="$data/python" UV_CACHE_DIR="$data/cache" UV_PYTHON_PREFERENCE=only-managed

say() {
    # a terminal shows it; double-clicked from the app menu, a notification does
    echo "$1"
    if [ ! -t 1 ] && command -v notify-send >/dev/null 2>&1; then
        notify-send -i "$root/web/luna-logo.png" Luna "$1" 2>/dev/null || true
    fi
}
stop() {
    say "Luna couldn't start: $1"
    echo "  (log: $data/launcher.log)"
    if [ "$(uname -s)" = Darwin ] && [ -t 0 ]; then read -r -p "Press Enter to close." _; fi
    exit 1
}
exec 3>>"$data/launcher.log"

uv="$data/uv/uv"
if [ ! -x "$uv" ]; then
    say "Getting Luna ready for the first time (a minute or two)..."
    arch="$(uname -m)"
    case "$arch" in arm64|aarch64) arch=aarch64 ;; x86_64|amd64) arch=x86_64 ;; *) stop "this computer's processor ($arch) isn't supported yet" ;; esac
    if [ "$(uname -s)" = Darwin ]; then target="$arch-apple-darwin"; else target="$arch-unknown-linux-gnu"; fi
    url="https://github.com/astral-sh/uv/releases/latest/download/uv-$target.tar.gz"
    tmp="$data/uv.tmp"
    rm -rf "$tmp" && mkdir -p "$tmp"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url" 2>&3 | tar -xz -C "$tmp" --strip-components=1 2>&3
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$url" 2>&3 | tar -xz -C "$tmp" --strip-components=1 2>&3
    else
        stop "it needs curl or wget to download its Python"
    fi
    [ -x "$tmp/uv" ] || stop "couldn't download uv from $url (no internet?)"
    rm -rf "$data/uv" && mv "$tmp" "$data/uv"
fi

venv="$data/venv"
if [ ! -x "$venv/bin/python" ]; then
    say "Getting Luna's own Python (first run only)..."
    rm -rf "$venv"                     # half-made by a run that was stopped
    "$uv" venv --quiet --python 3.12 --seed "$venv" >&3 2>&3 || stop "couldn't make her Python (no internet?)"
fi

case " $* " in
    *" --no-window "*) exec "$venv/bin/python" "$root/app/bootstrap.py" "$@" ;;
esac
# On its own: closing the terminal (or macOS's Terminal window) mustn't stop a setup halfway
nohup "$venv/bin/python" "$root/app/bootstrap.py" "$@" >>"$data/launcher.log" 2>&1 </dev/null &
[ -t 1 ] && echo "Luna's starting - her window opens in a moment, and this one can close."
exit 0
