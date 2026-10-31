"""The live monitor: what she's doing, as she does it.

    http://127.0.0.1:8792      (link in the thought viewer, or /monitor)

The thought log is the record, written when a turn ends. This is the
same turn while it happens: which stage it's at, her thinking and her
reply arriving token by token - coloured by how sure she was, on
llama-server - each tool call with its arguments, her mood, and how
full the context is.

It is served by the assistant itself rather than the viewer, because
this is the process the events happen in; a second process would need
a pipe between the two for no gain. Nothing is stored. With no page
open, emit() returns at its first line.

Localhost only, and stricter than that: a request whose Host or Origin
isn't this server is refused. The stream carries what you say and what
she thinks, and a page on any other site must not be able to read it -
including through a DNS name pointed at 127.0.0.1.

This file is the server and the event stream (emit, the request handler,
the page registry). It re-exports the rest, so `livefeed.X` still works:

    web/portrait_config.py   what the portrait page is told when it loads
    web/gesture_files.py     reading gesture and prop files for the pages
    web/gaze.py              where her eyes follow on screen
"""
import importlib.util
import json
import os
import queue
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import config
from web import holofan
from core import logbook
from web.gaze import _gaze_loop
from web.gesture_files import gesture_file, prop_entry, props_list
from web.portrait_config import portrait_config, portrait_models
from web.gesture_files import (  # noqa: F401  re-exported: livefeed.X keeps working
    _BONE,
    _GNAME,
    _IDLE_BANDS,
    _WORD,
    _ZONES,
    _num,
    _text,
    _words,
)
from web.portrait_config import (  # noqa: F401  re-exported: livefeed.X keeps working
    _gesture_mode,
    _model_sidecar,
    _mood_list,
    gesture_mode_changed,
    lights_changed,
    lights_config,
    portrait_clips,
    portrait_url,
)
from web.gaze import (  # noqa: F401  re-exported: livefeed.X keeps working
    _GAZE_REACH,
    _own_pids,
    gaze_target,
)

_subs = set()
_lock = threading.Lock()

# The last of each of these, replayed to a page that opens mid-session,
# so it shows where things stand instead of a blank screen until the
# next turn.
_SNAPSHOT_KINDS = ("stage", "mood", "context", "server", "turn", "gaze", "holo", "prop")
_snapshot = {}


def port():
    return int(getattr(config, "MONITOR_PORT", 8792))


def url():
    return f"http://127.0.0.1:{port()}"


def watching():
    return bool(_subs)


