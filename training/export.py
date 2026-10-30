"""Approved examples -> the trainer's files (docs/patches.md).

    python3 -m training.export gesture      (or habit)

Writes agent/dataset/export/<kind>-train.jsonl and <kind>-test.jsonl, one
conversation per line: {"messages": [system, ..., user, assistant]}, the
last message being the reply she should give. Only approved examples.

About one in ten is held back as the test set and never trained on. Which
ones is fixed by each example's id, so an example stays on the same side
every time you export, however many more you collect.
"""
import hashlib
import json
import os
import sys

from training import dataset

OUT = os.path.join(dataset.FOLDER, "export")
TEST_SHARE = 10          # one in ten held back
ENOUGH = 300             # a first patch wants 300 to 500


def held_back(example_id):
    return int(hashlib.sha1(str(example_id).encode()).hexdigest(), 16) % TEST_SHARE == 0


def conversation(example):
    """The chat she answered, with the reply she should have given last."""
    msgs = [{"role": m["role"], "content": m["content"]} for m in example.get("messages") or []
            if m.get("role") in ("system", "user", "assistant") and isinstance(m.get("content"), str)]
    if not msgs or msgs[-1]["role"] != "user" or not str(example.get("reply") or "").strip():
        return None
    return {"messages": msgs + [{"role": "assistant", "content": example["reply"].strip()}]}


def export(kind, folder=OUT):
    """(train count, test count, paths). ValueError for an unknown kind."""
    if kind not in dataset.KINDS:
        raise ValueError(f"no such kind {kind!r} - {', '.join(dataset.KINDS)}")
    train, test = [], []
    for ex in dataset.examples(kind):
        if ex.get("approved") is not True:
            continue
        conv = conversation(ex)
        if conv:
            (test if held_back(ex.get("id")) else train).append(conv)
    os.makedirs(folder, exist_ok=True)
    paths = {}
    for name, rows in (("train", train), ("test", test)):
        paths[name] = os.path.join(folder, f"{kind}-{name}.jsonl")
        with open(paths[name], "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(train), len(test), paths


def main(argv):
    if len(argv) != 1:
        print("usage: python3 -m training.export gesture|habit", file=sys.stderr)
        return 2
    try:
        n_train, n_test, paths = export(argv[0])
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    print(f"{argv[0]}: {n_train} to train on, {n_test} held back for testing")
    print(f"  {paths['train']}\n  {paths['test']}")
    if n_train == 0:
        print("Nothing approved to train on yet (/good, /fix, the examples page).", file=sys.stderr)
        return 1
    with open(paths["train"], encoding="utf-8") as f:
        longest = max((len(line) for line in f), default=0)
    print(f"  longest about {longest // 3:,} tokens (MAX_LEN in training/train.env leaves out longer ones)")
    if n_train < ENOUGH:
        print(f"  (a first patch wants {ENOUGH} to 500; fewer works as a trial run)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
