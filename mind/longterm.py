import re
import threading
import requests

import config
from mind import factstore
from core import logbook

# The tunables are read as config.X at each use rather than imported by
# value, so /set changes actually reach them. memory: an older install's
# agent/memory.json, as config loaded it at startup.
from config import memory, LM_URL, LLM_HEADERS

# Facts live in agent/facts.db (mind/factstore.py). Older installs could
# keep a capped list in agent/memory.json instead. If this one did, its
# facts are read into facts.db once ever (facts.db remembers it did, so a
# fact you forget never comes back from the old file), and the file is
# never written again. Preferences in it are still read by
# config.user_preferences() until they're moved to agent.json.

_lock = threading.Lock()
_imported = [False]


def _was_on_json():
    """Was this install keeping its facts in memory.json? Its config.json
    said so, or facts.db has never held a fact. One already on sqlite had
    the old list read in when it switched, and reading it again now would
    bring back every fact forgotten since."""
    wanted = str((config.setting("long_term_memory", {}) or {}).get("backend", "")).lower()

    if wanted.startswith("json"):
        return True

    active, retired = factstore.counts()

    return active + retired == 0


def ready():
    """facts.db is open to use. The first time ever, an old memory.json's
    facts come in, if this install was still keeping them there."""
    if not factstore.available():
        return False

    if _imported[0]:
        return True

    # Held through the import: a second caller waits for the facts rather
    # than seeing an empty memory while they're still coming in.
    with _lock:
        if _imported[0]:
            return True

        old = memory.get("long_term_facts")

        try:
            if isinstance(old, list) and old and not factstore.meta("memory_json_imported"):
                moved = factstore.import_facts(old) if _was_on_json() else 0
                factstore.set_meta("memory_json_imported", moved)

                if moved:
                    logbook.info("longterm", "read %d fact(s) from the old memory.json into facts.db", moved)
        except Exception:
            # facts.db itself works; the import is tried again next start
            logbook.exception("longterm", "reading the old memory.json facts failed")

        _imported[0] = True

    return True


# A real "fact" is one short, plain sentence describing something
# durable about the user - not a full assistant reply. Caps length and
# rejects multi-line / in-character text so a model that ignores the
# "one short sentence" instruction in the extraction prompt can't dump
# an entire chatty reply (cat sounds, emoji, search results, etc.)
# straight into permanent memory.
_MAX_FACT_CHARS = 220
# Signs a "fact" is really a leaked piece of her reply. Not the names she
# calls you: "Ryan likes being called Senpai" is a fact, and "senpai" being
# on this list once threw it away (2026-11-15).
_VOICE_TELLS = ("mrrp", "nya~", "purring", "\U0001F63E".lower())

# You asking her outright to keep something: "remember this", "remember that
# I...", "don't forget", "keep in mind", "make a note".
# "remember", typed fast: remeber, rember, remmber, rememeber.
_REMEMBER = r"re?m[ea]?m?[ea]?m?b[ae]?r"
_ASKED = re.compile(r"\b(" + _REMEMBER + r" (this|that|my|i|i'm|im|me|we|our|it)\b|"
                    r"(don'?t|dont|do not) forget\b|"
                    r"keep (this |that |it )?in mind\b|make a note\b|note (this|that) down\b)", re.I)


_ASKED_QUESTION = re.compile(r"\b(do|did|can|could|would|will|don'?t) you (still )?" + _REMEMBER + r"\b", re.I)


def asked_to_remember(text):
    """Did you ask her to keep something? (Then a turn where she didn't
    call remember_fact still gets the extraction pass.)"""
    text = str(text or "")
    if _ASKED_QUESTION.search(text) and not re.search(r"\b" + _REMEMBER + r" (this|that)\s*[:,-]", text, re.I):
        return False            # "do you remember my birthday?" asks, it doesn't tell
    return bool(_ASKED.search(text))


def status():
    """One short line for the Memory row: what's in it."""
    if not config.LONG_TERM_MEMORY_ENABLED:
        return "off"

    if not ready():
        return "facts.db can't be opened"

    active, retired = factstore.counts()
    line = f"sqlite · {active} fact{'s' if active != 1 else ''}"

    return f"{line}, {retired} retired" if retired else line


def _announce():
    """Push the current status to the header. Lazy import: ui is a
    consumer of this module, not a dependency of it."""
    try:
        import ui

        ui.set_memory(status())
    except Exception:
        pass  # headless, or the UI isn't up yet


def _guest():
    """Someone other than the owner is talking this turn (senses/people.py): their
    name, and their facts are the ones used. None for the owner."""
    try:
        from senses import people

        return people.guest()
    except Exception:
        return None


def get_facts() -> list:
    guest = _guest()

    if guest:
        from senses import people

        return people.facts(guest)

    return factstore.active_facts() if ready() else []


