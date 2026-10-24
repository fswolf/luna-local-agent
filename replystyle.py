"""Her role-play asides, written the usual way.

Small models drift into stage directions in brackets glued to the line
before them: "Alright, Senpai~:(bounces lightly) ...Got it~". Role-play
writes actions in asterisks, so a bracketed aside that reads as one
(it starts with an action word: giggles, bounces, winks, blushing) is
turned into one: "Alright, Senpai~ *bounces lightly* ...Got it~".

Ordinary brackets stay as they are: "(as of Oct 3, 2026)", "(the KITCO
page)", anything with a number, a link or a colon in it.

The swap keeps every character's position ("(" and ")" become "*",
"~:(" becomes "~ *"), so it can run on a reply while it streams without
moving what's already on the screen. Her replies are stored tidied too,
which matters most: a model copies its own earlier replies, and every
stored "~:(winks)" taught her to write the next one.
"""
import re

# words that end like an action ("-s", "-ing") but aren't one
_NOT_ACTIONS = frozenset("""as is was has his its this thus plus yes us less unless series news
always perhaps sometimes thanks yours ours hers theirs whereas besides towards afterwards
nothing something anything everything things during bring thing king morning evening string
being""".split())

_ASIDE = re.compile(r"(~?:?)\(([^()\n]{2,80})\)")


def _is_action(inner):
    words = inner.strip().split()
    if not words or re.search(r"[\d$%/:=@#]|https?", inner):
        return False
    first = words[0].lower().strip(",.!?")
    if not first.isalpha() or first in _NOT_ACTIONS or not inner.strip()[0].islower():
        return False
    return (len(first) > 3 and first.endswith("s") and not first.endswith("ss")) or \
           (len(first) > 5 and first.endswith("ing"))


def tidy(text):
    """Bracketed actions as *actions*, same length, nothing else touched.
    Never inside code: not in ``` blocks or `backticks`, and not straight
    after a word (print(items) is a call, not an aside)."""
    if "(" not in text:
        return text

    def swap(m):
        glue, inner = m.group(1), m.group(2)
        start = m.start()
        if start and (text[start - 1].isalnum() or text[start - 1] in "_`") and not glue:
            return m.group(0)
        before = text[:start]
        if before.count("```") % 2 or before.count("`") % 2:
            return m.group(0)
        if not _is_action(inner):
            return m.group(0)
        if glue == "~:":
            lead = "~ *"
        elif glue == ":":
            lead = " *"
        elif glue == "~":
            lead = "~*"
        else:
            lead = "*"
        return lead + inner + "*"

    return _ASIDE.sub(swap, text)
