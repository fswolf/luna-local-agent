"""When you tell her to forget something, it stays forgotten.

Deleting the fact row was only ever half of it. The same words sat on
in her episode notes, the running summary, the transcript she searches,
the thought log, her pages and profiles and the embedding cache, and the
next idle pass could write the fact straight back from any of them. So a
forget now does three things:

    1. a tombstone: a fingerprint of the fact, kept in facts.db
       (factstore.bury). Never the words: a hash of each word that
       matters, so it can be recognised again without being readable.
    2. a sweep: every store above, and the memory's own change log, has
       the sentences that carry it taken out, now (scrub_everywhere).
    3. a guard: whatever she writes from then on (her replies, summaries,
       episode notes, pages, profiles) goes through clean(), and a new
       fact that matches a tombstone isn't saved (factstore.add/replace).

What you say yourself is never filtered: if you bring it up again, you
meant to. The thought log is a debugging record: swept once, at the
forget, and not filtered after. Saying "remember this" (or adding it on the memory page) lifts
the tombstone.

Matching is by the fact's distinctive words, with names and small words
left out: "Ryan works at the bakery" is {work, bakery}. A sentence that
has all of them (most of them, for a long fact) goes. A one-word fact
("Ryan likes anime" is {anime}) only takes sentences that are also about
a person, so she can still talk about anime in general.
"""
import functools
import hashlib
import math
import re
import threading

from core import logbook

# Small words, and the ones every sentence about him has. On top of
# factstore's search stopwords.
_EXTRA_STOP = {
    "used", "now", "still", "really", "very", "also", "user", "always", "never",
    "anymore", "lot", "much", "some", "any", "one", "two", "into", "out", "up",
    "more", "most", "all", "every", "these", "those", "than", "too", "own",
    "s", "t", "d", "ll", "re", "ve", "m",
}
_PERSON = {"you", "your", "yours", "i", "my", "me", "mine", "he", "his", "him", "she", "her", "user"}
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


def _names():
    try:
        import config

        names = {str(getattr(config, n, "") or "").lower()
                 for n in ("USER_NAME", "AGENT_NAME")}
    except Exception:
        names = set()
    return {w for n in names for w in re.findall(r"[a-z0-9]+", n)} | {"luna"}


def _stem(word):
    """Rough, but the same every time: likes / liked / like -> lik,
    movie / movies -> movi."""
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "i"
    elif word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("es") and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return word[:-1] + "i" if len(word) > 3 and word.endswith("y") else word   # bakery / bakeries


@functools.lru_cache(maxsize=1)
def _stop():
    from mind import factstore

    small = factstore._STOP | _EXTRA_STOP
    return small | {_stem(w) for w in small}


def words(text, stop=None, names=None):
    """The words that carry a text's meaning, stemmed."""
    stop = _stop() if stop is None else stop
    names = _names() if names is None else names
    found = {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower().replace("'s ", " "))
             if len(w) > 1 and w not in stop and w not in names}
    return {w for w in found if w not in stop}          # "likes" is "like", a small word too


def _hash(word):
    return hashlib.sha256(("luna-forget:" + word).encode()).hexdigest()[:12]


def marks(text):
    """A fact's fingerprint: its meaning words, each hashed."""
    return {_hash(w) for w in words(text)}


def same_fact(candidate, tomb):
    """Is this candidate's mark set the forgotten fact again? Equal, or
    every forgotten word plus at most two more ("used to work at the
    bakery"), or nearly all of a long one."""
    if not tomb or not candidate:
        return False
    if candidate == tomb:
        return True
    if len(tomb) >= 2 and tomb <= candidate and len(candidate) <= len(tomb) + 2:
        return True
    return len(tomb) >= 3 and len(tomb & candidate) / len(tomb | candidate) >= 0.8


def _carries(sentence, tombs, stop, names):
    """Does this sentence carry any of the forgotten facts?"""
    have = {_hash(w) for w in words(sentence, stop, names)}
    if not have:
        return False
    about_someone = None
    for tomb in tombs:
        n = len(tomb)
        if n == 1:
            if tomb <= have:
                if about_someone is None:
                    about_someone = bool(set(re.findall(r"[a-z0-9]+", sentence.lower())) & (_PERSON | names))
                if about_someone:
                    return True
        elif n <= 3:
            if tomb <= have:
                return True
        elif len(tomb & have) >= math.ceil(0.75 * n):
            return True
    return False