# ---------------------------------------------------------------------------
# Choosing which facts to put in front of the model
#
# Every fact used to go into every system prompt. That is fine at thirty
# and wasteful at three hundred - and worse than wasteful, because a
# wall of unrelated trivia is exactly what makes a small model start
# answering questions nobody asked ("speaking of your cat...").
#
# Below the cap nothing changes and everything is sent. Above it, the
# facts that share vocabulary with what was just said are sent, plus the
# most recent few regardless - the newest facts are usually the ones
# still in play.
# ---------------------------------------------------------------------------
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "did",
    "do", "does", "for", "from", "had", "has", "have", "he", "her", "him",
    "his", "how", "i", "if", "in", "is", "it", "its", "me", "my", "not",
    "of", "on", "or", "our", "she", "so", "that", "the", "their", "them",
    "then", "there", "they", "this", "to", "was", "we", "were", "what",
    "when", "where", "which", "who", "why", "will", "with", "would",
    "you", "your", "am", "been", "being", "get", "got", "just", "like",
    "want", "need", "know", "think", "make", "let", "about",
}


def _words(text):
    return {
        word for word in re.findall(r"[a-z0-9']+", str(text).lower())
        if len(word) > 2 and word not in _STOPWORDS
    }


def relevant_facts(query, limit=None):
    """The facts worth showing for this turn, oldest first."""
    limit = limit or config.LONG_TERM_MEMORY_CONTEXT_FACTS
    _announce()  # cheap, and it catches edits made in the memory manager

    # By meaning first, when the embedding server is running and there are
    # more facts than fit - under the limit every fact travels anyway.
    # None means it couldn't (server down, request failed), and the
    # word matching below takes over exactly as before.
    facts = get_facts()

    if _guest():
        return _by_words(facts, query, limit)   # their own few facts, never the owner's

    if len(facts) > limit:
        try:
            from mind import embedmem

            chosen = embedmem.select(query, facts, limit)
        except Exception:
            chosen = None

        if chosen is not None:
            return chosen

    if ready():
        found = factstore.search(query, limit)

        if found is not None:          # None: no FTS5 here, the word ranking below does it
            return found

    return _by_words(facts, query, limit)


