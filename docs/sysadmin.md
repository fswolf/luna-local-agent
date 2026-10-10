# Sysadmin

Luna can look after your machines: check on them at the desk, keep an
eye on them on a schedule, and answer from your phone. Nothing here is
a separate product. It's the tools she already has, put together:

| Piece | What it gives her | Asks first? |
|-------|-------------------|-------------|
| `system_status` | VRAM, GPU temp and load, RAM, disk, the loaded model | no, it only reads |
| `run_command` | a shell, as you | **every command** |
| `read_file` / `list_files` | logs, configs, reports, anywhere under `~` minus the deny list | no (yours to change in the tools pane) |
| `write_file` / `edit_file` | notes and reports | yes, except a job writing inside `job_write_dirs` |
| [Scheduled jobs](plugins.md#scheduled-jobs) | work she does on her own, on a timer | once, when the job is created |
| [Discord](plugins.md#discord-remote-access) | the same Luna from your phone | per the `approval` setting |
| [Home Assistant](home.md) | power, plugs and sensors on your network | locks, doors and alarms always |

Things you can say at the desk:

- "How's the machine doing?"
- "What's using port 8080?"
- "Is the kokoro service running? Restart it if it isn't."
- "Show me the last 30 lines of the llama log and tell me what went wrong."
- "How much space is left on my home drive, and what's taking it?"
- "Write me a script that backs up ~/notes to the server."

Each command shows up in the popup exactly as it will run, with the
folder and her reason. Read it before you press `Y`: the command can
read anything you can. See [Files and commands](files.md#running-commands)
for the details.

## Setting up the scheduler

Three things, once:

```
mkdir -p ~/luna-jobs
/cron on
```

and in `config.json`:

```json
"files": { "job_write_dirs": ["~/luna-jobs"] }
```

- `/cron on` starts the scheduler and saves it.
- `job_write_dirs` is the one folder a job may write to without asking.
  It's how a job at 3am leaves you a report instead of a popup nobody
  answers. Pick a folder that holds nothing else.
- The folder has to exist, and it can't be `~` itself or anything
  overlapping Luna's own folder.

Then ask for a job in plain words, approve the popup, and it's saved
to `agent/cron.json`.

## Jobs worth having

Each of these can be asked for out loud or pasted into
`agent/cron.json`. Anything that fires while you might be asleep gets
`"speak": false`.

**Morning machine check.** Only speaks up when something's wrong.

```json
{"name": "morning-check", "schedule": "0 8 * * *",
 "task": "Check system_status. If disk or RAM is under 10% free, or the GPU is over 85C, say so in one sentence and add a dated line to ~/luna-jobs/health.md. Otherwise just say all good.",
 "speak": true}
```

**Weekly log read.** She reads, you get the summary.

```json
{"name": "log-review", "schedule": "0 9 * * 1",
 "task": "Read the last part of ~/.cache/ai-voice/kokoro.log and ~/luna-jobs/health.md. Write a short summary of errors and warnings from the past week to ~/luna-jobs/weekly.md, newest first.",
 "speak": false}
```

**Release watch.** Uses the web tools already in `job_tools`.

```json
{"name": "llama-release", "schedule": "every 1d",
 "task": "Search for the latest llama.cpp release. If it's newer than the one noted in ~/luna-jobs/versions.md, update that file and tell me what changed in two sentences.",
 "speak": false}
```

`/cron` lists the jobs and the last result of each. Ask her "what did
the morning check say?" and she can read the report back.

## Checking other machines

A job can't run commands unattended. `run_command` asks every time, a
job firing at night has nobody to ask, and it times out as a no. That's
deliberate, and the way around it is simple:

**Let the system do the shell part, and let Luna read the result.**

Your normal crontab (`crontab -e`) runs the commands and drops plain
text into `~/luna-jobs`. Her job reads that text and tells you what
matters. She never gets an unattended shell, and you wrote every
command that runs.

For an Unraid server or any other box you can reach with SSH keys:

```bash
# crontab -e on your desktop: every 30 minutes, what's running and how full it is
*/30 * * * * ssh -o BatchMode=yes root@tower 'docker ps -a --format "{{.Names}}\t{{.Status}}"' > ~/luna-jobs/tower-containers.txt 2>&1
*/30 * * * * ssh -o BatchMode=yes root@tower 'df -h /mnt/user /mnt/cache' > ~/luna-jobs/tower-disk.txt 2>&1
```

```json
{"name": "tower-check", "schedule": "0 */4 * * *",
 "task": "Read ~/luna-jobs/tower-containers.txt and ~/luna-jobs/tower-disk.txt. If a container that should be up has exited, or a share is over 90% full, tell me which. If the files are older than an hour, say the checks stopped running. Otherwise stay quiet.",
 "speak": true}
```

`BatchMode=yes` makes SSH fail instead of hanging on a password
prompt. Swap in your own host and the containers you care about.

At the desk you don't need any of this. "Is Plex running on the
tower?" becomes `ssh root@tower docker ps` in a popup, and you approve
it. SSH uses your key on its own. She can't read `~/.ssh` herself,
and doesn't need to.

## From your phone

With [Discord](plugins.md#discord-remote-access) on, the same questions
work from a private channel: "how's the machine?", "is the tower
check happy?", "restart kokoro". What happens when she wants to run a
command is the `approval` setting:

| `approval` | A command from Discord... |
|------------|---------------------------|
| `discord` (default) | is shown in the chat, and you reply `y` or `n` |
| `desk` | pops up at the keyboard, which is no use if you're out |
| `auto` | runs without asking. Only for a channel nobody else can post in |

Her own folder, `~/.config` and `~/.local` always get a question, even
on `auto`. `!stop` in Discord ends a turn that's going wrong.

## What she won't do

- **Use sudo or answer prompts.** Commands run with nothing on their
  input, so a password or y/n prompt fails instead of hanging. Do the
  root parts yourself, or give the command a sudoers rule you chose.
- **Run a command without you.** No allow-all and no "safe list". On
  Discord, only `auto` skips the question, and only because you set it.
- **Touch the deny list.** `~/.ssh`, `~/.gnupg`, keys, shell startup
  files and her own credentials are refused, reading included.
- **Let a job make jobs.** `schedule_job` is never in a job's tools.
- **Catch up.** Runs missed while Luna was closed are skipped.

Job reports show in the conversation, the logbook and `/cron`, and are
spoken unless `speak` is off. They aren't posted to Discord on their
own. Ask her from Discord and she'll read the latest one.
