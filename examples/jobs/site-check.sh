#!/usr/bin/env bash
# A security once-over of a website, for a report Luna (or you) can read.
#
#   bash site-check.sh example.com            the public face: only what any browser
#                                             or mail server sees anyway
#   bash site-check.sh example.com --active   plus open ports and probing for exposed
#                                             files. Your own sites, or a client's who
#                                             said yes (in writing): on someone else's
#                                             server this can count as unauthorised use.
#   bash site-check.sh example.com --report   the same findings as a report to read:
#                                             grouped worst first, a fix under each
#                                             (what Luna runs, and passes on as is)
#
# Public face: HTTPS and the redirect to it, the certificate, old TLS versions,
# security headers, cookie flags, version banners, security.txt, and the
# domain's email and DNS security (SPF, DMARC, DKIM, CAA, DNSSEC).
# Active: nmap's top 100 ports with versions, a short list of files that
# shouldn't be public (.git, .env, backups, phpinfo...), and nuclei's
# non-intrusive templates if nuclei is installed.
#
# Each finding is one line: [HIGH] [MED] [LOW] [INFO] or [OK], most with a
# "fix:" line under it (Debian and Apache), then a count. Scanning a site
# hosted on your own network from inside it, the ports and DNS answers are
# your router's inside view: the report says so at the top.
# Needs: curl, openssl, dig (bind-utils). For --active: nmap; nuclei optional.
# Nothing here changes anything on the site.

target=""; active=0; report=0
for a in "$@"; do
    case "$a" in --active) active=1 ;; --report) report=1 ;; -*) echo "unknown option $a"; exit 2 ;; *) target="$a" ;; esac
done
d=$(echo "$target" | sed -E 's#^[a-zA-Z]+://##; s#[/?].*$##; s#:.*$##' | tr 'A-Z' 'a-z')
[[ "$d" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]] \
    || { echo "usage: site-check.sh <domain> [--active] [--report]"; exit 2; }

high=0 med=0 low=0
found_lines=()
say() {   # say LEVEL text [fix]: the fix goes on its own line, for the web server it found
    case "$1" in HIGH) high=$((high + 1)) ;; MED) med=$((med + 1)) ;; LOW) low=$((low + 1)) ;; esac
    if [ $report = 1 ]; then found_lines+=("$1"$'\t'"$2"$'\t'"$3"); return 0; fi
    printf '[%s] %s\n' "$1" "$2"
    [ -n "$3" ] && printf '       fix: %s\n' "$3"
    return 0
}
part() { [ $report = 1 ] || echo "== $1"; }
have() { command -v "$1" >/dev/null; }
UA="Mozilla/5.0 (site-check)"

scope="$( [ $active = 1 ] && echo "public face + active" || echo "public face" )"
when=$(date '+%Y-%m-%d %H:%M')
[ $report = 1 ] || echo "== $d ($scope, $when)"

# Your own public address: when the site resolves to it, you're scanning your own
# network from inside, and the router answers for itself (its DNS, UPnP, admin page)
# as it does for anyone on the LAN. Forwarded ports are real; the rest isn't what
# the internet sees.
inside=0
if have dig; then
    me=$(dig +short +time=3 +tries=1 myip.opendns.com @resolver1.opendns.com 2>/dev/null | grep -E '^[0-9.]+$' | head -1)
    if [ -n "$me" ] && dig +short A "$d" | grep -qxF "$me"; then
        inside=1
        say INFO "$d is hosted on your own network ($me) and you're scanning it from inside: ports and DNS below are your router's inside view, not what the internet sees" \
            "for the outside view, run it from a phone hotspot or another network"
    fi
fi

