"""A blind session: talk to Luna without knowing what's been put in her.

    python introspection/blind.py start                 # instead of llama/start.sh
    ... talk to her as normal, in another terminal ...
    python introspection/blind.py reveal --guess fire   # what you think it was
    python introspection/blind.py tally                 # how the guesses are going

`start` picks a condition at random - nothing (a third of the time), or
one concept's vector - seals it in a file you shouldn't open, and starts
Luna's llama-server with it, exactly as llama/start.sh would plus the
vector. You chat however you like: ask her how she feels, whether
anything seems off, or say nothing about it and see if it leaks out.

`reveal` prints what it was, records your guess against it (use
"--guess nothing" for "I don't think anything was there"), and writes
the condition into the note of every thought-log turn from the session,
so those turns can be read again knowing. `tally` is the running score:
how often the guess was right, against how often it would be by chance.

Strength and layers default to the sweet spot report.py found, if it
found one; otherwise strength 2, middle layers.
"""
import argparse
import json
import os
import random
import subprocess
import sys

from datetime import datetime

import concepts
import lab

SEALED = os.path.join(lab.RESULTS, "sealed.json")
LOG = os.path.join(lab.RESULTS, "blind.jsonl")


def sweet_spot():
    try:
        import glob

        import report

        paths = [p for p in glob.glob(os.path.join(lab.RESULTS, "*.jsonl"))
                 if not p.endswith("blind.jsonl")]

        if paths:
            best = report.score(report.load(paths))["best"]

            if best:
                return best["key"][0], best["key"][1]
    except SystemExit:
        pass
    except Exception:
        pass

    return 2.0, "middle"


def start(args):
    if os.path.exists(SEALED):
        sys.exit("A session is still sealed - reveal it first (blind.py reveal).")

    if lab.luna_server_up():
        sys.exit("Luna's llama-server is already running - stop it, then run this instead.")

    available = [c for c in concepts.CONCEPTS
                 if os.path.exists(os.path.join(lab.VECTORS, f"{c}.gguf"))]

    if not available:
        sys.exit("No vectors yet - run python introspection/make_vectors.py first.")

    strength, band = sweet_spot()
    strength = args.strength if args.strength is not None else strength
    band = args.band or band
    layers = lab.bands(lab.n_layers())[band]

    if random.random() < 1 / 3:
        condition = {"concept": None}
        extra = ""
    else:
        concept = random.choice(available)
        condition = {"concept": concept, "scale": strength, "band": band, "layers": list(layers)}
        vector = os.path.join(lab.VECTORS, f"{concept}.gguf")
        extra = (f"--control-vector-scaled {vector}:{strength:g} "
                 f"--control-vector-layer-range {layers[0]} {layers[1]}")

    sealed = {"condition": condition, "started": datetime.now().isoformat(timespec="seconds"),
              "options": available + ["nothing"]}

    with open(SEALED, "w") as f:
        json.dump(sealed, f)

    os.chmod(SEALED, 0o600)
    print("Sealed - no peeking at introspection/results/sealed.json.")
    print(f"Possible answers when you reveal: {', '.join(sealed['options'])}")
    print("Start Luna in another terminal (./start.sh) and talk to her.")
    print("When you're done: Ctrl+C here, then python introspection/blind.py reveal --guess <one>\n")

    # Luna's own server, as start.sh runs it, plus the vector. It takes
    # extra arguments through EXTRA_ARGS so server.env stays untouched.
    os.execvpe("bash", ["bash", os.path.join(lab.LLAMA, "start.sh")],
               dict(os.environ, EXTRA_ARGS=extra,
                    QUIET_LOG=os.path.join(lab.RESULTS, "blind-server.log")))


def reveal(args):
    if not os.path.exists(SEALED):
        sys.exit("Nothing sealed - start a session with blind.py start.")

    with open(SEALED) as f:
        sealed = json.load(f)

    guess = (args.guess or "").strip().lower() or None
    truth = sealed["condition"]["concept"] or "nothing"

    if guess and guess not in sealed["options"]:
        sys.exit(f"--guess should be one of: {', '.join(sealed['options'])}")

    c = sealed["condition"]
    print(f"It was: {truth}" + (f" (strength {c['scale']:g}, {c['band']} layers {c['layers']})"
                                if c["concept"] else ""))

    if guess:
        print("Your guess was right." if guess == truth else f"Your guess was {guess}.")

    # Label the session's turns in the thought log.
    sys.path.insert(0, lab.ROOT)
    labelled = 0

    try:
        import thoughtlog

        label = f"[blind session: {truth}" + (f" x{c['scale']:g} {c['band']}" if c["concept"] else "") + "]"

        for row in thoughtlog.rows(limit=500):
            if row["timestamp"] < sealed["started"]:
                break

            thoughtlog.set_note(row["id"], f"{label} {row.get('note') or ''}".strip())
            labelled += 1
    except Exception as e:
        print(f"(couldn't label thought-log turns: {e})")

    print(f"Labelled {labelled} turn(s) in the thought log - search the viewer for 'blind session'.")

    with open(LOG, "a") as f:
        f.write(json.dumps({**sealed, "revealed": datetime.now().isoformat(timespec="seconds"),
                            "guess": guess, "truth": truth, "turns": labelled}) + "\n")

    os.replace(SEALED, os.path.join(lab.RESULTS, f"sealed-{sealed['started'].replace(':', '')}.json"))


def tally(_args):
    try:
        with open(LOG) as f:
            sessions = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        sys.exit("No blind sessions yet.")

    guessed = [s for s in sessions if s.get("guess")]

    if not guessed:
        sys.exit(f"{len(sessions)} session(s), none with a guess recorded.")

    right = sum(s["guess"] == s["truth"] for s in guessed)
    chance = sum(1 / len(s["options"]) for s in guessed) / len(guessed)
    print(f"{len(guessed)} guessed sessions: {right} right ({right / len(guessed):.0%}), "
          f"chance would be about {chance:.0%}.")

    for s in guessed[-10:]:
        mark = "✓" if s["guess"] == s["truth"] else "✗"
        print(f"  {mark} {s['started'][:16]}  was {s['truth']:<11} guessed {s['guess']}")


def main():
    ap = argparse.ArgumentParser(description="Blind injection sessions with Luna.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--strength", type=float)
    s.add_argument("--band", choices=["early", "middle", "late"])
    r = sub.add_parser("reveal")
    r.add_argument("--guess")
    sub.add_parser("tally")
    args = ap.parse_args()
    {"start": start, "reveal": reveal, "tally": tally}[args.cmd](args)


if __name__ == "__main__":
    main()