def _by_words(facts, query, limit):
    """Facts sharing vocabulary with the query, plus the newest few."""
    if len(facts) <= limit:
        return facts

    # The newest few always travel, relevant or not.
    keep = max(1, limit // 3)
    recent = facts[-keep:]
    candidates = facts[:-keep]

    terms = _words(query)

    if not terms:
        return facts[-limit:]

    scored = []

    for index, fact in enumerate(candidates):
        overlap = terms & _words(fact)

        if not overlap:
            continue

        # Favour the fact that says more about fewer things - a short
        # fact sharing two words beats a rambling one sharing three.
        score = len(overlap) / (1 + len(_words(fact)) ** 0.5)
        scored.append((score, index, fact))

    scored.sort(reverse=True)
    chosen = {index for _score, index, _fact in scored[:limit - keep]}

    return [f for i, f in enumerate(candidates) if i in chosen] + recent


# ---------------------------------------------------------------------------
# Editing what's remembered
#
# Adding was the only thing possible before, which meant a fact she
# misheard was permanent short of hand-editing her memory. Both of
# these take a phrase rather than an index, for the same reason
# set_reminder takes one: the model is good at repeating what was said
# and bad at bookkeeping.
# ---------------------------------------------------------------------------
def find_fact(phrase):
    """Best match for a loose description. Returns (index, fact) or
    (None, candidates) when it's too close to call."""
    facts = get_facts()

    if not facts:
        return None, []

    phrase = str(phrase or "").strip()
    lowered = phrase.lower()

    if not lowered:
        return None, []

    # An exact or containing match wins outright.
    for index, fact in enumerate(facts):
        if fact.lower() == lowered:
            return index, fact

    contains = [
        (index, fact) for index, fact in enumerate(facts)
        if lowered in fact.lower() or fact.lower() in lowered
    ]

    if len(contains) == 1:
        return contains[0]

    terms = _words(phrase)

    if not terms:
        return None, [fact for _index, fact in contains]

    scored = sorted(
        (
            (len(terms & _words(fact)) / (1 + len(terms ^ _words(fact))),
             index, fact)
            for index, fact in enumerate(facts)
        ),
        reverse=True,
    )

    best = [entry for entry in scored if entry[0] > 0]

    if not best:
        return None, []

    # Clearly ahead of the runner-up, or it's a guess not worth making.
    if len(best) == 1 or best[0][0] >= best[1][0] * 1.5:
        return best[0][1], best[0][2]

    return None, [fact for _score, _index, fact in best[:4]]


def forget_fact(phrase):
    """Remove one fact. Returns (removed_text, candidates).

    This really deletes, rather than retiring. "Forget that" is the one case
    where keeping a retired copy would be the opposite of what was
    asked."""
    index, found = find_fact(phrase)

    if index is None:
        return None, found

    guest = _guest()

    if guest:
        from senses import people

        return (found, []) if people.set_fact(guest, found, None) else (None, [])

    if not ready():
        return None, []

    removed = factstore.remove(found)
    _announce()
    return (found, []) if removed else (None, [])


def update_fact(phrase, replacement):
    """Correct one fact in place. Returns (old, new) or (None, candidates)."""
    replacement = str(replacement or "").strip()

    if not _looks_like_valid_fact(replacement):
        return None, []

    index, found = find_fact(phrase)

    if index is None:
        return None, found

    guest = _guest()

    if guest:
        from senses import people

        return ((found, replacement), []) if people.set_fact(guest, found, replacement) else (None, [])

    # A correction, not a change in the world - rewritten in place
    # rather than superseded, so no history row.
    if ready() and factstore.update(found, replacement):
        return (found, replacement), []

    return None, []


def why_not(fact):
    """Why add_fact would turn this fact away, in words she can repeat;
    "" when it wouldn't on these grounds (it may still be known already)."""
    fact = str(fact or "").strip()
    if not fact or fact.upper() == "NONE":
        return "it was empty"
    if len(fact) > _MAX_FACT_CHARS:
        return f"it's too long (keep it under {_MAX_FACT_CHARS} characters, one sentence)"
    if "\n" in fact:
        return "it's more than one line"
    if any(tell in fact.lower() for tell in _VOICE_TELLS):
        return "it reads like part of your reply, not a fact"
    return ""


def _looks_like_valid_fact(fact: str) -> bool:
    if not fact or fact.upper() == "NONE":
        return False
    if len(fact) > _MAX_FACT_CHARS:
        return False
    if "\n" in fact:  # a real fact is one line - multi-line means a leaked reply
        return False
    lowered = fact.lower()
    if any(tell in lowered for tell in _VOICE_TELLS):
        return False
    return True


def add_fact(fact: str, subject: str = "") -> bool:
    """Returns True if the fact was stored, False if rejected or already
    known - the remember_fact tool reports that back to the model."""
    fact = fact.strip()
    if not _looks_like_valid_fact(fact):
        return False
    guest = _guest()
    if guest:
        from senses import people

        return people.add_fact(guest, fact)
    if not ready():
        return False
    # No cap - permanence is the point.
    stored = factstore.add(fact, subject)
    _announce()
    return stored


def _strip_think(text):
    """LM Studio with reasoning parsing off sends the scratchpad inline."""
    return re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.IGNORECASE | re.DOTALL).strip()


def _ask_extractor(model, prompt):
    from core import lmstudio

    response = requests.post(
        LM_URL, headers=LLM_HEADERS,
        json=lmstudio.chore({"model": model,
                             "messages": [{"role": "user", "content": prompt}]},
                            max_tokens=300),
        timeout=120,
    )

    return _strip_think(response.json()["choices"][0]["message"].get("content") or "")


