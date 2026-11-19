#!/usr/bin/env bash
# Luna's music listener, on her server (or the same PC): server/music/listen.py.
#
#   server/music/install.sh              venv + model + a systemd service that starts on boot
#   server/music/install.sh --no-service venv + model only; run it yourself (shown at the end)
#   server/music/install.sh --port 8795  another port
#   server/music/install.sh remove       stop and remove the service (keeps the venv and model)
#
# Everything goes in ~/.local/share/luna-listen (venv, model), not the repo.
# The style model is MTG's Discogs-EffNet, CC BY-NC-SA 4.0: personal and
# open-source use only, never sold. Without it the listener still finds the
# tempo and beat. Needs python3 with venv; sudo only for the systemd service.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${LISTEN_HOME:-$HOME/.local/share/luna-listen}"
VENV="$HOME_DIR/venv" MODELS="$HOME_DIR/models"
PORT=8795 SERVICE=1 UNIT=/etc/systemd/system/luna-listen.service
say() { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
stop() { printf '\033[1;31mStopped:\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --no-service) SERVICE=0 ;;
        --port) PORT="$2"; shift ;;
        remove)
            sudo systemctl disable --now luna-listen 2>/dev/null || true
            sudo rm -f "$UNIT" && sudo systemctl daemon-reload
            say "Service removed. The venv and model are still in $HOME_DIR (rm -r it to free the space)."
            exit 0 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) stop "unknown option: $1 (try --help)" ;;
    esac
    shift
done

command -v python3 >/dev/null || stop "python3 isn't installed (Debian: sudo apt install python3 python3-venv)"
python3 -c 'import venv, ensurepip' 2>/dev/null || stop "python3's venv is missing (Debian: sudo apt install python3-venv)"
mkdir -p "$MODELS"

say "Python packages (Essentia, onnxruntime, numpy) in $VENV"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q essentia onnxruntime numpy || stop "pip couldn't install them (Essentia has wheels for Linux x86_64 and Python 3.9-3.13)"

say "The style model (MTG Discogs-EffNet, CC BY-NC-SA 4.0)"
get() {   # get FILE URL...  (first one that works)
    local f="$MODELS/$1"; shift
    [ -s "$f" ] && { echo "    have $(basename "$f")"; return 0; }
    for u in "$@"; do
        if curl -fsSL --retry 2 -o "$f.part" "$u"; then mv "$f.part" "$f"; echo "    got $(basename "$f")"; return 0; fi
    done
    rm -f "$f.part"; return 1
}
MTG=https://essentia.upf.edu/models HF=https://huggingface.co/Heyian/discogs-effnet-onnx/resolve/main
if get discogs-effnet-bsdynamic-1.onnx "$MTG/feature-extractors/discogs-effnet/discogs-effnet-bsdynamic-1.onnx" \
                                       "$MTG/music-style-classification/discogs-effnet/discogs-effnet-bsdynamic-1.onnx" \
                                       "$HF/discogs-effnet-bsdynamic-1.onnx" \
   && get genre_discogs400-discogs-effnet-1.json "$MTG/classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.json" \
                                                 "$HF/genre_discogs400-discogs-effnet-1.json"; then
    :
else
    echo "    couldn't download it: she'll still hear the tempo and beat, not the style. Run this again later."
fi

say "Self-test: a made-up 128 BPM beat"
"$VENV/bin/python" - "$HERE" "$MODELS" <<'PY'
import io, sys, wave
import numpy as np
sys.path.insert(0, sys.argv[1])
import listen
listen.load_model(sys.argv[2])
rate = 22050; x = np.zeros(rate * 8)
for b in np.arange(0.2, 8, 60 / 128):
    i = int(b * rate); n = int(0.12 * rate); t = np.arange(n) / rate
    x[i:i + n] += 0.9 * np.sin(2 * np.pi * (50 + 100 * np.exp(-t * 30)) * t) * np.exp(-t * 20)
buf = io.BytesIO()
with wave.open(buf, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes((x * 20000).astype("<i2").tobytes())
r = listen.listen(buf.getvalue())
print(f"    tempo {r['bpm']} BPM (should be ~128), style model {'loaded' if r['model'] else 'missing'}")
if not 120 < r["bpm"] < 136:
    sys.exit("    the tempo is off: something's wrong with Essentia here")
PY

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-this-machine}"
RUN="$VENV/bin/python $HERE/listen.py --port $PORT"
if [ "$SERVICE" = 1 ] && command -v systemctl >/dev/null; then
    say "A systemd service, luna-listen (asks for sudo)"
    sudo tee "$UNIT" >/dev/null <<UNITEOF
[Unit]
Description=Luna's music listener (server/music/listen.py)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
Environment=LISTEN_HOME=$HOME_DIR
ExecStart=$RUN
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now luna-listen
    sleep 2
    if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null; then say "Running, and it starts on boot."
    else echo "    it didn't answer yet: sudo journalctl -u luna-listen -n 30"; fi
else
    say "Run it yourself (or under screen):"
    echo "    $RUN"
fi
say "Done. In Luna:  /set music.url http://$IP:$PORT"
echo "    (a firewall on this machine needs port $PORT open to your desktop)"
