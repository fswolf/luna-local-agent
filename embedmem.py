"""Recalling facts by meaning, when there's an embedding server to ask.

Fact recall used to be word overlap (json) or bm25 (sqlite): "I got a
new graphics card" finds nothing about the 6950 XT, because no word is
shared. An embedding model turns each fact and the turn into a vector,
and facts that *mean* something close to what was said rank highest,
shared words or not.

It is entirely optional. llama/start.sh starts a small embedding model
on :8081; when that isn't answering, available() says so and longterm
quietly uses the word matching it always did. Nothing here ever makes
a turn fail.

A reranker (:8082, also optional) can sharpen the pick. The embedding
model compares two vectors made separately; the reranker reads what
was said and each candidate together, so it's better at telling a fact
that answers the turn from one that's merely on the same topic. It's
slower per fact, so it only re-orders the embedding's best matches, and
only when there are more of them than slots to fill.

Vectors are cached in agent/embeddings.db, keyed by the text and the
model that made them, so each fact is embedded once - editing a fact
or switching models simply misses the cache and makes a new one. The
query is the only thing embedded per turn: one short request.
"""
import hashlib
import os
import sqlite3
import threading
import time

from array import array

import requests

import config
import logbook

DB_FILE = os.path.join(config.BASE_DIR, "agent", "embeddings.db")
TIMEOUT = 2.0      # per request; a turn waits this long at most
RECHECK = 30.0     # seconds between "is it up?" checks

_lock = threading.Lock()
_state = {"up": None, "checked": 0.0, "model": ""}
_rerank = {"up": None, "checked": 0.0, "model": ""}


def _db():
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS vectors "
                 "(key TEXT PRIMARY KEY, dim INTEGER, data BLOB)")

    return conn


def _root():
    return config.EMBED_URL.split("/v1/")[0]


def available():
    """Is the embedding server answering? Checked at most every RECHECK
    seconds, so a turn never waits on a server that isn't there."""
    now = time.monotonic()

    if _state["up"] is not None and now - _state["checked"] < RECHECK:
        return _state["up"]

    try:
        response = requests.get(_root() + "/v1/models",
                                headers=config.EMBED_HEADERS, timeout=0.5)
        up = response.status_code == 200
        _state["model"] = ((response.json().get("data") or [{}])[0].get("id", "")
                           if up else "")
    except Exception:
        up = False

    if up != _state["up"]:
        logbook.info("embed", "embedding server %s",
                     f"up ({_state['model']})" if up else "not answering")

    _state.update(up=up, checked=now)

    return up


