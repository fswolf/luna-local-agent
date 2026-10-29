# Models

**Luna isn't tied to one model.** The Qwen3.5 models the installer offers
are what I run and test her on, not a requirement. Any model should work
if it:

- does **tool calling** (function calling), and
- runs on **llama.cpp** (`llama-server`) or **LM Studio**.

Luna talks to the model server through the usual OpenAI-style chat API,
so you can swap the model behind it. Most GGUF models on Hugging Face
with a tool-calling chat template should do.

This page is honest about what's been tested and what hasn't. I'm one
person with one graphics card, so a lot here is "should work" rather
than "works". Tried her on something else? Please say how it went in
[issue #2](https://github.com/fswolf/luna-local-agent/issues/2) and it'll
go in the table below.

## What's been tested

| Model | Quants | Tool calling | Notes |
|---|---|---|---|
| Qwen3.5 9B (and finetunes of it) | Q4_K_M, Q6_K, Q8_0 | Yes | What she's used with most, every day |
| Qwen3.5 27B | Q4_K_M, Q6_K | Yes | Offered by the installer for 22 GB and up; little testing so far |
| Qwen3.5 4B | Q4_K_M, Q6_K | Yes | For small cards or CPU only; little testing so far, and smaller models tend to miss more tool calls |
| huihui-ai abliterated Qwen3.5 (uncensored) | Same as above | Yes | The installer's default; refusals removed, nothing retrained |

**Untested:** Mistral, Llama 3.x, Gemma, Phi and the rest. Nothing in
Luna's main chat code is Qwen-only, so any of them with good tool
calling should work, but I can't promise it until someone tries.

## How much graphics memory

This is what the installer picks for you (Qwen3.5). It leaves room for
her context and, where it says "sees", her vision files:

| Graphics memory | Model the installer picks | Download |
|---|---|---|
| 32 GB and up | Qwen3.5 27B, Q6_K, sees | ~24 GB |
| 22-31 GB | Qwen3.5 27B, Q4_K_M, sees | ~18 GB |
| 14-21 GB | Qwen3.5 9B, Q8_0, sees | ~10 GB |
| 11-13 GB | Qwen3.5 9B, Q6_K, sees | ~8 GB |
| 8-10 GB | Qwen3.5 9B, Q4_K_M | ~6 GB |
| 6-7 GB | Qwen3.5 4B, Q6_K, sees | ~4 GB |
| less, or none | Qwen3.5 4B, Q4_K_M (runs on the CPU) | ~3 GB |

Apple Silicon counts about two thirds of its shared memory. For another
model, a rough rule: the GGUF file's size, plus 2 to 4 GB for 16k of
context, plus the vision file if it has one.
The embedding model and reranker want about 1.5 GB more beside it;
[What she runs on](parts.md) says how to move them to the CPU.

## Quantization

- **Q4_K_M** works and is the smallest that's usable.
- **Q6_K and Q8_0** call tools more steadily, at least on the 9B. If she
  says "done!" without actually doing it, or picks the wrong tool, try a
  bigger quant before giving up on the model.
- Below Q4, tool calling falls apart quickly. Not recommended.

## Context

- The installer sets **16k** on most models and **8k** on the smallest
  ones (`CTX` in `llama/server.env` for llama.cpp, or the context length
  slider in LM Studio).
- **16k is the practical minimum** for everyday use. Her system prompt,
  memory and tool list take a good share of it before you say anything.
- Tools that bring back a lot of text (web pages, forums, MCP servers)
  fill it fast. In the [tools pane](tools.md) you can switch off tools and
  whole MCP servers you aren't using, and each MCP server can have a cap
  on how much it may return (`max_result`, see [Tool calling](tools.md)).
- More context costs memory. If you have room to spare, 24k or 32k helps.

## Using a different model

**LM Studio:** download the model, load it, start the Local Server. Luna
uses whatever is loaded. With several loaded, set `llm.model` in
`config.json` to the one you want.

**llama.cpp:** put the GGUF's full path in `MODEL=` in
`llama/server.local.env` (your own overrides, read after
`llama/server.env`). If the model can see, put its mmproj file in
`MMPROJ=`, or leave it empty and it's looked for next to the model.

**Then check tool calling:** type `/tooltest`. It sends a set of plain
requests ("remind me in 5 minutes...", "what time is it?") two ways each
and reports which tools the model actually called. It takes about twenty
seconds and doesn't touch your conversation. It's the quickest way to
see whether a new model is any good for her.

## Model quirks

- **Chat template:** the model's GGUF needs a chat template that knows
  about tools. Both llama.cpp (Luna starts it with `--jinja`) and LM Studio
  read the template from the GGUF, so most models need nothing extra.
  A model whose GGUF ships without a working tool template will mostly
  just chat and never call a tool; `/tooltest` shows that straight away.
- **Stop tokens:** none needed for Qwen3.5. Untested on others.
- **Thinking models:** fine. Her reasoning is kept out of what she says
  out loud, whether the server sends it separately or inside
  `<think>` tags.
- **Tool calls written as text:** some models (Qwen among them) sometimes
  write a tool call into their reply (`<tool_call>` or `<function=...>`)
  instead of making a real call. Luna spots that, runs it anyway, and
  never says the markup out loud.
- **The research extras** (concept injection in [Her reasoning](reasoning.md))
  are experiments built around Qwen3.5 and llama.cpp. They're optional;
  nothing else depends on them.

## Uncensored or standard

The installer downloads the **uncensored** Qwen3.5 by default:
huihui-ai's abliterated versions (refusals taken out, nothing else
retrained), quantised by mradermacher, vision included. Standard is
Qwen's own release, which turns down some requests. `--standard` picks
it without asking. You can always switch later by loading the other one.

## Help fill this in

The more people report, the better this page gets. If you try a model,
note in [issue #2](https://github.com/fswolf/luna-local-agent/issues/2):

- the model and quant (e.g. "Mistral Small 3.2 24B, Q4_K_M"),
- llama.cpp or LM Studio, and your graphics memory,
- what `/tooltest` said,
- anything odd (template, stop tokens, context).
