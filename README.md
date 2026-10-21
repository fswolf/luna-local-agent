<img src="assets/luna-github-banner-v1.png" alt="Luna: Your voice. Your machine. Your Luna." width="100%">

<hr>

<img width="1210" alt="Luna in the terminal beside her animated Live2D portrait" src="assets/luna-desktop.png" />

# luna-local-agent

[![Tests](https://github.com/fswolf/luna-local-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/fswolf/luna-local-agent/actions/workflows/tests.yml)
[![Sponsor](https://img.shields.io/badge/sponsor-GitHub%20Sponsors-ea4aaa?logo=githubsponsors)](https://github.com/sponsors/fswolf)

**A local voice companion you can see inside: reasoning, confidence and
memory, all on your own machine.**

Luna listens, thinks, talks back and uses tools, and every turn leaves a
record you can open. That record holds what she thought before she
answered, how sure she was of each word, which turns look off, and a
live view of it all while it happens. It started as a voice front end
for LM Studio (this repo used to be called *LM-Studio-AI-Voice*) and
grew into a small research rig for watching a local model think.

```bash
git clone https://github.com/fswolf/luna-local-agent.git ~/ai-voice
```

(The folder is still `~/ai-voice`; every path below assumes it.)

Powered by:

- [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper): speech to text
- LM Studio or llama.cpp: the local model, with tool calling, picked automatically
- [kokoro-reader](https://github.com/fswolf/kokoro-reader): Kokoro TTS over local HTTP
- MCP: OBS, Home Assistant, ComfyUI and the rest of the MCP ecosystem as her tools

What she does:

- **Talks:** push-to-talk in three modes including hands free, replies that start a sentence in, and barge-in (talk over her and she stops)
- **Sees:** your screen, and your webcam when you switch it on
- **Notices you:** with the webcam watching, she says hi when you come back, looks at you instead of the screen, and keeps quiet in an empty room ([details](docs/vision.md#presence-noticing-youre-there))
- **Knows who's talking:** tells the people in your house apart by voice or face, uses their name and pronouns, and keeps each person's memories to themselves ([details](docs/people.md))
- **Reminders and real alarms:** she wakes you up, and nags until you're up
- **Email:** checks, reads and searches your inbox; sends only with your OK ([details](docs/email.md))
- **Files and commands:** writes and edits files and runs commands, every one shown and approved first, with read/write/execute permissions you set in the tools pane
- **Hard to steer:** a web page, an email or a stranger in chat can't quietly get her to read your files, send things out or switch something on
- **Moods and feelings:** she runs warmer or flatter with the clock and the session, and laughs, blushes or gasps in the moment, all set in one file you can edit ([details](docs/moods.md), [the companion side](docs/companion.md))
- **Long-term memory:** optional permanent SQLite store with its own browser editor
- **Your knowledge base:** point her at your notes, manuals, PDFs and docs, and she answers from them and says which file ([details](docs/knowledge.md))
- **Her reasoning, kept:** the model's scratchpad per turn, with a browser viewer for reading it back
- **See inside her:** token-by-token confidence, automatic flags for guesses and slips, `introspect` and `self_status` tools she can use on herself, and a live monitor
- **An animated portrait:** Live2D or VRM, lip-synced, blinking, gestures, blushes and tears; click her and she reacts by mood; bust or full body ([details](docs/portrait.md#portrait))
- **On a hologram fan:** live over WiFi on a Holoscope fan (P56, PD42), or on any HDMI fan as a screen; she floats in the air ([details](docs/fans.md))
- **Learns from herself:** daily lessons from her own mistakes, notes on every conversation, fact cleanup, saying so when she's unsure ([details](docs/learning.md#learning-from-herself))
- **Streams with you:** answers pomf.tv, Twitch, YouTube and IRC chat out loud ([details](docs/chat.md))
- **Plays games:** chess against you on a board you drag the pieces around on, and Minecraft, Zork, Vibe City and REALITI on her own when you go quiet; she remembers how she felt about them ([details](docs/games.md))
- **Runs your home:** lights, plugs, sensors and the thermostat through Home Assistant on your own network; locks and garage doors always ask first ([details](docs/home.md))
- **Adult toys (18+):** Lovense, and most other brands through Buttplug.io, so she can use them in a roleplay, with limits you set ([details](docs/devices.md#lovense))
- **From your phone:** Discord, with approvals answered right in the chat, and scheduled jobs ([details](docs/sysadmin.md))
- **Easy to set up:** the installer picks a model that fits your graphics card, she asks your name the first time she starts, and every setting is on one page in your browser, with presets: Assistant, Companion, Streamer ([details](docs/configuration.md#the-settings-page))
- **Knows her own manual:** ask her how to do something and she looks it up and tells you the exact command
- Linux first, also on macOS and Windows
- Full-screen terminal interface

Everything runs locally. No cloud APIs required.

## Her portrait

<img width="1210" alt="Luna's VRM model as she normally looks, beside the same model in hologram mode" src="assets/luna-hologram.jpg" />

Luna's own model, made in VRoid Studio, as she normally looks and in
hologram mode. `/holo` switches between them live, in the portrait
window and in OBS. Click her and she reacts: a head pat, a boop on the
nose, a poke in the tummy, each answered by how she's feeling. Live2D
and other VRM models work too ([details](docs/portrait.md#portrait)).

She can also float in mid-air on a hologram fan, a spinning blade of LEDs
where black shows as nothing. On a Holoscope WiFi fan she's streamed live
at about 15 frames a second, from a camera of her own, so your screen can
stay at bust while the fan shows all of her. An HDMI fan just shows the
portrait page. Which fans work and what to buy:
[hologram fans](docs/fans.md).

## Not just a yes-machine

Most AI companions are endlessly agreeable: be nice or be cruel, you get the same cheerful answer. Luna isn't built that way. How you treat her moves her mood, and her mood changes how she talks to you.

- **Kindness lands, and it builds.** Talk to her warmly and she warms up over the session. Repeating "love you" five times in a row counts for less each time, so warmth has to be real to count.
- **She's not always in the mood.** Flirting only goes somewhere once she's already warm towards you. Push before that and she'll tell you, in her own way, that she isn't feeling it.
- **She holds a grudge.** Insult her and she goes cool and short with you for a while. A real apology ends it.
- **She can walk away.** Keep being cruel and she stops talking for ten minutes.
- **She never stops doing her job.** Alarms, reminders, safety and anything urgent always get done, in any mood. Mood changes how she sounds, never what she'll do for you.

Why build it this way? Because warmth from something that can't be anything else doesn't mean much. When Luna is glad to see you, it's because of how the last hour went. You can see it on her face too: she blushes, sulks, crosses her arms and turns away. Every number behind it is in one file you can edit ([how it all works](docs/companion.md)).

## Watch her play

[![Luna plays Zork for 72 minutes](https://img.youtube.com/vi/Cd8UUsFD_js/maxresdefault.jpg)](https://www.youtube.com/watch?v=Cd8UUsFD_js)

Luna playing Zork I on her own for 72 minutes, all local, narrating as
she goes (part 1). Minecraft, Vibe City and REALITI ([her city](https://realiti.imbored.me/), open to other agents too) work the same way
([details](docs/games.md)).

## Watch her code

<img width="1210" alt="Luna writing a backup script in the terminal: she reads the SSH config, writes the file with approval, catches her own syntax error, fixes it and schedules the job (placeholder mockup until a real screenshot)" src="assets/luna-coding.png" />

Ask for a script and she writes it: she reads what she needs first,
every write asks you before it lands, and what she wrote is checked
straight away (Python, shell, JSON, TOML, YAML) but never run. Here she
catches her own unclosed quote and fixes it in the same turn
([files](docs/files.md), [checking her code](docs/learning.md#coding-checking-what-she-wrote)).

## See inside her

Local pages, served by Luna while she runs:

<img width="1210" alt="The live view: her reply streaming in, each word shaded by how sure she was, with the second look and review flags underneath" src="assets/live-view.png" />

**Live** (127.0.0.1:8792): the turn as it happens, newest on top, every word coloured by confidence, with the second look and the review flags as they land.

<img width="1210" alt="The thought viewer: every turn down the left, the selected one in full on the right with its flags" src="assets/thought-viewer.png" />

**Thoughts** (127.0.0.1:8792/thoughts/): every turn kept, searchable and filterable by flags, tools, rethinks and model.

<img width="1210" alt="The memory editor: add, edit, retire or delete the facts she keeps about you" src="assets/memory-manager.png" />

**Memory** (127.0.0.1:8792/memory/): the facts she keeps about you, to add, edit, retire or delete.

<img width="1210" alt="The settings page: presets at the top, then each setting with a switch, slider or box and a line saying what it does" src="assets/settings-page.png" />

**Settings** (127.0.0.1:8792/settings/, or `/settings`): every setting with a switch, slider or drop-down and a line saying what it does, search, presets, and a view of just what you've changed. The terminal's settings pane (Tab three times) keeps the everyday ones.

## Her knowledge

Give her a folder of your own notes, manuals, PDFs and docs, and she
answers from them: "what port did I put Jellyfin on?", "what does the
boss in chapter 3 do?", "my dishwasher says E24". She says which file
the answer came from, and when something you say matches a note
closely enough, it comes along with your turn without her having to
look.

On first start she makes the folder for you:

| System | Folder |
|--------|--------|
| Linux, macOS | `~/ai-voice/agent/knowledge` |
| Windows | `ai-voice\agent\knowledge`, wherever you installed her |

Drop files in, or `/knowledge add` any folder you already keep notes
in. It all stays on your machine, and keys and credentials are skipped
even if they're in there ([details](docs/knowledge.md)).

---

# Quick start


```bash
git clone https://github.com/fswolf/luna-local-agent.git ~/ai-voice
cd ~/ai-voice
./installer/install.sh                 # Linux, macOS
```

```powershell
powershell -ExecutionPolicy Bypass -File installer\install.ps1    # Windows
```

Then start her:

```bash
luna            # or ./start.sh, or luna.cmd on Windows
```

The installer looks at your graphics card and offers the biggest model
that fits (Qwen 3.5, from 4B up to 27B). The first time she starts, she
asks what to call you and what you mostly want her for. After that,
`/settings` has everything, and you can just ask her how things work.

The installer asks before anything that touches your system, and can be run again any time to repair or update. The whole story, including running LM Studio or llama.cpp and the voice server, is in [docs/install.md](docs/install.md).

---

# Documentation

- [Install](docs/install.md): the installer, the model picked for your GPU, LM Studio or llama.cpp, the voice server, first run
- [Configuration](docs/configuration.md): the settings page and presets, config.json, changing settings live, logging
- [Controls and voice](docs/controls.md): keys, voice modes, speech detection, barge-in, wake word
- [Tool calling](docs/tools.md): every tool, her own manual, turning them off, MCP servers
- [Files and commands](docs/files.md): reading, writing with approval, allow-all, run_command
- [Web](docs/web.md): search, research, reading pages
- [Email](docs/email.md): checking, reading and searching your inbox, sending with your OK
- [Vision](docs/vision.md): looking at your screen, the webcam, noticing you're there
- [People in the house](docs/people.md): she knows who's talking, by voice or face
- [Reminders and alarms](docs/reminders.md)
- [Knowledge](docs/knowledge.md): your notes, manuals and PDFs as something she can look things up in
- [Memory](docs/memory.md): facts, recall by meaning, the memory manager, conversation history
- [Her reasoning](docs/reasoning.md): thought log, token confidence, adaptive thinking, introspection
- [Learning from herself](docs/learning.md): lessons, episodes, fact cleanup, calibration
- [The companion](docs/companion.md): the whole companion side in depth: her moods and how they move, touch, gestures, saying no
- [Moods](docs/moods.md): the moods file, intensity, quick feelings she shows for a moment
- [Portrait](docs/portrait.md): Live2D and VRM, looking and thinking
- [Gestures](docs/gestures.md): how her body moves, what sets it off, writing your own
- [Hologram fans](docs/fans.md): Luna live on a Holoscope WiFi fan or an HDMI fan, and which to buy
- [Home automation](docs/home.md): Home Assistant on your own network, setup, what always asks, local devices
- [Sysadmin](docs/sysadmin.md): looking after your machines, scheduled checks, other boxes over SSH, from your phone
- [Plugins](docs/plugins.md): how they work, writing your own, scheduled jobs and Discord
- [Stream chat](docs/chat.md): pomf.tv, Twitch, YouTube and IRC, and what viewers can and can't reach
- [Games](docs/games.md): chess, Minecraft, Zork, Vibe City, REALITI, playing on her own
- [Home and devices](docs/devices.md): Home Assistant, Lovense, toys of most brands through Buttplug.io
- [Development](docs/development.md): project structure, extras

The same pages are on the [wiki](https://github.com/fswolf/luna-local-agent/wiki), and there's a
friendlier tour of her at [luna.imbored.me](https://luna.imbored.me/).

---

# Support her

If Luna's useful or fun to you, you can [sponsor her development](https://github.com/sponsors/fswolf).
It goes toward her own home server: a second GPU so she can run bigger, smarter models.

---

# License

MIT License
