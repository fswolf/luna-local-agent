#!/usr/bin/env bash
# A web server at a glance, read-only: up, load, memory, disks,
# failed services, the web and database services, every site Apache serves
# (its answer and how long its certificate has left), errors since boot.
# Needs SSH key login (BatchMode: fails instead of asking for a password).
WEB=you@192.168.1.10         # change to yours

ssh -o BatchMode=yes -o ConnectTimeout=5 "$WEB" 'bash -s' <<'EOF' || echo "Can't reach the web server over SSH (is it on, and does key login work?)"
echo "== $(hostname): up $(uptime -p | sed 's/^up //'), load $(cut -d' ' -f1-3 /proc/loadavg) on $(nproc) cores"
echo "== memory"; free -h | sed -n '1,3p'
echo "== disks"; df -h -x tmpfs -x devtmpfs -x squashfs -x overlay -x efivarfs 2>/dev/null
echo "== failed services"; systemctl --failed --no-legend --plain 2>/dev/null | grep . || echo "none"

echo "== web and database"
seen=" "
for s in apache2 nginx mariadb mysql; do
    systemctl list-unit-files "$s.service" --no-legend 2>/dev/null | grep -q . || continue   # not installed
    id=$(systemctl show -p Id --value "$s" 2>/dev/null)         # mysql is mariadb's other name on Debian
    case "$seen" in *" $id "*) continue ;; esac
    seen="$seen$id "
    echo "$s: $(systemctl is-active "$s" 2>/dev/null)"
done
if systemctl list-unit-files certbot.timer --no-legend 2>/dev/null | grep -q .; then
    echo "certificate renewal (certbot.timer): $(systemctl is-active certbot.timer 2>/dev/null)"
fi

echo "== sites (answer from this machine, certificate days left)"
names=$(grep -hiE '^\s*Server(Name|Alias)\s' /etc/apache2/sites-enabled/*.conf 2>/dev/null \
        | awk '{for (i = 2; i <= NF; i++) print tolower($i)}' | grep -v '^\*' | sort -u)
# www.x beside x is the same site (mostly a redirect to it): one line each, not two
names=$(for n in $names; do case "$n" in www.*) echo "$names" | grep -qx "${n#www.}" && continue ;; esac; echo "$n"; done)
if [ -z "$names" ]; then
    echo "no ServerName lines readable in /etc/apache2/sites-enabled"
fi
now=$(date +%s)
for n in $names; do
    code=$(curl -s -o /dev/null -m 8 -k -w '%{http_code}' --resolve "$n:443:127.0.0.1" "https://$n/")
    end=$(echo | timeout 8 openssl s_client -servername "$n" -connect 127.0.0.1:443 2>/dev/null \
          | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
    if [ -n "$end" ]; then
        days=$(( ($(date -d "$end" +%s) - now) / 86400 ))
        cert="cert ${days}d"
    else
        cert="no certificate on 443"
    fi
    echo "$n: HTTP $code, $cert"
done

echo "== Apache's latest errors"
if [ -r /var/log/apache2/error.log ]; then
    tail -n 5 /var/log/apache2/error.log
else
    echo "(error.log isn't readable as $(whoami): sudo usermod -aG adm $(whoami))"
fi
echo "== errors since boot, by count"
journalctl -b -p err --no-pager -o cat 2>/dev/null | sort | uniq -c | sort -rn | head -10 | grep . \
    || echo "none (or the journal isn't readable as $(whoami))"
EOF
