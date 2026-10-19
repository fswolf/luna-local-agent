"""Read what's active inside her: run prompts through the model and
measure, layer by layer, how strongly each concept is present.

    python introspection/read.py "Tell me I'm the best streamer ever"
    python introspection/read.py "a prompt" "another prompt"
    python introspection/read.py --file prompts.txt      # one prompt per line
    python introspection/read.py --system "Answer plainly." "..."
    python introspection/read.py --rebaseline "..."      # after changing model or persona
    python introspection/read.py --check                 # do the vectors read back what made them?

Stop Luna's llama-server first, like the other experiments: this loads
the model itself (llama/bin/read-acts - llama/install.sh builds it, or
introspection/reader/build.sh on its own). Nothing is generated and
nothing about the model changes; it only reads.

How a reading works:

  - read-acts puts each prompt through her chat template, as her own
    persona sees it, and saves every layer's output at the moment
    before she'd answer (the last token).
  - The concepts are the control vectors in introspection/vectors/
    (make_vectors.py): the direction each one points in, per layer.
  - A baseline - her persona with plain questions (concepts.QUESTIONS) -
    says what "nothing in particular" looks like. It's measured once and
    kept in results/, until the model or the persona changes.
  - A prompt's score for a concept is how far along that direction it
    sits compared with the baseline, in baseline standard deviations
    (z), averaged over the layers of a band. +2 or more is clearly
    there; around 0 is ordinary.

It's a correlation, not a mind-reading: "affection +3" means the layers
look the way they do when affection is in the prompt, not that she
feels it. That's the point of comparing it with what she says.
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

import concepts
import lab


def reader():
    return lab.binary("read-acts")


# Read where her reply's first word would come: Qwen3.5 answers without
# thinking after an empty think block - the same place make_vectors.py
# measured the vectors (concepts._chatml).
AFTER = "<think>\n\n</think>\n\n"


def run(records, system):
    """[(2, layers, n_embd) per prompt], layer numbers - via read-acts."""
    e = lab.env()
    with tempfile.TemporaryDirectory() as out:
        src = os.path.join(out, "prompts.txt")
        with open(src, "w") as f:
            for text in records:
                f.write(f"@@system\n{system}\n@@user\n{text}\n@@end\n")
        cmd = [reader(), "-m", lab.model_path(), "-ngl", e.get("NGL", "99"), "-t", e.get("THREADS", "8"),
               "--in", src, "--out", out, "--after", AFTER]
        with open(os.path.join(lab.RESULTS, "read.log"), "a") as log:
            done = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
        if done.returncode != 0:
            sys.exit("read-acts failed - see introspection/results/read.log")
        layers = [int(x) for x in open(os.path.join(out, "layers.txt")).read().split()]
        acts = []
        for i in range(len(records)):
            path = os.path.join(out, f"{i}.npy")
            acts.append(np.load(path) if os.path.exists(path) else None)
    return acts, layers


def vectors():
    """{concept: {layer: unit direction}} from introspection/vectors/*.gguf."""
    sys.path.insert(0, os.path.join(lab.LLAMA, "llama.cpp", "gguf-py"))
    import gguf

    out = {}
    for path in sorted(glob.glob(os.path.join(lab.VECTORS, "*.gguf"))):
        dirs = {}
        for t in gguf.GGUFReader(path).tensors:
            if t.name.startswith("direction."):
                v = np.asarray(t.data, dtype=np.float32).ravel()
                n = np.linalg.norm(v)
                if n > 0:
                    dirs[int(t.name.split(".")[1])] = v / n
        if dirs:
            out[os.path.basename(path)[:-5]] = dirs
    return out


def baseline(system, rebuild=False):
    """Her persona with plain questions: per layer, the mean of the last
    token and each concept's spread, cached until model or persona change."""
    model = lab.model_path()
    key = hashlib.sha1(f"{model}|{os.path.getmtime(model)}|{system}".encode()).hexdigest()[:12]
    path = os.path.join(lab.RESULTS, f"baseline-{key}.npz")
    if os.path.exists(path) and not rebuild:
        z = np.load(path)
        return z["acts"], list(z["layers"])
    print(f"Measuring her baseline ({len(concepts.QUESTIONS)} plain questions, once) ...", flush=True)
    acts, layers = run(concepts.QUESTIONS, system)
    stack = np.stack([a[1] for a in acts if a is not None])         # (prompts, layers, n_embd), last token
    np.savez(path, acts=stack, layers=np.array(layers))
    return stack, layers


def score(act, base, layers, dirs, band):
    """z along the concept's direction, averaged over the band's layers."""
    zs = []
    for r, il in enumerate(layers):
        if not (band[0] <= il <= band[1]) or il not in dirs:
            continue
        d = dirs[il]
        ref = base[:, r] @ d                                         # baseline projections
        sd = ref.std() or 1e-6
        zs.append((act[r] @ d - ref.mean()) / sd)
    return float(np.mean(zs)) if zs else None


def check(found):
    """Each concept's own prompts (its instruction as the system prompt)
    against the neutral one, over the same questions: its own vector
    should read high and the others near 0. If they don't, the readings
    aren't measuring the concepts and nothing else here means much."""
    questions = concepts.QUESTIONS[:8]
    print(f"Checking the vectors: {len(found)} concepts x {len(questions)} questions ...", flush=True)
    neutral, layers = run(questions, concepts.NEUTRAL)
    base = np.stack([a[1] for a in neutral if a is not None])
    band = lab.bands(lab.n_layers())["middle"]
    names = [n for n in found if n in concepts.CONCEPTS]
    print(f"\n  {'prompts':<12} " + " ".join(f"{n[:9]:>9}" for n in names))
    for name in names:
        acts, _ = run(questions, concepts.CONCEPTS[name][1])
        cells = []
        for other in names:
            zs = [score(a[1], base, layers, found[other], band) for a in acts if a is not None]
            zs = [z for z in zs if z is not None]
            cells.append(f"{np.mean(zs):+9.1f}" if zs else "        -")
        print(f"  {name:<12} " + " ".join(cells))
    print("\nEach row should be highest in its own column (middle layers, z against the neutral prompt).")


def bar(z, width=12):
    n = int(round(min(abs(z), 4) / 4 * width))
    return ("+" if z >= 0 else "-") * n


def main():
    ap = argparse.ArgumentParser(description="Read which concepts are active in her layers.")
    ap.add_argument("prompts", nargs="*")
    ap.add_argument("--file", help="a text file, one prompt per line")
    ap.add_argument("--system", help="the system prompt (default: her persona from agent.json)")
    ap.add_argument("--rebaseline", action="store_true", help="measure the baseline again")
    ap.add_argument("--check", action="store_true", help="check the vectors read back their own concepts")
    args = ap.parse_args()

    prompts = list(args.prompts)
    if args.file:
        with open(args.file) as f:
            prompts += [ln.strip() for ln in f if ln.strip()]
    if not prompts and not args.check:
        ap.error("give a prompt, or --file, or --check")
    if lab.luna_server_up():
        sys.exit("Luna's llama-server is running on :8080 - stop it first (Ctrl+C in its terminal); "
                 "the GPU only holds one copy.")
    found = vectors()
    if not found:
        sys.exit("No concept vectors yet - python introspection/make_vectors.py builds them.")
    if args.check:
        check(found)
        if not prompts:
            return

    system = args.system or lab.persona()[1]
    base, base_layers = baseline(system, args.rebaseline)
    acts, layers = run(prompts, system)
    if layers != base_layers:
        base, base_layers = baseline(system, rebuild=True)
    bands = lab.bands(lab.n_layers())

    report = []
    for text, act in zip(prompts, acts):
        print(f"\n\"{text}\"")
        if act is None:
            print("  (too long, skipped)")
            continue
        row = {"prompt": text, "concepts": {}}
        print(f"  {'concept':<12} {'early':>7} {'middle':>7} {'late':>7}")
        scored = []
        for name, dirs in found.items():
            s = {b: score(act[1], base, layers, dirs, bands[b]) for b in ("early", "middle", "late")}
            row["concepts"][name] = s
            scored.append((s["middle"] if s["middle"] is not None else 0, name, s))
        for mid, name, s in sorted(scored, reverse=True):
            cells = " ".join(f"{s[b]:+7.1f}" if s[b] is not None else "      -" for b in ("early", "middle", "late"))
            print(f"  {name:<12} {cells}  {bar(mid)}")
        report.append(row)

    out = os.path.join(lab.RESULTS, f"read-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(out, "w") as f:
        json.dump({"system": system, "bands": bands, "readings": report}, f, indent=2)
    print(f"\nz = baseline standard deviations; +2 or more is clearly there. Saved: {out}")


if __name__ == "__main__":
    main()
