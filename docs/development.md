# Project Structure

```text
ai-voice/
│
├── installer/        # install.sh, install.ps1, install.py, uninstall.py, requirements.txt
├── launch.py         # what start.sh / start.cmd / luna / luna.cmd run: voice server, then Luna
├── ai-voice-ctl.py
├── config.json
├── core/             # the core loop:
│   ├── assistant.py  #   one turn, typed or spoken, start to finish
│   ├── turnctx.py    #   the running turn: who started it, its passes (job, Discord), what it has seen
│   ├── interrupts.py #   stopping her: each turn's own Stop; HOME, barge-in, !stop
│   ├── history.py, transcript.py  # the conversation, and the full record summaries never touch
│   ├── logbook.py    #   the debug log (/log)
│   ├── timeutil.py   #   time shown to her; timeparse.py reads "next tuesday at 9", timewords.py the words
│   ├── lmstudio.py, mcpclient.py, chatroom.py, control.py, machine.py, firstrun.py
├── mind/             # what she knows and how she thinks about it:
│   ├── longterm.py, factstore.py, embedmem.py  # facts, the sqlite store, recall by meaning
│   ├── knowledge.py  #   your notes, manuals and PDFs
│   ├── notebook.py   #   her lessons and conversation notes (agent/notebook.db)
│   ├── skills.py, projects.py  # recipes for multi-step jobs, ongoing projects
│   ├── thoughtlog.py #   her reasoning, per turn (agent/thoughts.db)
│   ├── reflect.py    #   what she does while idle: session notes, the dream pass, fact cleanup, the greeting
│   ├── grounding.py  #   specifics in a reply that nothing she was given backs up
│   ├── situation.py  #   the live lines at the top of each turn: window, music, load, her hands
│   ├── mood/         #   how she feels, and what moves it (mood.X works from the folder):
│   │                 #     core (her state, S), drift, exchange, appraise, walkaway, show, saving, files
│   └── webpage.py, websearch.py  # reading pages and searching, for research
├── senses/           # what she perceives:
│   ├── camera.py, vision.py, desktop.py  # the webcam, the screen, the desktop
│   ├── presence.py   #   the webcam watching: arrivals, where you are, an empty room
│   ├── facecheck.py  #   one quick look to see who's at the desk
│   ├── voices.py     #   whose voice it is, by SpeechBrain's speaker model
│   └── people.py     #   who's who: owner, registered, guests, strangers; their own facts
├── voice/            # hearing and speaking:
│   ├── speech.py     #   the front door: load_models, transcribe, speak, Player
│   ├── listen.py     #   recording you, room calibration, VAD
│   ├── tts.py        #   her words into sound (Kokoro), lip sync
│   ├── playback.py   #   mic and speakers (PortAudio, afplay on a Mac)
│   ├── bargein.py    #   interrupting her, the wake word
│   └── ptt.py, wakeword.py  # push to talk, the wake-word model
├── life/             # her own days: coffee.py, reading.py, touches.py, gestures.py, reminders.py, alarm.py
├── web/              # her pages, served on 127.0.0.1:8792:
│   ├── livefeed.py   #   the server and event stream for the monitor and the portrait (python -m web.livefeed)
│   ├── portrait_config.py, gesture_files.py, gaze.py  # what the portrait loads, gesture files, where she looks
│   ├── settings_web.py, help_web.py  # /settings/ and /help/
│   ├── dataset_web.py  #   /examples/: examples for her patches (training/dataset.py)
│   ├── portrait_window.py  # /portrait's window of its own (no address bar)
│   ├── holofan.py    #   hologram fans (python -m web.holofan sim)
│   ├── station.py, satellites.py  # relay stations in other rooms, ESPHome satellites
│   └── live.html, settings.html, station.html  # the pages themselves
├── config/           # every setting, one namespace (config.X); one file per area:
│   ├── __init__.py   #   the namespace itself, plus /set (current, save_setting) and plugin_settings
│   ├── base.py       #   where things are read from, and her persona
│   ├── server.py     #   the model server, embeddings, reranking
│   ├── voice.py, desk.py, listening.py, abilities.py, moods.py,
│   ├── permissions.py, chat.py, mind.py, portrait.py, actions.py
│   ├── schema.py     #   what every setting is: its kind, choices and the line explaining it; BASIC
│   └── presets.py    #   Assistant, Companion, Streamer; Small, Medium, Large model
├── diagnose.py
├── kokoro-say.py
├── llm/              # the conversation engine, one job per file:
│   ├── prompts.py    #   the system prompt and generation parameters
│   ├── replay.py     #   stored history turned back into messages
│   ├── streaming.py  #   one completion from the model server, streamed
│   ├── rounds.py     #   the tool loop
│   ├── second_look.py#   adaptive thinking, rethink, vote, calibration, grounding
│   ├── turns.py      #   ask(): one turn end to end; prompt_budget() for /context
│   └── session.py    #   session switches (are tools working?)
├── main.py           # startup and the main loop; typed /commands go to commands/
├── commands/         # every /command, one module per area (app, reminders, settings,
│                     #   voice, life, portrait, memory, people, patches, plugins); handle(text)
├── llama/            # llama.cpp's own server - install.sh, start.sh, server.env
├── portrait/         # her animated portrait
│   ├── viewer/       #   the page: index.html, boot.js, portrait.js (VRM), live2d.js, gestures.js,
│   │                 #   face_layers.js (blush, tears, brows), debug_panel.js (?debug=1), studio.js,
│   │                 #   look.js (where she looks), emotes.js (hearts, sweat drop...),
│   │                 #   hologram.js / hologram3d.js, view.py (./studio.sh),
│   │                 #   vendor/ (bundled three.js and pixi.js; build.sh rebuilds them)
│   ├── gestures/     #   one file per gesture (wave.js, hug.js...), _pose.js helpers
│   ├── models/       #   Live2D folders and .vrm files
│   ├── animations/   #   .vrma clips (clips.json)
│   └── add_live2d.py
├── training/         # patches (LoRA, experimental) - docs/patches.md
│                     #   dataset.py the examples (/good, /fix); export.py them for training;
│                     #   train.sh + Containerfile + train.py the run (Unsloth, ROCm);
│                     #   patches.py what's on disk and loaded (/patches)
├── introspection/    # injected-thought experiments - make_vectors, trial, report, blind
├── memory-manager/
│   ├── manager.py
│   └── start.sh
├── thought-viewer/
│   ├── viewer.py
│   └── start.sh
├── plugins/
│   ├── __init__.py   # the loader
│   ├── example.py    # template - copy this
│   ├── pomf.py       # pomf.tv stream chat
│   ├── irc.py        # an IRC channel
│   ├── twitch.py     # Twitch chat (reads anonymously; posts with a bot account)
│   ├── youtube.py    # YouTube live chat (read-only, API key)
│   ├── cron.py       # scheduled jobs - /cron, agent/cron.json
│   ├── minecraft.py  # she joins your world and plays towards a goal
│   ├── home.py       # your smart home, through a local Home Assistant
│   ├── zork.py       # she plays Zork I - /zork, saves in agent/zork/
│   ├── vibecity.py   # she plays mayor in an open Vibe City window (its AI Player server)
│   ├── chessgame.py  # chess against her on a board page - /chess
│   ├── realiti.py    # she lives in a REALITI city of AI agents
│   └── discord.py    # remote access for the owner over Discord
├── tests/            # python -m unittest discover tests - turn safety, stopping her
├── tools/
│   ├── __init__.py   # the registry - @tool, specs, the on/off switches
│   ├── time.py       # one module per group, matching the tools pane
│   ├── reminders.py
│   ├── memory.py
│   ├── files.py
│   ├── desktop.py
│   ├── web.py
│   ├── shell.py      # run_command - every command asks
│   ├── introspect.py # the Self group - introspect, self_status, recall_episodes, note_lesson, reflect_now
│   └── manual.py     # read_manual - her own docs, so she can say how to use her
├── ui/               # the TUI (prompt_toolkit), one job per file:
│   ├── shared.py     #   the conversation, the status fields, where the view is
│   ├── messages.py   #   what the rest of Luna calls: add_message, set_status...
│   ├── text.py       #   widths, wrapping, frames
│   ├── conversation_pane.py # the conversation pane and the status bar
│   ├── launcher.py   #   the pages pane: opens portrait, settings, memory... in the browser
│   ├── help.py       #   what the help says (the /help/ page, help_web.py)
│   ├── tools_pane.py #   the tools pane
│   ├── settings_pane.py # the settings pane: the everyday settings, `a` for all
│   ├── approval.py   #   the permission popup (ask_approval)
│   └── app.py        #   style, keys, run(), stop()
│
├── agent/
│   ├── agent.json
│   ├── mood.json     # how she's feeling, so a restart doesn't wipe it
│   ├── facts.db      # the sqlite memory backend (gitignored)
│   ├── thoughts.db   # the reasoning log (gitignored)
│   ├── notebook.db   # lessons and conversation notes (gitignored)
│   ├── embeddings.db # cached embeddings (gitignored)
│   ├── cron.json     # scheduled jobs (gitignored)
│   ├── minecraft.json # places she pinned, per world (gitignored)
│   └── memory.json
│
├── assets/
│   ├── alarm.wav
│   ├── live-view.png
│   ├── luna-desktop.png
│   ├── memory-manager.png
│   ├── thought-viewer.png
│   ├── ui-conversation.png
│   ├── ui-help.png
│   ├── ui-pages.png
│   ├── ui-settings.png
│   └── ui-tools.png
│
├── history/
│   ├── conversation.json
│   └── transcript.jsonl
│
├── input/
│   ├── __init__.py
│   ├── linux_keyboard.py
│   ├── mac_keyboard.py
│   └── windows_keyboard.py
│
├── reminders/
│   └── reminders.json
│
├── games/zork/       # Zork I (MIT): zork1.z3 and zork_server.py, an MCP server around dfrotz
├── tts/              # experimental speech servers, each self-contained
│   ├── chatterbox/
│   └── qwen3/
│
├── docs/             # these pages - also published to the wiki by .github/workflows/publish-wiki.yml
└── README.md         # the front page: what she is, quick start, links here
```

