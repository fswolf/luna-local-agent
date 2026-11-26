#!/usr/bin/env bash
# Copies a web server's database backups (*.sql.gz) to a share on a NAS. Files already on the
# share are skipped. Read-only on the web server, nothing there is ever deleted;
# on the NAS it only writes into DEST. Each copy lands as .part, is checked with
# gzip -t, then renamed, so a cut-off copy never looks like a backup.
# Then it thins out old copies on the share, going by the date in each name:
# everything from the last KEEP_DAYS days, the first backup of each month for
# KEEP_MONTHS months, and always the newest KEEP_MIN of each database (so a
# backup that stopped running never gets cleaned away to nothing).
# --dry-run copies nothing and deletes nothing, only says what it would do.
# Needs SSH key login to both (BatchMode: fails instead of asking for a password).
WEB=you@192.168.1.10         # change to yours: the web server
SRC=backups
NAS=root@192.168.1.20        # and the NAS
DEST="/mnt/user/backups/SQL"  # the folder on the NAS (an Unraid share here)
KEEP_DAYS=30
KEEP_MONTHS=12
KEEP_MIN=7

dry=0; [ "$1" = "--dry-run" ] && dry=1

SSH=(ssh -n -o BatchMode=yes -o ConnectTimeout=5)
q=$(printf %q "$DEST")

have=$("${SSH[@]}" "$NAS" "mkdir -p $q && ls -1 $q") \
    || { echo "FAILED: can't reach the NAS, or $DEST isn't there"; exit 1; }
list=$("${SSH[@]}" "$WEB" "cd $SRC && ls -1 -- *.sql.gz") \
    || { echo "FAILED: can't list the backups on the web server"; exit 1; }
mapfile -t files <<<"$list"

copied=0; there=0; failed=()
for f in "${files[@]}"; do
    [[ $f =~ ^[A-Za-z0-9_.-]+\.sql\.gz$ ]] || continue
    if grep -qxF -- "$f" <<<"$have"; then there=$((there + 1)); continue; fi
    if [ $dry = 1 ]; then echo "would copy $f"; copied=$((copied + 1)); continue; fi
    if "${SSH[@]}" "$WEB" "cat $SRC/$f" \
        | ssh -o BatchMode=yes -o ConnectTimeout=5 "$NAS" "cd $q && cat > $f.part && gzip -t $f.part && mv $f.part $f"; then
        copied=$((copied + 1))
    else
        failed+=("$f")
        "${SSH[@]}" "$NAS" "rm -f $q/$f.part"
    fi
done

[ $dry = 1 ] && echo "== dry run: nothing copied or deleted"
echo "== backups to the NAS: copied $copied, already there $there, failed ${#failed[@]}"
[ ${#failed[@]} -gt 0 ] && printf 'FAILED: %s\n' "${failed[@]}"
# Thinning: names are <database>_<YYYY-MM-DD>.sql.gz, oldest first per database
# once sorted. A new month's first file is kept while the month is recent enough.
have=$("${SSH[@]}" "$NAS" "ls -1 $q") || { echo "FAILED: can't list $DEST for the cleanup"; exit 1; }
day_cut=$(date -d "-$KEEP_DAYS days" +%F)
month_cut=$(date -d "$(date +%Y-%m-01) -$((KEEP_MONTHS - 1)) months" +%Y-%m)
declare -A total seen month_of
mapfile -t dated < <(grep -E '^[A-Za-z0-9_.-]+_[0-9]{4}-[0-9]{2}-[0-9]{2}\.sql\.gz$' <<<"$have" | sort)
for f in "${dated[@]}"; do db=${f%_*}; total[$db]=$(( ${total[$db]:-0} + 1 )); done
gone=()
for f in "${dated[@]}"; do
    db=${f%_*}; d=${f##*_}; d=${d%.sql.gz}; m=${d:0:7}
    seen[$db]=$(( ${seen[$db]:-0} + 1 ))
    first=0; [ "${month_of[$db]}" != "$m" ] && { first=1; month_of[$db]=$m; }
    if [[ $d > $day_cut || $d == "$day_cut" ]]; then continue; fi
    if [ $first = 1 ] && [[ $m > $month_cut || $m == "$month_cut" ]]; then continue; fi
    if [ $(( total[$db] - seen[$db] )) -lt $KEEP_MIN ]; then continue; fi
    gone+=("$f")
done
if [ ${#gone[@]} -eq 0 ]; then
    echo "== cleanup: nothing old enough to remove"
elif [ $dry = 1 ]; then
    echo "== cleanup: would remove ${#gone[@]}"; printf '  %s\n' "${gone[@]}"
else
    "${SSH[@]}" "$NAS" "cd $q && rm -f -- ${gone[*]}" \
        && echo "== cleanup: removed ${#gone[@]} old backups" \
        || echo "FAILED: the cleanup couldn't remove old backups"
fi
echo "   keeping: the last $KEEP_DAYS days, the first of each month back to $month_cut, at least $KEEP_MIN of each"

echo "== newest on the NAS"; "${SSH[@]}" "$NAS" "cd $q && ls -1t -- *.sql.gz 2>/dev/null | head -4"
echo "== space on the share"; "${SSH[@]}" "$NAS" "df -h $q | tail -1"
[ ${#failed[@]} -eq 0 ]
