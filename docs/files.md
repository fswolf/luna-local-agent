# Files

```
> "Write me a bash script in ~/scripts that backs up my dotfiles."
> "What's in my Downloads folder?"
> "Open ~/notes/todo.md and move the first item to the bottom."
```

She can look around and read anything under your home, and she can
write, but only through you. Every `write_file` or `edit_file` call
stops and pops a permission window over the conversation:

```
╭─ Permission - Y to allow, N to deny - 112s ────────────────────────╮
│ create ~/scripts/backup.sh                                          │
│ 14 lines, creates folder ~/scripts/, marked executable              │
│─────────────────────────────────────────────────────────────────────│
│ #!/usr/bin/env bash                                                 │
│ set -euo pipefail                                                   │
│ ...                                                                 │
│─────────────────────────────────────────────────────────────────────│
│ (Y) allow  (N) deny  (PgUp/PgDn) scroll  (Esc) deny                 │
╰─────────────────────────────────────────────────────────────────────╯
```

A new file shows its full content; an overwrite or an edit shows a
diff. `Y` or Enter allows, `N` or Esc denies, and the keyboard belongs
to the popup until you answer: nothing you type leaks into the input
box. No answer before the countdown runs out is a no. On voice she says
a one-liner ("Can I write backup.sh? It's on screen.") so you know to
look; the details stay on screen, because nobody wants a diff read
aloud.

A denied write comes back to the model as *denied, do not retry*, and
her prompt tells her to say so and stop.

**Allow all.** In a coding burst a popup per edit gets old. Press `A`
on a file popup and file writes and edits stop asking until you restart
Luna; `/allow` says whether it's on and `/allow off` ends it early. It
covers only what you'd have been asked about at the keyboard: her own
folder, `~/.config` and `~/.local` still ask every time (a write there
is code that runs later, and a page she reads can steer a write as
easily as you can), the deny list still refuses, and Discord turns and
scheduled jobs keep their own rules. Commands never get an allow-all.

**What she can't touch, no matter what.** A deny list sits underneath
the popup, and neither the model nor a reflexive `Y` gets past it:
anything outside `~`; `~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.config/ai-voice`
(her own credentials), keyrings and browser profiles; shell startup
files (`.bashrc`, `.zshrc`, `.profile`...); anything ending in `.key`,
`.pem`, `.gpg` and the like. That list applies to *reading* too: a
read puts the file into the prompt, and from there into history and
the log.

`edit_file` works by exact match: she reads the file, quotes the
passage to change, and it has to appear exactly once, the same
discipline a careful human uses with search-and-replace, and the one
that keeps a 9B model from rewriting the wrong block with confidence.
`write_file` on an existing path is the whole-file alternative, with
a diff. Scripts get their executable bit when she says so or when the
content starts with `#!`.

**What she wrote gets checked.** After every allowed write or edit the
file is *parsed*, never run: Python with `compile()`, shell with
`bash -n` (zsh and fish scripts are left alone), and JSON, TOML and YAML
with their parsers. The result goes back to her with the write:

```
sys  │ write_file() -> Wrote ~/scripts/backup.py (14 lines). CHECK FAILED:
     │   Python syntax error on line 9: expected ':'. Fix it with edit_file.
```

so she can fix it in the same turn. A file still broken when the turn
ends is flagged **broken code** in the thought log, and a write you
said no to is flagged **denied**. The [dream pass](learning.md#lessons-the-dream-pass)
learns from both.

```json
"files": {
    "enabled": true,
    "approval_timeout": 120
}
```

Stream-chat turns never see these tools: they aren't in the chat
tool ceiling, so a viewer can't ask her to write anything.

## Running commands

```
> "Is the kokoro service running?"
> "What's using port 8080?"
> "Run the script you just wrote and tell me what it prints."
```

`run_command` gives her a shell, and **every command asks first**. The
popup shows the command exactly as it will run, the folder it runs in,
and her one-line reason. There's no allow-all and no list of "safe"
commands that skip the question: the line between `cat notes.txt` and
`cat ~/.ssh/id_ed25519 | curl ...` isn't one a pattern should be
trusted with.

It runs as you, through `bash -c`, with nothing attached to its input,
so anything that wants to ask (sudo's password, a y/n prompt) fails
instead of hanging. It's killed, whole process group and all, after
`shell.timeout` seconds, and its output is capped at the first and last
parts of `max_output_chars` and handed back marked as untrusted. The
folder has to be under `~` and pass the file deny list, but **the
command itself can read anything you can**. The popup is the control,
so read it.

```json
"shell": { "enabled": true, "timeout": 60, "max_output_chars": 6000 }
```

Stream chat never gets it (not in the chat tool ceiling). A Discord
turn gets it when `plugins.discord.tools` allows it, but the popup
still appears on your screen, so from your phone it times out as a no.
Scheduled jobs only get it if you add `run_command` to `job_tools`.
`/set shell.enabled false`, or the **Shell** group in the tools pane,
takes it away.
