"""The situation block: what's going on around her, right now.

A few lines at the top of every one of Ryan's turns, so she isn't
starting blind each time:

    Around you right now:
    - Focused window: firefox - Hyprland Wiki
    - Playing: Daft Punk - Veridis Quo (playing)
    - Machine: CPU 18%, RAM 21.4 of 31.2 GB free, GPU 34% busy (VRAM 11.2/16 GB)
    - Running: minecraft, zork
    - Next reminder: tomorrow 09:00 - take the bins out (in 18 hours)

Every line is optional and each source is cheap; anything that can't be
read (no Hyprland, no playerctl, a Mac without /proc) is simply left
out rather than guessed. The whole block is cached for a few seconds,
because a turn builds its prompt more than once.

Never on a stream-chat turn: the focused window's title and what's
playing are his business.

    "situation": {
        "enabled": true,
        "window": true, "music": true, "machine": true,
        "plugins": true, "reminders": true
    }

/set situation.enabled false turns it off; /situation shows what she'd
see this turn.
"""
import os
import shutil
import subprocess
import sys
import time

import config
import logbook

CACHE_SECONDS = 8

_cache = {"at": 0.0, "text": ""}


def enabled():
    return bool(getattr(config, "SITUATION_ENABLED", True))


def _part(name):
    return bool(getattr(config, "SITUATION_PARTS", {}).get(name, True))


# ---------------------------------------------------------------------------
# Sources - each returns a line, or "" when there's nothing honest to say
# ---------------------------------------------------------------------------
def _window():
    if sys.platform == "darwin":
        # lsappinfo needs no Accessibility permission, unlike System Events.
        if not shutil.which("lsappinfo"):
            return ""
        try:
            front = subprocess.run(["lsappinfo", "front"], capture_output=True,
                                   text=True, timeout=2).stdout.strip()
            out = subprocess.run(["lsappinfo", "info", "-only", "name", front],
                                 capture_output=True, text=True, timeout=2).stdout
            name = out.split("=", 1)[-1].strip().strip('"') if "=" in out else ""
            return f"Front app: {name}" if name else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    try:
        import vision

        _geometry, described = vision._active_window()
    except Exception:
        return ""

    return f"Focused window: {described}" if described else ""


def _music():
    try:
        import desktop

        if not desktop.media_available():
            return ""

        playing = desktop.now_playing()
    except Exception:
        return ""

    if not playing or playing.startswith("Nothing") or "reports no track" in playing:
        return ""

    return f"Playing: {playing}"


def _machine():
    parts = []

    try:
        load = os.getloadavg()[0] / max(1, os.cpu_count() or 1)
        parts.append(f"CPU {min(100, round(load * 100))}%")
    except (OSError, AttributeError):
        pass

    try:
        import machine

        total, available = machine.memory()

        if total and available is not None:
            parts.append(f"RAM {available:.1f} of {total:.1f} GB free")

        gpus = machine.gpus()

        if gpus:
            g = gpus[0]
            bits = []

            if g.get("busy") is not None:
                bits.append(f"{g['busy']}% busy")

            if g.get("vram_used") is not None and g.get("vram_total"):
                bits.append(f"VRAM {g['vram_used']:.1f}/{g['vram_total']:.0f} GB")

            if bits:
                parts.append("GPU " + ", ".join(bits))
    except Exception:
        pass

    return ("Machine: " + ", ".join(parts)) if parts else ""


def _plugins():
    try:
        import plugins

        on = [n for n in plugins.names() if plugins.get(n) and plugins.get(n).running()]
    except Exception:
        return ""

    return ("Running: " + ", ".join(on)) if on else ""


def _reminders():
    try:
        import reminders

        upcoming = reminders.pending()
    except Exception:
        return ""

    if not upcoming:
        return ""

    line = f"Next reminder: {reminders.describe(upcoming[0])}"

    if len(upcoming) > 1:
        line += f" (+{len(upcoming) - 1} more)"

    return line


SOURCES = (("window", _window), ("music", _music), ("machine", _machine),
           ("plugins", _plugins), ("reminders", _reminders))


# ---------------------------------------------------------------------------
def lines(fresh=False):
    """The block's lines, cached for a few seconds."""
    if not fresh and time.monotonic() - _cache["at"] < CACHE_SECONDS:
        return _cache["text"].splitlines()

    out = []

    for name, source in SOURCES:
        if not _part(name):
            continue

        try:
            line = source()
        except Exception as e:
            logbook.debug("situation", "%s failed: %s", name, e)
            line = ""

        if line:
            out.append(line[:200])

    _cache.update(at=time.monotonic(), text="\n".join(out))
    return out


def block():
    """The prompt block, or "" when it's off or there's nothing to say."""
    if not enabled():
        return ""

    found = lines()

    if not found:
        return ""

    return ("Around you right now (live, refreshed every turn - use it when it's relevant, "
            "don't recite it):\n" + "\n".join(f"- {line}" for line in found) + "\n")