def emit(kind, **data):
    """One event to every open page. Safe from any thread; never raises."""
    event = dict(data, t=kind, at=round(time.time(), 3))

    if kind in _SNAPSHOT_KINDS:
        # one prop event kept per prop (her mug, her book), so a page that
        # connects later puts each one where it should be
        _snapshot[f"prop:{data.get('name')}" if kind == "prop" else kind] = event

        if kind == "turn":
            # A new turn makes the old one's tail meaningless.
            _snapshot.pop("done", None)

    if not _subs:
        return

    with _lock:
        for q in list(_subs):
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # a page that stopped reading loses events, not the turn


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _allowed(self):
        here = {f"127.0.0.1:{port()}", f"localhost:{port()}"}
        origin = self.headers.get("Origin")

        if self.headers.get("Host") not in here:
            return False

        return origin is None or origin.split("://", 1)[-1] in here

    def do_GET(self):
        if not self._allowed():
            self.send_response(403)
            self.end_headers()
            return

        if self.path == "/":
            body = with_switcher(PAGE, "live").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/events":
            self._stream()
        elif self._page("GET"):
            pass
        elif self._mounted("GET"):
            pass
        elif self.path.split("?")[0] == "/portrait":
            self.send_response(301)
            self.send_header("Location", "/portrait/" + self.path[len("/portrait"):])
            self.end_headers()
        elif self.path.split("?")[0] == "/portrait/fan/status":
            self._json(200, holofan.status())
        elif self.path.startswith("/portrait/"):
            self._portrait(self.path.split("?", 1)[0][len("/portrait/"):])
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self._allowed():
            self.send_response(403)
            self.end_headers()
        elif self.path == "/portrait/touch":
            self._touch()
        elif self.path == "/portrait/outfit":
            self._outfit()
        elif self.path == "/portrait/gestures/save":
            self._save_gesture()
        elif self.path == "/portrait/props/save":
            self._save_prop()
        elif self.path in ("/portrait/cards/save", "/portrait/cards/import", "/portrait/cards/load", "/portrait/cards/delete"):
            self._card(self.path.rsplit("/", 1)[1])
        elif self.path == "/portrait/fan/frame":
            self._fan_frame()
        elif not self._page("POST") and not self._mounted("POST"):
            self.send_response(404)
            self.end_headers()

    def _page(self, method):
        """A plugin's page (add_page): /<name>/... handed to its handler.
        Returns False when the path isn't one of theirs."""
        path = self.path.split("?", 1)[0]
        for name, (_label, handler, _visible) in list(PAGES.items()):
            prefix = "/" + name
            if path == prefix:
                self.send_response(301)
                self.send_header("Location", prefix + "/")
                self.end_headers()
                return True
            if not path.startswith(prefix + "/"):
                continue
            body = b""
            if method == "POST":
                try:
                    body = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 65536))
                except (ValueError, OSError):
                    body = b""
            try:
                code, kind, out = handler(method, path[len(prefix):], body)
            except Exception as e:
                logbook.warn("monitor", "the %s page failed: %s", name, e)
                code, kind, out = 500, "text/plain; charset=utf-8", f"the {name} page failed: {e}"
            if isinstance(out, str):
                out = (with_switcher(out, name) if kind.startswith("text/html") else out).encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(out)))
            self.send_header("Cache-Control", "max-age=3600" if kind.startswith("image/") else "no-store")
            # no other site may frame these pages and trick clicks through them
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
            self.end_headers()
            self.wfile.write(out)
            return True
        return False

    def _touch(self):
        """The portrait was clicked (touch.js): she may answer it out loud
        (life/touches.py). JSON only - a plain form on some other page can't
        send that - and the zone must be one she knows."""
        kind = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 1024)
            zone = str(json.loads(self.rfile.read(length) or b"{}").get("zone", "")) if kind == "application/json" else ""
        except (ValueError, AttributeError):
            zone = ""
        if not zone:
            self.send_response(400)
            self.end_headers()
            return
        try:
            from life import touches

            touches.note(zone)
        except Exception:
            pass
        self.send_response(204)
        self.end_headers()

    def _outfit(self):
        """What she's wearing now (outfits.js reports after every change), for
        /outfit and her situation line (life/clothes.py). JSON only."""
        kind = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 2048)
            data = json.loads(self.rfile.read(length) or b"{}") if kind == "application/json" else {}
        except (ValueError, AttributeError):
            data = {}
        ok = False
        try:
            from life import clothes

            ok = isinstance(data, dict) and clothes.note(data.get("wearing"), data.get("off") or [],
                                                         data.get("pieces"))
        except Exception:
            ok = False
        self.send_response(204 if ok else 400)
        self.end_headers()

    def _save_gesture(self):
        """The pose studio's Save (studio.js): JSON in - never code - checked
        field by field, written as portrait/gestures/<name>.js. A gesture that's
        already there is only replaced with "overwrite": true, and the old file
        goes to portrait/gestures/backup/ first."""
        kind = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 512 * 1024)
            data = json.loads(self.rfile.read(length) or b"{}") if kind == "application/json" else None
            name, text = gesture_file(data)
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            return self._json(400, {"ok": False, "error": str(e)[:200]})
        gdir = os.path.join(config.BASE_DIR, "portrait", "gestures")
        path = os.path.join(gdir, name + ".js")
        if os.path.exists(path):
            if not data.get("overwrite"):
                return self._json(409, {"ok": False, "error": f"{name} already exists", "exists": True})
            bdir = os.path.join(gdir, "backup")
            os.makedirs(bdir, exist_ok=True)
            import shutil
            shutil.copy2(path, os.path.join(bdir, f"{name}.{time.strftime('%Y%m%d-%H%M%S')}.js"))
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(path + ".tmp", path)
        logbook.info("portrait", "pose studio saved gestures/%s.js", name)
        return self._json(200, {"ok": True, "name": name})

    def _card(self, what):
        """The pose studio's Cards tab (web/cards.py): save one from what she
        looks like now, take in one dropped on the studio, or put one on (the
        page reloads after, from the settings the card wrote)."""
        from web import cards
        import base64

        kind = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        limit = cards.MAX_CARD if what == "import" else 16 * 1024 * 1024
        if length <= 0 or length > limit:
            return self._json(413 if length > limit else 400, {"ok": False, "error": "too big, or empty"})
        body = self.rfile.read(length)
        try:
            if what == "import":
                if kind != "image/png":
                    raise ValueError("a card is a PNG")
                from urllib.parse import unquote
                name = unquote(self.headers.get("X-Card-Name") or "") or None    # sent encoded: a header can't carry every letter
                return self._json(200, {"ok": True, "card": cards.add(body, name)})
            if kind != "application/json":
                raise ValueError("JSON only")
            data = json.loads(body or b"{}")
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            if what == "save":
                image = str(data.get("image") or "")
                if not image.startswith("data:image/png;base64,"):
                    raise ValueError("the picture has to be a PNG")
                out = cards.pack(data.get("name"), base64.b64decode(image.split(",", 1)[1]),
                                 data.get("carry") or {}, data.get("gestures") or [],
                                 model=str(data.get("model") or "") or None)
                logbook.info("portrait", "card saved: %s (%s)", out["name"], ", ".join(out["carries"]))
                return self._json(200, dict(out, ok=True))
            if what == "delete":
                cards.remove(data.get("name"))
                logbook.info("portrait", "card deleted: %s", data.get("name"))
                return self._json(200, {"ok": True})
            out = cards.apply(data.get("name"))
            logbook.info("portrait", "card put on: %s", data.get("name"))
            emit("reload", model=out.get("model") or "")
            return self._json(200, dict(out, ok=True))
        except (ValueError, TypeError, OSError) as e:
            return self._json(400, {"ok": False, "error": str(e)[:200]})

    def _save_prop(self):
        """The pose studio's prop tab: where a prop sits in her hand, kept in
        portrait/props/props.json (JSON in, checked, numbers out)."""
        kind = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 4096)
            data = json.loads(self.rfile.read(length) or b"{}") if kind == "application/json" else None
            name, entry = prop_entry(data)
        except (ValueError, TypeError, AttributeError) as e:
            return self._json(400, {"ok": False, "error": str(e)[:200]})
        path = os.path.join(config.BASE_DIR, "portrait", "props", "props.json")
        try:
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            if not isinstance(saved, dict):
                saved = {}
        except (OSError, ValueError):
            saved = {}
        saved[name] = entry
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(saved, f, indent=2)
            f.write("\n")
        os.replace(path + ".tmp", path)
        logbook.info("portrait", "pose studio placed the %s prop", name)
        return self._json(200, {"ok": True, "name": name, **entry})

    def _fan_frame(self):
        """A frame for the hologram fan, already in its layout (fan.js)."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"ok": False, "error": "no length"})
        if not holofan.enabled():
            self.rfile.read(min(n, holofan.PACKET))
            return self._json(409, {"ok": False, "error": "portrait.fan.cast is off"})
        if n <= 0 or n > holofan.MAX_JPEG:
            self.rfile.read(min(max(n, 0), 1 << 20))
            return self._json(413, {"ok": False, "error": f"a frame is at most {holofan.MAX_JPEG} bytes"})
        holofan.start()
        ok, active = holofan.push(self.rfile.read(n), str(self.headers.get("X-Fan-Sender", ""))[:40])
        # active False: another page has the fan, or none is connected - this one can rest
        self._json(200 if ok else 400, {"ok": ok, "active": active})

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _mounted(self, method):
        """The thought viewer and the memory manager, served from here at
        /thoughts/ and /memory/ - their own handler code, run against this
        request. Returns False when the path isn't one of theirs."""
        for name in MOUNTS:
            prefix = "/" + name
            if self.path == prefix or self.path.startswith(prefix + "?"):
                self.send_response(301)
                self.send_header("Location", prefix + "/" + self.path[len(prefix):])
                self.end_headers()
                return True
            if not self.path.startswith(prefix + "/"):
                continue
            try:
                cls = _mount_class(name)
            except Exception as e:
                logbook.warn("monitor", "couldn't load %s: %s", name, e)
                body = f"couldn't load the {name} page: {e}".encode()
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return True
            original_path, original_cls = self.path, self.__class__
            self._checked_by_monitor = True   # Host and Origin, just above
            self.path = self.path[len(prefix):] or "/"
            self.__class__ = cls
            try:
                (self.do_POST if method == "POST" else self.do_GET)()
            finally:
                self.path, self.__class__ = original_path, original_cls
            return True
        return False

    _TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
              ".json": "application/json", ".vrm": "model/gltf-binary", ".glb": "model/gltf-binary",
              ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
              ".moc3": "application/octet-stream", ".vrma": "model/gltf-binary",
              ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav", ".m4a": "audio/mp4"}
    _SOUNDS = (".mp3", ".ogg", ".wav", ".m4a")

    def _portrait(self, rel):
        """The portrait page and its files - and nothing outside portrait/,
        whatever the path says. The page and its libraries live in
        portrait/viewer/ (vendor/ inside it); models/ and animations/ beside
        it are served at the same level, so the page finds them as models/...,
        gestures/..."""
        from urllib.parse import unquote
        rel = unquote(rel)   # a model folder with spaces or non-latin letters in its name
        if rel == "config.json":
            # ?model=... previews another model without switching to it
            from urllib.parse import parse_qs, urlsplit
            want = (parse_qs(urlsplit(self.path).query).get("model") or [""])[0]
            return self._body(json.dumps(portrait_config(want if want in portrait_models() else None)).encode(),
                              "application/json")

        if rel == "gestures/index.json":
            # every gesture file the page should load (portrait/gestures/)
            gdir = os.path.join(config.BASE_DIR, "portrait", "gestures")
            try:
                names = sorted(f[:-3] for f in os.listdir(gdir) if f.endswith(".js") and not f.startswith("_"))
            except OSError:
                names = []
            return self._body(json.dumps(names).encode(), "application/json")

        if rel == "props/index.json":
            return self._body(json.dumps(props_list()).encode(), "application/json")

        if rel == "props/props.json" and not os.path.isfile(
                os.path.join(config.BASE_DIR, "portrait", "props", "props.json")):
            return self._body(b"{}", "application/json")     # nothing placed yet: the defaults

        if rel == "sounds/index.json":
            # portrait/sounds/: {name: [files]} - a file by its name without the
            # extension (touch-self.mp3 -> "touch-self"), a folder by its name
            # (gasp/ -> every clip in it, one picked at random), and numbered files
            # by their shared name (moan01.mp3, moan02.mp3 -> "moan")
            sdir = os.path.join(config.BASE_DIR, "portrait", "sounds")
            found = {}
            for top, _dirs, files in os.walk(sdir):
                for f in sorted(files):
                    if os.path.splitext(f)[1].lower() not in self._SOUNDS:
                        continue
                    path = os.path.relpath(os.path.join(top, f), os.path.join(config.BASE_DIR, "portrait"))
                    url = "/".join(path.split(os.sep))
                    stem = os.path.splitext(f)[0].lower()
                    found.setdefault(stem, []).append(url)
                    base = re.sub(r"[_\- ]?\d+$", "", stem)      # moan-sexy01, moan-sexy02 -> also "moan-sexy"
                    if base and base != stem:
                        found.setdefault(base, []).append(url)
                    if top != sdir:
                        found.setdefault(os.path.relpath(top, sdir).replace(os.sep, "/").lower(), []).append(url)
            return self._body(json.dumps(found).encode(), "application/json")

        if rel == "cards/index.json":
            from web import cards
            return self._body(json.dumps(cards.cards()).encode(), "application/json")
        if rel == "cards/yours.json":
            from web import cards
            return self._body(json.dumps(cards.own_gestures()).encode(), "application/json")
        if rel.startswith("cards/thumb/") and rel.endswith(".png"):
            from web import cards
            try:
                return self._body(cards.picture(rel[12:-4]), "image/png")
            except (ValueError, OSError):
                self.send_response(404)
                self.end_headers()
                return

        if rel == "models.json":
            return self._body(json.dumps(portrait_models()).encode(), "application/json")

        root = os.path.realpath(os.path.join(config.BASE_DIR, "portrait"))
        full = os.path.realpath(os.path.join(root, "viewer", rel or "index.html"))
        if not os.path.isfile(full):
            full = os.path.realpath(os.path.join(root, rel or "index.html"))
        ext = os.path.splitext(full)[1].lower()

        if not full.startswith(root + os.sep) or ext not in self._TYPES or not os.path.isfile(full):
            self.send_response(404)
            self.end_headers()
            return

        with open(full, "rb") as f:
            self._body(f.read(), self._TYPES[ext], cache=ext in (".vrm", ".glb", ".png", ".jpg", ".webp", ".moc3")
                       and "vendor" not in full)  # .vrma not cached: you're likely re-recording it

    def _body(self, body, kind, cache=False):
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=60" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        q = queue.Queue(maxsize=5000)

        try:
            for event in list(_snapshot.values()):
                self._send(event)

            with _lock:
                _subs.add(q)

            quiet = 0
            while True:
                try:
                    self._send(q.get(timeout=1))
                    quiet = 0
                except queue.Empty:
                    if self._gone():
                        break
                    quiet += 1
                    if quiet >= 15:
                        quiet = 0
                        self.wfile.write(b": ping\n\n")  # keeps proxies and the tab awake
                        self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _lock:
                _subs.discard(q)

    def _gone(self):
        """The page closed its end (a closed tab or window): known within a
        second, instead of at the next write, so watching() is up to date."""
        import select
        import socket

        try:
            ready, _, _ = select.select([self.connection], [], [], 0)
        except (OSError, ValueError):                # closed under us
            return True
        if not ready:
            return False
        try:
            return self.connection.recv(1, socket.MSG_PEEK) == b""
        except ValueError:                           # a socket that can't peek (TLS): the next write tells
            return False
        except OSError:
            return True

    def _send(self, event):
        self.wfile.write(b"data: " + json.dumps(event, ensure_ascii=False).encode() + b"\n\n")
        self.wfile.flush()


