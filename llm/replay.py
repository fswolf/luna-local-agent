"""Turning stored history into messages the model sees again: timestamps, replayed tool calls, the worked tool example, the timing note.

Part of the llm package (it was one llm.py); see llm/__init__.py.
"""

import json
import re
from datetime import datetime

from core import timeutil
import tools

def _format_ts(when):
    """A stored timestamp as the prefix the model actually reads:
    'today 14:32, 17 minutes ago' rather than '2026-09-19T14:32:07'.

    The model used to be handed ISO timestamps and told to work out
    elapsed time from them. It was bad at it - confidently bad, calling
    yesterday "a few minutes ago" - and there was never a reason for it
    to try, since Python knows the answer exactly. Doing the
    subtraction here removes the failure and costs fewer tokens than
    the timestamp it replaces.
    """
    if isinstance(when, datetime):
        return timeutil.stamp(when)

    try:
        return timeutil.stamp(datetime.fromisoformat(str(when)))
    except (ValueError, TypeError):
        return str(when)


def _strip_leading_timestamps(text):
    """Models mimic whatever format they can see, so some of them open
    a reply with the prefix. Both forms are stripped: conversations
    saved before this change still carry the ISO one."""
    for pattern in (
        r"^(\[\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\]\s*)+",
        r"^(\[(?:today|tomorrow|yesterday|last \w+|\w{3} \d)[^\]]{0,48}\]\s*)+",
    ):
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    return text.strip()


def _timestamped(role, content, timestamp):
    """A history message, with no timestamp in it.

    It used to carry one - "[today 14:32, 17 minutes ago] ..." - so the
    model could judge elapsed time. That backfired twice. First she read
    the prefix aloud, because it was in the text and the text gets
    spoken. Then /tooltest found the real cost: with history attached
    she stopped calling tools entirely and answered in prose beginning
    with a timestamp of her own.

    Which makes sense. Every assistant message in history is prose, none
    of them are tool calls, and they all start the same way - so the
    history is a few-shot demonstration that the job is producing text
    in that shape. In-context examples beat instructions, and there were
    fifteen examples against one instruction.

    The timing information moves to _timing_note(), which states it once
    in the system prompt where there is no pattern to copy.
    """
    return {"role": role, "content": content}


def _valid_json(raw):
    """`raw` if it parses as a JSON object, "{}" otherwise."""
    try:
        return raw if raw and isinstance(json.loads(raw), dict) else "{}"
    except (ValueError, TypeError):
        return "{}"


def _replay(message):
    """One stored turn, as the messages the model should see.

    A turn that used tools becomes three messages rather than one - the
    assistant asking, the result coming back, the assistant answering -
    which is the shape the API defines and, more to the point, an
    example of the behaviour we want repeated. Without these the
    history only ever demonstrates talking.
    """
    calls = message.get("tools") or []

    if not calls:
        return [_timestamped(message["role"], message["content"],
                             message.get("timestamp"))]

    replayed = [{
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": f"past{index}",
                "type": "function",
                "function": {
                    "name": call.get("name", ""),
                    # Belt and braces: LM Studio parses this to render
                    # the chat template, and a fragment that doesn't
                    # parse comes back as an HTML 500 with no clue why.
                    "arguments": _valid_json(call.get("arguments")),
                },
            }
            for index, call in enumerate(calls)
        ],
    }]

    for index, call in enumerate(calls):
        replayed.append({
            "role": "tool",
            "tool_call_id": f"past{index}",
            "name": call.get("name", ""),
            "content": call.get("result", ""),
        })

    if message.get("content"):
        replayed.append({"role": message["role"], "content": message["content"]})

    return replayed


def _demonstration():
    """One worked tool call, for a history that contains none.

    _replay solves the problem going forward: once a turn in history
    used a tool, the model can see that tools get used. It does nothing
    for the hole it has to climb out of first. A fresh install, a
    cleared history, or the transcript this app has been accumulating
    all day are all the same situation - fifteen examples of answering
    in prose, zero of calling anything - and that is the state the
    bisect showed breaking tool calling outright.

    So when the window has no example in it, one is supplied. Not a
    fabricated one: the tool is actually called and the real result
    goes in, which costs nothing (get_datetime is local and instant)
    and has the side effect of putting the current time in front of her
    without a round trip. It disappears on its own the moment history
    has a real exchange to show instead.
    """
    try:
        result = tools.call("get_datetime", "{}")
    except Exception:
        return []

    if not result:
        return []

    now = datetime.now()

    return [
        {"role": "user", "content": "what time is it?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "example0",
                "type": "function",
                "function": {"name": "get_datetime", "arguments": "{}"},
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "example0",
            "name": "get_datetime",
            "content": result,
        },
        {
            "role": "assistant",
            "content": f"It's {now.strftime('%H:%M')} on {now.strftime('%A')}.",
        },
    ]


def _has_tool_example(messages):
    return any(m.get("tool_calls") for m in messages)


def _timing_note(messages):
    """When the conversation below happened, said once.

    Replaces the per-message prefixes. Same information, stated as a
    fact rather than demonstrated fifteen times in the shape of a reply.
    """
    stamps = []

    for message in messages:
        try:
            stamps.append(datetime.fromisoformat(str(message.get("timestamp"))))
        except (ValueError, TypeError):
            continue

    if not stamps:
        return ""

    now = datetime.now()
    started = timeutil.relative(stamps[0], now)
    latest = timeutil.relative(stamps[-1], now)

    if len(stamps) > 1 and started != latest:
        opening = (f"the most recent message was {latest}, "
                   f"and it began {started}.")
    else:
        opening = f"the most recent message was {latest}."

    note = [
        "",
        "The conversation below carries no timestamps. For reference: "
        + opening,
    ]

    # A long silence in the middle is the thing worth knowing about - it
    # is the difference between one conversation and two.
    if len(stamps) > 1:
        gaps = [(stamps[i + 1] - stamps[i], i) for i in range(len(stamps) - 1)]
        longest, where = max(gaps, default=(None, 0))

        if longest and longest.total_seconds() > 3600:
            span = timeutil.relative(
                stamps[where] + longest, stamps[where]
            ).replace("in ", "")
            note.append(
                f"There is a gap of {span} partway through it - what "
                "follows the gap is a later conversation."
            )

    return "\n".join(note) + "\n"
