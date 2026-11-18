"""The permanent fact table: where everything she's learned about you lives
(agent/facts.db). mind/longterm.py is the front door; this is the storage.

It keeps every fact ever learned in one file, searches them with FTS5 -
stemmed, term-weighted, milliseconds at thousands of rows - and never
deletes on its own. A Python whose sqlite was built without FTS5 still
gets the table; search() then says so (None) and longterm.py ranks the
facts by shared words instead. A fact that stops being true is *retired*, not
erased: it keeps its dates, it stops appearing in context, and it is
still there when you ask what your last graphics card was, or when the
retirement itself turns out to be the mistake.

Two clocks, kept apart. created_at and superseded_at are *record* time:
when she learned it and when she stopped believing it. valid_from and
valid_to are *real* time: when it was actually true. They differ
whenever you mention something after the fact ("I swapped cards last
Friday"), and only real time answers "what did I have in October?".
Real time is only ever filled from what was said; when nothing was,
record time stands in for it.

The schema is the design:

    fact           one short sentence, the only required thing
    subject        a one-word grouping ("hardware") so "what GPU" can
                   find a fact that never says the word GPU
    superseded_at  NULL means active; a timestamp means retired, and
                   says when
    superseded_by  which fact replaced it, if one did
    trust          'confirmed', or 'unconfirmed' for a fact the background
                   extractor guessed from one exchange: she shows it as
                   "(not sure)" and won't build pages on it until it comes
                   up again, he says it outright, or he confirms it
    valid_from     when it became true in his life, when he said so
                   ("2026-11-14", "2026-11", "2019"); NULL when he didn't
    valid_to       when it stopped being true, set when a newer fact with
                   a date replaces it; NULL means "until it was retired"
    embedding      reserved, unused - the column exists so adding
                   semantic search later is an UPDATE, not a migration

FTS5 runs as an external-content index over that table, kept in sync by
triggers - including on UPDATE, because a fixed mistake rewrites fact text
and an unsynced rewrite quietly corrupts search weeks before anyone
notices.

Threading: one connection, one lock, WAL.

Older installs kept a capped list in agent/memory.json instead. Those
facts are read in once (import_facts, from longterm.py) and the file is
never written again.
"""
import os
import re
import sqlite3
import threading
import time
from datetime import datetime

from core import logbook
from config import BASE_DIR

DB_FILE = os.path.join(BASE_DIR, "agent", "facts.db")

_lock = threading.Lock()
_db = None
_unavailable = None  # the reason, once known, so it's only logged once
_fts = True          # False: this sqlite has no FTS5, search() answers None

_TABLE = """
CREATE TABLE IF NOT EXISTS facts (
    id            INTEGER PRIMARY KEY,
    fact          TEXT NOT NULL,
    subject       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    superseded_at TEXT,
    superseded_by INTEGER,
    embedding     BLOB,
    valid_from    TEXT,
    valid_to      TEXT,
    trust         TEXT NOT NULL DEFAULT 'confirmed'
);

-- facts he told her to forget, as fingerprints, never words (mind/forgetting.py)
CREATE TABLE IF NOT EXISTS forgotten (
    marks  TEXT PRIMARY KEY,
    at     TEXT NOT NULL
);

-- small bookkeeping: what's been done once and mustn't be done again
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# The search index, kept in step by triggers. Without FTS5 none of it
# exists, and the triggers are dropped: a trigger naming a module this
# sqlite doesn't have would fail every insert.
_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    fact, subject,
    content='facts', content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, fact, subject)
    VALUES (new.id, new.fact, new.subject);
END;

CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, fact, subject)
    VALUES ('delete', old.id, old.fact, old.subject);
END;

CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE OF fact, subject ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, fact, subject)
    VALUES ('delete', old.id, old.fact, old.subject);
    INSERT INTO facts_fts(rowid, fact, subject)
    VALUES (new.id, new.fact, new.subject);
END;
"""


def _now():
    return datetime.now().isoformat(timespec="seconds")


_DATE = re.compile(r"^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$")


