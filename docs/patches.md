# Patches: teaching her habits

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

**Status:** collecting examples works now. Training, and the gesture tagging, come next.

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

## Where they're kept

`agent/dataset/examples.jsonl`, one example per line. It holds the prompt she was
answering, your facts included, so it's personal: it's in `.gitignore` and never
committed. Trained patches will go in `llama/patches/`, also never committed.

The examples are what matters. A patch fits one model; if you change models one day,
the same examples train a new patch for it overnight.
