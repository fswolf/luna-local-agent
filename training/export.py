"""Approved examples -> the trainer's files (docs/patches.md).

    python3 -m training.export gesture      (or habit)

Writes agent/dataset/export/<kind>-train.jsonl and <kind>-test.jsonl, one
conversation per line: {"messages": [system, ..., user, assistant]}, the
last message being the reply she should give. Only approved examples.

A tool turn has its calls between your message and her answer, the way
the server sent them to her: an assistant message with tool_calls, a tool
message per result. Its line also carries "tools", the definitions she was
offered, so the chat template writes them into her prompt as it did then.

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


def _arguments(raw):
    """A call's arguments as an object: chat templates differ on strings,
    and Qwen's XML form walks them key by key."""
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def _steps(rounds):
    """A tool turn's rounds as chat messages, or None if they don't pair up."""
    out, open_ids = [], []          # the calls still waiting for their result, in order
    for m in rounds or ():
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = []
            for i, c in enumerate(m["tool_calls"]):
                f = c.get("function") or {}
                if not f.get("name"):
                    return None
                calls.append({"id": c.get("id") or f"call_{len(out)}_{i}", "type": "function",
                              "function": {"name": f["name"], "arguments": _arguments(f.get("arguments"))}})
            out.append({"role": "assistant", "content": str(m.get("content") or ""), "tool_calls": calls})
            open_ids = [c["id"] for c in calls]
        elif m.get("role") == "tool" and open_ids:
            given = m.get("tool_call_id")
            tid = given if given in open_ids else open_ids[0]
            open_ids.remove(tid)
            out.append({"role": "tool", "tool_call_id": tid,
                        "name": str(m.get("name") or ""), "content": str(m.get("content") or "")})
        else:
            return None
    return out if out and out[-1]["role"] == "tool" and not open_ids else None


def conversation(example):
    """The chat she answered, with the reply she should have given last
    (and a tool turn's calls and results before it)."""
    msgs = [{"role": m["role"], "content": m["content"]} for m in example.get("messages") or []
            if m.get("role") in ("system", "user", "assistant") and isinstance(m.get("content"), str)]
    if not msgs or msgs[-1]["role"] != "user" or not str(example.get("reply") or "").strip():
        return None
    out = {}
    if example.get("rounds"):
        steps = _steps(example["rounds"])
        if steps is None:
            return None
        msgs += steps
        if example.get("tools"):
            out["tools"] = example["tools"]
    out["messages"] = msgs + [{"role": "assistant", "content": example["reply"].strip()}]
    return out


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