def when(text):
    """A real-time date as it's kept: "2026-11-14", "2026-11" or "2026";
    "today" is today. "" for anything else - a guess at "last week" is
    worse than no date, because a missing one falls back to record time."""
    text = str(text or "").strip().lower()
    if not text:
        return ""
    if text in ("today", "now"):
        return datetime.now().date().isoformat()
    m = _DATE.match(text)
    if not m:
        return ""
    year, month, day = m.group(1), m.group(2), m.group(3)
    if not 1900 <= int(year) <= 2200:
        return ""
    try:
        if day:
            return datetime(int(year), int(month), int(day)).date().isoformat()
        if month:
            return f"{year}-{int(month):02d}" if 1 <= int(month) <= 12 else ""
    except ValueError:
        return ""
    return year


def _set_aside(error):
    """facts.db can't be read as a database: move it (and its WAL files)
    aside as facts.db.bad-<time> so a fresh one can start, and say where
    it went. False if it couldn't be moved: then nothing is written."""
    keep = f"{DB_FILE}.bad-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        os.replace(DB_FILE, keep)
        for extra in ("-wal", "-shm"):
            if os.path.exists(DB_FILE + extra):
                os.replace(DB_FILE + extra, keep + extra)
    except OSError as e:
        logbook.error("factstore", "facts.db unreadable (%s) and couldn't be moved aside (%s)", error, e)
        logbook.tell(f"agent/facts.db can't be read ({error}) and couldn't be moved aside ({e}). "
                     "Memory is off until it's fixed or moved; nothing was written over it.")
        return False
    logbook.error("factstore", "facts.db unreadable (%s) - kept as %s", error, keep)
    logbook.tell(f"agent/facts.db couldn't be read ({error}). It was kept as "
                 f"{os.path.basename(keep)}, and a fresh one started.")
    return True


def _open():
    """The connection, with the table and (when this sqlite has FTS5) the
    index. Raises sqlite3 errors for _connect to sort out."""
    global _fts

    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    # timeout: the memory manager is another process on the same file
    db = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(_TABLE)
        have = {r[1] for r in db.execute("PRAGMA table_info(facts)")}
        for column, kind in (("valid_from", "TEXT"), ("valid_to", "TEXT"),   # a facts.db from before them
                             ("trust", "TEXT NOT NULL DEFAULT 'confirmed'")):
            if column not in have:
                try:
                    db.execute(f"ALTER TABLE facts ADD COLUMN {column} {kind}")
                except sqlite3.OperationalError as e:   # the memory manager added it first
                    if "duplicate column" not in str(e).lower():
                        raise
        had_index = db.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'facts_ai'").fetchone() is not None
        try:
            db.executescript(_FTS)
            _fts = True
            if not had_index:
                # new, or last opened by a sqlite without FTS5: catch the index up
                db.execute("INSERT INTO facts_fts(facts_fts) VALUES ('rebuild')")
        except sqlite3.OperationalError as e:
            if "fts5" not in str(e).lower():
                raise
            _fts = False
            for trigger in ("facts_ai", "facts_ad", "facts_au"):
                db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            logbook.warn("factstore", "no FTS5 in this sqlite (%s) - searching by shared words", e)
        db.commit()
    except Exception:
        db.close()
        raise
    return db


def _connect():
    global _db, _unavailable

    if _db is not None:
        return _db

    if _unavailable:
        return None

    try:
        _db = _open()
    except sqlite3.DatabaseError as e:
        # Busy is passing: try again next time rather than giving up on
        # the table for the whole session.
        if "locked" in str(e) or "busy" in str(e):
            logbook.warn("factstore", "busy (%s) - trying again later", e)
            return None

        # Not a database (a corrupt file): set it aside and start fresh,
        # rather than failing every turn.
        if not isinstance(e, sqlite3.OperationalError) and _set_aside(e):
            try:
                _db = _open()
            except (sqlite3.DatabaseError, OSError) as again:
                _unavailable = str(again)
                logbook.error("factstore", "a fresh facts.db can't be opened either: %s", again)
                return None
        else:
            _unavailable = str(e)
            if isinstance(e, sqlite3.OperationalError):
                logbook.error("factstore", "facts.db can't be opened: %s", e)
                logbook.tell(f"agent/facts.db can't be opened ({e}). Memory is off for now.")
            return None
    except OSError as e:
        logbook.warn("factstore", "unavailable (%s)", e)
        return None

    logbook.info("factstore", "open: %s%s", DB_FILE, "" if _fts else " (no FTS5)")
    return _db


def available():
    return _connect() is not None


