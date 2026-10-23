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

A tool result is a **string**: there's nowhere in the tool-calling
format to hand back an image. So `look_at_screen` captures one, stashes
it, and returns a sentence saying it did; the image is then attached to
the next message as an `image_url` block. From the model's point of view
it asked to look at something and the next thing it saw was a picture.

The image lives for exactly one turn. It isn't written to history, so
she can't look back at an earlier screenshot: ask "what about now?" and
she takes a new one.

## Which window

This is the fiddly part, and the answer depends on how you asked.

**Typed at her**, the focused window is her own terminal, and the one
behind it is whatever you last touched: on a tiling compositor that's
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

## The camera

She can also look through your webcam, one picture at a time, when
you ask.

```
> "What am I holding?"
> "Read this label for me."
> "Luna, look at this." (on stream, holding something up)
```

**It's off until you switch it on.** Open the tools pane (Tab twice),
find the **Camera** group and press Space on `look_at_camera`, or type
`/camera on`. On a fresh install, and in any config written before the
camera existed, it stays off.

Once it's on:

- **One picture per request.** No live feed, nothing in the background
  (unless you also turn on [presence](#presence-noticing-youre-there), below).
- **Nothing is saved.** The picture lives for one turn, like a
  screenshot, and goes only to your local model.
- **Only for you at the desk.** It's never offered to stream chat,
  Discord turns or scheduled jobs, so nobody can ask her to look but
  you.
- **You see it happen.** Each picture shows `Camera: took one picture`
  in the conversation, and your camera's own light comes on.

It needs OpenCV, which works on Linux, macOS and Windows:

```bash
pip install opencv-python-headless      # or: python3 installer/install.py --extras camera
```

and, like the screen, a model that can see.

```
/camera            on or off, which camera, whether it's ready
/camera list       every camera that opens, with its size
/camera test       take a picture without sending it anywhere
```

```json
"camera": { "device": 0, "width": 1280, "warmup": 5 }
```

| Key | Default | Purpose |
|-----|---------|---------|
| `device` | `0` | Which camera: a number (`/camera list` shows them; a virtual camera from OBS can take number 0), a device file like `/dev/video2` on Linux, or a camera server's URL (below) |
| `width` | `1280` | Pictures are scaled down to this, plenty for reading a label |
| `warmup` | `5` | Frames thrown away first, because a webcam's first frame is nearly black |

**A camera server instead of a webcam.** If your camera is already
served over the network (mjpg-streamer, ustreamer, go2rtc, motion, an
IP camera, a phone app like IP Webcam), point her at its URL:

```bash
/set camera.device http://192.168.1.20:8080/?action=snapshot
/set camera.device http://user:password@192.168.1.20:8080/video
/set camera.device rtsp://192.168.1.20:8554/cam
```

- A **snapshot URL** (answers with one JPEG) is the fastest and best.
- An **MJPEG stream** works too: she reads until the first whole
  picture and hangs up.
- Both of those go straight over HTTP and don't need OpenCV at all.
  `user:password@` in the URL is sent as a normal login, and never
  shown back in her messages.
- **RTSP** goes through OpenCV.

That's also the easy way round Linux webcam trouble: a server like
ustreamer owns the device, and everything else (OBS, a browser, Luna)
reads from it instead of fighting over `/dev/video0`.

**First time on each system:**

- **macOS** asks whether the terminal Luna runs in (Terminal, iTerm,
  kitty) may use the camera. If you said no, pictures fail or come
  back black: allow it in System Settings > Privacy & Security >
  Camera, then restart Luna.
- **Windows** needs Settings > Privacy > Camera > *Let desktop apps
  access your camera*.
- **Linux** usually just works. She asks for the camera through V4L2
  in MJPEG, which most USB webcams need to give a full-size picture.
  If it can't open the camera, check that you're in the `video` group
  and that nothing else holds it. One webcam often shows up as two
  `/dev/video` files and only one gives pictures; `/camera list` shows
  which.

On every system, a camera that OBS or Discord is already using may
refuse to open. She'll say so rather than guess.

### The camera light, and hooks

The webcam's light comes on whenever she opens the camera. On most
webcams it's wired to the sensor, so nothing can switch it off, and
that's the honest signal for anyone else in the room. Some cameras let
software set it, and for those (or anything else you want done around
the camera) there are hooks:

```json
"camera": { "before": "v4l2-ctl -d /dev/video0 -c led1_mode=0",
            "after":  "v4l2-ctl -d /dev/video0 -c led1_mode=3" }
```

- `before` runs each time she opens the webcam herself: a picture,
  the [face check](people.md#the-face-check), presence starting.
  `{device}` in the command becomes the camera.
- `after` runs when she's done with it, even if the picture failed.
- A hook that isn't installed, fails or hangs (3 seconds) goes in the
  logbook and the camera carries on without it.

Plugins can do the same with `on_camera_open(device)` and
`on_camera_close(device)`. `plugins/camera_led.py` is a worked one for
Linux cameras with a V4L2 LED control (many Logitech ones): install
`v4l-utils`, then `/camera_led on`. It tells you if your camera has no
such control. For those, a strip of tape over the light (not the lens)
always works.

## Presence: noticing you're there

A separate switch, off by default: the webcam stays open and she checks
for a face a few times a second. That costs a few percent of one CPU
core and no GPU. With it on she:

- **Greets you when you come back** after being away a while (20
  minutes by default), in one short line, only when nothing else is
  going on. At startup, the usual "welcome back" waits until someone is
  actually in front of the camera.
- **Looks at you.** Her portrait's eyes follow your face instead of
  aiming at the terminal.
- **Keeps quiet in an empty room.** After 5 minutes with nobody in
  view, games and scheduled jobs still run and still show on screen,
  but don't talk out loud.
- **Knows faces**, once you've enrolled them, so she greets the right
  person by name (and, with voices too, knows who's talking: see
  [People in the house](people.md)).

Your camera's light stays on while it watches: that's the honest
signal that it is. Nothing is recorded or sent: pictures live in memory, and the newest
one also answers `look_at_camera`, so the two never fight over the
camera. Face finding and face prints are OpenCV's YuNet and SFace, two
small models (about 40 MB together) downloaded once into
`~/.cache/ai-voice/models`. Until they arrive, OpenCV's built-in face
detector stands in: it notices faces but can't tell whose.

```
/presence             on or off, what it's doing right now
/presence on|off      switch it (saved to config.json)
/people               who she knows
/people enroll face Shannon    look at the camera for a few seconds
/people forget Shannon [face]  forget the prints, or the whole person
                               (voices: see people.md)
```

Enrolling takes ten face prints over a few seconds; turn your head a
little while it does. Prints are numbers describing a face, not
pictures, and live in `agent/people/` (one file per person, kept out of
git). Enroll again in different light if she's unsure of you.

```json
"camera": { "presence": { "enabled": false, "fps": 3, "greet": true, "greet_after_minutes": 20,
                          "look": true, "quiet": true, "quiet_after_minutes": 5,
                          "recognise": true, "match": 0.36 } }
```

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `false` | Keep the webcam watching |
| `fps` | `3` | Face checks a second |
| `greet` | `true` | Say hi when someone comes back |
| `greet_after_minutes` | `20` | How long someone must have been away first |
| `look` | `true` | Her portrait looks at the face in view |
| `quiet` | `true` | Games and jobs stop speaking when nobody's there |
| `quiet_after_minutes` | `5` | How long the room must be empty first |
| `recognise` | `true` | Match faces to enrolled people |
| `match` | `0.36` | How alike a face must be to count as someone (higher is stricter) |

All of them are on the settings page (`/settings`) too. Presence needs a webcam on
the same machine, not a camera server.
