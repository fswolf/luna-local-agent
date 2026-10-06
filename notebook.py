"""Luna's notebook: what she's learned about herself, and what happened.

Two kinds of entry, both written by reflect.py while she's idle, both
read back into her prompt by llm.py:

  lessons   one line each, about her own behaviour - "when he asks what
            day something falls on, call time_until instead of counting".
            Written by the dream pass from her flagged and low-confidence
            turns. Facts about Ryan don't belong here; they're memory.
  episodes  a few sentences per conversation: what it was about, what got
            decided, what was left unfinished. The newest one is how she
            knows what happened last time; older ones come back when
            they're relevant to what's being said now.

agent/notebook.db, gitignored. Nothing here is ever deleted by the app:
a retired lesson stays in the table, hidden from her, and /lessons
restore brings it back.
"""
import json
import os
import re
import sqlite3
import threading

from datetime import datetime

import config
import logbook

DB_FILE = os.path.join(config.BASE_DIR, "agent", "notebook.db")

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id        INTEGER PRIMARY KEY,
    created   TEXT NOT NULL,
    text      TEXT NOT NULL,
    from_ids  TEXT NOT NULL DEFAULT '[]',
    hits      INTEGER NOT NULL DEFAULT 0,
    last_used TEXT,
    retired   TEXT
);
CREATE TABLE IF NOT EXISTS episodes (
    id       INTEGER PRIMARY KEY,
    started  TEXT NOT NULL,
    ended    TEXT NOT NULL,
    turns    INTEGER NOT NULL,
    summary  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _run(fn, default=None):
    """One connection per call, under one lock: background jobs and turns
    both write here, and none of it is hot enough to pool."""
    with _lock:
        try:
            os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
            conn = sqlite3.connect(DB_FILE, timeout=10)

            try:
                conn.executescript(_SCHEMA)
                _migrate(conn)
                out = fn(conn)
                conn.commit()

                return out
            finally:
                conn.close()
        except sqlite3.Error as e:
            logbook.warn("notebook", "db error: %s", e)

            return default


def _migrate(conn):
    """Columns added after the first release, for a notebook.db that
    already exists."""
    have = {row[1] for row in conn.execute("PRAGMA table_info(lessons)")}

    if "origin" not in have:
        # "dream" - the daily pass; "self" - she noted it mid-conversation
        conn.execute("ALTER TABLE lessons ADD COLUMN origin TEXT NOT NULL DEFAULT 'dream'")


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# meta - small bits of bookkeeping (when the dream pass last ran, where the
# last episode ended, which fact pairs have already been checked)
# ---------------------------------------------------------------------------
def get(key, default=None):
    row = _run(lambda c: c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone())

    if not row:
        return default

    try:
        return json.loads(row[0])
    except ValueError:
        return default


def put(key, value):
    _run(lambda c: c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                             (key, json.dumps(value))))


# ---------------------------------------------------------------------------
# Similarity - by meaning when the embedding server is up, words otherwise
# ---------------------------------------------------------------------------
_WORD = re.compile(r"[a-z0-9']+")
_STOP = {"the", "a", "an", "to", "of", "and", "or", "i", "you", "he", "it",
         "is", "in", "on", "for", "when", "that", "this", "be", "with", "my",
         "your", "his", "instead", "not", "do", "don't", "if", "about"}


def _words(text):
    return {w for w in _WORD.findall(str(text or "").lower()) if w not in _STOP}


def overlap(a, b):
    wa, wb = _words(a), _words(b)

    return len(wa & wb) / max(1, len(wa | wb))


def similar(text, others, by_meaning=0.85, by_words=0.5):
    """The first of `others` that says the same thing as `text`, or None."""
    others = [o for o in others if o]

    if not others:
        return None

    try:
        import embedmem

        vecs = embedmem.vectors([text] + others)

        if vecs:
            best = max(others, key=lambda o: embedmem.cosine(vecs[text], vecs[o]))

            return best if embedmem.cosine(vecs[text], vecs[best]) >= by_meaning else None
    except Exception:
        pass

    best = max(others, key=lambda o: overlap(text, o))

    return best if overlap(text, best) >= by_words else None


def _pick(query, texts, limit, floor=0.3):
    """The `limit` texts closest to the query, best first. Embeddings when
    up; shared words otherwise, and nothing at all if nothing is shared -
    an unrelated lesson isn't worth its tokens."""
    if not texts or limit <= 0:
        return []

    if len(texts) <= limit:
        return list(texts)

    if str(query or "").strip():
        try:
            import embedmem

            scored = embedmem.rank(query, texts)

            if scored is not None:
                return [t for s, t in scored[:limit] if s >= floor]
        except Exception:
            pass

        q = _words(query)
        scored = sorted(((len(q & _words(t)), i, t) for i, t in enumerate(texts)), reverse=True)

        return [t for n, _i, t in scored[:limit] if n]

    return []


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------
def lessons(retired=False):
    where = "IS NOT NULL" if retired else "IS NULL"
    rows = _run(lambda c: c.execute(
        f"SELECT id, created, text, from_ids, hits, last_used, origin FROM lessons "
        f"WHERE retired {where} ORDER BY id").fetchall(), [])

    return [{"id": r[0], "created": r[1], "text": r[2], "from": json.loads(r[3] or "[]"),
             "hits": r[4], "last_used": r[5], "origin": r[6]} for r in rows]


