# Project Structure

```text
ai-voice/
│
├── installer/        # install.sh, install.ps1, install.py, uninstall.py, requirements.txt
├── launch.py         # what start.sh / luna / luna.cmd run: voice server, then Luna
├── ai-voice-ctl.py
├── alarm.py
├── assistant.py
├── chatroom.py
├── config.json
├── config/           # every setting, one namespace (config.X); one file per area:
│   ├── __init__.py   #   the namespace itself, plus /set (current, save_setting) and plugin_settings
│   ├── base.py       #   where things are read from, and her persona
│   ├── server.py     #   the model server, embeddings, reranking
│   ├── voice.py, desk.py, listening.py, abilities.py, moods.py,
│   └── permissions.py, chat.py, mind.py, portrait.py, actions.py
├── control.py
├── desktop.py
├── diagnose.py
├── factstore.py
├── history.py
├── kokoro-say.py
├── llm/              # the conversation engine, one job per file:
│   ├── prompts.py    #   the system prompt and generation parameters
│   ├── replay.py     #   stored history turned back into messages
│   ├── streaming.py  #   one completion from the model server, streamed
│   ├── rounds.py     #   the tool loop
│   ├── second_look.py#   adaptive thinking, rethink, vote, calibration, grounding
│   ├── turns.py      #   ask(): one turn end to end; prompt_budget() for /context
│   └── session.py    #   session switches (are tools working?)
├── lmstudio.py
├── logbook.py
├── longterm.py
├── machine.py
├── mcpclient.py      # MCP servers' tools as hers - config.json "mcp", /mcp
├── main.py
├── mood.py
├── notebook.py       # her lessons and conversation notes (agent/notebook.db)
├── reflect.py        # what she does while idle - session notes, the dream pass, fact cleanup, the greeting
├── skills.py         # her recipes for multi-step jobs (agent/skills.db)
├── projects.py       # ongoing projects: goal, log of tried/found, next step (agent/projects.db)
├── grounding.py      # the grounding check: specifics in a reply that nothing she was given backs up
├── situation.py      # the live lines at the top of each turn: window, music, load, plugins, next reminder
├── llama/            # llama.cpp's own server - install.sh, start.sh, server.env
├── embedmem.py       # recalling facts by meaning (and reranking), when those servers are up
├── livefeed.py       # the live monitor - /monitor, 127.0.0.1:8792 (and /portrait)
├── portrait/         # her animated portrait
│   ├── viewer/       #   the page: index.html, boot.js, portrait.js (VRM), live2d.js, gestures.js,
│   │                 #   look.js (where she looks), emotes.js (hearts, sweat drop...),
│   │                 #   hologram.js / hologram3d.js, view.py (./viewer.sh),
│   │                 #   vendor/ (bundled three.js and pixi.js; build.sh rebuilds them)
│   ├── gestures/     #   one file per gesture (wave.js, hug.js...), _pose.js helpers
│   ├── models/       #   Live2D folders and .vrm files
│   ├── animations/   #   .vrma clips (clips.json)
│   └── add_live2d.py
├── introspection/    # injected-thought experiments - make_vectors, trial, report, blind
├── memory-manager/
│   ├── manager.py
│   └── start.sh
├── thoughtlog.py     # her reasoning, per turn (agent/thoughts.db)
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
│   └── discord.py    # remote access for the owner over Discord
├── ptt.py
├── reminders.py
├── speech.py
├── interrupts.py     # stopping her: each turn's own Stop (speaking, generating, listening); HOME, barge-in, !stop
├── turnctx.py        # the running turn: who started it, its passes (job, Discord), what it has seen
├── tests/            # python -m unittest discover tests - turn safety, stopping her
├── timeutil.py
├── tools/
│   ├── __init__.py   # the registry - @tool, specs, the on/off switches
│   ├── time.py       # one module per group, matching the tools pane
│   ├── reminders.py
│   ├── memory.py
│   ├── files.py
│   ├── desktop.py
│   ├── web.py
│   ├── shell.py      # run_command - every command asks
│   └── introspect.py # the Self group - introspect, self_status, recall_episodes, note_lesson, reflect_now
├── transcript.py
├── ui/               # the TUI (prompt_toolkit), one job per file:
│   ├── shared.py     #   the conversation, the status fields, where the view is
│   ├── messages.py   #   what the rest of Luna calls: add_message, set_status...
│   ├── text.py       #   widths, wrapping, frames
│   ├── conversation_pane.py # the conversation pane and the status bar
│   ├── help.py       #   the help pane
│   ├── tools_pane.py #   the tools pane
│   ├── approval.py   #   the permission popup (ask_approval)
│   └── app.py        #   style, keys, run(), stop()
├── vision.py
├── voice_loop_kokoro.py
├── wakeword.py
├── webpage.py
├── websearch.py
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
