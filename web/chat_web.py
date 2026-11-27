"""/chat/: talk to her in a browser - the same conversation as the terminal.

Served by the live monitor (web/livefeed.py), so it's localhost only with the
same Host and Origin checks. Nothing here keeps its own copy of the chat: the
page mirrors ui.conversation, and what you send goes through the same door as
Enter in the terminal (ui.submit_soon), so a /command typed here runs as one
and her answer streams into both. A tool's question (ui.ask_approval) shows
in the page too, and either side can answer it.

    GET  /chat/            the page
    GET  /chat/head.js     her header, put on every page by livefeed.with_switcher
    GET  /chat/logo.png    her emblem, for the menu button
    GET  /chat/state       the conversation from where the page is up to; waits
                           up to WAIT seconds for something to change (v=).
                           head=1: only her header (status, model, busy, mic, voice);
                           tray=1 as well: the tray icon is up (app/tray.py)
    POST /chat/say         {"text"} or a form with "text" and one "file"
    POST /chat/talk        HOME from the page (talk, done, or stop her)
    POST /chat/dictate     the mic button: your words into the text box, not sent
    GET  /chat/spell?w=&w= {word: {"known", "suggestions"}} for the right-click menu (web/head.js)
    POST /chat/speak       {"e", "i"}: say one of her replies again (the speaker
                           under it); again on the same one stops it
    POST /chat/stop        stop her (and anything physical), like ai-voice-ctl stop
    POST /chat/answer      {"id", "answer": "yes" | "no" | "all"}
    POST /chat/rate        {"e", "i", "up": true|false, "better"}: the thumbs on her
                           reply at conversation index i (matched by its text), kept as an example for her
                           patches (training/dataset.py rate)
    POST /chat/tray        {"action": "chat" | "portrait" | "settings" | "voice" | "quit"}: the
                           tray icon's menu (chat opens her window; voice flips tts.enabled)
"""
import itertools
import json
import os
import secrets
import threading
import time
import urllib.parse

NAME = "chat"
WAIT = 20            # seconds a /state request waits for something new
BATCH = 0.05         # seconds to gather changes once one comes
KEEP = 300           # messages a page starts with; older ones stay in the terminal
MAX_TYPED = 20000    # characters in one message
MAX_BODY = 11 * 1024 * 1024   # a 10 MB picture and the form around it

_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat.html")
_HEAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "head.js")      # her header on every page
_LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "luna-logo.png")   # from the station app's emblem


def register():
    from web import livefeed

    livefeed.add_page(NAME, "chat", handle, max_body=MAX_BODY, request=True)


def url():
    from web import livefeed

    return f"{livefeed.url()}/{NAME}/"


WINDOW = (900, 980)   # the --web window, in pixels
WINDOWS = {"/portrait": "open or close the portrait window", "/pose": "pose studio, in a window of its own",
           "/monitor": "the live monitor, in a window of its own"}


def open_window():
    """The chat page in a window of its own with no address bar, the way
    /portrait opens hers (web/portrait_window.py; portrait.browser, when set,
    picks the browser for both). The process, or None when it went to an
    ordinary browser tab instead."""
    from web import portrait_window

    return portrait_window.open_app(url(), *WINDOW, profile="luna-chat")


def _json(code, obj):
    return code, "application/json", json.dumps(obj)


def _int(query, key, default):
    try:
        return int((query.get(key) or [default])[0])
    except (TypeError, ValueError):
        return default


