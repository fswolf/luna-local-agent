# Home and devices

Things in the room she can switch: your smart home through Home
Assistant, and toys through the Lovense Remote app or Buttplug.io's
Intiface Central. All of it stays on your own network, and anything
physical has limits, a stop that doesn't go through her, and never
starts from someone else's words. How plugins work in general is on
[Plugins](plugins.md).

## Your home: Home Assistant

```
/home on        /home off        /home        /home refresh
```

Connects her to a [Home Assistant](https://www.home-assistant.io/) on
your own network, so she can run your lights, plugs, sensors and
thermostat. Local only, and locks and garage doors always ask first.
Setup, safety and which devices to buy are on their own page:
[Home automation](home.md).

## Lovense or Buttplug?

There are two ways to connect toys, and they're both plugins:

| | Lovense plugin | Buttplug plugin |
|---|---|---|
| Talks to | the **Lovense Remote** app (phone or PC) in Game Mode | **Intiface Central** on the same PC as Luna |
| Brands | Lovense only | 750+ devices: Lovense, Kiiroo, We-Vibe, Satisfyer, The Handy, Magic Motion... |
| Good for | a Lovense toy that already lives in the Remote app (Second Life users) | anything else, and testing with simulated devices or a gamepad |
| Needs | the app and Luna on the same network | Bluetooth on the PC running Luna |

A Bluetooth toy connects to one app at a time, so pick one route per
toy: if it's paired with Lovense Remote, use the Lovense plugin; if it's
paired with Intiface, use the Buttplug plugin. Lovense toys work either
way.

### What kind of device is it?

Toys report what their motors do, and Luna treats each kind differently:

| Kind | What it does | What can be controlled | Luna's tool |
|------|--------------|------------------------|-------------|
| **Vibrator** (1 or more motors) | vibrates | intensity | `toy_vibrate`, `toy_pattern` (`lovense_vibrate`, `lovense_pattern`) |
| **Rotator** | spins (rotating heads) | speed | `toy_vibrate`, `toy_pattern` |
| **Oscillator** | moves back and forth by itself: thrusting machines, the Solace | **speed only**, not where it is in the stroke | `toy_stroke` (`lovense_move`) |
| **Stroker** | moves to exact positions: The Handy | position and timing | `toy_stroke` |

Vibration and motion are kept apart on purpose. A machine never runs
from a vibration command, it has its own lower speed cap, and it always
starts slow (see the limits below). A toy that does both, like the
Lovense Gravity, runs both at once, and each part stops when its own
time is up. Multi-motor vibrators run all their motors at the same
level.

### Talking to her about it

Plain words work; she picks the tools and the numbers:

- "Vibrate the plug at 40 for a minute"
- "Run a wave pattern on everything"
- "Start the machine slowly and build up"
- "Both toys on max" → vibration at 100 (or your `max_intensity`), the
  machine at its `max_motion` cap, which is 50% unless you've raised it
- "Stop" → everything stops at once, before she even reads it

In a scene it works the same way: "faster", "harder", "tease me a
little more" mean the toy, and her prompt tells her that describing it
isn't doing it - she calls the tool. Her instructions say "when she
asks" or "when he asks" from the `user` block in `agent/agent.json`
(see [configuration](configuration.md#whos-she-talking-to)).

If you don't say how long, it's about 10 seconds; nothing runs longer
than `max_seconds`. The caps are always yours, in `config.json`: she
can ask for 100, but she can't raise a ceiling.

## Lovense

```
/lovense on     /lovense off     /lovense     /lovense stop     /lovense toys     /lovense find
```

Connects her to Lovense toys through the Lovense Remote app on your own
network, the same bridge many Second Life toys use. While it's on she
has five tools:

| Tool | What it does |
|------|--------------|
| `lovense_vibrate` | A steady level, 0-20, for a number of seconds |
| `lovense_move` | Thrusting or stroking for machines (Mini Sex Machine, Solace, Gravity), 0-20, building up from slow |
| `lovense_pattern` | One of the app's built-in patterns: pulse, wave, fireworks, earthquake |
| `lovense_stop` | Stop one toy or all of them |
| `lovense_toys` | Which toys are connected, with battery |

**Setting it up.** Install Lovense Remote on your phone or PC, connect
the toy to it, and turn on Game Mode. The app shows an address and port;
put them in `config.json`:

```json
"plugins": {
    "lovense": {
        "enabled": false,
        "host": "192.168.1.50",
        "port": 20010,
        "use_https": false,
        "max_strength": 20,
        "max_seconds": 60,
        "max_motion": 10,
        "ramp_seconds": 3
    }
}
```

Or let Luna find it: with Game Mode on and the app open, `/lovense
find` looks for the Remote app on your network and saves its address
for you (if it finds more than one, `/lovense use <number>` picks).

`/lovense on` connects and lists the toys; with no toy paired it still
connects and says so, which is a good way to check the network path
first. `"enabled": true` connects at startup.

**Limits.** `max_strength` (0-20) and `max_seconds` cap whatever she
asks for, whatever the model writes.

**Machines get their own, stricter limits.** Thrusting and stroking
are a different thing from vibration, so they never come from a
vibration command:

- `max_motion` (0-20, default 10) caps machine speed separately from
  vibration, so a high vibration setting never becomes a machine at
  full speed. Raise it yourself once you know the machine.
- Motion always **builds up from slow** over `ramp_seconds` (default
  3), even if she asks for full speed straight away.
- A toy that does both (Gravity vibrates and thrusts) runs both at once,
  and each part stops when its own time is up.
- The app is always given the time left, so if Luna crashes or the
  network drops, the toy still stops on its own.

`lovense_toys` lists what each toy can do, so she knows which one moves.

**Stopping.** Any of these stops every toy, straight to the app,
without going through her:

- a **stop word** in your message: "stop", "red", "safeword", "enough",
  "too much", "pause", "ow", "ouch". It happens before she reads it, so
  it doesn't depend on the model noticing. Set your own with
  `"stop_words": [...]`.
- **interrupting her** (HOME, or `ai-voice-ctl.py stop`). Turn that off
  with `"stop_on_interrupt": false`.
- `/lovense stop`, `/lovense off`, or quitting Luna.

**In a roleplay.** While it's on and you're talking to her yourself, her
system prompt says which toy is connected and which tools drive it, so
she can use it when you ask or when it fits the scene, and is told to
say what she's doing and to stop when you say so. Stream chat and
Discord turns without memory never get that line.

**Who can use it.**

- Only your own turns: typed, voice, and Discord from an owner.
  Stream chat never sees these tools.
- Not a turn that has read outside content (an email, a web page, an
  MCP result such as Minecraft chat). Someone else's text can't be what
  switches it on; ask in your next message and it works.
  [Files](files.md#outside-content) explains the rule.
- Not a scheduled job.
- Stopping is never blocked.

### Finding them on your network

`/lovense find` and `/buttplug find` look on this computer first, then
on every machine on your own network: the same quiet pass
[find_device](sysadmin.md#finding-machines-on-your-network) uses, then a
knock on the one port each app uses (12345 for Intiface, 20010 and
30010 for Lovense Remote). Only something that answers like the app
counts: a Buttplug handshake, or a toy list from Lovense Remote. Only
private addresses are touched, and the address found is saved to
`config.json` as if you'd typed it. Intiface takes one client at a
time, so run `find` before `/buttplug on`, not while Luna is connected.

## Buttplug: toys of almost any brand

```
/buttplug on    /buttplug off    /buttplug    /buttplug stop    /buttplug scan    /buttplug find
```

`scan` looks for toys through Intiface; `find` looks for Intiface
itself, on this PC and on your network.

**This rests on someone else's work.** [Buttplug.io](https://buttplug.io)
is an open-source project that has spent years working out the
Bluetooth protocols of over 750 devices and putting one common protocol
in front of all of them, and [Intiface Central](https://intiface.com/central/)
is its free app that does the talking. BSD 3-Clause licensed. This
plugin is a small client for it; every device it supports is their
doing. If it's useful to you, go and say thanks.

That covers Lovense, Kiiroo, We-Vibe, Satisfyer, The Handy, Magic
Motion, Vorze and many more, and also Xbox gamepads and Switch Joy-Cons,
so you can try the whole thing with no toy at all. Support goes by
model, not just brand, so check [buttplug.io](https://buttplug.io)
before buying something new. Everything stays on your machine: no
cloud, no account.

The chain is short:

```
Luna  →  Intiface Central (on your PC, ws://127.0.0.1:12345)  →  Bluetooth  →  the toy
```

| Tool | What it does |
|------|--------------|
| `toy_vibrate` | A steady intensity, 0-100, for a number of seconds: vibration, and rotation on toys that do that |
| `toy_pattern` | pulse, wave, escalate, heartbeat or tease, up to a peak intensity |
| `toy_stroke` | Strokers and machines (The Handy, the Solace, thrusting machines) at a speed 0-100, building up from slow |
| `toy_stop` | Stop one device or all of them |
| `toy_list` | What's connected and what each can do |

### Installing Intiface Central

Download it from [intiface.com](https://intiface.com/) (Windows, macOS,
Linux, Android, iOS). On Linux:

- The official build is a zip for Ubuntu 24.04 from
  [its releases](https://github.com/intiface/intiface-central/releases/latest).
  It runs on Fedora as well: unzip it (it's a zip inside a zip), then
  run `./intiface_central`. If a library is missing, the error names it,
  and `dnf provides` finds the package.
- A Flatpak exists on Flathub, but it lags well behind (2.6 against
  3.2 at the time of writing). Prefer the zip.
- There's also `intiface-engine`, the same server with no window, for
  running in the background:
  `intiface-engine --websocket-port 12345 --use-bluetooth-le`.
- There's no point in a Docker container: it has to run on the machine
  that's physically near the toy, because the toy talks Bluetooth to it.

Intiface uses BlueZ on Linux. Check the PC has Bluetooth with
`bluetoothctl show`; if a device that's on and not connected to anything
else isn't found, a cheap USB Bluetooth dongle often fixes it. Pair
through Intiface's own scan, not the system's Bluetooth settings.

### Setting it up

1. Open Intiface Central and press the big **play button** (Start
   Server). The status changes to "Engine running, waiting for client".
2. Check the server address it shows. `ws://localhost:12345` is what
   Luna expects. If it shows your network address (`192.168.x.x`), the
   "listen on all interfaces" setting is on and anyone on your network
   could connect; turn it off in Intiface's Settings when Luna runs on
   the same PC.
3. Turn the device on and close its own phone app: a Bluetooth toy
   talks to one thing at a time. If you use Lovense Remote for Second
   Life, use [the Lovense plugin](#lovense) instead.
4. `pip install websocket-client` (or the installer's `toys` extra),
   then `/buttplug on`. If Intiface runs somewhere else (a phone, with
   "listen on all interfaces" on), `/buttplug find` looks for it on your
   network and saves its address; `/buttplug use <number>` picks if
   there's more than one. It scans for devices as it connects;
   `/buttplug scan` looks again, and `/buttplug` lists each device with
   what it can do.

```json
"plugins": {
    "buttplug": {
        "enabled": false,
        "url": "ws://127.0.0.1:12345",
        "max_intensity": 100,
        "max_seconds": 60,
        "max_motion": 50,
        "ramp_seconds": 3,
        "scan_on_start": true
    }
}
```

### Testing with no toy: simulated devices

Intiface can pretend to be any kind of device: **Devices → Advanced
Device Management → Simulated Devices**, pick a type (1-motor vibrator,
2-motor vibrator, oscillator, rotator, stroker), give it a name, and
press **Add Simulated Device**. Luna sees it as a real toy, and
Intiface shows what it's being told to do, so the whole path can be
checked before any hardware arrives. A good first test:

1. Add a **2-motor vibrator** and an **oscillator**, then `/buttplug on`
   and `/buttplug`: both are listed, the oscillator with
   "stroke/thrust".
2. Ask her to vibrate one and run the other at the same time: the
   vibrator holds its level while the oscillator starts low and climbs
   over about three seconds.
3. Say "stop": both drop to zero at once.

### Limits

- `max_intensity` (0-100) and `max_seconds` cap whatever she asks for,
  whatever the model writes.
- **Machines and strokers have their own cap**, `max_motion` (0-100,
  default 50), so a vibration setting never becomes a machine at full
  speed. "Max" on a machine means this cap. To allow more, raise it in
  `config.json` and `/buttplug off`, `/buttplug on` to reload; it's
  deliberately not something she can change.
- Motion always **builds up from slow** over `ramp_seconds` (default 3),
  even when she asks for full speed straight away. `0` turns the ramp
  off.
- When a new command replaces an old one, any device the new one
  doesn't cover is switched off, so nothing is left running unattended.

### Stopping, roleplay and who can use it

These work as for [Lovense](#lovense): a stop word in your message,
interrupting her, `/buttplug stop`, `/buttplug off` and quitting Luna
all stop every device (`stop_words` and `stop_on_interrupt` work the
same); her prompt lists what's connected and what each device can do;
only your own turns can start one, never a turn that has read outside
content or a scheduled job, and stopping is never blocked.
