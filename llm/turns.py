"""One turn end to end (ask), the thought log record, and the prompt budget for /context.

Part of the llm package (it was one llm.py); see llm/__init__.py.
"""

import hashlib
import time
from datetime import datetime

import config
from core import history
from life import gestures
from web import livefeed
from core import lmstudio
from core import logbook
from mind import mood
from mind import longterm
from life import reminders
import tools
from core import transcript
from core import turnctx
from mind import websearch
from voice import hearing

from . import session
from .prompts import _calibration_note, _previous_user_text, build_generation_params, build_memory_prompt, build_self_prompt, build_tools_prompt, turn_prompt, with_live
from .replay import _demonstration, _has_tool_example, _replay, _strip_leading_timestamps, _timestamped
from .rounds import _generate, _log_tool_call, _tool_rounds, _why_empty
from .second_look import (_adaptive_on, _calibrate, _ONLY_WHAT_CHANGED, _follow_through, _ground,
                          _promised_action, _rethink, _unbacked, _vote, turn_steps)
from .streaming import _last_raw

_window_cache = {"at": 0.0, "n": 0}

# How a server says the model itself can't take tools, as opposed to one
# tool call going wrong. Only these switch tools off for the session.
_NO_TEMPLATE_SIGNS = ("template", "jinja", "not support", "unsupported", "doesn't support",
                      "does not support", "tools param requires")


