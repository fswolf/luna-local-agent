"""Build one control vector per concept, from your own model.

    python introspection/make_vectors.py              # all of them
    python introspection/make_vectors.py ocean fire   # just these

Stop Luna's llama-server first (Ctrl+C in its terminal) - this loads the
model itself. Each concept takes a minute or two on the GPU. Vectors go
in introspection/vectors/<concept>.gguf and are specific to this model:
change the model, build them again.

The method is "mean": the average difference between the layers with
the concept in mind and without it, layer by layer. It's the plainest
definition of "the concept, as this model holds it", which is the point
- the experiment should be injecting the concept, not an artefact of a
cleverer extraction.
"""
import os
import subprocess
import sys

import concepts
import lab


def build(name, model):
    pos, neg = concepts.pairs(name)
    pos_file = os.path.join(lab.VECTORS, f"{name}.positive.txt")
    neg_file = os.path.join(lab.VECTORS, f"{name}.negative.txt")
    out = os.path.join(lab.VECTORS, f"{name}.gguf")

    with open(pos_file, "w") as f:
        f.write("\n".join(pos) + "\n")

    with open(neg_file, "w") as f:
        f.write("\n".join(neg) + "\n")

    e = lab.env()
    cmd = [lab.binary("llama-cvector-generator"), "-m", model,
           "-ngl", e.get("NGL", "99"), "-t", e.get("THREADS", "8"),
           "--positive-file", pos_file, "--negative-file", neg_file,
           "--method", "mean", "-o", out]

    print(f"  {name}: building from {len(pos)} prompt pairs ...", flush=True)

    with open(os.path.join(lab.RESULTS, "make_vectors.log"), "a") as log:
        done = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)

    if done.returncode != 0 or not os.path.exists(out):
        print(f"  {name}: FAILED - see introspection/results/make_vectors.log")

        return False

    print(f"  {name}: {out}")

    return True


def main():
    wanted = sys.argv[1:] or list(concepts.CONCEPTS)
    unknown = [w for w in wanted if w not in concepts.CONCEPTS]

    if unknown:
        sys.exit(f"unknown concept(s): {', '.join(unknown)} - "
                 f"choose from {', '.join(concepts.CONCEPTS)}")

    if lab.luna_server_up():
        sys.exit("Luna's llama-server is running on :8080 - stop it first "
                 "(Ctrl+C in its terminal); the GPU only holds one copy.")

    model = lab.model_path()
    print(f"model: {os.path.basename(model)} ({lab.n_layers(model)} layers)")
    ok = [build(name, model) for name in wanted]
    print(f"\n{sum(ok)} of {len(ok)} built. Next: python introspection/trial.py")


if __name__ == "__main__":
    main()
