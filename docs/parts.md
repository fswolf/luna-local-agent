# What she runs on

Luna isn't one model. Up to six pieces run on your machine, and only the
first one is required. This page says what each does, what it costs,
and what happens if you leave it out. Details and downloads are in
[Install](install.md); which chat models work is in [Models](models.md).

| Part | What it does | Where it runs | Memory | Without it |
|---|---|---|---|---|
| **Chat model** | Her mind: everything she says and decides | GPU (llama.cpp or LM Studio) | the GGUF's size, plus 2-4 GB for 16k of context | nothing works: this one is required |
| **Vision adapter** (mmproj) | Her eyes: screenshots, the webcam, the pictures in her games (Vibe City) | GPU, inside the chat server | about 0.6-1 GB of VRAM | text only: no `look_at_screen`, no webcam looks, no game pictures. Everything else is the same |
| **Embedding model** (Qwen3-Embedding-0.6B) | Matching by meaning: recalling facts, searching your notes, picking which tools go along each turn, meaning-mode gestures | GPU by default, or CPU | about 0.7 GB | she matches by shared words instead; tool routing sends every tool that's on |
| **Reranker** (Qwen3-Reranker-0.6B) | A closer second read of the best matches, so recall picks what answers you, not just what's on topic | GPU by default, or CPU | under 1 GB | recall uses the embedding's order as it is |
| **Whisper** (speech to text) | Her hearing | CPU, inside Luna | system RAM, none on the GPU | you type instead of talk |
| **Kokoro** (text to speech) | Her voice, a separate server (kokoro-reader) | GPU with PyTorch for NVIDIA or AMD, otherwise CPU | small, under about 1 GB | she answers on screen only |

## Turning parts off, or moving them

All in `llama/server.env` (or your own `llama/server.local.env`), read
when `llama/start.sh` starts:

| To | Set |
|---|---|
| leave out her vision | `MMPROJ=off` |
| leave out the embedding model | `EMBED=off` |
| leave out the reranker | `RERANK=off` |
| run the embedding model on the CPU | `EMBED_NGL=0` |
| run the reranker on the CPU | `RERANK_NGL=0` |

On a Mac, `start.sh` reads `llama/server.mac.env` instead, which already
leaves the embedding model and the reranker off to save shared memory.

**Not using `start.sh`?** With LM Studio or a model server of your own
(a Docker container on a home server, say), the same choices are made
there: load the model's vision file or not, run the embedding model and
reranker on a llama-server of their own (GPU or CPU), and point Luna at
them (below).

The two small models are 0.6B each, so on the CPU they're still quick:
recall takes a moment longer and the chat model gets their VRAM. That's
usually the better trade on a card that's nearly full.

Whisper's size is `stt.model` in the [settings](configuration.md)
(`small` by default; bigger hears better and is slower). Kokoro is its
own program: see *Running the Kokoro Server* in [Install](install.md).

**On another machine.** Any of the servers can live elsewhere, a home
server with the graphics card, say. Point Luna at them in `config.json`:
`llm.llama_url` or `llm.lmstudio_url` (chat), `llm.embed_url`,
`llm.rerank_url` and `tts.url`.
*The model on another machine* in [Install](install.md) covers the
address, the key and the firewall.

## Making it fit

Two rough budgets for the graphics card. "Working room" is the chat
server's scratch space, which grows with the batch size (`UBATCH`):

| | Chat model | Vision | Embedding + reranker | Working room | Left for context |
|---|---|---|---|---|---|
| 16 GB, 9B Q8_0, as shipped | ~10 GB | ~0.9 GB | ~1.6 GB | ~1-2 GB | ~1.5-2.5 GB |
| 20 GB, a 27B at IQ4_XS | ~15.7 GB | off | on the CPU | ~1 GB (`UBATCH=512`) | ~3.3 GB |

If it doesn't fit, in order of what it costs you:

1. The embedding model and reranker on the CPU (`EMBED_NGL=0`, `RERANK_NGL=0`).
2. Vision off (`MMPROJ=off`), if you rarely show her things.
3. A smaller working batch (`UBATCH=512`): slower to read a long prompt, replies just as fast.
4. An 8-bit context cache, about half the memory per token of context:
   `EXTRA="-ctk q8_0 -ctv q8_0"` in `server.env` (older llama.cpp builds
   also want `-fa on`).
5. A smaller quant of the chat model, or less context (`CTX`).

A card that only runs models (a server with no screen on it) has its
whole memory free; one that also draws your desktop loses 1-2 GB to it.

The [size presets](configuration.md#the-settings-page) are the other
half: they set how much of that context she fills each turn.

## How she scales

Luna is the same program on a laptop and on a server. A bigger model and
more memory don't make a different Luna; they let her carry more each
turn: more tools at once, more of the conversation word for word, more of
what she knows about you, and longer reads of a page or a command's
output. The three size presets (`/preset small`, `medium`, `large`, or
the settings page) are those steps:

| Model | What she gets | Runs on |
|---|---|---|
| 4 to 9B, 16k context (Small, as shipped) | **Held back on purpose.** Tool routing picks 3 tool groups a turn; the last 15 messages word for word; 25 facts, 4 lessons, 2 notes; short reads of pages (6,000 characters) and output; a 1,024-token first thinking budget | One 8 to 16 GB card, in your desktop |
| 14 to 32B, 32k context (Medium) | **Mostly unlocked.** 5 tool groups a turn; 30 messages; 40 facts, 6 lessons, 3 notes; longer research; a 2,048-token thinking budget | A 24 to 32 GB card, in your desktop or a home server |
| 70B class, 64k context or more (Large) | **Everything at once.** Routing off, so every tool that's on goes every turn; 50 messages; 60 facts, 8 lessons, 5 notes; the deepest reading (16,000 characters a page, 30,000 for research); a 4,096-token thinking budget | A server with around 64 GB of graphics memory |

The exact values are in `config/presets.py`, and the settings page shows
each one before and after before anything changes.

The small end is held back so it works: give a 9B every tool and a long
history in 16k and there's little room left for what you asked. Day to day
she runs on a 9B; the 27B has had a little testing, and nothing at 70B
yet ([Models](models.md) keeps that list). The sizes are guides, not
rules: what counts is the context window, so a 9B with 32k on a card with
room to spare can take Medium.

### From your desktop to a server

Nothing needs reinstalling. Luna talks to her models over an
OpenAI-style API, so moving them is a matter of addresses
([On another machine](#turning-parts-off-or-moving-them) above):

- **The chat model on a server**, on a card that only runs models, so its
  whole memory is hers and your desktop's card is free again.
- **Luna herself stays on your desktop:** your voice, her portrait, your
  files and your screen are there, where she needs them.
- **The small pieces go wherever there's room:** the embedding model and
  reranker on the server or a CPU, Kokoro on the desktop or the server.
- **Other rooms reach the same Luna** through [relay stations](stations.md).

Start on the desktop you have, move the model to a server when you get
one, and step up a size when the server has the memory. Her memory,
moods, notes and settings come along at every step, because none of them
live in the model. Patches are the exception: one fits only the model it
was trained for ([Patches](patches.md)).

### Helping a small model

- **[Asking a bigger model](ask.md):** when you tell her to, or on her own
  when she's stuck on a script or a server problem if you switch that on,
  she can put a question to Claude, Grok or ChatGPT. Only the question
  leaves your machine.
- **[Patches](patches.md)** (experimental): teach her own model the habits
  you want, from replies you picked, without giving it more to read every
  turn.
