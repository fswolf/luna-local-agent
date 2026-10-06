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
import json
import queue
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
_SNAPSHOT_KINDS = ("stage", "mood", "context", "server", "turn")
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
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/events":
            self._stream()
        else:
            self.send_response(404)
            self.end_headers()

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
    logbook.info("monitor", "live monitor on %s", url())

    return True


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
function nearBottom() { return innerHeight + scrollY >= document.body.scrollHeight - 120; }
function follow(was) { if (was) scrollTo(0, document.body.scrollHeight); }

function newTurn(ev) {
  $("empty")?.remove();
  document.querySelectorAll(".turn").forEach(t => t.classList.add("old"));
  const old = document.querySelectorAll(".turn");
  for (let i = 0; i < old.length - 4; i++) old[i].remove();   // keep the page light
  turn = el("div", "turn");
  const l = el("div", "lab", "you said");
  if (ev.source && ev.source !== "typed") l.appendChild(el("span", "src", ev.source));
  turn.append(l, el("div", "you", ev.text || ""));
  $("feed").appendChild(turn);
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
  turn(ev) { const w = nearBottom(); newTurn(ev); follow(w); },
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
