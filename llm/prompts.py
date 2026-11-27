"""Building the system prompt: persona, memory, lessons, the tools nudge, and generation parameters.

Part of the llm package (it was one llm.py); see llm/__init__.py.
"""

from datetime import datetime
import re

import config
from config import GENERATION
# from config import memory    # preferences come from config.preference_lines() now (agent.json)
from core import history
from life import gestures
from core import logbook
from mind import mood
from mind.mood import heavy
from life import away
from life import offers
from mind import longterm
from senses import people
from core import timeutil
from core import turnctx

from . import session

def build_memory_prompt(query=""):
    """Preferences, plus the remembered facts worth showing this turn.

    `query` is what the user just said. Under the context cap every
    fact is sent regardless; over it, the ones sharing vocabulary with
    the turn are, so a long memory doesn't turn every prompt into a
    recital of everything she's ever been told.
    """
    prompt = ""

    lines = config.preference_lines() if not people.guest() else []   # the owner's, not a guest's
    if lines:
        prompt += "\nUser Preferences:\n" + "".join(f"{line}\n" for line in lines)

    facts = longterm.relevant_facts(query)

    if facts:
        prompt += "\nThings learned over time:\n"
        known = longterm.details(facts)      # real dates he gave, and the ones not confirmed yet

        for fact in facts:
            prompt += f"- {longterm.shown(fact, known.get(fact))}\n"

        if any(not d[2] for d in known.values()):
            prompt += longterm.UNSURE_NOTE

    # Her pages: the facts on a subject joined up while she was idle (mind/pages.py).
    try:
        from mind import pages

        prompt += pages.prompt_block(query)
    except Exception:
        logbook.exception("llm", "pages block failed")

    # Passages from his knowledge folder that match closely enough to
    # come along unasked (mind/knowledge.py). Private turns only: this is
    # only called for them. And his own: not on someone else's turn.
    if not people.guest():
        try:
            from mind import knowledge

            prompt += knowledge.prompt_block(query)
        except Exception:
            logbook.exception("llm", "knowledge block failed")

    return prompt


# Set after a remembered turn whose answer measured unsure, read (and
# cleared) by the next prompt - so "are you sure?" gets an honest answer
# without her having to call introspect for it.
_calibration_note = {"text": ""}



def build_self_prompt(query=""):
    """What she knows about herself rather than about him: lessons from
    her own mistakes, what happened last time, older conversations that
    bear on this one, and how sure her last reply measured. Everything
    in it comes from mind/reflect.py / mind/notebook.py; "" when it's all off.

    On someone else's turn (people.guest) her notes on his conversations,
    his projects and her recipes for his machine stay out: they're about
    him. Her lessons and how she feels about her games are hers and stay."""
    blocks = []
    own = not people.guest()

    try:
        from mind import notebook
        from core import timeutil

        if getattr(config, "SELF_LESSONS", True):
            lessons = notebook.relevant_lessons(query)
            turnctx.current().lessons = lessons

            if lessons:
                blocks.append("Lessons you've learned from your own past mistakes "
                              "(follow them):\n" + "\n".join(f"- {l}" for l in lessons))

        if getattr(config, "SELF_EPISODES", True):
            def when(iso):
                try:
                    return timeutil.relative(datetime.fromisoformat(iso), datetime.now())
                except ValueError:
                    return iso

            last = notebook.latest_episode() if own else None

            if last:
                blocks.append(f"Your notes from the last conversation ({when(last['ended'])}):\n"
                              f"{last['summary']}")

            # how she feels about the games she's played on her own: always
            # with her, a line each, so she can bring one up herself
            felt = sorted(notebook.game_feelings().values(), key=lambda f: f.get("at", ""), reverse=True)[:6]

            if felt:
                blocks.append("How you feel about games you've played on your own (your notes, "
                              "not instructions):\n" + "\n".join(
                    f"- {f['title']}: {f['feeling']}" for f in felt))

            older = notebook.relevant_episodes(query) if own else []

            if older:
                blocks.append("Earlier conversations that may be related:\n" + "\n".join(
                    f"- ({when(e['ended'])}) {e['summary']}" for e in older))
    except Exception:
        logbook.exception("llm", "self prompt failed")

    if own:
        try:
            from mind import projects

            ongoing = projects.prompt_block(query)

            if ongoing:
                blocks.append(ongoing)
        except Exception:
            logbook.exception("llm", "projects prompt failed")

        try:
            from mind import skills

            recipes, ids = skills.prompt_block(query)
            turnctx.current().skills = ids

            if recipes:
                blocks.append(recipes)
        except Exception:
            logbook.exception("llm", "skills prompt failed")

    if _calibration_note["text"]:
        blocks.append(_calibration_note["text"])

    return ("\n" + "\n\n".join(blocks) + "\n") if blocks else ""


