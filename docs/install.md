# Install

```bash
git clone https://github.com/fswolf/luna-local-agent.git ~/ai-voice
cd ~/ai-voice
./installer/install.sh                 # Linux, macOS
```

```powershell
powershell -ExecutionPolicy Bypass -File installer\install.ps1    # Windows
```

The installer walks through it, asking before anything that touches the
system:

1. **Checks.** Python 3.10-3.13 (it offers to install 3.12 if there's
   none), your GPU, disk space.
2. **System packages** through your package manager (dnf, apt, pacman,
   zypper, brew or winget): PortAudio for audio, espeak-ng for the
   voice, git. On Linux it also offers grim, slurp, wl-clipboard and
   unrar. It shows the exact command first.
3. **Luna's Python environment.** It reuses `~/ai-voice-venv` if you
   already have one, otherwise it makes `.venv`. PyTorch comes as the
   small CPU build, since only voice detection uses it here.
4. **Her voice.** It clones [kokoro-reader](https://github.com/fswolf/kokoro-reader)
   next to this folder, in its own environment, with PyTorch for your GPU
   (NVIDIA, AMD with ROCm, Apple) or the CPU. If a voice server is
   already answering on :8899, it uses that instead.
5. **Her brain.** LM Studio (it tells you what to click), or llama.cpp
   built here (Linux) for the research features.
6. **Her model, picked for your machine.** It reads how much graphics
   memory you have and offers the biggest model that fits, with room for
   her context and her eyes:

   | Graphics memory | Model | Download |
   |---|---|---|
   | 32 GB and up | Qwen3.5 27B, Q6_K, sees | 24 GB |
   | 22-31 GB | Qwen3.5 27B, Q4_K_M, sees | 18 GB |
   | 14-21 GB | Qwen3.5 9B, Q8_0, sees | 10 GB |
   | 11-13 GB | Qwen3.5 9B, Q6_K, sees | 8 GB |
   | 8-10 GB | Qwen3.5 9B, Q4_K_M | 6 GB |
   | 6-7 GB | Qwen3.5 4B, Q6_K, sees | 4 GB |
   | less, or none | Qwen3.5 4B, Q4_K_M (runs on the CPU) | 3 GB |

   Apple Silicon counts about two thirds of its shared memory. You can
   pick another from the list. With llama.cpp it downloads the model
   into `llama/models` and points `llama/server.local.env` at it; with
   LM Studio it fetches it through LM Studio's own `lms` command, or
   tells you what to search for. All Apache-2.0, with tool calling.

   **Uncensored by default.** It then asks uncensored or standard, with
   uncensored first: the same Qwen3.5 sizes with the refusals taken out
   (huihui-ai's abliterated versions, quantised by mradermacher, eyes
   included). That's what most people run a companion on. Standard is
   Qwen's own release, which turns down some requests; `--standard`
   picks it without asking. The download sizes are the same as above,
   give or take a few hundred MB.
7. **Extras, pick any:** wake word, MCP, portrait tools, Live2D runtime,
   embedding model, the pomf chat plugin.
8. **Launchers.** A `luna` command and an app-launcher entry on Linux,
   `Luna.command` on macOS, `luna.cmd` and a Start menu shortcut on
   Windows.
9. **A health check**, then a summary of what's ready and what isn't.

Then start her:

```bash
luna            # or ./start.sh, or luna.cmd on Windows
```

The launcher starts her voice server too if the installer set one up,
and stops it again when she exits. One you were already running is
left alone.

**The first time**, before anything else, she asks three things: what
to call you, your pronouns, and what you mostly want her for
(Assistant, Companion or Streamer, see
[presets](configuration.md#the-settings-page)). Type the answers; `skip`
passes on one, `/skip` on all of it. Your name and pronouns go into
`agent/agent.json`'s `user` block, where you can change them later, and
she doesn't ask again.

**Updating:** `./update.sh` gets the latest version. It saves a copy of
your `config.json` in `agent/backups/` first, pulls the update while
keeping any changes you made, installs any Python packages the update
added, and then checks everything (below). If you and the update both
changed `config.json`, your settings win. On Windows it's `update.cmd`,
which does the same; if the pull clashes over anything else, it stops
and tells you where your saved `config.json` is. (It hasn't been tested
on Windows yet.)

`config.json` is yours and isn't in git: the first start makes it from
`config.example.json`. It used to be tracked, so the update that took
it out of git removes the old copy - `update.sh` and `update.cmd` put
yours straight back from the backup they just made.

**Checking:** `./start.sh --check` says in plain words what's missing
and how to fix it: Python packages, the model server, the voice server.
`./start.sh` runs the package part on every start, and offers to install
anything new before she starts instead of stopping with an error.

```
Luna's check:
  ✓ Python packages
  ✗ no model server answering (llama.cpp :8080 or LM Studio :1234)
      → open LM Studio's Local Server, or build llama.cpp: bash llama/install.sh
  ✓ her voice server is installed - ./start.sh starts it
```

Run the installer again any time to repair or update. It picks up
where it left off and only does what's missing. `--yes` takes every
default, and `--check` only runs the health check. Other options:
`--backend lmstudio|llama|skip`,
`--voice install|url:http://host:port|skip`,
`--gpu auto|cpu|cuda|rocm`, `--extras wakeword,mcp,portrait,...`,
`--model auto|skip|4b|9b-q4|9b|27b...`, `--standard` (Qwen's own
release instead of the uncensored one).
`python installer/uninstall.py` removes what it added and never touches
your memory, history or settings.

**Platforms, honestly:** Linux is where Luna lives and is tested. On
macOS and Windows she installs and runs as a voice and text companion.
The Linux-only parts (the global hotkey through evdev, Hyprland window
tools, grim screenshots) say "not available" instead of working, and
nobody has run her there much yet, so reports are welcome.

### By hand

```bash
python3.12 -m venv ~/ai-voice-venv && source ~/ai-voice-venv/bin/activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r installer/requirements.txt
```

You'll also need PortAudio (`portaudio-devel` / `portaudio19-dev` /
`brew install portaudio`), a model server (below) and
[kokoro-reader](https://github.com/fswolf/kokoro-reader) running on
:8899. Speech isn't synthesized inside Luna: she's a client of that
server, and stays text-only without it.

---

# Running LM Studio

1. Install LM Studio
2. Download a model
3. Start the Local Server
4. Verify it is running on:

```
http://localhost:1234
```

---

## Or llama.cpp directly

LM Studio runs llama.cpp underneath but only lets the chat API through.
Running llama.cpp's own server instead serves the same GGUF file and
opens up what LM Studio keeps inside: token probabilities, control
vectors, LoRA adapters, saved KV-cache slots. Luna works with either and
picks by herself at startup, llama-server first if both are up.

```bash
llama/install.sh          # build it - Vulkan on Linux ("rocm" for ROCm/HIP), Metal on a Mac
./start.sh                # starts llama.cpp too, then Luna; the header says "· llama.cpp"
```

Once llama.cpp is built, `./start.sh` starts it for you when no model
server is answering, waits for the model to load, and stops it again
when Luna exits. Its output goes to `llama/server.log`. A server you
started yourself (`llama/start.sh` in its own terminal, or LM Studio)
is used as it is and left running. To never auto-start it, set
`"autostart": false` (or `"backend": "lmstudio"`) in the `llm` block of
`config.json`.

`install.sh` clones llama.cpp into `llama/llama.cpp/` and builds only
`llama-server` and `llama-bench`, for this card. If a build tool is
missing it prints the exact `dnf install` line and stops. It doesn't
run sudo itself. Vulkan and ROCm builds can sit side by side; `bin/`
points at whichever was built last. Run `llama/bin/llama-bench -m
<model>` under each to see which is faster on your GPU.
`install.sh update` pulls the latest llama.cpp and rebuilds.

**On a Mac** it builds for Metal, Apple's GPU, so an Apple-silicon Mac
runs the model on its GPU with no setup beyond the tools:

```bash
xcode-select --install         # Apple's compiler
brew install cmake bash        # Homebrew: https://brew.sh
llama/install.sh
```

The newer bash is for `start.sh`: macOS still ships bash 3.2, and
`start.sh` switches to Homebrew's by itself. The GPU shares the Mac's
memory, so the model plus macOS has to fit in RAM.

On a Mac, `llama/start.sh` reads `llama/server.mac.env` instead of
`server.env`: lighter settings (one slot, smaller batches, the reranker
off) so the model leaves room for macOS and its audio. On any machine,
put your own overrides in `llama/server.local.env`, which is read last
and never committed. That's the place for `MODEL=` with your model's
full path; the default pattern matches one particular model and won't
find yours. `LLAMA_ENV=<file>` picks a settings file by hand.

`start.sh` reads `llama/server.env`, which holds the same load settings
as LM Studio's model page: context 16384, every layer on the GPU, 9
threads, batch 4096/2048, 4 parallel slots sharing one KV cache, 32
context checkpoints. Edit it there. With `MODEL` left empty it finds the
GGUF in LM Studio's own model folders (the Flatpak's included), so there's no second 10 GB copy.
If LM Studio still has a model loaded it says so, because two copies
won't fit in 16 GB of VRAM. Eject it in LM Studio first.

Thinking comes back in `reasoning_content`, where the thought log
already looks. How much she thinks is `REASONING_BUDGET` in
`server.env` (-1 unlimited, 0 off). `generation.reasoning` in
`config.json` is an LM Studio setting and llama-server ignores it.

Which server she uses:

```json
"llm": {
    "backend": "auto",
    "lmstudio_url": "http://localhost:1234/v1/chat/completions",
    "llama_url":    "http://127.0.0.1:8080/v1/chat/completions"
}
```

`auto` checks once at startup. `lmstudio` or `llama` forces one. To
switch servers mid-session, restart her.

Two more keys in the same block, both optional:

| Key | |
|-----|--|
| `model` | The model id to ask for, like `"qwen3.8-27b"`. Leave it out and she uses whatever the server has loaded. Set it on a server that holds several models (LM Studio with JIT loading, Ollama, vLLM); if that model isn't there, she shows offline instead of quietly using another |
| `api_key` | For a server that wants a key (LM Studio with authentication, vLLM `--api-key`, a hosted OpenAI-compatible endpoint). Better kept outside the repo in `~/.config/ai-voice/llm.json` as `{"api_key": "..."}`. Not needed for llama.cpp: `llama/.api_key` is used automatically |

**The model on another machine.** Put that machine's address in the
URLs above (`http://192.168.1.50:8080/...`), then on the model machine:

* llama.cpp: set `HOST="0.0.0.0"` in `llama/server.env` (the default
  only answers that machine itself), and copy its `llama/.api_key` into
  `llama/.api_key` on Luna's machine. Without the key, `auto` quietly
  falls back to LM Studio.
* LM Studio: turn on **Serve on Local Network** in the Developer tab.
* Open the port in its firewall (1234, 8080, 8081 for embeddings and
  8082 for the reranker),
  e.g. `sudo firewall-cmd --add-port=8080/tcp --permanent && sudo firewall-cmd --reload`.

`embed_url` and `rerank_url` in the same block point at the embedding
and reranker servers, if those run elsewhere too.

**Vision.** llama-server only takes images when it's started with the
model's vision adapter, a separate `mmproj-*.gguf`. `start.sh` looks
for one in the model's own folder, which is where LM Studio puts it,
and prints `vision: <file>` or `vision: off` when it starts. Without
one, every screenshot comes back "image input is not supported". A
finetune that doesn't ship its own mmproj uses its base model's (a
Qwen3.5-9B finetune takes the Qwen3.5-9B one): drop it beside the
model, or set `MMPROJ` in `server.env` to its full path (`off` disables
it). Luna asks the server whether the loaded model can see, and when
it can't, `look_at_screen` is left out of her tools and the tools pane
says why, instead of a turn failing.

**The key.** The first time `start.sh` runs it makes a random key in
`llama/.api_key` (gitignored, readable only by you) and starts the
server with it, with CORS limited to localhost. Luna reads the same
file and sends it with every request; LM Studio never sees it. Without
it, any web page open in your browser could reach a server on
localhost, and this one can write files (saved slots) and keep the GPU
busy. llama-server's own web page at :8080 will ask for the key too:
paste the contents of `llama/.api_key`.

**Token confidence.** On llama-server every turn also records the
probability of each token she produced, and the top alternatives
whenever she was less than 90% sure. LM Studio doesn't expose this.
See *Her reasoning* below for what the viewer does with it. Switch it
off with `/set thoughts.token_probs false`.

### Recalling facts by meaning

`llama/start.sh` also starts a small embedding model on
127.0.0.1:8081, beside the chat server, whenever it finds one. Its
output goes to `llama/embed.log`, and Ctrl+C stops both.

With more facts than fit in a prompt, she normally picks the ones that
share words with what you said. With the embedding server running she
picks the ones closest in *meaning*, so "I got a new graphics card"
finds the fact about the 6950 XT even though no word is shared. The
newest few facts still always travel, and a fact has to clear a
similarity floor (`llm.embed_min_score`, 0.35) to come along at all.

The model is Qwen3-Embedding-0.6B. Either download it into
`llama/models`:

```bash
mkdir -p ~/ai-voice/llama/models
curl -L -o ~/ai-voice/llama/models/Qwen3-Embedding-0.6B-Q8_0.gguf \
  https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-Q8_0.gguf
```

or search for it in LM Studio and download the Q8_0 GGUF. `start.sh`
looks in both places. It needs about 0.6 GB of VRAM. Without the model,
`start.sh` says so and starts the chat server alone. `EMBED` in
`server.env` is `auto` (start it if found), `off`, or `on` (refuse to
start without it).
Each fact is embedded once and cached in `agent/embeddings.db`; per
turn only what you said is embedded. If the server isn't answering she
goes back to matching words, with nothing to switch.

### The reranker (optional)

A second small model, Qwen3-Reranker-0.6B, can sharpen the pick. The
embedding model compares what you said and each fact as two separate
summaries; the reranker reads them side by side, so it's better at
telling a fact that answers you from one that's only on the same
topic. It's slower per fact, so it only reads the embedding's best
matches (`llm.rerank_candidates`, 24), and only on turns where more
facts match than there's room for. The similarity floor still decides
what counts as a match.

```bash
curl -L -o ~/ai-voice/llama/models/qwen3-reranker-0.6b-q8_0.gguf \
  https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/resolve/main/qwen3-reranker-0.6b-q8_0.gguf
```

or `installer/install.py --extras reranker`. `start.sh` then runs it on
127.0.0.1:8082, logging to `llama/rerank.log`. It costs about 0.6 GB on
disk and under 1 GB of VRAM. `RERANK` in `server.env` works like
`EMBED`: `auto` (start it if the model is found), `off` (never, even if
it is) or `on` (refuse to start without it). Without it, recall works
exactly as before.

### Short on memory?

On a 16 GB machine, especially a Mac where the model shares memory with
everything else, these lines in `llama/server.env` free the most:

| Setting | Saves | What you give up |
|---------|-------|------------------|
| `RERANK=off` | under 1 GB | the reranker's sharper pick |
| `EMBED=off` | about 0.7 GB | recall by meaning (back to matching words) |
| `MMPROJ=off` | about 0.6 to 1 GB | screenshots, the webcam and Vibe City pictures |
| `CTX=8192` | half the context memory | shorter conversations before old turns drop |
| `PARALLEL=1` | slot overhead | jobs and chat wait for each other |

A smaller quant of the chat model (Q4 instead of Q6 or Q8) saves the
most of all.

---

# Running the Kokoro Server

Speech is synthesized by [kokoro-reader](https://github.com/fswolf/kokoro-reader)
rather than loading Kokoro in-process. One loaded model serves every app
that asks, so the assistant starts in seconds instead of waiting on its
own copy.

```bash
git clone https://github.com/fswolf/kokoro-reader.git ~/kokoro-reader

source ~/ai-voice-venv/bin/activate
KOKORO_VOICE=af_bella python3 ~/kokoro-reader/server/kokoro_server.py
```

Check it:

```bash
curl -s localhost:8899/health
curl -s localhost:8899/voices
```

Replies are streamed. Each sentence is sent to the server the moment the
model finishes writing it, so she starts talking about a sentence in
rather than after the whole reply exists, and the next chunk is
synthesized while the current one plays, so there's no gap between them.
Chunks stay under the server's 1200-character limit.

If the server isn't answering, the assistant says so and keeps working
as a text chat.

In `config.json`:

```json
"tts": {
    "url": "http://127.0.0.1:8899",
    "speed": 1.0,
    "volume": 1.0,
    "pitch": 0.0
}
```

`pitch` is in semitones, applied to the audio after it comes back, so
it works with whatever engine is on the port, not just Kokoro. `+3` is
noticeably younger, `-3` older, and past about `±6` it stops sounding
like a person.

It shifts the formants along with the pitch, which is the naive
resample and deliberately so: a formant-preserving shift keeps the same
speaker's identity and only moves the note, which is right for music
and wrong for "give me a younger-sounding character". Moving them
together is what reads as a different person.

```
/set tts.pitch 3
```

applies immediately: no restart, so you can dial it in while she talks.

| Variable | Default | Purpose |
|----------|---------|---------|
| `TTS_URL` | `http://127.0.0.1:8899` | Server address |
| `TTS_VOICE` | `config.json` → `voice` | Voice (`af_bella`, `am_adam`, ...) |
| `TTS_SPEED` | `1.0` | 0.5 - 2.0 |
| `TTS_PITCH` | `0.0` | Semitones. `+3` younger, `-3` older |
| `TTS_VOLUME` | `1.0` | Playback gain |

Environment variables win over `config.json`. The `KOKORO_*` names still
work too, since that's what kokoro-reader itself uses.

## Using a different speech server

Nothing in the assistant is tied to Kokoro. The client speaks a
three-endpoint contract and knows nothing else about what's behind it:

```
POST /tts   {"text": ..., "voice": ..., "speed": ...}  ->  WAV bytes
GET  /health                                           ->  {"ok": true}
GET  /voices                                           ->  the voice list
```

Two things worth knowing if you write your own:

Text arrives **pre-chunked** (split on sentence boundaries, under 1000
characters) and the next chunk is requested while the current one is
still playing. So the server never sees a wall of text and doesn't need
to stream; it just needs to return a sentence's worth of audio promptly.

Audio can come back in **any common WAV format**: 8/16/32-bit integer,
float32, float64, mono or stereo, at any sample rate. The client reads
the header and scales accordingly. That matters because most PyTorch
speech models emit float32, which Python's `wave` module refuses to
open at all.

Point `tts.url` at the new port and nothing else changes.

---

# Run the Assistant

```bash
luna            # or ./start.sh, or luna.cmd on Windows
```

These find the virtualenv themselves, work from any directory, and pass
any arguments through. If the installer set up her voice server, the
launcher (`launch.py`) starts it first and stops it when she exits.
It checks the model server and the voice on the way past and *says* if
either is down rather than refusing to start. She runs as a text chat
without speech, and a launcher that won't launch is worse than one that
tells you why it'll be quiet.

Or without it:

```bash
source ~/ai-voice-venv/bin/activate
python main.py
```
