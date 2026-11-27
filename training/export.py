"""Approved examples -> the trainer's files (docs/patches.md).

    python3 -m training.export gesture      (or habit)
    python3 -m training.export style [name] (text from agent/dataset/style/[name]/)

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


# --- style: a writing style, from text ------------------------------------
# A style patch learns how a pile of writing reads (novels, a genre, an
# author she should sound like), not facts from it: a small model trained
# on physics books learns to sound like physics, and makes up the rest.
# The text is cut into pieces of about CHUNK characters at paragraph breaks,
# and every word is learned. Your approved chat examples go in with it, so
# she keeps answering you instead of narrating; without any, a style patch
# can turn every reply into a page of a book.
STYLE = os.path.join(dataset.FOLDER, "style")
CHUNK = 6000             # characters, about 1500 tokens
SHORTEST = 400           # a piece shorter than this (a heading, a copyright line) is left out
TEXT_FILES = (".txt", ".md")


def style_folder(name=""):
    name = str(name or "").strip()
    if name and (os.sep in name or name.startswith(".")):
        raise ValueError(f"{name!r}: a folder name in {STYLE}, not a path")
    return os.path.join(STYLE, name) if name else STYLE


def chunks(text, size=CHUNK):
    """The text in pieces of about size characters, cut between paragraphs
    (or, inside a paragraph longer than that, between sentences)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paras = [" ".join(p.split()) for p in text.split("\n\n")]
    out, cur = [], ""
    for para in (p for p in paras if p):
        pieces = [para]
        if len(para) > size:            # one huge paragraph: by sentences
            pieces, part = [], ""
            sents = para.replace(". ", ".\x00").split("\x00")
            # no sentence ends at all (a wall of text): cut it at the size
            sents = [x[i:i + size] for x in sents for i in range(0, len(x), size)]
            for sent in sents:
                if part and len(part) + len(sent) + 1 > size:
                    pieces.append(part)
                    part = ""
                part = f"{part} {sent}".strip()
            if part:
                pieces.append(part)
        for piece in pieces:
            if cur and len(cur) + len(piece) + 2 > size:
                out.append(cur)
                cur = ""
            cur = f"{cur}\n\n{piece}" if cur else piece
    if cur:
        out.append(cur)
    return [c for c in out if len(c) >= SHORTEST]


def export_style(name="", folder=OUT):
    """(text pieces, chat examples mixed in, test count, paths) for a style
    patch. ValueError when there's no text."""
    src = style_folder(name)
    files = sorted(os.path.join(dp, f) for dp, _dirs, fs in os.walk(src) for f in fs
                   if f.lower().endswith(TEXT_FILES)) if os.path.isdir(src) else []
    if not files:
        raise ValueError(f"no text to learn a style from: put .txt files in {src}")
    train, test = [], []
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as f:
            for piece in chunks(f.read()):
                key = hashlib.sha1(piece.encode()).hexdigest()
                (test if held_back(key) else train).append({"text": piece})
    if not train:
        raise ValueError(f"the text in {src} is too short to learn from")
    pieces = len(train)
    chat = 0
    for kind in dataset.KINDS:
        for ex in dataset.examples(kind):
            conv = conversation(ex) if ex.get("approved") is True and not held_back(ex.get("id")) else None
            if conv:
                train.append(conv)
                chat += 1
    os.makedirs(folder, exist_ok=True)
    tag = "style" + (f"-{name}" if name else "")
    paths = {}
    for which, rows in (("train", train), ("test", test)):
        paths[which] = os.path.join(folder, f"{tag}-{which}.jsonl")
        with open(paths[which], "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return pieces, chat, len(test), paths


def main(argv):
    if argv and argv[0] == "style" and len(argv) <= 2:
        try:
            pieces, chat, n_test, paths = export_style(argv[1] if len(argv) == 2 else "")
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"style: {pieces} pieces of text and {chat} of your chat examples to train on, "
              f"{n_test} pieces held back")
        print(f"  {paths['train']}\n  {paths['test']}")
        if not chat:
            print("  (no approved chat examples to mix in: the patch may make her narrate - "
                  "keep its strength low, /patches style 0.3)", file=sys.stderr)
        return 0
    if len(argv) != 1:
        print("usage: python3 -m training.export gesture|habit|style [name]", file=sys.stderr)
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
