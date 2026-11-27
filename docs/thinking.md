# How sure she is, and thinking twice

Every reply comes with a measure of how sure she was of it, and a shaky
reply can get a quiet second try before she says it. This page is the
practical side: what the percentage means, what moves it, and how to set
second looks for your model. [Her reasoning](reasoning.md) has the full
mechanics and every setting.

## How sure she is

On llama-server, every token she writes comes with the probability the
model gave it. Put together, that's the percentage beside each reply in the
thought viewer (127.0.0.1:8792/thoughts/). It's measured, not her own
account.

- **Every model has its own normal.** A 9B sits around 40-60% on everyday
  replies: a tease can be worded many ways, and it spreads its bets. Bigger
  models sit higher. A number only means something next to that model's
  usual numbers.
- **Sure isn't the same as good.** Replies that were thrown away with ↻
  scored about the same as the tries that replaced them (41% and 42%, 45%
  and 43% on a Qwen3.5 9B). The number says she was choosing between many
  words, not whether the reply landed.
- **It matters most on facts.** A run of coin-flip tokens on a number, a
  name or a date is a guess. That's what the review, the hedge line and the
  vote look for.
- **The red "low confidence" tag** is a run of three or more tokens in a row
  each under 30% (`LOW` and `SHAKY_RUN` in `mind/thoughtlog.py`). On a small
  model most replies have one, often a word choice in banter. The
  percentage beside it is the overall measure.

## What moves it

| Setting | What it does | On her certainty |
|---|---|---|
| Model size, quant | A bigger or less squeezed model knows its words better | Higher |
| `temperature` | How much she gambles on less likely words | Higher temperature, lower certainty |
| `top_p`, `top_k` | How many candidate words she picks from | Fewer, steadier |
| `presence_penalty` | Pushes her off words already used, against repeating | Strong values push her to unlikely words: lower certainty, odder replies |
| The subject | Banter has many right answers, a port number one | Banter scores lower, and that's fine |

The same Qwen3.5 9B went from a median of 66% to 42% over a week with no
change of model, after its sampling moved to `temperature 1.0` and
`presence_penalty 1.5`. Her replies felt more hit and miss the same week.
Sampling is per model (`generation.sampling`, the table on the settings
page). Change one value at a time, use her for a day, and compare the
percentages.

## Thinking twice

Every turn thinks on a modest budget (`adaptive.first_budget`). A reply is
shaky when it is:

- **less sure than `adaptive.rethink_below`**, whatever it's about, or
- **above that, but with a coin-flip run on a number or a name.**

A shaky reply gets a second look, silently, before anything is said.
`adaptive.mode` picks how:

| Mode | What it does | Good for |
|---|---|---|
| `vote` (default) | Asks `votes` (2) more times at the normal budget. The majority wins, but only when the facts in the answers differ. Only asked when a number or a name is shaky | Catching a wrong fact |
| `rethink` | Asks once more with `deep_budget`. The new reply takes over if it's different and surer | Making an everyday reply better |
| `auto` | The vote when a number or a name is shaky, rethink for everything else | Both |

A rethink replaces her reply only if the new one is different, at least
`min_gain` surer than the first, at least `rethink_below` sure, and not
guessing at a number or a name of its own. Otherwise the first stands. The
thought log keeps both, marked **second look**.

Her voice waits until the reply is settled (`adaptive.hold_speech`), so you
only hear the one she keeps. On a shaky reply that's a few seconds of quiet,
longer with `deep_budget: -1` (unlimited), so give it a limit.

## Setting it for your model

1. Use her for a day and look at the percentages in the thought viewer.
2. Set `rethink_below` a little under where most replies sit: 0.40 for a
   9B at around 45%. At the default 0.75 a small model thinks twice on every
   reply, and almost no second try is sure enough to replace the first.
3. Use `auto`, and a thinking limit for the second try.

```json
"adaptive": {
    "enabled": true,
    "mode": "auto",
    "rethink_below": 0.40,
    "deep_budget": 2048
}
```

Second looks need token probabilities: llama-server, the way Luna runs it.
LM Studio doesn't report them, so there are no percentages and no second
looks there.

## Trying again yourself

↻ under her latest reply on the chat page, or `/retry`, throws that reply
away and has her answer your message again ([Controls](controls.md)). A
second try at a reply that missed usually lands better, and whether it fit
the moment is the one thing you can judge that the model can't.

Thumbs down on the bad one, ↻, thumbs up on the new one, and the two are
kept together as one example for a habit patch: the bad reply, then the
good one in its place ([Patches](patches.md)). Click a lit thumb again, or
`/unrate`, to take it back.

## A day per model

None of this carries over from one model family to the next. A new family
means a day of setting it up again, in this order:

1. **Context:** how much fits, and so which tools ([Fitting her to your model](tuning.md)).
2. **Sampling:** from the model card, one change at a time.
3. **`rethink_below`:** from a day of her own percentages on those settings.

Sampling goes before the bar because it moves her certainty: set the bar
first, and the next sampling change throws it off.
