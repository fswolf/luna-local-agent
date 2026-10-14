"""Watch Luna in REALITI: what she does there and what the world says back, live.

    python games/realiti/watch.py <transcript>     (default: ~/luna-realiti/transcript.txt)

Follows the transcript plugins/realiti.py writes and colours it for
reading: the room she's in as a bar, what she does in purple after an
arrow, the world's own words as they came, what she says about it in
pink. Ctrl+C closes it; she carries on either way. /realiti watch opens
this for you. Standard library only.
"""
import os
import shutil
import sys
import textwrap
import time

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/luna-realiti/transcript.txt")

PURPLE, PINK, DIM, BOLD, ITALIC, RESET = ("\033[38;5;183m", "\033[38;5;218m", "\033[2m",
                                          "\033[1m", "\033[3m", "\033[0m")

_state = {"speaking": False}


def width():
    return max(30, min(shutil.get_terminal_size((100, 24)).columns, 110) - 2)


def out(text=""):
    sys.stdout.write(text + "\n")


def wrapped(text, style="", indent=""):
    for part in textwrap.wrap(text, width(), initial_indent=indent, subsequent_indent=indent) or [""]:
        out(f"{style}{part}{RESET}" if style else part)


def show(raw):
    """One transcript line. The transcript's own shapes:
    '== Room ==', '-> what she did  (time)', '   the world's words',
    '[Luna] what she said' (continued on '   ' lines), '-- note --'."""
    line = raw.rstrip("\n").rstrip()

    if not line:
        _state["speaking"] = False
        out()
    elif line.startswith("== ") and line.endswith(" =="):
        _state["speaking"] = False
        label = f" {line[3:-3]} "
        out(f"{DIM}──{RESET}{BOLD}{label}{RESET}{DIM}{'─' * max(2, width() - len(label) - 2)}{RESET}")
    elif line.startswith("-> "):
        _state["speaking"] = False
        wrapped("→ " + line[3:], PURPLE + BOLD)
    elif line.startswith("[") and "] " in line[:40]:
        _state["speaking"] = True
        name, said = line[1:].split("] ", 1)
        out(f"{PINK}{BOLD}{name}:{RESET}")
        wrapped(said, PINK + ITALIC, "  ")
    elif line.startswith("-- ") and line.endswith(" --"):
        _state["speaking"] = False
        wrapped(line, DIM)
    elif _state["speaking"]:
        wrapped(line.strip(), PINK + ITALIC, "  ")
    else:
        wrapped(line.strip(), "", "   ")

    sys.stdout.flush()


def main():
    sys.stdout.write(f"\033]0;Luna in REALITI\007{DIM}Luna in REALITI - watching {PATH}\n"
                     f"Ctrl+C closes this window; she carries on.{RESET}\n\n")

    while not os.path.exists(PATH):
        time.sleep(1)

    with open(PATH, encoding="utf-8", errors="replace") as f:
        for line in f.readlines()[-80:]:      # the last part, so you land mid-visit
            show(line)

        while True:
            line = f.readline()
            if line:
                show(line)
                continue
            time.sleep(0.3)
            if os.path.exists(PATH) and os.path.getsize(PATH) < f.tell():
                f.seek(0)     # trimmed or started over: from the top of what's left


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
