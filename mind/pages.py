"""Pages: one short note per subject she knows a lot about.

Facts are single sentences, saved one at a time over months. That's the
right way to collect them and the wrong way to think with them: on a
question about the server build, a small model gets six unrelated-looking
lines and has to join them up mid-reply. A page is that joining-up done
ahead of time, while she's idle:

    the server build: a second RX 6950 XT is ordered for the Unraid box.
    Ryan worries llama will starve his media server, so it gets a memory
    cap and runs training at night. Patches are planned for it.

What gets a page: a subject tag on three or more of your facts
("hardware"), or a name that turns up in three or more ("Shannon").
What goes in: those facts, plus her notes on past conversations that are
about it. She writes it in the idle dream pass (mind/reflect.py), a few
at a time, and only rewrites one when something under it changed.

What it's for: when your message touches a subject, by name or by
meaning, its page rides along in her prompt (self.pages_in_prompt, 2).
Only on your own turns, never a guest's or stream chat's, the same as
your facts.

    /pages               the pages she has
    /pages <subject>     read one
    /pages rebuild       rewrite them all on her next idle pass
    /pages forget <s>    drop one (it comes back if the facts still call for it)

Kept in agent/notebook.db (gitignored). Facts stay the source of truth:
a page is a summary she can always rewrite, never a place a fact lives.
"""
import hashlib
import re

import config
from core import logbook

