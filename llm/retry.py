"""Try again: her latest reply thrown away, and the same message answered
afresh (the ↻ under her reply on the chat page, or /retry).

Only where that's safe to do twice. Her latest reply has to answer your own
latest message, typed or spoken, with:

  no tools        a retry would run the command, send the email, set the
                  reminder or save the fact again
  no file         history keeps a marker for a picture or document, not the
                  file, so it can't be sent again
  no guest        someone else's turn is theirs to redo
  at the desk     a station's reply was spoken there; a retry from here
                  would speak on the PC
  nothing since   a greeting, a "you're back", a touch reaction or another
                  turn after it, in history or on screen, and it's gone.
                  A system line (/good's answer, a /command's) doesn't count:
                  that's the screen talking to you, not a turn

A retry takes the pair out of her history, marks it withdrawn in the
transcript (core/transcript.py; append-only, so a marker, never an edit),
takes her reply off the screen, and runs your words as a turn again: new
thought log row, new reply, but no second mood reading or drift step, no
fact extraction and no reminder catcher, since it's the same message.
"""
import threading

_lock = threading.Lock()
_last = {}      # the newest turn that went into history: what a retry would redo


def note(text, answer, entries, ok):
    """Every turn that went into history, from llm/turns.py. entries: the two
    history dicts it added (user, assistant). ok: safe to do twice."""
    with _lock:
        _last.clear()
        _last.update(text=str(text or ""), answer=str(answer or ""), entries=tuple(entries), ok=bool(ok))


def forget():
    with _lock:
        _last.clear()


def _state():
    """(text, answer, entries, index on screen) when a retry is possible, else
    (None, why). Caller doesn't hold anything."""
    import config
    import ui
    from core import history
    from ui.shared import _lock as ui_lock

    with _lock:
        last = dict(_last)
    if not last:
        return None, "there's no reply of hers to try again"
    if not last["ok"]:
        return None, ("her last reply can't be tried again (it used a tool, came with a file, "
                      "went to a station, or wasn't to you)")
    try:
        from mind import mood

        if mood.away():
            return None, "she's walked away for now"        # a retry mustn't get round a sulk
    except Exception:
        pass
    tail = history.tail(2)
    if len(tail) != 2 or tail[0] is not last["entries"][0] or tail[1] is not last["entries"][1]:
        return None, "something came after her last reply, so it can't be tried again"
    me = config.AGENT_NAME.lower()
    with ui_lock:
        conv = list(ui.conversation)
        streaming = ui.view.streaming
    at = latest_reply(conv, me)
    if streaming is not None or at is None or conv[at][1].strip() != last["answer"].strip():
        return None, "something came after her last reply, so it can't be tried again"
    return (last["text"], last["answer"], last["entries"], at), ""


def latest_reply(conv, me):
    """Index of her latest reply when only system lines come after it, else None."""
    for i in range(len(conv) - 1, -1, -1):
        if conv[i][0] == me:
            return i
        if conv[i][0] != "system":
            return None
    return None


def available():
    """Her reply's index on screen when ↻ can show, else None. Still shown
    while she's speaking it: a retry cuts the voice off, like a new message.
    While a reply is being written it isn't: the screen's last message is
    still open (streaming) then, and that turn isn't in history yet."""
    try:
        found, _why = _state()
        return found[3] if found else None
    except Exception:
        return None


def take():
    """Undo the last turn so it can run again: (text, undo), or (None, why).
    Called holding her turn (core/assistant.py), so nothing lands in between.
    undo goes to put_back() if the new turn fails."""
    import ui
    from core import history, transcript
    from ui.shared import _lock as ui_lock, _refresh

    found, why = _state()
    if not found:
        return None, why
    text, answer, entries, at = found
    try:
        from training import dataset

        dataset.retrying(ui.view.epoch, answer, text)     # a thumbs up on the new one can pair them
    except Exception:
        pass
    if not history.drop(entries):
        return None, "something came after her last reply, so it can't be tried again"
    history.save()
    transcript.withdraw()
    with ui_lock:
        if 0 <= at < len(ui.conversation) and ui.view.streaming is None and ui.conversation[at][1] == answer:
            ui.conversation.pop(at)
    _refresh()
    forget()
    return text, (text, answer, entries)


def put_back(undo, error):
    """The new reply failed (the server down, an error): her first reply comes
    back - history, transcript, the screen - so a retry never costs you the
    answer you had. Only what the failed turn didn't already replace."""
    import config
    import ui
    from core import history, transcript
    from ui.shared import _lock as ui_lock

    text, answer, entries = undo
    if not history.tail(1) or history.tail(1)[0].get("role") != "assistant":
        history.restore(entries)
        history.save()
        transcript.add("user", text)
        transcript.add("assistant", answer)
        note(text, answer, entries, ok=True)
    me = config.AGENT_NAME.lower()
    with ui_lock:
        last = ui.conversation[-1] if ui.conversation else None
    if last is None or last[0] != me:
        ui.add_message(me, answer)
    ui.add_message("system", f"Trying again failed ({error}); her first reply is back.")
