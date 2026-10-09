"""Ongoing projects: the things you're working on together, across sessions.

Her conversation notes say what happened; a project says where a piece
of work stands. "We're fixing the Mac audio" becomes a project with a
goal, a running log of what was tried and what was found, and the next
step - and it rides in her prompt until it's done:

    Ongoing projects:
    #2 fix the Mac audio (goal: Luna's voice plays on NZ_Kitty's Mac)
       found: the headphones refuse 24 kHz; 44.1 kHz plays fine
       tried: afplay with resampling - pushed, waiting on her test
       next: ask whether she heard Luna after pulling

She keeps them current with three tools: start_project, update_project
(tried / found / next / done) and project_notes (the whole log). You can
see and steer them with /projects.

agent/projects.db, gitignored. Nothing is deleted: a dropped project is
retired and /projects restore <n> brings it back.
"""
import os
import re
import sqlite3
import threading

from datetime import datetime

import config
import logbook

DB_FILE = os.path.join(config.BASE_DIR, "agent", "projects.db")

KINDS = ("tried", "found", "decided", "next", "note")
MAX_ENTRY = 300

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id       INTEGER PRIMARY KEY,
    created  TEXT NOT NULL,
    updated  TEXT NOT NULL,
    title    TEXT NOT NULL,
    goal     TEXT NOT NULL DEFAULT '',
    status   TEXT NOT NULL DEFAULT 'active',   -- active | paused | done
    next     TEXT NOT NULL DEFAULT '',
    retired  TEXT
);
CREATE TABLE IF NOT EXISTS entries (
    id         INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    at         TEXT NOT NULL,
    kind       TEXT NOT NULL,
    text       TEXT NOT NULL
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
            logbook.warn("projects", "db error: %s", e)
            return default


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _clean(text, limit=MAX_ENTRY):
    return " ".join(str(text or "").split())[:limit]


def enabled():
    return bool(getattr(config, "SELF_PROJECTS", True))


# ---------------------------------------------------------------------------
_COLS = "id, created, updated, title, goal, status, next, retired"


def _row(r):
    return dict(zip(("id", "created", "updated", "title", "goal", "status", "next", "retired"), r))


def projects(status=None, retired=False):
    """Newest-touched first. status: 'active', 'paused', 'done', or None for all."""
    where = ["retired IS NOT NULL" if retired else "retired IS NULL"]
    args = []

    if status:
        where.append("status=?")
        args.append(status)

    rows = _run(lambda c: c.execute(
        f"SELECT {_COLS} FROM projects WHERE {' AND '.join(where)} ORDER BY updated DESC",
        args).fetchall(), [])
    return [_row(r) for r in rows]


def get(project_id):
    rows = _run(lambda c: c.execute(f"SELECT {_COLS} FROM projects WHERE id=?",
                                    (int(project_id),)).fetchall(), [])
    return _row(rows[0]) if rows else None


def entries(project_id, limit=None):
    """Oldest first; the last `limit` when given."""
    rows = _run(lambda c: c.execute(
        "SELECT at, kind, text FROM entries WHERE project_id=? ORDER BY id",
        (int(project_id),)).fetchall(), [])
    rows = [{"at": a, "kind": k, "text": t} for a, k, t in rows]
    return rows[-limit:] if limit else rows


def find(ref):
    """A project by id ('2', '#2') or by name - the best title match among
    the ones not retired. None when nothing fits."""
    ref = str(ref or "").strip()

    if re.fullmatch(r"#?\d+", ref):
        found = get(int(ref.lstrip("#")))
        return found if found and not found["retired"] else None

    pool = projects()

    if not pool or not ref:
        return None

    words = set(re.findall(r"[a-z0-9']+", ref.lower()))
    scored = sorted(((len(words & set(re.findall(r"[a-z0-9']+", p["title"].lower()))), p)
                     for p in pool), key=lambda x: x[0], reverse=True)

    return scored[0][1] if scored[0][0] else None


def start(title, goal=""):
    """(id, created) - an active project with the same title is reused."""
    title = _clean(title, 100)
    goal = _clean(goal)
    same = next((p for p in projects() if p["title"].lower() == title.lower()), None)

    if same:
        _run(lambda c: c.execute("UPDATE projects SET status='active', updated=?, goal=COALESCE(NULLIF(?, ''), goal) WHERE id=?",
                                 (_now(), goal, same["id"])))
        return same["id"], False

    now = _now()
    new = _run(lambda c: c.execute(
        "INSERT INTO projects (created, updated, title, goal) VALUES (?,?,?,?)",
        (now, now, title, goal)).lastrowid)
    return new, True


def log(project_id, kind, text):
    kind = kind if kind in KINDS else "note"
    text = _clean(text)

    if not text:
        return

    _run(lambda c: c.execute("INSERT INTO entries (project_id, at, kind, text) VALUES (?,?,?,?)",
                             (int(project_id), _now(), kind, text)))
    _touch(project_id)


def set_next(project_id, text):
    _run(lambda c: c.execute("UPDATE projects SET next=?, updated=? WHERE id=?",
                             (_clean(text), _now(), int(project_id))))


def set_status(project_id, status):
    if status not in ("active", "paused", "done"):
        return False
    return _run(lambda c: c.execute("UPDATE projects SET status=?, updated=? WHERE id=?",
                                    (status, _now(), int(project_id))).rowcount, 0) > 0


def retire(project_id):
    return _run(lambda c: c.execute("UPDATE projects SET retired=? WHERE id=? AND retired IS NULL",
                                    (_now(), int(project_id))).rowcount, 0) > 0


def restore(project_id):
    return _run(lambda c: c.execute("UPDATE projects SET retired=NULL WHERE id=?",
                                    (int(project_id),)).rowcount, 0) > 0


def _touch(project_id):
    _run(lambda c: c.execute("UPDATE projects SET updated=? WHERE id=?", (_now(), int(project_id))))


# ---------------------------------------------------------------------------
# For the prompt
# ---------------------------------------------------------------------------
def _when(iso):
    try:
        import timeutil

        return timeutil.relative(datetime.fromisoformat(iso), datetime.now())
    except Exception:
        return iso


def render(project, recent=3):
    head = f"#{project['id']} {project['title']}"

    if project["goal"]:
        head += f" (goal: {project['goal']})"

    if project["status"] != "active":
        head += f" [{project['status']}]"

    lines = [head + f" - last touched {_when(project['updated'])}"]

    for e in (entries(project["id"], recent) if recent else []):
        if e["kind"] != "next":
            lines.append(f"   {e['kind']}: {e['text']}")

    if project["next"]:
        lines.append(f"   next: {project['next']}")

    return "\n".join(lines)


def _relevance(query, project):
    q = set(re.findall(r"[a-z0-9']{3,}", str(query).lower()))
    text = f"{project['title']} {project['goal']} {project['next']}".lower()
    return len(q & set(re.findall(r"[a-z0-9']{3,}", text)))


def prompt_block(query=""):
    """Active projects for this turn: all of them while they fit, else the
    ones that match what was said plus the most recently touched."""
    if not enabled():
        return ""

    active = projects("active")
    paused = projects("paused")

    if not active and not paused:
        return ""

    limit = int(getattr(config, "SELF_PROJECTS_IN_PROMPT", 3))

    if len(active) > limit:
        ranked = sorted(active, key=lambda p: (_relevance(query, p), p["updated"]), reverse=True)
        active = ranked[:limit]

    parts = []

    if active:
        parts.append("Ongoing projects with the user - when you work on one, record it with "
                     "update_project (tried / found / next), and mark it done when it is:\n"
                     + "\n".join(render(p) for p in active))

    if paused:
        parts.append("Paused projects (resume with update_project status active if he brings "
                     "one up): " + "; ".join(f"#{p['id']} {p['title']}" for p in paused[:5]))

    return "\n".join(parts)
