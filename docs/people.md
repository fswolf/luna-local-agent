# People in the house

Luna is set up for one person: the `user` block in `agent/agent.json`
says who that is. If other people talk to her too, she can tell you
apart. She knows **who is talking**, uses their name and pronouns for
that turn, and keeps **their own memories** separate from yours.

She recognises people two ways:

- **By voice**, on every spoken turn. This needs the voices extra.
- **By face**, while [presence](vision.md#presence-noticing-youre-there)
  is watching the webcam.

Typed turns are always you: the keyboard is yours.

## Setting it up

```bash
python3 installer/install.py --extras voices     # SpeechBrain, for voices
python3 installer/install.py --extras camera     # OpenCV, for faces
```

Enroll people in Luna:

```
/people enroll voice Shannon    the next 5 things said to her out loud are Shannon's voice
/people enroll face Shannon     Shannon looks at the camera for a few seconds
/people                         who she knows, and how many prints each
/people cancel                  stop a voice enrolment early
/people forget Shannon [voice]  forget the voice prints, or the whole person
```

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

The conversation shows who it was: `[Shannon] what's for dinner?`.
History and the transcript keep that label, so later turns don't put
Shannon's words in your mouth.

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

All of them are in the settings pane.

**Getting it right:**

- **Enroll in the room she listens in.** Use the same mic and the same
  distance you normally talk from. A headset print won't match you
  talking across the room.
- **Enroll again if she gets you wrong.** New prints add to the old
  ones, up to 40 a person.
