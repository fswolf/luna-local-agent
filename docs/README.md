# Luna's documentation

Everything the README only touches on, one subject per page.

- [Install](install.md): the installer, LM Studio or llama.cpp, the voice server, first run
- [Configuration](configuration.md): config.json, changing settings live, logging
- [Controls and voice](controls.md): keys, voice modes, speech detection, barge-in, wake word
- [Tool calling](tools.md): every tool, turning them off, MCP servers
- [Files and commands](files.md): reading, writing with approval, allow-all, run_command
- [Web](web.md): search, research, reading pages
- [Vision](vision.md): looking at your screen
- [Reminders and alarms](reminders.md)
- [Memory](memory.md): facts, recall by meaning, the memory manager, conversation history
- [Her reasoning](reasoning.md): thought log, token confidence, adaptive thinking, introspection
- [Learning from herself](learning.md): lessons, episodes, fact cleanup, calibration
- [Moods](moods.md)
- [Portrait](portrait.md): Live2D and VRM, looking and thinking
- [Plugins](plugins.md): stream chat, Minecraft, cron jobs, Discord
- [Development](development.md): project structure, extras

---

## See inside her

<img width="1210" alt="The live view: her reply streaming in, each word shaded by how sure she was" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/live-view.png" />

[Live](reasoning.md#watching-live-monitor) at 127.0.0.1:8792: the turn as it happens, newest on top, coloured by confidence.

<img width="1210" alt="The thought viewer: every turn down the left, the selected one in full on the right" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/thought-viewer.png" />

[Thoughts](reasoning.md) at 127.0.0.1:8792/thoughts/: every turn kept, searchable, filterable by flags.

<img width="1210" alt="The memory editor: the facts she keeps about you" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/memory-manager.png" />

[Memory](memory.md) at 127.0.0.1:8792/memory/: the facts she keeps about you, to edit, retire or delete.

---

## Everything she does

- Local speech recognition with Silero voice detection
- Local language model with tool calling
- Local text-to-speech via a shared Kokoro server
- Streaming replies: she talks while she's still thinking
- Barge-in: interrupt her mid-sentence
- Optional wake word, so open mode needs no keypress
- Optional vision: she can read what's on your screen
- Three push-to-talk modes, including hands free
- Configurable AI personality, and moods that shift with the clock and the session
- Long-term memory the model writes, corrects and forgets
- Permanent SQLite fact store that retires what stops being true, with a browser editor
- Reminders in plain language, with repeats, retry and DST-safe schedules
- Alarms that ring, nag and snooze until you're actually up
- Writes and edits your files, with every change approved on screen first
- Runs shell commands and opens apps, each one approved first
- Read, write and execute permissions you set from the tools pane: allow, ask or off
- A tools pane showing what each schema costs, and switches to turn them off
- Web search the model reaches for on its own
- Scheduled jobs she runs on her own, approved once, with writes fenced to folders you pick
- Remote access from Discord for the owner only, off until you switch it on, with approvals answered right in the chat
- Plays Minecraft: joins your world, works towards a goal, asks when something's unclear
- Searchable archive of every conversation, which pruning never deletes
- Her reasoning kept per turn, with token confidence, review flags and a browser viewer
- Adaptive thinking: a deeper second look only when an answer comes out shaky
- Lessons from her own mistakes, written while she's idle and followed from then on
- Notes on every conversation, and a greeting that picks up where you left off
- Duplicate and contradicting facts merged or retired, never deleted
- Says when she's unsure, measured from her own token probabilities
- Checks every script she writes for syntax errors, without running it
- Researches properly: reads the top pages in one go and keeps the parts that answer the question
- Follow-through: when she says she'll check something and stops, she's made to actually do it
- An animated portrait that looks at your terminal and visibly thinks
- Rotating debug log that records decisions, not just errors
- Every setting changeable from the terminal and saved, most without a restart
- Diagnostics for the things that fail quietly: tool selection, prompt size, scrolling
- Themeable full-screen terminal interface
- Cross-platform architecture