def state(version=None, have=0, epoch=None, wait=WAIT, head=False):
    """What the page needs to catch up. have: how many messages it holds
    (counted from the start of the conversation); epoch: the /clear it has
    seen. Sends from a little before the end of what it has, since the open
    reply grows and a tool's line lands just above it. head: only what her
    header shows (web/head.js on the other pages), no messages."""
    import ui
    from core import interrupts
    from ui.shared import _lock

    if version is not None and wait:
        with ui.changes:
            changed = ui.changes.wait_for(lambda: ui.view.version != version, timeout=wait)
        if changed:
            time.sleep(BATCH)   # a reply streams a token at a time: send a few together

    with _lock:
        convo = list(ui.conversation)
        streaming = ui.view.streaming
        now_version, now_epoch = ui.view.version, ui.view.epoch
        status, name, mood = ui.state["status"], ui.state["agent_name"], ui.state["mood"]
        rows = _rows(ui.state)

    if head:
        from ui.conversation_pane import _voice_on

        return {"v": now_version, "status": status, "name": name, "mood": mood, "rows": rows,
                "busy": interrupts.busy(), "stoppable": _stoppable(),
                "mic": _mic(), "can_talk": bool(ui.view.on_hotkey),
                "voice_on": _voice_on()}
    total = len(convo)
    # have > total is the open reply dropped empty (ui.end_message): no reset
    reset = epoch != now_epoch or have < 0
    if reset:
        start = max(0, total - KEEP)
    else:
        start = have if streaming is None else min(have, streaming)
        start = max(0, min(start, total) - 2)
    return {"v": now_version, "e": now_epoch, "reset": reset, "from": start,
            # a third 1: a /command's answer, shown open (ui.Asked)
            "msgs": [[speaker, text, 1] if isinstance(text, ui.Asked) else [speaker, text]
                     for speaker, text in convo[start:]], "total": total,
            "streaming": streaming, "busy": interrupts.busy(), "stoppable": _stoppable(),
            "status": status, "name": name,
            "mood": mood, "rows": rows, "ask": ui.pending_approval(), "notify_asks": _notify_asks(), "retry": _retry_at(), "mic": _mic(), "voice_mode": ui.state.get("mode", ""),
            "can_talk": bool(ui.view.on_hotkey), "rate": _rateable(now_epoch, convo),
            "dictated": dict(DICTATED), "replay": replaying()}


def _retry_at():
    """Her reply's index on screen where ↻ shows (llm/retry.py), or None."""
    try:
        from llm import retry

        return retry.available()
    except Exception:
        return None


def _retry(body):
    """↻: the page says which reply; it has to still be the one a retry would
    redo, so a click on a reply that something came after does nothing."""
    import ui

    try:
        data = json.loads(body or b"{}")
        epoch, index = int(data.get("e")), int(data.get("i"))
    except (ValueError, TypeError, AttributeError):
        return _json(400, {"error": "that couldn't be read"})
    if epoch != ui.view.epoch or index != _retry_at():
        return _json(409, {"error": "that reply can't be tried again any more"})
    ui.submit_soon("/retry")
    return _json(200, {"ok": True})


def _notify_asks():
    import config

    return bool(getattr(config, "TOOLS_NOTIFY_ASKS", True))


def _rateable(epoch, convo):
    """{index: "" | "up" | "fix" | "down"} for her replies the thumbs can keep."""
    try:
        from training import dataset

        return {str(i): r for i, r in dataset.rateable(epoch, convo).items()}
    except Exception:
        return {}


def _rate(body):
    import ui
    from training import dataset
    from ui.shared import _lock

    try:
        data = json.loads(body or b"{}")
        epoch, index, up = int(data.get("e")), int(data.get("i")), data.get("up") is True
        better = str(data.get("better") or "")[:MAX_TYPED]
        note = data.get("note") is True and not up
    except (ValueError, TypeError, AttributeError):
        return _json(400, {"error": "that couldn't be read"})
    with _lock:
        shown = ui.conversation[index][1] if epoch == ui.view.epoch and 0 <= index < len(ui.conversation) else None
    try:
        if shown is None:
            raise ValueError("that reply has gone from the conversation")
        if note:            # her own model writes it from your note, in the background
            # what she wrote answers your click, so it shows open (ui.Asked), not folded like a tool log
            ex = dataset.rate_note(epoch, shown, better, done=lambda said: ui.add_message("system", ui.Asked(said)))
        else:
            ex = dataset.rate(epoch, shown, up, better)
    except ValueError as e:
        return _json(409, {"error": str(e)})
    n = dataset.counts()
    kind = ex.get("kind", "habit")
    return _json(200, {"ok": True, "rated": ex.get("mark", "up" if up else "down"), "kind": kind,
                       "approved": n.get(kind, {}).get("approved", 0)})


# A reply said again (the speaker button): which one, and its Stop, so a
# second click, another reply's button, Stop, HOME or a new turn ends it
_replay = {"at": None, "stop": None}
_replay_lock = threading.Lock()
REPLAY_WAIT = 2               # seconds: for her turn, while the replay just stopped lets go of it


def replaying():
    """[epoch, index] of the reply being said again, or None."""
    with _replay_lock:
        return list(_replay["at"]) if _replay["at"] else None


def _stoppable():
    """Anything the Send button turns into Stop for. Not a reply said again:
    its own speaker button stops it, and you may well type while it plays
    (sending cuts it short, as any message of yours does)."""
    from core import interrupts

    return interrupts.busy(kinds=None, but=("replay",))


