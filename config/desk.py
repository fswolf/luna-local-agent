"""The desk: the control socket (push-to-talk binds), the TUI and its theme.

Part of the config package (it was one config.py); see config/__init__.py.
"""
import os

from .base import setting

# -------------------------
# Control socket (Hyprland / Wayland push-to-talk)
# -------------------------
CONTROL_SOCKET = os.environ.get(
    "AI_VOICE_SOCKET",
    os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "ai-voice.sock"),
)

# -------------------------
# TUI
# -------------------------
# Mouse capture gives wheel scrolling at the cost of text selection -
# the terminal can only hand drags to one of them. Off by default,
# because a window full of log lines you can't copy is worse than one
# you scroll with PgUp.
UI_MOUSE = bool(setting("ui", {}).get("mouse", False))

# -------------------------
# TUI theme
# -------------------------
# MewNix Candy by default. Override any subset in agent.json:
#   "theme": { "accent": "#ff87d7", "user": "#5fd7ff" }
# Values are hex colours; terminals without truecolor get the nearest
# 256-colour match automatically.
_THEME_DEFAULTS = {
    # sfav-style purple
    "accent": "#ff87d7",
    "border": "#b48cff",
    "title": "#ffafd7",
    "label": "#b48cff",

    # Main text
    "text": "#ccd0ea",
    "value": "#ccd0ea",

    # Agent / user
    "agent": "#ff87d7",
    "user": "#5fd7ff",

    # System/status
    "system": "#d9b46a",
    "ok": "#87ffaf",
    "warn": "#ff5f87",

    # Footer / separators
    "footer": "#8787af",
    "dim": "#5a5a78",

    # Prompt
    "prompt": "#ff87d7",

    # Links
    "link": "#b48cff",
}

THEME = dict(_THEME_DEFAULTS)
THEME.update(
    {k: v for k, v in setting("theme", {}).items() if k in _THEME_DEFAULTS}
)

