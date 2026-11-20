"""The examples her patches are trained from (docs/patches.md).

A patch teaches her a habit by showing it to her: a few hundred replies
the way you want them, each with the prompt she was answering. Those
examples are what lasts - a patch fits one model, but the examples train
the next model just as well - so they're kept here, plainly, one JSON
line each in agent/dataset/examples.jsonl (personal: it holds her whole
prompt, your facts included, and is never committed).

Her last turn is held in memory only (note_turn, from llm/turns.py) until
you keep it with /good or correct it with /fix. The last RECENT turns are
held too, by their reply as it shows on screen, so the chat page's
thumbs can keep any of them: up is /good, down with your version is /fix,
and down alone records the reply as a bad one (approved False, so it's
never trained on as it is; kept for training from good-and-bad pairs later). Only your own turns are
offered: not a guest's or a stranger's, not stream chat or Discord, not a
job, and not a turn that called tools (tool calls train differently; later).

Each example:
    id, when, model, kind ("habit" | "gesture"), source ("good" | "fix" | ...),
    messages   the system prompt, the last few turns and your message, as she saw them
    reply      what she should have said
    original   what she did say, when it was corrected
    approved   True, False (dropped) or None (waiting to be looked at)
    rated      "up" | "down", from the chat page's thumbs
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
RECENT = 40          # turns the chat page's thumbs can still reach

_lock = threading.Lock()
_last = {}           # her last turn, until you keep it or the next one replaces it
_recent = {}         # (conversation epoch, her reply as shown) -> turn, the last RECENT
_rated = {}          # the same key -> "up" | "fix" | "down", for the page


def _ui_ref():
    """(epoch, her reply as it shows in the conversation), or None. By its text,
    not its place: a line added above an open reply moves it down one."""
    try:
        import config
        import ui
        from ui.shared import _lock as ui_lock

        with ui_lock:
            at = ui.view.streaming
            if at is None:
                me = config.AGENT_NAME.lower()
                at = next((i for i in range(len(ui.conversation) - 1, -1, -1)
                           if ui.conversation[i][0] == me), None)
            if at is None or not 0 <= at < len(ui.conversation):
                return None
            shown = str(ui.conversation[at][1]).strip()
            return (ui.view.epoch, shown) if shown else None
    except Exception:
        return None


def kind_of(reply):
    """gesture when the reply has a gesture tag ([hug]) in it, else habit."""
    try:
        from life import gestures

        if "[" in reply and gestures._tag().search(reply):
            return "gesture"
    except Exception:
        pass
    return "habit"


def note_turn(system, context, user, reply, model="", used_tools=False):
    """Her finished turn, as she saw it. Called by every one of your own turns."""
    ref = _ui_ref()
    with _lock:
        _last.clear()
        _last.update(system=str(system or ""), context=[dict(m) for m in (context or [])][-CONTEXT:],
                     user=dict(user or {}), reply=str(reply or ""), model=str(model or ""),
                     used_tools=bool(used_tools), at=time.time())
        if ref is not None:
            _recent.pop(ref, None)                  # (the same words again: the newest wins)
            _recent[ref] = _last.copy()
            for k in list(_recent)[:-RECENT]:
                _recent.pop(k, None)
                _rated.pop(k, None)


def last():
    """A copy of her last turn, or {}."""
    with _lock:
        return json.loads(json.dumps(_last)) if _last else {}


def _me():
    try:
        import config

        return config.AGENT_NAME.lower()
    except Exception:
        return "luna"


def rateable(epoch, conversation):
    """{index: "" | "up" | "fix" | "down" | "tools"} for her replies in
    conversation (the [speaker, text] list on screen) that the thumbs know:
    your own turns from this conversation, "tools" for one where she used a
    tool (not keepable yet). A reply that isn't here is from before Luna
    started, or not a turn of yours."""
    me = _me()
    out = {}
    with _lock:
        for i, (who, text) in enumerate(conversation):
            key = (epoch, str(text).strip())
            if who == me and key in _recent:
                out[i] = "tools" if _recent[key].get("used_tools") else _rated.get(key, "")
    return out


def rate(epoch, shown, up, better=None):
    """The chat page's thumbs on her reply (as it shows on screen): up keeps
    it as it is, down with your version keeps that, down alone keeps it as a
    bad reply. Returns the example; ValueError says why not."""
    key = (int(epoch), str(shown or "").strip())
    with _lock:
        turn = _recent.get(key)
        turn = json.loads(json.dumps(turn)) if turn and not turn.get("used_tools") else None
    if turn is None:
        raise ValueError("that reply is too old to keep, or wasn't one of your own turns")
    better = str(better).strip() if better else ""
    mark = "up" if up else "fix" if better else "down"
    if not better and _rated.get(key) == mark:                               # a second click: nothing new
        return next((r for r in examples() if r.get("id") == turn.get("kept")), None) or {"kind": kind_of(turn["reply"])}
    if up:
        ex = keep("good", turn=turn, kind=kind_of(turn["reply"]))
    elif better:
        ex = keep("fix", reply=better, turn=turn, kind=kind_of(better))
    else:
        ex = keep("bad", turn=turn, kind=kind_of(turn["reply"]))
    with _lock:
        _rated[key] = mark
        if key in _recent:
            _recent[key]["kept"] = ex.get("id")
    if ex.get("id"):
        update(ex["id"], rated="up" if up else "down")
    ex["mark"] = mark
    return ex


def _messages(turn):
    """The conversation she answered, as chat messages (role and content only)."""
    out = [{"role": "system", "content": turn["system"]}]
    for m in turn["context"] + [turn["user"]]:
        content = m.get("content")
        if m.get("role") in ("user", "assistant") and isinstance(content, str) and content.strip():
            out.append({"role": m["role"], "content": content})
    return out


def keep(source="good", reply=None, kind="habit", turn=None):
    """Keep her last turn (or the one given) as an example: as it was (/good),
    with the reply you'd rather she gave (/fix), or as a bad one ("bad": the
    thumbs down with nothing typed). Returns the example; ValueError says why not."""
    if kind not in KINDS:
        raise ValueError(f"no such kind {kind!r}")

    turn = turn or last()

    if not turn:
        raise ValueError("there's no turn of hers to keep yet - talk to her first")
    if turn["used_tools"]:
        raise ValueError("that turn called tools; examples are plain replies for now")

    corrected = reply is not None and str(reply).strip() != turn["reply"].strip()

    # One example per reply: /good twice keeps it once, and /fix after /good
    # turns that same example into your version.
    bad = source == "bad"
    if turn.get("kept"):
        if bad:
            update(turn["kept"], approved=False, source="bad", rated="down")
        elif corrected:
            update(turn["kept"], reply=reply, source="fix", approved=True)
        elif source == "good" and next((r for r in examples() if r.get("id") == turn["kept"]),
                                       {}).get("approved") is False:
            update(turn["kept"], approved=True, source="good", rated="up")   # a thumbs down changed to up
        else:
            raise ValueError("you already kept that one")
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
        "approved": not bad,        # you chose it, so it's approved; a bad one never trains as it is
    }

    with _lock:
        os.makedirs(FOLDER, exist_ok=True)
        with open(FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
        if _last.get("at") == turn["at"]:
            _last["kept"] = example["id"]
        for t in _recent.values():
            if t.get("at") == turn["at"]:
                t["kept"] = example["id"]

    return example


def _read():
    """Every row. Caller holds _lock.

    A line that isn't an example (cut short by a crash mid-write, a typo
    from editing it by hand) comes back as its own text: it's skipped by
    everything that reads examples, said once in the log, and written back
    as it was by _rewrite, so one bad line neither hides every other
    example nor gets thrown away before you can look at it."""
    rows, bad = [], 0
    try:
        with open(FILE, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    row = None
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    rows.append(line.rstrip("\n"))
                    bad += 1
    except FileNotFoundError:
        return []
    if bad:
        try:
            from core import logbook

            logbook.warn("dataset", "%d line(s) of %s aren't examples: skipped, and kept as they are", bad, FILE)
        except Exception:
            pass
    return rows


def examples(kind=None):
    """Every example, oldest first (optionally one kind)."""
    with _lock:
        rows = _read()
    return [r for r in rows if isinstance(r, dict) and (kind is None or r.get("kind") == kind)]


def _rewrite(rows):
    """Caller holds _lock - from its read to here, so nothing kept meanwhile is lost."""
    os.makedirs(FOLDER, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write((r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)) + "\n")
    os.replace(tmp, FILE)


def update(example_id, **changes):
    """Change one example (approved, reply, kind, source). False if there's no such id."""
    allowed = {k: v for k, v in changes.items() if k in ("approved", "reply", "kind", "source", "rated")}
    if "kind" in allowed and allowed["kind"] not in KINDS:
        raise ValueError(f"no such kind {allowed['kind']!r}")
    with _lock:
        rows = _read()
        for r in rows:
            if isinstance(r, dict) and r.get("id") == example_id:
                if "reply" in allowed:
                    allowed["reply"] = str(allowed["reply"]).strip()
                    if allowed["reply"] != r.get("reply"):
                        r["original"] = r.get("original") or r.get("reply")
                r.update(allowed)
                _rewrite(rows)
                return True
    return False


def remove(example_id):
    """Delete an example for good. False if there's no such id."""
    with _lock:
        rows = _read()
        kept = [r for r in rows if not (isinstance(r, dict) and r.get("id") == example_id)]
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