def _speak(body):
    """The speaker under her reply: say it again through the PC's speakers,
    the way she said it (sentence by sentence, her voice and mood). A second
    click on the same one stops it; another one's button switches to that."""
    import ui
    from core import assistant, interrupts
    from ui.conversation_pane import _voice_on
    from ui.shared import _lock

    try:
        data = json.loads(body or b"{}")
        epoch, index = int(data.get("e")), int(data.get("i"))
    except (ValueError, TypeError, AttributeError):
        return _json(400, {"error": "that couldn't be read"})
    with _lock:
        msg = ui.conversation[index] if epoch == ui.view.epoch and 0 <= index < len(ui.conversation) else None
    if msg is None or msg[0] in ("user", "system") or msg[0].startswith("chat:") or not str(msg[1]).strip():
        return _json(409, {"error": "that reply has gone from the conversation"})

    with _replay_lock:
        playing, same = _replay["stop"], _replay["at"] == (epoch, index)
        if playing is not None:
            playing.stop(speaking=True, generating=True, listening=False)
            _replay.update(at=None, stop=None)
    if same:
        _wake()                               # the button goes back to a speaker
        return _json(200, {"ok": True, "playing": False})
    if not _voice_on():
        return _json(409, {"error": "her voice is off (tts.enabled)"})
    # Her turn, held while it plays, as any turn of hers is: a reminder, a
    # stream-chat reply or a job waits for it rather than talking over it,
    # and a message of yours cuts it short (respond() stops whoever holds
    # it). A moment's wait covers the replay just stopped above letting go.
    if not assistant._turn.acquire(timeout=REPLAY_WAIT):
        return _json(409, {"error": "she's in the middle of something - try again once she's done"})

    stop = interrupts.open("replay")
    assistant._hold(stop)
    with _replay_lock:
        _replay.update(at=(epoch, index), stop=stop)
    try:
        threading.Thread(target=_say_again, args=(msg[1], stop), daemon=True, name="replay").start()
    except Exception:
        assistant._hold(None)
        assistant._turn.release()
        raise
    _wake()                                   # this one's button turns to stop
    return _json(200, {"ok": True, "playing": True})


def _player(stop):
    """Her voice for a replay. No barge-in: talking over a replay isn't
    talking over her."""
    from voice import speech

    return speech.Player(barge_in=False, stop=stop)


def _say_again(words, stop):
    """Runs holding her turn (taken in _speak), and always lets go of it at
    the end, whatever fails on the way: an import failing outside the try
    left her turn held for good, and every reply after it waited forever."""
    from core import assistant, interrupts, logbook

    try:
        from llm.streaming import _Narrator

        with interrupts.using(stop):
            player = _player(stop)
            narrator = _Narrator(on_sentence=player.say)    # the same sentences a live reply is cut into
            narrator.feed(words)
            narrator.finish()
            player.wait()
    except Exception:
        logbook.exception("chat", "saying a reply again failed")
    finally:
        with _replay_lock:
            if _replay["stop"] is stop:
                _replay.update(at=None, stop=None)
        assistant._hold(None)
        assistant._turn.release()
        _wake()


def _wake():
    """Wake the pages' long poll: something they show changed."""
    from ui.shared import _refresh

    _refresh()


def _mic():
    """The mic open for you (voice/ptt.py), for the mic button. Read only if
    push to talk is loaded: importing it would load the audio stack."""
    import sys

    ptt = sys.modules.get("voice.ptt")
    try:
        return bool(ptt and ptt.listening())
    except Exception:
        return False


def stop():
    """The Stop button: what ai-voice-ctl's stop does (voice/ptt.py stop):
    she goes quiet, stops thinking, and anything physical stops with her.
    Without push to talk loaded, the same by hand."""
    import sys

    ptt = sys.modules.get("voice.ptt")
    if ptt is not None:
        ptt.stop()
        return
    import ui
    from core import interrupts

    ui.set_status("Stopped")
    interrupts.home()
    try:
        import plugins

        plugins.panic()
    except Exception:
        pass


# The chat page's mic (dictate): the last words heard. id is new for each
# dictation and each run of Luna (a page left open across a restart must
# not wait for the count to pass its old one); page is the page that asked,
# so a second chat window doesn't get the words too. text "": nothing
# heard; None: cancelled.
_BOOT = secrets.token_hex(3)
DICTATED = {"id": f"{_BOOT}-0", "page": "", "text": None}
_dictating = threading.Lock()     # a double click: one check-and-open at a time
_count = itertools.count(1)