def add_lesson(text, from_ids=(), origin="dream"):
    """Returns the new id, or None when she already knows this one - in
    which case the old lesson gets the credit (a hit) instead."""
    text = " ".join(str(text or "").split()).strip(" -•*")

    if len(text) < 12 or len(text) > 300:
        return None

    current = lessons()
    same = similar(text, [l["text"] for l in current])

    if same:
        lid = next(l["id"] for l in current if l["text"] == same)
        _run(lambda c: c.execute("UPDATE lessons SET hits = hits + 1 WHERE id=?", (lid,)))

        return None

    new = _run(lambda c: c.execute(
        "INSERT INTO lessons (created, text, from_ids, origin) VALUES (?,?,?,?)",
        (_now(), text, json.dumps(list(from_ids)), origin)).lastrowid)
    _cap(keep=new)

    return new


def _cap(keep=None):
    """Over max_lessons, the least-used oldest one is retired, not deleted -
    never the one that was just added."""
    limit = int(getattr(config, "SELF_MAX_LESSONS", 40))
    active = [l for l in lessons() if l["id"] != keep]
    limit -= 1 if keep else 0

    for l in sorted(active, key=lambda l: (l["hits"], l["id"]))[:max(0, len(active) - limit)]:
        retire_lesson(l["id"])


def retire_lesson(lesson_id):
    return _run(lambda c: c.execute(
        "UPDATE lessons SET retired=? WHERE id=? AND retired IS NULL",
        (_now(), int(lesson_id))).rowcount, 0) > 0


def restore_lesson(lesson_id):
    return _run(lambda c: c.execute(
        "UPDATE lessons SET retired=NULL WHERE id=?", (int(lesson_id),)).rowcount, 0) > 0


def relevant_lessons(query, limit=None):
    """Lesson texts for this turn. All of them while there are few; the
    closest to what was said once there are more than fit."""
    limit = int(getattr(config, "SELF_LESSONS_IN_PROMPT", 4) if limit is None else limit)

    return _pick(query, [l["text"] for l in lessons()], limit)


def credit(texts):
    """The lessons a real turn of Ryan's carried - counted after the turn,
    so building a prompt for /context or self_status counts nothing."""
    texts = list(texts or ())

    if texts:
        _run(lambda c: c.executemany(
            "UPDATE lessons SET hits = hits + 1, last_used=? WHERE text=? AND retired IS NULL",
            [(_now(), t) for t in texts]))


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------
def add_episode(started, ended, turns, summary):
    return _run(lambda c: c.execute(
        "INSERT INTO episodes (started, ended, turns, summary) VALUES (?,?,?,?)",
        (started, ended, int(turns), summary.strip())).lastrowid)


def episodes(limit=20):
    """Newest first."""
    rows = _run(lambda c: c.execute(
        "SELECT id, started, ended, turns, summary FROM episodes "
        "ORDER BY ended DESC LIMIT ?", (limit,)).fetchall(), [])

    return [{"id": r[0], "started": r[1], "ended": r[2], "turns": r[3], "summary": r[4]}
            for r in rows]


def latest_episode():
    found = episodes(1)

    return found[0] if found else None


def relevant_episodes(query, limit=None, skip_latest=True):
    """Older conversations that bear on this turn, newest first. The
    latest is left out by default - it travels anyway, as "last time"."""
    limit = int(getattr(config, "SELF_EPISODES_IN_PROMPT", 2) if limit is None else limit)
    skip = latest_episode()["id"] if skip_latest and latest_episode() else None

    # Stricter than the tool's search: these ride in every prompt, so an
    # episode has to be clearly about this, not just share a word.
    return [e for e in search_episodes(query, limit + 1, floor=0.45, min_words=2)
            if e["id"] != skip][:limit]


def search_episodes(query, limit=3, floor=0.35, min_words=1):
    """Her notes on past conversations, best match first - for the
    recall_episodes tool. Unlike relevant_episodes this always ranks,
    and says nothing rather than something unrelated."""
    pool = episodes(500)

    if not pool:
        return []

    if not str(query or "").strip():
        return pool[:limit]

    try:
        import embedmem

        scored = embedmem.rank(query, [e["summary"] for e in pool])

        if scored is not None:
            keep = [t for score, t in scored[:limit] if score >= floor]

            return [e for t in keep for e in pool if e["summary"] == t][:limit]
    except Exception:
        pass

    q = _words(query)
    scored = sorted(((len(q & _words(e["summary"])), -i, e) for i, e in enumerate(pool)),
                    key=lambda x: (x[0], x[1]), reverse=True)

    return [e for n, _i, e in scored[:limit] if n >= min_words]


def delete_episode(episode_id):
    return _run(lambda c: c.execute("DELETE FROM episodes WHERE id=?",
                                    (int(episode_id),)).rowcount, 0) > 0


def counts():
    return {
        "lessons": len(lessons()),
        "retired": len(lessons(retired=True)),
        "episodes": _run(lambda c: c.execute("SELECT COUNT(*) FROM episodes").fetchone()[0], 0),
    }
