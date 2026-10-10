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
import logbook

_subs = set()
_lock = threading.Lock()

# The last of each of these, replayed to a page that opens mid-session,
# so it shows where things stand instead of a blank screen until the
# next turn.
_SNAPSHOT_KINDS = ("stage", "mood", "context", "server", "turn", "gaze", "holo")
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
        _snapshot[kind] = event

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
        elif self._mounted("GET"):
            pass
        elif self.path.split("?")[0] == "/portrait":
            self.send_response(301)
            self.send_header("Location", "/portrait/" + self.path[len("/portrait"):])
            self.end_headers()
        elif self.path.startswith("/portrait/"):
            self._portrait(self.path.split("?", 1)[0][len("/portrait/"):])
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self._allowed() or not self._mounted("POST"):
            self.send_response(403 if not self._allowed() else 404)
            self.end_headers()

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
              ".moc3": "application/octet-stream"}

    def _portrait(self, rel):
        """The portrait page and its files, from portrait/ - and nothing
        outside it, whatever the path says."""
        if rel == "config.json":
            return self._body(json.dumps(portrait_config()).encode(), "application/json")

        root = os.path.realpath(os.path.join(config.BASE_DIR, "portrait"))
        full = os.path.realpath(os.path.join(root, rel or "index.html"))
        ext = os.path.splitext(full)[1].lower()

        if not full.startswith(root + os.sep) or ext not in self._TYPES or not os.path.isfile(full):
            self.send_response(404)
            self.end_headers()
            return

        with open(full, "rb") as f:
            self._body(f.read(), self._TYPES[ext], cache=ext in (".vrm", ".glb", ".png", ".jpg", ".webp", ".moc3")
                       and "vendor" not in full)

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

            while True:
                try:
                    self._send(q.get(timeout=15))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")  # keeps proxies and the tab awake
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _lock:
                _subs.discard(q)

    def _send(self, event):
        self.wfile.write(b"data: " + json.dumps(event, ensure_ascii=False).encode() + b"\n\n")
        self.wfile.flush()


# ---------------------------------------------------------------------------
# The other pages, under one roof
#
# The thought viewer and the memory manager stay their own programs in
# their own folders - each still runs on its own with its own start.sh.
# When this server is up (Luna running, or `python livefeed.py`), it
# serves them too, so one port and one process covers the monitor, the
# portrait, her thoughts and her memory, with a small switcher on each.
# ---------------------------------------------------------------------------
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


def portrait_models():
    """Every model in portrait/models, as paths portrait.model takes:
    a folder's .model3.json (Live2D), and any .vrm / .glb (3D)."""
    root = os.path.join(config.BASE_DIR, "portrait", "models")
    found = []

    for dirpath, _dirs, files in sorted(os.walk(root)):
        if dirpath[len(root):].count(os.sep) > 2:      # not deep inside a model's own folders
            continue

        for f in sorted(files):
            if f.endswith((".model3.json", ".vrm", ".glb")):
                found.append(os.path.relpath(os.path.join(dirpath, f), os.path.dirname(root)).replace(os.sep, "/"))

    return found


def portrait_config():
    """What the portrait page needs from config.json: which model, and
    which nodes are her ears if their names don't say so. A model that
    isn't there falls back to Sigewinne; with neither, the page says so."""
    root = os.path.join(config.BASE_DIR, "portrait")
    model = str(getattr(config, "PORTRAIT_MODEL", "") or "")
    missing = ""

    if not model or not os.path.isfile(os.path.join(root, model)):
        missing = model
        fallback = getattr(config, "_SIGEWINNE", "models/sigewinne/sigewinne.model3.json")
        model = fallback if os.path.isfile(os.path.join(root, fallback)) else ""

    # The live2d block belongs to one model: what config.json says if you
    # set one, else Sigewinne's expressions for Sigewinne and nothing for
    # a model you've just switched to (its expressions are found by name).
    live2d = config._stored("portrait.live2d") or {}
    if not live2d and model == getattr(config, "_SIGEWINNE", ""):
        live2d = {"expressions": {"sad": "tears", "flustered": "x_eyes", "confused": "spiral_eyes"}}

    return {"model": model, "missing": missing,
            "ear_bones": list(getattr(config, "PORTRAIT_EAR_BONES", []) or []),
            "live2d": live2d,
            "hologram": dict(getattr(config, "PORTRAIT_HOLOGRAM", {}) or {},
                             enabled=bool(getattr(config, "PORTRAIT_HOLOGRAM_ENABLED", False)))}


