# Scheduled jobs

Luna can do things on her own, on a timer: check something every
morning, summarize something every week, run a script of yours every
Sunday at 4am and tell you how it went. You set a job up once, approve
it once, and from then on it runs while Luna is open.

The settings and every rule are in [Plugins: scheduled jobs](plugins.md#scheduled-jobs).
This page is about using them, with a walkthrough at the end: a weekly
copy of a web server's database backups to a NAS.

## Turning it on

```
/cron on        start the scheduler (saved)
/cron           the jobs, when each last ran, and each script's state
/cron off       stop it (the jobs are kept)
```

## Making one

Ask for it in plain words, with the time and what to do:

> *"Every weekday at 8, check disk and VRAM and note anything low in
> ~/luna-jobs/disk.md."*

She calls `schedule_job`, and a popup shows the job: when it runs, what
it does, which tools it gets, and where it may write without asking.
Nothing is saved until you approve it. That's the step where you hand
her permission to act later, so it's the step that asks.

| Say | Schedule |
|-----|----------|
| every weekday at 8 | `0 8 * * 1-5` |
| every Sunday at 4am | `0 4 * * 0` |
| every 30 minutes | `every 30m` |
| once, on the 7th of October at 8 | `2026-10-07 08:00` |

Jobs live in `agent/cron.json` (gitignored, since they're yours).
"What jobs do I have?" lists them, and "cancel the disk-check job"
removes one.

## What a job can do

A job firing is a turn of its own: fresh context, none of your history,
and only the tools in `job_tools` (the time, system health, web search,
reading files, and writing files). It writes without asking only inside
the folders you list in `files.job_write_dirs`, like `~/luna-jobs`;
anywhere else asks, and at night nobody answers, so her report says
what she would have written.

**A job never picks a command.** `run_command` asks every time, and at
4am nobody's there to approve it. Shell work on a timer goes in a
script of yours instead, and the job names it.

## A job that runs a script

The script lives in `agent/jobs/` inside Luna's folder (gitignored, so
your host names stay yours). When the job is created, the popup shows
**the whole script**, and approving it pins that exact text by its
fingerprint. At each firing:

1. The scheduler checks the file is still exactly what you approved.
2. It runs it with `bash`, from your home folder, with nothing on its
   input.
3. Luna's job turn gets what it printed, and the task: tell you what
   failed, write a note, stay quiet if all is well.

She never chooses the command; she reads its output. If you edit the
script, the next firing skips it and tells you why. "Approve the script
for the nas-backups job" brings up the popup with the new text, for a
yes or a no.

## Walkthrough: weekly backups to the NAS

A web server makes a database dump every night into `~/backups`. Once a
week, Luna copies the new ones to a share on the NAS, checks each copy,
thins out old ones, and tells you if anything went wrong. Swap in your
own addresses: `you@192.168.1.10` (the web server) and
`root@192.168.1.20` (the NAS) are stand-ins.

### 1. Key login to both machines

On the computer Luna runs on. Skip the first line if you already have a
key:

```bash
ssh-keygen -t ed25519
ssh-copy-id you@192.168.1.10
ssh-copy-id root@192.168.1.20
ssh -o BatchMode=yes you@192.168.1.10 hostname
ssh -o BatchMode=yes root@192.168.1.20 hostname
```

The last two have to print a name without asking anything. The job
runs with nobody at the keyboard, so a password prompt is a failure.
The key needs no passphrase, or an SSH agent that's running when Luna
is. No password is written anywhere: not in the script, not in the job.

### 2. The script

Save this as `~/ai-voice/agent/jobs/backups-to-nas.sh`:

```bash
#!/usr/bin/env bash
# Copies the NUC's database backups to the Unraid share. Files already on the
# share are skipped. Read-only on the NUC, nothing there is ever deleted;
# on Unraid it only writes into DEST. Each copy lands as .part, is checked with
# gzip -t, then renamed, so a cut-off copy never looks like a backup.
# Then it thins out old copies on the share, going by the date in each name:
# everything from the last KEEP_DAYS days, the first backup of each month for
# KEEP_MONTHS months, and always the newest KEEP_MIN of each database (so a
# backup that stopped running never gets cleaned away to nothing).
# --dry-run copies nothing and deletes nothing, only says what it would do.
# Needs SSH key login to both (BatchMode: fails instead of asking for a password).
NUC=you@192.168.1.10
SRC=backups
NAS=root@192.168.1.20
DEST="/mnt/user/backups/SQL"
KEEP_DAYS=30
KEEP_MONTHS=12
KEEP_MIN=7

dry=0; [ "$1" = "--dry-run" ] && dry=1

SSH=(ssh -n -o BatchMode=yes -o ConnectTimeout=5)
q=$(printf %q "$DEST")

have=$("${SSH[@]}" "$NAS" "mkdir -p $q && ls -1 $q") \
    || { echo "FAILED: can't reach Unraid, or $DEST isn't there"; exit 1; }
list=$("${SSH[@]}" "$NUC" "cd $SRC && ls -1 -- *.sql.gz") \
    || { echo "FAILED: can't list the backups on the NUC"; exit 1; }
mapfile -t files <<<"$list"

copied=0; there=0; failed=()
for f in "${files[@]}"; do
    [[ $f =~ ^[A-Za-z0-9_.-]+\.sql\.gz$ ]] || continue
    if grep -qxF -- "$f" <<<"$have"; then there=$((there + 1)); continue; fi
    if [ $dry = 1 ]; then echo "would copy $f"; copied=$((copied + 1)); continue; fi
    if "${SSH[@]}" "$NUC" "cat $SRC/$f" \
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
```

What it does, in order:

- **Copies only what's missing.** Files already on the share are
  skipped, so the first run copies everything and later runs copy a
  week's worth.
- **Never leaves a broken copy.** Each file lands as `.part`, is checked
  with `gzip -t`, and only then gets its real name. A copy cut off
  halfway is deleted and reported.
- **Only reads the web server.** Nothing there is changed or deleted.
- **Thins out the share.** Going by the date in each name: everything
  from the last 30 days, the first backup of each month for a year, and
  always the newest 7 of each database, so a backup that stopped
  running is never cleaned away to nothing. Files named any other way
  are left alone.
- **Ends with a report:** copied, already there, failed, what was
  cleaned up, the newest files on the share and how full it is. Any
  problem is a line starting with `FAILED`.

The data goes from the web server to the NAS through your desktop
without being saved there.

### 3. Try it

```bash
bash ~/ai-voice/agent/jobs/backups-to-nas.sh --dry-run
bash ~/ai-voice/agent/jobs/backups-to-nas.sh
```

The first only says what it would copy and delete. The second does it.
If either asks for a password or can't reach a machine, go back to
step 1.

### 4. Ask her to schedule it

With `/cron on`:

> *"Every Sunday at 4am, run the script backups-to-nas.sh as a job
> called nas-backups. If any line says FAILED, tell me what. Otherwise
> one line on how many were copied and cleaned up."*

The popup shows the schedule, the task and the whole script. Read it,
approve it. `/cron` now shows:

```
cron: running, 1 job(s)
  nas-backups      0 4 * * 0
                   script backups-to-nas.sh: approved
```

### 5. Every Sunday

At 4am the scheduler runs the script, and Luna reads its report. If
everything copied, she says so in one line (on screen, and out loud if
someone's in the room). If a line says `FAILED`, she tells you which
file and why. The report also lands in the logbook, in `/cron`, and in
what she tells you when you come back.

### Changing it later

Edit the script and the next Sunday it doesn't run: she tells you it
changed since you approved it. Say *"approve the script for the
nas-backups job"*, read the new text in the popup, approve. To change
the time or the task, cancel the job and ask again.

## Good to know

- **Luna has to be open.** Runs missed while she was closed are
  skipped, not caught up. The backup script copies everything missing,
  so the next run makes up for a skipped week.
- **Set `"speak": false`** on anything at night if you don't want to be
  read a report at 4am. She already stays quiet when nobody's in front
  of the camera.
- **A script that hangs is stopped** after `script_timeout` (an hour
  by default), along with anything it started.
- **Only plain files directly in `agent/jobs/`,** 64 KB at most, can be
  a job's script. No job can write into Luna's folder, so none can
  rewrite one.
- **A job can't make jobs or approve scripts.** `schedule_job` and
  `approve_job_script` are never in a job's tools.
- **For a check you ask for yourself,** the same script works as a
  recipe: see [Skills (recipes)](skills.md).
