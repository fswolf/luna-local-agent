"""The tool loop: run the model, execute what it calls, repeat until it answers.

Part of the llm package (it was one llm.py); see llm/__init__.py.
"""

from config import MAX_TOOL_ROUNDS
import gestures
import interrupts
import livefeed
import logbook
import tools
import turnctx
import vision

from .streaming import _Narrator, _THINK_BLOCK, _calls_from_text, _chat_completion, _content, _last_raw, _visible

def _force_prose(payload, on_text=None, on_sentence=None):
    """Ask again with no tools offered.

    After a tool result some models keep trying to call something, or
    answer with nothing at all. Removing the tools takes that option
    away, so they have to produce words.
    """
    if interrupts.current().generating.is_set():
        return ""       # stopped: no new request to make up for it

    payload = dict(payload)
    payload.pop("tools", None)
    payload.pop("tool_choice", None)
    payload["messages"] = payload["messages"] + [{
        "role": "user",
        "content": "(Tell me what you just did, in one short sentence. "
                   "Do not call any more tools.)",
    }]

    if on_text or on_sentence:
        narrator = _Narrator(on_text, on_sentence)
        _chat_completion(payload, narrator)

        return narrator.finish()

    return _content(_chat_completion(payload))


def _tool_rounds(payload, model, on_text=None, on_sentence=None):
    """Run the model, execute any tools it asks for, repeat.

    Returns the final assistant text. Each round appends the assistant's
    tool_calls message and one `tool` message per call, which is the
    shape OpenAI-compatible servers expect on the way back in.

    Every round is streamed, including the ones that turn out to be
    tool calls - those simply produce no prose, so nothing is spoken.
    The round that finally answers starts talking while it is still
    being generated.
    """

    streaming = bool(on_text or on_sentence)
    _last_raw["called"] = set()
    _last_raw["exchanges"] = []

    # A round can produce prose *and* a tool call ("let me check that
    # for you" followed by get_datetime). That preamble is spoken and
    # shown as it arrives, so it has to end up in the returned text
    # too, or replace_message would wipe it off the screen.
    said = []

    # A game turn can ask for more rounds than chat gets (Vibe City's
    # checklist is a dozen calls); assistant.respond_to_job sets it.
    rounds = int(turnctx.current().max_rounds or MAX_TOOL_ROUNDS)

    for _round in range(rounds):
        # Stopped (HOME, !stop) - while a tool ran, or before the turn
        # even got the model: no new round.
        if interrupts.current().generating.is_set():
            return " ".join(said).strip()

        _last_raw["tool_rounds"] = _round + 1
        livefeed.emit("round", n=_round)
        narrator = _Narrator(on_text, on_sentence)
        message = _chat_completion(payload, narrator)
        calls = message.get("tool_calls") or []
        text = narrator.finish() if streaming else _content(message)

        if not streaming:
            gestures.from_tags(_THINK_BLOCK.sub("", message.get("content") or ""))

        # Some turns the model writes the call out as text instead of
        # sending it (Qwen's <function=...> form slipping past the
        # server's parser). It's already kept off the screen and out of
        # the voice; here it's run like any other call.
        if not calls:
            raw = narrator.raw if streaming else (message.get("content") or "")
            calls = _calls_from_text(raw, payload)
            if calls:
                logbook.info("tools", "ran %d tool call(s) the model wrote as text", len(calls))
                text = _visible(raw).strip() if not streaming else text
                message = dict(message, content=text)

        if text:
            said.append(text)

        if not calls:
            if said:
                return " ".join(said).strip()

            # Nothing usable and nothing to call: the model has finished
            # but said nothing. One more attempt with tools removed.
            return _force_prose(payload, on_text, on_sentence) or ""

        # The thinking that led here gets told what it decided. Only if
        # this run actually thought - a run with no scratchpad added no
        # entry, and the names would land on the previous round's.
        if _last_raw["thinking"] and _last_raw["thinking"][-1].get("run") is None:
            _last_raw["thinking"][-1]["run"] = _round
            _last_raw["thinking"][-1]["called"] = [
                _call_label(c.get("function") or {}) for c in calls
            ]

        # Echo the assistant turn back verbatim - dropping it breaks the
        # pairing between tool_call_id and result.
        payload["messages"].append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": calls,
        })

        for call in calls:
            function = call.get("function", {})
            name = function.get("name", "")
            arguments = function.get("arguments", "{}")
            _last_raw["called"].add(name)
            logbook.info("tools", "%s(%s)", name, str(arguments)[:300])
            livefeed.emit("tool", name=name, args=" ".join(str(arguments).split())[:300])

            # Only what this turn was offered. A model can name any tool
            # it has heard of - from the prompt, from history - and a
            # stream-chat turn's narrow list means nothing if a name
            # outside it still runs.
            offered = {(t.get("function") or {}).get("name") for t in payload.get("tools") or ()}

            # Routing sends only the groups a turn seems to need. A tool
            # that was allowed but not sent - she knew its name from the
            # prompt or history - is attached and run, not refused. The
            # turn's ceiling still decides what "allowed" means.
            if name not in offered and tools.attach(name):
                offered.add(name)

            if name not in offered:
                result = f"Error: {name} isn't available right now."
                logbook.warn("tools", "refused %s - not offered this turn", name)
            else:
                result = tools.call(name, arguments)
            livefeed.emit("tool_result", name=name,
                          result=result if len(result) <= 200 else result[:197] + "...")
            logbook.info("tools", "%s -> %s", name, str(result)[:300])
            _last_raw["exchanges"].append(
                {"name": name, "arguments": arguments, "result": result}
            )
            turnctx.current().exchanges.append(
                {"name": name, "arguments": arguments, "result": result})

            _log_tool_call(name, result)

            payload["messages"].append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "name": name,
                "content": result,
            })

        # more_tools, or a hidden tool called by name, attached a group:
        # the next round gets the longer list.
        routed = tools.refresh()

        if routed is not None and payload.get("tools"):
            payload["tools"] = routed

        # look_at_screen has no way to put an image in a tool result -
        # the field is a string - so it stashes the capture and we hand
        # it over here as a user turn instead. A text-only model will
        # reject this payload, and the error says so plainly rather than
        # us pretending she looked.
        label = vision.label()
        image = vision.take()

        if image:
            payload["messages"].append({
                "role": "user",
                "content": [
                    {"type": "text",
                     "text": f"(Here is {label} you asked for.)"},
                    {"type": "image_url", "image_url": {"url": image}},
                ],
            })

    # Out of rounds: same treatment, so a model stuck in a call loop
    # still produces something the user can read.
    if said:
        return " ".join(said).strip()

    return _force_prose(payload, on_text, on_sentence) or ""