---

# Tests

```bash
python -m unittest discover tests     # from the repo folder; no model, UI or network needed
```

`tests/test_turn_safety.py` covers the rules that hang off a turn
(`turnctx.py`): a turn's passes end with it and never reach another
thread; outside content marks only its own turn; web requests ask once
files and outside content mix; a job writes only in `job_write_dirs`;
allow-all and Discord auto-approve step aside for outside content; the
deny list; a narrow turn (stream chat) can't attach tools outside its
list, and routing state never outlives its turn. One test runs a whole
stream-chat turn through `llm.ask` against a fake model server.

`tests/test_interrupts.py` covers stopping her (`interrupts.py`): a HOME
pressed while a turn waits for the last one still lands; a stop never
reaches the next turn and nothing clears anyone else's; HOME stops your
own turn entirely and only silences the rest; a stop wakes a waiting
loop at once; a stopped turn makes no new request to the model.

`tests/test_shared_state.py` races real threads at the state several of
them share: walking away (two appraisals finishing together walk her out
once), the on-screen conversation (painting while messages come and go),
and the microphone count PortAudio restarts check. It also checks the ui
package's public names.

`tests/test_config.py` checks the config package: every live setting has
its constant, `BASE_DIR` is the repo, and `/set` and plugin switches change
the value everyone reads (against a temporary config.json).

`tests/test_mood_day.py` plays a recorded day of her moods (cold morning,
compliments, flirting into the lewd row, a grudge, walking away, making
up, a restart...) at three intensities and checks every label, dial,
prompt line and portrait event against `tests/data/mood_day.json`. It's
what lets `mind/mood/` be reorganised without changing who she is. When
you change her moods on purpose, record it again and read the diff:
`MOOD_DAY_RECORD=1 python -m unittest tests.test_mood_day`.

`tests/test_settings_web.py` also checks that no live setting is copied
at startup (`from config import X`), which made the settings page say
"saved" while nothing changed.

`tests/offline.py` keeps every test away from real servers; import it
first in a new test file.

Run them after touching tools, the turn code, the permission checks or
anything that stops her.

---

# Extras

```bash
python3 kokoro-say.py                 # read the clipboard aloud through
                                      # the TTS server - bind it to a key
```
