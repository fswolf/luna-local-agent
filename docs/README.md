# Luna's documentation

Everything the README only touches on, one subject per page.

- [Install](install.md) - the installer, LM Studio or llama.cpp, the voice server, first run
- [Configuration](configuration.md) - config.json, changing settings live, logging
- [Controls and voice](controls.md) - keys, voice modes, speech detection, barge-in, wake word
- [Tool calling](tools.md) - every tool, turning them off, MCP servers
- [Files and commands](files.md) - reading, writing with approval, allow-all, run_command
- [Web](web.md) - search, research, reading pages
- [Vision](vision.md) - looking at your screen
- [Reminders and alarms](reminders.md)
- [Memory](memory.md) - facts, recall by meaning, the memory manager, conversation history
- [Her reasoning](reasoning.md) - thought log, token confidence, adaptive thinking, introspection
- [Learning from herself](learning.md) - lessons, episodes, fact cleanup, calibration
- [Moods](moods.md)
- [Portrait](portrait.md) - Live2D and VRM, looking and thinking
- [Plugins](plugins.md) - stream chat, Minecraft, cron jobs, Discord
- [Development](development.md) - project structure, extras

---

## Everything she does

- Local speech recognition with Silero voice detection
- Local language model with tool calling
- Local text-to-speech via a shared Kokoro server
- Streaming replies — she talks while she's still thinking
- Barge-in — interrupt her mid-sentence
- Optional wake word, so open mode needs no keypress
- Optional vision — she can read what's on your screen
- Three push-to-talk modes, including hands free
- Configurable AI personality, and moods that shift with the clock and the session
- Long-term memory the model writes, corrects and forgets
- Permanent SQLite fact store that retires what stops being true, with a browser editor
- Reminders in plain language, with repeats, retry and DST-safe schedules
- Alarms that ring, nag and snooze until you're actually up
- Writes and edits your files, with every change approved on screen first
- A tools pane showing what each schema costs, and switches to turn them off
- Web search the model reaches for on its own
- Scheduled jobs she runs on her own, approved once, with writes fenced to folders you pick
- Remote access from Discord for the owner only, off until you switch it on
- Searchable archive of every conversation, which pruning never deletes
- Her reasoning kept per turn, with token confidence, review flags and a browser viewer
- Adaptive thinking — a deeper second look only when an answer comes out shaky
- Lessons from her own mistakes, written while she's idle and followed from then on
- Notes on every conversation, and a greeting that picks up where you left off
- Duplicate and contradicting facts merged or retired, never deleted
- Says when she's unsure, measured from her own token probabilities
- Checks every script she writes for syntax errors, without running it
- Researches properly: reads the top pages in one go and keeps the parts that answer the question
- Rotating debug log that records decisions, not just errors
- Every setting changeable from the terminal and saved, most without a restart
- Diagnostics for the things that fail quietly — tool selection, prompt size, scrolling
- Themeable full-screen terminal interface
- Cross-platform architecture
