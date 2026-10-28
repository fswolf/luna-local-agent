# Plugins

An add-on connects her to something the core has no business knowing
about: a stream chat, a game, a piece of hardware. Drop a `.py` file in
`plugins/` and it's found; delete it and it's gone. Nothing in the core
names a plugin, which is what makes them droppable.

```
/plugins        what's installed, and whether it's running
/<name> on      start one (saved, so it comes back next launch)
/<name> off     stop it
/<name>         its own status block
```

Every loaded plugin answers to its own name automatically: `/youtube on`
works the day you write `plugins/youtube.py`, with no change to the core.

```
> /plugins
Plugins:
  [on ] youtube      answers live chat out loud
  [off] example      a template - connects to nothing, answers nothing
  [--] twitch        no API key - see plugins/twitch.py
  [--] discord       no bot token - put it in ~/.config/ai-voice/discord.json
  [!!] mygame        didn't load: ModuleNotFoundError: No module named 'pygame'
```

`[--]` is loaded but can't run and says why; `[!!]` didn't import at
all. Neither stops the app starting.

**Plugins are tracked in git, all of them**, including any you add
later, so keep anything private out of the file itself. Credentials go
in `~/.config/ai-voice/`, and channel or account names in
`config.json`.

## Writing one

A module with a `NAME` and whichever of these it needs:

