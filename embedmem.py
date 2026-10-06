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


def rank(query, facts):
    """[(score, fact)] best first, or None if it couldn't be done - the
    caller falls back to word matching on None, never on an empty list.

    The server normalises every vector, so a dot product is the cosine.
    """
    if not facts or not str(query or "").strip() or not available():
        return None

    try:
        vectors = _vectors(list(dict.fromkeys(facts)))
        q = _embed([config.EMBED_QUERY_PREFIX + str(query)])[0]
    except Exception as e:
        logbook.warn("embed", "falling back to word matching: %s", e)
        _state.update(up=False, checked=time.monotonic())

        return None

    scored = [(sum(a * b for a, b in zip(q, vectors[f])), f)
              for f in facts if f in vectors]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return scored


def select(query, facts, limit):
    """The facts for this turn, oldest first, or None to fall back.

    Same carve-out as the word matcher: the newest few always travel,
    because a fact learned two minutes ago is usually still in play.
    The rest are the closest in meaning above EMBED_MIN_SCORE - a
    floor, so a turn about nothing in particular doesn't drag in the
    least-unrelated trivia just because there was room.
    """
    keep = max(1, limit // 3)
    recent = facts[-keep:]
    candidates = facts[:-keep]
    scored = rank(query, candidates)

    if scored is None:
        return None

    floor = float(getattr(config, "EMBED_MIN_SCORE", 0.35))
    chosen = {f for score, f in scored[:limit - keep] if score >= floor}

    logbook.info("embed", "recall by meaning: %d of %d facts (best %.2f)",
                 len(chosen), len(candidates), scored[0][0] if scored else 0)

    return [f for f in candidates if f in chosen] + recent
