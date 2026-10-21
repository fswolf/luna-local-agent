# Configuration

Two files, two jobs.

| File | Holds | You edit it when |
|------|-------|------------------|
| `agent/agent.json` | Who she is (name, personality, tone, traits, rules) and who you are | You want her to behave differently |
| `config.json` | How the machine runs: voice, models, thresholds, timeouts, theme | You want it to work differently |

They used to be one file, which meant tuning a VAD threshold and
rewriting her personality were the same edit, and you couldn't share
either one without handing over the other.

Where both define a key, `config.json` wins. `agent.json` is still read
as a fallback, so an older install that never split them keeps working
untouched.

## Who she's talking to

`agent.json` has a `user` block, so her prompts say "when she asks" or
"tell him instead" correctly rather than assuming:

```json
"user": {"name": "Shannon", "pronouns": "she/her"}
```

- `pronouns`: `he`, `she` or `they` (anything after the first slash is
  just for reading: `she/her` is `she`). Your own set works as three
  words, subject/object/possessive: `xe/xem/xyr`.
- `name`: what she calls you in her own notes ("Shannon asked...").
  Leave it out and she says "the user".
- No `user` block at all: "the user" and he/him everywhere, and no
  line about you in her system prompt.

It changes the wording of her instructions, not her personality: if
the personality text itself says "him", edit that too. Restart after
changing it.

Every block in `config.json` is optional and every value has a default
in the `config/` package (one file per area: `voice.py`, `listening.py`,
`moods.py`...), so a missing block means "use the defaults" rather than
an error.

`config.json` is yours and never goes to GitHub (it's in `.gitignore`).
What ships is `config.example.json`, the defaults written out
explicitly, because you can't turn a dial that isn't there. The first
start copies it to `config.json`; after that, updates never touch your
copy. A setting added in a later version takes its default from the
code until you set it, and `config.example.json` shows it so you can.

```json
{
    "voice": "af_bella",
    "generation": { "max_tokens": 4800, "reasoning": "low" },
    "stt":        { ... },
    "tts":        { ... },
    "vision":     { ... },
    "desktop":    { ... },
    "mood":       { ... },
    "files":      { ... },
    "plugins":    { ... },
    "wake_word":  { ... },
    "tools":      { ... },
    "web_search": { ... },
    "reminders":  { ... },
    "alarms":     { ... },
    "history":    { ... },
    "long_term_memory": { ... },
    "thoughts":   { ... },
    "adaptive":   { ... },
    "monitor":    { ... },
    "self":       { ... }
}
```

A syntax error in either file is reported and skipped rather than being
fatal: hand-editing them is the whole point of their being JSON.

## Changing settings without leaving the terminal

### The settings pane

Press **Tab three times** (conversation, help, tools, then settings).
It lists every setting `config.json` can hold, over 300 of them, grouped
by section, with a heading per plugin. Each row shows the name, its value
and a line saying what it does:

```
 Listening
 > mode                       auto                 How listening starts and stops: auto (HOME starts, ...
   vad                        auto               ↻ What decides you're talking: silero (a speech model)...
   silence_seconds            1.2                  Seconds of silence after you speak before she stops...
```

- A green value is set in your `config.json`; a grey one is the default.
- `↻` means a change takes effect on the next start; everything else
  applies at once, the same split `/set` uses.
- Passwords, tokens and keys show as `••••`, never in clear.

| Key | Does |
|---|---|
| Up / Down, PgUp / PgDn, wheel | Pick a setting |
| Space | Flip an on/off, step through a choice (`stt.mode`, `portrait.frame`...) |
| Enter | The same, or open a box to type a value: a number, text, or a comma-separated list |
| `/` | Filter: only the settings whose name or line matches, narrowing as you type. Esc clears it |
| `x` | Back to the default: takes the setting out of `config.json` (after a restart) |
| Esc | Cancel the edit box, clear the filter, then close the pane |

Values are checked before they're saved: a number has to be a number, a
choice one of its choices. A nested block like `mcp.servers` is shown but
edited in the file. What each setting is (its kind, allowed values and
explanation) lives in `config/schema.py`; a test fails if a setting in
`config.example.json` or the `/set` table isn't described there.

### /set

`/set` lists everything you can change, with its current value:

```
> /set
  [stt]
    stt.barge_in_margin              2.5
    stt.vad_threshold                0.4
    stt.model                        small   (needs a restart)
  [tts]
    tts.speed                        1.0
```

```
> /set stt.barge_in_margin 3.5
stt.barge_in_margin = 3.5 - saved
```

Changes are written to `config.json` immediately, so they survive a
restart. `/set` also takes any setting the settings pane knows (a
plugin's, the theme's...); those are saved for the next start. Most take effect at once; the few that don't (a Whisper model
size, a wake word file) say so rather than pretending.

That split is real, not cosmetic. Settings are read once at import and
copied into constants, which is why they can't normally change at
runtime. The ones worth tuning by ear are read from the config module
at the point of use instead, because tuning is a loop of *change it,
say something, listen, change it again* and a restart each time around
makes it useless.

`/mode` saves too: a mode you picked and then lost on restart is just
an annoyance.

---

# Logging

Writes to `~/.cache/ai-voice/ai-voice.log`, rotating so it can't grow
without bound. `/log` tails it without leaving the app.

It records decisions, not just errors. "TTS failed" is a line anyone
would write; the one that earns its keep looks like this:

```
[barge-in] fired | level=0.0412 baseline=0.0040 needed>0.0100
           speech=0.96 threshold=0.65 held=0.35s
```

A baseline sitting exactly on the floor means calibration ran during
silence, which is a bug that otherwise costs a screenshot and an hour
to find.

```json
"logging": { "enabled": true, "level": "info", "max_kb": 1024, "keep": 3 }
```

`debug` adds every VAD decision and tool argument, which is a lot;
`info` keeps what went wrong and the reasoning behind it.