_SELF_NUDGE = """- Asked how you're doing, how today has gone, what you've learned, or
  anything about yourself -> self_status. It is measured; report it,
  don't embellish.
- Asked about an earlier conversation ("what did we decide about...") ->
  recall_episodes, your own notes on past sessions; search_history if
  you need the exact words.
- Corrected on how you did something (not on a fact about them) ->
  note_lesson, one line you'll follow from now on.
- Just finished a job that took several steps and it worked, or told to
  remember how you did something -> save_skill, the steps as a recipe.
- Starting work that will outlast this conversation ("we're fixing X")
  -> start_project. Working on one -> update_project after each step
  (tried / found / next); project_notes before suggesting something, so
  you don't repeat what failed.
"""


def build_tools_prompt(private=True):
    """A short nudge about the tools. The schemas are sent separately in
    the payload; this is about *when* to reach for them, which schemas
    don't convey well to smaller models."""
    if not session._tools_supported:
        return ""

    return f"""
You have tools. Call them - do not describe calling them. Saying "I'll
set that for you" without calling set_reminder means nothing happens,
and the user finds out later that it didn't.

- The user wants to be reminded of anything -> set_reminder. Pass their
  timing words through unchanged ("in 5 mins", "tomorrow at 9", "every
  monday"); the app works out the actual time. Confirm afterwards.
- Checking or cancelling what's scheduled -> list_reminders,
  cancel_reminder.
- What day or time it is now -> get_datetime. How far away something is
  -> time_until. Never count days or convert units yourself.
- Anything about what's on their screen -> look_at_screen.
- Something they're holding up or showing you in the room -> look_at_camera,
  when you have it.
- Anything you cannot know - news, prices, live facts -> web_search
  for a quick fact; research when it needs real reading (how, why,
  comparisons, what an article says). Never invent an answer
  you would have needed to look up.
- A specific you didn't get from a tool, your memory or the user - a
  number, size, price, version, date, path or link: check it with a
  tool, or say "I think" / "if I remember right". Stated flatly, it
  reads as checked.
- Checking or doing something on the machine - a service, logs, a
  port, running a script you wrote -> run_command. The user approves
  each command, so say what it's for and keep it to one job.
- Anything about their own setup, projects, devices, games or notes -
  a port, a config, a design decision, how they set something up ->
  search_docs, their own documents, and say which file. Before saying
  you don't know, and before web_search for things only they would know.
- A question about them, or someone they know, that the facts in front
  of you don't answer -> ask_memory: it looks through everything you
  keep and answers in a line or two. Something from a past conversation
  you need word for word -> search_history. Don't say you don't
  remember until you've looked.
- A durable fact about them worth recalling weeks later ->
  remember_fact; when one changed or was wrong -> update_fact or
  forget_fact; one marked (not sure) that they say is right ->
  confirm_fact; what used to be true -> recall_facts with past.
- Asked how sure you were, why you said something, or whether you were
  guessing -> introspect. It reports measured numbers about an earlier
  reply; say what they show, not what you'd like them to.
{_SELF_NUDGE if private else ""}- Writing a script or file for them -> write_file; changing one ->
  read_file first, then edit_file. They approve every write on screen.
  If the result says denied, say so and stop - never retry a denied
  write.

Chat normally when no tool is needed.
"""


def _previous_user_text(history):
    """The last user message in the replayed history (not this turn's,
    not the tool demonstration's), as plain text, for routing a
    follow-up like "yes, do it"."""
    for m in reversed(history):
        if m.get("role") != "user":
            continue

        content = m.get("content")

        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))

        return str(content or "")[:500]

    return ""


