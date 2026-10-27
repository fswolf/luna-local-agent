"""After a reply: adaptive thinking, follow-through on promised actions, rethinking, voting, calibration and grounding.

Part of the llm package (it was one llm.py); see llm/__init__.py.
"""

import re

import config
from web import livefeed
from core import logbook

from .prompts import _calibration_note
from .replay import _strip_leading_timestamps
from .rounds import _log_tool_call, _tool_rounds
from .streaming import _Narrator, _chat_completion, _last_raw

# ---------------------------------------------------------------------------
# Adaptive thinking
#
# A small echo of mini-AGI's halting rule - stop when another step
# wouldn't change the answer - built from what's already measured. Every
# turn thinks on a modest budget. If the reply comes out shaky by its
# own token probabilities, the same question is asked again with the
# budget lifted, silently, and the second answer only replaces the
# first, out loud, when it is both different and surer. A confident
# reply never pays for the second look.
# ---------------------------------------------------------------------------
def _adaptive_on(remember):
    """Only for turns from Ryan, only on llama-server, and only while
    token probabilities are being collected - they are the signal."""
    return bool(remember and getattr(config, "ADAPTIVE_ENABLED", True)
                and getattr(config, "LLM_BACKEND", "") == "llama"
                and getattr(config, "THOUGHTS_ENABLED", True)
                and getattr(config, "THOUGHTS_TOKEN_PROBS", True))


def _same_answer(a, b):
    """Do two replies say the same thing? By meaning when the embedding
    server is up, by shared words otherwise - stricter, so a rephrasing
    isn't mistaken for a correction."""
    a, b = str(a or "").strip(), str(b or "").strip()

    if not a or not b:
        return a == b

    try:
        from mind import embedmem

        if embedmem.available():
            va, vb = embedmem._embed([a, b])

            return sum(x * y for x, y in zip(va, vb)) >= 0.88
    except Exception:
        pass

    wa, wb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))

    return len(wa & wb) / max(1, len(wa | wb)) >= 0.6


# "Let me read the file and fix it~" - and then the turn ends, with no
# tool called. Small models announce the step instead of taking it, and
# from the outside that looks like she stalled. Only the closing stretch
# of the reply is checked: a promise in the middle that she went on to
# keep in words isn't one. And only a sentence that starts with it
# ("Let me check the log." / "Okay, I'll fix it."): "maybe you'll let me
# test it" is asking, not promising.
_PROMISE = re.compile(
    r"(?:^|[.!?~\u2026\n][\W_]*)"                      # a sentence starts (emoji and all)
    r"(?:(?:ok(?:ay)?|alright|right|so|now|oh|hm+|mm+)\W+)?"   # "Okay, ..."
    r"(let me|lemme|i'll|i will|i'm going to|i'm gonna|gonna|going to)\s+"
    r"(?:just\s+|quickly\s+|actually\s+|now\s+)?"
    r"(read|check(?!\s+(?:back|in)\b)|look(?!\s+forward)|open|search|find|list|fix|edit|rewrite|update|write|"
    r"run|test|grab|pull up|see what|take a look)\b",
    re.IGNORECASE)


def _promised_action(answer):
    """What she said she'd do ("let me check the log"), if the reply ends
    on a promise she didn't keep; otherwise ""."""
    text = str(answer or "")

    if text.rstrip().endswith("?"):
        return ""

    # Matched in the whole reply, so a sentence start is a real one, not
    # wherever the closing stretch happens to begin.
    found = [m for m in _PROMISE.finditer(text) if m.end() > len(text) - 240]

    if not found:
        return ""

    start = found[-1].start(1)
    end = re.search(r"[.!?~\u2026\n]|$", text[start:]).start() + start

    return text[start:end].strip()[:120]


def _follow_through(payload, base_messages, answer, model, on_text, on_sentence,
                    prefix, nudge):
    """Run a proper tool turn after a reply that should have been one.
    Returns the full answer: what she said, the prefix, and the rest."""
    follow = dict(payload)
    follow.pop("reasoning_budget_tokens", None)

    if getattr(config, "LLM_BACKEND", "") == "llama":
        # The normal budget, not the rethink's unlimited one - a silent
        # minute of thinking is what "stalled" looks like from outside.
        follow["reasoning_budget_tokens"] = int(getattr(config, "ADAPTIVE_FIRST_BUDGET", 1024))
    follow["messages"] = list(base_messages) + [
        {"role": "assistant", "content": answer},
        {"role": "user", "content": nudge},
    ]

    if prefix:
        say = _Narrator(on_text, on_sentence)
        say.feed("\n\n" + prefix + " ")
        say.finish()

    try:
        more = _tool_rounds(follow, model, on_text, on_sentence)
    except Exception as e:
        logbook.warn("llm", "follow-through failed: %s", e)
        more = "...actually, I couldn't get at it. Can you paste it for me?"
        say = _Narrator(on_text, on_sentence)
        say.feed("\n\n" + more + " ")
        say.finish()

    return f"{answer}\n\n{prefix} {more}".replace("\n\n ", "\n\n").strip()


