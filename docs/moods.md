# Moods

Off the clock and the shape of the session, she runs a little warmer or
flatter, and it reaches the model as exactly one line of the system
prompt:

```
Right now you feel tired and glad of the company. Let that colour how
you sound - length, warmth, how playful you are - and nothing else.
```

Two dials, `energy` and `warmth`, each −1 to +1. Energy has three
bands and warmth four, giving twelve distinguishable states:

|              | flat | level | wired |
|--------------|------|-------|-------|
| **soft**     | cozy | doting | giddy |
| **fond**     | drowsy | warm | bright |
| **steady**   | flagging | level | keen |
| **prickly**  | worn thin | terse | restless |

Two dials rather than one, because a single dial can't tell "tired and
happy" from "awake and fed up", which are the two that actually turn up
at 4am. Warmth gets the extra band because three weren't enough: the
top one started at `0.35`, so a couple of turns of being nice to her ran
the dial into it and everything after that changed nothing you could
see. The current state rides on the Status row, `Idle · drowsy`, since
it's part of what state she's in, and `/mood` prints both dials with the
band each is sitting in plus what your last message scored, so "is this
even firing?" is something you can look at rather than infer.

Warmth also lifts energy a little: being fond of the company takes some
of the edge off being tired. Enough to move a cell, never enough to fake
wide awake at five in the morning.

**Warmth drifts home asymmetrically**, and this is the part that makes
the whole thing feel alive rather than nailed down. Coming back *up*
from a cold patch is quick: an assistant you have to coax out of a sulk
is a worse assistant. Coming back *down* from warmth you earned is slow.
Without that split the pull ate every kind word on the turn after it
landed: at a resting warmth of `+0.63`, affection put `+0.045` on the
dial and the drift took `-0.045` straight back off, so a clear
compliment moved her by `+0.0002`. It read as broken. It was just
critically damped.

**Almost everything here is free**: no sentiment scoring, no model
call. The shape of a session turns out to be the more honest signal
anyway. (The one exception is affection, below.)

| Signal | Effect |
|--------|--------|
| Time of day | The baseline: 6am and 9pm aren't the same person |
| Day of week | Friday evening lifts, Monday morning doesn't; weekends rest warmer |
| Hours at it | A long session wears her down, capped so it bottoms out |
| How long you were gone | A curve, not a switch: see below |
| What the machine did | A GPU pinned for hours means you were *around*, just elsewhere |
| Stream chat | A busy room is company; a dead one is a quiet night |
| Being kind to her | A short model call rates your message 0-3; she warms to it |
| Errors | A failed turn is dispiriting; a run of them compounds |
| A clean run | Ten turns where nothing broke lifts her a little |
| Barge-in | Being talked over, repeatedly, is wearing |
| Tempo | Fast short turns read as being in it together |

Every turn also pulls both dials back toward baseline, and the baseline
for warmth is *warm*. Without that, one bad five minutes would set the
tone for the evening, and an assistant you have to manage out of a
sulk is a worse assistant.

**Being away is a curve, not a switch.** This assistant spends most of
its life waiting, so "you came back" deserves more than one branch:

| Gone for | What it does |
|----------|--------------|
| under 30 min | nothing: you didn't really leave |
| a few hours | a small lift |
| most of a day | energy, mostly: it reads as a fresh start |
| a day or more | warmth, mostly: it reads as a reunion |
| days | warmer still |

And while she waits she samples the GPU every couple of minutes, so a
card pinned at 90% for six hours tells her you were *there* (gaming,
rendering), just not talking to her. That lands a little livelier and a
little less fond than being genuinely out, which is about right.

**It survives a restart**, faded by however long you were gone. A mood
that resets every launch isn't a mood, it's decoration, and this app
gets restarted a lot. Pick up five minutes later and it resumes; pick
up tomorrow and last night's is long gone. Saved in `agent/mood.json`.

**The label sticks.** A value has to clear a band boundary properly
before the label changes, because resting a hair from an edge made the
header flicker between two moods turn after turn.

**The wording varies.** Each state has a few phrasings and picks a
fresh one each time she arrives there. The same sentence every turn is
one a model either stops seeing or starts performing.

**And it tints her voice.** Drowsy speaks a few percent slower and
slightly lower, bright a touch faster and higher: multiplied on top of
your `tts.speed` and `tts.pitch`, capped at ±7% and ±0.45 semitones.
Small enough to read as mood rather than as a broken setting.
`mood.voice false` turns just that part off.

```json
"mood": {
    "enabled": true, "warmth": 0.45, "recovery": 0.25,
    "voice": true, "affection": true
}
```

`warmth` is where she settles when nothing's pushing; `recovery` is how
hard each turn pulls home: 0 means moods never fade, 1 means nothing
survives a single turn.

`/mood` shows where she is and what moved her recently, `/mood reset`
puts her back to baseline for the hour, and `/set mood.enabled false`
turns the whole thing off: the header row disappears with it.

## Being nice to her

The one signal that asks the model instead of reading the session, and
the only one that costs anything: after your turn, a short background
call rates how warm the message was, 0-3.

This started as a word list and that was the wrong shape. The
vocabulary of affection is *personal*: "good kitty" is one household's
phrase, and nobody else's spelling mistakes belong hard-coded in your
assistant. A model knows warmth in any wording and any language, which
is the whole job.

Three rules keep it from being a button:

- **It rates your message, not the exchange.** Whether she was nice
  back isn't the question.
- **Repeats fade.** The fifth kind word in a row is worth a fifth of
  the first, and it recovers once you stop.
- **Nothing here darkens her.** Bluntness rates 0, and 0 does nothing:
  the prompt says outright that swearing isn't unfriendly by itself. An
  assistant that cools when you're terse is one you have to manage, and
  she drifts back to warm on her own regardless. You never have to be
  nice to her to get a pleasant assistant; it just registers when you
  are.

Only *your* turns count. Stream chat goes through a different path
entirely, so a viewer being sweet to her doesn't move the same dial
you do.

It runs on a worker and fails to 0: a dead model, a timeout, or a
reply that isn't a digit all mean "nothing happened", and the turn
never waits for it. `mood.affection false` switches off just this part,
and with it the only per-turn cost moods have.

She won't bring it up unprompted, but she'll answer honestly if you ask
how she's doing: deflecting a direct question is worse than either
extreme.

One rule the code enforces rather than hopes for: **mood colours tone,
never capability.** There is no state in which she's less helpful, only
states in which she's drier about it. That's in the prompt line itself,
and it's the difference between a companion with a bad evening and
software you have to coax.
