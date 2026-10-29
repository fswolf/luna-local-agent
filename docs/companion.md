# The companion side

Luna is two things in one program: an assistant that does jobs (files,
the shell, mail, home, search, games), and a companion who has moods,
a body on screen, and reacts to you. This page is the whole companion
side in one place - what each part does, how they connect, the exact
numbers, every mood, touch and gesture she has, and how to change any
of it. The deeper pages it draws on are [Moods](moods.md) (the mood
engine's reasoning), [Portrait](portrait.md) (models, framing, the
debug viewer) and [Gestures](gestures.md).

One rule runs through all of it: **mood colours tone, never
capability.** There's no mood in which she does less, only moods in
which she's drier, softer, sulkier or more forward about it. The one
deliberate exception is walking away, and even then alarms, reminders
and stop words still work.

## Contents

- [How it fits together](#how-it-fits-together)
- [Where everything lives](#where-everything-lives)
- [Who she is: agent.json](#who-she-is-agentjson)
- [One turn, companion side](#one-turn-companion-side)
- [The mood engine](#the-mood-engine)
- [Reading the exchange](#reading-the-exchange)
- [The lewd row: desire](#the-lewd-row-desire)
- [The grudge row](#the-grudge-row)
- [Walking away](#walking-away)
- [Heavy moments](#heavy-moments)
- [Streams where lewd isn't allowed](#streams-where-lewd-isnt-allowed)
- [Every mood](#every-mood)
- [Quick feelings](#quick-feelings)
- [What shows on the portrait](#what-shows-on-the-portrait)
- [Touching her](#touching-her)
- [Every gesture](#every-gesture)
- [Turning her round](#turning-her-round)
- [Sounds and pronunciation](#sounds-and-pronunciation)
- [Stream chat](#stream-chat)
- [Making your own: the pose studio](#making-your-own-the-pose-studio)
- [Settings reference](#settings-reference)
- [Recipes](#recipes)
- [When something's off](#when-somethings-off)

## How it fits together

```
 agent.json (who she is) ─────────────────────────────┐
                                                      ▼
 the clock, the day, how long you've been  ──►  MOOD ENGINE  ──► one line in her system prompt
 at it, how long you were gone, the GPU,        (mind/mood/,          a tint on her voice (speed, pitch)
 stream chat, errors, barge-ins                 moods.json)      her face, idle moves, emotes ──► PORTRAIT
                                                   ▲  ▲                                          │
 after every reply: one small model call  ─────────┘  │                                          │
 reads your message + her answer (warmth, energy,     │                                          │
 a feeling, how flirty) ── desire, grudge, walk-away  │        you click her ── touch reaction ◄─┘
                                                      │        (touch.json + gesture files)
                                                      │                  │
                                                      └── touch talk ◄───┘  (she says one line)
```

- **The mood engine** is the heart: two dials (energy, warmth), two
  extra rows (lewd above, grudge below), and the rules that move them.
- **Everything visible follows the mood**: what she's told, how her
  voice sounds, her face, what she does when idle, which emotes pop up,
  how she reacts when touched.
- **The portrait feeds back in**: touches are told to her, and her
  reply to a touch is read like any exchange, so a poke can make her
  happier or crosser.

## Where everything lives

| File | What it holds |
|---|---|
| `agent/agent.json` | Her name, personality, tone, traits, rules, who you are, and how to pronounce her cat sounds |
| `agent/moods.json` | Every mood: its name, what she's told, face, voice, idle moves, emote; the lewd and grudge rows; quick feelings; walk-away lines |
| `agent/mood.json` | Where the dials are right now (saved after every turn, so a restart picks up where she was) |
| `mind/mood/` | The engine, one file per job: `core.py` her state, `drift.py` the dials moving, `exchange.py` what a turn did (desire, grudge, spanks), `walkaway.py`, `show.py` (label, prompt line, face, portrait), `saving.py` |
| `mind/mood/appraise.py` | The exchange reading: the one side question that asks how a turn landed |
| `mind/mood/files.py` | Loads and checks `agent/moods.json`, with built-in moods if it's broken |
| `config.json` → `"mood"` | On/off, intensity, where she rests, what shows where (see [Settings](#settings-reference)) |
| `portrait/touch.json` | What she does when each part of her is clicked, per mood |
| `portrait/gestures/*.js` | Every gesture: one file each, data only |
| `portrait/sounds/` | Her sound clips (`source/` inside is not in git) |
| `life/touches.py` | Touch talk: her one spoken line when you touch her |
| `life/gestures.py` | How her replies set gestures off (tags, meaning, keywords) |
| `portrait/viewer/` | The portrait page itself, the debug viewer and the pose studio |

## Who she is: agent.json

```json
{
    "name": "Luna",
    "nickname": "Echo",
    "user": {"name": "Ryan", "pronouns": "he/him"},
    "personality": "You are Luna: a flirty, affectionate cat-girl AI ...",
    "tone": "Intimate and playful, like talking to someone you're into ...",
    "traits": ["Flirts constantly; calls the user pet names", "..."],
    "rules": ["Clarity over comfort", "...", "Use nya/meow/mrrp or a trailing ~ at most once every few replies"],
    "pronounce": {"nya": "/njˈɑ/", "mew": "/mjˈu/", "meow": "/miˈW/", "mrrp": "/mˈɜɹp/"}
}
```

| Field | What it does |
|---|---|
| `name` | Her name everywhere: prompts, the header, what chat must say to get her attention |
| `nickname` | A second name she answers to |
| `user` | Your name and pronouns. Every prompt line that mentions you ("when he asks...") uses these. No pronouns, or ones it can't read, means he/him; `"they"` and three custom words (`xe/xem/xyr`) work |
| `personality` | The core of her system prompt: who she is, in a sentence or two |
| `tone` | How she sounds |
| `traits` | Habits, one per line |
| `rules` | Hard lines for how she talks. Small models are bad at counting across replies, so "at most once every few replies" style rules are followed loosely |
| `pronounce` | Words her voice says wrong, with the phonemes to use instead (see [Sounds and pronunciation](#sounds-and-pronunciation)). Only her voice uses this; the screen shows the word as written |

The **mood line** is added on top of this every turn - agent.json is
who she is, the mood is how she happens to be right now.

## One turn, companion side

What happens around a reply, in order:

1. **Before she answers**, her system prompt gets:
   - the **mood line** for where the dials are (in a public chat turn -
     stream or Discord - a mood marked `private` is swapped for the
     nearest one in its row that isn't);
   - in tags mode on a 3D model, the **gesture line**: the gestures she
     may use, each with its `about` text. Private ones only in your own
     turns; lewd ones not while a tame stream is live.
2. **She answers.** Any `[gesture]` tags she wrote are stripped from the
   text and played on the portrait. Actions she writes (`*giggles*`) can
   set gestures off by their keywords too.
3. **Her voice** gets the mood's speed and pitch tint, and the
   `pronounce` table is applied just before the text goes to Kokoro.
4. **After she answers**, on a background worker (the turn never waits
   for it), one small model call reads your message and her answer:
   how warm you were, whether it livened her up or wore her down,
   whether it was hostile, a quick feeling, how flirty it was. That
   moves the dials, may show a feeling on her face, builds or wipes
   desire, may start or end a grudge, and counts toward walking away.
5. **The turn closes**: both dials drift a step back toward where she
   rests, and the free signals (time, session length, tempo, the
   machine, the day, stream chat) nudge her.
6. **The portrait is told** the new mood: label, row, dials, face, idle
   moves, emote, and whether lewd is being held back.

## The mood engine

### Two dials, four rows, two extra rows

Energy and warmth each run from −1 to +1. Where they sit picks a cell:

|                | tired | even | wired |
|----------------|-------|------|-------|
| *lewd*         | teasing | frisky | heated |
| **very warm** (≥ 0.66) | cuddly | loving | flirty |
| **warm** (0.35 – 0.66) | sleepy | happy | excited |
| **neutral** (−0.20 – 0.35) | tired | calm | focused |
| **cool** (< −0.20) | sad | annoyed | mad |
| *grudge*       | sulky | hurt | furious |

Energy's bands break at **−0.20** and **0.35** (tired / even / wired).
The edges live in `agent/moods.json` (`energy.edges`, `warmth.edges`),
so you can move them.

**The label sticks.** A dial has to clear an edge by **0.07** before the
label changes, so resting near an edge doesn't flicker between two
moods. The lewd row also has a margin: once in, she stays until desire
drops below `enter − 0.1`.

### Where she rests

**Energy** follows the clock. These are the anchors, interpolated in
between:

| Hour | 0 | 2 | 4 | 6 | 8 | 10 | 13 | 16 | 19 | 22 |
|---|---|---|---|---|---|---|---|---|---|---|
| Energy baseline | +0.25 | +0.05 | −0.35 | −0.55 | −0.15 | +0.20 | +0.30 | +0.35 | +0.45 | +0.40 |

From that, every turn:

- **Hours at it** pull the target down by **0.06 per hour**, capped at
  **0.35**, so a marathon bottoms out instead of going through the floor.
- **Being fond of you** lifts it: half of however far warmth is above
  its resting point.
- Intensity scales the whole target.

**Warmth** rests at `mood.warmth` (**0.45**, just warm). As intensity
drops toward 0 the resting point slides toward plain calm (0.1).

### Drift

Every turn both dials move a step toward where she rests. The step is
`mood.recovery` (**0.25**): a quarter of the way.

Warmth drifts **asymmetrically**: coming back **up** from a cold patch
takes the full step, coming back **down** from warmth you earned takes
only **0.4** of it. Otherwise the drift ate every kind word the turn
after it landed.

### The free signals

| Signal | What it does |
|---|---|
| Time of day | The energy baseline above |
| Day of week | Friday evening lifts, Monday morning doesn't; weekends rest warmer |
| Hours at it | Lowers the energy target, 0.06/hour, capped at 0.35 |
| How long you were gone | Under 25 s between turns: +0.06 energy, +0.04 warmth (fast back-and-forth). Under 30 min: nothing. Under 3 h: +0.05 / +0.05. Longer: more energy for most of a day away, more warmth for a day or more (a reunion) |
| The GPU | Sampled every couple of minutes while she waits. Pinned for hours means you were around, just busy: a little livelier, a little less fond than being truly out |
| Stream chat | A busy room is company, a dead one is a quiet night |
| Errors | A failed turn is dispiriting; a run of them compounds |
| A clean run | Every 10 turns without an error: +0.05 warmth, +0.03 energy |
| Barge-in | Being talked over repeatedly wears on her |

All of them are multiplied by `mood.intensity` (0 to 2).

### Saved across restarts

The dials, desire and any grudge are saved to `agent/mood.json` after
every turn and restored at launch, faded by however long she was off.
Five minutes later she's where she was; tomorrow, last night's mood is
gone.

## Reading the exchange

The one mood signal that costs anything: a short model call after each
of **your** turns (stream chat doesn't count toward your dials). It
returns one line of five fields:

```
2 + + laughing 1
```

| # | Field | Values |
|---|---|---|
| 1 | How warm **your** message was | 0 neutral / businesslike / blunt (swearing isn't unfriendly by itself), 1 polite warmth, 2 clear affection or praise, 3 strong affection |
| 2 | Energy | `-` draining, `=` no change, `+` lively |
| 3 | Warmth | `-` only for real hostility aimed at her, `=`, `+` |
| 4 | A feeling | one of the [quick feelings](#quick-feelings), or none |
| 5 | How flirty or intimate your message was | 0 not, 1 flirting or suggestive, 2 openly intimate or sexual |

What each does:

- **Warmth rating** → warmth **+0.08 / +0.18 / +0.30** for 1 / 2 / 3, and
  energy 0.45× that. Repeats taper: each kind word in a row is divided
  by (1 + 0.4 × how many came recently), so the fifth "love you" is
  worth about a third of the first. It recovers as turns pass.
- **Energy / warmth marks** → energy ±0.06, warmth +0.05 or **−0.08**.
- **Feeling** → shown on her face for a few seconds (and its gesture
  and emote), then a small push to the dials.
- **Flirt** → builds desire (next section).
- **Hostile** (`-` warmth) → wipes desire, a further **−0.27** warmth, may
  start a grudge, and counts toward walking away.
- **Rating 3** → hearts beside her head, unless the feeling already
  brought its own emote (`compliment` in moods.json).

If the call fails, times out or answers in the wrong shape, nothing
happens. `mood.affection false` turns it off - and with it desire, the
grudge and walking away, since they all come from this reading.

## The lewd row: desire

A third dial, **desire**, from 0 to 1.

| What | Desire |
|---|---|
| A flirty message (field 5 = 1) | **+0.12** |
| An openly intimate one (field 5 = 2) | **+0.22** |
| A clearly affectionate one (rating 2+) | **+0.04** more |
| Repeats | divided by (1 + 0.2 × recent kind words) |
| Every turn | **−0.02** |
| Time away | halves every **20 minutes** |
| Any hostile message | **back to 0** at once |
| Warmth below warm (0.35) | **back to 0** - desire only lives at warm and above |

**Getting in:** warmth very warm (≥ 0.66) **and** desire ≥ `lewd.enter`
(**0.6**). Energy picks teasing, frisky or heated. In practice that's
roughly 5-10 minutes of real flirting from warm.

**Staying in:** until desire drops below 0.5 or warmth leaves very warm.

**What she's told:** in the lewd row, "*Right now you feel heated and
eager, wanting him now. Let that colour how you sound and what you're in
the mood for. Don't announce it unasked. Practical requests still get
done.*" Below very warm, she's told that if you push for sex or
intimate roleplay she isn't in the mood, to say so her own way, with a
hint of what would change that, and no lecture.

To make lewd impossible, set `"enter": 2` in the `lewd` block of
`agent/moods.json` (desire never gets past 1).

## The grudge row

**Getting in:** a hostile message while she's already cool (warmth
below −0.20), or one that knocks her there. It lasts `grudge.minutes`
(**20**); another insult restarts the clock.

**While it runs:**

- Warmth can't rise above **−0.25** (just under the cool edge) - not by
  drift, not by small kindnesses.
- Desire stays at 0.
- She's told: *you're holding a grudge. Let it show - short, prickly,
  not warm. Grumble at requests; you may refuse what isn't urgent until
  you get an apology, but alarms, reminders, safety and anything urgent
  always get done. A real apology ends it.*
- Sulky, hurt or furious by energy.

**Getting out:** a real apology or clear warmth (rating 2+, or a `+`
warmth mark) ends it on the spot and warms her **+0.10**. Otherwise the
timer does. Making up also works while she's walked away.

## Walking away

Real hostility (the reading's `-` warmth) **3 times in a row**
(`mood.walk_away_after`) and she stops talking for **10 minutes**
(`mood.walk_away_minutes`). A warm exchange clears the count, and half
an hour without another hostile one wipes it.

- She says one line from `walk_away.lines`, then nothing: no replies
  and no model calls.
- On the portrait she crosses her arms and turns her head away (`sulk`)
  with `walk_away.face`, holding it with no idle moves.
- Alarms and reminders still ring, in character but curt
  (`walk_away.prompt`). Stop words still stop toys. Discord gets "(She
  isn't talking right now.)"
- She comes back when the time's up, or sooner if what you say reads as
  making up. `/mood reset` brings her back at once.
- `mood.walk_away false` turns it off.

## Heavy moments

When you're having a really hard time, she notices and knows. The
exchange reading's sixth word (`normal`, `rough`, `heavy`) is read by
meaning; `heavy` counts at once, `rough` after two in a row, and two
normal messages step it back down. While it lasts she gets one line
about being present: listen more than fix, no advice or lectures unless
asked, follow your lead. Nothing else changes: the dials, the lewd row,
the grudge and walking away carry on as they are, and she decides what
to do with it. Only your own messages count, never in front of a guest,
never in stream chat. `/mood` shows it, `/mood reset` clears it, and the
wording and switch are the `"heavy"` block in `agent/moods.json`
([Moods](moods.md#heavy-moments)).

## Streams where lewd isn't allowed

Twitch and YouTube each have `"lewd": false` by default. While either
is live with it off:

- the lewd row **shows as the row below it** - teasing as cuddly,
  frisky as loving, heated as flirty - in her face, idles, voice,
  portrait, touch reactions and mood line;
- gestures marked `lewd: true` never play and aren't offered to her;
- desire keeps going underneath, so when the stream stops she's back
  where she was.

pomf, IRC and Discord hold nothing back. `/mood` says "lewd held back
while twitch is live". Allow it per channel:

```json
"twitch": { "lewd": true }
```

## Every mood

Generated from `agent/moods.json`. Face values are 0-1 (`lids` is the
half-lidded look); voice is a speed multiplier and a pitch shift in
semitones, capped at ±7% and ±0.45 at run time. Each mood has two or
more lines - she gets a fresh one each time she arrives there.

| Row | Mood | Energy | What she's told (one of) | Face | Voice | Idle moves | Emote |
|---|---|---|---|---|---|---|---|
| lewd | **teasing** | tired | in the mood, slow and teasing, wanting him close | happy 0.3, relaxed 0.3, blush 0.55, lids 0.6 | ×0.95, -0.3 st | shy, wink | hearts |
| lewd | **frisky** | even | frisky and bold, enjoying getting him going | happy 0.4, blush 0.55, lids 0.5 | ×1.03, +0.25 st | wink, bounce, look_back, leg_hold | hearts |
| lewd | **heated** | wired | heated and eager, wanting him now | happy 0.2, blush 0.85, lids 0.65 | ×1.04, +0.1 st | cup_breasts, touch_self, look_back | hearts |
| very warm | **cuddly** | tired | sleepy and cuddly, not wanting to be anywhere else | relaxed 0.4, happy 0.3, blush 0.2 | ×0.96, -0.25 st | shy, stretch | - |
| very warm | **loving** | even | openly fond of him, and not hiding it | happy 0.4, relaxed 0.2, blush 0.25 | - | shy | hearts |
| very warm | **flirty** | wired | flirty and playful with him | happy 0.3, blush 0.4, lids 0.45 | ×1.03, +0.25 st | wink, beckon_kiss | hearts |
| warm | **sleepy** | tired | sleepy and glad of the company | relaxed 0.35, happy 0.15 | ×0.95, -0.3 st | stretch | - |
| warm | **happy** | even | happy, easy company | happy 0.3, relaxed 0.1 | - | - | - |
| warm | **excited** | wired | excited and enjoying this | happy 0.45 | ×1.05, +0.35 st | bounce, dance | - |
| neutral | **tired** | tired | tired, but here | sad 0.3, relaxed 0.15 | ×0.95, -0.3 st | stretch | - |
| neutral | **calm** | even | calm, nothing much either way | happy 0.06 | - | standing_split | - |
| neutral | **focused** | wired | focused and interested | happy 0.12 | ×1.03, +0.2 st | look_hand | - |
| cool | **sad** | tired | sad and worn out | sad 0.7, angry 0.1 | ×0.95, -0.35 st | - | - |
| cool | **annoyed** | even | annoyed and not in the mood for much | angry 0.35, sad 0.1 | - | - | anger |
| cool | **mad** | wired | mad and wound up | angry 0.85 | ×1.04, +0.2 st | - | anger |
| grudge | **sulky** | tired | sulking and short with him, not over it | sad 0.5, angry 0.25 | ×0.95, -0.35 st | hands_on_chest | - |
| grudge | **hurt** | even | hurt and cool with him; he hasn't made it right | sad 0.55, angry 0.3 | - | shrug | - |
| grudge | **furious** | wired | furious with him and not hiding it | angry 0.9 | ×1.05, +0.25 st | hands_on_chest | anger |

The face is scaled by `mood.intensity`. **Idle moves** are picked half
the time when she does something on her own (the other half from the
gestures marked idle). A mood's **emote** pops up every 3-6 minutes.

## Quick feelings

A feeling is the fourth field of the exchange reading: it shows on her
face for a few seconds, plays its gesture and emote, then nudges the
dials. Add one to `feelings` in `agent/moods.json` and the model is
offered it on the next turn.

| Feeling | Face | Gesture | Emote | Nudge (energy, warmth) |
|---|---|---|---|---|
| happy | happy 0.7 | - | - | +0.03, +0.03 |
| laughing | happy 1.0 | bounce | - | +0.06, +0.04 |
| surprised | surprised 0.7 | - | - | +0.05, +0 |
| embarrassed | happy 0.3, blush 1.0 | shy | sweat | +0, +0.03 |
| touched | happy 0.5, relaxed 0.4, blush 0.5 | - | hearts | +0, +0.06 |
| playful | happy 0.4, blush 0.4, lids 0.5 | wink | - | +0.04, +0.03 |
| curious | surprised 0.25, happy 0.15 | - | question | +0.03, +0 |
| confused | surprised 0.2, sad 0.15 | - | question | +0, +0 |
| sad | sad 0.7 | - | - | -0.05, +0 |
| annoyed | angry 0.5 | - | anger | +0.02, -0.04 |

## What shows on the portrait

| Part | What drives it |
|---|---|
| **Face** | The mood's `face` (scaled by intensity), plus quick feelings and gesture faces on top. A mood's `lids` comes in glances - every 8-20 s her eyes lower for a few seconds - because held all the time it reads as sleepy. Blinks on top |
| **Blush** | Moods, feelings, gestures and touch reactions all raise it; the strongest wins |
| **Idle moves** | Every 20-40 s while idle, half from the mood's `idle` list, half from gestures marked idle. Full-body-only ones wait for full-body framing |
| **Emotes** | hearts, sweat, anger, question: from feelings, compliments, touch reactions and the mood's own `emote`. One at a time, at least 30 s apart (a mood's own every 3-6 min) |
| **Voice** | The mood's `voice`, capped |
| **Tail** | Wags on happy gestures; gestures can swish it (`wag`) or lift and hold it (`tail_up`) |
| **Tears, drool** | From gestures and sad moods (tears when `sad` > 0.55 for a while) |

`mood.face`, `mood.gestures`, `mood.emotes` and `mood.voice` switch each
part off on its own.

## Touching her

Click (or tap) a part of her on the portrait. A ray from the camera
finds the bone under the cursor and names the zone: **head, nose,
mouth, neck, chest, arms, tummy, back, groin, butt, legs, tail** (tail
only on models with tail bones). It works from any angle, so turned
round, a click on her back really is her back.

**Which reaction plays** - `portrait/touch.json` has a reaction per zone
per key, checked in this order:

1. her **mood name** (`flirty`, `heated`, `furious`...), if the zone has one;
2. her **row** (`lewd`, `grudge`);
3. her **warmth band**: `cool`, `neutral`, `warm`, `loving` (very warm).
   With no `lewd` entry she falls back to `loving`, with no `grudge`
   entry to `cool`.

A reaction can have **gestures** (one picked at random), a quick
**face** (with `seconds` to hold it), an **emote**, and an **ears**
twitch. **Gesture files join in on their own**: a gesture with
`touch: ['legs']` and `moods: ['warm']` is added to that zone's choices
in those moods, without touching `touch.json`. It joins for the mood the
zone answers from (in heated the chest answers from lewd, so a
`loving`-tagged gesture stays out).

- **Cooldown:** 1.5 s between touch reactions.
- **Too much:** 5 touches within 8 s gets a "that's enough" reaction
  (`too_much_reaction`): cool → arms crossed and angry, warm → flustered,
  lewd → blush and hearts.
- **Touches add up** (`build` and `soft`): in the lewd row, while she's
  tired, the chest, tummy, groin, back and legs take three touches before
  the full reaction (two when she's even, one when she's wired). Before
  that she settles into it: `sleepy_lean`, `hand_over` (chest) or a
  `squirm`, on the first touch, then just her face. See
  [portrait](portrait.md).
- **Hover** (debug viewer): the cursor shows the zone and what it would
  do in her current mood, and how far a touch has built up.

Every zone, every mood, as it stands (`*` = a gesture that tagged
itself in; the emote in brackets):

| Zone | cool | neutral | warm | loving | lewd | grudge |
|---|---|---|---|---|---|---|
| **head** | shrug, pat_hmph* | bashful, pat_lean* | bashful, pat_lean* | bashful, pat_lean*, pat_nuzzle* (hearts) | bashful, pat_nuzzle* (hearts) | shrug, huff*, pat_hmph* (anger) |
| **nose** | surprise | surprise, boop* | wink, boop* | wink, boop* (hearts) | nose_tease | shrug (anger) |
| **mouth** | shh | shy, say_ah* | blow_kiss, say_ah* | blow_kiss, beckon_kiss*, say_ah* (hearts) | blow_kiss, open_wide* (hearts) | shh |
| **chest** | hands_on_chest (anger) | shy | bashful | cup_breasts, beckon_kiss* | cup_breasts | hands_on_chest (anger) |
| **tummy** | shrug | surprise | giggle, bounce | giggle, bashful | giggle, bashful | shrug, huff* |
| **groin** | shy (anger) | shy | bashful | touch_self | touch_self, climax*, masturbate* | hands_on_chest (anger) |
| **legs** | step_back* | standing_split, knee_lift* | knee_lift*, weight_shift* | weight_shift* (hearts) | leg_hold (hearts) | - (anger) |
| **butt** | step_back (anger) | surprise | shy | bashful (hearts) | sultry_beckon, wink, bend_over* (hearts) | huff (anger) |
| **tail** | - | - | - | - (hearts) | - (hearts) | huff (anger) |
| **back** | shrug | - | - | - (hearts) | bend_over* | huff |
| **neck** | step_back | shy | bashful | bashful (hearts) | - (hearts) | huff (anger) |
| **arms** | - | - | - | - | - | huff |

### Spanks

From **warm** up - **warm** (sleepy, happy, excited), **very warm** (cuddly,
loving, flirty) and **lewd** - a click on her bum is a **spank** instead of a
normal touch reaction:

- She flinches (`spank_flinch`): hips jolt, back arches, shoulders snap
  up, a gasp and a blush, a tail flick. Every click, no cooldown.
- **Her bum reddens**: a red glow over her cheeks that steps up every
  **10** spanks (up to fairly red), with a small flash on each one.
  Spanks are forgotten one every **10 s**, so it fades when you stop.
  Every tenth one brings hearts (lewd) or a sweat drop (very warm).
- **Too many is a punishment**, Tamagotchi style: every **60** spanks
  (counted the same way, forgotten one per 10 s) knocks her down a
  notch: warmth **−0.10**, energy −0.03, desire **−0.20**. Keep at it and
  she drops out of the mood.
- She hears about it like any touch ("with a spank on the butt, 5
  times") and may say something.
- None of it while a tame stream is live, and in her other moods a click
  on her bum is an ordinary touch.

The numbers are `SPANK_LIMIT`, `SPANK_FORGET`, `SPANK_WARMTH` and
`SPANK_DESIRE` in `mind/mood/exchange.py`, and `SPANK_STEP` / `SPANK_FORGET` in
`portrait/viewer/portrait.js`.

### Touch talk: she says something

The portrait reacts instantly. Separately, the touch is sent to her and
she answers **out loud with one short line**, in character, knowing her
mood and what you were talking about:

- pokes within **1.5 s** are gathered into one ("on the head, 3 times");
- one line, at most **40 tokens**, no tools, no thinking;
- at most one every **12 s** (`portrait.touch_talk_cooldown`);
  touches in between get the portrait's reaction only;
- never while you're talking, while she's answering, or while she's
  walked away;
- saved to her history as `*touches you on the head*` and her line, so
  she remembers it and her mood reads it like any exchange.

`portrait.touch_talk false` (the settings pane's "touch talk") turns it
off.

## Every gesture

Generated from `portrait/gestures/`. 🔥 lewd (held back on a tame
stream) · 🔒 private (never from stream chat) · 🧍 full body only ·
💤 idle (she does it on her own).

| Gesture | What it is (her description) | Kind | Flags | Touch zones | Moods |
|---|---|---|---|---|---|
| `arch_stretch` | relaxed, unwinding, at ease: hands behind her head, arches her back with a long sigh | 5.0 s | 💤 | - | any |
| `bashful` | bashful, embarrassed, small and quiet: head tipped down, a hand at her collarbone, blushing | 5.5 s | - | - | any |
| `beckon_kiss` | flirty, teasing, wants you closer: beckons you over with a finger, winks, then blows you a kiss | chain: sultry_beckon → blow_kiss | 🔒 | mouth, chest | loving |
| `bend_over` | lewd, teasing: bends right over with her back to you, hands on her backside | 9.0 s | 🔥🔒🧍 | butt, back | lewd |
| `blow_kiss` | fond, affectionate, sending love, goodnight: fingers to her lips, then blows you a kiss | 3.0 s | - | - | any |
| `boop` | booped on the nose: squeezes her eyes shut, 'hey!', then a happy flustered smile | 1.8 s | - | nose | neutral, warm, loving |
| `bounce` | happy, cheerful, can't keep it in: bounces happily on the spot | 1.3 s | 💤 | - | any |
| `climax` | lewd, heated: peaks, then left out of breath | chain: touch_self → pant | 🔥🔒 | groin | heated |
| `cry` | deeply sad, hurt, grieving, moved to tears: head down, shoulders shaking with sobs | 7.0 s | - | - | any |
| `cup_breasts` | lewd, teasing: hands flat on her chest, blushing and panting | 8.5 s | 🔥 | - | any |
| `dance` | celebrating, feeling great, music, playful: a cute dance to the beat | 16 s | - | - | any |
| `explain` | - | 2.4 s | - | - | any |
| `face_me` | turning back to face you, giving you her attention: the view swings back to her front | turn (0°) | - | - | any |
| `giggle` | amused, tickled, a little embarrassed: covers her mouth and giggles, shoulders bobbing | 2.4 s | - | tummy | warm, loving, lewd |
| `hands_on_chest` | - | 4.0 s | - | - | any |
| `huff` | annoyed, grumpy, offended: arms crossed tight, chin up, looks away with a huff | 3.0 s | - | head, tummy, arms | grudge |
| `hug` | affectionate, comforting, glad you're here, missing you: arms open, then wraps you in a hug, head on your shoulder | 4.6 s | - | - | any |
| `jog` | energetic, restless, exercise, can't sit still: runs on the spot, then catches her breath | 5.0 s | - | - | any |
| `jump` | big excitement, great news, thrilled: jumps for joy | 1.35 s | - | - | any |
| `knee_lift` | ticklish, startled by a touch: knee jerks up with a squeak and a laugh | 1.9 s | 🧍 | legs | neutral, warm |
| `leg_hold` | lewd, smug, teasing: holds one leg straight up against her shoulder, arm hooked round it | 7.2 s | 🔥🔒🧍 | legs | lewd |
| `look_back` | lewd, teasing: turns around, bends over and looks back at you over her shoulder | 7.0 s | 🔥🔒🧍 | - | any |
| `look_hand` | - | 3.6 s | 💤 | - | any |
| `masturbate` | lewd, heated: touches herself until she's spent, then out of breath | chain: touch_self → touch_self → pant | 🔥🔒 | groin | heated |
| `nose_tease` | lewd, teasing: looks up at you, lips parted, blushing | 4.2 s | 🔥🔒 | nose | lewd |
| `open_wide` | lewd, teasing: blushing, eyes half closed, mouth opened wide and held | 4.0 s | 🔥🔒 | mouth | lewd |
| `pant` | out of breath, exhausted, worn out after effort: bent over, hands on her knees, then a long sigh | 7.5 s | - | - | any |
| `pat_hmph` | hmph: chin up, turns her head away from a pat she didn't want, a small pout | 2.6 s | - | head | cool, grudge |
| `pat_lean` | enjoying a head pat: tips her head up into your hand, eyes closed, content | 3.2 s | - | head | neutral, warm, loving |
| `pat_nuzzle` | nuzzling into a head pat like a cat, eyes closed, blushing and happy | 3.4 s | - | head | loving, lewd |
| `peace_dance` | cute, playful, showing off: a little dance with peace signs by her face and a wink | 16 s | - | - | any |
| `say_ah` | opens her mouth wide, 'aah', like at the dentist; playful, a bit silly | 2.8 s | - | mouth | neutral, warm, loving |
| `shh` | a secret, mischief, being sly: finger to her lips with a sly smile | 2.8 s | - | - | any |
| `shrug` | unsure, don't know, oh well, whatever: a shrug with open hands | 2.2 s | - | - | any |
| `shy` | shy, flustered by a compliment, sweet on you: hands together at her chest, looks away shyly, then peeks back at you | 4.2 s | 🔒 | - | any |
| `spank_flinch` | flinching from a spank, surprised and flustered | 0.9 s | 🔥🔒 | (bum, warm and up - see Spanks) | warm, very warm, lewd |
| `standing_split` | bored, idly showing off: a standing split, leg held up by the ankle | 6.6 s | 🧍 | legs | neutral, calm, tired |
| `step_back` | annoyed, not having it, wants space: steps back away from you, chin up, looking off | 2.8 s | 🧍 | legs | cool |
| `stretch` | tired, sleepy, just woke up: arms up over her head in a big stretch and a yawn | 4.2 s | 💤 | - | any |
| `sulk` | - | 600 s | - | - | any |
| `sultry_beckon` | sultry, inviting, come here: curls her fingers to beckon you, other hand on her hip, a sly smile | 3.4 s | 🔒 | - | any |
| `surprise` | happily surprised, delighted by something unexpected: a little gasp, hands flying to her chest | 3.2 s | - | - | any |
| `touch_self` | lewd, heated: one hand on her breast, one between her legs, blushing and panting | 10 s | 🔥🔒 | - | any |
| `tuck_hair` | - | 2.6 s | 💤 | - | any |
| `turn_around` | turning around, showing you her back: the view swings round behind her | turn (180°) | - | - | any |
| `turn_side` | turning to the side, showing her profile: the view swings round to her side | turn (90°) | - | - | any |
| `wave` | hello, goodbye, see you, welcome back: a friendly wave | 2.6 s | - | - | any |
| `weight_shift` | pleased, coy, showing off a little: shifts her weight onto one hip, head tilted | 3.8 s | 🧍 | legs | warm, loving |
| `wink` | playful, teasing, a little flirty, in on the joke: winks at you with a smile | 1.6 s | - | - | any |

How her replies set gestures off is `portrait.gestures`:

- **tags** (default): she's offered `[name]` tags with each gesture's
  `about`, and writes one where it fits. Keywords in what she writes are
  the fallback.
- **meaning**: an embedding model compares the exchange with each
  gesture's `about` (turns are never picked this way).
- **keywords**: only words in her `*actions*` and emoji.
- **off**.

**Chains** (`chain: [...]`) play gestures one after another as one;
their own flags, touches, moods, sound and emotes apply. **Clips**
(`.vrma` files in `portrait/animations/`) play like gestures; see
[Portrait](portrait.md).

## Turning her round

`turn_around`, `turn_side` and `face_me` swing the camera round her
instead of moving her. The view eases round in about a second and
drifts back to the front after **120 s**.

**Ask her, the way you'd say it.** What you type or say turns her
straight away, before she answers (portrait/viewer/turns.js), even with
`portrait.gestures` off:

| You say | She |
|---|---|
| turn around, spin around | turns round; again brings her back |
| show me your ass / bum / butt / back, let me see your behind | shows you her back |
| turn to the side, turn sideways, show me your profile | shows you her side |
| turn left, turn right | turns a quarter that way, from wherever she is |
| turn 90, turn 180 deg, turn -45 | turns that far (+ is her right) |
| face me, turn back, turn to me | faces you again |

"Turn left", "turn around", "turn back" and the numbers count only in a
short message (8 words or fewer), so "I had to turn left at the lights"
doesn't spin her. **She can do it herself too:** `*turns around*`,
`*spins around*`, `*turns sideways*`, `*turns back to you*` in her reply.
When you've just asked, her own `*turns around*` in the answer doesn't
turn her back again. Chat has `!turn`, `!side` and `!front`. Your mouse can't
rotate the live portrait - only she and chat can.

## Sounds and pronunciation

**Sounds.** Put clips in `portrait/sounds/` (mp3, ogg, wav, m4a). The clips
there go in git; keep full recordings in `portrait/sounds/source/`, which
git ignores. A gesture names one:

```js
sound: 'touch-self'                                  // the file touch-self.mp3
sound: { name: 'moan', from: 'random', len: 11 },    // a random stretch, 11 s
```

- A **folder** (`gasp/`) or **numbered files** (`moan01.mp3`,
  `moan02.mp3`) answer to one name and one is picked at random.
- `from` is seconds into the clip or `random`; `len` defaults to the
  gesture's length. It fades out at the end, or when another gesture
  starts.
- No file, no sound: nothing breaks.
- `portrait.sounds false` turns them off; `portrait.sound_volume` (0-1,
  default 0.8).
- Keep a `CREDITS.md` there for packs that ask for credit.

**Pronunciation.** Kokoro spells out words it doesn't know ("N-Y-A").
`pronounce` in agent.json fixes that for her voice only:

```json
"pronounce": { "nya": "/njˈɑ/", "nyan": "/njˈɑn/", "mew": "/mjˈu/", "meow": "/miˈW/", "mrrp": "/mˈɜɹp/" }
```

Any case, and a stretched last letter counts ("Nyaaa"). Real words that
merely contain one ("Kenya") are left alone. The phonemes use Kokoro's
own symbols (`W` is the "ow" sound, `ˈ` marks the stressed part).

## Stream chat

Viewers don't move her mood dials (only how busy the room is counts,
as company), but they can make her move:

| Command | What she does |
|---|---|
| `!wave` `!hi` `!hello` | waves |
| `!hug` | hugs |
| `!jump` | jumps |
| `!bounce` `!hop` | bounces |
| `!dance` | dances |
| `!jog` `!run` | jogs |
| `!shrug` | shrugs |
| `!stretch` | stretches |
| `!kiss` `!blowkiss` | blows a kiss |
| `!bashful` `!blush` | goes bashful |
| `!turn` | turns round (again to come back) |
| `!side` | side view |
| `!front` | faces the front |

One command every 5 s across the whole chat. Plain chat works too: a
hug for her, someone new saying hi, bye, laughing or hype can get a
wave, a hug, a jump or a bounce. **Private** gestures never play from
chat; **lewd** ones never play on a tame stream. See [Stream
chat](chat.md).

## Making your own: the pose studio

The debug viewer (`./viewer.sh`, or `?debug=1`) has a **pose studio**
window: pose her with sliders (click a part of her to pick the bone),
lay keyframes on a timeline, set every detail on this page (touches,
moods, flags, sound, emotes, tail), link gestures into chains, and
**save** straight into `portrait/gestures/`. It plays through the same
engine as everything else, so what you see is what she does. Details in
[Portrait](portrait.md#the-pose-studio-making-gestures-without-code).

## Settings reference

```json
"mood": {
    "enabled": true, "intensity": 1, "warmth": 0.45, "recovery": 0.25,
    "prompt": true, "voice": true, "face": true, "gestures": true,
    "emotes": true, "affection": true,
    "walk_away": true, "walk_away_after": 3, "walk_away_minutes": 10
},
"portrait": {
    "gestures": "tags", "chat_gestures": true, "touch_talk": true,
    "touch_talk_cooldown": 12, "sounds": true, "sound_volume": 0.8
},
"twitch":  { "lewd": false },
"youtube": { "lewd": false }
```

| Setting | Default | What it does |
|---|---|---|
| `mood.enabled` | true | The whole mood system |
| `mood.intensity` | 1 | 0 almost flat (rests calm, nothing moves her), 1 as designed, 2 very visibly emotional |
| `mood.warmth` | 0.45 | Where warmth rests |
| `mood.recovery` | 0.25 | How hard each turn pulls her home (0 = moods never fade, 1 = nothing lasts a turn) |
| `mood.prompt` | true | The mood line in her system prompt |
| `mood.voice` | true | The speed and pitch tint |
| `mood.face` | true | Her face and quick feelings on the portrait |
| `mood.gestures` | true | Mood idle moves and feeling gestures |
| `mood.emotes` | true | Hearts, sweat, anger, question |
| `mood.affection` | true | The exchange reading (and so desire, grudge, walk-away) |
| `mood.walk_away` | true | Walking away after repeated hostility |
| `mood.walk_away_after` | 3 | Hostile exchanges in a row |
| `mood.walk_away_minutes` | 10 | How long she's gone |
| `portrait.gestures` | tags | tags / meaning / keywords / off |
| `portrait.chat_gestures` | true | Viewers' commands and chat reactions |
| `portrait.touch_talk` | true | Her spoken line when touched |
| `portrait.touch_talk_cooldown` | 12 | Seconds between spoken touch lines |
| `portrait.sounds` | true | Gesture sounds |
| `portrait.sound_volume` | 0.8 | 0-1 |
| `twitch.lewd`, `youtube.lewd` | false | Allow the lewd row while that stream is live |

In `agent/moods.json`: `lewd.enter` (0.6), `grudge.minutes` (20),
`compliment.rating` (3), and every mood and feeling. In `mind/mood/exchange.py`: the
desire and hostility weights (`DESIRE_FLIRT`, `DESIRE_AFFECTION`,
`DESIRE_FADE`, `HOSTILE_HIT`).

## Recipes

**Make her steadier, for work.** `mood.intensity` 0.3, `mood.face` and
`mood.gestures` false, `mood.walk_away` false. Same engine, much less
swing.

**Make her more emotional.** `mood.intensity` 1.5-2. Faces, swings and
voice tint all scale up.

**Change what a mood is.** Edit its entry in `agent/moods.json` -
lines, face, voice, idle, emote. Picked up on the next turn; a typo
keeps the last good version and `/mood` says what's wrong.

**Add a quick feeling.** Add it to `feelings` with a face, an optional
gesture and emote, and a nudge. The model is offered it next turn.

**Change a touch reaction.** Edit the zone and mood in
`portrait/touch.json` (gestures, face, seconds, emote, ears). Or have a
gesture tag itself in with `touch:` and `moods:`.

**Make a new gesture and tie it to a touch.** Pose studio → animate it →
details: tick the zone and the moods → save. It joins that touch in
those moods at once.

**Make lewd harder or impossible.** Raise `lewd.enter` (0.8 is a long
road; 2 is never). Or keep it but hide it on stream with the
`twitch` / `youtube` `lewd` settings.

**Let her stay grumpy longer.** Raise `grudge.minutes`.

## When something's off

| Problem | Look at |
|---|---|
| Her mood never changes | `/mood` shows both dials, the band each is in, what your last message scored and what moved her. Is `mood.enabled` on? Is `mood.affection` on (without it only the free signals move her)? |
| She never gets to lewd | `/mood` shows desire. It only builds while she's warm or very warm, and resets on any hostile message. Is a tame stream live ("lewd held back")? |
| She's stuck sulky | A grudge: `/mood` shows the minutes left. Apologise, or `/mood reset` |
| She stopped talking | She walked away. Make up, wait 10 minutes, or `/mood reset` |
| A touch does nothing | That zone has no entry for her current mood (hover in the debug viewer shows it), or the cooldown, or a full-body gesture in bust framing |
| A gesture never plays | 🧍 needs full-body framing; 🔒 never from chat; 🔥 not on a tame stream. The debug panel's red text lists files that didn't load |
| A sound doesn't play | Is the file in `portrait/sounds/` with the name the gesture uses? A browser may want one click on the page before it plays audio |
| She says "N-Y-A" | Add the word to `pronounce` in agent.json |
