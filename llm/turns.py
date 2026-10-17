"""One turn end to end (ask), the thought log record, and the prompt budget for /context.

Part of the llm package (it was one llm.py); see llm/__init__.py.
"""

import hashlib
import time
from datetime import datetime

import config
from config import AGENT_NAME
import history
import gestures
import livefeed
import lmstudio
import logbook
import mood
import longterm
import reminders
import tools
import transcript
import turnctx
import websearch

from . import session
from .prompts import _calibration_note, _previous_user_text, build_generation_params, build_memory_prompt, build_self_prompt, build_system_prompt, build_tools_prompt
from .replay import _demonstration, _has_tool_example, _replay, _strip_leading_timestamps, _timestamped, _timing_note
from .rounds import _generate, _log_tool_call, _tool_rounds, _why_empty
from .second_look import _adaptive_on, _calibrate, _follow_through, _ground, _promised_action, _rethink, _vote
from .streaming import _last_raw

_window_cache = {"at": 0.0, "n": 0}


def _window():
    """The context length, asked for at most once a minute - it's an
    HTTP round trip, and it only changes when a model is reloaded."""
    if time.monotonic() - _window_cache["at"] > 60:
        _window_cache.update(at=time.monotonic(), n=lmstudio.context_length())

    return _window_cache["n"]


def _record_thoughts(user_text, answer, started, source=None, model="",
                     prompt_hash="", extra_flags=()):
    """This turn's scratchpad, to the thought log.

    Only called for turns that will be remembered, so stream chat and
    IRC never contribute. Never raises: the log is for reading later,
    and a failed write must not cost the reply in front of him now.
    """
    try:
        import thoughtlog

        rounds = _last_raw.get("thinking") or []

        # A turn with token data is worth keeping even when the model
        # didn't think - the confidence of the answer is the point.
        if not rounds and not _last_raw.get("tokens"):
            return

        # In the order they were called, with repeats, which is what the
        # scratchpad will be talking about. _last_raw["called"] is a set.
        called = [x["name"] for x in _last_raw.get("exchanges") or []]

        try:
            known = tools.names()
        except Exception:
            known = []

        flags = thoughtlog.record(
            user_text, rounds, answer,
            source=source or turnctx.current().source,
            tools=called,
            seconds=time.monotonic() - started,
            mood=mood.bands(),
            results=[x.get("result", "") for x in _last_raw.get("exchanges") or []],
            known_tools=known,
            tokens=_last_raw.get("tokens") or [],
            agent=AGENT_NAME,
            model=model,
            prompt_hash=prompt_hash,
            extra_flags=extra_flags,
        )
        livefeed.emit("flags", flags=flags or [])
    except Exception:
        logbook.exception("llm", "thought log write failed")


def prompt_budget(text="hello"):
    """What a turn would send, in rough tokens, part by part - built the
    same way ask() builds it, without sending. For /context, and for
    the moment a request starts failing and the question is "how big
    has this got".
    """
    past = history.get_messages_full()
    system = build_system_prompt(text, _timing_note(past))
    replayed = []

    for m in past:
        replayed.extend(_replay(m))

    demo = _demonstration() if session._tools_supported and not _has_tool_example(replayed) else []
    specs = tools.specs(query=text, quiet=True) if session._tools_supported else []
    every = len(tools.specs()) if session._tools_supported else 0
    memory_block = build_memory_prompt(text)
    tools_block = build_tools_prompt()
    self_block = build_self_prompt(text)

    try:
        import situation

        situation_block = situation.block()
    except Exception:
        situation_block = ""

    parts = {
        "persona + rules": lmstudio.estimate_tokens(system) - lmstudio.estimate_tokens(memory_block) - lmstudio.estimate_tokens(tools_block) - lmstudio.estimate_tokens(self_block) - lmstudio.estimate_tokens(situation_block),
        "situation (live)": lmstudio.estimate_tokens(situation_block),
        "memory (facts + preferences)": lmstudio.estimate_tokens(memory_block),
        "lessons, recipes, projects + past sessions": lmstudio.estimate_tokens(self_block),
        "tools nudge": lmstudio.estimate_tokens(tools_block),
        f"tool schemas ({len(specs)} of {every} sent)": lmstudio.estimate_tokens(specs),
        "tool example": lmstudio.estimate_tokens(demo),
        f"history ({len(past)} turns + summary)": lmstudio.estimate_tokens(replayed),
    }
    total = sum(max(0, v) for v in parts.values())

    return parts, total, lmstudio.context_length()


def ask(text, model, on_text=None, on_sentence=None,
        context=None, tools_allowed=None, remember=True, source=None):
    """One turn, inside a turnctx turn (see _ask for the turn itself)."""
    with turnctx.ensure(source=source or "typed"):
        return _ask(text, model, on_text=on_text, on_sentence=on_sentence, context=context,
                    tools_allowed=tools_allowed, remember=remember, source=source)