def _no_tool_template(error):
    text = str(error).lower()
    return "tool" in text and any(sign in text for sign in _NO_TEMPLATE_SIGNS)


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
        from mind import thoughtlog

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
            agent=config.AGENT_NAME,
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
    past = history.recent()
    system, live = turn_prompt(text, past)
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
        from mind import situation

        situation_block = situation.block()
    except Exception:
        situation_block = ""

    from .prompts import _profile

    profile_block = _profile(True)
    whole = system + live
    parts = {
        "persona + rules": lmstudio.estimate_tokens(whole) - lmstudio.estimate_tokens(memory_block) - lmstudio.estimate_tokens(tools_block) - lmstudio.estimate_tokens(self_block) - lmstudio.estimate_tokens(situation_block) - lmstudio.estimate_tokens(profile_block),
        "profile of who you're talking to": lmstudio.estimate_tokens(profile_block),
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


def _tool_steps(answer):
    """(the tool rounds, her answer after them) for a training example, or
    None when the reply on screen isn't exactly those rounds' words: put
    right by a second look or a follow-through, stopped partway, or a
    screenshot handed in, which an example can't hold."""
    rounds, final = _last_raw.get("rounds") or [], _last_raw.get("rounds_final")
    if not rounds or not final or _last_raw.get("rounds_image"):
        return None
    said = [m["content"] for m in rounds if m.get("role") == "assistant" and m.get("content")]
    if _strip_leading_timestamps(" ".join(said + [final]).strip()) != answer.strip():
        return None
    return [dict(m) for m in rounds], _strip_leading_timestamps(final).strip()


def _heard(send, payload, *args):
    """Send the turn; if the server turned the recording away, once more
    as words only (hearing.drop says so in the log)."""
    try:
        return send(payload, *args)
    except RuntimeError as e:
        if not hearing.drop(payload, e):
            raise
        _log_tool_call("hearing", "the server wouldn't take the recording, sent the words only")
        return send(payload, *args)


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
    # This turn's tool calls. Only the tool rounds reset these, so a turn
    # without tools kept the last turn's: saved into this turn's history,
    # and read as "a tool was called" by the second look and held speech.
    _last_raw["exchanges"] = []
    _last_raw["called"] = set()
    _last_raw["steps"] = []           # follow-throughs, in order (second_look._note_step)
    _last_raw["steps_said"] = ""

    past = [] if context is not None else history.recent()
    turn = turnctx.current()
    turn.private = context is None
    # A fresh turn starts clean. A stream-chat turn starts marked: its
    # words are a stranger's from the first token.
    turn.seen = "stream chat" if context is not None else None
    turn.read_local = False
    turn.lessons = []
    turn.skills = []
    # A turn from stream chat never sees her notes on Ryan's
    # conversations - "last time" is his business, not the room's.
    # live: what changes every turn, in front of the latest message so the
    # system prompt stays the same and the server can reuse it
    # (llm.stable_prompt); "" when that's off.
    system, live = turn_prompt(text, past, private=context is None)
    messages = [{"role": "system", "content": system}]

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
    # and anything real that follows takes precedence over it. Not on a
    # game's turn (clock off): its worked example is "what time is it?",
    # and a game turn starts with no history, so that question was the
    # only conversation she saw - and she answered it, every turn.
    if session._tools_supported and not _has_tool_example(replayed) and turnctx.current().clock:
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

    # Said out loud with stt.send_audio on and a model that can hear: the
    # recording goes with the words (voice/hearing.py). Words only otherwise.
    # Taken off the turn as it's used: a second ask inside the same turn
    # (some other question entirely) mustn't get this recording too.
    recording, turn.recording = turn.recording, None
    # A file sent with the message (core/attachments.py): this request only.
    # It's outside content, so the turn counts as having read some (what
    # her tools ask before acting on), and the history keeps just a line.
    attached, turn.attachment = turn.attachment, None
    if attached is not None:
        from core import attachments

        turn.seen = turn.seen or f"a file you sent ({attached.name})"
        body = attachments.content(user_content, attached)
    else:
        body = hearing.content(user_content, recording)
    # The turn's note goes in front of the words (and of the line saying a
    # recording is attached). Only on this message, and only in the request:
    # history.add_message below stores what was said, so the note never
    # piles up turn after turn.
    messages.append(_timestamped("user", with_live(live, body), now))
    # The same message as /good would keep it: the words and that a file was
    # sent, never the file or a document's text (core/attachments.py).
    kept_user = (_timestamped("user", with_live(live, f"{user_content}\n{attached.marker()}"), now)
                 if attached is not None else None)

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

    payload.update(build_generation_params(payload["model"]))

    # Adaptive thinking: a modest budget up front, a deeper second look
    # only if the answer comes out shaky. The messages are copied now,
    # before tool rounds append to them, so a rethink asks the same
    # question afresh rather than continuing the first attempt.
    adaptive = _adaptive_on(remember)
    base_messages = list(messages)

    # Held speech: her sentences wait until the reply has had its second
    # look, so a reply that gets corrected is never half-said and only the
    # one she settles on is spoken. Once a tool is called there's no second
    # look, and from then on she speaks as she goes.
    speech = (_HeldSpeech(on_sentence)
              if adaptive and on_sentence and getattr(config, "ADAPTIVE_HOLD_SPEECH", True) else None)
    first_sentence = speech or on_sentence

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
                  source=source or ("chat" if context is not None else turnctx.current().source),
                  guest=bool(getattr(turnctx.current(), "speaker", None)))    # not the owner: the portrait won't undress for them
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
            answer = _heard(_tool_rounds, payload, model, on_text, first_sentence)
        except RuntimeError as e:
            if "image" in str(e).lower() or "vision" in str(e).lower():
                if getattr(config, "LLM_BACKEND", "") == "llama":
                    fix = ("llama-server was started without the model's vision "
                           "adapter - put its mmproj GGUF next to the model (or "
                           "set MMPROJ in server/llama/server.env) and restart it")
                else:
                    fix = "load a vision model in LM Studio"

                raise RuntimeError(
                    f"This model can't accept images - {fix}, or turn vision "
                    f"off in agent.json. ({e})"
                ) from e

            if "tool" not in str(e).lower():
                raise

            payload.pop("tools", None)
            payload["messages"] = messages

            if _no_tool_template(e):
                # This model has no tool template. Drop tools for the rest
                # of the session and retry the same turn without them, so
                # the user sees an answer rather than an error.
                session._tools_supported = False
                _log_tool_call(
                    "tools", "unsupported by this model - using keyword triggers"
                )
            else:
                # Anything else that mentions tools ("failed to parse tool
                # call arguments") is one bad generation, not the model:
                # this turn goes without, the next one gets them back.
                logbook.warn("llm", "tool round failed, answering this turn without tools: %s", e)
                _log_tool_call("tools", "that went wrong, answering without tools this once")

            if speech:
                speech.forget()     # the failed attempt's sentences: only the retry's are hers

            answer = _heard(_generate, payload, on_text, first_sentence)
    else:
        answer = _heard(_generate, payload, on_text, first_sentence)

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
        if speech:
            speech.release()
        _log_tool_call("follow-through", f"said \u201c{promise}\u201d but called nothing - doing it now")
        livefeed.emit("rethink", step="done", outcome="follow-through: promised a step, taking it")
        answer = _follow_through(
            payload, base_messages, answer, model, on_text, on_sentence, "",
            f"(Not from {config.USER}, and nothing new has been said: your reply ended with "
            f"\u201c{promise}\u201d but you didn't call a tool. If one of your tools does that, "
            "call it now and finish the job. If none of them does, don't reach for a different "
            "tool - just say in a sentence that you can't do that from here. Your reply is already "
            "out, so don't repeat any of it: after the tool, say only what it showed, in a "
            "sentence or two.)")
        kept_promise = True

    unbacked = (_unbacked(answer, _last_raw.get("exchanges"), text)
                if remember and payload.get("tools") and not kept_promise
                and getattr(config, "FOLLOW_THROUGH", True) else "")

    if unbacked:
        # She said she did it, or that it works, and the record says
        # otherwise. Back to it, out loud: do it now or own up. The calls
        # made before stay in this turn's record.
        if speech:
            speech.release()
        before, called = list(_last_raw.get("exchanges") or []), set(_last_raw.get("called") or ())
        _log_tool_call("follow-through", unbacked[0].upper() + unbacked[1:].split(". ")[0])
        livefeed.emit("rethink", step="done", outcome="follow-through: a claim the tools don't back")
        answer = _follow_through(
            payload, base_messages, answer, model, on_text, on_sentence, "",
            f"(Not from {config.USER} - your own check: {unbacked} {_ONLY_WHAT_CHANGED})")
        _last_raw["exchanges"] = before + list(_last_raw.get("exchanges") or [])
        _last_raw["called"] = called | set(_last_raw.get("called") or ())
        kept_promise = True

    if (adaptive and not kept_promise and not _last_raw.get("exchanges")
            and _last_raw.get("tokens")
            and answer != "...sorry, I got tangled up there. Say that again?"):
        how = _vote if str(getattr(config, "ADAPTIVE_MODE", "vote")).lower() == "vote" else _rethink
        try:
            second = how(payload, base_messages, answer, on_text, on_sentence, held=bool(speech))
        except Exception:
            if speech:
                speech.release()    # the second look failed: the reply she wrote still gets said
            raise

    if speech:
        # Corrected: the first reply was never said, and now never will be.
        # Anything else: say it now.
        speech.drop() if (second and second.get("corrected")) else speech.release()

    if second and second.get("wants_tools"):
        # She answered without looking, and the second look says she
        # should have. Go and look now, out loud, as a normal tool turn:
        # the first pass called nothing, so nothing runs twice.
        second = None
        answer = _follow_through(
            payload, base_messages, answer, model, on_text, on_sentence,
            "Hang on, let me check.",
            f"(Not from {config.USER} - your own second look: you can check this "
            "yourself with your tools instead of asking. Do it now. " + _ONLY_WHAT_CHANGED + ")")

    first_answer = answer

    if second and second["corrected"]:
        # The answer she settled on takes the first one's place, on screen
        # and in history: glued on after it, she said nearly the same thing
        # twice, and then copied that from her own history. The thought log
        # still keeps both, side by side (below).
        answer = second["answer"]

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

    if remember and source is None and turn.private and not turn.speaker and not turn.job \
            and not turn.remote:
        # Your own turn, offered for /good and /fix (training/dataset.py):
        # held in memory only, written nowhere unless you keep it.
        try:
            from training import dataset

            used = bool(_last_raw.get("exchanges")) or bool(turn.exchanges)
            steps, reply = (_tool_steps(answer) if used else None) or (None, answer)
            dataset.note_turn(base_messages[0]["content"], replayed, kept_user or hearing.words_only(base_messages[-1]), reply,
                              model=payload.get("model", ""), used_tools=used,
                              rounds=steps, tools=payload.get("tools") if steps else None)
        except Exception:
            logbook.exception("llm", "couldn't note the turn for /good")

    if remember:
        # The hash is of the system prompt as sent, so a changed persona,
        # rule or memory selection is a different hash - and a flag rate
        # that moves can be lined up against the prompt that moved it.
        prompt_hash = hashlib.sha1(
            (messages[0]["content"] + live).encode("utf-8", "replace")
        ).hexdigest()[:12]

        if second:
            _last_raw.update(second["first"])

        _record_thoughts(text, first_answer, started, source,
                         model=payload.get("model", ""), prompt_hash=prompt_hash,
                         extra_flags=extra_flags)

        # The second look as a row of its own, beside the first, so the
        # two can be compared - same question, more thinking. "rethink" was
        # only checked behind the scenes; "correction" she said out loud.
        if second:
            _last_raw.update(second["second"])
            _record_thoughts(text, second["answer"], started, "correction" if second["corrected"] else "rethink",
                             model=payload.get("model", ""), prompt_hash=prompt_hash)

    conf = None

    if second:
        conf = second["conf2"] if second["corrected"] else second["conf"]
    elif _last_raw.get("tokens"):
        try:
            from mind import thoughtlog

            conf = thoughtlog.confidence(_last_raw["tokens"])["conf"]
        except Exception:
            pass

    livefeed.emit("done", seconds=round(time.monotonic() - started, 1), conf=conf)
    gestures.after_reply(text, answer, private=bool(turn.private))

    try:
        from mind import reflect

        reflect.touch()  # any turn, chat included - she's not idle

        if remember and turn.lessons:
            from mind import notebook

            notebook.credit(turn.lessons)

        if remember and turn.skills:
            from mind import skills

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
    # Someone other than the owner said it (senses/people.py): the history says
    # who, so later turns don't put their words in his mouth.
    from senses import people

    guest = people.guest()
    said = f"[{guest}] {text}" if guest else text
    if attached is not None:
        said = f"{said}\n{attached.marker()}"      # that it was sent, never the file
    history.add_message("user", said)
    history.add_message("assistant", answer, tools=_last_raw.get("exchanges"), steps=turn_steps(answer))

    # The same turns, to a file summarization never touches. core/history.py
    # deletes these once they're folded into the summary; this is what
    # makes "what did we decide last week" answerable.
    transcript.add("user", said)
    transcript.add("assistant", answer)
    history.maybe_summarize(model)
    history.save()

    called = _last_raw.get("called") or set()

    if source in ("reminder", "task"):
        # Her own reminder or task firing. Its text names a time ("6 PM daily
        # inbox sweep"), so the nets below read it as a new request and tried
        # to schedule it again. It's a note she wrote, not something you said.
        return answer

    if not session._tools_supported:
        longterm.extract_in_background(model, text, answer)
        reminders.extract_in_background(model, text)
    elif not called & tools.SCHEDULES:
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

        # The same safety net for memory: you said "remember this" and she
        # answered without calling remember_fact (it happened: "Remember
        # this: your mind runs on UnraidTower's RX 7900 XT" got a warm reply
        # and nothing saved). The extraction pass looks at the turn, told
        # you asked, and keeps what you meant unless it's known already.
        if "remember_fact" not in called and longterm.asked_to_remember(text):
            logbook.info("longterm", "asked to remember, no remember_fact call - extracting: %s", text[:120])
            longterm.extract_in_background(model, text, answer, asked=True)

    return answer


class _HeldSpeech:
    """Her sentences for the voice, held back until the turn knows whether
    the reply stands. Called like on_sentence. release() speaks what's held
    and lets the rest through; drop() throws it away for good (the reply was
    replaced); forget() throws it away and keeps holding (a retry)."""

    def __init__(self, on_sentence):
        self._on_sentence = on_sentence
        self._held = []
        self._open = False

    def __call__(self, sentence):
        if not self._open and _last_raw.get("exchanges"):
            self.release()      # a tool was called: no second look, so no reason to wait
        if self._open:
            self._on_sentence(sentence)
        else:
            self._held.append(sentence)

    def release(self):
        held, self._held, self._open = self._held, [], True
        for sentence in held:
            self._on_sentence(sentence)

    def drop(self):
        self._held, self._open = [], True

    def forget(self):
        self._held = []
