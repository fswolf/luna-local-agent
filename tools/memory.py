"""What she knows about you, and what she can look up.

The editing tools take a loose description rather than an index,
for the same reason set_reminder takes words: the model is good
at repeating what was said and bad at bookkeeping.
"""
import functools

import config
from mind import factstore, longterm
from core import transcript

from . import tool


def _hers(fn):
    """Changes made through her tools are logged as hers (factstore's audit log)."""
    @functools.wraps(fn)        # (the tool call checks the arguments against its signature)
    def run(*args, **kwargs):
        with factstore.acting("her tools"):
            return fn(*args, **kwargs)
    return run


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
@tool(
    "remember_fact",
    "Save one durable fact about the user for future conversations - a "
    "preference, a project, something about their life. Only for things "
    "worth recalling weeks later, not passing details of this chat.",
    {
        "fact": {
            "type": "string",
            "description": "The fact, written as a short third-person "
                           f"statement, e.g. '{config.USER_NAME or 'The user'} streams as a VTuber'.",
        },
        "since": {
            "type": "string",
            "description": "Only when the user said when it became true: the date as "
                           "YYYY-MM-DD, YYYY-MM or YYYY, worked out from today's date. "
                           "Leave it out rather than guess.",
        },
        "again": {
            "type": "boolean",
            "description": "Only when the user told you to forget this before and has now asked "
                           "for it to be remembered again.",
        },
    },
    required=("fact",),
)
@_hers
def _remember_fact(fact, since="", again=False):
    if longterm.add_fact(fact, since=since, again=_yes(again)):
        return f"Saved: {fact}" + _date_note(since) + _reminder_offer(fact)

    why = longterm.why_not(fact)

    return f"Not saved: {why}." if why else "Not saved: you already know that (it's in your memory)."

def _yes(value):
    """A boolean argument, however the model sent it ("false" is a word, and truthy)."""
    return value is True or str(value).strip().lower() in ("true", "yes", "1")


def _reminder_offer(fact):
    """A fact with a date coming up ("Shannon's birthday is March 3"): ask once
    about a reminder (life/offers.py). Your own turns only."""
    try:
        from life import offers
        return offers.on_save(fact)
    except Exception:
        return ""


def _date_note(since):
    """What became of a date she gave: kept, or not understood."""
    if not str(since or "").strip():
        return ""
    kept = factstore.when(since)
    return f" (true since {kept})" if kept else (
        f" (the date {since!r} wasn't understood, so it was saved without one: "
        "use YYYY-MM-DD, YYYY-MM or YYYY)")


# `about` arrived with the fact table. Without it this tool was a
# SELECT * - fine at thirty facts, a context bomb at three thousand.
# It stays optional so "what do you know about me" still works, but a
# bare call now returns the newest slice rather than everything.
@tool(
    "recall_facts",
    "Search what has been remembered about the user. Pass `about` to "
    "look something up ('gpu', 'streaming'); omit it for the most "
    "recently learned facts. Set `past` for what used to be true too "
    "('what was my last graphics card?', 'what did I have in October?').",
    {
        "about": {
            "type": "string",
            "description": "What to look for, in plain words. Optional.",
        },
        "past": {
            "type": "boolean",
            "description": "Also show facts that are no longer true, with when. Needs `about`.",
        },
    },
)
def _recall_facts(about="", past=False):
    about = str(about or "").strip()

    if about and _yes(past):
        found = longterm.history(about)
        if not found:
            return f"Nothing remembered about {about!r}, then or now."
        return "\n".join(_then_and_now(f) for f in found) + (
            "\n(\"learned\" and \"stopped believing\" are when you heard and when you updated it; "
            "only \"true from/to\" are real dates the user gave.)")

    if about:
        facts = longterm.relevant_facts(about, limit=10)

        if not facts:
            return f"Nothing remembered about {about!r}."
    else:
        facts = longterm.get_facts()[-15:]

        if not facts:
            return "Nothing saved yet."

    known = longterm.details(facts)
    listing = "\n".join(f"- {longterm.shown(f, known.get(f))}" for f in facts)
    return listing + ("\n" + longterm.UNSURE_NOTE.strip() if any(not d[2] for d in known.values()) else "")


def _then_and_now(f):
    """One line of history: the fact, now or then, and its dates."""
    real = " ".join(x for x in (f"true from {f['since']}" if f["since"] else "",
                                f"to {f['until']}" if f["until"] else "",
                                "" if f.get("sure", True) else "(not sure)") if x)
    if f["active"]:
        return f"- NOW: {f['fact']} (learned {f['learned']}{'; ' + real if real else ''})"
    return (f"- BEFORE: {f['fact']} (learned {f['learned']}, stopped believing {f['retired']}"
            f"{'; ' + real if real else ''})")


@tool(
    "forget_fact",
    "Delete something remembered about the user, when they say it is "
    "wrong or ask you to forget it. Describe the fact in your own "
    "words - you do not need to quote it exactly.",
    {
        "about": {
            "type": "string",
            "description": "Roughly what the fact says, e.g. 'works at "
                           "the bakery'.",
        },
    },
    required=("about",),
)
@_hers
def _forget_fact(about):
    removed, candidates = longterm.forget_fact(about)

    if removed:
        return f"Forgotten: {removed}"

    if candidates:
        listing = "\n".join(f"- {c}" for c in candidates)

        return (
            f"More than one could be it:\n{listing}\nAsk the user which "
            "one, then call this again with wording closer to theirs."
        )

    return f"Nothing remembered matches {about!r}. Nothing was deleted."