# ---------------------------------------------------------------------------
# The other pages, under one roof
#
# The thought viewer and the memory manager stay their own programs in
# their own folders - each still runs on its own with its own start.sh.
# When this server is up (Luna running, or `python -m web.livefeed`), it
# serves them too, so one port and one process covers the monitor, the
# portrait, her thoughts and her memory, with a small switcher on each.
# ---------------------------------------------------------------------------
# Pages a plugin serves while it's on (the chess board): name -> (label,
# handler, visible). handler(method, path, body) -> (status, content type,
# body); path is what follows /<name>. visible() decides whether the
# switcher links it.
PAGES = {}


def add_page(name, label, handler, visible=lambda: True):
    PAGES[name] = (label, handler, visible)


MOUNTS = {"thoughts": ("thought-viewer", "viewer.py", "her thoughts"),
          "memory": ("memory-manager", "manager.py", "her memory")}
_mount_classes = {}


def _mount_class(name):
    """The app's own request handler, with the page switcher slipped into
    every HTML page it sends."""
    if name not in _mount_classes:
        folder, file, _label = MOUNTS[name]
        spec = importlib.util.spec_from_file_location(f"luna_{name}_page",
                                                      os.path.join(config.BASE_DIR, folder, file))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        base = mod.Handler

        def _send(self, code, body, content_type="application/json", *rest):
            if content_type.startswith("text/html") and isinstance(body, str):
                body = with_switcher(body, name)
            return base._send(self, code, body, content_type, *rest)

        _mount_classes[name] = type(f"Mounted_{name}", (base,), {"_send": _send})
    return _mount_classes[name]