def portrait_url(transparent=False):
    return url() + "/portrait/" + ("?bg=transparent" if transparent else "")


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
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=_gaze_loop, daemon=True, name="portrait-gaze").start()
    logbook.info("monitor", "live monitor on %s", url())

    return True


# ---------------------------------------------------------------------------
# Where the portrait should look
#
# On Hyprland the portrait window and Luna's terminal both have a place
# on screen, so the portrait can turn towards the conversation instead
# of staring at the middle of its own window. The direction goes out as
# a "gaze" event: x and y from -1 to 1, x towards the right of the
# screen, y up. Anywhere else (another compositor, OBS, the terminal on
# another workspace) it sends {"none": true} and the portrait looks
# ahead, as it always did.
# ---------------------------------------------------------------------------
# How far away, in screen pixels, counts as "as far to the side as she
# can look". Roughly a monitor's width from the portrait.
_GAZE_REACH = 1100.0


def _own_pids():
    pids, pid = set(), os.getpid()

    for _ in range(12):
        if pid <= 1 or pid in pids:
            break

        pids.add(pid)

        try:
            with open(f"/proc/{pid}/stat") as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break

    return pids


def gaze_target():
    """{"x", "y"} from the portrait window towards Luna's terminal, or
    None when either can't be found."""
    import shutil
    import subprocess

    if not shutil.which("hyprctl"):
        return None

    try:
        out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True,
                             text=True, timeout=2)
        clients = json.loads(out.stdout) if out.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return None

    ours = _own_pids()
    terminal = next((c for c in clients if c.get("pid") in ours), None)
    # The portrait page's <title> is "Luna"; Chromium's --app window
    # takes the page title as its own.
    # Firefox and friends append their own name: "Luna — Mozilla Firefox".
    portrait = next((c for c in clients if c is not terminal
                     and re.match(r"^Luna(\s+[-—–]\s+.*)?$", str(c.get("title", "")).strip())),
                    None)

    if not terminal or not portrait:
        return None

    if (terminal.get("workspace") or {}).get("id") != (portrait.get("workspace") or {}).get("id"):
        return None  # she can't see it from here

    try:
        (tx, ty), (tw, th) = terminal["at"], terminal["size"]
        (px, py), (pw, ph) = portrait["at"], portrait["size"]
    except (KeyError, TypeError, ValueError):
        return None

    # Her face sits in the upper third of the window; the conversation
    # is wherever the terminal's middle is.
    dx = (tx + tw / 2) - (px + pw / 2)
    dy = (ty + th / 2) - (py + ph * 0.3)
    clamp = lambda v: max(-1.0, min(1.0, v))

    return {"x": round(clamp(dx / _GAZE_REACH), 3), "y": round(clamp(-dy / _GAZE_REACH), 3)}


