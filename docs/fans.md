# Hologram fans

A hologram fan is a spinning blade of LEDs. Spun fast, it draws a round
picture that seems to float in the air, and black shows as nothing at all.
Luna can show on two kinds of fan.

| Fan | How she gets there | Live? |
|---|---|---|
| **HDMI fan** (Holofan HDMI and others) | It's a screen: open `/portrait/?fan=1` on it | Yes |
| **WiFi fan run by the Holoscope app** (P56, PD42, P42, HS56...) | Luna streams to it over WiFi (`web/holofan.py`) | Yes, about 15 frames a second |
| Any other WiFi fan (3D LED FAN, 3D Circle, 5D Displayer, Spin Display apps...) | Not supported: those only play clips from their own card | No |

Status: built against the protocol and tested with the pretend fan
(`python3 -m web.holofan sim`, below), not yet on a real fan.

## Buying one

| Fan | Size | Price seen (Oct 2026) | With Luna |
|---|---|---|---|
| **Holoscope P56** | 22" / 56 cm | about US$150-350 | Live. Its protocol and picture format were checked on a real fan by [p56-studio](https://github.com/trackerr/p56-studio) |
| **Holoscope PD42 / P42** | 16.5" / 42 cm | about US$32 (TVCMALL) to US$164 (Holofex HoloXG2) | Probably live. An older picture format that newer firmware may ignore |
| **HDMI fan** (Holofan HDMI, Holofex, superbholo, luminafans) | 30-100 cm | from about €1,200 | Live, no setup beyond a screen |
| Other WiFi fans | | US$80-250 | Clips from their own card only |

- **Look for "Holoscope"** in the listing, its photos, the manual or the
  Q&A. Fans rarely say which app they use, and the same model names turn up
  under many brands. If the seller can't say, skip it.
- **The model shows up when it connects.** The debug viewer names it (P56,
  PD42...) and says if it's one Luna can't draw for yet.
- **Put a microSD card in a PD42** (FAT32, 32 GB or less). Without one it
  fails every upload, and it may need one for live video too.
- **Bluetooth:** many fans have a Bluetooth speaker, but on these fans
  WiFi and Bluetooth share one radio, so her voice stays on your speakers.

## HDMI fan

Plug the fan in as a second screen and open the portrait full screen on it:

```bash
chromium --kiosk --app="http://127.0.0.1:8792/portrait/?fan=1"
```

`?fan=1` gives a black background, all of her centred, and no buttons or
notes. `&frame=bust` shows head and shoulders instead. The fan shows the
middle square of whatever it's sent.

## WiFi fan (Holoscope)

Turn it on in `config.json`:

```json
"portrait": {
    "fan": { "cast": true, "framing": "full", "fps": 15 }
}
```

Then put the computer and the fan on one network:

- **The fan's own WiFi.** Join `3D-...` (password usually `12345678`). The
  fan is `192.168.4.1`. This is simplest, but the computer loses its normal
  internet unless it has a second network adapter.
- **Your router.** Use the Holoscope app once to give the fan your WiFi
  (2.4 GHz only), then set `"ip"` to the fan's address.

Luna announces herself, the fan connects to her, and from then on she shows
on it whenever a portrait page is open: the desktop portrait, the OBS
source or the viewer. The page renders her a second time with a camera of
its own (centred, square, black background, turning when she turns), so the
portrait on your screen can stay at bust. Her framing is set from her
standing height, so a bow or a crouch moves her within the circle instead of
moving the camera. While a fan is connected she also plays the legs-only
gestures, even if your own screen shows her at bust. When the page closes,
the fan goes back to its own clips.

The page has to be drawing: a minimised window stops, and so does an OBS
source with "Shutdown source when not visible" ticked. If two pages are
open, the first one keeps the fan and the other rests. This works with 3D
(VRM) models only.

The debug viewer (`./studio.sh`) shows the fan under **hologram fan**: which
model it is, its address, frames a second, the JPEG quality and any error.
A fan that goes quiet for 12 seconds (unplugged, out of range) is let go,
and it connects again by itself when it comes back.

| `portrait.fan` | Default | |
|---|---|---|
| `cast` | `false` | Stream to a Holoscope fan |
| `framing` | `"full"` | `"full"` or `"bust"` |
| `fps` | `15` | 8 to 25. The fan needs one at least every 130 ms |
| `scale` | `1` | Bigger or smaller in the circle |
| `x`, `y` | `0` | Move her off centre (a fraction of the picture) |
| `rotation` | `0` | Degrees clockwise, for a fan hung sideways |
| `mirror` | `false` | For a fan watched from behind |
| `gain` | per model (1.5) | Holoscope's brightness lift for dark pictures; `1` turns it off if she looks washed out |
| `ip` | | The fan's address, once it's on your router |

`?nocast` on a portrait URL stops that page from casting, and
`?fanframe=bust` sets the framing for that page only.

### Trying it without a fan

```bash
python3 -m web.holofan sim        # a pretend P56; "sim 15" for a PD42
```

It acts as a fan on this machine: it hears Luna, connects and takes the
stream, then writes `/tmp/holofan-preview.png` every second, the round picture a
real fan would show (it needs Pillow). Set `"ip": "127.0.0.1"` while you
try it.

### How it works

The protocol was worked out by
[p56-studio](https://github.com/trackerr/p56-studio) (MIT), which also has a
full open-source replacement for the Holoscope app. Luna is the server: she
broadcasts `<her-ip>HS` on UDP 8988, and the fan connects to her on TCP 6666
and reports its model. To cast, she sends `5A 26 26 F5`, the fan answers
`29`, and then one frame at a time follows. Each frame is a JPEG of at most
20,476 bytes in a fixed 20,480-byte packet. The picture is unrolled around
its centre into one strip per LED arm, outside-in (688×240 for a P56's four
arms of 172 LEDs, 960 angles). The page does that unrolling on the GPU
(`portrait/viewer/fan.js`) and posts the JPEG to `/portrait/fan/frame`;
`web/holofan.py` relays it to the fan.

Luna never sends the fan's format, factory-reset, delete or Bluetooth
commands. On these fans WiFi and Bluetooth share one radio, and with
Bluetooth audio connected a P56 drops off WiFi. So her voice stays on your
speakers.

Luna listens on TCP 6666 on every network while casting is on, and only
accepts connections from local addresses (home network, the fan's own
WiFi). Anyone on your network could connect and see what the fan would
show, which is only her portrait.
