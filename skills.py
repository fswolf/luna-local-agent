"""Luna's skill library: recipes for jobs she's done well before.

A small model is bad at planning a multi-step job from nothing and good
at following a worked example. So when she finishes something that took
several steps and it went right - checked the voice server, backed up a
folder, set up a reminder chain - the steps get written down as a named
recipe, and the next time something similar comes up the recipe rides
in her prompt:

    Recipes you've saved for jobs like this:
    #3 check whether the voice server is up (when: "is kokoro running")
      1. run_command: curl -s http://127.0.0.1:8899/health
      2. if nothing answers, run_command: tail -20 ~/.cache/ai-voice/kokoro.log
      3. tell him which it is, and the last error line if there is one

She saves one with the save_skill tool (you approve it on screen, like a
lesson), or you ask her to ("remember how you did that"). /skills lists
them, /skills show <n> prints one, /skills forget <n> hides one.

agent/skills.db, gitignored. Like lessons, nothing is deleted: a
forgotten skill is retired and /skills restore <n> brings it back.

Recall is strict on purpose. Lessons are short and all of them travel
while there are few; a recipe is a paragraph, so one only comes along
when it clearly fits what was just said.
"""
import json
import os
import re
import sqlite3
import threading

from datetime import datetime

import config
import logbook

DB_FILE = os.path.join(config.BASE_DIR, "agent", "skills.db")

MAX_STEPS = 12
MAX_STEP_CHARS = 300
MAX_NAME_CHARS = 80
MAX_WHEN_CHARS = 200

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id        INTEGER PRIMARY KEY,
    created   TEXT NOT NULL,
    name      TEXT NOT NULL,
    use_when  TEXT NOT NULL,
    steps     TEXT NOT NULL,           -- JSON list of strings
    tools     TEXT NOT NULL DEFAULT '[]',
    uses      INTEGER NOT NULL DEFAULT 0,
    last_used TEXT,
    retired   TEXT
);
"""


def _run(fn, default=None):
    with _lock:
        try:
            os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
            conn = sqlite3.connect(DB_FILE, timeout=10)

            try:
                conn.executescript(_SCHEMA)
                out = fn(conn)
                conn.commit()
                return out
            finally:
                conn.close()
        except sqlite3.Error as e:
            logbook.warn("skills", "db error: %s", e)
            return default


def _now():
    return datetime.now().isoformat(timespec="seconds")


def enabled():
    return bool(getattr(config, "SELF_SKILLS", True))


# ---------------------------------------------------------------------------
# Reading and writing
# ---------------------------------------------------------------------------
def _row(r):
    return {"id": r[0], "created": r[1], "name": r[2], "when": r[3],
            "steps": json.loads(r[4] or "[]"), "tools": json.loads(r[5] or "[]"),
            "uses": r[6], "last_used": r[7], "retired": r[8]}


def skills(retired=False):
    where = "IS NOT NULL" if retired else "IS NULL"
    rows = _run(lambda c: c.execute(
        "SELECT id, created, name, use_when, steps, tools, uses, last_used, retired "
        f"FROM skills WHERE retired {where} ORDER BY id").fetchall(), [])
    return [_row(r) for r in rows]


def get(skill_id):
    rows = _run(lambda c: c.execute(
        "SELECT id, created, name, use_when, steps, tools, uses, last_used, retired "
        "FROM skills WHERE id=?", (int(skill_id),)).fetchall(), [])
    return _row(rows[0]) if rows else None


def clean_steps(steps):
    """A list of short step strings, whatever shape they arrived in: a
    list, or one string with a step per line ("1. ...", "- ...")."""
    if isinstance(steps, str):
        steps = steps.splitlines()

    out = []

    for step in steps or ():
        text = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", " ".join(str(step).split()))

        if text:
            out.append(text[:MAX_STEP_CHARS])

    return out[:MAX_STEPS]


def check(name, when, steps):
    """'' if it's a usable recipe, else what's wrong with it."""
    if len(" ".join(str(name or "").split())) < 4:
        return "give it a name, a few words saying what it does"

    if len(" ".join(str(when or "").split())) < 6:
        return "say when to use it - what the user would say or need"

    if len(clean_steps(steps)) < 2:
        return "a recipe needs at least two steps - a one-step job doesn't need one"

    return ""


def find_same(name, when):
    """An active skill that's clearly the same job, or None."""
    current = skills()

    if not current:
        return None

    try:
        import notebook

        same = notebook.similar(f"{name}. {when}", [f"{s['name']}. {s['when']}" for s in current],
                                by_meaning=0.9, by_words=0.6)
    except Exception:
        same = None

    return next((s for s in current if f"{s['name']}. {s['when']}" == same), None)


