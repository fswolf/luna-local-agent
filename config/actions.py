"""Tool calling, alarms, reminders, the shell, web search and page fetches.

Part of the config package (it was one config.py); see config/__init__.py.
"""
from .base import setting

# -------------------------
# Tool calling
# -------------------------
# Lets the model call set_reminder, web_search, remember_fact and so on
# for itself instead of relying on keyword triggers. Needs a model with
# a tool template (Qwen, Llama 3.1+, Mistral, Hermes...); if the server
# rejects the payload we fall back automatically at runtime.
_tools_cfg = setting("tools", {})
TOOLS_ENABLED = _tools_cfg.get("enabled", True)
if not isinstance(TOOLS_ENABLED, bool):      # the old opt-in list (see TOOLS_OPT_IN)
    TOOLS_ENABLED = True
# How many times the model may call tools before it must answer in prose.
MAX_TOOL_ROUNDS = int(_tools_cfg.get("max_rounds", 4))

# -------------------------
# Alarms
# -------------------------
# An alarm is a reminder that has to actually wake somebody, so it gets
# its own volume, repeats until dismissed, and plays a tone after the
# voice. Speech alone doesn't wake anyone - it is exactly the thing a
# sleeping brain is best at folding into a dream.
_alarm_cfg = setting("alarms", {})
ALARMS_ENABLED = bool(_alarm_cfg.get("enabled", True))
# Independent of tts.volume on purpose: the level you picked for a
# conversation at midnight is not the level that gets you up at seven.
ALARM_VOLUME = float(_alarm_cfg.get("volume", 1.0))
ALARM_REPEATS = int(_alarm_cfg.get("repeats", 5))
ALARM_GAP_SECONDS = float(_alarm_cfg.get("gap_seconds", 25))
# Nine, because every alarm clock ever made used nine.
ALARM_SNOOZE_MINUTES = int(_alarm_cfg.get("snooze_minutes", 9))
# Empty means the bundled assets/alarm.wav, and if that is missing or
# unreadable the tone is synthesized instead - an alarm that fails
# silently is worse than no alarm, because you were relying on it.
ALARM_TONE = str(_alarm_cfg.get("tone", "")).strip()

_reminders_cfg = setting("reminders", {})
REMINDERS_ENABLED = _reminders_cfg.get("enabled", True)
REMINDER_CHECK_INTERVAL_SECONDS = _reminders_cfg.get("check_interval_minutes", 10) * 60

_shell_cfg = setting("shell", {})
# run_command: she runs a shell command, and every one asks first.
SHELL_ENABLED = bool(_shell_cfg.get("enabled", True))
SHELL_TIMEOUT = float(_shell_cfg.get("timeout", 60))
SHELL_MAX_OUTPUT = int(_shell_cfg.get("max_output_chars", 6000))
# sudo in her commands: off, or a password box on your screen for each one
# (tools/askpass.sh). The password goes to sudo, never to her.
SHELL_SUDO = bool(_shell_cfg.get("sudo", False))
# Remote sources whose commands run without the popup - for automation
# from Discord. Empty by default: opting in is yours, in core config.
SHELL_AUTO_APPROVE_SOURCES = [str(s).strip().lower() for s in
                              _shell_cfg.get("auto_approve_sources", []) if str(s).strip()]

_web_search_cfg = setting("web_search", {})
WEB_SEARCH_ENABLED = _web_search_cfg.get("enabled", True)
WEB_SEARCH_MAX_RESULTS = _web_search_cfg.get("max_results", 5)
# Opening a page she found, rather than summarizing the search blurb.
PAGE_FETCH_ENABLED = bool(_web_search_cfg.get("fetch_pages", True))
# How much of a page reaches the model. Roughly a thousand tokens per
# 4000 characters, so this is the main cost control.
PAGE_MAX_CHARS = int(_web_search_cfg.get("page_max_chars", 6000))
PAGE_TIMEOUT = float(_web_search_cfg.get("page_timeout", 20))
# read_page and research refuse this machine and the local network
# (your router, llama-server, the monitor) unless this is on. A page
# can ask her to "read" http://192.168.1.1/ as easily as you can.
PAGE_ALLOW_LOCAL = bool(_web_search_cfg.get("allow_local", False))
# research: how many pages it reads, and how much of them in total.
RESEARCH_PAGES = max(1, int(_web_search_cfg.get("research_pages", 3)))
RESEARCH_MAX_CHARS = int(_web_search_cfg.get("research_max_chars", 9000))