def dictate(page=""):
    """The mic button: record and transcribe on the desktop mic, then the
    words go into the page's text box (state()'s "dictated") to fix before
    sending. HOME, the tray and the terminal still send at once. While a
    turn of yours is running, a click is HOME (manual mode: "done"; else
    stop), and in hands-free mode it switches hands-free, as before: that
    mode is a conversation, not dictation. While she answers something
    you typed, the click dictates (her voice goes quiet so the mic doesn't
    hear her; her reply still finishes on screen), as typing would. Returns
    an error, or None."""
    import sys

    import ui
    from core import interrupts

    ptt = sys.modules.get("voice.ptt")
    if ptt is None or not ui.view.on_hotkey:
        return "push to talk isn't set up in this Luna"
    mode = ptt.mode()
    with _dictating:
        if mode == "open" or interrupts.busy(kinds=("voice",)):
            return talk()
        # she goes quiet first, or the mic records her instead of you (as ptt does)
        interrupts.stop_all(generating=False, listening=False)
        stop = interrupts.open("voice")       # opened at the click: a second click finds it
    page = str(page or "")[:40]

    def run():
        text = None
        try:
            from core import assistant

            with interrupts.using(stop):
                text = assistant.dictation(mode)
        finally:
            interrupts.close(stop)            # however it ended: an open one reads as "busy" for good
            with ui.changes:
                DICTATED.update(id=f"{_BOOT}-{next(_count)}", page=page, text=text)
            ui.set_status("Idle")             # wakes the pages' long poll with the words

    threading.Thread(target=run, daemon=True, name="dictation").start()
    return None


def talk():
    """HOME from the page: what HOME does (start talking, done, or stop her),
    run on her main loop like a key. Returns an error, or None."""
    import ui

    hotkey = ui.view.on_hotkey
    if not hotkey:
        return "push to talk isn't set up in this Luna"
    loop = ui.view.loop
    if loop is not None:
        try:
            loop.call_soon_threadsafe(hotkey)
            return None
        except RuntimeError:
            pass
    hotkey()
    return None


def _rows(st):
    """The terminal's status panel (ui/conversation_pane.py), for the menu."""
    from ui.conversation_pane import _voice_on

    tts = f"{st['voice']} - {st['voice_server']}" + ("" if _voice_on() else " · voice off")
    return [["Status", st["status"]], ["Mood", st["mood"] or "off"], ["Voice", st["mode"]],
            ["Memory", st["memory"]], ["TTS", tts], ["Model", st["model"]]]


# The tray icon (app/tray.py): when it last asked, so closing her window can
# leave her running there instead of quitting (ui/headless.py)
TRAY = {"seen": 0.0}
TRAY_FRESH = 10          # seconds: a tray that asked this recently is there


def tray_up():
    return time.monotonic() - TRAY["seen"] < TRAY_FRESH


def _tray(body):
    """What the tray's menu does that the page has no button for."""
    try:
        action = str(json.loads(body or b"{}").get("action") or "")
    except (ValueError, AttributeError):
        return _json(400, {"error": "that couldn't be read"})
    if action == "voice":
        from ui.conversation_pane import _voice_on
        from web import settings_web

        ok, message, _entry = settings_web.change("tts.enabled", not _voice_on())
        return _json(200 if ok else 400, {"ok": ok, "message": message, "voice_on": _voice_on()})
    if action == "chat":
        open_window()
        return _json(200, {"ok": True})
    command = {"portrait": "/portrait", "settings": "/settings", "quit": "/quit"}.get(action)
    if not command:
        return _json(400, {"error": "unknown action"})
    error = say(command)
    return _json(503, {"error": error}) if error else _json(200, {"ok": True})


def say(text, attachment=None):
    """Hand it to Luna the way Enter does. Returns an error, or None."""
    import ui

    if not ui.view.on_submit:
        return "Luna isn't taking messages yet"
    ui.submit_soon(text, attachment)
    return None


