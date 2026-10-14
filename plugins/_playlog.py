"""Game playlogs: each of her turns, in a text file to read later - and
in her memory (remember / finished below), so time spent playing becomes
an episode she can recall like any conversation.

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
import json
import os
import re
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


# ---------------------------------------------------------------------------
# Her memory of playing: one record line per turn into the open play
# session (notebook.play_turn); reflect.py writes the finished session up
# as an episode while she's idle.
# ---------------------------------------------------------------------------
_FRAMING = re.compile(r"^Result from the [\w .-]+ tool \(outside content[^)]*\):\s*")


def _short(value, n):
    text = " ".join(str(value or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def exchange_line(exchange):
    """One tool call as a line: the tool, its arguments, what came back."""
    name = str(exchange.get("name", "")).split("__", 1)[-1]
    args = exchange.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            args = {"": args}
    shown = ", ".join(f"{k}={_short(v, 60)}" if k else _short(v, 60) for k, v in args.items())
    result = _FRAMING.sub("", str(exchange.get("result", "")))
    return f"- {name}({shown}) -> {_short(result, 220)}"


def remember(game, title, said, exchanges=(), lines=None):
    """This turn, into her memory of the session: what she did (lines if
    the game has words for it, else her tool calls) and what she said."""
    try:
        import notebook

        did = list(lines) if lines else [exchange_line(x) for x in exchanges or ()
                                         if not str(x.get("name", "")).endswith("game_note")]
        text = "\n".join(did + ([f"she said: {_short(said, 500)}"] if str(said or "").strip() else []))
        notebook.play_turn(game, title, text)
    except Exception:
        pass        # a memory that couldn't be written is never a reason a turn fails


def finished(game):
    """She stopped playing: the session gets written up while she's idle."""
    try:
        import notebook

        notebook.play_end(game)
    except Exception:
        pass
