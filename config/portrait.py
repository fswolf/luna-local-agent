"""Her portrait (models, hologram, gestures), MCP servers, the live monitor.

Part of the config package (it was one config.py); see config/__init__.py.
"""
import os

from .base import BASE_DIR, setting

# The portrait window (portrait/, served by the live monitor at
# /portrait/): a VRM model that blinks, looks around, twitches its ears
# and moves its mouth with her voice. /portrait opens it.
#   "portrait": { "model": "models/luna/robot_default.vrm", "ear_bones": [],
#                 "browser": "", "size": "420x560" }
_portrait_cfg = setting("portrait", {})
# Luna's own model (portrait/models/luna/, ships with the repo) is the
# default, and the fallback when portrait.model points at something that
# isn't there. Sigewinne (Live2D) if the robot model is missing.
_LUNA_ROBOT = "models/luna/robot_default.vrm"
_SIGEWINNE = "models/sigewinne/sigewinne.model3.json"
_DEFAULT_PORTRAIT = (_LUNA_ROBOT if os.path.isfile(os.path.join(BASE_DIR, "portrait", _LUNA_ROBOT))
                     else _SIGEWINNE)
PORTRAIT_MODEL = str(_portrait_cfg.get("model") or _DEFAULT_PORTRAIT)
PORTRAIT_EAR_BONES = list(_portrait_cfg.get("ear_bones", []) or [])
PORTRAIT_BROWSER = str(_portrait_cfg.get("browser", ""))
PORTRAIT_SIZE = str(_portrait_cfg.get("size", "420x560"))
# How much of her the camera fits: "bust" (head and shoulders, the
# default) or "full" (all of her), switched from the tools pane; an open
# portrait reframes at once. "face" (a close crop) is still accepted
# here and as ?frame=face. A page with ?frame= on its URL keeps that
# framing whatever this says, so an OBS source can keep its own.
FRAMES = ("bust", "full")
# Touching her portrait (portrait/touch.json): she reacts there at once,
# and with touch_talk on she also answers out loud in one short line
# (touches.py), at most once every touch_talk_cooldown seconds.
PORTRAIT_TOUCH_TALK = bool(_portrait_cfg.get("touch_talk", True))
PORTRAIT_TOUCH_TALK_COOLDOWN = float(_portrait_cfg.get("touch_talk_cooldown", 12))
PORTRAIT_FRAME = str(_portrait_cfg.get("frame", "bust")).lower()
if PORTRAIT_FRAME not in FRAMES + ("face",):
    PORTRAIT_FRAME = "bust"
# Live2D only: which expression is which (portrait/add_live2d.py fills it
# in), and which parameters are the ears if their names don't say so.
# The hologram look (portrait/viewer/hologram.js): off unless "enabled": true, or
# ?holo=1 on the portrait URL. tint, mix (0 = her own colours, 1 = all
# tint), intensity, glitch (how often it tears), base (the projector glow).
#   "hologram": { "enabled": true, "tint": "#c37bff", "mix": 0.8 }
PORTRAIT_HOLOGRAM = dict(_portrait_cfg.get("hologram", {}) or {})
PORTRAIT_HOLOGRAM_ENABLED = bool(PORTRAIT_HOLOGRAM.get("enabled", False))
# Gestures on a 3D model (gestures.py, portrait/viewer/gestures.js). How her
# replies set them off: "tags" (she picks, keywords as fallback),
# "meaning" (the embedding model, keywords as fallback), "keywords",
# "off". chat_gestures: viewers' !hug, hi, lol. meaning_margin: how far
# a gesture must beat an ordinary reply in meaning mode.
PORTRAIT_GESTURES = str(_portrait_cfg.get("gestures", "tags"))
PORTRAIT_CHAT_GESTURES = bool(_portrait_cfg.get("chat_gestures", True))
PORTRAIT_MEANING_MARGIN = float(_portrait_cfg.get("meaning_margin", 0.04))
# Little sounds with her gestures (portrait/sounds/, yours - not in git): a
# gesture file names one, sound: 'touch-self'. No file there, no sound.
# sound_volume 0-1.
PORTRAIT_SOUNDS = bool(_portrait_cfg.get("sounds", True))
# Her morning coffee (coffee.py): once a day, between from and to (hours,
# 24h clock), the first time you're around she picks up her mug, takes a
# sip every few minutes, and puts it down after `minutes`. Each sip wakes
# her up a little (energy, 0 for none).
#   "coffee": { "enabled": true, "from": 5, "to": 11, "minutes": 40, "sip_minutes": 4, "wake": 0.03 }
_coffee_cfg = dict(_portrait_cfg.get("coffee", {}) or {})
PORTRAIT_COFFEE = bool(_coffee_cfg.get("enabled", True))
PORTRAIT_COFFEE_FROM = int(_coffee_cfg.get("from", 5))
PORTRAIT_COFFEE_TO = int(_coffee_cfg.get("to", 11))
PORTRAIT_COFFEE_MINUTES = float(_coffee_cfg.get("minutes", 40))
PORTRAIT_COFFEE_SIP_MINUTES = float(_coffee_cfg.get("sip_minutes", 4))
PORTRAIT_COFFEE_WAKE = float(_coffee_cfg.get("wake", 0.03))
PORTRAIT_SOUND_VOLUME = max(0.0, min(1.0, float(_portrait_cfg.get("sound_volume", 0.8))))
# Hologram fans (holofan.py, docs/fans.md). An HDMI fan just shows
# /portrait/?fan=1. A WiFi fan run by the Holoscope app (P56, PD42...) gets
# her live with cast on: Luna listens on TCP 6666 and announces herself on
# UDP 8988. framing "full" or "bust"; scale/x/y move her in the circle;
# rotation (degrees) and mirror for how the fan hangs; fps 8-25; ip: the
# fan's address once it's on your router (it finds Luna either way); gain:
# the brightness lift for dark pictures (per model, 1 = off).
#   "fan": { "cast": true, "framing": "full", "fps": 15 }
PORTRAIT_FAN = dict(_portrait_cfg.get("fan", {}) or {})
PORTRAIT_FAN_CAST = bool(PORTRAIT_FAN.get("cast", False))
PORTRAIT_LIVE2D = dict(_portrait_cfg.get("live2d", {}) or {})
if not PORTRAIT_LIVE2D and PORTRAIT_MODEL == _SIGEWINNE:
    # Its three expressions, so moods show on her face out of the box.
    PORTRAIT_LIVE2D = {"expressions": {"sad": "tears", "flustered": "x_eyes", "confused": "spiral_eyes"}}

# MCP servers whose tools she can use (mcpclient.py). Read at startup.
#   "mcp": { "enabled": true, "servers": { "obs": {"command": "...", "args": [...]} } }
_mcp_cfg = setting("mcp", {})
MCP_ENABLED = bool(_mcp_cfg.get("enabled", True))
MCP_SERVERS = dict(_mcp_cfg.get("servers", {}) or {})

# The live monitor (livefeed.py): a page served by the assistant on
# 127.0.0.1, showing each turn as it happens. Read at startup.
#   "monitor": { "enabled": true, "port": 8792 }
_monitor_cfg = setting("monitor", {})
MONITOR_ENABLED = bool(_monitor_cfg.get("enabled", True))
MONITOR_PORT = int(_monitor_cfg.get("port", 8792))