def why_unavailable():
    return _unavailable


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def active_facts():
    """Every active fact, oldest first - same shape get_facts() had."""
    db = _connect()

    with _lock:
        rows = db.execute(
            "SELECT fact FROM facts WHERE superseded_at IS NULL ORDER BY id"
        ).fetchall()

    return [r[0] for r in rows]


def counts():
    """(active, retired)."""
    db = _connect()

    with _lock:
        active, retired = db.execute(
            "SELECT sum(superseded_at IS NULL), sum(superseded_at IS NOT NULL) "
            "FROM facts"
        ).fetchone()

    return active or 0, retired or 0


def rows(retired=False, limit=200, sure_only=False):
    """(id, fact, subject, created_at, superseded_at) for /facts. sure_only
    leaves out the unconfirmed: what pages and profiles are written from."""
    db = _connect()
    where = "IS NOT NULL" if retired else "IS NULL"
    if sure_only:
        where += " AND trust = 'confirmed'"

    with _lock:
        return db.execute(
            f"SELECT id, fact, subject, created_at, superseded_at FROM facts "
            f"WHERE superseded_at {where} ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def subjects():
    """The subject vocabulary in use, most common first - shown to the
    extractor so it reuses "hardware" instead of minting "pc",
    "computer" and "gpu" on different days."""
    db = _connect()

    with _lock:
        found = db.execute(
            "SELECT subject FROM facts WHERE subject != '' "
            "GROUP BY subject ORDER BY count(*) DESC LIMIT 20"
        ).fetchall()

    return [r[0] for r in found]


def details(facts):
    """{fact: (valid_from, valid_to, sure)} for the active facts among these
    that have something to show beside them: a real date, or not sure."""
    facts = [str(f) for f in facts or []]
    db = _connect()
    if db is None or not facts:
        return {}
    out = {}
    with _lock:
        for start in range(0, len(facts), 400):          # sqlite's variable limit
            chunk = facts[start:start + 400]
            marks = ",".join("?" * len(chunk))
            for fact, since, until, trust in db.execute(
                    f"SELECT fact, valid_from, valid_to, trust FROM facts WHERE superseded_at IS NULL "
                    f"AND (valid_from IS NOT NULL OR valid_to IS NOT NULL OR trust != 'confirmed') "
                    f"AND fact IN ({marks})", chunk):
                out[fact] = (since or "", until or "", trust == "confirmed")
    return out


def row_details(ids):
    """{id: (valid_from, valid_to, sure)} for these rows, where there's anything to show."""
    ids = [int(i) for i in ids or []][:1000]
    db = _connect()
    if db is None or not ids:
        return {}
    with _lock:
        found = db.execute(
            f"SELECT id, valid_from, valid_to, trust FROM facts WHERE id IN ({','.join('?' * len(ids))}) "
            "AND (valid_from IS NOT NULL OR valid_to IS NOT NULL OR trust != 'confirmed')", ids).fetchall()
    return {i: (since or "", until or "", trust == "confirmed") for i, since, until, trust in found}


def is_sure(fact_id):
    db = _connect()
    with _lock:
        row = db.execute("SELECT trust FROM facts WHERE id = ?", (int(fact_id),)).fetchone()
    return bool(row) and row[0] == "confirmed"


def history(query, limit=10):
    """Facts matching query, retired ones too, oldest first: dicts of fact,
    active, learned, retired, since, until (real time where said, else "").
    For "what did I have before?" - the one place retired facts are read."""
    db = _connect()
    if db is None:
        return []
    limit = max(1, int(limit))
    cols = "f.id, f.fact, f.superseded_at, f.created_at, f.valid_from, f.valid_to, f.trust"
    found = []
    with _lock:
        match = _match_expression(query) if _fts else ""
        if match:
            try:
                found = db.execute(
                    f"SELECT {cols} FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
                    "WHERE facts_fts MATCH ? ORDER BY bm25(facts_fts) LIMIT ?", (match, limit)).fetchall()
            except sqlite3.OperationalError as e:
                logbook.warn("factstore", "history match %r failed: %s", match, e)
        if not found:                       # no FTS5, or nothing ranked: shared words
            terms = [t for t in re.findall(r"[a-z0-9]+", str(query or "").lower())
                     if len(t) > 1 and t not in _STOP]
            if terms:
                where = " OR ".join("lower(f.fact || ' ' || f.subject) LIKE ?" for _t in terms[:12])
                found = db.execute(f"SELECT {cols} FROM facts f WHERE {where} ORDER BY f.id DESC LIMIT ?",
                                   [f"%{t}%" for t in terms[:12]] + [limit]).fetchall()
    return [{"fact": fact, "active": retired is None, "learned": (learned or "")[:10],
             "retired": (retired or "")[:10], "since": since or "", "until": until or "",
             "sure": trust == "confirmed"}
            for _id, fact, retired, learned, since, until, trust in sorted(found)]


# The same stopwords longterm.py's word ranking uses, for the same
# reason: "what" and "have" match everything and mean nothing.
_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "did",
    "do", "does", "for", "from", "had", "has", "have", "he", "her", "him",
    "his", "how", "i", "if", "in", "is", "it", "its", "me", "my", "not",
    "of", "on", "or", "our", "she", "so", "that", "the", "their", "them",
    "then", "there", "they", "this", "to", "was", "we", "were", "what",
    "when", "where", "which", "who", "why", "will", "with", "would",
    "you", "your", "am", "been", "being", "get", "got", "just", "like",
    "want", "need", "know", "think", "make", "let", "about",
}


