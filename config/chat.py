"""Plugins and stream chat: each plugin's block, and the shared chat policy
(tool ceiling, cooldowns).

Part of the config package (it was one config.py); see config/__init__.py.
"""
from .base import setting

# -------------------------
# Plugins
# -------------------------
# Everything under "plugins" in config.json, keyed by plugin name. The
# core never learns what a plugin's own keys mean - it just hands the
# block over - which is what keeps a plugin droppable.
#
# "chat" is the exception: shared policy for any plugin that feeds her
# live chat from strangers. It lives here rather than in a plugin
# because it is the part that must not be per-plugin. A plugin can ask
# for a wider tool list; chatroom.TOOL_CEILING is what it gets.
#
# API keys are deliberately not in here. config.json is in the repo,
# and a key pasted into it is a key on GitHub - plugins read their own
# from the environment or from ~/.config/ai-voice/.
_plugins_cfg = setting("plugins", {})

_chat_cfg = _plugins_cfg.get("chat") or {}
# Which tools a stranger's question may reach. Everything absent from
# this acts on Ryan's machine or Ryan's data, and a viewer must not be
# able to reach it by asking nicely: the tools are dropped from the
# request, not refused at call time.
CHAT_TOOLS = tuple(_chat_cfg.get(
    "tools", ["get_datetime", "time_until", "web_search"]
))
# Seconds between answers, so she isn't talking over the stream.
CHAT_COOLDOWN_SECONDS = float(_chat_cfg.get("cooldown_seconds", 8))
# And per viewer, so one person can't monopolise her.
CHAT_USER_COOLDOWN_SECONDS = float(_chat_cfg.get("user_cooldown_seconds", 30))
# A very long chat message is a paste, and a paste aimed at her is
# usually an attempt at something.
CHAT_MAX_MESSAGE_CHARS = int(_chat_cfg.get("max_message_chars", 300))
# How much of the room she can see. Memory only, never stored.
CHAT_CONTEXT_LINES = int(_chat_cfg.get("context_lines", 12))
