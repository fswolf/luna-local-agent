# Home automation

Luna can run your smart home: lights, plugs, sensors, thermostats,
blinds, locks. She does it through [Home Assistant](https://www.home-assistant.io/),
free, open-source software that runs on a machine of yours and talks to
your devices over your own network. No cloud account, no app from the
bulb's maker, nothing leaving the house.

```
/home on        connect          /home off       disconnect
/home           status           /home refresh   re-read the device list
```

Things you can say once it's set up:

- "Turn off the living room lights"
- "Dim the bedroom to 30 percent"
- "Is anything still on downstairs?"
- "What's the temperature upstairs?"
- "Is the back door locked?"
- "Set the heat to 21"

## How it fits together

```
you  ->  Luna  ->  Home Assistant  ->  your devices
         (this PC)  (this PC or a box     (Zigbee, Wi-Fi,
                     on your network)      Z-Wave, Matter...)
```

Home Assistant has an [MCP server built in](https://www.home-assistant.io/integrations/mcp_server/).
The `home` plugin connects Luna to it, and Home Assistant's actions
show up as her tools, in the tools pane under **MCP: home**, while the
plugin is on. When it's off they're gone from the prompt and cost
nothing.

## Local only, by design

The plugin refuses any address that isn't on your own network, before
a byte is sent:

| Allowed | Refused |
|---------|---------|
| `localhost`, `127.0.0.1` | Any public address |
| `192.168.x.x`, `10.x.x.x`, `172.16-31.x.x` | Cloud links (Nabu Casa and the like) |
| Names that resolve to those, like `homeassistant.local` | A name that resolves to a public address |

So a typo or a pasted cloud link can't send your home's state off the
box. Luna talks to Home Assistant directly, and Home Assistant talks to
your devices. Home Assistant's optional paid cloud service is never
involved.

## Setting up Home Assistant

You only do this once. Start on this PC; move it to its own box later
if you like (see *Moving it to its own box*).

### 1. Install it

The [installation page](https://www.home-assistant.io/installation/)
lists every option. On a Linux desktop the easy one is a container.
Make a folder for it (say `~/homeassistant`) with this
`docker-compose.yml`:

```yaml
services:
  homeassistant:
    container_name: homeassistant
    image: ghcr.io/home-assistant/home-assistant:stable
    volumes:
      - ./config:/config:Z
      - /etc/localtime:/etc/localtime:ro
      - /run/dbus:/run/dbus:ro
    restart: unless-stopped
    privileged: true
    network_mode: host
```

```bash
cd ~/homeassistant
docker compose up -d          # or: podman compose up -d
```

The `:Z` matters on Fedora: SELinux won't let the container write its
config folder without it. Then open `http://localhost:8123` and make an
account. During onboarding, leave analytics unticked if you don't want
usage stats sent.

### 2. Add your devices

Settings, Devices & services. Home Assistant finds a lot on its own
(TVs, Chromecasts, printers, some smart plugs); Zigbee devices need a
dongle first, see *Devices that stay local*.

### 3. Turn on its MCP server

Settings, Devices & services, **Add integration**, search for **Model
Context Protocol Server**, add it. There's nothing to fill in.

### 4. Choose what Luna can see

Settings, Voice assistants, **Expose**. Tick what she's allowed to see
and control. **This is the main control**: what isn't ticked doesn't
exist as far as she's concerned. Start with a few lights and add more
as you trust it.

### 5. Make her a token

Click your name (bottom left), Security, **Long-lived access tokens**,
Create token, name it "Luna". Copy it: Home Assistant only shows it
once.

## Connecting Luna

Put the token outside the repo:

```jsonc
// ~/.config/ai-voice/homeassistant.json
{"token": "eyJhbGciOi..."}
```

`HASS_TOKEN` in the environment works too. Then:

```bash
pip install mcp      # once, in Luna's venv
```

```
> /home on
home: 9 tools from http://localhost:8123 - 2 device(s) that always ask (saved)
```

`(saved)` means it reconnects next launch. `/home off` stops that.

The settings, in `config.json` under `plugins`:

```json
"home": {
    "enabled": false,
    "url": "http://localhost:8123",
    "ask_all": false,
    "ask_domains": ["lock", "cover", "alarm_control_panel", "valve", "siren"]
}
```

| Key | |
|-----|--|
| `url` | where Home Assistant is. Must be on your own network |
| `ask_all` | `true`: every change asks first. Good while you're starting out |
| `ask_domains` | kinds of device that always ask (below) |
| `skip_tools` | Home Assistant tools to leave out. Default: its timers (she has her own reminders) and broadcast (it talks out of your speakers). Set `[]` to get them back |

## What always asks

Exposing a device is the first gate. Some changes get a second one and
**always ask first**, in the popup at the desk:

| Asks | Why |
|------|-----|
| Locks, garage doors and gates, alarm panels, valves, sirens (`ask_domains`) | These open your house, set off an alarm or flood it |
| A sweep with no device named ("turn everything off in the kitchen") while any of those are exposed | It could reach a lock |
| Every change, with `"ask_all": true` | Your choice |

- **Blinds and curtains don't ask.** They share the cover domain with
  garage doors; the plugin tells them apart by device type.
- **Reading never asks.** "Is the door locked?" just answers.
- **The popup says why it's asking**, for example *Front Door
  (lock.front_door) always asks*.
- **From Discord, these ask in the chat** even when Discord approval is
  set to `auto` (see [Plugins](plugins.md)). Everything else from
  Discord follows that setting.
- **Unsure means ask.** If the plugin can't tell what a call would
  touch, it asks.

`/home` shows exactly which devices are on the always-ask list. After
exposing something new in Home Assistant, `/home refresh` re-reads it
(it also refreshes on its own every ten minutes).

## Devices that stay local

Home Assistant being local doesn't help if the bulb itself phones home.
Many cheap Wi-Fi plugs and bulbs only work through their maker's cloud,
so what you buy matters as much as the software.

| Kind | What you need | Notes |
|------|---------------|-------|
| **Zigbee** | A USB dongle (Sonoff, SMLight) | The most common local option. Bulbs, plugs, buttons, motion and door sensors. Use Home Assistant's built-in Zigbee support or [Zigbee2MQTT](https://www.zigbee2mqtt.io/). Devices only ever talk to the dongle |
| **Z-Wave** | A Z-Wave USB stick | Common for locks and wall switches |
| **Thread / Matter** | A Thread border router | Newer devices; Matter is designed to work locally |
| **Shelly** | Nothing extra | Wi-Fi relays and plugs with a local API |
| **ESPHome** | An ESP32 board | Build your own sensors ([esphome.io](https://esphome.io/)) |

**Avoid** anything whose box says it needs an app account to work.

A cheap first setup: Home Assistant on this PC, a Zigbee dongle, and a
couple of Zigbee bulbs or plugs.

## Moving it to its own box

Home Assistant on this PC stops when the PC does. When you want it
always on, put it on a Raspberry Pi or a small mini PC, copy your
`config` folder across (or use Home Assistant's own backup and
restore), then change one line:

```json
"url": "http://192.168.1.50:8123"
```

Use the box's address on your network, or `http://homeassistant.local:8123`
if your network resolves that name. The token stays the same if you
restored a backup; otherwise make a new one.

## Keep it updated

Home Assistant had a serious bug in 2026
([CVE-2026-34205](https://nvd.nist.gov/vuln/detail/CVE-2026-34205)):
some add-on apps were reachable, unprotected, from anything on your
network. It's fixed in Supervisor 2026.03.2. Update regularly; with the
container install that's `docker compose pull && docker compose up -d`.

## When it doesn't work

| `/home on` says | Fix |
|-----------------|-----|
| `no token` | Make one (step 5) and save it to `~/.config/ai-voice/homeassistant.json` |
| `homeassistant.json is broken` | A stray comma or quote in that file |
| `the token was refused` | The token is wrong or was deleted. Make a new one |
| `can't reach Home Assistant` | It isn't running, or `url` is wrong. Open the address in a browser |
| `MCP server didn't answer ... 404` | The Model Context Protocol Server integration isn't added (step 3) |
| `offered no tools` | Nothing is exposed yet (step 4) |
| `isn't on your own network` | `url` points outside your network. That's refused on purpose |
| `pip install mcp` | The MCP library isn't installed in Luna's venv |
