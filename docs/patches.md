# Patches: teaching her habits

> **Experimental.** Collecting examples works and is safe to use every day. Training a
> patch is new: the scripts are written and tested piece by piece, but a full training
> run on a real graphics card hasn't been done yet. Expect some fiddling the first time,
> and keep the [limits](#limits-and-known-gaps) in mind.

A patch (a LoRA) is a small file that sits on top of her model and changes how it
writes, not what it knows. Her personality, moods and memory stay where they are. A
patch teaches a habit by example: show her a few hundred replies the way you want them,
and she picks up the pattern.

Two are planned:

- **Gestures:** gesture tags in the right places, so the portrait moves with what she
  says. A small model can't follow a gesture instruction in its prompt without its voice
  changing, but it can learn the habit from examples of her own replies.
- **Habits:** the things you'd correct: how she opens a reply, emoji pile-ups, reply
  length, a phrase she leans on too much.

Each is its own patch, so one can be tested and rolled back without touching the other.

## In short

1. Talk to her as usual, and keep the good replies (`/good`) or your better version
   (`/fix <reply>`).
2. Look through them on the examples page now and then: approve, drop, edit.
3. With a few hundred approved, stop Luna and the model server, check with
   `training/train.sh gesture --check`, then run `training/train.sh gesture` (or `habit`).
   Leave it running; overnight is a good time.
4. Restart `llama/start.sh`. The new patch loads by itself, for the model it was made for.
5. Try it with `/patches`, at half strength first if you like.

## Collecting examples

Talk to her as usual. When a reply is right, or you know how it should have gone:

```
/good                 keep her last reply as an example, as it is
/fix <better reply>   keep your version of her last reply instead
/examples             how many there are, and the page to look through them
```

She never sees these: commands don't go into her history, her transcript or her notes,
so collecting examples doesn't change the conversation you're having.

Only your own turns can be kept. Not a guest's or a stranger's, not stream chat or
Discord, not a game or a job, and not a turn where she called tools (those train
differently, later).

A first patch wants **300 to 500** examples. There's no rush: they keep.

## The examples page

`http://127.0.0.1:8792/examples/` (also in the Pages pane, and linked from `/examples`).
Newest first, each with what you said, her reply, and your version if you fixed it.

- **Approve** or **Drop**: a dropped example stays on the page but is never trained on.
- **Edit** the reply in place; her original is kept beside it.
- Each reply can be kept once: `/good` twice keeps it once, and `/fix` after `/good` turns
  that example into your version.
- Switch an example between **habit** and **gesture**.
- **Delete** it for good.
- Fold out the conversation before it and the prompt she was answering.

## Training a patch

By hand, when there are enough approved examples. Training needs the whole graphics
card, so stop Luna, `llama/start.sh` and LM Studio first. The script won't start while
her model servers or LM Studio still hold a model (`FORCE=1` to try anyway).

```
training/train.sh gesture --check    check first: lists anything missing
training/train.sh gesture            (or habit) the real run, overnight
```

What it does:

1. Exports your approved examples (`python3 -m training.export gesture` does just this
   step). About one in ten is held back for testing and never trained on, the same ones
   every time.
2. Builds the trainer container the first time (`training/Containerfile`: Unsloth with
   PyTorch for ROCm, in podman or docker), so nothing is installed on your system.
3. Trains, in the container, with your graphics card passed through. It prints how many
   examples it used, how many it left out and why, and the loss as it goes.
4. Turns the result into a GGUF patch in `llama/patches/`, with a `.json` beside it
   saying which model it was made for, how many examples, and when.

A patch is named for what it is: `gesture-<model>-<date>-n<examples>.gguf`. A second
run on the same day adds the time, so the first one is kept.

### Settings

In `training/train.env`. Any of them can also be given on the command line, like
`BASE=/models/qwen-9b training/train.sh gesture`.

| Setting | Default | What it does |
|---|---|---|
| `BASE` | (none, required) | The full-size (safetensors) version of the exact model she runs, not the GGUF. A Hugging Face id or a folder |
| `FOR_MODEL` | the model `llama/start.sh` last started | The GGUF the patch is for, by file name |
| `RANK` | 16 | How much the patch can change. Small, so she picks up the habit without forgetting other things |
| `EPOCHS` | 2 | Passes over the examples |
| `LR` | 1e-4 | Learning rate: low and gentle |
| `MAX_LEN` | 8192 | Tokens. Longer examples are left out; the run says how many. Lower it if memory runs out |
| `LOAD_4BIT` | 1 | Loads the model in 4 bits so a 9B fits a 16 GB card |
| `ENGINE` | podman, else docker | What runs the trainer |
| `ROCM` | rocm6.4 | The PyTorch build in the container: rocm6.4 for ROCm 6 drivers, rocm7.2 for 7 |

### What she learns from

Only the last reply in each example: the one you approved or wrote. Her prompt, your
lines and her earlier replies in that conversation are there as context, never learned
from, since you never reviewed them. Whatever her model's chat template writes before a
reply (Qwen's empty thinking block) is context too, so a patch doesn't teach her to skip
thinking.

## Using a patch

Restart `llama/start.sh`. It loads every patch made for the model it's starting and
leaves the others out, saying which and why. `PATCHES` in `llama/server.env`: `auto`
(the default), `off`, or the names to load.

```
/patches                  what's there, what's loaded, what's made for another model
/patches gesture 0.5      half strength (0 = off, 1 = full), until the next restart
```

To roll a patch back, set `/patches <name> 0`, or take it out of `PATCHES` (or delete the
file) and restart.

### Changing models

A patch only fits the model it was trained on. Change `MODEL` in `server.env` and the old
patches stay out by themselves; nothing breaks, and `/patches` says they're for another
model. Train new ones for the new model from the same examples, with `BASE` set to its
safetensors version.

The examples are what matters. They're plain conversations, not tied to a model, so
they carry over to every model you use.

## Where things are kept

| What | Where | In git? |
|---|---|---|
| Examples | `agent/dataset/examples.jsonl` | Never: they hold her whole prompt, your facts included |
| Exports for training | `agent/dataset/export/` | Never |
| Training runs | `agent/dataset/runs/<name>/` | Never |
| Patches | `llama/patches/` | Never: built from your examples, for your model |
| Settings | `training/train.env`, `PATCHES` in `llama/server.env` | Yes |

## Limits and known gaps

- **Not yet run on a real card.** The scripts, the export, the masking and the loading
  are tested, but no full training run has been done. It's Linux only, on an AMD card
  through ROCm for now.
- **Luna's own model server only.** Patches are loaded by `llama/start.sh` (llama.cpp's
  server). LM Studio and other servers don't load them; `/patches` can only change the
  strength on llama.cpp's server.
- **AMD cards.** ROCm support for the RX 6000 series is listed as limited, and 4-bit
  loading on AMD is newer than on NVIDIA. If the model won't load in 4 bits, that's
  where to look first.
- **Tools.** The examples don't carry the tool list she's given, and turns where she
  called tools aren't collected yet, so a patch never sees tools while it trains. Keep
  patches gentle and check tools still work after loading one (`/tooltest`).
- **Gesture tagging.** Gesture examples have to be tagged by hand for now: `/fix` with
  the tags where they belong (or edit them in on the examples page), then switch the
  example to **gesture** there; `/good` and `/fix` keep examples as habits. Tagging her real
  replies automatically, and scripted practice conversations, are planned.
- **No before-and-after check yet.** Compare her with the patch at 0 and at 1 yourself
  until the automatic test run exists.
