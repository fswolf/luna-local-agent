# Vision

Optional. Lets her look at your screen.

```
> "What does this error say?"
> "Read my editor for me."
> "Look at the wiki page."
> "What's on my screen?"
```

Needs `grim`, and a model that can see: a vision model in LM Studio,
or on llama-server the model's `mmproj` file (see *Or llama.cpp
directly*). When the server says the loaded model can't take images,
`look_at_screen` isn't offered at all, and the tools pane says what's
missing.

```json
"vision": {
    "enabled": true,
    "scale": 0.5,
    "max_kb": 4096
}
```

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `false` | Off unless you ask for it |
| `scale` | `0.5` | grim's scale factor. Half a 4K screen still reads fine and is a quarter of the bytes |
| `max_kb` | `4096` | Refuses rather than sending something that takes ten seconds to move |

## How it works

A tool result is a **string** — there's nowhere in the tool-calling
format to hand back an image. So `look_at_screen` captures one, stashes
it, and returns a sentence saying it did; the image is then attached to
the next message as an `image_url` block. From the model's point of view
it asked to look at something and the next thing it saw was a picture.

The image lives for exactly one turn. It isn't written to history, so
she can't look back at an earlier screenshot — ask "what about now?" and
she takes a new one.

## Which window

This is the fiddly part, and the answer depends on how you asked.

**Typed at her**, the focused window is her own terminal, and the one
behind it is whatever you last touched — on a tiling compositor that's
close to arbitrary. So typed turns capture the whole screen, which on
Hyprland is honest anyway: everything is visible at once.

**By voice through a compositor bind**, you deliberately focused
something before you spoke, so the focused window is exactly right.

Either way she never photographs herself: her own terminal is found by
walking `/proc` up from her process, and skipped.

You can also just name it. The model passes your words through and the
matching happens in Python, including the generic words people actually
use:

```
"look at my browser"       -> firefox
"what's in my editor"      -> Code
"read the music player"    -> kitty running ncmpcpp
```

`/look` tests all of it without involving the model:

```
/look              list the windows she can choose from
/look full         the whole screen
/look select       drag a box, like a screenshot bind
/look firefox      one window by name
```

That separates "is grim working" from "can this model see", which are
the two ways this fails and they look identical from the outside.
