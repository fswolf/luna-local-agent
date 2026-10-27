"""The grounding check: specifics she said that nothing backs up.

A small model states guesses in exactly the same voice as facts. The
calibration check catches the ones she was unsure of token by token; this
catches the ones she was sure of and had no source for. After a reply,
every *checkable specific* in it - a number with a unit, a price, a
percentage, a version, a year, a time, a URL, a file path - is looked
for in what she actually had in front of her this turn:

  * the system prompt (memory facts, the situation block, projects...)
  * the conversation history and what was just said
  * every tool result of the turn

A specific that appears in none of them, in a reply that doesn't hedge,
is ungrounded. What happens then is `grounding.mode`:

  "flag"    the thought log gets an "ungrounded" flag, and her next
            prompt tells her which details weren't sourced
  "hedge"   all that, plus a short line said after the reply ("I haven't
            checked those details, so take them with a grain of salt.")
            when a strong specific (path, URL, version, price, unit...)
            was ungrounded - the default
  "check"   all that, and when the turn had tools she's sent straight
            back to verify them with a tool or say she isn't sure

Deliberately narrow. Words aren't checked - names and descriptions are
too loose to match - and neither is code, fenced or `inline`, where a
path is an instruction, not a claim. A lone bare number or year is
noted but never flagged on its own.
"""
import re

import config

# Kinds, strongest first. "number" is weak: two or three bare digits are
# flagged in the log but never said out loud.
_PATTERNS = (
    ("url", re.compile(r"\bhttps?://[^\s)\]>'\"]+", re.I)),
    ("domain", re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|dev|ai|gg|tv|co|app)\b", re.I)),
    ("path", re.compile(r"(?<![\w/])(?:~|\.{1,2})?/(?:[\w.\-]+/)+[\w.\-]*|(?<![\w/])~/[\w.\-]+")),
    ("version", re.compile(r"\bv?\d+\.\d+(?:\.\d+)+\b|\bv\d+(?:\.\d+)?\b|\bversion\s?\d+(?:\.\d+)*\b", re.I)),
    ("money", re.compile(r"[$€£¥]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:usd|cad|eur|dollars|bucks)\b", re.I)),
    ("percent", re.compile(r"\b\d+(?:\.\d+)?\s?%")),
    ("measure", re.compile(
        r"\b\d[\d,]*(?:\.\d+)?\s?(?:tb|gb|mb|kb|gib|mib|ghz|mhz|khz|hz|ms|kw|w|watts|v|volts|"
        r"°c|°f|fps|tokens|cores|threads|rpm|km|mi|miles|kg|lbs?|mph|kph)\b", re.I)),
    ("time", re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s?(?:am|pm)?\b", re.I)),
    ("year", re.compile(r"\b(?:19|20)\d{2}\b")),
    ("number", re.compile(r"\b\d{2,}(?:[.,]\d+)?\b")),
)
_STRONG = {"url", "domain", "path", "version", "money", "percent", "measure"}

_FENCED = re.compile(r"```.*?```|`[^`\n]+`", re.S)   # code blocks and `inline code`
# The reply already owns up: "I think", "probably", "about", "if I remember"...
_HEDGED = re.compile(
    r"\b(i think|i believe|i'm not sure|not sure|probably|might|maybe|if i remember|iirc|"
    r"i guess|haven't checked|not certain|don't know|no idea|could be|should be)\b"
    r"|\b(?:about|around|roughly|approximately|approx\.?)\s*[$€£]?\d|~\s*\d", re.I)
_DIGITS = re.compile(r"\d+(?:\.\d+)?")


def mode():
    m = str(getattr(config, "GROUNDING_MODE", "hedge")).lower()
    return m if m in ("flag", "hedge", "check") else "hedge"


def enabled():
    return bool(getattr(config, "GROUNDING_ENABLED", True))


def claims(answer):
    """[(kind, text)] - each specific once, strongest reading first, and a
    span already claimed by a stronger kind isn't counted again."""
    text = _FENCED.sub(" ", str(answer or ""))
    taken, out, seen = [], [], set()

    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            span = m.span()

            if any(a < span[1] and span[0] < b for a, b in taken):
                continue

            value = m.group(0).strip().rstrip(".,;:!?")

            if kind == "path" and value.count("/") < 2 and not value.startswith("~/"):
                continue

            key = value.lower()

            if key not in seen:
                seen.add(key)
                out.append((kind, value))

            taken.append(span)

    return out


def _norm(text):
    return re.sub(r"(?<=\d),(?=\d{3}\b)", "", str(text or "").lower())


def _backed(kind, value, evidence):
    v = _norm(value)

    if v in evidence:
        return True

    if kind in ("url", "domain", "path"):
        # A trailing slash or a different scheme shouldn't count as new.
        core = v.rstrip("/").split("://", 1)[-1]
        return core in evidence

    # Numbers: every number in it has to appear as a number in the
    # evidence ("24 kHz" is backed by "24 kHz" or "24khz", not by "240").
    nums = _DIGITS.findall(v)

    if not nums:
        return False

    for n in nums:
        if not re.search(rf"(?<![\d.]){re.escape(n)}(?![\d]|\.\d)", evidence):
            return False

    return True


def check(answer, evidence_texts):
    """(ungrounded [(kind, value)], strong: bool). Empty when the reply
    hedges, has no specifics, or every specific has a source."""
    if not enabled():
        return [], False

    found = claims(answer)

    if not found:
        return [], False

    if _HEDGED.search(str(answer)):
        return [], False

    evidence = _norm("\n".join(str(t or "") for t in evidence_texts))
    loose = [(k, v) for k, v in found if not _backed(k, v, evidence)]
    strong = any(k in _STRONG for k, _v in loose)

    # One bare number or year on its own isn't worth a flag - "the 1980
    # game", "about 350 points" - two or more, or anything strong, is.
    if not strong and len(loose) < 2:
        return [], False

    return loose, strong


def flag(loose):
    shown = ", ".join(v for _k, v in loose[:4]) + (" ..." if len(loose) > 4 else "")
    return f"ungrounded: stated {shown} with no tool result, memory or message behind it"


def note(loose):
    shown = ", ".join(v for _k, v in loose[:4])
    return (f"About your previous reply: you stated {shown} without anything to back "
            "it up - no tool result, memory or message said so. If it comes up, say it "
            "wasn't checked, or check it now.")


def hedge_line():
    return str(getattr(config, "GROUNDING_HEDGE_LINE",
                       "I haven't checked those details, though, so take them with a grain of salt.")).strip()