def clean(text, tombs=None):
    """text with every sentence that carries a forgotten fact taken out.
    tombs: mark sets to look for; the stored ones when not given. Anything
    that isn't text (None, a number) comes back as it was."""
    if not isinstance(text, str) or not text.strip():
        return text
    if tombs is None:
        tombs = tombstones()
    tombs = [t for t in tombs if t]
    if not tombs:
        return text
    stop, names = _stop(), _names()
    out, dropped = [], False
    for line in text.split("\n"):
        parts = _SENTENCE.split(line)
        kept = [s for s in parts if not _carries(s, tombs, stop, names)]
        if len(kept) == len(parts):
            out.append(line)                        # untouched lines keep their spacing
            continue
        dropped = True
        joined = " ".join(s for s in kept if s.strip())
        if joined.strip():
            out.append(joined)
    if not dropped:
        return text
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def clean_calls(calls, tombs=None):
    """A message's tool calls with their arguments and results cleaned too:
    "Forgotten: Ryan works at the bakery" is a result, and those ride along
    in her history as examples."""
    if not calls:
        return calls
    if tombs is None:
        tombs = tombstones()
    if not tombs:
        return calls
    out = []
    for call in calls:
        if isinstance(call, dict):
            call = dict(call)
            if isinstance(call.get("result"), str):
                call["result"] = clean(call["result"], tombs)
            if isinstance(call.get("arguments"), str):
                call["arguments"] = _clean_arguments(call["arguments"], tombs)
        out.append(call)
    return out


def _clean_arguments(raw, tombs):
    """Arguments are JSON that gets replayed to the model server, so they
    must stay JSON: the string values are cleaned, never the text as a whole."""
    import json

    try:
        data = json.loads(raw)
    except ValueError:
        return raw if clean(raw, tombs) == raw else "{}"
    if not isinstance(data, dict):
        return raw
    cleaned = {k: clean(v, tombs) if isinstance(v, str) else v for k, v in data.items()}
    return raw if cleaned == data else json.dumps(cleaned)


def tombstones():
    """Every forgotten fact's marks; [] when facts.db can't be read."""
    try:
        import os

        from mind import factstore

        if factstore._db is None and not os.path.exists(factstore.DB_FILE):
            return []           # no memory yet (a fresh install, a test): nothing forgotten, nothing created
        return factstore.tombstones()
    except Exception:
        logbook.exception("forgetting", "couldn't read the tombstones")
        return []


def forgotten(fact):
    """Does this fact match one she was told to forget?"""
    have = marks(fact)
    return any(same_fact(have, t) for t in tombstones())


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------
def forget(fact, wait=False):
    """Bury the fact and take it out of everything else. The sweep runs on
    its own thread (the transcript and thought log can be big) unless wait."""
    from mind import factstore

    tomb = marks(fact)
    if not tomb:
        return False
    factstore.bury(tomb)
    # the sweep (and the vector drop, which may ask the embedding server its
    # model name) bound now, not when the thread gets to it; and who asked,
    # for the log (the thread doesn't inherit it)
    who = factstore._by.get()
    work = (scrub_everywhere, _drop_vectors, [tomb], [fact], f"{who}, forgetting" if who else "forgetting")
    if wait:
        _sweep(*work)
    else:
        threading.Thread(target=_sweep, args=work, daemon=True, name="forget-sweep").start()
    return True


def _sweep(sweep, drop, tombs, texts, who="forgetting"):
    from mind import factstore

    try:
        with factstore.acting(who):
            drop(texts)
            sweep(tombs)
    except Exception:
        logbook.exception("forgetting", "sweep failed")


def scrub_everywhere(tombs):
    """Take the sentences carrying these out of every store. {store: count}."""
    done = {}
    for name, fn in (("facts", _facts), ("memory log", _log), ("conversation", _history), ("transcript", _transcript),
                     ("episodes", _episodes), ("lessons", _lessons), ("pages", _pages), ("profiles", _profiles),
                     ("conclusions", _conclusions), ("thoughts", _thoughts)):
        try:
            done[name] = fn(tombs)
        except Exception:
            logbook.exception("forgetting", "scrubbing %s failed", name)
    changed = {k: v for k, v in done.items() if v}
    logbook.info("forgetting", "swept: %s", ", ".join(f"{k} {v}" for k, v in changed.items()) or "nothing else had it")
    return done


def _facts(tombs):
    """Other rows that say the same thing, active or retired: a reworded copy,
    or the old version kept as history."""
    from mind import factstore

    gone = []
    for retired in (False, True):
        for row_id, fact, *_ in factstore.rows(retired=retired, limit=100000):
            if any(same_fact(marks(fact), t) for t in tombs) and factstore.delete_row(row_id):
                gone.append(fact)
    _drop_vectors(gone)
    return len(gone)