# A tool call written out as text, which a model falls back to when the
# request it's answering offers no tools (Qwen's XML form, and the JSON
# one inside <tool_call> tags).
_TOOL_MARKUP = re.compile(r"<tool_call>|<function=", re.IGNORECASE)


def _rethink(payload, base_messages, answer, on_text, on_sentence):
    """A deeper second look at a shaky reply. Returns None when the
    first reply was sure enough, otherwise a dict with both passes'
    thinking and tokens, the outcome, and what (if anything) was said."""
    from mind import thoughtlog

    first = {"thinking": _last_raw.get("thinking") or [],
             "tokens": _last_raw.get("tokens") or [],
             "exchanges": [], "called": set()}
    shape = thoughtlog.confidence(first["tokens"])
    conf = shape["conf"]

    if conf is None or (conf >= config.ADAPTIVE_RETHINK_BELOW and not shape["shaky"]):
        return None

    reason = (f"shaky: {shape['shaky'].split(',')[0]}" if shape["shaky"]
              else f"only {conf:.0%} sure")

    try:
        import ui

        ui.set_status("Rethinking...")
    except Exception:
        pass

    livefeed.emit("rethink", step="start", reason=reason, conf=conf)
    logbook.info("llm", "rethinking - %s", reason)

    # Tools stay in the request. Without them a model that decides on a
    # second look it should check something writes the call out as text
    # - "<tool_call><function=list_files>..." - and that was being spoken
    # as her correction. With them it comes back as a real tool call,
    # which is caught below and handed back to run properly.
    deep = {k: v for k, v in payload.items() if k != "tool_choice"}
    deep["messages"] = list(base_messages)
    deep["reasoning_budget_tokens"] = int(config.ADAPTIVE_DEEP_BUDGET)

    _last_raw.update(thinking=[], tokens=[], exchanges=[], called=set())
    quiet = _Narrator()  # nothing to the screen or the voice yet

    try:
        reply = _chat_completion(deep, quiet)
    except Exception as e:
        logbook.warn("llm", "rethink failed: %s", e)
        _last_raw.update(first)
        livefeed.emit("rethink", step="done", outcome=f"failed: {e}"[:120])

        return None

    second_text = _strip_leading_timestamps(quiet.finish())

    wants_tool = (reply or {}).get("tool_calls") or _TOOL_MARKUP.search(second_text or "")

    if wants_tool and not payload.get("tools"):
        # No tools this turn to do it with: the first answer stands.
        _last_raw.update(first)
        outcome = "kept the first answer - the second look reached for a tool"
        _log_tool_call("rethink", f"{reason} → {outcome}")
        livefeed.emit("rethink", step="done", outcome=outcome)

        return None

    if wants_tool:
        # The second look's answer is "I should go and check" - which is
        # better than either reply. ask() runs that as a proper tool turn.
        _last_raw.update(first)
        outcome = "second look wants to check with a tool - doing that"
        _log_tool_call("rethink", f"{reason} → {outcome}")
        livefeed.emit("rethink", step="done", outcome=outcome)

        return {"wants_tools": True, "corrected": False, "answer": "", "said": "",
                "conf": conf, "conf2": None, "outcome": outcome}

    second = {"thinking": _last_raw.get("thinking") or [],
              "tokens": _last_raw.get("tokens") or [],
              "exchanges": [], "called": set()}
    shape2 = thoughtlog.confidence(second["tokens"])
    conf2 = shape2["conf"]
    same = _same_answer(answer, second_text)

    # Surer than the first, and sure in its own right: trading a 25%
    # guess for a 30% guess out loud is worse than leaving it.
    surer = (conf2 is not None and not shape2["shaky"]
             and conf2 >= max(conf + config.ADAPTIVE_MIN_GAIN,
                              config.ADAPTIVE_RETHINK_BELOW))
    corrected = bool(second_text) and not same and surer and config.ADAPTIVE_SPEAK_CORRECTIONS
    said = ""

    if corrected:
        said = f"{config.ADAPTIVE_PREFIX} {second_text}".strip()
        speaker = _Narrator(on_text, on_sentence)
        speaker.feed("\n\n" + said + " ")
        speaker.finish()
        outcome = f"corrected herself - {conf:.0%} → {conf2:.0%} sure"
    elif not second_text:
        outcome = "second look came back empty - kept the first answer"
    elif same:
        outcome = f"held - same answer on a second look ({conf2:.0%} sure)"
    elif not surer:
        outcome = (f"kept the first answer - the second wasn't sure enough "
                   f"either ({conf2:.0%} vs {conf:.0%})" if conf2 is not None
                   else "kept the first answer")
    else:
        outcome = f"would have corrected ({conf2:.0%} sure) - speak_corrections is off"

    _log_tool_call("rethink", f"{reason} → {outcome}")
    livefeed.emit("rethink", step="done", outcome=outcome, conf=conf2)

    return {"first": first, "second": second, "answer": second_text, "said": said,
            "corrected": corrected, "conf": conf, "conf2": conf2, "outcome": outcome}