def _extract_fact_sqlite(model, user_text, answer, asked=False):
    """Extraction with the table in charge: the model may also notice
    that a new statement makes an old fact false.

    The old prompt could only answer "new fact" or "nothing", so "I got
    a 7900 XTX" landed *next to* "Ryan has a 6950 XT" and both got
    served forever after. Here the model gets a third verb - and the
    facts it might be contradicting are chosen by the same search the
    conversation uses, not the last 25 by age, which stops working the
    moment the table outgrows its window.

    Every parse failure degrades toward add(): the worst outcome of a
    mangled reply is the coexistence bug we already had, never a lost
    fact and never a wrongly retired one.
    """
    query = f"{user_text} {answer}"
    known = factstore.search(query, limit=12)
    if known is None:                   # no FTS5: the same word ranking the conversation uses
        known = _by_words(factstore.active_facts(), query, 12)
    known_block = ""

    if known:
        known_block = (
            "Facts already remembered that may be relevant:\n"
            + "\n".join(f"- {f}" for f in known)
            + "\n\n"
        )

    used = factstore.subjects()
    subject_line = (
        "Reuse one of these subjects when it fits: " + ", ".join(used) + ". "
        if used else ""
    )

    prompt = (
        "You are deciding whether to permanently remember something from "
        "this exchange. Be strict - most exchanges contain nothing worth "
        "permanently remembering. Only report a fact if it is durable and "
        "specific (identity, an explicitly stated preference, a concrete "
        "standing project or commitment) - NOT routine chit-chat.\n\n"
        f"{known_block}"
        "Reply with exactly ONE line, in one of these three forms:\n"
        "NONE\n"
        "NEW | <one-word subject> | <the fact, one short sentence>\n"
        "REPLACE | <the old fact, copied exactly from the list above> | "
        "<the new fact, one short sentence>\n\n"
        "Use REPLACE only when the exchange shows a listed fact is no "
        "longer true (something was replaced, changed, ended). If both "
        "could still be true at once, use NEW. "
        f"{subject_line}"
        + ("The user explicitly asked for something here to be remembered: report "
           "it unless it is already in the list above.\n\n" if asked else
           "When in doubt, reply NONE.\n\n")
        + f"User: {user_text}\nAssistant: {answer}"
    )

    try:
        raw = _ask_extractor(model, prompt)
    except Exception as e:
        # Never breaks the conversation, but say why in the log: a wrong
        # model name here means no fact is ever learned.
        logbook.info("longterm", "fact extraction failed: %s", e)
        return

    # A reasoning model may think out loud first; the answer is the
    # last non-empty line once any <think> block is gone.
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    if not lines:
        return

    line = lines[-1]

    if line.upper() == "NONE":
        return

    parts = [p.strip() for p in line.split("|")]
    verb = parts[0].upper()

    if verb == "REPLACE" and len(parts) >= 3:
        old, new = parts[1], parts[-1]

        if not _looks_like_valid_fact(new):
            return

        # Exact echo first; the fuzzy matcher when the model reworded
        # the old fact, which it will.
        if factstore.replace(old, new):
            logbook.info("longterm", "superseded: %r -> %r", old, new)
            _announce()

            return

        index, found = find_fact(old)

        if index is not None and factstore.replace(found, new):
            logbook.info("longterm", "superseded: %r -> %r", found, new)
            _announce()

            return

        add_fact(new)  # couldn't place the old one - degrade to coexist

        return

    if verb == "NEW" and len(parts) >= 2:
        subject = parts[1] if len(parts) >= 3 else ""

        if len(subject.split()) > 1:  # that's a fact, not a subject
            subject = ""

        if _looks_like_valid_fact(parts[-1]):
            add_fact(parts[-1], subject)

        return

    # Not in the format at all - an older-style bare fact still counts.
    if len(parts) == 1 and _looks_like_valid_fact(line):
        add_fact(line)


def _extract_fact(model, user_text, answer, asked=False):
    if not _guest():
        if ready():
            _extract_fact_sqlite(model, user_text, answer, asked)
        return

    # A guest's facts (senses/people.py): the simpler new-fact-or-nothing ask.

    existing = get_facts()
    existing_block = ""
    if existing:
        existing_block = (
            "Facts already remembered (do NOT log anything that repeats "
            "or reworders any of these):\n"
            + "\n".join(f"- {f}" for f in existing[-25:])
            + "\n\n"
        )

    prompt = (
        "You are deciding whether to permanently remember something from "
        "this exchange. Be strict - most exchanges contain nothing worth "
        "permanently remembering. Only report a fact if it is durable and "
        "specific (identity, an explicitly stated preference, a concrete "
        "standing project or commitment) - NOT routine chit-chat, and NOT "
        "already covered by the existing facts below in different words.\n\n"
        f"{existing_block}"
        "If this exchange contains a genuinely new, specific, durable "
        "fact, reply with ONLY that fact as one short sentence. Otherwise "
        "reply with exactly NONE. When in doubt, reply NONE.\n\n"
        f"User: {user_text}\nAssistant: {answer}"
    )
    try:
        from core import lmstudio

        response = requests.post(
            LM_URL, headers=LLM_HEADERS,
            json=lmstudio.chore({"model": model,
                                 "messages": [{"role": "user", "content": prompt}]},
                                max_tokens=120),
            timeout=120,
        )
        result = _strip_think(response.json()["choices"][0]["message"].get("content") or "")
    except Exception as e:
        logbook.info("longterm", "fact extraction failed: %s", e)
        return  # extraction failing shouldn't ever break the conversation

    if _looks_like_valid_fact(result):
        add_fact(result)


def extract_in_background(model, user_text, answer, asked=False):
    if not config.LONG_TERM_MEMORY_ENABLED:
        return
    from core import turnctx

    # The thread starts with no turn of its own: carry who was talking,
    # so a guest's fact lands in their file and not the owner's.
    speaker = turnctx.current().speaker
    try:
        from senses import people

        if speaker == people.STRANGER:
            return              # nobody to keep facts for: skip the model call
    except Exception:
        pass

    def run():
        # Its own thread: a locked facts.db or a full disk here printed a
        # traceback over the screen, once per turn.
        try:
            with turnctx.begin(source="extract", private=True, speaker=speaker):
                _extract_fact(model, user_text, answer, asked)
        except Exception:
            logbook.exception("longterm", "fact extraction failed")

    threading.Thread(target=run, daemon=True).start()