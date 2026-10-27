"""The examples page: look through what her patches will learn from.

    http://127.0.0.1:8792/examples/      (or /examples in the terminal)

Every example kept with /good or /fix (and, later, the gesture-tagged
ones), newest first: your message, her reply, your version if you fixed
it. Approve, drop (kept, but never trained on), edit the reply, or delete
it for good. The prompt she was answering is there too, folded away.

Served by livefeed, so localhost only and Host/Origin checked; a change
also needs this run's key, which only this page carries (as on the
settings page).
"""
import json
import os
import secrets

from core import logbook

NAME = "examples"
KEY = secrets.token_urlsafe(24)       # this run's; the page re-reads it after a restart


def _row(r):
    msgs = r.get("messages") or []
    said = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
    return {"id": r.get("id"), "when": r.get("when"), "kind": r.get("kind"), "source": r.get("source"),
            "model": r.get("model"), "approved": r.get("approved"), "said": said, "reply": r.get("reply"),
            "original": r.get("original"),
            "context": [m for m in msgs if m.get("role") != "system"][:-1],
            "system": next((m["content"] for m in msgs if m.get("role") == "system"), "")}


def handle(method, sub, body):
    """(status, content type, body) for /examples/<sub>."""
    from training import dataset

    sub = sub or "/"

    if method == "GET" and sub == "/":
        return 200, "text/html; charset=utf-8", PAGE.replace("__KEY__", KEY)

    if method == "GET" and sub == "/api":
        rows = [_row(r) for r in reversed(dataset.examples())]
        return 200, "application/json", json.dumps({"examples": rows, "counts": dataset.counts()})

    if method == "POST" and sub == "/api":
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = None
        if not isinstance(data, dict) or not secrets.compare_digest(str(data.get("key", "")), KEY):
            return 403, "application/json", json.dumps({"ok": False, "message": "this page is out of date - reload it"})

        action, ex = data.get("action"), str(data.get("example", ""))
        try:
            if action == "approve":
                ok = dataset.update(ex, approved=True)
            elif action == "drop":
                ok = dataset.update(ex, approved=False)
            elif action == "edit":
                ok = dataset.update(ex, reply=str(data.get("reply", "")))
            elif action == "kind":
                ok = dataset.update(ex, kind=str(data.get("kind", "")))
            elif action == "delete":
                ok = dataset.remove(ex)
            else:
                return 400, "application/json", json.dumps({"ok": False, "message": "unknown action"})
        except ValueError as e:
            return 400, "application/json", json.dumps({"ok": False, "message": str(e)})

        if ok:
            logbook.info("dataset", "web: %s %s", action, ex)
        return (200 if ok else 404), "application/json", json.dumps(
            {"ok": ok, "message": "done" if ok else "no such example", "counts": dataset.counts()})

    return 404, "text/plain; charset=utf-8", "not found"


def register():
    from web import livefeed

    livefeed.add_page(NAME, "examples", lambda method, sub, body: handle(method, sub, body))


def url():
    from web import livefeed

    return livefeed.url() + "/examples/"


def _web_page(name):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name), encoding="utf-8") as f:
        return f.read()


PAGE = _web_page("dataset.html")   # the page itself: web/dataset.html