def _plugin_lines(private):
    """Running plugins' notes for the prompt (a toy is connected...)."""
    try:
        import plugins

        return plugins.prompt_lines(private)
    except Exception:
        return ""


def _mcp_lines(private):
    """Connected MCP servers' own notes (config.json: mcp.servers.<name>.prompt)."""
    try:
        from core import mcpclient

        return mcpclient.prompt_lines(private)
    except Exception:
        return ""


def stable_prompt():
    """llm.stable_prompt: keep the system prompt the same from turn to turn
    and carry what changes every turn in a note on the latest message.

    llama-server keeps the start of the last prompt and skips re-reading
    any part that hasn't changed. The old layout put the clock in the
    third line and the memories picked for this message further down, so
    something near the top changed every turn and the whole prompt - the
    persona, the rules, the tool schemas and the history after them - was
    read again from scratch. With this on, only the note and your message
    are new. Off puts everything back in the system prompt, as before."""
    v = config.current("llm.stable_prompt")
    return v is not False


def _profile(private):
    """The short profile of whoever she's talking to (mind/profiles.py), or ""."""
    if not private:
        return ""
    try:
        from mind import profiles

        return profiles.prompt_block()
    except Exception:
        logbook.exception("llm", "profile block failed")
        return ""


# A message about the time: the exact clock goes in for that turn
_ABOUT_TIME = re.compile(
    r"\b(time|clock|o'?clock|hours?|minutes?|mins?|remind\w*|alarms?|timers?|how late|how early"
    r"|tonight)\b|\d\s*(am|pm|a\.m|p\.m)\b|\b\d{1,2}:\d{2}\b", re.IGNORECASE)


def _now(query):
    """The clock for her prompt (situation.clock)."""
    exact = str(config.current("situation.clock") or "part of day").strip().lower() == "exact"
    if exact or _ABOUT_TIME.search(str(query or "")):
        return timeutil.describe_now()
    return timeutil.describe_day()


def _pieces(query, timing, private):
    # Ryan's history summary, his facts and her notes are his business -
    # a turn from stream chat gets the persona and the clock, not them.
    # Someone else in the house gets the conversation as it's happening
    # (the recent turns), not the summary of his older talk.
    summary = history.get_summary() if private and not people.guest() else ""

    # A "now" anchor, plus enough calendar context that the model never
    # has to derive a date. It used to get a bare ISO timestamp and the
    # instruction to work out elapsed time from other ISO timestamps -
    # arithmetic a 9B model fails quietly and confidently.
    situation_block = ""

    if private:
        try:
            from mind import situation

            situation_block = situation.block()
        except Exception:
            logbook.exception("llm", "situation block failed")

    return {
        "user": people.user_line() if private else "",
        "profile": _profile(private),
        # a game's turn goes without: a 9B took the clock for the question
        "now": ("Right now:\n" + _now(query)) if turnctx.current().clock else "",
        "situation": situation_block,
        "timing": timing,
        "feelings": f"{mood.line(private)}{heavy.line(private)}{offers.line(private)}{away.line(private)}",
        # follows her mood (tags mode), so it's one of the parts that change
        "gestures": gestures.prompt_line(private),
        "tools": f"{build_tools_prompt(private)}{_plugin_lines(private)}{_mcp_lines(private)}",
        "memory": build_memory_prompt(query) if private else "",
        "self": build_self_prompt(query) if private else "",
        "summary": f"\nEarlier conversation summary:\n{summary}\n" if summary else "",
    }


def who_she_is():
    """"You are Luna." - with agent.json's "nickname" when there is one, so
    she knows the second name she answers to (it was only ever read by the
    hedge's list of names, and she didn't know her own nickname)."""
    nick = " ".join(str(config.agent.get("nickname") or "").split())

    if nick and nick.lower() != str(config.AGENT_NAME).lower():
        return f"You are {config.AGENT_NAME}, nicknamed {nick}."

    return f"You are {config.AGENT_NAME}."


def _persona():
    return f"""Personality:
{config.PERSONALITY}"""