def _match_expression(query):
    """User words -> a MATCH expression that cannot misfire.

    Every term is quoted, which makes it a literal: AND, OR, NOT, NEAR,
    a stray hyphen and an apostrophe are all FTS5 syntax in raw text,
    and "what's my GPU?" must be a question, not a parse error.
    """
    terms = [
        t for t in re.findall(r"[a-z0-9]+", str(query or "").lower())
        if len(t) > 1 and t not in _STOP
    ]

    return " OR ".join(f'"{t}"' for t in terms[:24])


def search(query, limit=25):
    """The facts worth showing for this turn, oldest first. None when
    there's no FTS5 to rank with: the caller ranks them itself.

    bm25 does the choosing, with one carve-out kept from the old
    scorer: the newest few facts always travel, relevant or not,
    because a fact learned two minutes ago is usually still in play in
    a way no ranking function can see.
    """
    db = _connect()
    limit = max(1, int(limit))

    if db is None or not _fts:
        return None

    with _lock:
        total = db.execute(
            "SELECT count(*) FROM facts WHERE superseded_at IS NULL"
        ).fetchone()[0]

        if total <= limit:
            everything = db.execute(
                "SELECT fact FROM facts WHERE superseded_at IS NULL ORDER BY id"
            ).fetchall()

            return [r[0] for r in everything]

        keep = max(1, limit // 3)
        recent = db.execute(
            "SELECT id, fact FROM facts WHERE superseded_at IS NULL "
            "ORDER BY id DESC LIMIT ?",
            (keep,),
        ).fetchall()
        recent_ids = {r[0] for r in recent}

        match = _match_expression(query)
        ranked = []

        if match:
            try:
                ranked = db.execute(
                    "SELECT f.id, f.fact FROM facts_fts "
                    "JOIN facts f ON f.id = facts_fts.rowid "
                    "WHERE facts_fts MATCH ? AND f.superseded_at IS NULL "
                    "ORDER BY bm25(facts_fts) LIMIT ?",
                    (match, limit),
                ).fetchall()
            except sqlite3.OperationalError as e:
                logbook.warn("factstore", "match %r failed: %s", match, e)

        chosen = {}

        for fact_id, fact in ranked:
            if fact_id not in recent_ids and len(chosen) < limit - keep:
                chosen[fact_id] = fact

        for fact_id, fact in recent:
            chosen[fact_id] = fact

    # Oldest first, like the list this replaces - the newest facts sit
    # closest to the conversation.
    return [chosen[i] for i in sorted(chosen)]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def add(fact, subject="", since="", sure=True, again=False):
    """Store one fact, true since `since` when that's known. sure=False is
    a guess from one exchange (unconfirmed). False if an identical active
    fact exists (hearing an unconfirmed one again confirms it), or if it's
    one he told her to forget - unless `again`: he's asked for it back,
    which lifts the tombstone."""
    fact = str(fact or "").strip()

    if not fact:
        return False

    if not _allowed(fact, again):
        return False

    db = _connect()

    with _lock:
        dupe = db.execute(
            "SELECT trust FROM facts WHERE fact = ? AND superseded_at IS NULL",
            (fact,),
        ).fetchone()

        if dupe:
            # known already: a second hearing confirms a guess, and a date
            # he's now given for it is still worth keeping
            changed = 0
            with db:
                if dupe[0] != "confirmed":
                    changed += db.execute("UPDATE facts SET trust = 'confirmed' WHERE fact = ? "
                                          "AND superseded_at IS NULL", (fact,)).rowcount
                if when(since):
                    changed += db.execute(
                        "UPDATE facts SET valid_from = ? WHERE fact = ? AND superseded_at IS NULL "
                        "AND valid_from IS NULL", (when(since), fact)).rowcount
            return changed > 0

        with db:    # commits, or rolls back on an error (locked, disk full)
            db.execute(
                "INSERT INTO facts(fact, subject, created_at, valid_from, trust) VALUES (?, ?, ?, ?, ?)",
                (fact, str(subject or "").strip().lower(), _now(), when(since) or None,
                 "confirmed" if sure else "unconfirmed"),
            )

    return True


def _allowed(fact, again):
    """Not a forgotten fact - or he's asked for it back, and the tombstone goes."""
    from mind import forgetting

    have = forgetting.marks(fact)
    hit = [t for t in tombstones() if forgetting.same_fact(have, t)]
    if not hit:
        return True
    if not again:
        logbook.info("factstore", "not saved, he asked for it to be forgotten: %r", fact)
        return False
    unbury(hit)
    return True


def replace(old_fact, new_fact, subject="", since="", sure=True):
    """new_fact supersedes old_fact (matched by exact text). The old row
    is retired, never deleted - reversible, and it keeps the history.
    `since`, when known, is the real day it changed: the new fact's start
    and the old one's end.
    False if the old fact isn't there, in which case the caller should
    just add() - a missed replacement must degrade to today's behaviour
    (both facts coexist), never to a lost fact."""
    new_fact = str(new_fact or "").strip()

    if not new_fact or not _allowed(new_fact, False):
        return False

    db = _connect()

    with _lock:
        row = db.execute(
            "SELECT id, subject FROM facts "
            "WHERE fact = ? AND superseded_at IS NULL",
            (str(old_fact or "").strip(),),
        ).fetchone()

        if not row:
            return False

        old_id, old_subject = row

        # Both or neither: a failure between them used to leave the shared
        # connection mid-transaction, and the next commit anywhere saved
        # the new fact without retiring the old one.
        since = when(since) or None
        with db:
            cursor = db.execute(
                "INSERT INTO facts(fact, subject, created_at, valid_from, trust) VALUES (?, ?, ?, ?, ?)",
                (new_fact, str(subject or old_subject or "").strip().lower(), _now(), since,
                 "confirmed" if sure else "unconfirmed"),
            )
            db.execute(
                "UPDATE facts SET superseded_at = ?, superseded_by = ?, "
                "valid_to = coalesce(?, valid_to) WHERE id = ?",
                (_now(), cursor.lastrowid, since, old_id),
            )

    return True


def confirm(fact):
    """He said it's right: an unconfirmed fact becomes a confirmed one."""
    db = _connect()

    with _lock:
        with db:
            cursor = db.execute("UPDATE facts SET trust = 'confirmed' WHERE fact = ? AND superseded_at IS NULL "
                                "AND trust != 'confirmed'", (str(fact or "").strip(),))

    return cursor.rowcount > 0


def confirm_row(fact_id):
    db = _connect()

    with _lock:
        with db:
            cursor = db.execute("UPDATE facts SET trust = 'confirmed' WHERE id = ?", (int(fact_id),))

    return cursor.rowcount > 0


def set_since(fact, since):
    """Give an active fact the real date it became true. False if the date
    isn't one or the fact isn't there."""
    since = when(since)
    if not since:
        return False
    db = _connect()

    with _lock:
        with db:
            cursor = db.execute(
                "UPDATE facts SET valid_from = ? WHERE fact = ? AND superseded_at IS NULL",
                (since, str(fact or "").strip()))

    return cursor.rowcount > 0


def update(old_fact, new_fact):
    """Rewrite a fact in place - a correction, not a change in the
    world, so no history row. The AU trigger keeps FTS honest."""
    if not _allowed(str(new_fact or ""), False):
        return False
    db = _connect()

    with _lock:
        with db:
            cursor = db.execute(
                "UPDATE facts SET fact = ? "
                "WHERE fact = ? AND superseded_at IS NULL",
                (str(new_fact or "").strip(), str(old_fact or "").strip()),
            )

    return cursor.rowcount > 0


def remove(fact):
    """Actually delete - only for an explicit "forget that". The user
    asking for something to be forgotten is the one case where keeping
    a retired copy would be doing the opposite of what they asked."""
    db = _connect()

    with _lock:
        with db:
            cursor = db.execute(
                "DELETE FROM facts WHERE fact = ?", (str(fact or "").strip(),)
            )

    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Row-level edits, by id
#
# The tools above match by text because that's what a model is good at
# repeating. The memory manager works by id because that's what a row
# on a screen has - and an id can't pick the wrong fact when two are
# worded almost alike.
# ---------------------------------------------------------------------------
def set_row(fact_id, fact, subject):
    db = _connect()

    with _lock:
        with db:
            cursor = db.execute(
                "UPDATE facts SET fact = ?, subject = ? WHERE id = ?",
                (str(fact or "").strip(), str(subject or "").strip().lower(),
                 int(fact_id)),
            )

    return cursor.rowcount > 0


def retire_row(fact_id):
    db = _connect()

    with _lock:
        with db:
            cursor = db.execute(
                "UPDATE facts SET superseded_at = ? "
                "WHERE id = ? AND superseded_at IS NULL",
                (_now(), int(fact_id)),
            )

    return cursor.rowcount > 0


def restore_row(fact_id):
    db = _connect()

    with _lock:
        with db:
            cursor = db.execute(
                "UPDATE facts SET superseded_at = NULL, superseded_by = NULL, valid_to = NULL "
                "WHERE id = ?",
                (int(fact_id),),
            )

    return cursor.rowcount > 0


def delete_row(fact_id):
    db = _connect()

    with _lock:
        with db:
            cursor = db.execute("DELETE FROM facts WHERE id = ?", (int(fact_id),))

    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Tombstones: what he told her to forget, as fingerprints (mind/forgetting.py)
# ---------------------------------------------------------------------------
def bury(marks):
    """Keep a forgotten fact's fingerprint: a set of word hashes."""
    key = " ".join(sorted(marks or ()))
    if not key:
        return False
    db = _connect()

    with _lock, db:
        db.execute("INSERT OR REPLACE INTO forgotten(marks, at) VALUES (?, ?)", (key, _now()))

    return True


def unbury(mark_sets):
    """He's asked for these back."""
    db = _connect()

    with _lock, db:
        for marks in mark_sets:
            db.execute("DELETE FROM forgotten WHERE marks = ?", (" ".join(sorted(marks)),))


def tombstones():
    """[set of word hashes] for every forgotten fact."""
    db = _connect()
    if db is None:
        return []

    with _lock:
        found = db.execute("SELECT marks FROM forgotten").fetchall()

    return [set(r[0].split()) for r in found]


def forgotten_count():
    db = _connect()
    if db is None:
        return 0

    with _lock:
        return db.execute("SELECT count(*) FROM forgotten").fetchone()[0]


def unbury_all():
    """Let her learn anything again (the memory page's button)."""
    db = _connect()

    with _lock, db:
        return db.execute("DELETE FROM forgotten").rowcount


# ---------------------------------------------------------------------------
# Facts from an older install's memory.json
# ---------------------------------------------------------------------------
def meta(key):
    """A bookkeeping value, or None."""
    db = _connect()

    with _lock:
        row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()

    return row[0] if row else None


def set_meta(key, value):
    db = _connect()

    with _lock, db:
        db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, str(value)))


def _forgotten_here(db, fact):
    """import_facts holds the lock already: the same check as _allowed, inline."""
    from mind import forgetting

    have = forgetting.marks(fact)
    return any(forgetting.same_fact(have, set(r[0].split()))
               for r in db.execute("SELECT marks FROM forgotten").fetchall())


def import_facts(facts):
    """Absorb a list of facts. Idempotent - a fact already here (active
    OR retired) is skipped, so reading the same old list again never
    resurrects something that was superseded since."""
    db = _connect()
    added = 0

    with _lock, db:
        for fact in facts:
            fact = str(fact or "").strip()

            if not fact:
                continue

            known = db.execute(
                "SELECT 1 FROM facts WHERE fact = ?", (fact,)
            ).fetchone()

            if not known and not _forgotten_here(db, fact):
                db.execute(
                    "INSERT INTO facts(fact, subject, created_at) "
                    "VALUES (?, '', ?)",
                    (fact, _now()),
                )
                added += 1

    return added

