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
6. **Extras, pick any:** wake word, MCP, portrait tools, Live2D runtime,
   embedding model, the pomf chat plugin.
7. **Launchers.** A `luna` command and an app-launcher entry on Linux,
   `Luna.command` on macOS, `luna.cmd` and a Start menu shortcut on
   Windows.
8. **A health check**, then a summary of what's ready and what isn't.

Then start her:

```bash
luna            # or ./start.sh, or luna.cmd on Windows
```

The launcher starts her voice server too if the installer set one up,
and stops it again when she exits. One you were already running is
left alone.

Run the installer again any time to repair or update. It picks up
where it left off and only does what's missing. `--yes` takes every
default, and `--check` only runs the health check. Other options:
`--backend lmstudio|llama|skip`,
`--voice install|url:http://host:port|skip`,
`--gpu auto|cpu|cuda|rocm`, `--extras wakeword,mcp,portrait,...`.
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
llama/install.sh          # build it - Vulkan; "rocm" for ROCm/HIP instead
llama/start.sh            # serve on 127.0.0.1:8080
./start.sh                # Luna finds it; the header says "· llama.cpp"
```

`install.sh` clones llama.cpp into `llama/llama.cpp/` and builds only
`llama-server` and `llama-bench`, for this card. If a build tool is
missing it prints the exact `dnf install` line and stops. It doesn't
run sudo itself. Vulkan and ROCm builds can sit side by side; `bin/`
points at whichever was built last. Run `llama/bin/llama-bench -m
<model>` under each to see which is faster on your GPU.
`install.sh update` pulls the latest llama.cpp and rebuilds.

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