| | |
|--|--|
| `NAME` | what `/<name> on\|off` calls it: **the only required one** |
| `SUMMARY` | one line for `/plugins` |
| `available()` / `why_unavailable()` | can it run, and if not why |
| `start(model)` / `stop()` | `(ok, message)` |
| `running()` / `status()` | state, and the block `/<name>` prints |
| `command(text)` | anything else after `/<name>`: `/minecraft goal build a hut` calls `command("goal build a hut")` |
| `prompt_line(private)` | a line for her prompt while it runs ("a toy is connected") |
| `on_user_text(text)` | sees each of your messages before she does |
| `panic()` | you interrupted her (HOME): stop anything physical |
| `on_camera_open(device)` / `on_camera_close(device)` | the webcam is opening / has closed again; keep it quick ([camera light](vision.md#the-camera-light-and-hooks), `plugins/camera_led.py`) |

A plugin can also bring an MCP server with it and drop it again:
`mcpclient.connect_server(name, spec)` starts the server and registers
its tools while the plugin is on, and `mcpclient.disconnect_server(name)`
takes them back out of her prompt. That's how the Minecraft tools only
exist while `/minecraft` is on.

Everything missing gets a sensible default, so a plugin that only needs
`start()` is four lines. Settings live under `plugins` in `config.json`
keyed by `NAME`, read with `config.plugin_settings(NAME)`: the core
never learns what those keys mean.

A game gets most of its machinery from `plugins/_game.py`: the loop
that takes her turns while you're quiet (`_game.Loop`), settings over
defaults, guides from `agent/knowledge/<game>/`, and `record()`, which
writes each turn to the playlog and her memory of the session. A game
keeps only its own prompt, tools and rules.

A plugin that fails to import, or explodes on start, is reported and
skipped. It's an add-on; a broken one must not be why the app won't
launch.

```
> /plugins
  [!!] youtube      didn't load: ModuleNotFoundError: No module named 'googleapiclient'
```

### Keys don't go in config.json

`config.json` is in the repo, so a key pasted into it is a key on
GitHub. Read yours from the environment or from a file outside the repo
entirely:

```python
CREDENTIALS_FILE = os.path.expanduser("~/.config/ai-voice/yourplugin.json")
key = os.environ.get("YOURPLUGIN_KEY", "") or _stored().get("apikey", "")
```

Two things worth copying rather than rediscovering:

* **Tell a broken credentials file apart from a missing one.** Swallowing
  a JSON syntax error into an empty dict makes a misplaced comma look
  exactly like "no API key", and sends you hunting for a key that was
  there all along.
* **Reject placeholders.** `"PUT_YOUR_KEY_HERE"` is a non-empty string,
  so it passes every check, starts cleanly, and then fails at the far
  end where the only symptom is silence.

An account name or id belongs in the same file as the key, not in
`config.json`. They're one credential (the key belongs to that account),
and splitting them across two files buys you a mismatch that looks
exactly like a dead connection. Which channel to watch is not a
credential; that stays in `config.json` with the rest of the behaviour.

## The plugins

| Page | What's on it |
|------|--------------|
| [Stream chat](chat.md) | pomf.tv, Twitch, YouTube and IRC: answering your stream's chat, flood defences, what viewers can reach |
| [Games](games.md) | Minecraft, Zork, Vibe City, REALITI: playing on her own, her notes, watching her play |
| [Home and devices](devices.md) | Home Assistant, Lovense, Buttplug.io toys |
| [Asking a bigger model](ask.md) | Claude, Grok and ChatGPT: she asks one a question when you tell her to |
| [Cron and Discord](#sysadmin-cron-and-discord) | scheduled jobs, and the same Luna from your phone (below) |

## Sysadmin: cron and Discord

Every other plugin connects her to a *conversation*. These two give
her a sysadmin side: she looks after the machine on a schedule, and
she can be reached from anywhere, the way a homelab bot would be.
For putting them to work, with ready-made jobs, see [Sysadmin](sysadmin.md).
They're adapted from CR0N, a friend's Discord sysadmin bot. Its
scheduler and remote control came over; its regex-gated shell didn't
(see *What came across*).

| Layer | What it is | Out of the box |
|-------|------------|----------------|
| **Scheduler**: `plugins/cron.py` | Jobs she runs on her own on a timer, reporting out loud and in the TUI | off |
| **Discord**: `plugins/discord.py` | Remote access: the owner talks to her from a private channel or DM | off, and its writes ask |

**Both are off until you switch them on**, and neither does anything
on a fresh install. `/cron on` and `/discord on` save `"enabled": true`
into `config.json` so they come back next launch. If you share your
folder with someone, check those two keys (and
`files.auto_approve_sources`) first, or they get your switches too.

### Scheduled jobs

```
/cron on              /cron off              /cron       (jobs, last runs)
```

```json
"cron": {
    "enabled": false,
    "job_tools": ["get_datetime", "time_until", "system_status", "system_health",
                  "last_boot", "web_search",
                  "read_page", "list_files", "read_file", "write_file",
                  "edit_file", "recall_facts"]
}
```

Ask for one in plain words: *"every weekday at 8, check disk and VRAM
and note anything low in ~/luna-jobs/disk.md"*. She calls
`schedule_job`, and **you approve it in the popup** before it's saved.
This is the step where you hand her permission to act later, so it's
the step that asks. `list_jobs` and `cancel_job` cover the rest. All
three sit in the **Jobs** group of the tools pane, and they're only
offered while `/cron` is on.

Jobs live in `agent/cron.json` (gitignored, since it's yours) and can
be edited by hand:

```json
[{"name": "disk-check", "schedule": "0 8 * * 1-5",
  "task": "Check free disk and VRAM; note anything under 10% in ~/luna-jobs/disk.md",
  "speak": false}]
```

| Schedule | Means |
|----------|-------|
| `0 8 * * 1-5` | cron line: weekdays at 08:00 |
| `*/15 * * * *` | every quarter hour |
| `every 30m` / `every 2h` / `every 1d` | an interval, 5 minutes minimum, counted on your local clock (`every 1d` = local midnight, `every 2h` = 00:00, 02:00, ...) |
| `2026-10-07 08:00` | once, then removed |

* **`speak` defaults to `true`.** A job reads its report aloud, so set
  `"speak": false` on anything that fires at night.
* **Day-of-month and weekday are ANDed,** not cron's OR.
* **Missed runs are skipped, not caught up.** A 08:00 disk check is no
  use at 14:00. A one-off whose time passed while the app was closed
  shows in `/cron` as skipped and stays in the file until you delete it.
* **A broken `agent/cron.json` stops `/cron on`** with the parse error
  rather than starting with no jobs, so a stray comma doesn't look like
  everything got cancelled. A single bad entry is skipped, shown in
  `/cron`, and kept in the file when she saves.

### What a job turn is

A job firing is a turn of its own, not one of yours:

* **Fresh context, nothing stored.** It doesn't see your history, and
  its tool output (web pages, file contents) never lands in history,
  where it would be replayed into your private turns.
* **Its own tool list:** `job_tools`, enforced the same way as chat's.
  A job can never call `schedule_job`, so jobs don't breed jobs.
* **It waits its turn.** If you're mid-conversation it queues behind
  you, and a slow job isn't fired again on top of itself.
* **It's echoed** as `Job: disk-check` in the conversation and in the
  logbook. `/cron` shows the last result of each.

### Writing without asking: `job_write_dirs`

A job that can't write is half a job, and a popup at 3am is a no. So
there's one carve-out, and **it lives in `files`, not in the plugin**:

```json
"files": { "enabled": true, "approval_timeout": 120,
           "job_write_dirs": ["~/luna-jobs"] }
```

Inside those folders, a *job's* `write_file` / `edit_file` goes through
without the popup and is logged as `job_write_dirs, not asked`.
Everything else is unchanged:

* **Anywhere else asks.** Away from the keyboard that times out as a
  no, and her report says what she would have written.
* **The deny list still wins.** `.ssh`, `.env`, keys and the rest are
  refused before this check is ever reached.
* **`~` itself is ignored,** since that would be every file you own,
  and so is **anything overlapping this app's folder**. A job that can
  quietly rewrite her own code can switch this check off. (That's the
  exact hole CR0N had.)
* **Only job turns get it.** The flag is thread-local and set only by
  `assistant.respond_to_job`, under the turn lock. A reminder firing
  mid-job, or anything you type, still asks.
* **Symlinks don't escape.** Paths are resolved first, so
  `~/luna-jobs/up -> ~` writes to `~` and asks.

`read_page` is in the default `job_tools`, so a page a job reads can
try to steer what it writes. The worst it can do unasked is write
inside `~/luna-jobs`. Drop `read_page` from the list if that's still
too much.

A plugin is a file in a folder, and a permission a plugin can grant
itself is not a permission. The plugin only *labels* its turns as
jobs. Which folders that label unlocks is decided by you, in core
config.

### Discord: remote access

```
/discord on           /discord off           /discord    (status)
```

The second layer is CR0N's best idea: a private Discord channel (or a
DM) as a remote control. From your phone you get the same Luna as at
the desk. It's a normal private turn with your history and the full
tool list, and it waits its turn instead of cutting off whatever is
happening at the keyboard. Your message shows in the TUI as yours,
tagged `[discord]`.

#### Setup

```bash
pip install discord.py
```

Credentials go outside the repo:

```jsonc
// ~/.config/ai-voice/discord.json
{"token": "your-bot-token", "owner_ids": [123456789012345678]}
```

In the [Developer Portal](https://discord.com/developers/applications):
New Application → **Bot** → Reset Token (that's `token`), and switch on
**Message Content Intent** on the same page. Invite it under OAuth2 →
URL Generator with the `bot` scope and *Send Messages* / *Read Message
History*. For `owner_ids`: Discord Settings → Advanced → Developer
Mode, then right-click your name → *Copy User ID*. `DISCORD_TOKEN` in
the environment works instead of the file. With no token, or no owner
ids, `/plugins` shows it as `[--]` and says which is missing.

```json
"discord": {
    "enabled": false,
    "channel": "",
    "speak": false,
    "remember": true,
    "tools": null
}
```

| Key | |
|-----|--|
| `channel` | name or id of the one server channel she listens in. `""` = DMs only |
| `speak` | also read replies aloud at the desk. Off: whoever's in the room didn't ask |
| `remember` | `true` = part of your normal history, like a typed turn |
| `tools` | `null` = every tool. A list narrows it. **Don't delete the key**: missing, it falls back to the stream-chat list |

Every tool includes `clipboard` and `look_at_screen`, which means
"what's on my clipboard?" from your phone sends it to Discord. That's
the point of remote access, but if a password manager copies through
your clipboard, give `tools` a list without those two.

In Discord, `!stop` cuts off the reply in progress (CR0N's `!kill`)
and `!status` shows what `/discord` does. Long replies are split
under Discord's 2000-character limit. `/discord` also tells you why
it's quiet: a rejected token, Message Content Intent switched off, or
a non-owner it's been ignoring.

#### Writes and commands from Discord: approval

When a Discord turn wants to write a file or run a command, the
plugin's `approval` setting decides who says yes:

| Mode | What happens |
|------|--------------|
| `discord` (default) | She asks in the same chat: the command or the file change, then **y** / **n** (or tap ✅ / ❌). Only owner replies count. No answer in `approval_timeout` seconds (300) is a no |
| `auto` | Nobody is asked: it goes straight through. For automation |
| `desk` | The popup on the desk screen, as if you'd asked at the keyboard. From your phone that times out as a no |

```
/discord approval auto|discord|desk     switch it (saved)
/discord                                shows the current mode
```

```json
"discord": { ..., "approval": "discord", "approval_timeout": 300 }
```

Every command a Discord turn runs is also shown at the desk as
`discord ran: ...`, and every approval, denial and timeout goes in the
log.

On `auto`, security is the owner's to assume: **whoever holds the bot
token, or an owner's Discord account, has a shell on this machine,** and
so does a web page she reads during a Discord turn if it talks her into
running something. These guards stay on in every mode:

| Guard | Why |
|-------|-----|
| Only `owner_ids` are obeyed; everyone else is ignored and logged | Without it, anyone who can type in the channel has remote access |
| The Permissions switches in the tools pane | Execute *off* takes commands away from Discord too; read and write *off* the same |
| The file deny list (`.ssh`, `.gnupg`, `.env`, `~/.config/ai-voice`, keys, shell startup files) | `read_file` and `write_file` refuse them, including the bot token. A *command* isn't bound by it |
| File writes to Luna's own folder, `~/.config`, `~/.local` always ask, even on `auto` | A write there is code that runs later |

The approver is attached to the Discord turn's own thread by
`assistant.respond_remote`, so a reminder or a job firing at the same
time still follows its own rules. `files.auto_approve_sources` and
`shell.auto_approve_sources` still exist for other remote sources, but
Discord doesn't need them any more.

### What came across from CR0N, and what didn't

| From CR0N | Here |
|-----------|------|
| Scheduled autonomous tasks, 👍 before scheduling | `schedule_job` + popup approval |
| Reminders vs tasks ("who holds the verb?") | `set_reminder` pings *you*; `schedule_job` is work *she* does |
| Every action logged | logbook, plus the `Job:` line on screen |
| Turn budget and stuck-loop detection | not yet. Jobs run under the normal tool-round limit |
| `!kill` mid-run | `!stop` in Discord |
| Helper delegation to other PCs | not planned |
| Remote access over Discord, no approval | `plugins/discord.py`: `approval` auto, or ask in the chat, or ask at the desk |
| `bash` with regex auto-approve | `run_command`: asks at the desk or in Discord, or runs straight through on `approval: auto` (no regex) |
| `pass` password store | **no** |
| Write-guard on its own code by path string | **no.** Paths are resolved, and the app folder is excluded outright |

Both plugins are tracked in git like every other plugin. Neither holds
anything personal: the token lives in `~/.config/ai-voice/`, and your
jobs in the gitignored `agent/cron.json`.
