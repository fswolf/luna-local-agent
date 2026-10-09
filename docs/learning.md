# Learning from herself

Eight things that make her a little better each day, and more aware of what's around her. None of them
changes the model's weights. They change what she gets told about
herself, and all of it is written down where you can read it, edit it,
or switch it off.

| Part | What it does | Where to look |
|---|---|---|
| Lessons (the dream pass) | reads back her own turns that went wrong and writes one-line lessons she follows from then on; she can also note one herself, with your OK | `/lessons` |
| Episodic memory | a few sentences of her own notes on each conversation | `/episodes` |
| Fact cleanup | merges facts that say the same thing twice, retires the losing side of a contradiction | `/facts retired` |
| Calibration | says so out loud when her token probabilities say she didn't know | the thought log's **overconfident** flag |
| Startup greeting | after a break, opens by picking up where you left off | the first thing she says |
| Recipes (skill library) | saves the steps of a multi-step job that went right, and brings them back for similar jobs | `/skills` |
| Ongoing projects | work that spans sessions: the goal, what was tried and found, the next step | `/projects` |
| Situation block | a few live lines each turn: your focused window, music, machine load, running plugins, next reminder | `/situation` |

Each one switches on and off in the tools pane's **Learning** group, or
with `/set self.<name> false` (`/set situation.enabled false` for the
situation block).

## Lessons: the dream pass

Once a day (`self.reflect_every_hours`), when she's been idle for ten
minutes, she reads back her own recent turns that went wrong. That
means turns with a review flag, turns where her measured confidence was
low, and turns where the next thing you said started with "no", "wrong"
or "actually". She writes at most three lessons. Each one is about her
own behaviour, specific enough to act on, and cites the turns it came
from:

```
LESSON: When asked what day a date falls on, call time_until instead
of working it out. (#212, #230)
```

The lessons most relevant to what you just said ride in her prompt
(`self.lessons_in_prompt`, 4 by default; all of them while there are
only a few). This is the mini-AGI idea without retraining: she gets
better through what she remembers, not new weights. A lesson that says
the same thing as one she already has is not added; the old one gets
the credit instead. Past `self.max_lessons`, the least-used old lesson
is retired.

```
/reflect                 run the whole pass now: notes, lessons, fact cleanup
/lessons                 what she's learned, with the turns each came from
/lessons forget 3        hide one from her (kept, not deleted)
/lessons retired         the hidden ones; /lessons restore 3 brings one back
```

Facts about you aren't lessons; those go through memory as before.
A flag is a hint, not proof, and the prompt tells her so: a turn that
was actually fine teaches her nothing. Lessons from the background pass
show up on screen as **Luna reflected - …** so you see each one as it
arrives. The turns she reads are marked as records, and a flag that
quotes a web page or a file is shown to her by tool name only, so
text from outside can't dictate a lesson.

She can also do this herself:

- **`note_lesson`**: when you correct *how* she did something, she can
  write the lesson down then and there. It pops the same approval window
  as a file write, and only a yes saves it. She can't use it on a turn
  that read a web page, a file or the screen, and she gets three per
  session; the rest wait for the daily pass.
- **`reflect_now`**: she runs the whole pass herself (after a run of
  mistakes, or when you ask her to reflect). It waits for the current
  reply to finish so it doesn't slow her down, and runs at most once an
  hour.

## Episodic memory and continuity

Facts are things like "Ryan has a 6950 XT". Episodes are things like
"we spent the evening fixing his waybar; unfinished: he wants the
clock on the left". After `self.idle_minutes` (30) of quiet, or at the
next startup, each finished conversation becomes 2-4 sentences of her
own notes, from the transcript. Her notes on the most recent one are
always in her prompt. Older ones come back when they bear on what's
being said (by meaning when the embedding server is up), up to
`self.episodes_in_prompt`.

At startup the previous session is written up first. Then, if it's
been more than `self.idle_minutes` since you last talked, she opens
the session herself: a line or two that picks up anything left
unfinished. The notes also show on screen as **Last time (…)**. Turn the
greeting off with `/set self.greet false` and you keep the notes.

