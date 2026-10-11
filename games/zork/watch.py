"""Watch Luna play Zork: the game's screen, live, in a terminal.

    python games/zork/watch.py [saves folder]      (default: agent/zork)

Follows transcript.txt as zork_server.py writes it and tidies it for
reading: the game's status line (room, score, moves) becomes one short
bar, her commands are purple after a '>', what she says about the game
is pink, and everything is wrapped to the window instead of running off
the edge. Ctrl+C closes it; the game carries on either way. /zork watch
opens this for you.
"""
import os
import re
import shutil
import sys
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SAVES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "agent", "zork")
PATH = os.path.join(SAVES, "transcript.txt")

PURPLE, PINK, DIM, BOLD, ITALIC, RESET = ("\033[38;5;183m", "\033[38;5;218m", "\033[2m",
                                          "\033[1m", "\033[3m", "\033[0m")

# dfrotz's status line: the room on the left, score and moves far right
STATUS = re.compile(r"^\s*(\S.*?)\s{2,}Score:\s*(-?\d+)\s+Moves:\s*(\d+)\s*$")
SPEAKER = re.compile(r"^\[([A-Za-z][\w .'-]{0,30})\]\s?(.*)$")

_state = {"blank": True, "speaking": False}


def width():
    return max(30, min(shutil.get_terminal_size((100, 24)).columns, 110) - 2)


def out(text=""):
    sys.stdout.write(text + "\n")


def wrapped(text, style="", indent=""):
    for part in textwrap.wrap(text, width(), initial_indent=indent,
                              subsequent_indent=indent + ("  " if text[:1] in "-*" else "")) or [""]:
        out(f"{style}{part}{RESET}" if style else part)


def blank():
    if not _state["blank"]:
        out()
    _state["blank"] = True


def show(raw):
    line = raw.rstrip("\n").rstrip()

    if not line:
        _state["speaking"] = False
        blank()
        return

    _state["blank"] = False
    status = STATUS.match(line)
    speaker = SPEAKER.match(line)

    if status:
        room, score, moves = status.groups()
        label = f" {room}  ·  score {score}  ·  move {moves} "
        out(f"{DIM}{'─' * 2}{RESET}{BOLD}{label}{RESET}{DIM}{'─' * max(2, width() - len(label) - 2)}{RESET}")
    elif line.startswith("> "):
        _state["speaking"] = False
        wrapped(line, PURPLE + BOLD)
    elif speaker and not line.startswith(("[saved", "[restored")):
        _state["speaking"] = True
        name, said = speaker.groups()
        out(f"{PINK}{BOLD}{name}:{RESET}")
        wrapped(said, PINK + ITALIC, "  ")
    elif _state["speaking"]:
        wrapped(line, PINK + ITALIC, "  ")     # the rest of what she said
    elif line.startswith(("[", "=====")):
        wrapped(line[:width()], DIM)
    else:
        # keep the game's own indentation (inventory lists)
        indent = line[:len(line) - len(line.lstrip())]
        wrapped(line.strip(), "", indent)

    sys.stdout.flush()


def main():
    sys.stdout.write(f"\033]0;Luna plays Zork\007{DIM}Luna plays Zork - watching {PATH}\n"
                     f"Ctrl+C closes this window; the game keeps going.{RESET}\n\n")

    while not os.path.exists(PATH):
        time.sleep(1)

    with open(PATH, encoding="utf-8", errors="replace") as f:
        # The last part of what's already there, so you land mid-game.
        for line in f.readlines()[-80:]:
            show(line)

        while True:
            line = f.readline()
            if line:
                show(line)
                continue
            time.sleep(0.3)
            if os.path.exists(PATH) and os.path.getsize(PATH) < f.tell():
                f.seek(0, 2)     # the server trimmed it: carry on from the end


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