MIN_FACTS = 3
PER_PASS = 3
_WORD = re.compile(r"\b[A-Z][a-z]{2,}\b")
_FIRST = re.compile(r"^\W*([A-Z][a-z]{2,})\b")
_VAGUE_TAGS = {"general", "misc", "other", "none", "unknown", "fact", "facts", "user", "info"}
_NOT_NAMES = {"The", "And", "But", "His", "Her", "Hers", "She", "They", "Their", "When", "Then", "This",
              "That", "With", "From", "For", "Has", "Had", "Was", "Wants", "Likes", "Loves", "Uses",
              "Prefers", "Doesn", "Didn", "Isn", "Wasn", "Can", "Will", "Would", "Should", "Also",
              "Every", "Each", "Some", "Most", "Not", "Never", "Always", "Mon", "Tue", "Wed", "Thu",
              "Fri", "Sat", "Sun", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
              "Sunday", "January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    subject  TEXT PRIMARY KEY,
    text     TEXT NOT NULL,
    sources  TEXT NOT NULL,
    facts    INTEGER NOT NULL DEFAULT 0,
    updated  TEXT NOT NULL
);
"""


def enabled():
    v = config.current("self.pages")
    return v is not False


def _run(fn, default=None):
    from mind import notebook

    def go(conn):
        conn.executescript(_SCHEMA)
        return fn(conn)
    return notebook._run(go, default)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def pages():
    """{subject: {"text", "facts", "updated"}}, alphabetical."""
    rows = _run(lambda c: c.execute("SELECT subject, text, facts, updated FROM pages ORDER BY subject").fetchall(), [])
    return {r[0]: {"text": r[1], "facts": r[2], "updated": r[3]} for r in rows}


def get(subject):
    return pages().get(_find(subject) or "")


def _find(subject):
    want = str(subject or "").strip().lower()
    return next((s for s in pages() if s.lower() == want), None)


def forget(subject):
    found = _find(subject)
    if found:
        _run(lambda c: c.execute("DELETE FROM pages WHERE subject=?", (found,)))
    return found


def rebuild_all():
    """Mark every page stale, so the next idle pass rewrites them."""
    return _run(lambda c: c.execute("UPDATE pages SET sources=''").rowcount, 0)


# ---------------------------------------------------------------------------
# What deserves a page
# ---------------------------------------------------------------------------
def _facts():
    from mind import factstore, longterm

    if longterm.backend() == "sqlite" and factstore.available():
        return [(r[1], r[2] or "") for r in factstore.rows(limit=2000)]      # (fact, subject), active only
    return [(f, "") for f in longterm.relevant_facts("")]


def _names(facts, skip):
    """Capitalised words that are names. Facts are often written without a subject ("Runs an
    Unraid server"), so a word seen only at the start of a sentence that looks like a verb
    (ends in s, ed or ing) doesn't count; "Shannon uses an iMac" still makes Shannon a name.
    Anywhere else in a sentence, a capital means a name."""
    inside, starts = set(), set()
    for fact in facts:
        first = _FIRST.match(fact)
        start = first.start(1) if first else -1
        for m in _WORD.finditer(fact):
            (starts if m.start() == start else inside).add(m.group())
    verbish = {w for w in starts - inside if re.search(r"(s|ed|ing)$", w)}
    return (inside | starts) - verbish - skip


def subjects(facts=None):
    """{subject: [facts]} for every subject with enough behind it. A tag and a name that
    are the same word ("shannon", "Shannon") are one subject."""
    facts = _facts() if facts is None else facts
    skip = {str(getattr(config, n, "") or "").strip() for n in ("USER", "USER_NAME", "AGENT_NAME")} | _NOT_NAMES
    names = _names([f for f, _t in facts], skip)
    found, label = {}, {}
    for fact, tag in facts:
        tag = str(tag or "").strip().lower()
        if tag and tag not in _VAGUE_TAGS:
            found.setdefault(tag, []).append(fact)
            label.setdefault(tag, tag)
        for name in set(_WORD.findall(fact)) & names:
            found.setdefault(name.lower(), []).append(fact)
            label[name.lower()] = name                  # a name's capitals win over a tag's
    out = {}
    for key, items in found.items():
        unique = list(dict.fromkeys(items))
        if len(unique) >= MIN_FACTS:
            out[label[key]] = unique
    return out


def _episodes(subject):
    from mind import notebook
    try:
        return notebook.search_episodes(subject, limit=3, floor=0.45, min_words=1)
    except Exception:
        return []


def _sources(facts, episodes):
    key = "\n".join(sorted(facts)) + "|" + ",".join(str(e["id"]) for e in episodes)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Writing (from the idle dream pass)
# ---------------------------------------------------------------------------
def _prompt(subject, facts, episodes):
    user = getattr(config, "USER", "the user")
    lines = [f"Everything you have saved that has to do with {subject}:", ""]
    lines += [f"- {f}" for f in facts]
    if episodes:
        lines += ["", "Your notes from conversations about it:"]
        lines += [f"- {e['summary']}" for e in episodes]
    lines += ["",
              f"Write yourself a short note on {subject}, 3 to 6 sentences of plain text: what or who it is "
              f"to {user}, how the pieces connect, what's current, and anything still unresolved. Use only "
              "what's above; don't guess or add anything. No heading, no list, no preamble: start with the note."]
    return "\n".join(lines)


def _clean(text):
    text = re.sub(r"^\s*(here'?s|note|sure)[^:\n]*:\s*", "", str(text or "").strip(), flags=re.I)
    text = " ".join(text.split())
    return text[:900]


def write(ask, yield_=lambda: None, report=None, limit=PER_PASS):
    """Write or refresh the pages whose material changed. ask(prompt) -> text.
    Returns the subjects written. yield_() raises to stop when a turn starts."""
    if not enabled():
        return []
    have = _run(lambda c: dict(c.execute("SELECT subject, sources FROM pages").fetchall()), {})
    written = []
    wanted = subjects()
    # pages whose subject no longer has enough behind it go
    for gone in set(have) - set(wanted):
        _run(lambda c, g=gone: c.execute("DELETE FROM pages WHERE subject=?", (g,)))
    # most material first: the subjects that matter most get written first
    for subject, facts in sorted(wanted.items(), key=lambda kv: -len(kv[1])):
        if len(written) >= limit:
            break
        episodes = _episodes(subject)
        sources = _sources(facts, episodes)
        if have.get(subject) == sources:
            continue
        yield_()
        try:
            text = _clean(ask(_prompt(subject, facts, episodes)))
        except Exception as e:
            logbook.warn("pages", "writing %s failed: %s", subject, e)
            break
        if len(text) < 20:
            continue
        from datetime import datetime
        _run(lambda c: c.execute(
            "INSERT OR REPLACE INTO pages (subject, text, sources, facts, updated) VALUES (?,?,?,?,?)",
            (subject, text, sources, len(facts), datetime.now().isoformat(timespec="seconds"))))
        written.append(subject)
        if report:
            report(f"Page on {subject}: {text[:120]}{'...' if len(text) > 120 else ''}")
    return written


# ---------------------------------------------------------------------------
# Into the prompt
# ---------------------------------------------------------------------------
def relevant(query, limit=None):
    """[(subject, text)] for this turn: a subject named in your message first, then the
    closest by meaning, if close enough."""
    if not enabled() or not str(query or "").strip():
        return []
    if limit is None:
        v = config.current("self.pages_in_prompt")
        limit = 2 if v is None else int(v)                  # 0 means none, not the default
    all_pages = pages()
    if not all_pages or limit <= 0:
        return []
    said = str(query).lower()
    named = [s for s in all_pages if re.search(r"\b" + re.escape(s.lower()) + r"\b", said)]
    picked = named[:limit]
    if len(picked) < limit:
        rest = {s: p["text"] for s, p in all_pages.items() if s not in picked}
        try:
            from mind import embedmem
            scored = embedmem.rank(query, list(rest.values())) if rest else None
        except Exception:
            scored = None
        for score, text in scored or []:
            if len(picked) >= limit or score < 0.5:
                break
            subject = next((s for s, t in rest.items() if t == text and s not in picked), None)
            if subject:
                picked.append(subject)
    return [(s, all_pages[s]["text"]) for s in picked]


def prompt_block(query):
    from core import turnctx

    if turnctx.current().speaker:            # a guest: your pages are yours, like your facts
        return ""
    found = relevant(query)
    if not found:
        return ""
    return "\nYour own notes, joined up from what you've learned (summaries; the facts above win if they differ):\n" + \
        "\n".join(f"- {subject}: {text}" for subject, text in found) + "\n"
