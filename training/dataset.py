"""The examples her patches are trained from (docs/patches.md).

A patch teaches her a habit by showing it to her: a few hundred replies
the way you want them, each with the prompt she was answering. Those
examples are what lasts - a patch fits one model, but the examples train
the next model just as well - so they're kept here, plainly, one JSON
line each in agent/dataset/examples.jsonl (personal: it holds her whole
prompt, your facts included, and is never committed).

Her last turn is held in memory only (note_turn, from llm/turns.py) until
you keep it with /good or correct it with /fix. Only your own turns are
offered: not a guest's or a stranger's, not stream chat or Discord, not a
job, and not a turn that called tools (tool calls train differently; later).

Each example:
    id, when, model, kind ("habit" | "gesture"), source ("good" | "fix" | ...),
    messages   the system prompt, the last few turns and your message, as she saw them
    reply      what she should have said
    original   what she did say, when it was corrected
    approved   True, False (dropped) or None (waiting to be looked at)
"""
import json
import os
import threading
import time
import uuid

from config import BASE_DIR

FOLDER = os.path.join(BASE_DIR, "agent", "dataset")
FILE = os.path.join(FOLDER, "examples.jsonl")
CONTEXT = 6          # turns of conversation kept before your message
KINDS = ("habit", "gesture")

_lock = threading.Lock()
_last = {}           # her last turn, until you keep it or the next one replaces it


def note_turn(system, context, user, reply, model="", used_tools=False):
    """Her finished turn, as she saw it. Called by every one of your own turns."""
    with _lock:
        _last.clear()
        _last.update(system=str(system or ""), context=[dict(m) for m in (context or [])][-CONTEXT:],
                     user=dict(user or {}), reply=str(reply or ""), model=str(model or ""),
                     used_tools=bool(used_tools), at=time.time())


def last():
    """A copy of her last turn, or {}."""
    with _lock:
        return json.loads(json.dumps(_last)) if _last else {}


def _messages(turn):
    """The conversation she answered, as chat messages (role and content only)."""
    out = [{"role": "system", "content": turn["system"]}]
    for m in turn["context"] + [turn["user"]]:
        content = m.get("content")
        if m.get("role") in ("user", "assistant") and isinstance(content, str) and content.strip():
            out.append({"role": m["role"], "content": content})
    return out


def keep(source="good", reply=None, kind="habit"):
    """Keep her last turn as an example: as it was (/good), or with the reply
    you'd rather she gave (/fix). Returns the example; ValueError says why not."""
    if kind not in KINDS:
        raise ValueError(f"no such kind {kind!r}")

    turn = last()

    if not turn:
        raise ValueError("there's no turn of hers to keep yet - talk to her first")
    if turn["used_tools"]:
        raise ValueError("that turn called tools; examples are plain replies for now")

    corrected = reply is not None and str(reply).strip() != turn["reply"].strip()

    # One example per reply: /good twice keeps it once, and /fix after /good
    # turns that same example into your version.
    if turn.get("kept"):
        if not corrected:
            raise ValueError("you already kept that one")
        update(turn["kept"], reply=reply, source="fix")
        return next((r for r in examples() if r.get("id") == turn["kept"]), None) or {}
    example = {
        "id": uuid.uuid4().hex[:12],
        "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": turn["model"],
        "kind": kind,
        "source": source,
        "messages": _messages(turn),
        "reply": str(reply).strip() if corrected else turn["reply"],
        "original": turn["reply"] if corrected else None,
        "approved": True,           # you chose it, so it's approved
    }

    with _lock:
        os.makedirs(FOLDER, exist_ok=True)
        with open(FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
        if _last.get("at") == turn["at"]:
            _last["kept"] = example["id"]

    return example


def _read():
    """Every row. Caller holds _lock."""
    try:
        with open(FILE, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


def examples(kind=None):
    """Every example, oldest first (optionally one kind)."""
    with _lock:
        rows = _read()
    return [r for r in rows if kind is None or r.get("kind") == kind]


def _rewrite(rows):
    """Caller holds _lock - from its read to here, so nothing kept meanwhile is lost."""
    os.makedirs(FOLDER, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, FILE)


def update(example_id, **changes):
    """Change one example (approved, reply, kind, source). False if there's no such id."""
    allowed = {k: v for k, v in changes.items() if k in ("approved", "reply", "kind", "source")}
    if "kind" in allowed and allowed["kind"] not in KINDS:
        raise ValueError(f"no such kind {allowed['kind']!r}")
    with _lock:
        rows = _read()
        for r in rows:
            if r.get("id") == example_id:
                if "reply" in allowed:
                    allowed["reply"] = str(allowed["reply"]).strip()
                    if allowed["reply"] != r["reply"]:
                        r["original"] = r.get("original") or r["reply"]
                r.update(allowed)
                _rewrite(rows)
                return True
    return False


def remove(example_id):
    """Delete an example for good. False if there's no such id."""
    with _lock:
        rows = _read()
        kept = [r for r in rows if r.get("id") != example_id]
        if len(kept) == len(rows):
            return False
        _rewrite(kept)
    return True


def counts():
    """{kind: {"approved": n, "waiting": n, "dropped": n}}"""
    out = {k: {"approved": 0, "waiting": 0, "dropped": 0} for k in KINDS}
    for r in examples():
        c = out.setdefault(r.get("kind", "habit"), {"approved": 0, "waiting": 0, "dropped": 0})
        c["approved" if r.get("approved") is True else "dropped" if r.get("approved") is False else "waiting"] += 1
    return out