# --- DNS -------------------------------------------------------------------
part "DNS and email"
if have dig; then
    ips=$(dig +short A "$d" | grep -E '^[0-9.]+$' | tr '\n' ' ')
    [ -n "$ips" ] && say INFO "resolves to $ips" || say HIGH "no A record: $d doesn't resolve"
    root=$(echo "$d" | awk -F. '{print $(NF-1)"."$NF}')
    spf=$(dig +short TXT "$root" | tr -d '"' | grep -i '^v=spf1')
    if [ -z "$spf" ]; then say MED "no SPF record on $root: anyone can send mail that claims to be from it" "add a TXT record on $root: v=spf1 plus your mail provider's include, ending in -all"
    elif echo "$spf" | grep -q '+all'; then say HIGH "SPF ends in +all: it allows every server on the internet" "change +all to -all in the same TXT record"
    elif echo "$spf" | grep -q -- '-all'; then say OK "SPF: $spf"
    else say LOW "SPF doesn't end in -all (soft or neutral): $spf" "once every server that sends your mail is in the record, change ~all to -all in that same record"; fi
    dmarc=$(dig +short TXT "_dmarc.$root" | tr -d '"' | grep -i '^v=DMARC1')
    if [ -z "$dmarc" ]; then say MED "no DMARC record: spoofed mail from $root isn't rejected or reported" "add a TXT record named _dmarc.$root: v=DMARC1; p=none; rua=mailto:you@$root (reports first; raise p=none to p=quarantine once they show only your own mail)"
    elif echo "$dmarc" | grep -qiE 'p=none'; then say LOW "DMARC is p=none: reports only, spoofed mail still delivered" "in the _dmarc.$root TXT record, change p=none to p=quarantine once the reports show only your own mail"
    else say OK "DMARC: $(echo "$dmarc" | grep -oiE 'p=[a-z]+')"; fi
    dkim=""
    for s in default selector1 selector2 google k1 mail dkim s1 s2 mxvault; do
        dig +short TXT "$s._domainkey.$root" | grep -qi 'p=' && { dkim="$s"; break; }
    done
    [ -n "$dkim" ] && say OK "DKIM key found (selector $dkim)" \
        || say INFO "no DKIM key under the common selector names (it may use another name)"
    [ -n "$(dig +short CAA "$root")" ] && say OK "CAA set: only named authorities may issue certificates" \
        || say LOW "no CAA record: any certificate authority may issue for $root" "add a CAA record (its own record type, not TXT) on $root: 0 issue \"letsencrypt.org\""
    [ -n "$(dig +short DS "$root")" ] && say OK "DNSSEC signed" || say INFO "no DNSSEC"
else
    say INFO "dig isn't installed (sudo dnf install bind-utils): DNS and email checks skipped"
fi

# --- HTTP and HTTPS ----------------------------------------------------------
part "web"
hdr=$(curl -s -D - -o /dev/null -m 15 -A "$UA" "https://$d/" 2>/dev/null)
h() { echo "$hdr" | grep -i "^$1:" | tail -1 | cut -d: -f2- | sed 's/^ *//; s/\r$//'; }
srv=$(h server); pb=$(h x-powered-by)
# Fixes are written for what serves the site: Apache (the default), nginx, or Plesk
# (nginx in front, set up through its panel rather than config files).
stack=apache
echo "$srv" | grep -qi nginx && stack=nginx
echo "$pb $hdr" | grep -qi plesk && stack=plesk
web() {   # web "Apache fix" "nginx line": the fix for this server
    case $stack in
        nginx) echo "nginx, in the site's server block: $2, then sudo systemctl reload nginx" ;;
        plesk) echo "Plesk: the domain's Apache & nginx Settings, Additional nginx directives: $2" ;;
        *) echo "Apache: $1" ;;
    esac
}
phpini() {   # where the PHP settings go
    case $stack in
        plesk) echo "Plesk: the domain's PHP Settings, Additional configuration directives: $1" ;;
        nginx) echo "in PHP-FPM's php.ini (Debian: /etc/php/<version>/fpm/php.ini): $1, then sudo systemctl restart php<version>-fpm" ;;
        *) echo "in PHP's php.ini (Debian: /etc/php/<version>/apache2/php.ini): $1, then reload Apache" ;;
    esac
}
[ $stack = apache ] || say INFO "served by $( [ $stack = plesk ] && echo "Plesk (nginx in front)" || echo nginx ): the fixes are written for it"

loc=$(curl -s -o /dev/null -m 10 -A "$UA" -w '%{http_code} %{redirect_url}' "http://$d/")
case "$loc" in
    3*" https://"*) say OK "http:// redirects to https" ;;
    000*) say INFO "nothing answers on plain http (port 80)" ;;
    *) case $stack in
           plesk) fix="Plesk: the domain's Hosting Settings, Permanent SEO-safe 301 redirect from HTTP to HTTPS" ;;
           nginx) fix="nginx, in the port 80 server block: return 301 https://\$host\$request_uri; then sudo systemctl reload nginx" ;;
           *) fix="Apache: Redirect permanent / https://$d/ in the port 80 VirtualHost (sudo certbot --apache --redirect does it for you)" ;;
       esac
       say MED "http:// doesn't redirect to https (answers ${loc%% *})" "$fix" ;;
