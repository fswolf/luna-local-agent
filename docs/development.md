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
├── config.py
├── control.py
├── desktop.py
├── diagnose.py
├── factstore.py
├── history.py
├── kokoro-say.py
├── llm.py
├── lmstudio.py
├── logbook.py
├── longterm.py
├── machine.py
├── mcpclient.py      # MCP servers' tools as hers - config.json "mcp", /mcp
├── main.py
├── mood.py
├── notebook.py       # her lessons and conversation notes (agent/notebook.db)
├── reflect.py        # what she does while idle - session notes, the dream pass, fact cleanup, the greeting
├── llama/            # llama.cpp's own server - install.sh, start.sh, server.env
├── embedmem.py       # recalling facts by meaning, when the embedding server is up
├── livefeed.py       # the live monitor - /monitor, 127.0.0.1:8792 (and /portrait)
├── portrait/         # her animated portrait: boot.js, live2d.js, portrait.js (VRM), look.js (where she looks), add_live2d.py, models/, vendor/, blender/
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
│   └── discord.py    # remote access for the owner over Discord
├── ptt.py
├── reminders.py
├── speech.py
├── state.py
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
├── ui.py
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
├── tts/              # experimental speech servers, each self-contained
│   ├── chatterbox/
│   └── qwen3/
│
├── docs/             # these pages - also published to the wiki by .github/workflows/publish-wiki.yml
└── README.md         # the front page: what she is, quick start, links here
```

---

# Extras

```bash
python3 kokoro-say.py                 # read the clipboard aloud through
                                      # the TTS server - bind it to a key
```