The first run only writes up the last three conversations, not your
whole transcript. Stream chat never sees any of it: a turn from chat
gets no lessons, no episodes and no "last time".

```
/episodes                the last eight, newest first
/episodes forget 4       delete one
```

The prompt only carries older notes that are clearly about what's being
said. For anything else she has **`recall_episodes`**: she searches her
own notes when you ask "what did we decide about the waybar last
month?", and uses `search_history` when she needs the exact words.

## Recipes: the skill library

A small model is bad at planning a multi-step job from nothing and good
at following a worked example. So when she finishes something that took
several steps and it went right, the steps get saved as a named recipe,
and the next time something similar comes up the recipe rides along in
her prompt:

```
Recipes you've saved for jobs like this:
#3 check whether the voice server is up (use when: is kokoro running)
  1. run_command: curl -s http://127.0.0.1:8899/health
  2. if nothing answers, run_command: tail -20 ~/.cache/ai-voice/kokoro.log
  3. tell him which it is, and the last error line if there is one
```

- **How one gets saved:** she calls `save_skill` after a job works, or
  when you say "remember how you did that". **You approve it on screen**,
  like a lesson, because it goes into her prompt. If the turn read a web
  page, a file or the screen, the popup says so, so you can check the
  steps say what you'd want.
- **What it remembers:** a name, when to use it, 2 to 12 steps, and
  which tools that turn used. Saving the same job again updates the
  recipe instead of adding a second one.
- **When it comes back:** only when it clearly fits what you just said
  (by meaning when the embedding server is up, otherwise at least two
  shared words), at most `skills_in_prompt` (2) at a time. A recipe is a
  paragraph, so an unrelated one isn't worth its tokens.
- **Your controls:** `/skills` lists them, `/skills show <n>` prints one,
  `/skills forget <n>` hides it, `/skills retired` and
  `/skills restore <n>` bring one back. Nothing is deleted, and over
  `max_skills` (60) the least-used is retired.

Stored in `agent/skills.db` (gitignored). Following a recipe still goes
through every normal approval: a step that runs a command still asks.

## Ongoing projects

Her conversation notes say what happened; a project says where a piece
of work stands. "We're fixing the Mac audio" becomes a project with a
goal, a running log of what was tried and found, and the next step, and
it rides in her prompt every session until it's done:

```
Ongoing projects with the user:
#1 fix the Mac audio (goal: Luna's voice plays on NZ_Kitty's Mac) - last touched 2 hours ago
   tried: afplay with resampling
   found: the headphones refuse 24 kHz; 44.1 kHz plays
   next: ask if she heard Luna after pulling
Paused projects: #2 build a Zork primer
```

| Tool | |
|---|---|
| `start_project` | starts tracking work that will outlast this conversation |
| `update_project` | records what was **tried**, what was **found**, a **decision**, the **next** step, or a new status (`paused`, `done`) |
| `project_notes` | the whole log, so she doesn't suggest what already failed |

- **Which ones she sees:** every active project while there are up to
  `projects_in_prompt` (3); past that, the ones matching what you said
  plus the most recently touched. Paused ones get a single line, so she
  knows they exist. Done ones drop out.
- **No popup.** A project is a work log built from your own conversation,
  not an instruction to her, so it doesn't ask first. You can see and
  steer every one of them.
- **Your controls:** `/projects` lists them, `/projects show <n>` prints
  the log, `/projects done|pause|resume <n>` changes the status,
  `/projects drop <n>` hides one and `/projects restore <n>` brings it
  back. `/projects dropped` lists the hidden ones.

Stored in `agent/projects.db` (gitignored). At most six active at once.

## The situation block

A few live lines at the top of every one of your turns, so she isn't
starting blind:

```
Around you right now:
- Focused window: firefox - Hyprland Wiki
- Playing: Daft Punk - Veridis Quo (playing)
- Machine: CPU 18%, RAM 21.4 of 31.2 GB free, GPU 34% busy (VRAM 11.2/16 GB)
- Running: minecraft, zork
- Next reminder: tomorrow 09:00 - take the bins out (in 18 hours)
```

