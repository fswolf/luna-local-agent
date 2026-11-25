"""A window into her memory.

    python memory-manager/manager.py

opens a small page on http://127.0.0.1:8790 with three tabs. About you:
view, search, add, edit, confirm, retire, restore and delete facts
(agent/facts.db), and what she's concluded about you and the people she
knows (mark one wrong, or bring it back). (Your preferences used to be edited here too; they live
in agent.json now, under Who she is on the settings page.) Her notebook
(agent/notebook.db): how she feels about the games she's played, and her
notes on past conversations and game sessions. Her lessons: what she's
learned about how she behaves - facts are about you, the notebook is about her. It's a separate
process on purpose: memory is the one thing you occasionally want to
inspect while suspecting the assistant of being wrong about it.

Safe to use while she runs: SQLite coordinates the two processes itself
(WAL), and the assistant reads rows per query rather than caching them,
so an edit here is in her next prompt.

Localhost only. It's your memory; nothing here should ever be
reachable from another machine.
"""
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

PORT = 8790


def _factstore():
    from mind import factstore

    return factstore


def _ready():
    """facts.db open (an old memory.json's facts read in, the first time)."""
    from mind import longterm

    return longterm.ready()


# ---------------------------------------------------------------------------
# One state blob for the page
# ---------------------------------------------------------------------------
HISTORY = 500          # the newest changes the History tab shows


def state():
    active, retired, warning, forgotten, history = [], [], "", 0, []

    if _ready():
        store = _factstore()
        rows = store.rows(limit=100000)
        old = store.rows(retired=True, limit=100000)
        ids, extra = [r[0] for r in rows + old], {}
        for start in range(0, len(ids), 1000):                  # row_details takes 1000 at a time
            extra.update(store.row_details(ids[start:start + 1000]))
        info = lambda i: dict(zip(("since", "until", "sure"), extra.get(i, ("", "", True))))
        active = [
            {"id": i, "fact": fact, "subject": subject, "created": created[:10], **info(i)}
            for i, fact, subject, created, _w in rows
        ]
        retired = [
            {"id": i, "fact": fact, "subject": subject,
             "created": created[:10], "retired": when[:10], **info(i)}
            for i, fact, subject, created, when in old
        ]
        forgotten = store.forgotten_count()
        history = [{"at": at[:16].replace("T", " "), "action": action, "id": fact_id, "fact": text,
                    "detail": detail, "by": by}
                   for _e, at, action, fact_id, text, detail, by in store.events(limit=HISTORY)]
    else:
        warning = "agent/facts.db can't be opened - the assistant's log says why."

    return {
        "active": active,
        "retired": retired,
        "forgotten": forgotten,
        "history": history,
        "warning": warning,
        "notebook": notebook_state(),
    }


def _notebook():
    from mind import notebook

    return notebook


def notebook_state():
    """Her notebook for the page, or None if it can't be read."""
    try:
        nb = _notebook()
        games = nb.play_episodes()
        lesson = lambda l: {"id": l["id"], "text": l["text"], "created": str(l["created"])[:10],
                            "hits": l["hits"], "origin": l["origin"]}
        return {
            "feelings": [{"game": g, "title": f.get("title", g), "feeling": f.get("feeling", ""),
                          "at": str(f.get("at", ""))[:10]}
                         for g, f in sorted(nb.game_feelings().items(),
                                            key=lambda kv: str(kv[1].get("at", "")), reverse=True)],
            "episodes": [{"id": e["id"], "ended": str(e["ended"])[:16].replace("T", " "),
                          "turns": e["turns"], "summary": e["summary"], "game": games.get(e["id"], "")}
                         for e in nb.episodes(100000)],
            "lessons": [lesson(l) for l in nb.lessons()],
            "retired_lessons": [lesson(l) for l in nb.lessons(retired=True)],
            **conclusions_state(),
        }
    except Exception:
        return None