def _log_tool_call(name, result):
    """Surface tool use in the conversation, so it's never a mystery why
    a reminder appeared or where a fact came from."""
    try:
        import ui
    except Exception:
        return

    summary = result if len(result) <= 160 else result[:157] + "..."
    ui.add_message("system", f"{name}() -> {summary}")


def _why_empty():
    """Best explanation for a reply that came back with no words in it."""
    stop = interrupts.current()

    if stop.generating.is_set():
        return "you interrupted it, so generation was cut short"

    if stop.speaking.is_set():
        return (
            "playback was stopped mid-reply - if you didn't press HOME, "
            "barge-in is firing on her own voice. Check /barge and raise "
            "stt.barge_in_margin"
        )

    if _last_raw.get("reasoning") and not _last_raw.get("content"):
        return (
            "the model produced only reasoning and no answer - lower "
            "generation.reasoning in agent.json, or raise max_tokens"
        )

    if _last_raw.get("tool_rounds", 0) >= MAX_TOOL_ROUNDS:
        return (
            f"it called tools {MAX_TOOL_ROUNDS} times without answering - "
            "raise tools.max_rounds, or the model is stuck in a loop"
        )

    if not _last_raw.get("deltas"):
        return "LM Studio streamed nothing at all - is the model still loaded?"

    return "the model returned no usable text"


def _call_label(function):
    """get_datetime({}) as `get_datetime`, set_reminder(...) with its
    arguments, cut short: what she decided is only half the story
    without what she decided to ask for."""
    name = function.get("name", "?")
    args = " ".join(str(function.get("arguments") or "").split())

    if args in ("", "{}"):
        return name

    return f"{name}({args[:90]}{'…' if len(args) > 90 else ''})"


def _generate(payload, on_text=None, on_sentence=None):
    """One completion, streamed or not depending on who's listening."""
    if on_text or on_sentence:
        narrator = _Narrator(on_text, on_sentence)
        _chat_completion(payload, narrator)

        return narrator.finish()

    return _content(_chat_completion(payload))
