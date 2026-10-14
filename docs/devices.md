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

## Lovense

```
/lovense on     /lovense off     /lovense     /lovense stop     /lovense toys
```

Connects her to Lovense toys through the Lovense Remote app on your own
network, the same bridge many Second Life toys use. While it's on she
has four tools:

| Tool | What it does |
|------|--------------|
| `lovense_vibrate` | A steady level, 0-20, for a number of seconds |
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
        "max_seconds": 60
    }
}
```

`/lovense on` connects and lists the toys; with no toy paired it still
connects and says so, which is a good way to check the network path
first. `"enabled": true` connects at startup.

**Limits.** `max_strength` (0-20) and `max_seconds` cap whatever she
asks for, whatever the model writes.

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

## Buttplug: toys of almost any brand

```
/buttplug on    /buttplug off    /buttplug    /buttplug stop    /buttplug scan
```

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

| Tool | What it does |
|------|--------------|
| `toy_vibrate` | A steady intensity, 0-100, for a number of seconds: vibration, and rotation or oscillation on toys that do that |
| `toy_pattern` | pulse, wave, escalate, heartbeat or tease, up to a peak intensity |
| `toy_stroke` | Back and forth for strokers like The Handy, at a speed 0-100 |
| `toy_stop` | Stop one device or all of them |
| `toy_list` | What's connected and what each can do |

**Setting it up.**

1. Install [Intiface Central](https://intiface.com/central/) and press
   Start Server.
2. Turn the device on and close its own phone app: a Bluetooth toy
   talks to one thing at a time. If you use Lovense Remote for Second
   Life, use [the Lovense plugin](#lovense) instead.
3. `pip install websocket-client` (or the installer's `toys` extra),
   then `/buttplug on`. It scans for devices as it connects;
   `/buttplug scan` looks again.

```json
"plugins": {
    "buttplug": {
        "enabled": false,
        "url": "ws://127.0.0.1:12345",
        "max_intensity": 100,
        "max_seconds": 60,
        "scan_on_start": true
    }
}
```

On Linux, Intiface uses BlueZ. If it doesn't find a device that's on
and not connected to anything else, a cheap USB Bluetooth dongle often
fixes it.

**Limits, stopping, roleplay and who can use it** work as for
[Lovense](#lovense): `max_intensity` and `max_seconds` cap whatever she
asks for; a stop word in your message, interrupting her,
`/buttplug stop`, `/buttplug off` and quitting Luna all stop every
device (`stop_words` and `stop_on_interrupt` work the same); her prompt
lists what's connected and what each device can do; only your own turns
can start one, never a turn that has read outside content or a
scheduled job, and stopping is never blocked.
