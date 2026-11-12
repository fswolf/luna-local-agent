"""Building the system prompt: persona, memory, lessons, the tools nudge, and generation parameters.

Part of the llm package (it was one llm.py); see llm/__init__.py.
"""

from datetime import datetime

import config
from config import AGENT_NAME, PERSONALITY, TONE, TRAITS, RULES, GENERATION
from config import memory
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

    if "user_preferences" in memory and not people.guest():   # the owner's, not a guest's
        prompt += "\nUser Preferences:\n"

        for key, value in memory["user_preferences"].items():
            prompt += f"{key}: {value}\n"

    facts = longterm.relevant_facts(query)

    if facts:
        prompt += "\nThings learned over time:\n"

        for fact in facts:
            prompt += f"- {fact}\n"

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
- Something from a past conversation you can't see -> search_history.
  Don't say you don't remember until you've looked.
- A durable fact about them worth recalling weeks later ->
  remember_fact; a correction to one -> update_fact or forget_fact.
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
        "now": timeutil.describe_now(),
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


def _persona():
    return f"""Personality:
{PERSONALITY}"""


def _manner():
    return f"""Tone:
{TONE}

Traits:
{', '.join(TRAITS)}

Rules:
{', '.join(RULES)}"""


def build_system_prompt(query="", timing="", private=True):
    """The whole prompt as one system message, the way it always was: what
    changes every turn sits in it too. For callers that build a request of
    their own (a touch, diagnose.py); a turn uses build_prompt_parts."""
    p = _pieces(query, timing, private)
    return _whole(p)


def _whole(p):
    return f"""
You are {AGENT_NAME}.
{p['user']}{p['profile']}
Right now:
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
You are {AGENT_NAME}.
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
        "Right now:\n" + p["now"], p["situation"], p["timing"], p["feelings"], p["gestures"],
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


def build_generation_params():
    gen = GENERATION
    params = {}

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