@tool(
    "confirm_fact",
    "The user just said something you have marked (not sure) is right. "
    "Marks it confirmed, so you can treat it as true from now on.",
    {
        "about": {
            "type": "string",
            "description": "Roughly what the fact says.",
        },
    },
    required=("about",),
)
@_hers
def _confirm_fact(about):
    done, candidates = longterm.confirm_fact(about)

    if done:
        fact, was_unsure = done
        return f"Confirmed: {fact}" if was_unsure else f"Already confirmed: {fact}"

    if candidates:
        listing = "\n".join(f"- {c}" for c in candidates)
        return f"More than one could be it:\n{listing}\nAsk which one."

    return f"Nothing remembered matches {about!r}. If it's new, use remember_fact."


@tool(
    "update_fact",
    "Replace something remembered about the user when it changed - they "
    "moved, changed jobs, swapped hardware, finished the project. The old "
    "version is kept as history. Set `mistake` only when the old fact was "
    "never right (you misheard).",
    {
        "about": {
            "type": "string",
            "description": "Roughly what the old fact says.",
        },
        "corrected": {
            "type": "string",
            "description": "The replacement, as one short third-person "
                           "sentence.",
        },
        "since": {
            "type": "string",
            "description": "Only when the user said when it changed: the date as "
                           "YYYY-MM-DD, YYYY-MM or YYYY, worked out from today's date. "
                           "Leave it out rather than guess.",
        },
        "mistake": {
            "type": "boolean",
            "description": "True when the old fact was never right: it's fixed with no history kept.",
        },
    },
    required=("about", "corrected"),
)
@_hers
def _update_fact(about, corrected, since="", mistake=False):
    mistake = _yes(mistake)
    changed, candidates = longterm.update_fact(about, corrected, since=since, mistake=mistake)

    if changed:
        if changed[0] == changed[1]:
            return f"Unchanged: {changed[0]!r}" + (_date_note(since) or " (it already says that)")
        if mistake or longterm.guest():          # a guest's facts keep no history
            return f"Fixed: {changed[0]!r} is now {changed[1]!r}" + _date_note(since) + _reminder_offer(changed[1])
        return (f"Updated: {changed[1]!r} (kept {changed[0]!r} as what used to be true)" + _date_note(since)
                + _reminder_offer(changed[1]))

    if candidates:
        listing = "\n".join(f"- {c}" for c in candidates)

        return f"More than one could be it:\n{listing}\nAsk which one."

    why = longterm.why_not(corrected)
    if why:
        return f"Not changed: {why}."

    return (
        f"Nothing remembered matches {about!r}, and {corrected!r} was not "
        "saved. Use remember_fact if this is new."
    )

@tool(
    "search_history",
    "Look through past conversations for something the user is "
    "referring to. Use this whenever they mention something you can't "
    "see in the messages above - an earlier decision, a plan, a name. "
    "Search before saying you don't remember.",
    {
        "about": {
            "type": "string",
            "description": "What to look for, in their words - 'the "
                           "deploy window', 'what we decided about the "
                           "migration'.",
        },
    },
    required=("about",),
    available=lambda: config.TRANSCRIPT_ENABLED,
    why=lambda: "the transcript is off - set history.transcript true",
)
def _search_history(about):
    hits = transcript.search(about)

    if not hits:
        return (
            f"Nothing in past conversations matches {about!r}. Say so "
            "plainly rather than inventing a memory of it."
        )

    return (
        transcript.describe(hits, config.AGENT_NAME)
        + "\n\n(These were matched on wording alone, so some may be "
        "coincidence. If none of them actually answers the question, "
        "say you don't recall rather than stretching one to fit.)"
    )


@tool(
    "ask_memory",
    "Ask your own memory a question and get one answer: it searches your facts, what you've "
    "concluded about people, your notes on past conversations and the conversations themselves "
    "together. Use it for anything about the person you're talking to (or someone they know) "
    "that isn't already in front of you - 'how does Ryan take his coffee?', 'what did Shannon "
    "say about her trip?' - before saying you don't know.",
    {
        "question": {
            "type": "string",
            "description": "The question, as you'd ask yourself, e.g. 'how does Ryan take his coffee?'.",
        },
        "about": {
            "type": "string",
            "description": "Someone else it's about, by name, when it isn't the person you're "
                           "talking to. Optional.",
        },
    },
    required=("question",),
)
def _ask_memory(question, about=""):
    from mind import recall

    return recall.answer(question, about)


# ---------------------------------------------------------------------------
# Meeting people (senses/people.py's ladder)
# ---------------------------------------------------------------------------
@tool(
    "meet_guest",
    "Someone new told you their name (or the user introduced them: 'this is "
    "my friend Mike'). Puts the name to the face and voice you just saw and "
    "heard, so you know them for the rest of this session. Nothing is saved: "
    "only the user can keep them for good.",
    {
        "name": {"type": "string", "description": "Their name, as they said it."},
    },
    required=("name",),
)
def _meet_guest(name):
    from senses import people

    _ok, said = people.meet(name)
    return said