def with_switcher(html, here):
    """A small pill bottom-right linking the pages this server serves."""
    links = [("", "live"), ("portrait/", "portrait"), ("thoughts/", "thoughts"), ("memory/", "memory")]
    for name, (label, _handler, visible) in list(PAGES.items()):
        try:
            if visible():
                links.append((name + "/", label))
        except Exception:
            pass
    items = "".join(
        f'<a href="/{href}"{" class=on" if (href.rstrip("/") or "live") == here else ""}>{label}</a>'
        for href, label in links)
    nav = ("<style>#luna-nav{position:fixed;right:12px;bottom:10px;z-index:9999;display:flex;gap:2px;"
           "background:#120d1ccc;border:1px solid #3a2d55;border-radius:999px;padding:3px;"
           "font:12px system-ui,sans-serif;backdrop-filter:blur(6px)}"
           "#luna-nav a{color:#a99cc8;text-decoration:none;padding:3px 10px;border-radius:999px}"
           "#luna-nav a:hover{color:#e6dcff;background:#2a2040}"
           "#luna-nav a.on{color:#14081c;background:#c49dff}"
           f"@media print{{#luna-nav{{display:none}}}}</style><nav id=luna-nav>{items}</nav>")
    i = html.find("<body")
    if i < 0:
        return html
    j = html.find(">", i)
    return html[:j + 1] + nav + html[j + 1:]


