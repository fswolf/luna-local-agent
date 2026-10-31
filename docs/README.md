# Luna's documentation

Luna is a persistent-state agent manager: one mind built from several
local models working together ([what she runs on](parts.md)), with
memory and moods that carry on between sessions, heavy tooling, research,
and learning from her own turns. The companion, the assistant and the
streamer are faces on that same agent, picked with presets.

Everything the README only touches on, one subject per page.

- [Install](install.md): the installer, the model picked for your GPU, LM Studio or llama.cpp, the voice server, first run
- [Models](models.md): which models work, what's been tested, graphics memory, quants, context, using your own
- [What she runs on](parts.md): the six pieces (chat model, vision, embedding, reranker, hearing, voice), what each costs, how to leave one out or move it, and how she scales from a 9B on your desktop to a 70B on a server
- [Configuration](configuration.md): the settings page and presets, config.json, changing settings live, logging
- [Controls and voice](controls.md): keys, voice modes, speech detection, barge-in, wake word
- [Tool calling](tools.md): every tool, her own manual, turning them off, MCP servers
- [Files and commands](files.md): reading, writing with approval, allow-all, run_command
- [Web](web.md): search, research, reading pages
- [Asking a bigger model](ask.md): she asks Claude, Grok or ChatGPT when you tell her to
- [Email](email.md): checking, reading and searching your inbox, sending with your OK
- [Vision](vision.md): looking at your screen, the webcam, noticing you're there
- [People in the house](people.md): who's talking, by voice or face, and their own memories
- [Who she's talking to](who.md): how every turn is matched to a person, and what changes for a guest
- [Relay stations](stations.md): talk to her from another room on an old phone or tablet
- [Reminders and alarms](reminders.md)
- [Offers](offers.md): things she notices on her own (a full disk, a date coming up) and offers to help with
- [Knowledge](knowledge.md): your notes, manuals and PDFs as something she can look things up in
- [Memory](memory.md): facts, recall by meaning, the memory manager, conversation history
- [Her reasoning](reasoning.md): thought log, token confidence, adaptive thinking, introspection
- [Learning from herself](learning.md): lessons, episodes, fact cleanup, calibration
- [Patches](patches.md) (experimental): collecting examples, training a patch (LoRA) for her model, loading it, changing models
- [The companion](companion.md): the whole companion side in one place - persona, every mood and the exact numbers, the lewd and grudge rows, touches, gestures, sounds, settings, recipes
- [Moods](moods.md): the moods file, intensity, quick feelings she shows for a moment
- [Portrait](portrait.md): Live2D and VRM, looking and thinking
- [Cards](cards.md): her look as a picture, to switch looks or share one
- [Hologram fans](fans.md): Luna live on an HDMI or Holoscope WiFi fan
- [Textures](textures.md): new clothes, irises and skin for her 3D model from UV templates, through ComfyUI
- [Gestures](gestures.md): how her body moves, and writing your own
- [Home automation](home.md): Home Assistant on your own network, setup, what always asks, local devices
- [Sysadmin](sysadmin.md): looking after your machines, scheduled checks, other boxes over SSH, from your phone
- [Plugins](plugins.md): how they work, writing your own, scheduled jobs and Discord
- [Stream chat](chat.md): pomf.tv, Twitch, YouTube and IRC, and what viewers can and can't reach
- [Games](games.md): chess, Minecraft, Zork, Vibe City, REALITI, Game Boy, playing on her own
- [Home and devices](devices.md): Home Assistant, Lovense, toys of most brands through Buttplug.io
- [Development](development.md): project structure, extras

---

## See inside her

<img width="1210" alt="The live view: her reply streaming in, each word shaded by how sure she was" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/live-view.png" />

[Live](reasoning.md#watching-live-monitor) at 127.0.0.1:8792: the turn as it happens, newest on top, coloured by confidence.

<img width="1210" alt="The thought viewer: every turn down the left, the selected one in full on the right" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/thought-viewer.png" />

[Thoughts](reasoning.md) at 127.0.0.1:8792/thoughts/: every turn kept, searchable, filterable by flags.

<img width="1210" alt="The memory editor: the facts she keeps about you" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/memory-manager.png" />

[Memory](memory.md) at 127.0.0.1:8792/memory/: the facts she keeps about you, to edit, retire or delete.

<img width="1210" alt="The settings page: presets at the top, then each setting with a switch, slider or box" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/settings-page.png" />

[Settings](configuration.md#the-settings-page) at 127.0.0.1:8792/settings/: every setting, with search and presets.

---

## Everything she does

- Local speech recognition with Silero voice detection
- Local language model with tool calling
- Local text-to-speech via a shared Kokoro server
- Streaming replies: she talks while she's still thinking
- Barge-in: interrupt her mid-sentence
- Optional wake word, so open mode needs no keypress
- Optional vision: she can read what's on your screen, and see through your webcam when you switch it on
- [Presence](vision.md#presence-noticing-youre-there): she notices you at the desk, says hi when you come back, looks at you, and goes quiet in an empty room
- [People in the house](people.md): she knows who's talking by voice or face, and keeps each person's memories separate
- [Relay stations](stations.md): talk to her from another room through an old phone or tablet, no extra hardware
- Three push-to-talk modes, including hands free
- Configurable AI personality, and moods that shift with the clock and the session
- Long-term memory the model writes, corrects and forgets
- Permanent SQLite fact store that retires what stops being true, with a browser editor
- Reminders in plain language, with repeats, retry and DST-safe schedules
- Alarms that ring, nag and snooze until you're actually up
- [Notices things on her own](offers.md), like a disk filling up or a birthday coming, and offers to help: only acts if you say yes
- Writes and edits your files, with every change approved on screen first
- Runs shell commands and opens apps, each one approved first
- Read, write and execute permissions you set from the tools pane: allow, ask or off
- A tools pane showing what each schema costs, and switches to turn them off
- Web search the model reaches for on its own
- [Asks a bigger model](ask.md), Claude, Grok or ChatGPT, when you tell her to ("ask your big brother..."), and tells you the answer in her own words
- Scheduled jobs she runs on her own, approved once, with writes fenced to folders you pick
- Remote access from Discord for the owner only, off until you switch it on, with approvals answered right in the chat
- Plays Minecraft: joins your world, works towards a goal, asks when something's unclear
- Plays Zork I, the classic text adventure, on her own or with you calling the moves
- Plays mayor in Vibe City, building the town in your open game window while you watch
- Plays chess against you on a board page, saying a sentence or two about each move
- Lives in a REALITI city of AI agents, walking, talking and remembering
- Runs your [smart home](home.md) through a Home Assistant on your own network, locks and garage doors always asking first
- Searchable archive of every conversation, which pruning never deletes
- Her reasoning kept per turn, with token confidence, review flags and a browser viewer
- Adaptive thinking: when an answer comes out shaky, she asks herself again and goes with what most answers agree on
- A grounding check: specifics she states with no tool, memory or message behind them get flagged, and said with a hedge
- Lessons from her own mistakes, written while she's idle and followed from then on
- Notes on every conversation, and a greeting that picks up where you left off
- Recipes: the steps of jobs that went right, saved and brought back when a similar job comes up
- Ongoing projects that carry across sessions: what was tried, what was found, what's next
- A live situation block each turn: your focused window, music, machine load, what's running, what's in her hands
- Duplicate and contradicting facts merged or retired, never deleted
- Says when she's unsure, measured from her own token probabilities
- Checks every script she writes for syntax errors, without running it
- Researches properly: reads the top pages in one go and keeps the parts that answer the question
- Follow-through: when she says she'll check something and stops, she's made to actually do it
- An animated portrait that looks at your terminal and visibly thinks
- Live on a [hologram fan](fans.md): streamed over WiFi to a Holoscope fan, or on any HDMI fan
- Rotating debug log that records decisions, not just errors
- Every setting on one page in your browser (or the terminal), with search and presets, most applied without a restart
- An installer that picks the model for your graphics card, and a first start that asks your name
- Her own manual: ask how to do something and she looks it up and gives the exact command
- Diagnostics for the things that fail quietly: tool selection, prompt size, scrolling
- Themeable full-screen terminal interface
- Cross-platform architecture
