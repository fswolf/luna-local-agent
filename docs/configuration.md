# Configuration

Two files, two jobs.

| File | Holds | You edit it when |
|------|-------|------------------|
| `agent/agent.json` | Who she is — name, personality, tone, traits, rules | You want her to behave differently |
| `config.json` | How the machine runs — voice, models, thresholds, timeouts, theme | You want it to work differently |

They used to be one file, which meant tuning a VAD threshold and
rewriting her personality were the same edit — and you couldn't share
either one without handing over the other.

Where both define a key, `config.json` wins. `agent.json` is still read
as a fallback, so an older install that never split them keeps working
untouched.

Every block in `config.json` is optional and every value has a default
in `config.py`, so a missing block means "use the defaults" rather than
an error. The file that ships has them written out explicitly, because
you can't turn a dial that isn't there.

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
fatal — hand-editing them is the whole point of their being JSON.

## Changing settings without leaving the terminal

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
restart. Most take effect at once; the few that don't — a Whisper model
size, a wake word file — say so rather than pretending.

That split is real, not cosmetic. Settings are read once at import and
copied into constants, which is why they can't normally change at
runtime. The ones worth tuning by ear are read from the config module
at the point of use instead, because tuning is a loop of *change it,
say something, listen, change it again* and a restart each time around
makes it useless.

`/mode` saves too — a mode you picked and then lost on restart is just
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
silence — which is a bug that otherwise costs a screenshot and an hour
to find.

```json
"logging": { "enabled": true, "level": "info", "max_kb": 1024, "keep": 3 }
```

`debug` adds every VAD decision and tool argument, which is a lot;
`info` keeps what went wrong and the reasoning behind it.