esac

if [ -z "$hdr" ]; then
    err=$(curl -s -o /dev/null -m 15 "https://$d/" 2>&1; echo "exit $?")
    say HIGH "https://$d/ doesn't answer, or its certificate doesn't check out ($err)"
else
    say INFO "https answers $(echo "$hdr" | grep -m1 '^HTTP' | tr -d '\r')"
    hsts=$(h strict-transport-security)
    [ -n "$hsts" ] && say OK "HSTS: $hsts" || say MED "no HSTS header: a first visit can be downgraded to plain http" "$(web "in the 443 VirtualHost: Header always set Strict-Transport-Security \"max-age=31536000; includeSubDomains\" (sudo a2enmod headers, then reload)" "add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains\" always;")"
    csp=$(h content-security-policy)
    [ -n "$csp" ] && say OK "Content-Security-Policy set" || say LOW "no Content-Security-Policy: no second line of defence against injected scripts" "$(web "Header always set Content-Security-Policy \"default-src 'self'\"" "add_header Content-Security-Policy \"default-src 'self'\" always;") (then loosen it for what the site really loads: test it, a strict one can break pages)"
    if [ -n "$(h x-frame-options)" ] || echo "$csp" | grep -qi frame-ancestors; then say OK "framing restricted (clickjacking)"
    else say LOW "no X-Frame-Options or frame-ancestors: the site can be framed (clickjacking)" "$(web "Header always set X-Frame-Options SAMEORIGIN" "add_header X-Frame-Options SAMEORIGIN always;")"; fi
    [ "$(h x-content-type-options | tr 'A-Z' 'a-z')" = nosniff ] && say OK "X-Content-Type-Options: nosniff" || say LOW "no X-Content-Type-Options header: browsers may guess what a file is (nosniff stops that)" "$(web "Header always set X-Content-Type-Options nosniff" "add_header X-Content-Type-Options nosniff always;")"
    [ -n "$(h referrer-policy)" ] && say OK "Referrer-Policy: $(h referrer-policy)" || say LOW "no Referrer-Policy: full addresses can leak to other sites" "$(web "Header always set Referrer-Policy strict-origin-when-cross-origin" "add_header Referrer-Policy strict-origin-when-cross-origin always;")"
    [ -n "$(h permissions-policy)" ] || say INFO "no Permissions-Policy"
    if echo "$srv" | grep -qE '[0-9]+\.[0-9]+'; then
        [ $stack = apache ] && fix="in /etc/apache2/conf-available/security.conf: ServerTokens Prod and ServerSignature Off, one per line, then sudo systemctl reload apache2" \
            || fix="server_tokens off; in the http block of /etc/nginx/nginx.conf, then sudo systemctl reload nginx"
        say LOW "Server header shows a version: $srv" "$fix"
    elif [ -n "$srv" ]; then say INFO "Server: $srv"; fi
    if [ -n "$pb" ]; then
        if echo "$pb" | grep -qi php; then fix=$(phpini "expose_php = Off")
        elif [ $stack = apache ]; then fix="Apache: Header always unset X-Powered-By"
        else fix=$(web "" "proxy_hide_header X-Powered-By; fastcgi_hide_header X-Powered-By;"); fi
        say LOW "X-Powered-By shows: $pb" "$fix"
    fi
    while read -r c; do
        [ -z "$c" ] && continue
        name=$(echo "$c" | cut -d: -f2- | cut -d= -f1 | tr -d ' ')
        miss=""
        echo "$c" | grep -qi '; *secure' || miss="$miss Secure"
        echo "$c" | grep -qi '; *httponly' || miss="$miss HttpOnly"
        echo "$c" | grep -qi '; *samesite' || miss="$miss SameSite"
        if [ -n "$miss" ]; then
            if [ "$name" = PHPSESSID ]; then fix=$(phpini "session.cookie_secure = 1, session.cookie_httponly = 1, session.cookie_samesite = Lax")
            else fix="the site's own code sets this cookie: add the Secure, HttpOnly and SameSite flags where it does"; fi
            say MED "cookie $name is missing:$miss" "$fix"
        else say OK "cookie $name: Secure, HttpOnly, SameSite"; fi
    done < <(echo "$hdr" | grep -i '^set-cookie:')
    gen=$(curl -s -m 15 -A "$UA" "https://$d/" | grep -oiE '<meta[^>]+name="generator"[^>]*>' | grep -oiE 'content="[^"]+"' | head -1)
    [ -n "$gen" ] && say LOW "the page says what built it, version and all: $gen" "remove the generator meta tag from the site's template (WordPress has it switched off by a one-line filter or a plugin)"
    sec=$(curl -s -o /dev/null -m 10 -A "$UA" -w '%{http_code}' "https://$d/.well-known/security.txt")
    [ "$sec" = 200 ] && say OK "security.txt published" || say INFO "no security.txt (where to report a problem)" "optional: /.well-known/security.txt with a Contact: line (securitytxt.org writes one)"