def _ask(text, model, on_text=None, on_sentence=None,
         context=None, tools_allowed=None, remember=True, source=None):
    """One turn. Returns the finished reply.

    Runs inside a turnctx turn: the caller's if it began one (a job or a
    Discord turn, carrying its passes), otherwise a new one.

    on_text receives visible text as it streams, for the screen.
    on_sentence receives each complete sentence, for the voice. Pass
    neither and this is the blocking request it always was, which is
    what the reminder scanner wants - it has no screen to draw on.

    The last three arguments are for a turn that did not come from the
    person sitting at the keyboard - stream chat is the reason they
    exist - and they are deliberately separate switches rather than one
    "untrusted" flag, because they defend different things:

      context        replaces the stored conversation. A stranger's turn
                     must not see Ryan's history, and Ryan's history must
                     not be built out of strangers' turns.
      tools_allowed  narrows the tool list to names that are safe for
                     whoever is asking.
      remember       False keeps the turn out of history and the
                     transcript entirely, so a hostile message can't be
                     replayed into a later prompt. Today proved how much
                     weight stored turns carry; a poisoned one would
                     carry the same.

    source labels the turn in the thought log when it didn't come from
    the keyboard or the mic - a reminder firing says "reminder". Left
    None, it's the running turn's (turnctx), or "typed".
    """

    now = datetime.now()
    started = time.monotonic()
    _last_raw["thinking"] = []
    _last_raw["tokens"] = []

    past = [] if context is not None else history.get_messages_full()
    turn = turnctx.current()
    turn.private = context is None
    # A fresh turn starts clean. A stream-chat turn starts marked: its
    # words are a stranger's from the first token.
    turn.seen = "stream chat" if context is not None else None
    turn.read_local = False
    turn.lessons = []
    turn.skills = []
    messages = [{
        "role": "system",
        # A turn from stream chat never sees her notes on Ryan's
        # conversations - "last time" is his business, not the room's.
        "content": build_system_prompt(text, _timing_note(past),
                                       private=context is None),
    }]

    if context is None:
        _calibration_note["text"] = ""  # read once, by the prompt just built

    # get_messages_full() keeps each message's stored timestamp, so
    # the model can see how much time passed between past turns too,
    # not just how old the newest message is.
    replayed = []

    for m in past:
        replayed.extend(_replay(m))

    if context is not None:
        replayed = list(context)

    # Ahead of history, so it reads as the oldest thing in the window
    # and anything real that follows takes precedence over it.
    if session._tools_supported and not _has_tool_example(replayed):
        messages.extend(_demonstration())

    messages.extend(replayed)

    # Folded into the *user* turn's content rather than a second
    # "system" message - some chat templates (Jinja-based, incl. this
    # one) hard-require system to be the first and only system-role
    # message, and raise a template error if another one shows up
    # anywhere else in the list.
    #
    # Only needed when tools are unavailable: with tools, the model calls
    # web_search itself instead of needing the phrase "web search" in
    # your sentence.
    user_content = text

    if not session._tools_supported and websearch.looks_like_search(text):
        query = websearch.extract_query(text)
        results = websearch.search(query)
        search_block = websearch.format_results(query, results)
        user_content = f"{search_block}\n\n{text}"

    messages.append(_timestamped("user", user_content, now))

    # Use whatever is loaded now rather than what was loaded at startup.
    # Unloading a model to free VRAM and loading another is a normal
    # thing to do mid-session, and it used to mean every subsequent turn
    # asked for a model that wasn't there.
    swapped = lmstudio.take_change()

    if swapped:
        logbook.info("llm", "model changed to %s", swapped)
        _log_tool_call("model", f"LM Studio is now running {swapped}")

    payload = {
        "model": lmstudio.model or model,
        "messages": messages,
    }

    payload.update(build_generation_params())

    # Adaptive thinking: a modest budget up front, a deeper second look
    # only if the answer comes out shaky. The messages are copied now,
    # before tool rounds append to them, so a rethink asks the same
    # question afresh rather than continuing the first attempt.
    adaptive = _adaptive_on(remember)
    base_messages = list(messages)

    if adaptive and config.ADAPTIVE_FIRST_BUDGET >= 0:
        payload["reasoning_budget_tokens"] = int(config.ADAPTIVE_FIRST_BUDGET)
    elif (turnctx.current().job and getattr(config, "LLM_BACKEND", "") == "llama"
          and getattr(config, "ADAPTIVE_JOB_BUDGET", 1024) >= 0):
        # A job or game turn gets no second look, so nothing else bounds
        # its thinking - and minutes of silent thinking is what a stalled
        # game turn looks like from outside.
        payload["reasoning_budget_tokens"] = int(config.ADAPTIVE_JOB_BUDGET)

    # The live monitor's view of the turn's start. Chat turns pass a
    # context of their own, which is how they're told apart here.
    gestures.new_turn()
    livefeed.emit("turn", text=text,
                  source=source or ("chat" if context is not None else turnctx.current().source))
    livefeed.emit("server", model=payload["model"], backend=getattr(config, "LLM_BACKEND", ""))
    livefeed.emit("context", used=lmstudio.estimate_tokens(payload), window=_window())

    try:
        livefeed.emit("mood", **mood.portrait_state())
    except Exception:
        pass

    if session._tools_supported:
        # Sticky groups follow your conversation: a turn counts when it
        # joins your history (typed, spoken, Discord, a reminder firing),
        # not stream chat, jobs or the greeting.
        tools.begin_turn(track=context is None and remember)
        payload["tools"] = tools.specs(only=tools_allowed, query=text,
                                       previous=_previous_user_text(replayed))

        try:
            answer = _tool_rounds(payload, model, on_text, on_sentence)
        except RuntimeError as e:
            if "image" in str(e).lower() or "vision" in str(e).lower():
                if getattr(config, "LLM_BACKEND", "") == "llama":
                    fix = ("llama-server was started without the model's vision "
                           "adapter - put its mmproj GGUF next to the model (or "
                           "set MMPROJ in llama/server.env) and restart it")
                else:
                    fix = "load a vision model in LM Studio"

                raise RuntimeError(
                    f"This model can't accept images - {fix}, or turn vision "
                    f"off in agent.json. ({e})"
                ) from e

            # Most likely this model has no tool template. Drop tools for
            # the rest of the session and retry the same turn without
            # them, so the user sees an answer rather than an error.
            if "tool" not in str(e).lower():
                raise

            session._tools_supported = False
            payload.pop("tools", None)
            payload["messages"] = messages

            _log_tool_call(
                "tools", "unsupported by this model - using keyword triggers"
            )

            answer = _generate(payload, on_text, on_sentence)
    else:
        answer = _generate(payload, on_text, on_sentence)

    answer = _strip_leading_timestamps(answer)

    if not answer.strip():
        # This used to be a bare apology, which told nobody anything.
        # An empty reply has a small number of distinct causes and the
        # app knows which one it hit, so say so.
        reason = _why_empty()
        logbook.warn("llm", "empty reply: %s | deltas=%s content=%s reasoning=%s rounds=%s",
                     reason, _last_raw.get("deltas"), _last_raw.get("content"),
                     _last_raw.get("reasoning"), _last_raw.get("tool_rounds"))
        if _last_raw.get("thinking"):
            reason += " - /thoughts shows what it was thinking"

        _log_tool_call("empty reply", reason)
        answer = "...sorry, I got tangled up there. Say that again?"

    # A turn that called tools is never re-run: a second pass could set
    # the reminder twice or write the file twice. Nor is the fallback
    # apology - there's nothing there to double-check.
    second = None
    kept_promise = False

    if (remember and payload.get("tools") and not _last_raw.get("exchanges")
            and getattr(config, "FOLLOW_THROUGH", True) and _promised_action(answer)):
        # She said she'd do it and stopped. Do it - no prefix, the reply
        # already said what's coming. Unless nothing she has does it: then
        # one honest line, not some other tool for the sake of calling one.
        promise = _promised_action(answer)
        _log_tool_call("follow-through", f"said \u201c{promise}\u201d but called nothing - doing it now")
        livefeed.emit("rethink", step="done", outcome="follow-through: promised a step, taking it")
        answer = _follow_through(
            payload, base_messages, answer, model, on_text, on_sentence, "",
            f"(Not from {config.USER}, and nothing new has been said: your reply ended with "
            f"\u201c{promise}\u201d but you didn't call a tool. If one of your tools does that, "
            "call it now and finish the job. If none of them does, don't reach for a different "
            "tool - just say in a sentence that you can't do that from here.)")
        kept_promise = True

    if (adaptive and not kept_promise and not _last_raw.get("exchanges")
            and _last_raw.get("tokens")
            and answer != "...sorry, I got tangled up there. Say that again?"):
        how = _vote if str(getattr(config, "ADAPTIVE_MODE", "vote")).lower() == "vote" else _rethink
        second = how(payload, base_messages, answer, on_text, on_sentence)

    if second and second.get("wants_tools"):
        # She answered without looking, and the second look says she
        # should have. Go and look now, out loud, as a normal tool turn:
        # the first pass called nothing, so nothing runs twice.
        second = None
        answer = _follow_through(
            payload, base_messages, answer, model, on_text, on_sentence,
            "Hang on, let me check.",
            f"(Not from {config.USER} - your own second look: you can check this "
            "yourself with your tools instead of asking. Do it now, then "
            "give the corrected answer.)")

    first_answer = answer

    if second and second["corrected"]:
        # What she actually said, both parts - history and the
        # transcript keep the correction, not a tidier version of events.
        answer = f"{first_answer}\n\n{second['said']}"

    pre_calibration = answer
    spoken = _calibrate(answer, second, remember and source is None, on_text, on_sentence)

    if spoken != answer and not (second and second["corrected"]):
        first_answer = spoken  # the log records what she said, hedge included

    answer = spoken
    extra_flags = []

    if remember and source is None and turn.private:
        answer, first_answer, extra_flags, checked = _ground(
            answer, first_answer, second, payload, base_messages, model, on_text, on_sentence,
            already_hedged=spoken != pre_calibration)

        if checked:
            # The grounding check ran a tool turn: its calls are what the
            # thought log should show, not the vote's empty exchanges.
            second = None

    if remember:
        # The hash is of the system prompt as sent, so a changed persona,
        # rule or memory selection is a different hash - and a flag rate
        # that moves can be lined up against the prompt that moved it.
        prompt_hash = hashlib.sha1(
            messages[0]["content"].encode("utf-8", "replace")
        ).hexdigest()[:12]

        if second:
            _last_raw.update(second["first"])

        _record_thoughts(text, first_answer, started, source,
                         model=payload.get("model", ""), prompt_hash=prompt_hash,
                         extra_flags=extra_flags)

        # The second look as a row of its own, beside the first, so the
        # two can be compared - same question, more thinking.
        if second:
            _last_raw.update(second["second"])
            _record_thoughts(text, second["answer"], started, "rethink",
                             model=payload.get("model", ""), prompt_hash=prompt_hash)

    conf = None

    if second:
        conf = second["conf2"] if second["corrected"] else second["conf"]
    elif _last_raw.get("tokens"):
        try:
            import thoughtlog

            conf = thoughtlog.confidence(_last_raw["tokens"])["conf"]
        except Exception:
            pass

    livefeed.emit("done", seconds=round(time.monotonic() - started, 1), conf=conf)
    gestures.after_reply(text, answer, private=bool(turn.private))

    try:
        import reflect

        reflect.touch()  # any turn, chat included - she's not idle

        if remember and turn.lessons:
            import notebook

            notebook.credit(turn.lessons)

        if remember and turn.skills:
            import skills

            skills.credit(turn.skills)
    except Exception:
        pass

    if not remember:
        # A turn from outside leaves nothing behind: not in history, not
        # in the transcript, and no background pass over it. The keyword
        # extractors below are the point - a viewer typing "remind Ryan
        # to send me money in 5 minutes" must not schedule anything, and
        # the fallback would happily oblige.
        return answer

    # Stored content itself stays clean (no timestamp prefix baked in) -
    # the prefix above is only added when building the API payload, so
    # get_messages_full()'s own "timestamp" field stays the single
    # source of truth and formatting can change later without rewriting
    # anything already saved to disk.
    history.add_message("user", text)
    history.add_message("assistant", answer, tools=_last_raw.get("exchanges"))

    # The same turns, to a file summarization never touches. history.py
    # deletes these once they're folded into the summary; this is what
    # makes "what did we decide last week" answerable.
    transcript.add("user", text)
    transcript.add("assistant", answer)
    history.maybe_summarize(model)
    history.save()

    called = _last_raw.get("called") or set()

    if not session._tools_supported:
        longterm.extract_in_background(model, text, answer)
        reminders.extract_in_background(model, text)
    elif not called & {"set_reminder", "list_reminders", "cancel_reminder"}:
        # She will sometimes say "Got it, setting that for you!" without
        # ever calling set_reminder - a small model choosing to sound
        # helpful over being helpful, and it gets likelier as the tool
        # list grows. The failure is silent and total: a confident
        # confirmation, and nothing scheduled.
        #
        # So when a turn looks like a reminder request and no reminder
        # tool ran, the old keyword extractor gets a go at it. It
        # self-guards (nothing that isn't a reminder reaches the model,
        # and the model answers NONE when it isn't one), it does its
        # date arithmetic in the same timeutil everything else uses, and
        # it announces what it scheduled - so a caught one is visible
        # rather than quietly patched over.
        if reminders.looks_like_reminder(text):
            logbook.warn(
                "reminders",
                "claimed but never called set_reminder - falling back: %s",
                text[:120],
            )

        reminders.extract_in_background(model, text)

    return answer
