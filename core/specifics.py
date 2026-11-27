"""The specifics in a reply: its numbers, and the names that don't just
start a sentence. What a second look, the hedge line and the review's
"low confidence" flag look for in an unsure run: a coin-flip run on one of
these is a guess; a run on wording ("leans in closer") is a small model's
normal. Shared by llm/second_look.py and mind/thoughtlog.py (which the
thought viewer runs on its own, without the rest of her).
"""
import re

import config


# A number, or a capitalised word that doesn't follow a sentence's end
_KEY_TERM = re.compile(r"\d+(?:[.,:]\d+)*|(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z]{2,}\b")


def _names_of_us():
    """Her names and yours, pet names included: "here, Daddy" is how she
    addresses you, not a fact she could have wrong."""
    names = {config.AGENT_NAME, getattr(config, "USER_NAME", "")}

    try:
        prefs = config.user_preferences()
        names.add(prefs.get("name", ""))
        nick = prefs.get("nicknames") or []
        names.update(nick if isinstance(nick, list) else [nick])
    except Exception:
        pass

    try:
        names.add(config.agent.get("nickname", ""))
    except Exception:
        pass

    return {str(n).lower() for n in names if n}


def _key_terms(text):
    """The parts of an answer that make it *this* answer: numbers, and
    capitalised names that don't just start a sentence. Her *actions*,
    line breaks, dashes and a trailing ~ end a sentence too, so "*leans in*
    Here's the thing" is a sentence start, not a name. Her name and yours
    (pet names too) aren't specifics."""
    text = re.sub(r"\*[^*\n]*\*", ". ", str(text or ""))
    text = re.sub(r"\s*\n\s*|\s*[~\u2014\u2013]\s*|\s+-\s+|\.{3}|\u2026|:\s+", ". ", text)   # "**Tip**: Make" too
    text = re.sub(r"[.!?]['\")\]]+", ".", text)                 # end quote after the stop
    # quotes, markdown and emoji aren't words: '. "Hold on' and 'blush~ 🐾 That' start sentences
    text = re.sub(r"[\"\u201c\u201d\u2018\u2019*_()\[\]#>]|[^\w\s.,:;!?'-]", " ", text)
    text = re.sub(r"\s+", " ", re.sub(r"([.!?])(\s*[.!?])+", r"\1", text)).strip(" .")
    skip = _names_of_us() | _PLAIN
    return {t for t in (m.group(0).lower().replace(",", "") for m in _KEY_TERM.finditer(text))
            if t not in skip}


# Capitalised mid-line for emphasis or in a story ("called The Archive"), they
# still aren't a name or a number she could have wrong.
_PLAIN = set("""the that this these those there then than they them their you your yours
and but not now yes yeah okay what when where which who why how she her his him its
our out all any one just still even maybe also because every everything nothing
something someone everyone here very really well please thank thanks sorry hey hello
""".split())


def _unsure_of_a_specific(answer, span):
    """Does the unsure run hold one of the reply's specifics - a number, or
    a name (a capitalised word that doesn't just start a sentence)? Those
    are read off the whole reply, where a sentence start can be told apart;
    the run alone can start mid-sentence."""
    span = " ".join(str(span or "").lower().replace(",", "").split())
    return bool(span) and any(term in span for term in _key_terms(answer))
