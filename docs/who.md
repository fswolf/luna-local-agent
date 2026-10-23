# Who she's talking to

Every turn, before she answers, Luna works out who said it. That one
answer decides whose name she uses, whose memories she sees and what
she's allowed to do. This page is the whole picture: every way a turn
reaches her, how she tells people apart on each, and what changes when
it isn't you.

Setting people up (enrolling voices and faces) is on
[People in the house](people.md).

## The short version

| Where the turn came from | Who she thinks it is |
|---|---|
| Typed at the desk | You. With the [face check](people.md#the-face-check) on, whoever the camera sees |
| Spoken at the desk | The voice she recognises. Unsure, no voice prints, or clearly not you: the face at the desk has a say |
| A relay station or satellite in another room | The voice she recognises, a stranger if it clearly isn't you, otherwise you. Never the desk camera |
| Discord | You, if your Discord account is in `owner_ids`. Everyone else is ignored |
| Stream chat (Twitch, YouTube, IRC) | A viewer, by their chat name. Never you, never anyone she knows |
| Scheduled jobs, reminders, greetings | Nobody: she's starting the turn herself |

"You" is the person in the `user` block of `agent/agent.json`.

## The ladder

Everyone she talks to is on one of four rungs, and the rung decides what
she shares and what she'll do:

| Rung | Who | Name | Memory | Tools |
|---|---|---|---|---|
| **Owner** | You | Yours | All of yours | All of them |
| **Registered** | Enrolled with `/people enroll` (Shannon) | Theirs | Their own file, kept for good | All of them |
| **Guest** | Someone she met this session ("I'm Mike") | Theirs | Kept in memory only, gone on restart | A short safe list, plus their own facts |
| **Stranger** | Someone who clearly isn't you, and she doesn't know | None | Nothing kept | A short safe list |

The safe list is the clock, sums, web search, the system status, her
manual and `meet_guest`. Nothing that reads your files, screen, mail,
history or home, and nothing that acts for you. On a guest's or a
stranger's turn your preferences and facts never reach her prompt, and
she's told to keep your private life private.

**She only steps down from owner on evidence.** A face or a voice counts
as a stranger only when it's compared with your own prints and is
clearly not you (0.1 under the match line). Nothing to compare with
means you: no camera, a dark room, a voice that only just missed, or you
never enrolled. So a broken camera never locks you out of your own
memory. To be told apart from strangers at all, enroll yourself, by face
and by voice.

**Meeting someone.** When a stranger tells her their name, or you
introduce them ("this is my friend Mike"), she calls `meet_guest` and
puts that name to the face and voice she just saw and heard. For the
rest of the session she knows Mike: his name, and what he tells her, all
in memory only. `/people guest Mike` does the same from the keyboard.
Nothing about a guest touches the disk unless you keep them:
`/people keep Mike` makes him registered, with his prints and facts in
his own file. That's always your call, never hers.

## What she uses to tell

**Voice prints.** Each spoken turn's recording becomes a print (192
numbers from SpeechBrain's ECAPA model) and is compared with everyone's
enrolled prints. The best match counts if it clears `people.voice_match`.
It runs alongside transcription, so it costs no time. This works the
same at the desk, on a relay station and on a satellite: they all hand
her the recording.

**Presence.** With `camera.presence.enabled`, the webcam watches all the
time at a few checks a second and recognises enrolled faces (YuNet finds
the face, SFace makes a 128-number print). She always knows who's in
front of the desk.

**The face check.** The one-look version of presence, for when you'd
rather the camera stayed shut. With `people.face_check` on and presence
off, she opens the camera for a single picture when you type, or when a
voice only just missed or sounded like a stranger. Step by step [below](#the-face-check-step-by-step).

**The platform.** Discord and stream chat say who sent a message. She
trusts Discord's account ID for you (`owner_ids`) and treats every chat
name as a stranger's, whatever it claims.

## How a spoken turn at the desk is decided

1. **A voice she recognises wins.** "Shannon" is Shannon (and Mike is
   Mike, once she's met him), whoever is on camera.
2. **The face gets a say** when the voice can't settle it: no voice
   prints to compare with, a voice that only just missed (within 0.1
   under `people.voice_match`), or a voice that's clearly not yours. The
   face comes from presence, or from a face check. A face she knows wins,
   so your face overrules a stranger-sounding voice (a cold, a bad mic).
3. **A stranger,** if the voice or the face clearly isn't you and nothing
   says otherwise.
4. **Otherwise it's you.**

A relay station or satellite skips step 2. Its microphone is in
another room, so the face at the desk says nothing about who's talking
there.

## The face check, step by step

What happens on a turn with `people.face_check` on:

1. **Is a look needed at all?** Not if presence is watching (it already
   knows), not on a Discord, stream chat, station or scheduled turn, and
   not if the last look is still good. A look stays good for
   `people.face_check_minutes` (10) as long as turns keep coming. After
   5 minutes with no turns it's stale, because someone else could have
   sat down.
2. **Can she look?** OpenCV installed, someone enrolled by face, not
   paused. If not, she notes why once in the logbook and doesn't ask
   again for a minute.
3. **One picture.** The webcam opens, asked for a small picture (640
   wide, the size faces are matched at), throws away a few frames while
   the exposure settles, keeps one and closes again. The
   [camera hooks](vision.md#the-camera-light-and-hooks) run around it.
4. **The biggest face** is found (YuNet), turned into a print (SFace)
   and compared with everyone's face prints. It counts if it clears
   `camera.presence.match`.
5. **The answer** is a name, "someone who isn't you", "a face she can't
   place", "nobody in view" or "too dark to see anyone". All of those
   are answers: the last three just mean the turn is decided the usual
   way. The logbook gets one line, like `checked (typed): Shannon (0.52)`.
   Anyone other than you is looked at again after 2 minutes (not 10),
   so when you sit back down she doesn't treat you as a guest for long.

### When it happens

- **Typing:** when you press Enter, if there's no good look to go on.
  The turn waits for it, at most `people.face_check_seconds` (2).
- **Speaking:** the look starts the moment the voice match comes back
  unsure, while Whisper is still turning your words into text. By the
  time she knows what you said, she usually knows who said it, so it
  adds no time.
- **Never twice:** a turn that finds a look already under way waits for
  that one instead of opening the camera again.

### When something goes wrong

The face check is an extra. Every failure ends the same way: she
doesn't know, and the turn carries on exactly as if it were off.

| What goes wrong | What she does |
|---|---|
| No OpenCV, nobody enrolled by face | Doesn't look; says why once, checks again in a minute |
| Face models still downloading | Doesn't look; tries again in 20 seconds. Still missing after 10 minutes: a failure |
| Camera won't open (in use by OBS or a VTuber tracker, no permission) | A failure |
| The look takes longer than `face_check_seconds` | The turn goes on without it. A failure |
| The camera driver hangs completely | That look is left behind; later turns don't wait for it. `/people` says it's stuck |
| Something unexpected breaks in the code | Caught, logged, counted as a failure |
| A hook (camera.before/after, a plugin) fails or hangs | Logged; the picture is taken anyway |

After a failure she waits a minute before looking again. Three failures
in a row pause the face check for the session, with one line in the
chat saying why. `/people check` clears the pause and looks straight
away.

## What changes when it's someone else

On anyone else's turn:

- **She uses their name and pronouns** (a registered person's from their
  file or the `people` list in `agent.json`; a guest's name as they gave
  it), and her prompt says she's talking with them, not you. A stranger
  gets no name, and she can ask for one.
- **Their own memories.** A registered person's facts go into their file
  (`agent/people/<name>.json`), a guest's stay in memory, a stranger's
  aren't kept. Her prompt shows their facts, never yours, and none of
  your preferences. "Forget that" only touches theirs.
- **Guests and strangers get the short tool list** ([the ladder](#the-ladder)).
- **The conversation shows it:** `[Shannon] what's for dinner?`,
  `[guest] hi!`, and history and the transcript keep the label, so later
  turns don't put their words in your mouth.
- **One shared history.** She's in one room, so everyone sees the same
  conversation. That includes a stranger's turn: she's told not to share
  your private life, but the recent conversation is in front of her.

Stream chat is stricter again: a viewer's turn never touches history or
memory, sees none of your private context and gets a short list of safe
tools. See [Chat](chat.md#this-is-the-one-input-that-isnt-you).

## Privacy

- **Prints are numbers, not pictures or recordings.** They live in
  `agent/people/`, which is gitignored, and never leave your machine.
- **Presence and the face check keep no pictures.** A frame lives in
  memory for one match and is dropped. Nothing is written to disk and
  nothing goes to the model (only `look_at_camera`, which you ask for,
  sends a picture to her).
- **The camera light** comes on whenever the webcam is open. That's the
  honest signal for anyone else in the room. If your camera allows it,
  the [camera hooks](vision.md#the-camera-light-and-hooks) can change it.

## When she gets it wrong

| What happens | Try |
|---|---|
| She calls you by someone else's name | Raise `people.voice_match` a little, and enroll yourself again where you usually sit |
| She doesn't recognise you or a guest | Lower `people.voice_match`, or enroll more lines in the room she listens in |
| A face isn't recognised | Enroll the face again in your usual light; `camera.presence.match` sets how strict it is |
| The face check says "paused" | `/people` shows why. `/people check` tries again. "Took longer than 2 s": raise `people.face_check_seconds` |
| Someone on a relay station is taken for you | Enroll their voice, and yours: on a station, voice is all she has |
| She treats you as a stranger | `/people check` looks again. If it's your voice, enroll a few more lines where you usually sit |
| Strangers are taken for you | Enroll yourself by face and voice: without your prints she has nothing to tell you apart by |

`/people` shows everyone she knows, how many prints each has, and how
voices, presence and the face check are doing. The logbook says what
each turn was decided as (`heard (Shannon): ...`, `checked (typed): ...`).

## For developers

- `people.decide(voice_name, voice_checked, voice_score, at_desk)`
  decides a spoken turn; `people.typed_speaker()` a typed one. Both
  return a name, `people.STRANGER`, or None for the owner, and never
  raise.
- `people.verdict(kind, vector, threshold)` is the one matcher: a name,
  `STRANGER` (the owner's own best score is `MARGIN` under the line), or
  None. Voices, presence and the face check all use it.
- Session guests live in `people._session` (`meet`, `keep`,
  `forget_guest`); `facts`, `add_fact` and `set_fact` route to it, and
  drop anything for `STRANGER`. `people.tools_for(speaker)` is the tool
  ceiling `assistant._respond` passes as `tools_allowed`.
- The answer travels with the turn as `turnctx.current().speaker`;
  `people.guest()` reads it and `people.user_line()` writes the prompt
  line from it.
- `facecheck.check(reason, force=False)` is the face check. Whatever
  fails, it returns None ("couldn't tell") and the turn carries on as if
  it were off. `facecheck.status()` is the `/people` line,
  `facecheck.unsure(score)` the grey-zone test.
- The look runs on its own thread with a deadline, and its result is
  shared: a second caller waits only for what's left of the first one's
  budget. `assistant._whose_voice(..., at_desk=True)` starts it early on
  spoken desk turns.
- `camera.frame(device, width)` is one picture for code to look at
  (never raises); `camera.opened(device)` wraps any open of the webcam
  in the hooks.
- The tuning constants (the grey zone, the 5-minute gap, retry and
  pause counts) are at the top of `facecheck.py`.
  `tests/test_facecheck.py` fakes each failure; `tests/test_ladder.py`
  covers the rungs.
- Plugins can hear the webcam open and close with
  `on_camera_open(device)` and `on_camera_close(device)`.
