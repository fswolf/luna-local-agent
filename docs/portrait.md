# Portrait

<img width="1210" alt="Luna's portrait window next to the terminal" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/portrait.png" />

```
/portrait          her animated portrait in a small window of its own (again closes it)
/portrait obs      the see-through URL for an OBS browser source
```

A window with her in it that follows what she's doing. She blinks and
glances around, looks up and to the side while she thinks, and looks at
you while you talk. Her ears twitch now and then and perk up when you
start speaking. Her mouth moves with her actual voice: every sentence's
loudness is sent to the page as it starts playing. Her mood shows as a
smile, a blush or a frown. A failed tool gets a moment of spiral eyes,
and a big jump in warmth gets a flustered ><.

It's served by the live monitor, so `monitor.enabled` has to be on. It
opens as an app-style Chromium window (its own process, so `/portrait`
can close it again), or in your normal browser if there's no Chromium.
On Hyprland, float and pin it by title:

```
windowrulev2 = float, title:^(Luna)$
windowrulev2 = pin, title:^(Luna)$
```

**She looks at the conversation.** On Hyprland the live monitor checks
twice a second where the portrait window and Luna's terminal are, and
tells the page. She turns her head and eyes towards the terminal while
you talk and while she answers, and drifts back to it when idle. Move
either window and she follows. Anywhere that can't be worked out (another
compositor, OBS, the terminal on another workspace) she looks straight
ahead as before. If a model was rigged mirrored and looks the wrong way,
set `"flip_gaze": true` in `portrait.live2d`.

**Thinking is something you can watch.** She looks up and away from
you, to the side, then down for a moment as if weighing it, switches
sides, and glances back at you now and then. Her eyes dart in small
movements, her head follows further and wanders on its own, tilts
towards the side she's looking, and her brow lifts a little. It's the
same for the Live2D and the 3D portrait (`portrait/look.js`).

Page options: `?bg=transparent` (OBS), `?frame=face` (closer crop),
`?debug=1` (test buttons for every reaction, including *you: left /
right / ahead* to try the looking), `?demo=1` (acts out a conversation
on its own).

## Live2D models

```bash
python portrait/add_live2d.py ~/Downloads/1_希格雯.rar --name sigewinne
```