def _gaze_loop():
    """Twice a second while a page is open: tell the portrait where the
    terminal is, when that changes. Costs nothing with no page open."""
    last = object()

    while True:
        time.sleep(0.5)

        if not _subs:
            last = object()  # a page that opens later gets a fresh answer
            continue

        target = gaze_target()

        if target is None:
            if last is not None:
                emit("gaze", none=True)
                last = None
            continue

        if (not isinstance(last, dict) or abs(target["x"] - last["x"]) > 0.02
                or abs(target["y"] - last["y"]) > 0.02):
            emit("gaze", **target)
            last = target


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Luna, live</title>
<style>
  :root {
    --bg: #13111c; --panel: #1b1829; --panel2: #201c33; --line: #2d2548;
    --text: #d9d4ec; --dim: #8880a8; --accent: #c49dff; --accent-dim: #7c5cc4;
    --cyan: #7fcfcf; --danger: #e06c8a; --ok: #7ad4a0; --amber: #e0b06c;
    --think-bg: #15122a; --think-border: #3a3060;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 14px/1.55 system-ui, sans-serif; }
  header { position: sticky; top: 0; z-index: 2; background: var(--panel);
           border-bottom: 1px solid var(--line); padding: 12px 18px; }
  .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  h1 { font-size: 18px; margin: 0 10px 0 0; color: var(--accent); }
  .pill { font-size: 12px; border: 1px solid var(--line); border-radius: 20px;
          padding: 1px 10px; color: var(--dim); white-space: nowrap; }
  #stage { font-size: 13px; font-weight: 600; color: var(--bg); background: var(--dim);
           border: 0; padding: 3px 12px; }
  #stage.listening, #stage.recording { background: var(--cyan); }
  #stage.thinking, #stage.chat { background: var(--accent); }
  #stage.speaking { background: var(--ok); }
  #stage.transcribing { background: var(--amber); }
  #conn.off { color: var(--danger); border-color: var(--danger); }
  .ctx { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--dim); }
  .bar { width: 140px; height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; }
  .bar i { display: block; height: 100%; background: var(--ok); width: 0; transition: width .3s; }
  .bar i.warn { background: var(--amber); } .bar i.full { background: var(--danger); }
  main { max-width: 980px; margin: 0 auto; padding: 18px 18px 80px; }
  .turn { margin: 0 0 26px; }
  .turn.old { border-top: 1px solid var(--line); padding-top: 14px; }
  .turn.old { opacity: .55; }
  .lab { color: var(--dim); font-size: 11px; text-transform: uppercase;
         letter-spacing: .08em; margin: 12px 0 4px; display: flex; gap: 8px; align-items: center; }
  .you { font-size: 16px; }
  .src { font-size: 11px; color: var(--accent); border: 1px solid var(--accent-dim);
         border-radius: 20px; padding: 0 7px; text-transform: none; letter-spacing: 0; }
  .think { background: var(--think-bg); border: 1px solid var(--think-border); border-radius: 8px;
           padding: 10px 13px; font: 13px/1.65 ui-monospace, "Cascadia Mono", monospace;
           color: #c8c0e0; white-space: pre-wrap; word-break: break-word; }
  .say { border-left: 3px solid var(--ok); padding: 2px 0 2px 12px; color: #a8d8b8;
         white-space: pre-wrap; word-break: break-word; font-size: 15px; }
  .tool { background: #172626; border: 1px solid #2f5555; border-radius: 8px; padding: 7px 11px;
          margin: 8px 0; font-size: 13px; }
  .tool code { color: var(--cyan); }
  .tool .res { color: var(--dim); margin-top: 3px; white-space: pre-wrap; word-break: break-word; }
  .flags { margin-top: 10px; background: #2a1a24; border: 1px solid #5a2a40; border-radius: 8px;
           padding: 7px 11px; font-size: 13px; color: #e8b8c8; }
  .flags b { color: var(--danger); }
  .end { color: var(--dim); font-size: 12px; margin-top: 6px; }
  .rethink { margin: 12px 0 4px; padding: 6px 11px; border-radius: 8px; font-size: 13px;
             background: #2a2416; border: 1px solid #6a5a2a; color: #f0d9a8; }
  .rethink b { color: var(--amber); }
  .p2 { background: rgba(196,157,255,.10); border-radius: 3px; }
  .p3 { background: rgba(224,176,108,.28); border-radius: 3px; }
  .p4 { background: rgba(224,108,138,.42); color: #fff; border-radius: 3px; }
  .cursor::after { content: "▍"; color: var(--accent); animation: blink 1s steps(2) infinite; }
  @keyframes blink { 50% { opacity: 0; } }
  .empty { color: var(--dim); padding: 40px 0; text-align: center; }
  @media (max-width: 640px) { .bar { width: 80px; } }
</style></head><body>
<header>
  <div class="row">
    <h1>Luna, live</h1>
    <span id="stage" class="pill">idle</span>
    <span id="mood" class="pill" title="energy · warmth">mood</span>
    <span id="model" class="pill">model</span>
    <span class="ctx"><span>context</span><span class="bar"><i id="ctxbar"></i></span><span id="ctxtext">-</span></span>
    <span id="conn" class="pill">connecting…</span>
  </div>
</header>
<main id="feed"><div class="empty" id="empty">Waiting for her next turn. Talk to her and it streams in here.</div></main>
<script>
const $ = id => document.getElementById(id);
let turn = null, box = null, boxKind = "";

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
// Newest turn on top. While it streams, keep its end in view - unless
// you've scrolled off it to read something else.
function nearBottom() {
  if (!turn) return true;
  const r = turn.getBoundingClientRect();
  return r.top < innerHeight && r.bottom <= innerHeight + 120;
}
function follow(was) {
  if (!was || !turn) return;
  const r = turn.getBoundingClientRect();
  if (r.bottom > innerHeight) scrollBy(0, r.bottom - innerHeight + 24);
}

function newTurn(ev) {
  $("empty")?.remove();
  document.querySelectorAll(".turn").forEach(t => t.classList.add("old"));
  const old = document.querySelectorAll(".turn");
  for (let i = 4; i < old.length; i++) old[i].remove();   // keep the page light
  turn = el("div", "turn");
  const l = el("div", "lab", "you said");
  if (ev.source && ev.source !== "typed") l.appendChild(el("span", "src", ev.source));
  turn.append(l, el("div", "you", ev.text || ""));
  $("feed").prepend(turn);
  box = null; boxKind = "";
}
function stream(kind) {
  // Thinking and reply each get a box; a new box starts whenever the
  // stream switches between them or a tool call interrupts.
  if (!turn) newTurn({text: "(a turn already in progress)"});
  if (boxKind === kind && box) return box;
  document.querySelectorAll(".cursor").forEach(c => c.classList.remove("cursor"));
  turn.appendChild(el("div", "lab", kind === "t" ? "thinking" : "she says"));
  box = el("div", (kind === "t" ? "think" : "say") + " cursor");
  turn.appendChild(box); boxKind = kind;
  return box;
}
function tokSpan(text, p) {
  if (p == null || p >= 0.9) return document.createTextNode(text);
  const s = el("span", p >= 0.6 ? "p2" : p >= 0.3 ? "p3" : "p4", text);
  s.title = Math.round(p * 100) + "% likely";
  return s;
}

const handlers = {
  server(ev) { $("model").textContent = ev.model + (ev.backend === "llama" ? " · llama.cpp" : ""); },
  stage(ev) {
    const s = (ev.status || "idle").replace(/[.…]+$/, "");
    $("stage").textContent = s.toLowerCase();
    $("stage").className = "pill " + s.toLowerCase().split(/[ (]/)[0];
  },
  mood(ev) { $("mood").textContent = ev.label ? `${ev.label} · ${ev.energy} / ${ev.warmth}` : "mood off"; },
  context(ev) {
    const f = ev.window ? ev.used / ev.window : 0, bar = $("ctxbar");
    bar.style.width = Math.min(100, f * 100) + "%";
    bar.className = f > 0.9 ? "full" : f > 0.7 ? "warn" : "";
    $("ctxtext").textContent = ev.window ? `~${(ev.used / 1000).toFixed(1)}k / ${(ev.window / 1000).toFixed(0)}k` : `~${(ev.used / 1000).toFixed(1)}k`;
  },
  turn(ev) { newTurn(ev); scrollTo(0, 0); },
  round(ev) { if (ev.n > 0) box = null; },
  tok(ev) { const w = nearBottom(); stream(ev.p).appendChild(tokSpan(ev.s, ev.c)); follow(w); },
  tool(ev) {
    const w = nearBottom();
    if (!turn) newTurn({text: ""});
    document.querySelectorAll(".cursor").forEach(c => c.classList.remove("cursor"));
    const t = el("div", "tool"); t.dataset.name = ev.name;
    t.append(document.createTextNode("calls "), el("code", null, `${ev.name}(${ev.args || ""})`));
    turn.appendChild(t); box = null; boxKind = ""; follow(w);
  },
  tool_result(ev) {
    const t = [...turn?.querySelectorAll(".tool") || []].reverse().find(x => x.dataset.name === ev.name && !x.dataset.done);
    if (t) { t.dataset.done = 1; t.appendChild(el("div", "res", "→ " + ev.result)); }
  },
  flags(ev) {
    if (!turn || !ev.flags.length) return;
    const f = el("div", "flags");
    for (const x of ev.flags) {
      const [code, ...why] = x.split(": "), line = el("div");
      line.append(el("b", null, "!! " + code), document.createTextNode(why.length ? " — " + why.join(": ") : ""));
      f.appendChild(line);
    }
    turn.appendChild(f);
  },
  rethink(ev) {
    const w = nearBottom();
    if (!turn) return;
    document.querySelectorAll(".cursor").forEach(c => c.classList.remove("cursor"));
    const r = el("div", "rethink");
    r.append(el("b", null, ev.step === "start" ? "taking a second look" : "second look: "),
             document.createTextNode(ev.step === "start" ? ` — ${ev.reason}` : ev.outcome));
    turn.appendChild(r); box = null; boxKind = ""; follow(w);
  },
  done(ev) {
    document.querySelectorAll(".cursor").forEach(c => c.classList.remove("cursor"));
    if (turn) turn.appendChild(el("div", "end", `${ev.seconds}s` + (ev.conf != null ? ` · ${Math.round(ev.conf * 100)}% sure` : "")));
  },
};

function connect() {
  const es = new EventSource("/events");
  es.onopen = () => { $("conn").textContent = "live"; $("conn").className = "pill"; };
  es.onerror = () => { $("conn").textContent = "reconnecting…"; $("conn").className = "pill off"; };
  es.onmessage = m => { const ev = JSON.parse(m.data); (handlers[ev.t] || (() => {}))(ev); };
}
connect();
</script>
</body></html>
"""


def main():
    """`python livefeed.py [--open thoughts|memory|portrait]`: the pages
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