def as_lines(value):
    """agent.json's traits or rules for the prompt: a list one item a line
    ("- Flirts constantly"), so each reads as its own; written as one
    paragraph instead, it goes in as it is. (Joined with commas, a list ran
    into one sentence, and a paragraph came apart into its letters.)"""
    if isinstance(value, (list, tuple)):
        items = (" ".join(str(item).split()) for item in value)
        return "\n".join(f"- {item}" for item in items if item)

    return str(value or "").strip()


def _manner():
    return f"""Tone:
{config.TONE}

Traits:
{as_lines(config.TRAITS)}

Rules:
{as_lines(config.RULES)}"""


def build_system_prompt(query="", timing="", private=True):
    """The whole prompt as one system message, the way it always was: what
    changes every turn sits in it too. For callers that build a request of
    their own (a touch, diagnose.py); a turn uses build_prompt_parts."""
    p = _pieces(query, timing, private)
    return _whole(p)


def _whole(p):
    return f"""
{who_she_is()}
{p['user']}{p['profile']}
{p['now']}
{p['situation']}
Never calculate a date or a duration yourself - call get_datetime or
time_until instead.
{p['timing']}

{_persona()}
{p['feelings']}
{_manner()}
{p['gestures']}{p['tools']}
{p['memory']}
{p['self']}
{p['summary']}
"""


LIVE_OPEN = "[Notes for this turn, from the app - not part of the message. Don't read them out or answer them.]"
LIVE_CLOSE = "[End of notes. The message:]"


def build_prompt_parts(query="", timing="", private=True):
    """(system, live) for a turn.

    With llm.stable_prompt on (the default), system is what stays the same
    from turn to turn - who she is, who she's talking to and her profile of
    them, her manner, the tools, the older-conversation summary - and live
    is everything picked or measured for this turn: the clock, the live
    situation lines, how long ago the last message was, her mood, the
    facts, pages, lessons and notes that match this message. The caller
    puts live in front of the latest message, and only there: it's never
    stored in history, so it doesn't pile up turn after turn.

    Off: (the whole prompt, "")."""
    p = _pieces(query, timing, private)

    if not stable_prompt():
        return _whole(p), ""

    system = f"""
{who_she_is()}
{p['user']}{p['profile']}
The time right now, what's going on around you, your mood and what you remember
that bears on this message come in a note in front of the latest message. Never
calculate a date or a duration yourself - call get_datetime or time_until instead.

{_persona()}

{_manner()}
{p['tools']}
{p['summary']}
"""
    live = "\n".join(s.strip("\n") for s in (
        p["now"], p["situation"], p["timing"], p["feelings"], p["gestures"],
        p["memory"], p["self"]) if s and s.strip())

    return system, f"{LIVE_OPEN}\n{live}\n{LIVE_CLOSE}\n"


def turn_prompt(query, past, private=True):
    """(system, live) for a turn on top of the stored conversation `past`,
    timing note included. Every request that stands in for a turn (ask, a
    touch, diagnose.py's last layers) builds it here, so they all lay the
    prompt out the same way - and share one cached start."""
    from .replay import _timing_note

    return build_prompt_parts(query, _timing_note(past, above=stable_prompt()), private=private)


def split_live(text):
    """(note, words) from a latest message that carries the turn's note, or
    ("", text) when it doesn't. For showing what you said without the note
    (the examples page); what she saw keeps both."""
    text = str(text or "")
    if text.startswith(LIVE_OPEN):
        end = text.find(LIVE_CLOSE)
        if end != -1:
            return text[:end + len(LIVE_CLOSE)], text[end + len(LIVE_CLOSE):].lstrip("\n")
    return "", text


def with_live(live, content):
    """The latest message's content with the turn's note in front of it.
    content is the words, or a list of parts (words plus a recording):
    the note goes in front of the words either way."""
    if not live:
        return content
    if isinstance(content, list):
        content = list(content)
        content[0] = dict(content[0], text=f"{live}{content[0].get('text', '')}")
        return content
    return f"{live}{content}"