def _log(tombs):
    """The memory's own change log: rows still carrying it (a reworded or
    corrected copy whose fact row went some other way, an old "was: ..."),
    words emptied. The deleted rows' own log rows were emptied as they went."""
    from mind import factstore

    return factstore.scrub_events(lambda text: bool(text) and any(
        same_fact(marks(part), t) for t in tombs for part in _SENTENCE.split(text) + [text]))


def _history(tombs):
    from core import history

    n = 0
    with history._lock:
        summary = history._data.get("summary", "")
        cleaned = clean(summary, tombs)
        if cleaned != summary:
            history._data["summary"] = cleaned
            n += 1
        keep = []
        for m in history._data.get("messages", []):
            new = clean(m.get("content"), tombs)
            calls = clean_calls(m.get("tools"), tombs)
            if new != m.get("content") or calls != m.get("tools"):
                n += 1
                if isinstance(new, str) and not new.strip() and not calls:
                    continue
                m["content"] = new
                if calls is not None:
                    m["tools"] = calls
            keep.append(m)
        history._data["messages"] = keep
    if n:
        history.save()
    return n


def _transcript(tombs):
    import json
    import os

    from core import transcript

    if not os.path.exists(transcript.TRANSCRIPT_FILE):
        return 0
    n = 0
    with transcript._lock:
        entries = transcript._load()
        out = []
        for e in entries:
            new = clean(e.get("text", ""), tombs)
            if new != e.get("text", ""):
                n += 1
                if not new.strip():
                    continue
                e = dict(e, text=new)
            out.append(e)
        if n:
            tmp = transcript.TRANSCRIPT_FILE + ".new"
            with open(tmp, "w", encoding="utf-8") as handle:
                for e in out:
                    handle.write(json.dumps(e, ensure_ascii=False) + "\n")
            os.replace(tmp, transcript.TRANSCRIPT_FILE)
    return n


def _rewrite(table, column, tombs, empty_sql=None):
    """Clean one text column of a notebook.db table; rows left empty get
    empty_sql (delete or retire). Returns how many rows changed."""
    from mind import notebook

    def go(c):
        changed = []
        for row_id, text in c.execute(f"SELECT id, {column} FROM {table}").fetchall():
            new = clean(text, tombs)
            if new == text:
                continue
            changed.append(text)
            if not new.strip() and empty_sql:
                c.execute(empty_sql, (row_id,))
            else:
                c.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (new, row_id))
        return changed

    changed = notebook._run(go, []) or []
    _drop_vectors(changed)
    return len(changed)


def _episodes(tombs):
    return _rewrite("episodes", "summary", tombs, "DELETE FROM episodes WHERE id=?")


def _lessons(tombs):
    return _rewrite("lessons", "text", tombs, "UPDATE lessons SET retired=datetime('now') WHERE id=?")


def _keyed(table, key, tombs):
    """pages / profiles: clean the text, and mark them to be rewritten from
    what's left (sources='')."""
    from mind import notebook

    def go(c):
        c.execute(f"CREATE TABLE IF NOT EXISTS {table} ({key} TEXT PRIMARY KEY, text TEXT NOT NULL, "
                  "sources TEXT NOT NULL, facts INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL)")
        n = 0
        for name, text in c.execute(f"SELECT {key}, text FROM {table}").fetchall():
            new = clean(text, tombs)
            if new != text:
                n += 1
                if new.strip():
                    c.execute(f"UPDATE {table} SET text=?, sources='' WHERE {key}=?", (new, name))
                else:
                    c.execute(f"DELETE FROM {table} WHERE {key}=?", (name,))
        return n

    return notebook._run(go, 0) or 0


def _pages(tombs):
    return _keyed("pages", "subject", tombs)


def _profiles(tombs):
    return _keyed("profiles", "person", tombs)


def _conclusions(tombs):
    from mind import conclusions

    return conclusions.scrub(tombs)


def _thoughts(tombs):
    import os

    from mind import thoughtlog

    if not os.path.exists(thoughtlog.DB_FILE):
        return 0
    conn = thoughtlog._conn()
    try:
        n = 0
        for row_id, said, reasoning, answer in conn.execute(
                "SELECT id, user_text, reasoning, answer FROM thoughts").fetchall():
            new = [clean(t, tombs) for t in (said, reasoning, answer)]
            if new != [said, reasoning, answer]:
                n += 1
                conn.execute("UPDATE thoughts SET user_text=?, reasoning=?, answer=? WHERE id=?", (*new, row_id))
                conn.execute("DELETE FROM thought_tokens WHERE id=?", (row_id,))   # the tokens spell it out too
        conn.commit()
        return n
    finally:
        conn.close()


def _drop_vectors(texts):
    if not texts:
        return
    try:
        from mind import embedmem

        embedmem.drop(texts)
    except Exception:
        logbook.exception("forgetting", "couldn't drop cached vectors")