That's the Sigewinne model from
[vtuber-nook](https://vtuber-nook.com/asset/721/free-live2d-live2d-model-genshin-sigewinne/),
which is what the screenshot shows. On Fedora, opening the `.rar` needs
`sudo dnf install unrar` (from RPM Fusion). `7z` or `bsdtar` work too, or
extract it in your file manager and pass the folder.

This copies the model into `portrait/models/<name>/` with plain file
names, registers any `.exp3.json` expressions the model3.json forgot to
list, shrinks 8K textures to 4K (`--texture 0` keeps them), and switches
`config.json` to it. Restart Luna afterwards, then `/portrait`.

The standard Cubism parameters drive it: head angle, eyeballs, eye
open/smile, mouth open and form, cheek, brows and breath. Ears are the
model's own ear-physics parameters, nudged after physics runs, and
they're found by name. Expressions are matched to roles by what they
show (spiral eyes → confused, >< → flustered, tears → sad). All of that
lives in `config.json` under `portrait.live2d` if a model needs it
spelled out:

```json
"portrait": {
    "model": "models/sigewinne/sigewinne.model3.json",
    "live2d": {
        "expressions": {"confused": "spiral_eyes", "flustered": "x_eyes", "sad": "tears"},
        "ear_params": ["Param29", "Param31", "Param30", "Param35", "Param37", "Param39"],
        "crop": {"top": 0.02, "height": 0.42}
    }
}
```

### Using more of the rig

Most Live2D models hang their hair and ears off the head angles, and
their clothes off the body angles, with breathing feeding both. So the
portrait moves the body on its own instead of copying the head:

- **Body:** a slow sway of its own, a change of posture every half
  minute or so, leaning in while you talk, a little hop when she's
  pleased. The clothes physics swings with it.
- **Breathing:** a breath in that's quicker than the breath out, a
  little different each time, slower when it's late and quiet, and a
  top-up breath before she starts talking. Each breath also lifts the
  head and body slightly, so you can see it even on a model whose own
  breath parameter is subtle.
- **Brows and eyes:** worried when a reply came out unsure, one brow up
  when the grounding check flags a guess, furrowed when a tool fails,
  wide-eyed when you talk over her, softer when she's warm. One brow sits
  higher on the side she looks to while thinking. On Sigewinne the bangs
  hide much of the brows, so this mostly shows through the eyes.
- **Talking and listening:** small nods and brow lifts on her louder
  syllables, and an "mm-hm" nod every few seconds while you talk.
- **Idle:** after a quiet minute she looks around more, and now and then
  she stretches. Late at night her eyelids get heavier.

Two settings tune it, under `portrait.live2d`:

| Key | Default | What it does |
|-----|---------|--------------|
| `breath` | `1` | How visible her breathing is. `0` turns it off, `2` is deep |
| `motion` | `1` | How much the body sways and gestures move overall |
| `flip_lean` | `false` | For a rig where leaning in looks like leaning back |

The `?debug=1` page has a button for every gesture and reaction, sliders
for `breath` and `motion` (try values there, then put them in
`config.json`), and a picker that holds any one of the model's
parameters on a slider, named from its display file. That's the way to
find out what an unlabelled parameter like Sigewinne's `Param27` does.

Live2D's Cubism Core comes from Live2D's CDN. For offline use, run
`bash portrait/vendor/get_cubism_core.sh` once. It's Live2D's code under
their licence, so it's downloaded rather than shipped here. Models you
add are gitignored. They're usually big and always someone else's: the
Sigewinne model is marked personal use only, so check its Booth page
before putting it on stream.

### Hologram

Any Live2D model can be shown as a hologram: tinted towards one colour,
see-through, a glowing edge, scanlines rolling up, a faint flicker and
a projector glow under her. Now and then the picture tears sideways for
a moment, and it always does when a tool fails or you talk over her.
She brightens a little while she talks.

It's a filter over the finished picture (`portrait/hologram.js`), so
blinking, talking, the hair and ear physics and everything else come
through it unchanged.

Switch it with `/holo` (or `/holo on`, `/holo off`), or the **hologram
look** row in the tools pane's Portrait group. Either one saves the
choice and flips an open portrait straight away. `?holo=1` on the
portrait address forces it for that page (the `?debug=1` page gets
glitch and on/off buttons). The rest of the look is set in config.json:

```json
"portrait": {
    "hologram": { "enabled": true, "tint": "#c37bff", "mix": 0.8,
                  "intensity": 1.0, "glitch": 1.0, "base": true }
}
```

| Key | Default | What it does |
|-----|---------|--------------|
| `enabled` | `false` | On for every launch. `?holo=0` turns it off for one page |
| `tint` | `#c37bff` | The hologram's colour |
| `mix` | `0.8` | How much of her own colour is replaced by the tint: `0` keeps her colours, `1` is all tint |
| `intensity` | `1.0` | Overall brightness and opacity. Raise it for dark models |
| `glitch` | `1.0` | How hard the random tears hit. `0` turns them off |
| `base` | `true` | The projector glow and beam under her |

It works in OBS too: with `?bg=transparent&holo=1` she floats over the
stream as a projection.

### When something's off

| What you see | What to do |
|---|---|
| "couldn't load Live2D's Cubism Core" | Your machine can't reach Live2D's CDN. Run `bash portrait/vendor/get_cubism_core.sh` once. |
| She doesn't react | Open `http://127.0.0.1:8792/portrait/?debug=1`. Its buttons fire each reaction by hand, so you can tell the model from the events. |
| Too much or too little of her shows | Add `"crop": {"top": 0.02, "height": 0.42}` under `portrait.live2d`. A bigger `height` shows more; `crop_face` does the same for `?frame=face`. |
| Ears don't twitch | The debug panel lists the ear parameters it found. Name them in `portrait.live2d.ear_params` if it found none. |
| The window doesn't float on Hyprland | `windowrulev2 = float, title:^(Luna)$`, plus `pin` to keep it on every workspace. |

## VRM (3D) models

Point `portrait.model` at a `.vrm` and the same page renders it in 3D
with three-vrm. Blink, the five mouth shapes, the mood expressions and
look-at come from the VRM itself. Ears are nodes named like `Ear_L`, or
listed in `portrait.ear_bones`. `models/placeholder.vrm` is a stand-in
generated by `make_placeholder.py`.

`portrait/blender/` builds a 3D Luna in Blender from her pictures: a
cat girl with a purple-to-magenta bob, pink eyes, a fang and a bell
choker. Run `build_luna.py` then `export_luna.py` in Blender, then
`python portrait/make_vrm.py`:

- **Rigged, not just parented.** Her body is weighted to the spine,
  chest, neck and shoulders, so breathing and leaning bend her instead
  of sliding the whole torso. The portrait lifts her shoulders with each
  breath and lets her body sway and shift its weight on its own.
- **Hair that swings.** The bob, the side locks and the bangs hang from
  six bone chains that `make_vrm.py` turns into VRM spring bones, with
  colliders on the head, neck and shoulders so the hair doesn't pass
  through her.
- **Textures you can repaint.** Every part has UVs, and the colours are
  baked to `portrait/textures/luna_<part>.png` on export. Paint over
  those (or swap in generated ones, same size and layout) and export
  with `LUNA_KEEP_TEXTURES=1` so they're kept instead of baked over.
- `LUNA_HAIR=long` builds the long hair from the first wallpaper instead
  of the bob.

To use her instead of Sigewinne, set `portrait.model` to
`models/luna.vrm`.

`portrait/vendor/build.sh` rebuilds the two bundled libraries
(three.js + three-vrm, pixi.js + pixi-live2d-display) if you ever want
newer ones.