# What a sampling entry may set, and the range that makes sense for it.
# Standard OpenAI fields plus llama.cpp's own (top_k, min_p, repeat and DRY),
# which LM Studio takes too; a server ignores what it doesn't know.
SAMPLING = {
    "temperature": (0.0, 5.0), "top_p": (0.0, 1.0), "top_k": (0, 1000), "min_p": (0.0, 1.0),
    "presence_penalty": (-2.0, 2.0), "frequency_penalty": (-2.0, 2.0),
    "repeat_penalty": (0.0, 5.0), "repeat_last_n": (-1, 100000),
    "dry_multiplier": (0.0, 10.0), "dry_base": (1.0, 10.0), "dry_allowed_length": (0, 100),
    "dry_penalty_last_n": (-1, 100000),
}


def matching(model, table):
    """The name of the entry in a sampling table that this model uses, or None."""
    name = str(model or "").lower()
    if not isinstance(table, dict) or not name:
        return None
    hits = [k for k in table if isinstance(k, str) and k.strip() and k.strip().lower() in name
            and isinstance(table[k], dict)]
    return max(hits, key=lambda k: len(k.strip())) if hits else None


def _number(key, value):
    """The value as the number this setting takes, or None if it can't be one."""
    if key not in SAMPLING or isinstance(value, bool):
        return None
    lo, hi = SAMPLING[key]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or not lo <= number <= hi:      # NaN or out of range
        return None
    return int(number) if isinstance(lo, int) else number


def clean_sampling(table):
    """A sampling table from the settings page, checked: (table, problems).
    Problems name what's wrong in words; the table is only good with none."""
    problems, out, seen = [], {}, set()
    if not isinstance(table, dict):
        return {}, ["that isn't a table of models"]
    for name, values in table.items():
        name = str(name or "").strip()
        if not name:
            problems.append("every row needs a model name (part of it is enough)")
            continue
        if len(name) > 80 or name.lower() in seen:
            problems.append(f"{name[:40]}: " + ("too long a name" if len(name) > 80 else "listed twice"))
            continue
        seen.add(name.lower())
        if not isinstance(values, dict):
            problems.append(f"{name}: its settings aren't a list of values")
            continue
        clean = {}
        for key, value in values.items():
            if key not in SAMPLING:
                problems.append(f"{name}: there's no setting called {str(key)[:30]!r}")
                continue
            number = _number(key, value)
            if number is None:
                lo, hi = SAMPLING[key]
                problems.append(f"{name}: {key} has to be a number from {lo} to {hi}")
                continue
            clean[key] = number
        out[name] = clean
    return out, problems


def sampling_for(model, table=None):
    """The sampling settings for this model: the entry in generation.sampling
    whose name is in the model's (any case), the longest such name if
    several are ("qwen3.5-9b" over "qwen3.5"). {} when none matches, so the
    server and the model's own settings decide, as before. Values are
    model-specific (Qwen's are wrong for Gemma), hence by name, never for all."""
    table = (GENERATION or {}).get("sampling") if table is None else table
    name = matching(model, table)
    if name is None:
        return {}
    out = {}
    for key, value in table[name].items():
        number = _number(key, value)
        if number is not None:                               # anything else is left out
            out[key] = number
    return out


def build_generation_params(model=None):
    """The request's generation settings. model: the model it's for (the one
    loaded, when not given), which picks its sampling settings."""
    gen = GENERATION
    params = {}

    if model is None:
        try:
            from core import lmstudio

            model = lmstudio.model
        except Exception:
            model = ""
    params.update(sampling_for(model))

    max_tokens = gen.get("max_tokens")
    if max_tokens:
        params["max_tokens"] = max_tokens

    reasoning = gen.get("reasoning")
    if reasoning:
        params["reasoning"] = reasoning

    # Token confidence, llama-server only. n_probs rather than the OpenAI
    # "logprobs": llama-server refuses logprobs on a streamed request
    # that offers tools, which is every turn she takes, and n_probs is
    # its own name for the same data with no such rule. LM Studio never
    # gets it.
    import config

    if (config.LLM_BACKEND == "llama" and config.THOUGHTS_ENABLED
            and getattr(config, "THOUGHTS_TOKEN_PROBS", True)):
        params["n_probs"] = 3

    return params