def conclusions_state():
    """What she's concluded about each person (mind/conclusions.py)."""
    from mind import conclusions

    try:
        conclusions.rows(limit=1)
    except Exception:
        return {"conclusions": [], "retired_conclusions": []}     # the rest of the notebook still shows
    row = lambda r: {"id": r["id"], "person": conclusions.label(r["person"]), "text": r["text"],
                     "kind": r["kind"], "from": len(r["sources"]), "created": str(r["created"])[:10],
                     "why": r["why"], "backed": str(r["backed"])[:10]}
    return {"conclusions": [row(r) for r in conclusions.rows()],
            "retired_conclusions": [row(r) for r in conclusions.rows(retired=True, limit=500)]}


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------
def apply(action, body):
    """One edit from the page. Fact changes go in her memory's log as the memory page's."""
    from mind import factstore

    with factstore.acting("memory page"):
        _apply(action, body)


def _apply(action, body):
    fact = str(body.get("fact", "")).strip()
    subject = str(body.get("subject", "")).strip()

    if action.startswith("nb_"):
        nb = _notebook()
        if action == "nb_feeling":
            game, feeling = str(body.get("game", "")), str(body.get("feeling", "")).strip()
            title = nb.game_feelings().get(game, {}).get("title", game)
            if not game or not feeling:
                raise ValueError("empty feeling")
            nb.set_game_feeling(game, title, feeling)
        elif action == "nb_feeling_forget":
            nb.forget_game_feeling(str(body.get("game", "")))
        elif action == "nb_episode_forget":
            nb.delete_episode(int(body.get("id", -1)))
        elif action == "nb_lesson_retire":
            nb.retire_lesson(int(body.get("id", -1)))
        elif action == "nb_lesson_restore":
            nb.restore_lesson(int(body.get("id", -1)))
        elif action == "nb_conclusion_wrong":
            from mind import conclusions

            conclusions.mark_wrong(int(body.get("id", -1)), "on the memory page")
        elif action == "nb_conclusion_restore":
            from mind import conclusions

            conclusions.restore(int(body.get("id", -1)))
        else:
            raise ValueError(f"unknown action {action!r}")
        return

    if not _ready():
        raise ValueError("agent/facts.db can't be opened - nothing was changed")

    store = _factstore()
    fact_id = int(body.get("id", -1))

    if action == "add":
        if not fact:
            raise ValueError("empty fact")

        store.add(fact, subject, again=True)       # you adding it is asking for it back
    elif action == "edit":
        if not fact:
            raise ValueError("empty fact")

        store.set_row(fact_id, fact, subject)
        store.confirm_row(fact_id)                 # you wrote it: it's sure
    elif action == "retire":
        store.retire_row(fact_id)
    elif action == "restore":
        store.restore_row(fact_id)
    elif action == "confirm":
        store.confirm_row(fact_id)
    elif action == "delete":
        # a delete is a forget: out of everything else she keeps, and never relearned
        gone = [r[1] for r in store.rows(limit=100000) + store.rows(retired=True, limit=100000)
                if r[0] == fact_id]
        if store.delete_row(fact_id) and gone:
            from mind import forgetting

            forgetting.forget(gone[0], wait=True)
    elif action == "unforget_all":
        store.unbury_all()
    else:
        raise ValueError(f"unknown action {action!r}")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _request_ok(handler, post=False):
    """Only this machine's own page may talk to this server.

    Host must be 127.0.0.1 or localhost on our port: a page on some other
    site that re-points its own name at 127.0.0.1 (DNS rebinding) still
    sends its own name as Host, and is turned away here. A browser always
    sends Origin on a cross-site POST, so that must be ours too. And a
    POST must say application/json - a plain HTML form can't send that,
    and a script on another site can't send it without a preflight that
    this server never answers.

    Served through the live monitor (/memory/, /thoughts/), the monitor
    has already checked Host and Origin against its own port.
    """
    if not getattr(handler, "_checked_by_monitor", False):
        here = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

        if handler.headers.get("Host") not in here:
            return False

        origin = handler.headers.get("Origin")

        if origin is not None and origin.split("://", 1)[-1] not in here:
            return False

    if post:
        kind = (handler.headers.get("Content-Type") or "").split(";")[0].strip().lower()

        if kind != "application/json":
            return False

    return True


MAX_BODY = 1024 * 1024      # a fact, a note or the preferences: far less than this


