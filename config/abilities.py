"""What she can reach: logging, vision, the desktop, tool switches and
routing, the knowledge base, ComfyUI, the camera.

Part of the config package (it was one config.py); see config/__init__.py.
"""
from .base import setting

# -------------------------
# Logging
# -------------------------
# Writes to ~/.cache/ai-voice/ai-voice.log. Off costs nothing, on costs
# a few kilobytes a day and turns "it broke" into a line you can read.
_log_cfg = setting("logging", {})
LOG_ENABLED = bool(_log_cfg.get("enabled", True))
# debug logs every VAD decision and tool argument, which is a lot; info
# logs the things that went wrong and the choices behind them.
LOG_LEVEL = str(_log_cfg.get("level", "info")).upper()
LOG_MAX_KB = int(_log_cfg.get("max_kb", 1024))
LOG_KEEP = int(_log_cfg.get("keep", 3))

# -------------------------
# Vision
# -------------------------
# Lets her look at your screen. Needs grim, and needs a vision model
# loaded in LM Studio - a text-only model will reject the request and
# the error is shown as-is. Optional "vision" block in agent.json:
#   "vision": { "enabled": true, "scale": 0.5 }
_vision_cfg = setting("vision", {})
VISION_ENABLED = bool(_vision_cfg.get("enabled", False))
# grim's own scale factor. Half a 4K screen is still plenty to read an
# error dialog off, and a quarter of the bytes.
VISION_SCALE = float(_vision_cfg.get("scale", 0.5))
VISION_MAX_BYTES = int(_vision_cfg.get("max_kb", 4096)) * 1024

# -------------------------
# Desktop control
# -------------------------
# Acting on the desktop rather than only looking at it - playback,
# volume, clipboard, window focus. Each tool checks for its own program
# at call time, so a missing playerctl costs that one tool rather than
# all four. Optional "desktop" block in config.json:
#   "desktop": { "enabled": true, "clipboard": true }
_desktop_cfg = setting("desktop", {})
DESKTOP_ENABLED = bool(_desktop_cfg.get("enabled", True))

# Her hands on your files: list_files/read_file are free under ~, minus
# a deny list; write_file/edit_file pop an approval window in the TUI
# and wait. No answer within approval_timeout seconds is a no.
#   "files": { "enabled": true, "approval_timeout": 120 }
# Tools switched off by hand, by name. Not in SETTINGS because it's a
# list rather than a scalar - the tools pane (Tab, twice) edits it, and
# tools.set_enabled writes it back.
TOOLS_DISABLED = list(setting("tools", {}).get("disabled", []))
# Routing: every tool stays on, and each turn is sent only the groups it
# seems to need (tools/routing.py). The core groups always travel; a
# group used in the last sticky_turns turns stays; she can attach any
# other with more_tools. false sends every tool on every turn.
_tools_cfg = setting("tools", {})
TOOLS_ROUTING = bool(_tools_cfg.get("routing", True))
TOOLS_ROUTE_GROUPS = int(_tools_cfg.get("route_groups", 3))
TOOLS_STICKY_TURNS = int(_tools_cfg.get("sticky_turns", 3))
_core = _tools_cfg.get("core", ["Time", "Math", "Reminders", "Memory", "Shell"])
TOOLS_CORE = list(_core) if isinstance(_core, (list, tuple)) else ["Time", "Math", "Reminders", "Memory", "Shell"]
# The opt-in tools (tools.OPT_IN, the camera) switched on - an on-list,
# so they stay off until you choose them. Its own key: tools.enabled is
# the master switch further down.
_opt_in = setting("tools", {}).get("opt_in", [])
TOOLS_OPT_IN = list(_opt_in) if isinstance(_opt_in, (list, tuple)) else []
# An older config.json kept this list under tools.enabled, which is also
# the master on/off switch. A list there means: the camera list (moved
# here) with tools on. Fixed in the file on the next save of either.
_old_enabled = setting("tools", {}).get("enabled", True)
if isinstance(_old_enabled, (list, tuple)):
    TOOLS_OPT_IN = sorted(set(TOOLS_OPT_IN) | set(_old_enabled))

# The webcam, for look_at_camera. The switch is the tool's row in the
# tools pane; these only say which camera and how big.
#   "camera": { "device": 0, "width": 1280, "warmup": 5 }
# Her knowledge base (knowledge.py): folders of your notes, manuals,
# PDFs and docs she can look things up in. The index is a cache outside
# the repo (~/.cache/ai-voice/knowledge.db).
#   "knowledge": { "enabled": true, "folders": ["~/luna-knowledge"], "auto": true,
#                  "auto_passages": 2, "min_score": 0.55, "rescan_minutes": 10 }
_knowledge_cfg = setting("knowledge", {})
KNOWLEDGE_ENABLED = bool(_knowledge_cfg.get("enabled", True))
KNOWLEDGE_FOLDERS = list(_knowledge_cfg.get("folders") or ["~/luna-knowledge"])
KNOWLEDGE_AUTO = bool(_knowledge_cfg.get("auto", True))           # matching passages travel with the turn unasked
KNOWLEDGE_AUTO_PASSAGES = int(_knowledge_cfg.get("auto_passages", 2))
KNOWLEDGE_MIN_SCORE = float(_knowledge_cfg.get("min_score", 0.55))  # how close, by meaning, to come in unasked
KNOWLEDGE_RESCAN_MINUTES = float(_knowledge_cfg.get("rescan_minutes", 10))

# ComfyUI, for make_texture (portrait/texture.py).
#   "comfyui": { "url": "http://127.0.0.1:8188" }
COMFY_URL = str((setting("comfyui", {}) or {}).get("url", "http://127.0.0.1:8188"))

_camera_cfg = setting("camera", {})
# A number (a webcam here), a /dev/video path, or a camera server's URL.
_cam = _camera_cfg.get("device", 0)
CAMERA_DEVICE = int(_cam) if isinstance(_cam, (int, float)) or str(_cam).strip().lstrip("-").isdigit() else str(_cam).strip()
CAMERA_WIDTH = int(_camera_cfg.get("width", 1280))
CAMERA_WARMUP = int(_camera_cfg.get("warmup", 5))

