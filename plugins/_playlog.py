"""Game playlogs: each of her turns, in a text file to read later.

    agent/playlogs/zork-2026-10-11.txt
    agent/playlogs/vibecity-2026-10-11.txt

One file per game per day, appended turn by turn. A game can hand over
a ready-made block (Zork writes the screen the way the watch window
shows it: a status bar, the game's text wrapped, then what she said);
otherwise it's her words under a turn number and the time. A helper
for the game plugins (the leading underscore keeps the loader from
treating it as a plugin). Never fails a turn: a log that can't be
written is skipped.
"""
import os
import textwrap

from datetime import datetime

import config

DIR = os.path.join(config.BASE_DIR, "agent", "playlogs")
WIDTH = 78


def said_block(text, width=WIDTH):
    """Her words under her name, wrapped and indented."""
    lines = [f"{config.AGENT_NAME}:"]
    for para in (text or "").strip().splitlines():
        lines += textwrap.wrap(para.strip(), width, initial_indent="  ", subsequent_indent="  ") or [""]
    return "\n".join(lines)


def write(game, turn, said, block=None, also=None):
    """Append one turn.

    said   what she said this turn
    block  the whole turn already laid out (optional); without it, her
           words under a "turn N  time" line
    also   other files to copy her words into, as "[Luna] ..." (the Zork
           transcript, so the watch window shows them too)

    Returns the playlog's path, or None.
    """
    said = (said or "").strip()

    if not said and not block:
        return None

    try:
        os.makedirs(DIR, exist_ok=True)
        now = datetime.now()
        path = os.path.join(DIR, f"{game}-{now:%Y-%m-%d}.txt")
        body = block or f"--- turn {turn}  {now:%H:%M:%S} ---\n{said_block(said)}"

        with open(path, "a", encoding="utf-8") as f:
            f.write("\n" + body.rstrip() + "\n")

        if said:
            for extra in also or []:
                with open(extra, "a", encoding="utf-8") as f:
                    f.write(f"\n[{config.AGENT_NAME}] {said}\n")

        return path
    except Exception:
        return None
