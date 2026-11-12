"""Cards: a short summary of a person, in her prompt whenever she's talking to them.

Her facts are single lines, and only the ones that match your message go
in the prompt. A card is the other half: a few sentences she wrote herself,
while idle, from everything she has on you - who you are to her, what you
do, what matters to you, how you like to be helped - so the gist is always
there even when the message doesn't touch it.

    Ryan runs Luna on his Fedora desktop and an Unraid server he's moving
    her model onto. He builds her himself, prefers plain talk to fuss,
    and hates tools that censor an idea. Shannon is his wife...

It stays the same from turn to turn (it's only rewritten in the idle dream
pass, and only when the facts under it changed), so it sits in the part of
the prompt llama-server reuses (llm.stable_prompt).

Who gets one: you, from your facts (three or more), and each person she
knows by voice or face, from theirs. On someone else's turn she sees their
card, never yours; a stranger or someone met this session gets none.

    /card                 the cards she has
    /card <name>          read one (/card me for yours)
    /card rebuild         rewrite them on her next idle pass (/reflect does it now)
    /card forget <name>   drop one (it comes back if the facts are still there)

Kept in agent/notebook.db (gitignored), beside her pages. Facts stay the
source of truth: a card is a summary she can always rewrite.
"""
import hashlib
import re
from datetime import datetime

import config
from core import logbook