def _embed(texts):
    response = requests.post(
        config.EMBED_URL, headers=config.EMBED_HEADERS,
        json={"input": texts, "model": _state["model"] or "embed"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = sorted(response.json()["data"], key=lambda d: d["index"])

    return [d["embedding"] for d in data]


def _key(text):
    return hashlib.sha1(f"{_state['model']}\n{text}".encode()).hexdigest()


def _vectors(facts):
    """{fact: vector} for every fact, embedding only the uncached ones."""
    keys = {fact: _key(fact) for fact in facts}
    found = {}

    with _lock:
        conn = _db()

        try:
            for fact, key in keys.items():
                row = conn.execute("SELECT data FROM vectors WHERE key=?",
                                   (key,)).fetchone()

                if row:
                    found[fact] = array("f", row[0])

            missing = [f for f in facts if f not in found]

            # In batches: the server holds one batch in a single ubatch,
            # and a first run against a long memory shouldn't be one
            # enormous request.
            for start in range(0, len(missing), 32):
                chunk = missing[start:start + 32]

                for fact, vector in zip(chunk, _embed(chunk)):
                    vec = array("f", vector)
                    found[fact] = vec
                    conn.execute("INSERT OR REPLACE INTO vectors VALUES (?,?,?)",
                                 (keys[fact], len(vec), vec.tobytes()))

            conn.commit()
        finally:
            conn.close()

    return found


def vectors(texts):
    """{text: vector} through the cache, or None when the server's down.
    For the background jobs (lesson dedup, fact cleanup) that compare
    stored texts with each other rather than with a query."""
    if not texts or not available():
        return None

    try:
        return _vectors(list(dict.fromkeys(texts)))
    except Exception as e:
        logbook.warn("embed", "vectors failed: %s", e)
        _state.update(up=False, checked=time.monotonic())

        return None


def embed_fresh(texts, batch=8):
    """Vectors for text that mustn't be cached - web passages, which
    have no business in agent/embeddings.db. Raises on failure; the
    caller has its own fallback. Small batches: the server's context
    is short (EMBED_CTX), and a passage is a paragraph, not a fact."""
    out = []

    for start in range(0, len(texts), batch):
        out.extend(_embed(texts[start:start + batch]))

    return out


def cosine(a, b):
    """The server normalises, so the dot product is the cosine."""
    return sum(x * y for x, y in zip(a, b))


_queries = {}


def _query_vector(query):
    """One turn ranks facts, lessons and past sessions against the same
    words - embed them once, not three times."""
    key = (_state["model"], query)
    vector = _queries.get(key)

    if vector is None:
        vector = _embed([config.EMBED_QUERY_PREFIX + query])[0]

        if len(_queries) > 16:
            _queries.clear()

        _queries[key] = vector

    return vector


def rank(query, facts):
    """[(score, fact)] best first, or None if it couldn't be done - the
    caller falls back to word matching on None, never on an empty list.

    The server normalises every vector, so a dot product is the cosine.
    """
    if not facts or not str(query or "").strip() or not available():
        return None

    try:
        vectors = _vectors(list(dict.fromkeys(facts)))
        q = _query_vector(str(query))
    except Exception as e:
        logbook.warn("embed", "falling back to word matching: %s", e)
        _state.update(up=False, checked=time.monotonic())

        return None

    scored = [(sum(a * b for a, b in zip(q, vectors[f])), f)
              for f in facts if f in vectors]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return scored


# ---------------------------------------------------------------------------
# The reranker
# ---------------------------------------------------------------------------
def reranker_available():
    """Is the reranker answering? Same cadence as available()."""
    now = time.monotonic()

    if _rerank["up"] is not None and now - _rerank["checked"] < RECHECK:
        return _rerank["up"]

    try:
        response = requests.get(config.RERANK_URL.split("/v1/")[0] + "/v1/models",
                                headers=config.EMBED_HEADERS, timeout=0.5)
        up = response.status_code == 200
        _rerank["model"] = ((response.json().get("data") or [{}])[0].get("id", "")
                            if up else "")
    except Exception:
        up = False

    if up != _rerank["up"]:
        logbook.info("embed", "reranker %s",
                     f"up ({_rerank['model']})" if up else "not answering")

    _rerank.update(up=up, checked=now)

    return up


def rerank(query, texts):
    """texts re-ordered best first by the reranker, or None if it isn't
    there or the request failed - the caller keeps its own order then."""
    if not texts or not reranker_available():
        return None

    try:
        response = requests.post(
            config.RERANK_URL, headers=config.EMBED_HEADERS,
            json={"model": _rerank["model"] or "rerank", "query": str(query),
                  "documents": list(texts)},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()["results"]
    except Exception as e:
        logbook.warn("embed", "rerank failed, keeping the embedding order: %s", e)
        _rerank.update(up=False, checked=time.monotonic())

        return None

    order = sorted(results, key=lambda r: r["relevance_score"], reverse=True)

    return [texts[r["index"]] for r in order if 0 <= r["index"] < len(texts)]


def select(query, facts, limit):
    """The facts for this turn, oldest first, or None to fall back.

    Same carve-out as the word matcher: the newest few always travel,
    because a fact learned two minutes ago is usually still in play.
    The rest are the closest in meaning above EMBED_MIN_SCORE - a
    floor, so a turn about nothing in particular doesn't drag in the
    least-unrelated trivia just because there was room. When more pass
    the floor than fit, the reranker (if it's running) picks which.
    """
    keep = max(1, limit // 3)
    recent = facts[-keep:]
    candidates = facts[:-keep]
    scored = rank(query, candidates)

    if scored is None:
        return None

    floor = float(getattr(config, "EMBED_MIN_SCORE", 0.35))
    slots = limit - keep
    passing = [f for score, f in scored if score >= floor]
    how = "by meaning"

    # More good matches than room: let the reranker choose which travel.
    # The floor still decides what's a match at all, so the reranker
    # never brings in more than the embedding alone would have.
    if len(passing) > slots:
        better = rerank(query, passing[:max(slots, int(getattr(config, "RERANK_CANDIDATES", 24)))])

        if better is not None:
            passing = better
            how = "by meaning, reranked"

    chosen = set(passing[:slots])

    logbook.info("embed", "recall %s: %d of %d facts (best %.2f)",
                 how, len(chosen), len(candidates), scored[0][0] if scored else 0)

    return [f for f in candidates if f in chosen] + recent