| Line | Comes from |
|---|---|
| Focused window | the focused window on Hyprland, skipping her own terminal (the front app on a Mac) |
| Playing | `playerctl`, when something is playing |
| Machine | CPU load, free RAM, and the GPU's load and VRAM |
| Running | plugins that are on |
| Next reminder | the soonest one, and how many more |

Anything that can't be read is left out, never guessed. It's cached for
a few seconds and costs roughly 60 to 100 tokens. Stream chat never gets
it: your window title and your music are your business.

**Toggle:** the **situation block** switch in the tools pane's Learning
group, or `/set situation.enabled false`. Each line can be switched off
in `config.json`. `/situation` shows exactly what she'd see right now.

```json
"situation": {
    "enabled": true,
    "window": true, "music": true, "machine": true,
    "plugins": true, "reminders": true
}
```

## Fact cleanup

The same pass compares remembered facts that look alike (by meaning
with the embedding server, by shared words without it) and asks her
about each close pair: same thing, contradiction, or different facts?
Duplicates get merged into one. In a contradiction the losing fact is
**retired**, not deleted: `/facts retired` and the memory manager still
have it. Each pair is only asked about once. This needs the sqlite
memory backend.

## Calibration

On llama-server her token probabilities measure how sure she actually
was. When a reply measured under `self.hedge_below` (60%) *and* had a
run of coin-flip tokens in it (a name, a date, a number she was guessing
at), didn't call a tool, and didn't already hedge, two things happen.
The run matters: playful banter averages low because there are lots of
ways to word it, and that isn't a guess.

- she adds `self.hedge_line` out loud ("I'm not totally sure about that
  one, though.");
- her next prompt tells her how sure that reply was, so "are you sure?"
  gets an honest answer without a tool call.

With `hedge_line` set to `""` she stays quiet, and the thought log flags
the reply as **overconfident** ("sounded sure at 38%, and didn't say
so"). The dream pass reads those flags. Reminders, alarms and her
startup greeting are never hedged.

## `self_status`

A tool in the *Self* group, next to `introspect`. Ask her how she's
doing and she can answer from measurements:

- which model and server she's on;
- how full her context window is;
- her mood dials;
- how long she's been up;
- today's average confidence, how many replies came in under the
  threshold, and how many of those she admitted to;
- today's review flags and second looks;
- how many facts, lessons and past conversations she has;
- her newest lesson.

It's read-only, and it isn't in stream chat's allowed tools.

## Coding: checking what she wrote

`write_file` and `edit_file` now parse what they just wrote: Python
with `compile()`, shell with `bash -n`, plus JSON, TOML and YAML.
Nothing she wrote is ever *run*. The verdict goes back to her in the
tool result ("CHECK FAILED: Python syntax error on line 7 … Fix it with
edit_file"), so she can fix it in the same turn. A file that's still
broken when the turn ends gets a **broken code** flag. If you say no
to a write, that's a **denied** flag instead of "tool failed", so the
dream pass can tell "the tool broke" from "he didn't want that". A
failed tool's flag now names the tool and keeps its error message, so
a lesson can say *why* ("copy the exact indentation for edit_file").

## Stream chat sees none of it

A turn from stream chat gets her persona and the clock. It doesn't get
your history summary, your remembered facts, her lessons or her session
notes. The self tools refuse on a chat turn even if a model names one
it wasn't offered, and now *every* tool does: a call to a tool the turn
wasn't given is refused before it runs.

```json
"self": {
    "lessons": true, "lessons_in_prompt": 4, "max_lessons": 40,
    "reflect_every_hours": 20,
    "episodes": true, "episodes_in_prompt": 2, "idle_minutes": 30,
    "tidy_facts": true,
    "calibration": true, "hedge_below": 0.6,
    "hedge_line": "I'm not totally sure about that one, though.",
    "greet": true,
    "skills": true, "skills_in_prompt": 2, "max_skills": 60,
    "projects": true, "projects_in_prompt": 3
}
```

Everything is stored in `agent/notebook.db` (gitignored). `/context`
shows what lessons, recipes and past sessions cost, under **lessons,
recipes, projects + past sessions**, and the situation block under **situation
(live)**. Usually it's a hundred or two tokens.
