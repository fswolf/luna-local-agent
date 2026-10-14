# Moods

Off the clock and the shape of the session, she runs a little warmer or
flatter, and it reaches the model as exactly one line of the system
prompt:

```
Right now you feel sleepy and glad of the company. Let that colour how
you sound - length, warmth, how playful you are - and nothing else.
```

Two dials, `energy` and `warmth`, each −1 to +1. Energy has three
bands and warmth four, giving twelve distinguishable states:

|                | tired | even | wired |
|----------------|-------|------|-------|
| **very warm**  | cuddly | loving | flirty |
| **warm**       | sleepy | happy | excited |
| **neutral**    | tired | calm | focused |
| **cool**       | sad | annoyed | mad |

Two dials rather than one, because a single dial can't tell "tired and
happy" from "awake and fed up", which are the two that actually turn up
at 4am. Warmth gets the extra band because three weren't enough: the
top one started at `0.35`, so a couple of turns of being nice to her ran
the dial into it and everything after that changed nothing you could
see. The current state rides on the Status row, `Idle · sleepy`, since
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

**Almost everything here is free**: no sentiment scoring, and only one
small model call. The shape of a session turns out to be the more honest signal
anyway. (The one exception is reading the exchange, below.)

| Signal | Effect |
|--------|--------|
| Time of day | The baseline: 6am and 9pm aren't the same person |
| Day of week | Friday evening lifts, Monday morning doesn't; weekends rest warmer |
| Hours at it | A long session wears her down, capped so it bottoms out |
| How long you were gone | A curve, not a switch: see below |
| What the machine did | A GPU pinned for hours means you were *around*, just elsewhere |
| Stream chat | A busy room is company; a dead one is a quiet night |
| The exchange | A short model call after her reply: how warm you were, whether it livened her up, a quick feeling |
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

**And it tints her voice.** Sleepy speaks a few percent slower and
slightly lower, excited a touch faster and higher: multiplied on top of
your `tts.speed` and `tts.pitch`, capped at ±7% and ±0.45 semitones.
Small enough to read as mood rather than as a broken setting.
`mood.voice false` turns just that part off.

```json
"mood": {
    "enabled": true, "intensity": 1, "warmth": 0.45, "recovery": 0.25,
    "prompt": true, "voice": true, "face": true, "gestures": true,
    "affection": true
}
```

