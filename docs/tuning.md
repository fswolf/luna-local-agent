# Fitting her to your model

[Models](models.md) says which models work and how much memory they
need. This page is what to set once one is running: how a model's size,
quant and context change what she can do, what small models get wrong,
and what Luna does about it. It's from testing on a Qwen3.5 9B (Q4_K_M
and Q8_0) and a 32B on llama-server, and it grows as I test more.
These are findings, not rules: if your model behaves differently, say how
in [issue #2](https://github.com/fswolf/luna-local-agent/issues/2).

## At a glance

| You have | Set | Why |
|----------|-----|-----|
| 9B at Q4 | `portrait.gestures keywords` | At Q4 she doesn't write gesture tags at all. Her *actions* still move her |
| 9B at Q8 | `portrait.gestures tags` | Tags work most of the time, and she picks her own moves |
| 16k context | the Small [size preset](configuration.md#the-settings-page), most tool groups off in the tools pane | A full tool list leaves too little room for the conversation |
| 32k context | Medium or Large, every tool on | Room for all of it |

## Gestures: tags, keywords and her actions

How her replies move her portrait is `portrait.gestures` (the settings
page explains each option):

- **tags:** she's offered a few names like `[wave]` and puts one in her
  reply. It needs a model that follows that kind of instruction: a 9B at
  Q8 mostly does, at Q4 it doesn't try.
- **keywords:** what she acts out in asterisks, `*waves at you*` or
  `*bends forward*`, plays the move. Every model writes actions, so this
  works on all of them. Your own plain words ("turn around", "face me",
  "take off your top") work in every mode, even with gestures off.
- **meaning:** the embedding model she already runs for memory picks a
  move from what was said. Nothing goes in her prompt.

Whichever you pick, her written actions are what fire most reliably. Small
models act things out at length, `*bounces a little higher in my chair,
the playful edge of my smile widening*`, and the whole action is read for
a move, not only its first few words. If she writes an action in square
brackets instead, `[blushing]`, it's shown and read as `*blushing*`.

## What small models get wrong, and what she does about it

**They're unsure of almost every chat reply.** A 9B sits under 75%
confidence on most banter, because there are many ways to word a tease.
That's word choice, not doubt about a fact, so [a second
look](reasoning.md) only happens when her doubt sits on a specific: a
number, a name, a time. She checks "the card has 16 GB" and leaves "*leans
in closer*" alone.

**They garble small formats.** After each exchange a short call rates
your message for her mood, as one line of six fields. A 9B often adds a
field or swaps one, so the line is read part by part rather than all or
nothing, and the flirt score that moves her mood isn't lost when one part
is wrong. When it's unclear whether you were kind or rude, it counts as
neither.

**They quote whatever is in their prompt.** The time, her memories of your
projects, what you said you were doing tonight: a small model brings them
up all the time. If you tell her you're "testing", she'll talk about
testing for the rest of the conversation; `/clear` before a roleplay.
The rest is her agent file (below).

## Roleplay is mostly the agent file

The same 9B that drifted out of every scene had roleplayed fine before.
What made the difference was her personality file, `agent/agent.json`,
not the model:

- **Strong words win.** "Flirts constantly" made her flirt through
  security reports. "Flirty and affectionate", next to a trait that says
  she gets straight when you need real help, keeps both.
- **Say what to do, not what to avoid.** A rule listing "testing, code,
  hardware, logs" puts those words in front of her every turn. "In a
  scene, talk only about what's happening between you two" does the same
  job without them.
- **Give numbers, not "on occasion".** "About one reply in four" and "at
  most one emoji in a reply" hold better than "not in every response".
- **Tell her she has a body.** "When you act something out in
  *asterisks*, it really happens" makes her act more out, and her actions
  are what move the portrait.

Rules that worked, to adapt:

```json
"When the user writes an action in *asterisks*, you're in a scene together: stay in it until they step out",
"In a scene, talk only about what's happening between you two, right there",
"Speak as yourself, in first person: say 'you' to the user, 'I' and 'me' about yourself",
"Your body is on screen: when you act something out in *asterisks*, it really happens",
"When you're in the mood, show it: describe what you do and feel, in a few vivid lines"
```

How she talks is yours to set: her agent file is read every turn, and
nothing in the code decides how often she says nya or how far a scene
goes. Different people, different models, different tastes.

## Still being tested

- How well a 9B at Q8 holds a scene with the rules above.
- 4B models: expect more breaking out of scenes and no tags; keywords and
  your own words are what hold up.
