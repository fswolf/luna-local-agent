# Patches: teaching her habits

> **Experimental.** Collecting examples works and is safe to use every day. Training a
> patch is new: the first full run, start to finish, was done in November 2026 on an
> RX 7900 XT in a Debian VM, and her model server loaded the patch. What it ran into is
> in [The first run](#the-first-run); keep the [limits](#limits-and-known-gaps) in mind.

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
4. Restart `server/llama/start.sh`. The new patch loads by itself, for the model it was made for.
5. Try it with `/patches`, at half strength first if you like.

## Collecting examples

Talk to her as usual. When a reply is right, or you know how it should have gone:

```
/good                 keep her last reply as an example, as it is
/fix <better reply>   keep your version of her last reply instead
/unrate               take back the rating on her last reply
/examples             how many there are, and the page to look through them
```

In the web chat, her replies have a thumbs up and a thumbs down beside the copy
button (small grey icons that show when you hover over a reply, and stay faintly there
on a phone), so you can keep any of her recent replies, not only the last one:

- Thumbs up keeps the reply as it is, like `/good`.
- Thumbs down asks how it should have gone. Type your version and it's kept like `/fix`; leave it
  empty ("Just mark it bad") and the reply is kept as a bad example. A bad example is never
  trained on as it is (it's dropped), but it's kept: a later kind of training learns from
  good and bad replies side by side.
- Or type a note instead of the reply and press **She rewrites it**: "a playful no, she's
  not in the mood", "shorter, and tease me back". Her own model writes the reply from the
  same moment (the same prompt, her reply and your note), on your machine only, never a
  bigger model, and it's kept like your own version with the note beside it. A line in the
  conversation shows what she wrote; fix it on the examples page if it's off. This is how
  to teach her things she never does on her own, like saying no, where there's no reply of
  hers to keep.
- A reply with gesture tags in it goes to the **gesture** examples, the rest to **habit**.
  You can still switch it on the examples page.
- Changed your mind? Click the other thumb: it's still one example. Click the lit
  thumb again and the rating is taken back, the example with it (`/unrate` in the console
  does the same for her last reply).
- **Thumbs down, ↻, thumbs up:** mark a reply bad, have her try again, and
  give the new one a thumbs up, and the two are kept as one example: the bad
  reply as the original and the new one as the reply, the same as typing the
  better version yourself. No thumb on the new one and nothing extra is kept.
  Take back the thumbs up and the first reply is a plain thumbs down again; take
  back the thumbs down and both go.

She never sees these: commands don't go into her history, her transcript or her notes,
so collecting examples doesn't change the conversation you're having.

Only your own turns can be kept. Not a guest's or a stranger's, not stream chat or
Discord, not a game or a job.

**Turns where she used tools** are kept whole: each call she made, what came back, and her
answer after it, with the tools she was offered, so training sees what she saw. Your
version replaces the answer after the tools; the calls stay as she made them. What came
back is never learned (it's the tool's words, not hers). Her calls are learned only where
the model's chat template writes them the way she would: Qwen's drops the thinking from
calls before her answer, so on Qwen the calls are context and her answer is what's learned.
A tool turn that was put right afterwards (a second look or a follow-through added to it)
or stopped partway can't be kept: it shows Copy only.

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
card, so stop Luna, `server/llama/start.sh` and LM Studio first. The script won't start while
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
4. Turns the result into a GGUF patch in `server/llama/patches/`, with a `.json` beside it
   saying which model it was made for, how many examples, and when.

A patch is named for what it is: `gesture-<model>-<date>-n<examples>.gguf`. A second
run on the same day adds the time, so the first one is kept.

### Leaving it running

- **No timer to set.** It's a fixed amount of work, `EPOCHS` passes over your
  examples, then it stops and writes the patch. How long depends on how many examples
  there are and how long they are.
- **Watch the first few minutes.** It prints how many examples it's using (and how many
  were too long), a progress bar with the time left, and the loss every few steps. The
  loss should drift down.
- **The first run takes longest.** It builds the trainer image (PyTorch for ROCm,
  several GB) and downloads the full-size model (`BASE`, about 18 GB for a 9B) into
  `~/.cache/huggingface`. Both happen once.
- **Start it in `screen`** (or `tmux`). If your SSH connection drops, the run goes with
  it. `screen -S train` starts one, Ctrl+A then D leaves it running, and `screen -r train`
  comes back to it (in `tmux`: Ctrl+B then D, and `tmux attach`).
- **Let it finish.** Nothing is saved partway, so a stopped run starts over. Keep the
  machine from sleeping or rebooting.

### Settings

In `training/train.env`. Any of them can also be given on the command line, like
`BASE=/models/qwen-9b training/train.sh gesture`.

| Setting | Default | What it does |
|---|---|---|
| `BASE` | (none, required) | The full-size (safetensors) version of the exact model she runs, not the GGUF. A Hugging Face id or a folder |
| `FOR_MODEL` | the model `server/llama/start.sh` last started | The GGUF the patch is for, by file name |
| `RANK` | 16 | How much the patch can change. Small, so she picks up the habit without forgetting other things |
| `EPOCHS` | 2 | Passes over the examples |
| `LR` | 1e-4 | Learning rate: low and gentle |
| `MAX_LEN` | 8192 | Tokens. Longer examples are left out; the run says how many. Lower it if memory runs out |
| `LOAD_4BIT` | 1 | Loads the model in 4 bits so a 9B fits a 16 GB card |
| `ENGINE` | podman, else docker | What runs the trainer |
| `ROCM` | rocm6.4 | The PyTorch build in the container: rocm6.4 for ROCm 6 drivers, rocm7.2 for 7 |

### Setting BASE

`BASE` is the one setting every run needs. Open `training/train.env` and put the
full-size version of her model between the quotes:

```
BASE="${BASE:-DavidAU/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP}"
```

It has to be the **same model she runs, at full size**: the 16-bit safetensors, not the
GGUF. Her GGUF is a packed copy for running; the trainer learns on the original, and the
patch it makes is turned into a GGUF that sits on top of her packed one. A different
finetune, or the stock model it was made from, gives a patch that doesn't fit.

To find it:

1. Her model's file name is in `server/llama/server.env` (`MODEL`), and
   `training/train.sh habit --check` prints it on its first line.
2. On Hugging Face, open the GGUF's page. The full-size version is usually the same
   name without `-GGUF`, by the same author, and its page has a *Browse quantizations*
   link back to the GGUF repo. Check it says *Safetensors*.
3. Put that id in `BASE`. The first run downloads it (about 18 GB for a 9B) into
   `~/.cache/huggingface`; or download it yourself and give the folder instead.

What I run, and set:

| | |
|---|---|
| Her model (`MODEL`) | `Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-MTP-Q8_0.gguf`, from `DavidAU/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP-GGUF` |
| `BASE` | `DavidAU/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP` |
| `FOR_MODEL` | left empty: `start.sh` notes the model it starts, and the patch is named for it |

`--check` shows both before anything runs: `patch: habit, for <her GGUF>` and
`trained on: <BASE>`. If those two aren't the same model, stop there.

### What she learns from

Only the last reply in each example: the one you approved or wrote. Her prompt, your
lines and her earlier replies in that conversation are there as context, never learned
from, since you never reviewed them. Whatever her model's chat template writes before a
reply (Qwen's empty thinking block) is context too, so a patch doesn't teach her to skip
thinking.

## Training on her model server

Training needs the graphics card her model runs on. When that's another machine (a
server, or a VM with the card passed through), train there. That machine needs a little
of Luna's folder, not all of it, and nothing installed in Python: the export runs on
plain `python3`.

1. **A Luna folder on the server**, say `~/luna`, with:
   - `training/` and `config/`, copied from your Luna folder;
   - `agent/dataset/examples.jsonl`, your examples. They're collected where she runs
     and never go in git, so copy them over again before every run;
   - her llama folder at `server/llama`. If the server already runs her model from a
     copy of `server/llama` somewhere else (say `~/luna/llama`), link it rather than
     copying: `mkdir -p ~/luna/server && ln -s ~/luna/llama ~/luna/server/llama`. The
     script reads which model is running (`patches/.current_model`, written by
     `start.sh`) and writes the patch where `start.sh` loads it from, so both have to be
     the folder the server really uses.

   Any way of copying works: `scp`, `rsync`, or FileZilla over SFTP.
2. **`BASE` in `training/train.env`**: the full-size version of the exact model the
   server runs ([Setting BASE](#setting-base) above).
3. **Docker or podman.** With Docker, your user has to be in the `docker` group:
   `sudo usermod -aG docker <you>`, then log in again (`docker ps` should list nothing,
   not "permission denied").
4. **Memory.** Loading the full-size 9B to pack it into 4 bits goes through the
   computer's memory first, about 15 GB at the peak. A VM with 16 GB or less needs swap
   or the run is killed while loading (`dmesg` says "Out of memory"):

   ```
   sudo fallocate -l 16G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
5. **`screen`** (or `tmux`) for leaving it running: `sudo apt install screen` on Debian.
6. **Stop her model server**, then check and run:

   ```
   cd ~/luna && training/train.sh habit --check
   screen -S train
   cd ~/luna && training/train.sh habit
   ```
7. **Start her model server again.** It loads the new patch by itself.

**Memory and disk.** A 9B loaded in 4 bits (`LOAD_4BIT=1`) takes 5 to 6 GB of the card,
and training a patch adds the room for the examples on top, so a 16 to 20 GB card has
space once her server is stopped. Her server and the training together don't fit. The
disk needs about 18 GB for the full-size 9B and a few GB for the trainer image.

From Luna on your desktop, `/patches` shows the patches the server has loaded ("loaded
on her model server") and `/patches <name> 0.5` changes their strength, the same as on
one machine.

### The first run

Fourteen examples, two passes, `LOAD_4BIT=1`, on an RX 7900 XT (20 GB) in a Debian VM
with Docker. What it ran into, all handled in the scripts now:

| What happened | Why, and the fix |
|---------------|------------------|
| `permission denied` on the Docker socket | not in the `docker` group: `sudo usermod -aG docker <you>`, log in again |
| `unable to find group render` | the group exists on the host, not in the container: `train.sh` passes the `video` and `render` groups by number |
| `getpwuid(): uid not found: 1000` | your user doesn't exist in the container: `train.sh` sets `USER` and `LOGNAME` |
| killed while loading the model | out of memory (`dmesg`): 16 GB of swap, above |
| `unexpected keyword argument 'warmup_ratio'` | Transformers 5 dropped it: `train.py` passes `warmup_steps` and only the settings the installed version takes |
| `AssertionError: expected size ... stride ...` in `_scaled_dot_product_flash_attention_backward` on the first step | PyTorch's compiler got the attention step's memory layout wrong on ROCm. Off for training by default now; `COMPILE=1` in `train.env` tries it again |
| `FileNotFoundError` writing the `.gguf` | `server/llama` was a link to `~/luna/llama`, outside the folder the container sees. `train.sh` mounts the link's real folder now |
| 7 of 14 examples left out | longer than `MAX_LEN` (8192 tokens) |
| `causal_conv1d is not installed` | a warning only: part of Qwen3.5 uses PyTorch's slower, correct fallback |

If the conversion fails after training, run the same command again the same day: a
run folder that already holds a trained patch is converted without training again.

Container versions that worked: Unsloth 2026.11.12, Transformers 5.17, PyTorch
2.9.1 with ROCm 6.4, which knows the 7900 XT (gfx1100) without `HSA_OVERRIDE_GFX_VERSION`.

Fourteen examples is far too few to change how she writes; that run proved the route,
from a thumbs-up to a patch her server loads.

## Using a patch

Restart `server/llama/start.sh`. It loads every patch made for the model it's starting and
leaves the others out, saying which and why. `PATCHES` in `server/llama/server.env`: `auto`
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
model. It goes by the GGUF's file name, so another quant of the same model (Q8_0 instead
of Q4_K_S) counts as another model too. The patch does fit it, since both come from the
same full-size model: set `"for"` in the patch's `.json` to that file's name (without
`.gguf`) to load it there. Train new ones for the new model from the same examples, with `BASE` set to its
safetensors version.

The examples are what matters. They're plain conversations, not tied to a model, so
they carry over to every model you use.

## Where things are kept

| What | Where | In git? |
|---|---|---|
| Examples | `agent/dataset/examples.jsonl` | Never: they hold her whole prompt, your facts included |
| Exports for training | `agent/dataset/export/` | Never |
| Training runs | `agent/dataset/runs/<name>/` | Never |
| Patches | `server/llama/patches/` | Never: built from your examples, for your model |
| Settings | `training/train.env`, `PATCHES` in `server/llama/server.env` | Yes |

## Limits and known gaps

- **One real run so far**, on an RX 7900 XT ([The first run](#the-first-run)). It's
  Linux only, on an AMD card through ROCm for now.
- **Luna's own model server only.** Patches are loaded by `server/llama/start.sh` (llama.cpp's
  server). LM Studio and other servers don't load them; `/patches` can only change the
  strength on llama.cpp's server.
- **AMD cards.** ROCm support for the RX 6000 series is listed as limited, and 4-bit
  loading on AMD is newer than on NVIDIA. If the model won't load in 4 bits, that's
  where to look first.
- **Tools.** Plain examples train without the tool list she's given; tool turns carry it.
  A tool turn is long (the tool list and every result count), so `MAX_LEN` in
  `training/train.env` may leave some out: the trainer says how many. Keep patches gentle
  and check tools still work after loading one (`/tooltest`).
- **Gesture tagging.** Gesture examples have to be tagged by hand for now: `/fix` with
  the tags where they belong (or edit them in on the examples page), then switch the
  example to **gesture** there; `/good` and `/fix` keep examples as habits. Tagging her real
  replies automatically, and scripted practice conversations, are planned.
- **No before-and-after check yet.** Compare her with the patch at 0 and at 1 yourself
  until the automatic test run exists.
