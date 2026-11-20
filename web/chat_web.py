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
                           up to WAIT seconds for something to change (v=)
    POST /chat/say         {"text"} or a form with "text" and one "file"
    POST /chat/talk        the mic button: HOME (talk, done, or stop her)
    POST /chat/stop        stop her (and anything physical), like ai-voice-ctl stop
    POST /chat/answer      {"id", "answer": "yes" | "no" | "all"}
    POST /chat/rate        {"e", "i", "up": true|false, "better"}: the thumbs on her
                           reply at conversation index i (matched by its text), kept as an example for her
                           patches (training/dataset.py rate)
"""
import json
import os
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
WINDOWS = {"/portrait": "open or close her portrait window", "/pose": "pose studio, in a window of its own",
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
                "busy": interrupts.busy(), "mic": _mic(), "can_talk": bool(ui.view.on_hotkey),
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
            "msgs": [[speaker, text] for speaker, text in convo[start:]], "total": total,
            "streaming": streaming, "busy": interrupts.busy(), "status": status, "name": name,
            "mood": mood, "rows": rows, "ask": ui.pending_approval(), "mic": _mic(), "voice_mode": ui.state.get("mode", ""),
            "can_talk": bool(ui.view.on_hotkey), "rate": _rateable(now_epoch, convo)}


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
    except (ValueError, TypeError, AttributeError):
        return _json(400, {"error": "that couldn't be read"})
    with _lock:
        shown = ui.conversation[index][1] if epoch == ui.view.epoch and 0 <= index < len(ui.conversation) else None
    try:
        if shown is None:
            raise ValueError("that reply has gone from the conversation")
        ex = dataset.rate(epoch, shown, up, better)
    except ValueError as e:
        return _json(409, {"error": str(e)})
    n = dataset.counts()
    kind = ex.get("kind", "habit")
    return _json(200, {"ok": True, "rated": ex.get("mark", "up" if up else "down"), "kind": kind,
                       "approved": n.get(kind, {}).get("approved", 0)})


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


def talk():
    """The mic button: what HOME does (start talking, done, or stop her),
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
    command = {"portrait": "/portrait", "settings": "/settings", "quit": "/quit"}.get(action)
    if not command:
        return _json(400, {"error": "unknown action"})
    error = say(command)
    return _json(503, {"error": error}) if error else _json(200, {"ok": True})


def say(text, attachment=None):
    """Hand it to Luna the way Enter does. Returns an error, or None."""
    import ui

    if not ui.view.on_submit:
        return "she isn't taking messages yet"
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
    if method == "POST" and sub == "/talk":
        error = talk()
        return _json(503, {"error": error}) if error else _json(200, {"ok": True})
    if method == "POST" and sub == "/stop":
        stop()
        return _json(200, {"ok": True})
    if method == "POST" and sub == "/answer":
        return _answer(body)
    if method == "POST" and sub == "/rate":
        return _rate(body)
    if method == "POST" and sub == "/tray":
        return _tray(body)
    return 404, "text/plain; charset=utf-8", "not here"