fi

# --- certificate and TLS -----------------------------------------------------
part "certificate and TLS"
if have openssl; then
    cert=$(echo | timeout 10 openssl s_client -servername "$d" -connect "$d:443" 2>/dev/null)
    end=$(echo "$cert" | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
    if [ -n "$end" ]; then
        days=$(( ($(date -d "$end" +%s) - $(date +%s)) / 86400 ))
        issuer=$(echo "$cert" | openssl x509 -noout -issuer 2>/dev/null | sed 's/.*O *= *\([^,]*\).*/\1/')
        [ $stack = plesk ] && renew="Plesk: the domain's SSL/TLS Certificates page (SSL It!) shows why it isn't renewing" \
            || renew="on the server: sudo certbot renew --dry-run shows why it isn't renewing"
        if [ $days -lt 0 ]; then say HIGH "certificate expired $(( -days )) days ago" "$renew"
        elif [ $days -lt 14 ]; then say HIGH "certificate expires in $days days ($issuer)" "$renew"
        elif [ $days -lt 30 ]; then say MED "certificate expires in $days days ($issuer)" "$renew"
        else say OK "certificate valid $days more days ($issuer)"; fi
    else
        say INFO "couldn't read the certificate on port 443"
    fi
    for v in tls1 tls1_1; do
        if echo | timeout 8 openssl s_client -"$v" -cipher 'DEFAULT@SECLEVEL=0' -servername "$d" -connect "$d:443" 2>/dev/null | grep -qE '^ *Cipher *: *[A-Z][A-Z0-9_-]+'; then   # a failed handshake prints 0000
            say MED "still accepts $( [ $v = tls1 ] && echo "TLS 1.0" || echo "TLS 1.1" ), retired in 2021" "$( [ $stack = apache ] && echo "Apache: SSLProtocol -all +TLSv1.2 +TLSv1.3 (in /etc/apache2/mods-available/ssl.conf), then reload" || echo "nginx: ssl_protocols TLSv1.2 TLSv1.3; in the http block of /etc/nginx/nginx.conf, then sudo systemctl reload nginx" )" ; fi
    done 2>/dev/null
    echo | timeout 8 openssl s_client -tls1_3 -servername "$d" -connect "$d:443" 2>/dev/null | grep -q 'TLSv1.3' \
        && say OK "TLS 1.3 supported" || say LOW "no TLS 1.3" "comes with a newer OpenSSL and web server: usually a system upgrade"
fi

# --- active: only when asked ---------------------------------------------------
if [ $active = 1 ]; then
    part "open ports (active)"
    if have nmap; then
        ports=$(nmap -Pn --top-ports 100 -sV --version-light -T4 "$d" 2>/dev/null | grep -E '^[0-9]+/tcp +open')
        if [ -z "$ports" ]; then say INFO "no open ports in the top 100 answered"; fi
        close="if it isn't meant to be public, stop the service or close the port in the firewall"
        [ $inside = 1 ] && say INFO "the ports below are what your router lets your own network see: forwarded ports are real, the router's own services (DNS, UPnP, its admin page) aren't reachable from outside"
        while read -r line; do
            [ -z "$line" ] && continue
            p=${line%%/*}; rest=$(echo "$line" | awk '{$1=$2=""; print}' | sed 's/^ *//')
            # from inside, the router answers for itself on these: not the internet's view
            if [ $inside = 1 ] && [[ " 53 1900 5000 5351 " == *" $p "* ]]; then
                say INFO "port $p open: $rest. Most likely your router's own service, seen from inside" "check from outside before changing anything"
                continue
            fi
            case "$p" in
                80|443) say OK "port $p open: $rest" ;;
                22) say INFO "port 22 open (SSH): $rest. Fine if key-only" "make sure: PasswordAuthentication no in /etc/ssh/sshd_config" ;;
                25) say INFO "port 25 open: $rest. Normal if this server receives mail for the domain (the risk would be an open relay, which this doesn't test)" ;;
                465|587|993|995) say INFO "port $p open: $rest. Normal for a mail server, and encrypted" ;;
                110|143) say LOW "port $p open: $rest. Plain POP3/IMAP: passwords can cross unencrypted unless TLS is required first" "Dovecot: ssl = required in /etc/dovecot/conf.d/10-ssl.conf, then sudo systemctl reload dovecot. Or close $p and keep 993/995" ;;
                3306|5432|6379|27017|9200|11211|1433) say HIGH "port $p open to the internet: $rest. Databases shouldn't be" "make it listen on 127.0.0.1 only (MariaDB: bind-address = 127.0.0.1 in /etc/mysql/mariadb.conf.d/50-server.cnf, then restart it) or close it in the firewall" ;;
                21) ftpd=$(echo "$rest" | grep -oiE 'proftpd|vsftpd|pure-ftpd' | head -1 | tr 'A-Z' 'a-z')
                    if [ $stack = plesk ]; then fix="if nothing needs FTP: switch it off in Plesk (Tools & Settings, Services Management), and use SFTP over SSH instead"
                    else fix="if nothing needs FTP: sudo systemctl disable --now ${ftpd:-<the FTP service>}, and use SFTP over SSH instead"; fi
                    say HIGH "port 21 open: $rest. FTP sends passwords in plain text" "$fix" ;;
                23|445|139|3389|5900) say HIGH "port $p open: $rest. Old or risky to expose" "$close" ;;
                10000) say HIGH "port 10000 open: almost certainly Webmin, a full server admin panel, open to the whole internet" "allow=<your IP> in /etc/webmin/miniserv.conf, then sudo systemctl restart webmin" ;;
                2082|2083|2086|2087) say HIGH "port $p open: cPanel/WHM's admin login, open to the whole internet" "restrict it to your IP in WHM's Host Access Control" ;;
                8006) say HIGH "port 8006 open: Proxmox's admin panel, open to the whole internet" "close it in the firewall and reach it over a VPN (Tailscale)" ;;
                9090) say HIGH "port 9090 open: usually Cockpit, a server admin panel, open to the whole internet" "close it in the firewall and reach it over a VPN (Tailscale)" ;;
                8880|8443)
                    if [ $stack = plesk ]; then say MED "port $p open: Plesk's admin panel, open to the whole internet" "Plesk: Tools & Settings, Restrict Administrative Access: allow only your own IP"
                    else say MED "port $p open: $rest. Often an admin panel (Plesk and others): check what it is" "$close"; fi ;;
                53)
                    # a server that answers lookups for any domain, for anyone, is used to amplify DDoS attacks
                    if have dig && dig +short +time=3 +tries=1 @"$d" example.com A 2>/dev/null | grep -qE '^[0-9.]+$'; then
                        say HIGH "port 53 is an open resolver: it looks up any domain for anyone (used in DDoS attacks)" "BIND: allow-recursion { localhost; localnets; }; in /etc/bind/named.conf.options, then sudo systemctl reload named"
                    else
                        say INFO "port 53 open: $rest. Answers for its own domains only, which is fine for a DNS server"
                    fi ;;
                *) say MED "port $p open: $rest. Meant to be public?" "$close" ;;
            esac
        done <<< "$ports"
    else
        say INFO "nmap isn't installed (sudo dnf install nmap): ports skipped"
    fi

    part "files that shouldn't be public (active)"
    found=0
    probe() {   # probe PATH LEVEL WHAT [must-contain] [fix]
        local body code
        body=$(curl -s -m 10 -A "$UA" -w '\n%{http_code}' "https://$d$1")
        code=${body##*$'\n'}; body=${body%$'\n'*}
        [ "$code" = 200 ] || return
        [ -n "$4" ] && ! echo "$body" | grep -q "$4" && return
        say "$2" "$1 is readable: $3 (https://$d$1)" "${5:-move it out of the web root, or delete it}"; found=1
    }
    probe /.git/HEAD HIGH "the site's git history, source code and maybe passwords" "ref:" "$(web "RedirectMatch 404 /\\.git in the site's config" "location ~ /\\.git { deny all; }"), or deploy without the .git folder"
    probe /.env HIGH "an environment file, usually passwords and keys" "="
    probe /.svn/entries HIGH "the site's Subversion history"
    probe /.DS_Store LOW "a Mac folder listing" "Bud1"
    probe /phpinfo.php MED "PHP's full configuration" "PHP Version"
    probe /info.php MED "PHP's full configuration" "PHP Version"
    probe /server-status MED "Apache's live status: who's visiting what" "Apache Server Status" "in /etc/apache2/mods-available/status.conf: Require local, then reload"
    probe /backup.zip HIGH "a backup archive"
    probe /backup.sql HIGH "a database dump"
    probe /db.sql HIGH "a database dump"
    probe /wp-config.php.bak HIGH "a WordPress config backup, with the database password" "DB_PASSWORD"
    probe /phpmyadmin/ MED "phpMyAdmin's login" "phpMyAdmin" "$( [ $stack = apache ] && echo "in /etc/apache2/conf-available/phpmyadmin.conf: Require ip <your IP> instead of Require all granted, then sudo systemctl reload apache2" || web "" "location /phpmyadmin { allow <your IP>; deny all; }" )"
    [ $found = 0 ] && say OK "none of the usual leaked files are readable"

    if have nuclei; then
        part "nuclei (active, non-intrusive templates)"
        out=$(nuclei -u "https://$d" -silent -nc -severity low,medium,high,critical -etags intrusive,dos,fuzz,bruteforce -rl 20 2>/dev/null)
        if [ -z "$out" ]; then say OK "nuclei found nothing at low severity or above"; fi
        while read -r line; do
            [ -z "$line" ] && continue
            case "$line" in *"[critical]"*|*"[high]"*) say HIGH "nuclei: $line" ;; *"[medium]"*) say MED "nuclei: $line" ;; *) say LOW "nuclei: $line" ;; esac
        done <<< "$out"
    else
        say INFO "nuclei isn't installed: its checks skipped (optional)"
    fi
