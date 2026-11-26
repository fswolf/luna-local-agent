#!/usr/bin/env bash
# Updates a Debian or Ubuntu server's packages: lists what's waiting, then
# upgrades it all.
#
#   bash web-update.sh            list what's waiting, upgrade it all
#   bash web-update.sh --check    list only, change nothing
#
# Upgrading needs root, so run it yourself in a terminal: sudo asks for your
# password on the server. --check needs no root, so Luna can run that part.
# The list is from Debian's own daily refresh (apt-daily.timer).
#
# Upgrades only: nothing is removed (no autoremove, no full-upgrade), your
# config files are kept when a package ships a new one, and it never reboots.
# Afterwards: Apache and MariaDB checked, and whether a reboot is waiting.
WEB=you@192.168.1.10         # change to yours

check=0; [ "$1" = "--check" ] && check=1

read -r -d '' REMOTE <<'EOF'
echo "== $(hostname)"
list=$(apt list --upgradable 2>/dev/null | tail -n +2)
if [ -z "$list" ]; then
    echo "== nothing to upgrade"
    exit 0
fi
echo "== $(echo "$list" | wc -l) to upgrade ($(echo "$list" | grep -c -- '-security') of them security fixes):"
echo "$list" | awk -F'[/ ]' '{s = ($2 ~ /security/) ? "  (security)" : ""; print "  " $1 "  " $3 s}'

[ "$CHECK" = 1 ] && { echo "== check only: nothing changed"; exit 0; }
if [ -t 0 ]; then
    sudo env DEBIAN_FRONTEND=noninteractive apt-get update -q >/dev/null &&
    sudo env DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --with-new-pkgs \
        -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold \
        || { echo "FAILED: the upgrade stopped partway; run sudo apt-get upgrade on the server to see why"; exit 1; }
else
    echo "FAILED: upgrading needs root on the server, and there's no terminal here for sudo to ask in."
    echo "Run it yourself in a terminal, or use --check to only list what's waiting."
    exit 1
fi

echo "== after"
for s in apache2 mariadb; do
    systemctl list-unit-files "$s.service" --no-legend 2>/dev/null | grep -q . && echo "$s: $(systemctl is-active "$s")"
done
newest=$(ls /boot/vmlinuz-* 2>/dev/null | sed 's|.*/vmlinuz-||' | sort -V | tail -1)
if [ -e /run/reboot-required ] || { [ -n "$newest" ] && [ "$newest" != "$(uname -r)" ]; }; then
    echo "reboot waiting: running kernel $(uname -r)${newest:+, installed $newest} (sudo reboot when it suits you)"
else
    echo "no reboot needed"
fi
EOF

# in a terminal, -t gives sudo one to ask for your password in; Luna has none,
# and BatchMode makes SSH fail instead of waiting for a password of its own
if [ -t 0 ]; then tty=(-t); else tty=(-o BatchMode=yes); fi
ssh "${tty[@]}" -o ConnectTimeout=5 "$WEB" "CHECK=$check bash -c $(printf %q "$REMOTE")" \
    || echo "== the update didn't finish (see above)"