| Setting | What it does |
|---------|--------------|
| `intensity` | How far she swings and how strongly it shows. 0 is almost flat (the ship's computer end: she rests calm and nothing moves her), 1 is as designed, 2 wears her heart on her sleeve |
| `warmth` | Where she settles when nothing's pushing |
| `recovery` | How hard each turn pulls her home: 0 means moods never fade, 1 means nothing survives a single turn |
| `prompt` | The one line in her system prompt |
| `voice` | The speed and pitch tint |
| `face` | Her face on the portrait, and the quick feelings |
| `gestures` | Idle moves that suit the mood, and gestures that go with a feeling |
| `affection` | The one model call: reading the exchange after your turn |

There's one mood system, not modes to pick from. A sysadmin who wants a
dry, steady assistant sets `intensity` low and turns `face` and
`gestures` off; someone who wants her visibly emotional turns
`intensity` up. Same engine, same rules.

## The moods file

What each mood *is* lives in `agent/moods.json`, not in code. Edit it
and the next turn picks it up; a typo keeps the last good version and
`/mood` tells you what's wrong.

```json
"energy": { "edges": [-0.20, 0.35], "words": ["tired", "even", "wired"] },
"warmth": { "edges": [-0.20, 0.35, 0.66], "words": ["cool", "neutral", "warm", "very warm"] },
"grid": [["sad", "annoyed", "mad"], ...],
"states": {
  "sleepy": {
    "lines": ["sleepy and glad of the company", "..."],
    "face":  { "relaxed": 0.35, "happy": 0.15 },
    "voice": { "speed": 0.95, "pitch": -0.3 },
    "idle":  ["stretch"],
    "private": false
  }
}
```

- **edges** are where one band ends and the next begins, low to high.
  The grid needs one more row than warmth has edges and one more mood
  per row than energy has edges, so adding a mood means adding an edge.
- **lines** are what she's told, rotated so she doesn't hear the same
  sentence twice running.
- **face** is what the portrait shows: `happy`, `relaxed`, `sad`,
  `angry`, `surprised`, `blush`, each 0-1, and `lids`: how far her eyes
  rest closed (0.45 is the half-lidded flirty look; blinks still happen
  on top, capped at 0.7 so her eyes never just shut).
- **voice** is a speed multiplier and a pitch shift in semitones, still
  capped at ±7% and ±0.45.
- **idle** is gestures she drifts into now and then in that mood, half
  the time instead of the usual idle ones.
- **emote** pops up beside her head now and then in that mood (every
  3-6 minutes): `"hearts"` for loving and flirty, `"anger"` for annoyed
  and mad. See Emotes.
- **private** keeps a mood out of stream chat and Discord turns: there
  she gets the nearest mood in the same row that isn't private.

**feelings** are the quick ones, below.

`/mood` shows where she is and what moved her recently, `/mood reset`
puts her back to baseline for the hour, and `/set mood.enabled false`
turns the whole thing off: the header row disappears with it.

## Reading the exchange

The one signal that asks the model instead of reading the session, and
the only one that costs anything: after her reply, a short background
call reads what you said and what she answered and returns one line:

```
2 + + laughing
```

- **how warm your message was**, 0-3, the warmth rating below
- **energy**, `-` `=` `+`: did that wear on her or liven her up
- **warmth**, `-` `=` `+`: `-` only for real hostility, never bluntness
- **a feeling** from the `feelings` list in the moods file, or none

The feeling shows on her face for a few seconds (and plays its gesture,
if it has one), then gives the slow dials a small push:

```json
"laughing": { "face": { "happy": 1.0 }, "gesture": "bounce", "nudge": [0.06, 0.04] }
```

Add a feeling to the file and the model is offered it on the next turn.
It runs while she's still speaking, so a laugh lands with the words.

### Being nice to her

This started as a word list and that was the wrong shape. The
vocabulary of affection is *personal*: "good kitty" is one household's
phrase, and nobody else's spelling mistakes belong hard-coded in your
assistant. A model knows warmth in any wording and any language, which
is the whole job.

Three rules keep it from being a button:

- **The warmth rating is your message, not the exchange.** Whether she
  was nice back isn't the question.
- **Repeats fade.** The fifth kind word in a row is worth a fifth of
  the first, and it recovers once you stop.
- **Bluntness doesn't darken her.** It rates 0, and 0 does nothing:
  the prompt says outright that swearing isn't unfriendly by itself. An
  assistant that cools when you're terse is one you have to manage, and
  she drifts back to warm on her own regardless. You never have to be
  nice to her to get a pleasant assistant; it just registers when you
  are.

Only *your* turns count. Stream chat goes through a different path
entirely, so a viewer being sweet to her doesn't move the same dial
you do.

It runs on a worker and fails to nothing: a dead model, a timeout, or a
reply in the wrong shape all mean "nothing happened", and the turn
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

## Emotes

Little pictures that pop up beside her head, the anime way, all kept
rare on purpose so they still mean something:

- **hearts** when a compliment really lands, when she's touched, and now
  and then while she's loving or flirty
- **sweat** (the big sweat drop) when she's embarrassed
- **anger** (the popping vein mark) when she's annoyed, now and then
  while she's annoyed or mad, and while she's walked away
- **question** when she's curious or confused All set in
`agent/moods.json`:

```json
"compliment": { "rating": 3, "emote": "hearts" },
"feelings": { "touched": { ..., "emote": "hearts" } },
"states":   { "loving":  { ..., "emote": "hearts" } }
```

- **compliment**: an exchange that reads as warm at `rating` or more
  (0-3, see "Being nice to her") shows it once, unless the feeling it
  raised already has its own emote.
- One at a time, at least 30 seconds apart. A mood's own ones come
  every 3-6 minutes. While she's walked away, only `walk_away.emote`
  shows (the anger mark).

The portrait draws hearts itself. To use your own art, put a sprite
sheet in `portrait/emotes/hearts.png`: the frames in one row, square
unless `portrait/emotes/hearts.json` says otherwise:

```json
{ "frames": 8, "fps": 12, "size": 0.05, "count": 3 }
```

`size` is how big each one is beside her head in metres, `count` how
many in a burst, and `motion` how it moves: `float` (drifts up, like
the hearts), `slide` (slips down, like the sweat drop), `throb` (pulses
in place, like the anger mark) or `bob` (pops up and bobs, like the
question mark). A new name (`"emote": "stars"`) only needs its PNG,
and floats unless its JSON says otherwise. The debug page
(`./viewer.sh`) has a button for each under **emotes**.
`/set mood.emotes false` turns them off.

## Walking away

On by default, and the one deliberate exception to "tone, never
capability" above: real hostility a few exchanges running makes her
stop talking for a while, the way a person would leave the room. Where
she's a tool first, `/set mood.walk_away false` turns it off.

- **What counts:** the exchange reading's own "hostile" mark, which it
  gives for being hurtful to her, not for bluntness or swearing.
  `walk_away_after` of those (3) in a row tips it. A warm exchange
  clears the count, and half an hour without another wipes it.
- **Leaving:** the next time you speak to her she says one short line
  from `walk_away.lines` in `agent/moods.json`. After that, nothing: no
  reply, and no model call for it. On the portrait she
  crosses her arms and turns her head away (`walk_away.hold`, the
  `sulk` gesture) with `walk_away.face`, and holds it, no idle moves,
  until she's back; then she turns back round.
- **While she's away:** stream chat and jobs (games included) get
  nothing. Discord gets "(She isn't talking right now.)" so it doesn't
  look broken. Stop words still stop toys, since they never go
  through her. Alarms and reminders still ring, in character: they get
  `walk_away.prompt` in place of her usual mood line, so a reminder
  comes out curt and sulky ("It's nine. Meds.") rather than sweet.
- **Coming back:** after `walk_away_minutes` (10), or sooner if what
  you say reads as making up. Then she answers that message. Either way
  she's cool with you for a while and warms back up on her own.
  `/mood reset` brings her back at once.

```json
"mood": { "walk_away": true, "walk_away_after": 3, "walk_away_minutes": 10 }
```