fi

if [ $report = 0 ]; then
    echo "== summary: $high high, $med medium, $low low"
    exit 0
fi

# The report: plain text with **bold** (what Luna's chat and Discord both show),
# grouped worst first, a fix under each finding. Meant to be
# passed on as it is, so how it reads doesn't depend on whoever passes it on.
item() {   # item text [fix]: "**Title:** the rest", then the fix under it
    local title=${1%%: *} rest=""
    [ "$title" != "$1" ] && rest=${1#*: }
    if [ -n "$rest" ]; then printf -- '- **%s:** %s\n' "${title^}" "$rest"; else printf -- '- **%s**\n' "${1^}"; fi
    local fix=$2
    [[ $fix =~ ^[a-z]+\  ]] && fix=${fix^}   # a plain word, not a setting like allow=
    [ -n "$fix" ] && printf -- '  - **Fix:** %s\n' "$fix"
    return 0
}
echo "**Security check: $d** ($scope, $when)"
echo "**$high high, $med medium, $low low**"
for f in "${found_lines[@]}"; do
    IFS=$'\t' read -r lvl text fix <<< "$f"
    [ "$lvl" = INFO ] && [[ "$text" == *"hosted on your own network"* ]] && { echo; echo "**Scanned from inside your own network:** ${text#*: }. ${fix^}."; }
done
for lvl in HIGH MED LOW; do
    case $lvl in HIGH) name="High: fix first" ;; MED) name="Medium" ;; LOW) name="Low" ;; esac
    first=1
    for f in "${found_lines[@]}"; do
        IFS=$'\t' read -r l text fix <<< "$f"
        [ "$l" = "$lvl" ] || continue
        [ $first = 1 ] && { echo; echo "**$name**"; first=0; }
        item "$text" "$fix"
    done
done
good=(); notes=()
for f in "${found_lines[@]}"; do
    IFS=$'\t' read -r l text fix <<< "$f"
    case $l in
        OK) good+=("${text%%: *}") ;;
        INFO) case "$text" in *"hosted on your own network"*|"resolves to "*|"https answers "*|"Server: "*|"nothing answers on plain http"*) ;; *) notes+=("$text") ;; esac ;;
    esac
done
if [ ${#notes[@]} -gt 0 ]; then echo; echo "**Notes**"; for n in "${notes[@]}"; do echo "- ${n^}"; done; fi
if [ ${#good[@]} -gt 0 ]; then echo; printf '**Already good:** '; ( IFS=';'; echo "${good[*]}" | sed 's/;/; /g' ); fi
