# Gestures

How Luna's 3D portrait moves its body, how she decides when to move it,
and how to write your own gestures in a few lines of JavaScript.

Everything here is about VRM (3D) models. Live2D models have their own
motions and don't use any of this.

- [What a gesture is](#what-a-gesture-is)
- [From her reply to her body](#from-her-reply-to-her-body)
- [How she picks one](#how-she-picks-one)
- [What happens every frame](#what-happens-every-frame)
- [The skeleton and its numbers](#the-skeleton-and-its-numbers)
- [Anatomy of a gesture file](#anatomy-of-a-gesture-file)
- [Writing one, step by step](#writing-one-step-by-step)
- [Common mistakes](#common-mistakes)
- [Code or a .vrma clip?](#code-or-a-vrma-clip)

> **No code needed:** the debug viewer's pose studio poses her with sliders,
> keyframes it, and saves the gesture file for you. See
> [Portrait](portrait.md#the-pose-studio-making-gestures-without-code). Every
> gesture she has, with its touches and moods, is listed in
> [The companion](companion.md#every-gesture).

## What a gesture is

A gesture is a short list of **key poses** in time. A pose says where some
of her bones point: "right upper arm raised, forearm bent up, hand turned
so the palm faces you". The portrait eases smoothly from one key to the
next and blends the whole thing over whatever she's already doing
(breathing, looking around, talking), so a gesture never snaps on or off.

Each gesture is one file in `portrait/gestures/`:

```
portrait/
├── viewer/gestures.js   the player: loads the files, blends them, plays them
└── gestures/
    ├── _pose.js       shared helpers (rest pose, mirroring, fingers)
    ├── wave.js
    ├── hug.js
    ├── wink.js
    └── ...            one file per gesture
```

The file name is the gesture's name: `wink.js` is `wink`. Files starting
with `_` are helpers or notes and are never loaded as gestures.

## From her reply to her body

```
 you: "I missed you"
        │
        ▼
 Luna's prompt offers her the tags     (life/gestures.py reads every gesture
 [wave] [hug] [wink] ...                file with an "about" line)
        │
        ▼
 she replies "I missed you too [hug]"
        │
        ├── the screen, the voice and her history get "I missed you too"
        │   (the tag is cut out before anything is shown or spoken)
        │
        └── the live monitor sends {"t": "gesture", "name": "hug"}
                │
                ▼
         the portrait page finds hug.js (already loaded) and plays it
```

### When the page loads

1. The portrait asks the server for `gestures/index.json`: a list of every
   `.js` file in `portrait/gestures/` except the `_` ones.
2. It loads each file and reads its settings. `left: true` makes a mirrored
   copy called `<name>_left`, `idle` adds it to her idle moves,
   `private: true` keeps it away from stream chat.
3. The viewer (`./viewer.sh`) makes a button for every gesture it found. A
   file with a mistake in it gets a pink line in the panel saying which
   file and what's wrong, instead of a missing button.

Files are read fresh on every page load, so after editing a gesture, F5
is enough.

### What sets a gesture off

| Trigger | How |
|---------|-----|
| She chooses | In `tags` mode her prompt offers a few gestures that fit her mood (names only), and she writes the tag where it fits. Private ones are only offered in your own conversations |
| Meaning | In `meaning` mode the embedding model compares what was said with each gesture's description |
| Keywords | A word from a gesture's `keywords` inside an action she writes (`*beckons you closer*`), or its emoji anywhere. Also you saying hi or asking for a hug |
| Chat | Viewers' `!wave`, `!hug`, a first "hi", "lol" (never private gestures) |
| You | `/portrait wink`, or the button in the viewer |
| On her own | Gestures with `idle`, every 25 to 55 seconds while she's idle, in the moods they're marked for |
| Events | She waves when she wakes up and shrugs when a tool fails |

`/portrait gestures <mode>`, or the **gestures** row in the settings pane,
switches between `tags`, `meaning`, `keywords` and `off`. See
[Portrait](portrait.md#gestures) for the details of each. Her clothes
follow the same setting unless `portrait.clothes` says otherwise; see
*Her clothes* in [Companion](companion.md).

## How she picks one

There are three ways, and you choose which with `/portrait gestures <mode>`
or the **gestures** row in the settings pane. Every gesture file and clip
takes part in all three; the same two lines in a file feed them:

```js
about: "sultry come-hither, teasing, inviting",          // tags and meaning
keywords: ["beckon", "come hither", "crooks a finger"],  // keyword fallback
```

### Tags: she decides

Not the default. Any line in her prompt about her body changes how a
small model talks (more narrated actions, a different rhythm), so
`keywords` is the default: gestures come from the actions she writes
anyway, and her prompt stays exactly as her persona has it. Switch to
`tags` for a bigger model that handles it well.

Her system prompt gets one short line offering a few gestures that fit
her mood right now, names only, and nothing about how to write:

> You can move on screen: put one of these where it fits: [hug]
> [blow_kiss] [giggle] [shy] [wink] [beckon_kiss] [bounce] [wave]. Most
> replies need none.

About 50 tokens. Which names come up depends on her mood band (grudge,
cool, neutral, warm, loving, lewd; a sad mood puts `cry` first), from
`BAND_PICKS` in `life/gestures.py`, and `portrait.gestures_offered` (8) sets how
many. Lewd ones are only offered in the lewd band, and never while she's
tame on stream.

It used to list every gesture with what it's for. With forty-odd gestures
that was hundreds of tokens, and a small model read it as an invitation to
narrate a move in every line: "(giggles softly) ... (beckons him over)".
Written `[name] (what it's for)`, models also copied the descriptions
instead of writing the tag. A handful of names does the job; every gesture
still plays from a described move (below), the keyword fallback and
meaning mode.

The language model reads the conversation and, when it fits, writes the
tag into its reply like any other word. Nothing else chooses: it's the
same reasoning that picks her words, so it understands the moment, not
just the vocabulary. That's why it suits role-play: "come a little
closer..." in a teasing scene gets `[sultry_beckon]` with no keyword in
sight.

As the reply streams in, the tag is cut out before anything is shown,
spoken or saved, and the portrait is told to play it. Private gestures are
left out of the line in chat rooms, so she can't pick them there.

**A move she describes plays too.** If she still narrates one, an aside in
parentheses or asterisks that clearly matches a gesture's `about` (and
name) plays that gesture: "(beckons you over and blows a kiss)" is
`beckon_kiss`, "*waves hello*" is `wave`. The words stay as she wrote
them. An aside has to share at least two words with the gesture and be
mostly about it, so "(poses, shifting between a few animations)" or
"*giggles, realizing what he's doing*" play nothing. Each gesture plays
once per reply, and only gestures she could be offered on that turn
(nothing private in chat, nothing lewd while tame).

The `about` text is the whole interface: write it as "when to use this",
short and concrete. A vague `about` gets picked at odd times; no `about`
means she never picks it herself.

Cost: about 60 tokens of prompt (cached by llama.cpp, so read once) plus a
few output tokens when she uses one.

### Meaning: the embedding model decides

After she answers, the embedding model (the one that recalls her memories)
turns two things into vectors, lists of numbers that capture meaning:

- the exchange: "They said: ... She answered: ...";
- a short description of each gesture. The built-ins have hand-written
  ones; every other gesture or clip with an `about` gets "A moment for the
  gesture sultry beckon: sultry come-hither, teasing, inviting."

It compares the exchange with every description (cosine similarity, 0 to
1) and also with a few "ordinary reply" descriptions (facts, a finished
task, an explanation). A gesture plays only if it beats the best
"ordinary" score by `portrait.meaning_margin` (0.04 by default), so most
replies get nothing. `/portrait meaning <text>` shows the scores for any
line, and the log records them for every reply.

It runs after the reply, off the turn's path (10 to 30 ms), needs the
embedding server, and is fuzzier than tags. Private gestures only take part
in your own conversations.

### Keywords: the safety net

Underneath both modes (and alone in `keywords` mode), the portrait watches
what she writes. A word from a gesture's `keywords` inside an action
(`*beckons*`, `*puts a finger to her lips*`) plays it; an emoji in the list
(🤫) plays it anywhere. A keyword matches the start of a word, so `hug`
catches hugs and hugging. A tag she wrote herself always wins over a
keyword, and the earliest match in the reply wins over later ones.

Keywords only look inside `*actions*`, never at ordinary sentences, so
"I hugged a tree today" doesn't make her hug.

For a `.vrma` clip, put `about` and `keywords` in `clips.json`.

## What happens every frame

About 60 times a second the portrait builds her pose in layers:

1. **Her own body language.** `portrait.js` sets her head and neck (where
   she's looking), chest and shoulders (breathing), spine (sway).
2. **Rest pose.** Arms down, elbows soft, fingers a little curled, legs
   straight. Any other bone a gesture has touched goes back to straight.
3. **Gestures on top.** For each playing gesture, the player:
   - works out a **weight** from 0 to 1: rising over the fade-in, 1 while
     it plays, falling over the fade-out;
   - finds the two keys around the current time and eases between them
     (smoothstep, so motion starts and stops gently);
   - turns each bone towards that pose by the weight (a quaternion slerp),
     or, for `+` bones, adds the rotation on top of what's there.
4. **Expressions.** The gesture's `expr` values are applied: smiles,
   winks, blush, tears.
5. **Physics.** three-vrm runs the spring bones (hair, ears, tail), so
   they swing from whatever the body just did.

Two consequences worth knowing:

- **A gesture never has to return to rest itself.** The fade-out blends
  it back into her normal pose.
- **Starting a new gesture fades the old one out** while the new one fades
  in, so you can interrupt freely.

Gestures run on real time, not frame count, so they last the same on a
slow machine and a fast one.

## The skeleton and its numbers

Every VRM model has the same named bones (the VRM humanoid standard):
`hips`, `spine`, `chest`, `upperChest`, `neck`, `head`, `leftShoulder`,
`leftUpperArm`, `leftLowerArm`, `leftHand`, the finger bones, and the legs,
each with a left and a right. That's why one gesture works on every VRM
model.

Rotations are `[x, y, z]` in **radians** (π ≈ 3.14 is half a turn, 1.57
a quarter turn, 0.5 is about 30°). They're measured from the T-pose: all
zeros means arms straight out to the sides, palms down.

### Directions, right side

| Bone | x | y | z |
|------|---|---|---|
| `rightUpperArm` | rolls the whole arm | + swings it forward, − back | 0 straight out, + lowers (1.22 hangs at her side), − raises above the shoulder |
| `rightLowerArm` | (use the 4th number instead) | + bends the forearm forward, towards her chest | − bends it up (−2.4 brings the hand near the shoulder), + down |
| `rightHand` | rolls the palm | swings the hand side to side | flexes the wrist up or down |
| `'+head'`, `'+neck'` | + nods down | turns left or right | tilts towards a shoulder |
| `'+spine'`, `'+chest'` | + leans forward | twists | leans sideways |
| `rightUpperLeg` | − lifts the leg forward | | |
| `rightLowerLeg` | + bends the knee | | |
| `rightFoot` | tilts the foot (keeps it flat when the knee bends) | | |

### The left side is a mirror

Use the right side's numbers with **y and z flipped**:

```js
rightUpperArm: [0, 0.8, 1.15]    // right hand to her chest
leftUpperArm:  [0, -0.8, -1.15]  // the same thing, left hand
```

You rarely need to type the left side: `both({...})` mirrors a right-side
pose onto both arms, and `left: true` makes a whole left-handed copy.

### A 4th number: twisting a forearm

`rightLowerArm: [0, 2.0, -0.55, -0.4]`: the 4th number turns the forearm
about its own length, like turning a doorknob, before the bend. It's how a
palm comes to face the right way without the wrist bending unnaturally.
Combine it with the hand's x for the rest of the turn.

### Plain bones and `+` bones

- **Plain** (`rightUpperArm`): "point this bone here". Used for arms, hands,
  fingers and legs.
- **With `+`** (`'+head'`, `'+spine'`, `'+chest'`): "add this to what she's
  already doing". Used for bones the portrait animates itself (her head
  follows her gaze, her chest breathes), so the gesture adds a nod or a
  lean without stopping the rest.

### Hips are special

`hips: [x, y, z]` is a **position in metres**, not a rotation:
`hips: [0, 0.15, 0]` lifts her 15 cm (the jump uses it), `[-0.025, 0, 0]`
shifts her weight onto one leg. A `left: true` copy mirrors it too, so a
sway to her right becomes a sway to her left.

## Anatomy of a gesture file

Here's `wink.js`, a whole gesture:

```js
// wink: a playful wink with a little head tilt and a smile
export default {
  about: "playful, teasing, a little flirty",
  dur: 1.6, fade: [0.25, 0.4],
  keys: [
    [0.0, { '+head': [0.02, 0, 0] }],
    [0.35, { '+head': [0.04, -0.06, -0.16] }],
    [1.1, { '+head': [0.04, -0.06, -0.17] }],
    [1.6, { '+head': [0.01, 0, -0.04] }],
  ],
  expr: { blinkRight: [[0, 0], [0.3, 1], [0.95, 1], [1.2, 0]],
          relaxed: [[0, 0], [0.3, 0.55], [1.6, 0.4]], blush: 0.25 },
};
```

### The keys

| Key | What it does |
|-----|--------------|
| `dur` | How long it plays, in seconds |
| `fade` | `[in, out]`: seconds to blend in and back out |
| `keys` | `[[time, pose], ...]`, times in seconds from the start |
| `expr` | Her face while it plays (below) |
| `osc` | A wobble on top: `[[bone, axis, amount, speed], ...]`. The wave uses `['rightHand', 1, 0.3, 2.3]`: hand, y axis, 0.3 radians, 2.3 times a second |
| `add` | Poses added on top for the whole gesture, like `{'+head': [0, 0, 0.14]}` |
| `hips` | (inside a pose) Her position, metres |
| `sob` | `true`: little shoulder hitches, used by `cry` |
| `then` | `'pant'`: another gesture that fades in as this one ends, used by `jog` |

### Settings

| Setting | What it does |
|---------|--------------|
| `about: "..."` | When to use it. Offers it to her as a tag in tags mode, and is what meaning mode compares with. Without it she won't choose it herself, but it still plays from buttons, commands and idle |
| `keywords: [...]` | Words that play it when she writes them inside an `*action*`, and emoji that play it anywhere |
| `lights: [[0, 0], [8, 0.9], [10, 0.3]]` | Her light strips throb while it plays: seconds and how hard (0 to 2, about 1.4 at a peak), joined smoothly; the throb gets faster as it gets brighter. A chain's curve runs over the whole chain. Only shows with light strips on |
| `idle: true` or `idle: ['warm', 'loving']` | One of the things she does on her own when nothing's happening: `true` in any mood, a list only in those mood bands (`grudge`, `cool`, `neutral`, `warm`, `loving`, `lewd`). The pose studio's Details tab has a box for each. The debug panel shows what she'd pick from in the mood you set, with **▶ play an idle** to try one |
| `private: true` | Never triggered from stream chat, and only offered to her in your own conversations |
| `left: true` | Also make a mirrored copy, `<name>_left` |
| `full: true` | It only reads with all of her on screen (her legs): offered to her, and played as an idle move, only while the portrait is framed full body. In the bust view it would be a tag that shows nothing |
| `face: 'away'` or `face: 'me'` | She turns at the hips so her back (or her front) is square to you, from wherever you're looking: front, side or behind. The turn is worked out once as it starts, so you can still drag round her while it plays. A `+hips` turn in the keys comes on top of it. `bend_over` uses `away`. Kept when you open and save it in the pose studio, and the studio's preview turns her the same way |
| `touch: [...]` | Touch zones it answers when you click her: `['legs']`. See *Touching her* in [portrait](portrait.md) |
| `moods: [...]` | With `touch`: the mood bands (`cool`, `neutral`, `warm`, `loving`) or mood names it suits. Leave it out for any mood |
| `prop: 'mug'` | The prop it's made with (a `.glb` in `portrait/props/`, placed in her hand from the pose studio's *Prop* tab); opening the gesture in the studio puts it in her hand. Her morning coffee plays `coffee_pickup`, `coffee_sip` and `coffee_putdown`; reading plays `book_open_pickup`, `book_read_turn`, `book_read_lookup` and `book_open_putdown` (a prop called `book_open` finds `book_open_pickup` and `book_open_putdown` by name). She holds one prop at a time: picking one up puts the other down first. While she holds one, only its own moves (named like its pick-up: `coffee_*`, `book_*`) and gestures that leave her arms alone play, so a wave or a hug from chat, a touch or her reply doesn't swing it about. Walking away puts it down |
| `prop_at: 0.9` | With `prop`: the second the prop appears in her hand (picking up) or goes (putting down) |
| `hold: true` | With `prop`: her last pose is held after the gesture ends, so her arm stays round the mug between sips, until it's put down |
| `clothes: [{ at: 2.0, off: ['top'] }]` | On a model whose clothes come off: a piece goes (or, with `on`, comes back) at that second. Taking a piece off plays the gesture that has it: `tie_off`, `top_off`, `bottoms_off`. Such a gesture never plays in tame mode or on a model without that piece on. The pose studio's Details tab sets it (**+ clothes**). See *Her clothes* in [Companion](companion.md) |

### How keys fill in

You don't have to repeat every bone in every key. For each bone, the
player looks for the nearest keys **that mention that bone** on either side
of the current time and eases between them. A bone missing from the later
keys simply holds its last value.

So: **put the full pose on the first and the last key**, and in between
list only what changes. `sultryBeckon.js` does exactly that: the arms are
in the first and last keys, and the keys in between only curl the fingers.

### Her face: `expr`

A number holds an expression for the whole gesture; a list of
`[time, value]` pairs animates it:

```js
expr: { happy: 0.6 }                                   // smile throughout
expr: { blush: [[0, 0], [0.8, 1], [3, 1], [3.6, 0]] }  // blush rises, holds, fades
```

| Name | What it is |
|------|------------|
| `happy`, `sad`, `angry`, `relaxed`, `surprised` | Moods. VRoid's `happy` opens the mouth into a grin; `relaxed` is a softer smile with the eyes eased |
| `blink`, `blinkLeft`, `blinkRight` | Eyes. `blinkRight: 1` closes her right eye (a wink) |
| `aa`, `ih`, `ou`, `ee`, `oh` | Mouth shapes. `ou` is a pucker |
| `blush`, `tears` | Luna's own overlays, 0 to 1 |

A wink's eye opens again by itself when the gesture ends.

### Helpers from `_pose.js`

```js
import { both, fingers, open } from './_pose.js';
```

| Helper | What it gives you |
|--------|-------------------|
| `both({ right side })` | The same pose on both arms, left mirrored |
| `fingers('right', 0.5)` | Fingers curled: 0 straight, 0.5 relaxed, 1 a fist |
| `open('right')` | Fingers flat |
| `REST` | Her normal standing pose, if you want to return to it explicitly |

For one finger different from the rest (pointing, shh), set its three
bones yourself after the helper:

```js
...fingers('right', 0.9),                      // curl them all
rightIndexProximal: [0, 0, 0], rightIndexIntermediate: [0, 0, 0], rightIndexDistal: [0, 0, 0],
```

## Writing one, step by step

Say you want her to put a hand on her heart.

**1. Start with one bone.** Make `portrait/gestures/hand_on_heart.js`:

```js
export default {
  dur: 3, keys: [[0, { rightUpperArm: [0, 0.8, 1.15] }], [3, { rightUpperArm: [0, 0.8, 1.15] }]],
};
```

Run `./viewer.sh`, click **hand on heart**, drag round to look from the
side. The upper arm should come down and forward.

**2. Add the forearm.** Bend it towards her chest:

```js
rightLowerArm: [0, 2.15, -0.15],
```

F5, click, look. Nudge one number at a time by about 0.1 to 0.3 until the
hand sits where you want.

**3. Fix the hand.** If the palm faces the wrong way, change `rightHand`'s
x, or add a 4th number to `rightLowerArm`. Check from the side.

**4. Give it life.** A second key a little different from the first, so
she isn't frozen, a head tilt, a face:

```js
import { fingers } from './_pose.js';

const HAND = { rightUpperArm: [0, 0.8, 1.15], rightLowerArm: [0, 2.15, -0.15], rightHand: [0, 0.2, 0] };

export default {
  about: "touched, grateful",
  dur: 3.0, fade: [0.5, 0.6],
  keys: [
    [0.0, { ...HAND, ...fingers('right', 0.2), '+head': [0.06, 0, 0.08] }],
    [1.5, { '+head': [0.09, 0, 0.12] }],
    [3.0, { ...HAND, ...fingers('right', 0.25), '+head': [0.06, 0, 0.1] }],
  ],
  expr: { relaxed: 0.4, blush: [[0, 0], [1, 0.5]] },
};
```

**5. Let her use it.** The `about` line is all it takes. Within about 20
seconds she has `[hand_on_heart]` in her prompt, and `/portrait
hand_on_heart` works.

## Common mistakes

| You see | Why | Fix |
|---------|-----|-----|
| No button for your gesture | A typo in the file, or a viewer started before an update | Look for a pink line under the buttons; restart `./viewer.sh` once after updating Luna |
| Her left arm goes the wrong way | Left uses the right's numbers with y and z flipped | Flip the signs of y and z, or write the right side and use `both()` |
| She leans over like a falling tower | `'+hips'` rotates her whole body from the hips | Use plain `hips: [x, y, z]` (metres) to move her |
| Palm faces the wrong way | The forearm and wrist need a roll | Change `rightHand` x, or add a 4th number to `rightLowerArm`; steps of 0.3 |
| An arm points somewhere odd mid-gesture | A bone missing from the first key falls back to a later key, or vice versa | Put the full pose on the first and last keys |
| A hand goes through her body | The pose is fine from the front only | Drag round to her side in the viewer and adjust y |
| It snaps instead of easing | `fade` too short, or keys too close together | `fade: [0.4, 0.6]` is a good start |

## Code or a .vrma clip?

| | Gesture in code | `.vrma` clip |
|---|---|---|
| Made with | A text editor and the viewer | XR Animator (webcam), Blender, or a download |
| Good for | Poses, holds, small expressive moves | Fluid full-body motion: dances, walks, anything acted out |
| Lives in | `portrait/gestures/` | `portrait/animations/` |
| Settings | Inside the file | `portrait/animations/clips.json` |

Both play through the same blend, both can carry `expr` (blush, tears,
smiles), and a clip named like a gesture (`wave.vrma`) replaces it. See
[Portrait](portrait.md#animation-clips-vrma) for clips.