def _length(headers):
    """Content-Length, 0 to MAX_BODY. Negative or broken is 0: read(-1)
    would wait until the page hung up."""
    try:
        return max(0, min(int(headers.get("Content-Length") or 0), MAX_BODY))
    except ValueError:
        return 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet - it's a local page, not a service

    def _send(self, code, body, content_type="application/json"):
        payload = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if not _request_ok(self):
            self._send(403, '{"error": "forbidden"}')

            return

        if self.path == "/":
            self._send(200, PAGE, "text/html")
        elif self.path == "/api/state":
            try:
                body = json.dumps(state())
            except Exception as e:
                # the sqlite file locked or broken: the page says why, the
                # server doesn't print a traceback for every refresh
                self._send(500, json.dumps({"error": f"couldn't read her memory: {e}"}))
                return
            self._send(200, body)
        else:
            self._send(404, '{"error": "not found"}')

    def do_POST(self):
        if not _request_ok(self, post=True):
            self._send(403, '{"error": "forbidden"}')

            return

        if not self.path.startswith("/api/"):
            self._send(404, '{"error": "not found"}')

            return

        try:
            length = _length(self.headers)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("expected a JSON object")
            apply(self.path[5:], body)
            self._send(200, '{"ok": true}')
        except Exception as e:
            self._send(400, json.dumps({"ok": False, "error": str(e)}))


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Luna's memory</title>
<style>
  :root {
    --bg: #16121f; --panel: #1e1830; --line: #322a4a;
    --text: #d8d2e8; --dim: #8a80a5; --accent: #b48aff;
    --accent-dim: #7c5cc4; --danger: #e06c8a; --ok: #7ad4a0;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px 60px;
    background: var(--bg); color: var(--text);
    font: 15px/1.5 system-ui, sans-serif;
    max-width: 900px; margin-inline: auto;
  }
  h1 { font-size: 20px; margin: 0 0 4px; color: var(--accent); }
  h2 { font-size: 15px; margin: 28px 0 8px; color: var(--dim);
       text-transform: uppercase; letter-spacing: .08em; }
  #meta { color: var(--dim); font-size: 13px; margin-bottom: 12px; }
  #warning {
    display: none; background: #3a2438; border: 1px solid #6a3a55;
    color: #e8b8c8; padding: 8px 12px; border-radius: 8px;
    font-size: 13px; margin: 10px 0;
  }
  #search, #addrow input {
    width: 100%; padding: 9px 12px; border-radius: 8px;
    border: 1px solid var(--line); background: var(--panel);
    color: var(--text); font-size: 14px; outline: none;
  }
  #search:focus, #addrow input:focus { border-color: var(--accent-dim); }
  .fact {
    display: flex; gap: 10px; align-items: flex-start;
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 8px; padding: 9px 12px; margin: 6px 0;
  }
  .fact .text { flex: 1; word-break: break-word; }
  .fact .subject {
    color: var(--accent-dim); font-size: 12px;
    border: 1px solid var(--line); border-radius: 20px;
    padding: 1px 9px; white-space: nowrap; margin-top: 2px;
  }
  .fact .date { color: var(--dim); font-size: 12px;
                white-space: nowrap; margin-top: 3px; }
  .fact.retired { opacity: .6; }
  .fact .unsure { color: var(--danger); font-size: 12px; border: 1px dashed var(--line);
                  border-radius: 20px; padding: 1px 9px; white-space: nowrap; margin-top: 2px; }
  .fact.retired .text { text-decoration: line-through; }
  button {
    background: none; border: 1px solid var(--line); color: var(--dim);
    border-radius: 6px; padding: 3px 10px; font-size: 12px;
    cursor: pointer; white-space: nowrap;
  }
  button:hover { color: var(--text); border-color: var(--accent-dim); }
  button.danger:hover { color: var(--danger); border-color: var(--danger); }
  input.inline, textarea {
    width: 100%; background: var(--bg); color: var(--text);
    border: 1px solid var(--accent-dim); border-radius: 6px;
    padding: 6px 9px; font-size: 14px; outline: none;
  }
  input.inline.subject-input { width: 130px; }
  #addrow { display: flex; gap: 8px; margin: 10px 0 4px; }
  #addrow input { flex: 1; }
  #addrow input.short { flex: 0 0 140px; }
  textarea { font-family: ui-monospace, monospace; font-size: 13px;
             min-height: 220px; resize: vertical; }
  .row-buttons { display: flex; gap: 6px; }
  #status { position: fixed; bottom: 14px; right: 16px; font-size: 13px;
            color: var(--ok); opacity: 0; transition: opacity .3s; }
  .empty { color: var(--dim); font-size: 13px; padding: 8px 2px; }
  .meta-note { color: var(--dim); font-size: 13px; }
  #epsearch, #hsearch {
    width: 100%; padding: 9px 12px; border-radius: 8px;
    border: 1px solid var(--line); background: var(--panel);
    color: var(--text); font-size: 14px; outline: none;
  }
  #tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); margin: 6px 0 16px; flex-wrap: wrap; }
  #tabs a { color: var(--dim); text-decoration: none; padding: 7px 14px; border-radius: 8px 8px 0 0;
            border: 1px solid transparent; border-bottom: none; margin-bottom: -1px; font-size: 14px; }
  #tabs a:hover { color: var(--text); }
  #tabs a.on { color: var(--accent); background: var(--panel); border-color: var(--line); }
  #tabs span { font-size: 12px; color: var(--dim); }
  @media (max-width: 480px) { #tabs a { padding: 6px 8px; font-size: 13px; } }
  section[hidden] { display: none; }
  .fact .game { color: var(--ok); font-size: 12px; border: 1px solid var(--line);
                border-radius: 20px; padding: 1px 9px; white-space: nowrap; margin-top: 2px; }
</style></head><body>

<h1>Luna's memory</h1>
<nav id="tabs">
  <a href="#facts" data-tab="facts">About you <span id="n-facts"></span></a>
  <a href="#notebook" data-tab="notebook">Her notebook <span id="n-notebook"></span></a>
  <a href="#lessons" data-tab="lessons">Her lessons <span id="n-lessons"></span></a>
  <a href="#history" data-tab="history">History</a>
</nav>

<section data-tab="facts">
<div id="meta">loading...</div>
<div id="unforget" style="display:none" class="meta-note">Forgotten facts stay forgotten (she keeps a fingerprint, not the words).
  <button onclick="unforgetAll()">let her learn them again</button></div>
<div id="warning"></div>

<h2>Add a fact</h2>
<div id="addrow">
  <input id="newfact" placeholder="one short fact, e.g. works nights" >
  <input id="newsubject" class="short" placeholder="subject (optional)">
  <button onclick="addFact()">add</button>
</div>

<h2>Facts</h2>
<input id="search" placeholder="filter..." oninput="render()">
<div id="active"></div>

<h2 id="retired-h">Retired</h2>
<div id="retired"></div>

<div id="nb-conclusions">
<h2>What she's concluded</h2>
<div class="meta-note">Read back from your conversations while she's idle: <b>said</b> is something you told her, <b>inferred</b> her own read of you (from two or more exchanges). Overnight she merges duplicates, sets aside the older of two that contradict, and lets guesses nothing has backed up fade. Mark one wrong and she won't conclude it again. <code>/conclusions why &lt;n&gt;</code> in the app shows the conversation behind one.</div>
<input id="csearch" placeholder="filter..." oninput="renderNotebook()">
<div id="conclusions"></div>
<h2>Set aside</h2>
<div id="rconclusions"></div>
</div>

<h2>Preferences</h2>
<div class="meta-note">What she calls you, nicknames and what to avoid are in agent.json now, as <code>user_preferences</code>: the settings page, <a href="/settings/">Who she is</a>.</div>
<!-- <textarea id="prefs" spellcheck="false"></textarea>
<div style="margin-top:8px"><button onclick="savePrefs()">save preferences</button></div> -->
</section>

<section data-tab="notebook" hidden>
<div class="meta-note">What she remembers about herself: written by her while idle, in her own words. Facts are about you; this is about her.</div>
<div class="empty nb-missing" style="display:none">Her notebook (agent/notebook.db) can't be read right now.</div>
<div id="nb">
<h2>How she feels about games</h2>
<div id="feelings"></div>

<h2>Her notes on conversations and games</h2>
<input id="epsearch" placeholder="filter..." oninput="renderNotebook()">
<div id="episodes"></div>
</div>
</section>

<section data-tab="lessons" hidden>
<div class="meta-note">What she's learned about how she behaves: from her idle passes, and the ones she noted herself mid-conversation. Retire one and she stops being reminded of it.</div>
<div class="empty nb-missing" style="display:none">Her lessons (agent/notebook.db) can't be read right now.</div>
<div id="nb-lessons">
<h2>Lessons she's learned</h2>
<div id="lessons"></div>
<h2 id="rlessons-h">Retired lessons</h2>
<div id="rlessons"></div>
</div>
</section>

<section data-tab="history" hidden>
<div class="meta-note">Every change to what she knows about you, newest first: what changed, when, and who did it (her own tools, the background extractor, the tidy pass, this page). A forgotten fact's words are gone from here too; only the date it was forgotten stays.</div>
<h2>Changes to the facts</h2>
<input id="hsearch" placeholder="filter..." oninput="renderHistory()">
<div id="history"></div>
</section>

<div id="status"></div>

<script>
let S = {active: [], retired: []};

function flash(msg, bad) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.style.color = bad ? "var(--danger)" : "var(--ok)";
  el.style.opacity = 1;
  setTimeout(() => el.style.opacity = 0, 1800);
}