def _calibrate(answer, second, remember, on_text, on_sentence):
    """Make what she says match how sure she measured.

    When her own token probabilities say she didn't know and the answer
    doesn't admit it, a short hedge is spoken after it (self.hedge_line),
    and the next prompt tells her how sure that reply was - so a "you
    sure?" gets the truth. Only for Ryan's own turns on llama-server - a
    reminder she's delivering isn't a claim she can be unsure of - never
    after a tool call (wording a tool result back can be low-probability
    without being a guess), and never on top of a spoken correction.
    """
    if not (remember and getattr(config, "SELF_CALIBRATION", True)
            and _last_raw.get("tokens") and not _last_raw.get("exchanges")):
        return answer

    try:
        from mind import thoughtlog

        if second:
            shape = thoughtlog.confidence(second["second" if second["corrected"] else "first"]["tokens"])
        else:
            shape = thoughtlog.confidence(_last_raw["tokens"])
    except Exception:
        return answer

    conf = shape["conf"]

    if conf is None or conf >= config.SELF_HEDGE_BELOW:
        return answer

    shaky = f" - shakiest on {shape['shaky'].split(', ', 1)[-1]}" if shape["shaky"] else ""
    _calibration_note["text"] = (
        f"About your previous reply: your own token probabilities say you were "
        f"only {conf:.0%} sure of it{shaky}. If it comes up, be upfront that you "
        "weren't sure."
    )

    # Said out loud only when the doubt has a place - a run of coin-flip
    # tokens (a name, a number, a date) - not when a playful reply simply
    # had a lot of ways to be worded. Banter averages low; it isn't a guess.
    if (second and second["corrected"]) or thoughtlog._HEDGED.search(answer) \
            or not config.SELF_HEDGE_LINE or not shape["shaky"]:
        return answer

    line = config.SELF_HEDGE_LINE.strip()
    speaker = _Narrator(on_text, on_sentence)
    speaker.feed(" " + line + " ")
    speaker.finish()
    _log_tool_call("calibration", f"{conf:.0%} sure - added \"{line}\"")
    livefeed.emit("rethink", step="done", outcome=f"hedged - only {conf:.0%} sure", conf=conf)

    return f"{answer} {line}"


# ---------------------------------------------------------------------------
# Self-consistency: on a shaky reply, ask again and go with the majority
# ---------------------------------------------------------------------------
_KEY_TERM = re.compile(r"\d+(?:[.,:]\d+)*|(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z]{2,}\b")


def _key_terms(text):
    """The parts of an answer that make it *this* answer: numbers, and
    capitalised names that don't just start a sentence."""
    return {m.group(0).lower().replace(",", "") for m in _KEY_TERM.finditer(str(text or "").strip())}


def _agrees(a, b):
    """Same answer, for voting. The specifics decide when both have some:
    "The capital is Sydney" and "The capital is Canberra" share almost
    every word and still disagree, while "Canberra." and "It's Canberra,
    the capital of Australia" agree. Without specifics, overall likeness."""
    ka, kb = _key_terms(a), _key_terms(b)

    if ka and kb:
        return bool(ka & kb) and (ka <= kb or kb <= ka)

    return _same_answer(a, b)

