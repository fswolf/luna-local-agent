# People in the house

Luna is set up for one person: the `user` block in `agent/agent.json`
says who that is. If other people talk to her too, she can tell you
apart. She knows **who is talking**, uses their name and pronouns for
that turn, and keeps **their own memories** separate from yours.

She recognises people two ways:

- **By voice**, on every spoken turn. This needs the voices extra.
- **By face**, while [presence](vision.md#presence-noticing-youre-there)
  is watching the webcam.

Typed turns are you: the keyboard is yours. With the
[face check](#the-face-check) on, she takes a quick look to make sure.

[Who she's talking to](who.md) is the whole picture: every way a turn
reaches her, and how each is decided.

## Setting it up

```bash
python3 installer/install.py --extras voices     # SpeechBrain, for voices
python3 installer/install.py --extras camera     # OpenCV, for faces
```

Enroll people in Luna:

```
/people enroll voice Shannon    Shannon reads 5 short lines out loud, one at a time
/people enroll face Shannon     Shannon looks at the camera for a few seconds
/people                         who she knows, and how many prints each
/people cancel                  stop a voice enrolment early
/people forget Shannon [voice]  forget the voice prints, or the whole person
/people guest Mike              name the person she just saw or heard, for this session
/people keep Mike               keep a session guest for good (their own file)
```

Someone she doesn't know isn't treated as you: once you're enrolled,
she can tell when it clearly isn't you, and they get a guest's turn
with none of your memories. See [the ladder](who.md#the-ladder).

A voice enrolment shows each line to read: everyday things like "Can you
set a short timer for three minutes?", picked at random from 15 so the
prints don't all come from the same words. While it runs she only
listens: she doesn't answer the lines or act on them (no timer gets set).
A line read too quickly to make a print is asked for again.

Enroll yourself too, under the name in your `user` block. Otherwise she
can only tell "Shannon" from "not Shannon". Not Shannon is you.

Pronouns come from `agent.json`, next to your own:

```json
"user":   { "name": "Ryan", "pronouns": "he/him" },
"people": [ { "name": "Shannon", "pronouns": "she/her" } ]
```

## How she decides who's talking

1. **The voice.** Each spoken turn's recording, the same one Whisper
   transcribes, becomes a voice print. That print is compared with
   everyone's prints. The closest one counts if it clears
   `people.voice_match`. This runs alongside transcription, so it adds
   no time.
2. **The face**, but only when voices can't be compared at all (nobody
   has voice prints yet, or the voices extra isn't installed). Then the
   recognised face in front of the camera stands in.
3. **Otherwise it's you.** If her voice compare ran and matched nobody,
   the speaker counts as you, even with someone else on camera.

With the [face check](#the-face-check) on, a voice that only just
missed `people.voice_match` gets a quick look at the camera too.

On a relay station or satellite only the voice counts: the camera is at
the desk, not in that room.

The conversation shows who it was: `[Shannon] what's for dinner?`.
History and the transcript keep that label, so later turns don't put
Shannon's words in your mouth.

## The face check

Presence watches all the time. If you'd rather the webcam stayed shut,
the face check is the one-look version: off by default, and only used
while presence is off.

```
/set people.face_check true
/people check                  look now, and say who she sees
```

When it's on, she opens the camera for one picture:

- **when you type**, so Shannon at your keyboard is Shannon, and
- **when a voice only just misses** (within 0.1 under
  `people.voice_match`): not sure, so she looks.

One look counts for `people.face_check_minutes` (10) while the
conversation keeps going, so most turns don't touch the camera at all.
After 5 minutes with no turns she looks again on the next one: someone
else could have sat down. Only the biggest face in view counts.
Turns from Discord, stream chat, relay stations and scheduled jobs never
use it: the camera is at the desk.

The picture is matched against the face prints and dropped. It isn't
saved, isn't sent anywhere and never reaches the model. The logbook
says what each look found ("checked (typed): Shannon (0.52)").

On a spoken turn the look happens while she's still transcribing, so
it usually adds no time. A typed turn waits for it, at most a couple of
seconds, and only when there's no recent look to go on.

**It never holds a turn up.** A look gets `people.face_check_seconds`
(2) and the turn goes on without it after that. No OpenCV, nobody with
face prints, the camera busy (OBS, a VTuber tracker), a black frame, a
camera that hangs, a room too dark to see: she just doesn't know, and decides the usual way.
After 3 failed looks in a row it pauses for the session and says why
once. `/people` shows how it's doing, and `/people check` tries again.

The camera light comes on for each look. See
[the camera light](vision.md#the-camera-light-and-hooks) if yours can
be switched.

## Their own memories

On someone else's turn:

- **Facts** she learns go into their file (`agent/people/shannon.json`),
  not into your memory.
- **Her prompt** shows only their facts, never yours, and none of your
  preferences.
- **Corrections** like "forget that" or "actually it's…" change only
  their facts.

On your turns, nothing changes: your facts, your memory backend, as
before. Someone else's facts never show up in your turns either.

She still shares one conversation history with everyone. She's in one
room, after all.

## Privacy

Prints are numbers describing a face or a voice, not pictures or
recordings. They live in `agent/people/`, which is gitignored, and
nothing about them is ever sent anywhere.

The speaker model is SpeechBrain's ECAPA, about 80 MB. The face models
are OpenCV's YuNet and SFace. All of them download once into
`~/.cache/ai-voice/models` and run on the CPU.

## Settings

| Key | Default | Purpose |
|-----|---------|---------|
| `people.voice` | `true` | Tell people apart by voice on spoken turns |
| `people.voice_match` | `0.3` | How alike a voice must be to count as someone, 0-1. Raise it if she mixes people up, lower it if she doesn't recognise you |
| `camera.presence.match` | `0.36` | The same for faces |
| `people.face_check` | `false` | With presence off: one camera look to see who's typing, or who's talking when the voice isn't sure |
| `people.face_check_minutes` | `10` | How long one look counts |
| `people.face_check_seconds` | `2` | How long a look may take before the turn goes on without it |

All of them are on the settings page (`/settings`).

**Getting it right:**

- **Enroll in the room she listens in.** Use the same mic and the same
  distance you normally talk from. A headset print won't match you
  talking across the room.
- **Enroll again if she gets you wrong.** New prints add to the old
  ones, up to 40 a person.