async function api(action, body) {
  const r = await fetch("api/" + action, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {}),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { flash(data.error || "failed", true); throw new Error(); }
  return data;
}

async function refresh(keepPrefs) {
  const r = await fetch("api/state");
  S = await r.json();
  const unsure = S.active.filter(f => !f.sure).length;
  document.getElementById("meta").textContent =
    `${S.active.length} active` + (unsure ? ` (${unsure} not sure)` : "") +
    `, ${S.retired.length} retired` + (S.forgotten ? `, ${S.forgotten} forgotten for good` : "");
  document.getElementById("unforget").style.display = S.forgotten ? "" : "none";
  const warn = document.getElementById("warning");
  warn.style.display = S.warning ? "block" : "none";
  warn.textContent = S.warning;
  // if (!keepPrefs) document.getElementById("prefs").value = S.prefs;    // moved to agent.json
  render();
  renderNotebook();
  renderHistory();
}

// The change log: text a model wrote, so textContent only
function renderHistory() {
  const q = document.getElementById("hsearch").value.toLowerCase();
  fill("history", (S.history || [])
    .filter(h => !q || [h.fact, h.detail, h.action, h.by].join(" ").toLowerCase().includes(q))
    .map(h => nbRow((h.id != null ? "#" + h.id + " " : "") + h.action + (h.fact ? ": " + h.fact
                    : h.action === "forgotten" ? ": (the words were forgotten)" : ""),
                    [["subject", h.detail], ["game", h.by], ["date", h.at]], [])),
    "no changes yet");
}

