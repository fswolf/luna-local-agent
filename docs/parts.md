# What she runs on

Luna isn't one model. Up to six pieces run on your machine, and only the
first one is required. This page says what each does, what it costs,
and what happens if you leave it out. Details and downloads are in
[Install](install.md); which chat models work is in [Models](models.md).

| Part | What it does | Where it runs | Memory | Without it |
|---|---|---|---|---|
| **Chat model** | Her mind: everything she says and decides | GPU (llama.cpp or LM Studio) | the GGUF's size, plus 2-4 GB for 16k of context | nothing works: this one is required |
| **Vision adapter** (mmproj) | Her eyes: screenshots, the webcam, pictures sent to her | GPU, inside the chat server | about 0.6-1 GB of VRAM | text only: no `look_at_screen`, no webcam looks, no pictures. Everything else is the same |
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

The two small models are 0.6B each, so on the CPU they're still quick:
recall takes a moment longer and the chat model gets their VRAM. That's
usually the better trade on a card that's nearly full.

Whisper's size is `stt.model` in the [settings](configuration.md)
(`small` by default; bigger hears better and is slower). Kokoro is its
own program: see *Running the Kokoro Server* in [Install](install.md).

**On another machine.** Any of the servers can live elsewhere, a home
server with the graphics card, say. Point Luna at them in `config.json`:
`llm.llama_url` (chat), `llm.embed_url`, `llm.rerank_url` and `tts.url`.
*The model on another machine* in [Install](install.md) covers the
address, the key and the firewall.

## Making it fit

Rough budgets for the graphics card, with everything on it:

| | Chat model | Vision | Embedding + reranker | Working room | Left for context |
|---|---|---|---|---|---|
| 16 GB, 9B Q8_0 | ~10 GB | ~0.9 GB | ~1.6 GB | ~1 GB | ~2.5 GB |
| 20 GB, 27B IQ4_XS | ~15.7 GB | (off) | on the CPU | ~1 GB | ~3.3 GB |

If it doesn't fit, in order of what it costs you:

1. The embedding model and reranker on the CPU (`EMBED_NGL=0`, `RERANK_NGL=0`).
2. Vision off (`MMPROJ=off`), if you rarely show her things.
3. A smaller working batch (`UBATCH=512`): slower to read a long prompt, replies just as fast.
4. A smaller quant of the chat model, or less context (`CTX`).

A card that only runs models (a server with no screen on it) has its
whole memory free; one that also draws your desktop loses 1-2 GB to it.

The [size presets](configuration.md#the-settings-page) are the other
half: they set how much of that context she fills each turn.
