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

Live2D's Cubism Core comes from Live2D's CDN. For offline use, run
`bash portrait/vendor/get_cubism_core.sh` once. It's Live2D's code under
their licence, so it's downloaded rather than shipped here. Models you
add are gitignored. They're usually big and always someone else's: the
Sigewinne model is marked personal use only, so check its Booth page
before putting it on stream.

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

`portrait/blender/` builds a 3D Luna from her wallpaper in Blender.
Run `build_luna.py` then `export_luna.py` in Blender, then
`python portrait/make_vrm.py`. That adds the humanoid bones, blink and
mouth shape keys, toon shading, and a look-at that slides the iris
texture (`portrait/textures/iris.png`, from `design/make_textures.py`).
It's a work in progress: it looks better in Blender than it does in
the portrait window so far.

`portrait/vendor/build.sh` rebuilds the two bundled libraries
(three.js + three-vrm, pixi.js + pixi-live2d-display) if you ever want
newer ones.