// Her notebook: rows built with textContent, never innerHTML - it's text
// a model wrote, some of it from games and web pages.
function nbRow(text, chips, buttons, dim) {
  const row = document.createElement("div");
  row.className = "fact" + (dim ? " retired" : "");
  const t = document.createElement("div");
  t.className = "text"; t.textContent = text;
  row.appendChild(t);
  for (const [cls, label] of chips) {
    if (!label) continue;
    const c = document.createElement("div");
    c.className = cls; c.textContent = label;
    row.appendChild(c);
  }
  const box = document.createElement("div");
  box.className = "row-buttons";
  for (const [label, cls, fn] of buttons) {
    const b = document.createElement("button");
    b.textContent = label; if (cls) b.className = cls;
    b.onclick = fn; box.appendChild(b);
  }
  row.appendChild(box);
  return row;
}

function fill(id, rows, empty) {
  const el = document.getElementById(id);
  el.replaceChildren(...rows);
  if (!rows.length) {
    const d = document.createElement("div");
    d.className = "empty"; d.textContent = empty;
    el.appendChild(d);
  }
}

function editFeeling(row, f) {
  row.replaceChildren();
  const input = document.createElement("input");
  input.className = "inline"; input.value = f.feeling;
  const save = document.createElement("button");
  save.textContent = "save";
  save.onclick = async () => { await api("nb_feeling", {game: f.game, feeling: input.value}); flash("saved"); refresh(true); };
  const cancel = document.createElement("button");
  cancel.textContent = "cancel"; cancel.onclick = () => refresh(true);
  const box = document.createElement("div");
  box.className = "row-buttons"; box.append(save, cancel);
  row.append(input, box);
  input.focus();
  input.onkeydown = e => { if (e.key === "Enter") save.onclick(); };
}