MIN_FACTS = 3
MAX_FACTS = 150                      # newest first; a card is a gist, not an index
PER_PASS = 3
OWNER = "\x00owner"                  # your card's key: never a name anyone can enroll

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    person   TEXT PRIMARY KEY,
    text     TEXT NOT NULL,
    sources  TEXT NOT NULL,
    facts    INTEGER NOT NULL DEFAULT 0,
    updated  TEXT NOT NULL
);
"""


def enabled():
    return config.current("self.card") is not False


def _run(fn, default=None):
    from mind import notebook

    def go(conn):
        conn.executescript(_SCHEMA)
        return fn(conn)
    return notebook._run(go, default)


def _owner_name():
    return str(getattr(config, "USER", "") or "the user")


def label(person):
    return _owner_name() if person == OWNER else person


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def cards():
    """{person: {"text", "facts", "updated"}}; yours first."""
    rows = _run(lambda c: c.execute("SELECT person, text, facts, updated FROM cards").fetchall(), [])
    found = {r[0]: {"text": r[1], "facts": r[2], "updated": r[3]} for r in rows}
    return dict(sorted(found.items(), key=lambda kv: (kv[0] != OWNER, kv[0].lower())))


def _find(name):
    want = str(name or "").strip().lower()
    if want in ("me", "mine", "my", _owner_name().lower()):
        return OWNER
    return next((p for p in cards() if p != OWNER and p.lower() == want), None)


def get(name):
    return cards().get(_find(name) or "")


def forget(name):
    found = _find(name)
    if found and found in cards():
        _run(lambda c: c.execute("DELETE FROM cards WHERE person=?", (found,)))
        return label(found)
    return None


def rebuild_all():
    """Mark every card stale, so the next idle pass rewrites them."""
    return _run(lambda c: c.execute("UPDATE cards SET sources=''").rowcount, 0)


# ---------------------------------------------------------------------------
# What each card is written from
# ---------------------------------------------------------------------------
def _owner_facts():
    from mind import factstore, longterm

    if longterm.backend() == "sqlite" and factstore.available():
        facts = [r[1] for r in factstore.rows(limit=MAX_FACTS)]          # newest first, active only
        facts.reverse()
    else:
        facts = list(longterm.get_facts())[-MAX_FACTS:]
    try:
        from config import memory

        prefs = memory.get("user_preferences") or {}
        facts += [f"Prefers {k}: {v}" for k, v in prefs.items()]
    except Exception:
        pass
    return facts


def _material():
    """({person: [facts]}, complete): complete is False when something
    couldn't be read, so nobody's card is dropped for a read that failed."""
    out, complete = {}, True
    try:
        mine = _owner_facts()
        if len(mine) >= MIN_FACTS:
            out[OWNER] = mine
    except Exception:
        logbook.exception("cards", "couldn't read your facts")
        complete = False
    try:
        from senses import people

        for name, person in people.everyone().items():
            theirs = [str(f) for f in (person.get("facts") or []) if str(f).strip()][-MAX_FACTS:]
            if len(theirs) >= MIN_FACTS and name != people.STRANGER and not people.is_owner(name):
                out[name] = theirs
    except Exception:
        logbook.exception("cards", "couldn't read the people she knows")
        complete = False
    return out, complete


def material():
    """{person: [facts]} for everyone with enough behind them: you, and the
    people she knows by voice or face (not someone met this session)."""
    return _material()[0]


def missing():
    """Has someone with enough facts no card yet, or one marked for rewriting
    (/card rebuild)? Then the idle loop writes it without waiting for the
    next dream pass, which can be most of a day away."""
    if not enabled():
        return False
    try:
        stale = set(_run(lambda c: [r[0] for r in c.execute("SELECT person FROM cards WHERE sources=''")], []))
        return bool((set(material()) - set(cards())) | (stale & set(material())))
    except Exception:
        return False


def _sources(facts):
    return hashlib.sha1("\n".join(facts).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Writing (from the idle dream pass)
# ---------------------------------------------------------------------------
def _prompt(person, facts):
    who = label(person)
    owner = _owner_name()
    lines = [f"Everything you have saved about {who}:", ""]
    lines += [f"- {f}" for f in facts]
    lines += ["",
              f"Write yourself a short card on {who}: who they are"
              + ("" if person == OWNER else f" (to you and to {owner})")
              + ", what they do, what matters to them, and how they like to be talked to and helped. "
              "3 to 5 sentences, under 90 words, plain text. Use only what's above; don't guess or add "
              "anything, and leave out passing details. No heading, no list, no preamble: start with the card."]
    return "\n".join(lines)


def _clean(text):
    text = re.sub(r"^\s*(here'?s|card|sure)[^:\n]*:\s*", "", str(text or "").strip(), flags=re.I)
    text = " ".join(text.split())
    return text[:700]


def write(ask, yield_=lambda: None, report=None, limit=PER_PASS):
    """Write or refresh the cards whose facts changed. ask(prompt) -> text.
    Returns the people written. yield_() raises to stop when a turn starts."""
    if not enabled():
        return []
    have = _run(lambda c: dict(c.execute("SELECT person, sources FROM cards").fetchall()), {})
    wanted, complete = _material()
    for gone in (set(have) - set(wanted)) if complete else ():
        _run(lambda c, g=gone: c.execute("DELETE FROM cards WHERE person=?", (g,)))
    written = []
    for person, facts in wanted.items():               # yours first
        if len(written) >= limit:
            break
        sources = _sources(facts)
        if have.get(person) == sources:
            continue
        yield_()
        try:
            text = _clean(ask(_prompt(person, facts)))
        except Exception as e:
            logbook.warn("cards", "writing %s's card failed: %s", label(person), e)
            break
        if len(text) < 20:
            continue
        _run(lambda c: c.execute(
            "INSERT OR REPLACE INTO cards (person, text, sources, facts, updated) VALUES (?,?,?,?,?)",
            (person, text, sources, len(facts), datetime.now().isoformat(timespec="seconds"))))
        written.append(label(person))
        if report:
            report(f"Card on {label(person)}: {text[:120]}{'...' if len(text) > 120 else ''}")
    return written


# ---------------------------------------------------------------------------
# Into the prompt
# ---------------------------------------------------------------------------
def for_turn():
    """(name, text) for whoever she's talking to this turn, or None. You get
    yours; someone she knows gets theirs; a stranger or someone met this
    session gets none, and nobody but you ever gets yours."""
    if not enabled():
        return None
    from core import turnctx
    from senses import people

    speaker = turnctx.current().speaker
    if not speaker:
        person = OWNER
    elif speaker == people.STRANGER or people.session_guest(speaker) is not None:
        return None
    else:
        person = speaker
    card = cards().get(person)
    return (label(person), card["text"]) if card else None


def prompt_block():
    found = for_turn()
    if not found:
        return ""
    name, text = found
    return (f"Your card on {name} (your own summary of what you know; a fact that says "
            f"otherwise wins):\n{text}\n")