def _vote(payload, base_messages, answer, on_text, on_sentence):
    """Like _rethink, but instead of one deeper look it asks the same
    question `adaptive.votes` more times at the normal thinking budget and
    compares the answers. Whatever most of them agree on wins:

      * the first reply is in the majority -> it stands ("held, 3 of 3")
      * two or more later answers agree with each other and not with the
        first -> she corrects herself with the majority answer
      * nobody agrees with anybody -> the first stands, and calibration
        says she wasn't sure
      * most of the new answers reach for a tool -> she goes and checks

    A correction needs a fact to correct: only when her answer and the
    majority's both carry specifics (numbers, names) that differ does she
    speak again. Playful replies that merely differ in wording are left
    alone, so the vote changes what she knows, never how she sounds.

    Returns the same shape _rethink does, so ask() treats them alike."""
    from mind import thoughtlog

    first = {"thinking": _last_raw.get("thinking") or [],
             "tokens": _last_raw.get("tokens") or [],
             "exchanges": [], "called": set()}
    shape = thoughtlog.confidence(first["tokens"])
    conf = shape["conf"]

    if conf is None or (conf >= config.ADAPTIVE_RETHINK_BELOW and not shape["shaky"]):
        return None

    reason = (f"shaky: {shape['shaky'].split(',')[0]}" if shape["shaky"]
              else f"only {conf:.0%} sure")
    n = max(1, min(4, int(getattr(config, "ADAPTIVE_VOTES", 2))))

    try:
        import ui

        ui.set_status("Double-checking...")
    except Exception:
        pass

    livefeed.emit("rethink", step="start", reason=f"{reason} - asking {n} more times", conf=conf)
    logbook.info("llm", "voting - %s, %d more answers", reason, n)

    sample = {k: v for k, v in payload.items() if k != "tool_choice"}
    sample["messages"] = list(base_messages)

    if getattr(config, "LLM_BACKEND", "") == "llama":
        sample["reasoning_budget_tokens"] = int(getattr(config, "ADAPTIVE_FIRST_BUDGET", 1024))

    votes = []

    for _ in range(n):
        _last_raw.update(thinking=[], tokens=[], exchanges=[], called=set())
        quiet = _Narrator()

        try:
            reply = _chat_completion(sample, quiet)
        except Exception as e:
            logbook.warn("llm", "vote sample failed: %s", e)
            continue

        text = _strip_leading_timestamps(quiet.finish())
        shape_n = thoughtlog.confidence(_last_raw.get("tokens") or [])
        votes.append({
            "text": text,
            "tool": bool((reply or {}).get("tool_calls") or _TOOL_MARKUP.search(text or "")),
            "conf": shape_n["conf"],
            "run": {"thinking": _last_raw.get("thinking") or [],
                    "tokens": _last_raw.get("tokens") or [], "exchanges": [], "called": set()},
        })

    _last_raw.update(first)

    if not votes:
        livefeed.emit("rethink", step="done", outcome="the extra answers failed - kept the first")
        return None

    tool_votes = sum(v["tool"] for v in votes)

    if tool_votes * 2 > len(votes) and payload.get("tools"):
        outcome = f"{tool_votes} of {len(votes)} new answers wanted to check with a tool - doing that"
        _log_tool_call("vote", f"{reason} → {outcome}")
        livefeed.emit("rethink", step="done", outcome=outcome)
        return {"wants_tools": True, "corrected": False, "answer": "", "said": "",
                "conf": conf, "conf2": None, "outcome": outcome}

    pool = [{"text": answer, "conf": conf, "run": first, "first": True}]
    pool += [dict(v, first=False) for v in votes if v["text"].strip() and not v["tool"]]

    if len(pool) == 1:
        outcome = ("the extra answers reached for a tool she wasn't offered - kept the first"
                   if tool_votes else "the extra answers came back empty - kept the first")
        _log_tool_call("vote", f"{reason} → {outcome}")
        livefeed.emit("rethink", step="done", outcome=outcome)
        return None

    # How many of the others each answer agrees with.
    for a in pool:
        a["agree"] = sum(1 for b in pool if b is not a and _agrees(a["text"], b["text"]))

    total = len(pool)
    best = max(pool, key=lambda a: (a["agree"], a["first"], a["conf"] or 0))
    first_agree = pool[0]["agree"]
    corrected = False
    said = ""

    if best["first"] or first_agree >= best["agree"]:
        backing = next((a for a in pool[1:] if _agrees(answer, a["text"])), None)
        outcome = (f"held - {first_agree + 1} of {total} answers agree" if first_agree
                   else f"no agreement across {total} answers - kept the first")
        shown = backing or (pool[1] if total > 1 else pool[0])
        second_run, second_text = shown["run"], shown["text"]
        conf2 = (backing or {}).get("conf")
    elif best["agree"] >= 1 and not (_key_terms(answer) and _key_terms(best["text"])):
        # The others agree with each other, but nobody said anything
        # checkable - a number, a name. That's three wordings of the same
        # mood, not a corrected fact, and her first wording stands.
        conf2 = best["conf"]
        second_run, second_text = best["run"], best["text"]
        outcome = f"held - the other {total - 1} answers only differ in wording"
    elif best["agree"] >= 1:
        conf2 = best["conf"]
        second_run, second_text = best["run"], best["text"]

        if config.ADAPTIVE_SPEAK_CORRECTIONS:
            corrected = True
            said = f"{config.ADAPTIVE_PREFIX} {best['text']}".strip()
            speaker = _Narrator(on_text, on_sentence)
            speaker.feed("\n\n" + said + " ")
            speaker.finish()
            outcome = f"corrected herself - {best['agree'] + 1} of {total} answers agree on another reply"
        else:
            outcome = (f"would have corrected ({best['agree'] + 1} of {total} agree) - "
                       "speak_corrections is off")
    else:
        conf2 = None
        shown = pool[1] if total > 1 else pool[0]
        second_run, second_text = shown["run"], shown["text"]
        outcome = f"no agreement across {total} answers - kept the first"

    _log_tool_call("vote", f"{reason} → {outcome}")
    livefeed.emit("rethink", step="done", outcome=outcome, conf=conf2)

    return {"first": first, "second": second_run, "answer": second_text, "said": said,
            "corrected": corrected, "conf": conf, "conf2": conf2, "outcome": outcome}