def add(name, when, steps, tools=()):
    """New id, or the existing id when it replaces a skill for the same job."""
    name = " ".join(str(name).split())[:MAX_NAME_CHARS]
    when = " ".join(str(when).split())[:MAX_WHEN_CHARS]
    steps = clean_steps(steps)
    tools = sorted({str(t) for t in tools if t})
    same = find_same(name, when)

    if same:
        # Same job, newer recipe: the new steps win, the history stays.
        _run(lambda c: c.execute(
            "UPDATE skills SET name=?, use_when=?, steps=?, tools=? WHERE id=?",
            (name, when, json.dumps(steps), json.dumps(tools), same["id"])))
        return same["id"]

    new = _run(lambda c: c.execute(
        "INSERT INTO skills (created, name, use_when, steps, tools) VALUES (?,?,?,?,?)",
        (_now(), name, when, json.dumps(steps), json.dumps(tools))).lastrowid)
    _cap(keep=new)
    return new


def _cap(keep=None):
    """Over max_skills, the least-used oldest is retired, never deleted."""
    limit = int(getattr(config, "SELF_MAX_SKILLS", 60))
    active = [s for s in skills() if s["id"] != keep]
    limit -= 1 if keep else 0

    for s in sorted(active, key=lambda s: (s["uses"], s["id"]))[:max(0, len(active) - limit)]:
        retire(s["id"])


def retire(skill_id):
    return _run(lambda c: c.execute(
        "UPDATE skills SET retired=? WHERE id=? AND retired IS NULL",
        (_now(), int(skill_id))).rowcount, 0) > 0


def restore(skill_id):
    return _run(lambda c: c.execute(
        "UPDATE skills SET retired=NULL WHERE id=?", (int(skill_id),)).rowcount, 0) > 0


def credit(ids):
    """The skills a real turn of Ryan's carried - counted after the turn."""
    ids = [int(i) for i in ids or ()]

    if ids:
        _run(lambda c: c.executemany(
            "UPDATE skills SET uses = uses + 1, last_used=? WHERE id=?",
            [(_now(), i) for i in ids]))


# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------
_WORD = re.compile(r"[a-z0-9']+")
_STOP = {"the", "a", "an", "to", "of", "and", "or", "i", "you", "he", "it", "is", "in",
         "on", "for", "when", "that", "this", "be", "with", "my", "your", "his", "do",
         "can", "me", "what", "how", "please", "could", "would", "luna", "hey", "just",
         "check", "make", "get", "set", "up"}


def _words(text):
    return {w for w in _WORD.findall(str(text or "").lower()) if w not in _STOP and len(w) > 2}


def relevant(query, limit=None):
    """The skills that clearly fit this turn, best first. By meaning when
    the embedding server is up, else at least two shared words with the
    skill's name and when-to-use."""
    if not enabled() or not str(query or "").strip():
        return []

    limit = int(getattr(config, "SELF_SKILLS_IN_PROMPT", 2) if limit is None else limit)
    pool = skills()

    if not pool or limit <= 0:
        return []

    keys = [f"{s['name']}. {s['when']}" for s in pool]

    try:
        import embedmem

        scored = embedmem.rank(query, keys)

        if scored is not None:
            keep = [t for score, t in scored[:limit] if score >= 0.45]
            return [s for t in keep for s in pool if f"{s['name']}. {s['when']}" == t][:limit]
    except Exception:
        pass

    q = _words(query)
    scored = sorted(((len(q & _words(k)), -i, s) for i, (k, s) in enumerate(zip(keys, pool))),
                    key=lambda x: (x[0], x[1]), reverse=True)

    return [s for n, _i, s in scored[:limit] if n >= 2]


def render(skill):
    lines = [f"#{skill['id']} {skill['name']} (use when: {skill['when']})"]
    lines += [f"  {i}. {step}" for i, step in enumerate(skill["steps"], 1)]
    return "\n".join(lines)


def prompt_block(query):
    """The recipes for this turn, ready for the system prompt, and their ids."""
    found = relevant(query)

    if not found:
        return "", []

    text = ("Recipes you've saved for jobs like this - follow the steps that fit, adapt "
            "the rest, and say so if one doesn't apply:\n" + "\n".join(render(s) for s in found))

    return text, [s["id"] for s in found]