def start():
    """Serve the page, if monitor.enabled. A port already in use is a
    line in the log, not a failed startup."""
    if not getattr(config, "MONITOR_ENABLED", True):
        return False

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port()), _Handler)
    except OSError as e:
        logbook.warn("monitor", "live monitor not started on :%s: %s", port(), e)
        return False

    server.daemon_threads = True

    try:
        from web import settings_web

        settings_web.register()          # /settings/: every setting, in a browser
    except Exception as e:
        logbook.warn("monitor", "settings page unavailable: %s", e)

    try:
        from web import help_web

        help_web.register()              # /help/: every command and key
    except Exception as e:
        logbook.warn("monitor", "help page unavailable: %s", e)

    try:
        from web import dataset_web

        dataset_web.register()           # /examples/: examples for her patches
    except Exception as e:
        logbook.warn("monitor", "examples page unavailable: %s", e)

    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=_gaze_loop, daemon=True, name="portrait-gaze").start()
    holofan.start()          # only does anything with portrait.fan.cast on
    logbook.info("monitor", "live monitor on %s", url())

    return True


def _web_page(name):
    """A page's HTML from web/ (kept out of the code so each side reads as what it is)."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name), encoding="utf-8") as f:
        return f.read()


PAGE = _web_page("live.html")   # the page itself: web/live.html


def main():
    """`python -m web.livefeed [--open thoughts|memory|portrait]`: the pages
    without Luna. If the server's already up (Luna's running), this just
    opens the page in your browser."""
    import socket
    import sys
    import webbrowser

    page = ""
    if "--open" in sys.argv[1:-1]:
        page = sys.argv[sys.argv.index("--open") + 1].strip("/")
    target = url() + ("/" + page + "/" if page and page != "live" else "/")
    with socket.socket() as probe:
        probe.settimeout(0.3)
        running = probe.connect_ex(("127.0.0.1", port())) == 0
    if running:
        webbrowser.open(target)
        print(target)
        return
    server = ThreadingHTTPServer(("127.0.0.1", port()), _Handler)
    server.daemon_threads = True
    print(f"{url()}  - live, /portrait/, /thoughts/, /memory/  (Ctrl+C stops it)")
    threading.Timer(0.4, lambda: webbrowser.open(target)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
