# Skills (recipes)

A small model is bad at planning a job from nothing and good at
following a worked example. So when a job of several steps goes right,
Luna writes the steps down as a recipe, you approve it, and the next
time you ask for something like it the recipe comes along in her
prompt. Do it once by hand, and from then on it's one sentence.

How the library works inside is in
[Learning from herself](learning.md#recipes-the-skill-library). This
page is about using it, with a walkthrough at the end.

## What a recipe is

A name, when to use it, and the steps that worked, written as
instructions to herself:

```
Recipes you've saved for jobs like this:
#3 check whether the voice server is up (use when: is kokoro running)
  1. run_command: curl -s http://127.0.0.1:8899/health
  2. if nothing answers, run_command: tail -20 ~/.cache/ai-voice/kokoro.log
  3. tell him which it is, and the last error line if there is one
```

| Part | What it holds |
|------|---------------|
| Name | a few words saying what the job is |
| Use when | what you'd say when you want it. This is what she matches against, so it matters most |
| Steps | 2 to 12, in order, naming the tools and the exact commands that worked |
| Tools | which tools that turn used, noted on its own |

Saving the same job again updates the recipe instead of adding a second
one. They live in `agent/skills.db` on your machine (gitignored).

## How one gets saved

Two ways: she offers after a job that took several steps and worked
(the `save_skill` tool), or you tell her ("remember how you did that").
Either way a popup shows the whole recipe before anything is kept,
because it will ride in her prompt later. If that turn read a web page,
an email or a file, the popup says so, so you can check the steps are
yours and not something she read. On Discord the question comes in the
chat.

```
╭─ Luna wants to save a recipe ──────────────────────────────────────╮
│ name: check the VM's health                                        │
│ use when: check vm health, how is the virtual machine doing        │
│                                                                    │
│ 1. run_command: bash ~/ai-voice/agent/jobs/vm-health.sh            │
│ 2. report what it printed: anything failed, full or erroring first │
│ 3. if it can't reach the VM, say so and stop                       │
╰────────────────────────────────────────────────────────────────────╯
```

At most five a session, so a chatty evening doesn't fill the library.

## How one comes back

Only when it clearly fits what you just said, and at most
`self.skills_in_prompt` (2) at a time: a recipe is a paragraph, and an
unrelated one isn't worth its place in the prompt.

- **With the embedding server up** she matches by meaning, so "is the
  VM ok?" finds "check the VM's health".
- **Without it**, at least two real words have to match the name or the
  use-when line, and everyday words like "check", "please" or "set up"
  don't count.

So write the use-when line with every way you'd say it: "vm health"
and "virtual machine" both.

Following a recipe changes nothing about approvals. A step that runs a
command still pops up, every time.

## Walkthrough: "check vm health"

The most useful recipes wrap a script of your own: she can't run a
command without you, but she can remember which one to ask for and how
to read what it prints. Here's a health check for another machine on
your network, start to finish. Swap in your own address;
`you@192.168.1.20` is a stand-in.

### 1. Key login, so nothing asks for a password

On the computer Luna runs on. Skip the first line if you already have a
key:

```bash
ssh-keygen -t ed25519
ssh-copy-id you@192.168.1.20
ssh -o BatchMode=yes you@192.168.1.20 uptime
```

The last line has to print the uptime without asking anything.
`BatchMode` makes SSH fail instead of waiting for a password, which
matters because her commands run with nothing on their input. No
password is ever written down: not in the script, not in the recipe,
not in her memory. She can't read `~/.ssh` herself and doesn't need to;
SSH uses your key on its own.

### 2. The script

Scripts go in `agent/jobs/` inside Luna's folder. It's gitignored, so
your host names stay yours, and it can't be a `job_write_dirs` folder,
so no scheduled job can quietly change a script you'll later approve
without reading. Save this as `~/ai-voice/agent/jobs/vm-health.sh`:

```bash
#!/usr/bin/env bash
# The VM at a glance, read-only: up, load, memory, disks,
# failed services, errors since boot.
VM=you@192.168.1.20

ssh -o BatchMode=yes -o ConnectTimeout=5 "$VM" 'bash -s' <<'EOF' || echo "Can't reach the VM over SSH (is it on, and does key login work?)"
echo "== $(hostname): up $(uptime -p | sed 's/^up //'), load $(cut -d' ' -f1-3 /proc/loadavg) on $(nproc) cores"
echo "== memory"; free -h | sed -n '1,3p'
echo "== disks"; df -h -x tmpfs -x devtmpfs -x squashfs -x overlay -x efivarfs 2>/dev/null
echo "== failed services"; systemctl --failed --no-legend --plain 2>/dev/null | grep . || echo "none"
echo "== errors since boot, by count"
journalctl -b -p err --no-pager -o cat 2>/dev/null | sort | uniq -c | sort -rn | head -10 | grep . || echo "none"
EOF
```

Keep it read-only: it looks, it never restarts or deletes anything.
Plain text with a `==` heading per part is easy for her to read back to
you. If the far end can't read its journal, add your user to the
`systemd-journal` group there (`adm` too, for Apache's logs).

### 3. Run it yourself once

```bash
bash ~/ai-voice/agent/jobs/vm-health.sh
```

If it prints the report, she'll get the same report. If it hangs or
asks for a password, go back to step 1.

### 4. Ask her, by full path

"Run `bash ~/ai-voice/agent/jobs/vm-health.sh` and tell me how the VM
is doing." Approve the popup. Give the full path (wherever Luna lives):
her commands start in your home folder, so `agent/jobs/vm-health.sh` on
its own won't be found.

### 5. Tell her to remember it

Once the report is right: "Remember how you did that, as check vm
health or check the virtual machine's health." The recipe popup comes
up. Before you approve, read it:

| Look for | Why |
|----------|-----|
| The step runs the script by its full path | a relative path fails the next time |
| No numbers from today | "disk is 41% full" in a step gets repeated next week whatever the disk says |
| Only tools that really ran | a recipe is what worked, not what she imagines might |
| Both ways you'd say it in "use when" | so it comes back however you ask |

Not right? Deny it and say what to change: "save it again: step one
runs the script, step two reports plainly, no other tools." A denied
recipe isn't kept, and saving the same job again updates it.

### 6. From now on

"Check vm health." The recipe comes along, she asks to run the script,
you approve, and she tells you what matters: something failed, a disk
filling up, the same error a hundred times. From Discord it works the
same, with the approval in the chat.

## One more machine

Copy the script, change the address and what it checks. A web server
might list the sites Apache serves, the answer each gives and how many
days each certificate has left; a NAS might list its containers and how
full each share is. Save it as its own file in `agent/jobs/`, run it
once, ask her once, and save it as its own recipe ("check nuc health",
"is the web server ok"). The scripts in there make good templates for
each other, and since none of them hold a password, they're safe to
copy around.

## Asked for, or on a timer

A recipe is for when you ask. For a timer, name the same script in a
scheduled job: *"every Sunday at 4, run backups-to-nas.sh and tell me
if anything failed."* The popup shows the whole script; approve it once
and the scheduler runs exactly that text each time, with no popup at
4am, and she reads you what it printed. Change the script and it won't
run until you approve the new text. See
[Scheduled jobs](jobs.md#walkthrough-weekly-backups-to-the-nas).

## Your controls

| Command | What it does |
|---------|--------------|
| `/skills` | lists the recipes she has |
| `/skills show <n>` | prints one in full |
| `/skills forget <n>` | hides it; it stops coming back |
| `/skills retired` | lists hidden ones |
| `/skills restore <n>` | brings one back |

Nothing is deleted. Past `self.max_skills` (60) the least used is
retired on its own. `self.skills` turns the whole thing off.