# ---------------------------------------------------------------------------
# Grounding: specifics she stated with nothing behind them (mind/grounding.py)
# ---------------------------------------------------------------------------
def _evidence(payload):
    """What she had in front of her this turn: the system prompt, every
    user message, every tool result. Her own earlier replies don't count -
    a guess repeated isn't a source."""
    out = []

    for m in payload.get("messages") or ():
        if m.get("role") not in ("system", "user", "tool"):
            continue

        content = m.get("content")

        if isinstance(content, list):
            content = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))

        out.append(str(content or ""))

    out += [str(x.get("result", "")) for x in _last_raw.get("exchanges") or []]
    return out


def _ground(answer, first_answer, second, payload, base_messages, model, on_text, on_sentence,
            already_hedged=False):
    """(answer, first_answer, extra_flags, checked) after the grounding
    check - `checked` when it sent her back to verify with a tool."""
    try:
        from mind import grounding

        loose, strong = grounding.check(answer, _evidence(payload))
    except Exception:
        logbook.exception("llm", "grounding check failed")
        return answer, first_answer, [], False

    if not loose:
        return answer, first_answer, [], False

    flags = [grounding.flag(loose)]
    note = grounding.note(loose)
    _calibration_note["text"] = (_calibration_note["text"] + "\n" + note).strip()
    mode = grounding.mode()
    corrected = bool(second and second.get("corrected"))
    logbook.info("llm", "ungrounded: %s", ", ".join(v for _k, v in loose[:6]))

    if mode == "check" and payload.get("tools") and not _last_raw.get("exchanges"):
        shown = ", ".join(v for _k, v in loose[:4])
        _log_tool_call("grounding", f"unsourced {shown} - checking")
        livefeed.emit("rethink", step="done", outcome=f"grounding: checking {shown}")
        answer = _follow_through(
            payload, base_messages, answer, model, on_text, on_sentence,
            "Actually, let me double-check that.",
            f"(Not from {config.USER} - your own grounding check: you stated {shown} but nothing "
            "you were given says so. Check them with your tools now, or say plainly that "
            "you're not sure. Don't repeat them as fact.)")

        if not corrected:
            first_answer = answer

        return answer, first_answer, flags, True

    if mode in ("hedge", "check") and strong and not already_hedged and not corrected:
        line = grounding.hedge_line()

        if line:
            speaker = _Narrator(on_text, on_sentence)
            speaker.feed(" " + line + " ")
            speaker.finish()
            _log_tool_call("grounding", f"unsourced {', '.join(v for _k, v in loose[:4])} - "
                                        f"added \"{line}\"")
            livefeed.emit("rethink", step="done", outcome="grounding: hedged unsourced details")
            answer = f"{answer} {line}"
            first_answer = answer

    return answer, first_answer, flags, False
