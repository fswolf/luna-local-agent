#!/usr/bin/env bash
# The machine Luna's model runs on (a VM with the graphics card, or any box
# running llama-server on port 8080) at a glance, read-only: up, load, memory,
# disks, the GPU (busy, VRAM, temperatures, power), llama-server (up, model,
# context, busy slots), failed services, the music listener (luna-listen),
# GPU driver warnings, errors since boot.
# AMD graphics cards (sysfs); for NVIDIA, swap the GPU part for nvidia-smi.
# Needs SSH key login (BatchMode: fails instead of asking for a password).
VM=you@192.168.1.30          # change to yours

ssh -o BatchMode=yes -o ConnectTimeout=5 "$VM" 'bash -s' <<'EOF' || echo "Can't reach the VM over SSH (is it on, and does key login work?)"
echo "== $(hostname): up $(uptime -p | sed 's/^up //'), load $(cut -d' ' -f1-3 /proc/loadavg) on $(nproc) cores"
echo "== memory"; free -h | sed -n '1,3p'
echo "== disks"; df -h -x tmpfs -x devtmpfs -x squashfs -x overlay -x efivarfs 2>/dev/null

echo "== GPU"
found=0
for d in /sys/class/drm/card[0-9]*/device; do
    [ "$(cat "$d/vendor" 2>/dev/null)" = 0x1002 ] && [ -r "$d/mem_info_vram_total" ] || continue
    found=1
    used=$(( $(cat "$d/mem_info_vram_used") / 1048576 )); total=$(( $(cat "$d/mem_info_vram_total") / 1048576 ))
    echo "busy $(cat "$d/gpu_busy_percent" 2>/dev/null || echo ?)%, VRAM $used of $total MiB ($(( used * 100 / total ))%)"
    hw=$(ls -d "$d"/hwmon/hwmon* 2>/dev/null | head -1)
    if [ -n "$hw" ]; then
        line=""
        for t in "$hw"/temp*_input; do
            [ -r "$t" ] || continue
            label=$(cat "${t%_input}_label" 2>/dev/null || basename "${t%_input}")
            line="$line$label $(( $(cat "$t") / 1000 ))C, "
        done
        p=$(cat "$hw/power1_average" 2>/dev/null || cat "$hw/power1_input" 2>/dev/null)
        [ -n "$p" ] && line="${line}power $(( p / 1000000 )) W, "
        f=$(cat "$hw/fan1_input" 2>/dev/null)
        [ -n "$f" ] && line="${line}fan $f rpm, "
        [ -n "$line" ] && echo "${line%, }"
    fi
done
[ $found = 0 ] && echo "FAILED: no AMD GPU found (dropped off the bus, or not passed through?)"

echo "== llama-server (port 8080)"
if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health)" = 200 ]; then
    echo "up"
    command -v python3 >/dev/null || echo "(python3 isn't installed here: no model or slot details)"
    command -v python3 >/dev/null && python3 -c '
import json, os, sys
def load(s):
    try:
        return json.loads(s)
    except Exception:
        return None
p, s = load(sys.argv[1]), load(sys.argv[2])
if isinstance(p, dict):
    ctx = (p.get("default_generation_settings") or {}).get("n_ctx") or p.get("n_ctx") or "?"
    model = os.path.basename(str(p.get("model_path") or "?"))
    print("model %s, context %s" % (model, ctx))
if isinstance(s, list):
    busy = sum(1 for x in s if isinstance(x, dict) and x.get("is_processing"))
    print("slots: %d of %d busy" % (busy, len(s)))
' "$(curl -s -m 5 http://127.0.0.1:8080/props)" "$(curl -s -m 5 http://127.0.0.1:8080/slots)"
else
    echo "FAILED: llama-server isn't answering on 8080 (still loading, or its screen session ended)"
fi

echo "== failed services"; systemctl --failed --no-legend --plain 2>/dev/null | grep . || echo "none"
echo "== music service (luna-listen): $(systemctl is-active luna-listen 2>/dev/null || echo not installed)"
echo "== GPU driver warnings since boot"
journalctl -k -b -p warning --no-pager -o cat 2>/dev/null | grep -i amdgpu | tail -5 | grep . || echo "none (or the journal isn't readable as $(whoami))"
echo "== errors since boot, by count"; journalctl -b -p err --no-pager -o cat 2>/dev/null | sort | uniq -c | sort -rn | head -10 | grep . || echo "none (or the journal isn't readable as $(whoami))"
EOF