// Tabs: one page each for facts, her notebook and her lessons, remembered in
// the address (#notebook), so a reload or a link lands on the same one.
function showTab() {
  const want = (location.hash || "#facts").slice(1);
  const tab = ["facts", "notebook", "lessons", "history"].includes(want) ? want : "facts";
  document.querySelectorAll("section[data-tab]").forEach(s => s.hidden = s.dataset.tab !== tab);
  document.querySelectorAll("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.tab === tab));
}
window.addEventListener("hashchange", showTab);
showTab();

function count(id, n) { document.getElementById(id).textContent = n ? `(${n})` : ""; }

function renderNotebook() {
  const N = S.notebook;
  for (const id of ["nb", "nb-lessons", "nb-conclusions"]) document.getElementById(id).style.display = N ? "" : "none";
  document.querySelectorAll(".nb-missing").forEach(el => el.style.display = N ? "none" : "");
  count("n-facts", S.active.length);
  count("n-notebook", N ? N.episodes.length + N.feelings.length : 0);
  count("n-lessons", N ? N.lessons.length : 0);
  if (!N) return;

  fill("feelings", N.feelings.map(f => {
    const row = nbRow(f.title + ": " + f.feeling, [["date", f.at]], [
      ["edit", "", () => editFeeling(row, f)],
      ["forget", "danger", async () => {
        if (!confirm("Forget how she feels about " + f.title + "?")) return;
        await api("nb_feeling_forget", {game: f.game}); refresh(true); }],
    ]);
    return row;
  }), "nothing yet - she writes one after each game session");

  const q = document.getElementById("epsearch").value.toLowerCase();
  fill("episodes", N.episodes
    .filter(e => !q || e.summary.toLowerCase().includes(q) || e.game.toLowerCase().includes(q))
    .map(e => nbRow(e.summary, [["game", e.game], ["date", e.ended]], [
      ["forget", "danger", async () => {
        if (!confirm("Forget this?\n\n" + e.summary)) return;
        await api("nb_episode_forget", {id: e.id}); refresh(true); }],
    ])), "no notes yet");

  // where it came from, and how often it's been used or learned again
  const tags = l => [["game", l.origin === "self" ? "noted herself" : ""],
                     ["subject", l.hits ? `used ${l.hits}×` : ""], ["date", l.created]];
  fill("lessons", N.lessons.map(l => nbRow(l.text, tags(l), [
    ["retire", "", async () => { await api("nb_lesson_retire", {id: l.id}); refresh(true); }],
  ])), "no lessons yet");
  fill("rlessons", N.retired_lessons.map(l => nbRow(l.text, tags(l), [
    ["restore", "", async () => { await api("nb_lesson_restore", {id: l.id}); refresh(true); }],
  ], true)), "none retired");

  // whose, said or her read, how many exchanges it came from, when
  const cq = document.getElementById("csearch").value.toLowerCase();
  const ctags = c => [["subject", c.person], ["game", c.kind],
                      ["date", `#${c.id} · from ${c.from} · ${c.created}` + (c.backed ? ` · seen again ${c.backed}` : "")]];
  fill("conclusions", N.conclusions
    .filter(c => !cq || (c.text + " " + c.person + " " + c.kind).toLowerCase().includes(cq))
    .map(c => nbRow(c.text, ctags(c), [
      ["wrong", "", async () => { await api("nb_conclusion_wrong", {id: c.id}); refresh(true); }],
    ])), "none yet - she reads back conversations while idle");
  // one the pass outdated can still be marked wrong, so it never comes back
  fill("rconclusions", N.retired_conclusions.map(c => nbRow(c.text + (c.why ? "  (" + c.why + ")" : ""), ctags(c), [
    ...(c.why.startsWith("marked wrong") ? [] :
        [["wrong", "", async () => { await api("nb_conclusion_wrong", {id: c.id}); refresh(true); }]]),
    ["restore", "", async () => { await api("nb_conclusion_restore", {id: c.id}); refresh(true); }],
  ], true)), "none set aside");
}

function factRow(f, retired) {
  const row = document.createElement("div");
  row.className = "fact" + (retired ? " retired" : "");
  const text = document.createElement("div");
  text.className = "text";
  text.textContent = f.fact;
  row.appendChild(text);
  if (f.subject) {
    const s = document.createElement("div");
    s.className = "subject"; s.textContent = f.subject;
    row.appendChild(s);
  }
  if (!f.sure) {
    const u = document.createElement("div");
    u.className = "unsure"; u.textContent = "not sure";
    u.title = "picked up once in passing; she won't state it as fact until it's confirmed";
    row.appendChild(u);
  }
  if (f.since || f.until) {
    const t = document.createElement("div");
    t.className = "date"; t.textContent = "true " + [f.since && "from " + f.since, f.until && "to " + f.until].filter(Boolean).join(" ");
    row.appendChild(t);
  }
  if (retired && f.retired) {
    const d = document.createElement("div");
    d.className = "date"; d.textContent = "retired " + f.retired;
    row.appendChild(d);
  } else if (f.created) {
    const d = document.createElement("div");
    d.className = "date"; d.textContent = f.created;
    row.appendChild(d);
  }

  const buttons = document.createElement("div");
  buttons.className = "row-buttons";

  function btn(label, cls, fn) {
    const b = document.createElement("button");
    b.textContent = label; if (cls) b.className = cls;
    b.onclick = fn; buttons.appendChild(b);
  }

  if (!retired) {
    if (!f.sure) btn("confirm", "", async () => { await api("confirm", {id: f.id}); refresh(true); });
    btn("edit", "", () => editRow(row, f));
    btn("retire", "", async () => { await api("retire", {id: f.id}); refresh(true); });
  } else {
    btn("restore", "", async () => { await api("restore", {id: f.id}); refresh(true); });
  }
  btn("delete", "danger", async () => {
    if (!confirm("Forget this for good?\n\n" + f.fact + "\n\nIt's also taken out of her notes, summaries and logs, and she won't learn it again unless you add it back.")) return;
    await api("delete", {id: f.id}); refresh(true);
  });

  row.appendChild(buttons);
  return row;
}

function editRow(row, f) {
  row.replaceChildren();
  const text = document.createElement("input");
  text.className = "inline"; text.value = f.fact;
  row.appendChild(text);
  const subject = document.createElement("input");
  subject.className = "inline subject-input";
  subject.value = f.subject || ""; subject.placeholder = "subject";
  row.appendChild(subject);
  const buttons = document.createElement("div");
  buttons.className = "row-buttons";
  const save = document.createElement("button");
  save.textContent = "save";
  save.onclick = async () => {
    await api("edit", {id: f.id, fact: text.value,
                       subject: subject.value});
    flash("saved"); refresh(true);
  };
  const cancel = document.createElement("button");
  cancel.textContent = "cancel"; cancel.onclick = () => refresh(true);
  buttons.append(save, cancel);
  row.appendChild(buttons);
  text.focus();
  text.onkeydown = e => { if (e.key === "Enter") save.onclick(); };
}

function render() {
  const filter = document.getElementById("search").value.toLowerCase();
  const match = f => !filter || f.fact.toLowerCase().includes(filter)
                   || (f.subject || "").toLowerCase().includes(filter);

  const active = document.getElementById("active");
  active.replaceChildren();
  const shown = S.active.filter(match);
  if (!shown.length)
    active.innerHTML = '<div class="empty">nothing here</div>';
  shown.forEach(f => active.appendChild(factRow(f, false)));

  const retiredWrap = document.getElementById("retired");
  retiredWrap.replaceChildren();
  const rows = S.retired.filter(match);
  if (!rows.length)
    retiredWrap.innerHTML = '<div class="empty">nothing retired</div>';
  rows.forEach(f => retiredWrap.appendChild(factRow(f, true)));
}

async function unforgetAll() {
  if (!confirm("Let her learn the forgotten facts again if they come up?")) return;
  await api("unforget_all", {}); flash("done"); refresh(true);
}

async function addFact() {
  const fact = document.getElementById("newfact");
  const subject = document.getElementById("newsubject");
  if (!fact.value.trim()) return;
  await api("add", {fact: fact.value, subject: subject.value});
  fact.value = ""; subject.value = "";
  flash("added"); refresh(true);
}
document.getElementById("newfact").onkeydown =
  e => { if (e.key === "Enter") addFact(); };

// async function savePrefs() {    // preferences moved to agent.json
//   await api("prefs", {text: document.getElementById("prefs").value});
//   flash("preferences saved");
// }

refresh();
</script>
</body></html>
"""


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"memory manager: {url}  (Ctrl+C stops it)")

    threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