def _say(body, headers):
    from web import station

    kind = (headers.get("Content-Type") or "").lower() if headers else ""
    attachment = None
    if kind.startswith("multipart/form-data"):
        from core import attachments

        text, files = station._form(headers.get("Content-Type"), body)
        if files is None:
            return _json(400, {"error": "that form couldn't be read", "code": "bad_form"})
        if len(files) > attachments.MAX_FILES:
            return _json(413, {"error": "one file a message", "code": "too_many"})
        if files:
            try:
                attachment = attachments.prepare(*files[0])
            except attachments.Refused as e:
                return _json(e.status, {"error": e.reason, "code": e.code})
    elif kind.startswith("application/json"):
        try:
            text = str(json.loads(body or b"{}").get("text") or "")
        except (ValueError, AttributeError):
            return _json(400, {"error": "that couldn't be read", "code": "bad_json"})
    else:
        # a plain form from some other page can't get past the Origin check,
        # but there's no reason to take one either
        return _json(415, {"error": "send JSON or a form with a file"})
    text = text.strip()
    if not text and attachment is not None:
        text = "What do you think of this?" if attachment.kind == "image" else "Have a look at this."
    if not text:
        return _json(400, {"error": "nothing to say"})
    if len(text) > MAX_TYPED:
        return _json(413, {"error": f"keep it under {MAX_TYPED} characters"})
    error = say(text, attachment)
    if error:
        return _json(503, {"error": error})
    return _json(200, {"ok": True})


def _answer(body):
    import ui

    try:
        data = json.loads(body or b"{}")
        which, answer = int(data.get("id")), str(data.get("answer"))
    except (ValueError, TypeError, AttributeError):
        return _json(400, {"error": "that couldn't be read"})
    value = {"yes": True, "no": False, "all": "all"}.get(answer)
    if value is None:
        return _json(400, {"error": "answer yes, no or all"})
    if not ui.answer_approval(value, which=which):
        return _json(409, {"error": "that question has already closed"})
    return _json(200, {"ok": True})


def _nav():
    """[label, address, command, title] for every page, in the launcher's
    order (ui/launcher.py), so the terminal's Tab pane and her menu agree.
    Chat first; a command only where the page opens a window of its own."""
    from ui import launcher

    out = [["Chat", "/chat/", "", ""]]
    for label, _what, command, address in launcher.entries():
        if command == "/chat":
            continue
        if command.startswith("/portrait") and command != "/portrait":
            continue        # the OBS address is for OBS, not a link
        path = urllib.parse.urlsplit(address).path if address else ""
        query = urllib.parse.urlsplit(address).query if address else ""
        # these open windows of their own, so the page sends the command
        out.append([label, path + (f"?{query}" if query else ""), command if command in WINDOWS else "",
                    WINDOWS.get(command, "")])
    return out


def page():
    from core import attachments

    with open(_HTML, encoding="utf-8") as f:
        html = f.read()
    try:
        files = attachments.info()
    except Exception:
        files = {}
    boot = {"files": files, "max": MAX_TYPED}
    # </ inside a script would end it early
    return html.replace("__BOOT__", json.dumps(boot).replace("</", "<\\/"))


def handle(method, sub, body, request=None):
    request = request or {}
    query = urllib.parse.parse_qs(request.get("query") or "")
    headers = request.get("headers")
    if method == "GET" and sub in ("", "/"):
        return 200, "text/html; charset=utf-8", page()
    if method == "GET" and sub == "/head.js":
        with open(_HEAD, encoding="utf-8") as f:
            js = f.read().replace("__NAV__", json.dumps(_nav()).replace("</", "<\\/"))
        return 200, "text/javascript; charset=utf-8", js
    if method == "GET" and sub == "/logo.png":
        with open(_LOGO, "rb") as f:
            return 200, "image/png", f.read()
    if method == "GET" and sub == "/state":
        if query.get("tray"):
            TRAY["seen"] = time.monotonic()
        version = _int(query, "v", None)
        return _json(200, state(version, _int(query, "n", 0), _int(query, "e", None),
                                head=bool(query.get("head"))))
    if method == "POST" and sub == "/say":
        return _say(body, headers)
    if method == "POST" and sub == "/dictate":
        try:
            asker = (json.loads(body or b"{}") or {}).get("page", "")
        except (ValueError, AttributeError):
            asker = ""
        error = dictate(asker)
        return _json(503, {"error": error}) if error else _json(200, {"ok": True})
    if method == "POST" and sub == "/talk":
        error = talk()
        return _json(503, {"error": error}) if error else _json(200, {"ok": True})
    if method == "GET" and sub == "/spell":
        from core import spelling

        return _json(200, spelling.check_many(query.get("w") or []))
    if method == "POST" and sub == "/speak":
        return _speak(body)
    if method == "POST" and sub == "/stop":
        stop()
        return _json(200, {"ok": True})
    if method == "POST" and sub == "/answer":
        return _answer(body)
    if method == "POST" and sub == "/retry":
        return _retry(body)
    if method == "POST" and sub == "/rate":
        return _rate(body)
    if method == "POST" and sub == "/tray":
        return _tray(body)
    return 404, "text/plain; charset=utf-8", "not here"
