"""Watch Luna play Zork: the game's screen, live, in a terminal.

    python games/zork/watch.py [saves folder]      (default: agent/zork)

Follows transcript.txt as zork_server.py writes it: her commands in
purple after a '>', the game's replies as they come. Ctrl+C closes it;
the game carries on either way. /zork watch opens this for you.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SAVES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "agent", "zork")
PATH = os.path.join(SAVES, "transcript.txt")

PURPLE, DIM, BOLD, RESET = "\033[38;5;183m", "\033[2m", "\033[1m", "\033[0m"


def show(line):
    if line.startswith("> "):
        sys.stdout.write(f"{PURPLE}{BOLD}{line}{RESET}")
    elif line.startswith(("[", "=====")):
        sys.stdout.write(f"{DIM}{line}{RESET}")
    else:
        sys.stdout.write(line)
    sys.stdout.flush()


def main():
    sys.stdout.write(f"\033]0;Luna plays Zork\007{DIM}Luna plays Zork - watching {PATH}\n"
                     f"Ctrl+C closes this window; the game keeps going.{RESET}\n\n")

    while not os.path.exists(PATH):
        time.sleep(1)

    with open(PATH, encoding="utf-8", errors="replace") as f:
        # The last part of what's already there, so you land mid-game.
        lines = f.readlines()
        for line in lines[-60:]:
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
