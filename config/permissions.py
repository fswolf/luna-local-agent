"""What needs asking: email, file reads and writes, job folders, remote
auto-approve, the clipboard.

Part of the config package (it was one config.py); see config/__init__.py.
"""
import os

from .base import setting
from .abilities import _desktop_cfg

# Email (tools/mail.py). The login is in ~/.config/ai-voice/email.json,
# never here. Reading is on whenever there's a login; sending is off
# until you say so, and even then every message asks.
#   "email": { "enabled": true, "send": false, "max": 20 }
_email_cfg = setting("email", {})
EMAIL_ENABLED = bool(_email_cfg.get("enabled", True))
EMAIL_SEND = bool(_email_cfg.get("send", False))
EMAIL_MAX = int(_email_cfg.get("max", 20))   # most messages one check or search returns

_files_cfg = setting("files", {})
FILES_ENABLED = bool(_files_cfg.get("enabled", True))
FILES_APPROVAL_TIMEOUT = float(_files_cfg.get("approval_timeout", 120))
# The Permissions group in the tools pane. read: allow | ask | off,
# write: ask | allow | off. "allow" for write is the saved form of the
# popup's A: her own folder, ~/.config and ~/.local still ask, and the
# deny list still refuses. Execute is shell.enabled (commands always ask).
FILES_READ = str(_files_cfg.get("read", "allow")).lower()
FILES_WRITE = str(_files_cfg.get("write", "ask")).lower()
# Folders a scheduled job (plugins/cron.py) may write in without the
# popup. Yours to set - a plugin can't widen it. The deny list still
# wins, ~ itself and this app's own folder are ignored, and every other
# write still asks.
#   "files": { ..., "job_write_dirs": ["~/luna-jobs"] }
# Remote plugins whose owner turns write without the popup - remote
# access, where nobody is at the desk to answer it. The deny list still
# applies. Empty = every remote write asks (and times out as a no).
#   "files": { ..., "auto_approve_sources": ["discord"] }
FILES_AUTO_APPROVE_SOURCES = [str(s).strip().lower() for s in
                              _files_cfg.get("auto_approve_sources", []) if str(s).strip()]
FILES_JOB_WRITE_DIRS = [os.path.expanduser(str(p)) for p in
                        _files_cfg.get("job_write_dirs", []) if str(p).strip()]
# Separate from the rest, because reading the clipboard means whatever
# you last copied - a password, an API key - can land in the model's
# context and from there in history on disk. On by default, but it is
# the one here worth knowing is a switch.
DESKTOP_CLIPBOARD = bool(_desktop_cfg.get("clipboard", True))

