"""The settings page: every setting, in a browser.

    http://127.0.0.1:8792/settings/      (or /settings in the terminal)

The terminal's settings pane keeps the everyday ones; this page has all
of them, with switches, sliders, drop-downs, search and presets. Both
stand on the same three things, so they can't disagree: config/schema.py
says what a setting is, config.save_any() checks and saves it, and
ui.settings_pane._after() applies the ones that need more than a new
value (the mic mode, presence, the portrait's frame...).

Served by livefeed, so it inherits its guard: localhost only, and a
request whose Host or Origin isn't this server is refused. Changing a
setting also needs this session's key, which is only in the page itself:
another site open in your browser can send a request here, but can't
read the page to learn the key. Passwords and tokens are never sent to
the page, only whether one is set.
"""
import json
import re
import secrets

import config
import logbook

NAME = "settings"
KEY = secrets.token_urlsafe(24)       # this session's; a restart makes a new one


def _pane():
    from ui import settings_pane

    return settings_pane


# Sliders for the numbers people drag rather than type: (min, max, step).
RANGES = {
    "tts.speed": (0.5, 2, 0.05), "tts.volume": (0, 2, 0.05), "tts.pitch": (-6, 6, 0.5),
    "stt.sensitivity": (0.2, 3, 0.05), "stt.silence_seconds": (0.4, 4, 0.1),
    "alarms.volume": (0, 2, 0.05), "portrait.sound_volume": (0, 1, 0.05),
    "camera.presence.fps": (1, 10, 0.5), "camera.presence.greet_after_minutes": (5, 240, 5),
    "camera.presence.quiet_after_minutes": (1, 60, 1),
}


def _range(kind, line, path=""):
    """A slider's (min, max, step) for the numbers whose line gives a
    0-1 or 0..2 style range, or that RANGES names; None for a plain box."""
    if kind not in ("float", "int"):
        return None
    if path in RANGES:
        return RANGES[path]
    if re.search(r"\b0\s*-\s*1\b", line):
        return (0, 1, 0.01)
    m = re.search(r"\b0 [^,]*, 1 [^,]*, 2\b", line)       # "0 almost flat, 1 as designed, 2 very emotional"
    if m:
        return (0, 2, 0.05)
    return None


def entry(path):
    """One setting, as the page sees it."""
    pane = _pane()
    kind, line, choices = pane.describe(path)
    value, is_set = pane._value(path)
    group, title = pane._section(path)
    from config.schema import BASIC

    out = {"path": path, "name": pane._short(path, group), "group": group, "kind": kind,
           "help": line, "choices": list(choices), "set": is_set,
           "live": bool(config.SETTINGS.get(path, (None, False))[1]),
           "basic": path in BASIC, "range": _range(kind, line, path)}

    if kind == "secret":
        out["value"] = None
        out["has"] = bool(value)                  # never the secret itself
    elif kind == "dict":
        out["value"] = None                       # a nested block can hold logins (mcp.servers' headers)
        out["has"] = len(value) if isinstance(value, dict) else 0
    else:
        out["value"] = value

    rng = out["range"]
    if rng and isinstance(value, (int, float)) and not isinstance(value, bool):
        # a value set outside the usual range by hand: widen it rather than clamp
        out["range"] = (min(rng[0], value), max(rng[1], value), rng[2])

    return out


def listing():
    """Every setting, grouped, plus the presets."""
    from config.presets import PRESETS

    pane = _pane()
    groups, where = [], {}

    for path in pane._all_paths():
        group, title = pane._section(path)

        if group not in where:
            where[group] = len(groups)
            groups.append({"key": group, "title": title, "settings": []})

        groups[where[group]]["settings"].append(entry(path))

    presets = [{"name": n, "label": p["label"], "about": p["about"], "count": len(p["values"]),
                "values": p["values"],
                "active": all(pane._value(path)[0] == v for path, v in p["values"].items())}
               for n, p in PRESETS.items()]

    return {"groups": groups, "presets": presets}


def _raw(value):
    """What the page sent -> the text config's checks expect."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(map(str, value))
    if value is None:
        return ""
    return str(value)


def change(path, value):
    """Save one setting and apply it. Returns (ok, message, entry or None)."""
    if not isinstance(path, str) or not path or len(path) > 120:
        return False, "no such setting", None
    if path not in _pane()._all_paths():
        return False, f"unknown setting {path!r}", None

    try:
        saved, live = config.save_any(path, _raw(value))
    except ValueError as e:
        return False, str(e), None
    except OSError as e:
        return False, f"couldn't write config.json: {e}", None

    _pane()._after(path, saved)
    logbook.info("settings", "web: %s changed", path)
    return True, "saved" + ("" if live else ", applies after a restart"), entry(path)


def reset(path):
    if path not in _pane()._all_paths():
        return False, f"unknown setting {path!r}", None
    try:
        removed = config.reset_setting(path)
    except OSError as e:
        return False, f"couldn't write config.json: {e}", None
    return True, ("back to the default after a restart" if removed else "already the default"), entry(path)


def preset(name):
    from config import presets

    try:
        done = presets.apply(name)
    except KeyError:
        return False, f"no preset {name!r}", None
    except (ValueError, OSError) as e:
        return False, str(e), None

    for path, value, _live in done:
        _pane()._after(path, value)

    later = sum(1 for _p, _v, live in done if not live)
    label = presets.PRESETS[name]["label"]
    logbook.info("settings", "web: preset %s", name)
    return True, (f"{label}: {len(done)} settings changed"
                  + (f", {later} after a restart" if later else "")), None


# ---------------------------------------------------------------------------
# The page (livefeed.add_page)
# ---------------------------------------------------------------------------
def handle(method, sub, body, key=None):
    """(status, content type, body) for /settings/<sub>."""
    sub = sub or "/"

    if method == "GET" and sub == "/":
        return 200, "text/html; charset=utf-8", PAGE.replace("__KEY__", KEY)

    if method == "GET" and sub == "/api":
        return 200, "application/json", json.dumps(listing())

    if method == "POST" and sub == "/api":
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = None
        if not isinstance(data, dict) or not secrets.compare_digest(str(data.get("key", "")), KEY):
            return 403, "application/json", json.dumps({"ok": False, "message": "this page is out of date - reload it"})

        action = data.get("action")
        if action == "set":
            ok, message, item = change(data.get("path"), data.get("value"))
        elif action == "reset":
            ok, message, item = reset(data.get("path"))
        elif action == "preset":
            ok, message, item = preset(str(data.get("name", "")))
        else:
            ok, message, item = False, "unknown action", None

        return (200 if ok else 400), "application/json", json.dumps({"ok": ok, "message": message, "entry": item})

    return 404, "text/plain; charset=utf-8", "not found"


def register():
    import livefeed

    livefeed.add_page(NAME, "settings", lambda method, sub, body: handle(method, sub, body))


def url():
    import livefeed

    return livefeed.url() + "/settings/"


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Luna, settings</title>
<style>
:root{--bg:#0e0a16;--panel:#161021;--line:#2c2140;--text:#e6dcff;--dim:#9a8dbb;--accent:#c49dff;--pink:#ff8fd0;--ok:#7fe0a8;--warn:#ffcf7a;--bad:#ff8a8a}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:#0e0a16f2;backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 20px 12px}
.top{display:flex;align-items:center;gap:14px;flex-wrap:wrap;max-width:980px;margin:0 auto}
h1{font-size:17px;margin:0;color:var(--pink);letter-spacing:.3px}
h1 small{color:var(--dim);font-weight:400;font-size:13px;margin-left:6px}
.search{flex:1;min-width:200px}
.search input{width:100%;padding:8px 12px;background:var(--panel);border:1px solid var(--line);border-radius:8px;color:var(--text);font:inherit}
.search input:focus{outline:none;border-color:var(--accent)}
.seg{display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{background:none;border:0;color:var(--dim);padding:7px 12px;font:inherit;cursor:pointer}
.seg button.on{background:var(--accent);color:#14081c}
main{max-width:980px;margin:0 auto;padding:16px 20px 90px}
.presets{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:22px}
.preset{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:6px}
.preset b{color:var(--accent);display:flex;justify-content:space-between;align-items:center}
.preset b em{font-style:normal;font-weight:400;font-size:11px;color:#14081c;background:var(--ok);border-radius:999px;padding:1px 8px}
.preset.on{border-color:var(--ok)}
.preset p{margin:0;color:var(--dim);font-size:13px;flex:1}
.preset button{align-self:flex-start;background:none;border:1px solid var(--accent);color:var(--accent);border-radius:6px;padding:4px 12px;cursor:pointer;font:inherit}
.preset button:hover{background:var(--accent);color:#14081c}
section{scroll-margin-top:80px;margin-bottom:14px;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
section>h2{margin:0;font-size:14px;padding:10px 14px;cursor:pointer;display:flex;justify-content:space-between;user-select:none}
section>h2 span{color:var(--dim);font-weight:400}
section.closed .rows{display:none}
.row{display:grid;grid-template-columns:minmax(150px,230px) 1fr auto;grid-template-areas:"name ctl reset" "help help help";gap:6px 16px;padding:10px 14px;border-top:1px solid var(--line);align-items:center}
.row .name{grid-area:name}.row .ctl{grid-area:ctl}.row .reset{grid-area:reset}
.row .name{font-family:ui-monospace,"Cascadia Mono",monospace;font-size:13px;word-break:break-all}
.row .name i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--ok);margin-left:6px;vertical-align:middle}
.row .help{grid-area:help;color:var(--dim);font-size:12.5px;margin-top:-4px}
mark{background:#c49dff40;color:inherit;border-radius:3px;padding:0 1px}
section>h2 .after{color:var(--warn);font-size:11.5px;font-weight:400;margin-left:8px}
.jump{background:var(--panel);border:1px solid var(--line);color:var(--text);border-radius:8px;padding:7px 9px;font:inherit;max-width:180px}
.count{color:var(--dim);font-size:12.5px;margin:0 0 10px 2px}
.row .tag{font-size:11px;color:var(--warn);margin-left:6px}
.ctl{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ctl input[type=text],.ctl input[type=number],.ctl input[type=password],.ctl select{background:#0e0a16;border:1px solid var(--line);color:var(--text);border-radius:6px;padding:6px 9px;font:inherit;min-width:0}
.ctl input[type=text],.ctl input[type=password]{width:min(360px,100%)}
.ctl input[type=number]{width:110px}
.ctl input[type=range]{width:220px;accent-color:var(--accent)}
.ctl output{font-family:ui-monospace,monospace;color:var(--accent);min-width:40px}
.ctl .note{color:var(--dim);font-size:12.5px}
.sw{position:relative;width:42px;height:24px;flex:none}
.sw input{opacity:0;width:0;height:0}
.sw span{position:absolute;inset:0;background:#2c2140;border-radius:24px;cursor:pointer;transition:.15s}
.sw span:before{content:"";position:absolute;width:18px;height:18px;left:3px;top:3px;background:#cfc4ea;border-radius:50%;transition:.15s}
.sw input:checked+span{background:var(--accent)}
.sw input:checked+span:before{transform:translateX(18px);background:#14081c}
.sw input:focus-visible+span,.reset:focus-visible,.seg button:focus-visible,.preset button:focus-visible{outline:2px solid var(--pink);outline-offset:2px}
.row{transition:background .6s}
.row.saved{background:#1f3a2c;transition:none}
.row.failed{background:#3a1f26;transition:none}
section>h2 em{font-style:normal;color:var(--ok);font-weight:400;font-size:12px;margin-left:8px}
.reset{background:none;border:0;color:var(--dim);cursor:pointer;font-size:15px;padding:2px 6px;visibility:hidden}
.row.isset .reset{visibility:visible}
.reset:hover{color:var(--pink)}
.empty{color:var(--dim);text-align:center;padding:40px}
#toast{position:fixed;left:50%;bottom:58px;z-index:10;transform:translateX(-50%);background:#241a38;border:1px solid var(--line);padding:9px 16px;border-radius:8px;opacity:0;transition:opacity .2s;pointer-events:none;max-width:90vw}
#toast.show{opacity:1} #toast.bad{border-color:var(--bad);color:var(--bad)}
@media (max-width:640px){
  header{padding:10px 12px}.top{gap:8px}h1 small{display:none}.search{order:3;flex-basis:100%}
  .seg button{padding:6px 10px}.jump{max-width:120px}
  main{padding:12px 12px 90px}
  .presets{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:4px}
  .preset{flex:0 0 80%;scroll-snap-align:start}
  .row{grid-template-columns:1fr auto;grid-template-areas:"name reset" "ctl ctl" "help help"}
  .ctl input[type=range]{flex:1;width:auto}
}
</style></head>
<body>
<header><div class="top">
<h1>Luna <small>settings</small></h1>
<div class="search"><input id="q" type="search" placeholder="Search all settings: name or what it does" autocomplete="off"></div>
<div class="seg"><button id="vb" class="on">Everyday</button><button id="va">All</button><button id="vc" title="Only what you've set in config.json">Changed</button></div>
<select class="jump" id="jump" title="Jump to a section" hidden></select>
</div></header>
<main>
<div class="presets" id="presets"></div>
<div class="count" id="count"></div>
<div id="list"></div>
</main>
<div id="toast"></div>
<script>
const KEY = "__KEY__";
let data = null, view = "basic", query = "", closed = new Set();
try { closed = new Set(JSON.parse(localStorage.getItem("luna.settings.closed") || "[]")); } catch (e) {}
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function toast(text, bad) {
  const t = $("#toast"); t.textContent = text; t.className = "show" + (bad ? " bad" : "");
  clearTimeout(toast.t); toast.t = setTimeout(() => t.className = "", 2600);
}

async function load() {
  const r = await fetch("api", {cache: "no-store"});
  data = await r.json();
  presets(); render();
}

async function send(body) {
  const r = await fetch("api", {method: "POST", headers: {"Content-Type": "application/json"},
                                body: JSON.stringify(Object.assign({key: KEY}, body))});
  let out = {};
  try { out = await r.json(); } catch (e) { out = {ok: false, message: "no answer from Luna"}; }
  return out;
}

function presets() {
  $("#presets").innerHTML = data.presets.map(p =>
    `<div class="preset${p.active ? " on" : ""}"><b>${esc(p.label)}${p.active ? "<em>in use</em>" : ""}</b><p>${esc(p.about)}</p>
     <button data-preset="${esc(p.name)}" title="${esc(Object.entries(p.values).map(([k, v]) => k + " = " + v).join("\n"))}">Use ${esc(p.label)} · ${p.count} settings</button></div>`).join("");
}

function control(s) {
  const id = "c_" + s.path.replace(/[^a-z0-9]/gi, "_");
  if (s.kind === "bool")
    return `<label class="sw"><input type="checkbox" id="${id}" data-path="${esc(s.path)}" ${s.value ? "checked" : ""}><span></span></label>`;
  if (s.kind === "choice" && s.choices.length)
    return `<select id="${id}" data-path="${esc(s.path)}">` +
      (s.choices.some(c => String(c).toLowerCase() === String(s.value).toLowerCase()) ? "" : `<option selected disabled>${esc(s.value ?? "choose")}</option>`) +
      s.choices.map(c =>
      `<option ${String(c).toLowerCase() === String(s.value).toLowerCase() ? "selected" : ""}>${esc(c)}</option>`).join("") + `</select>`;
  if (s.kind === "dict")
    return `<span class="note">${s.has ? s.has + " entries, edited" : "Edited"} in config.json (a nested block)</span>`;
  if (s.kind === "secret")
    return `<input type="password" id="${id}" data-path="${esc(s.path)}" placeholder="${s.has ? "set (hidden) - type to replace" : "not set"}" autocomplete="off">`;
  if (s.range && typeof s.value === "number")
    return `<input type="range" id="${id}" data-path="${esc(s.path)}" min="${s.range[0]}" max="${s.range[1]}" step="${s.range[2]}" value="${s.value}"><output>${s.value}</output>`;
  if (s.kind === "int" || s.kind === "float")
    return `<input type="number" id="${id}" data-path="${esc(s.path)}" step="${s.kind === "int" ? 1 : "any"}" value="${esc(s.value ?? "")}">`;
  const v = Array.isArray(s.value) ? s.value.join(", ") : (s.value ?? "");
  return `<input type="text" id="${id}" data-path="${esc(s.path)}" value="${esc(v)}" placeholder="${s.kind === "list" ? "none (comma-separated)" : "not set"}">`;
}

let allRestart = new Set();          // sections where every change waits for a restart: said once, on the heading

function hl(text) {
  // the search words marked, the rest escaped
  text = String(text ?? "");
  if (!query) return esc(text);
  const lower = text.toLowerCase(), q = query.toLowerCase();
  let out = "", at = 0, i;
  while ((i = lower.indexOf(q, at)) >= 0) { out += esc(text.slice(at, i)) + "<mark>" + esc(text.slice(i, i + q.length)) + "</mark>"; at = i + q.length; }
  return out + esc(text.slice(at));
}

function row(s) {
  const tag = s.live || allRestart.has(s.group) ? "" : '<span class="tag" title="takes effect after a restart">↻ restart</span>';
  return `<div class="row${s.set ? " isset" : ""}" data-row="${esc(s.path)}">
    <div class="name" title="${esc(s.path)}">${hl(s.name)}${s.set ? '<i title="set in config.json"></i>' : ""}${tag}</div>
    <div class="ctl">${control(s)}</div>
    <button class="reset" data-reset="${esc(s.path)}" title="Back to the default">↺</button>
    ${s.help ? `<div class="help">${hl(s.help)}</div>` : ""}</div>`;
}

function render() {
  if (!data) return;
  const q = query.toLowerCase();
  let html = "", shown = 0, sections = [];
  allRestart = new Set(data.groups.filter(g => g.settings.every(s => !s.live)).map(g => g.key));
  for (const g of data.groups) {
    const rows = g.settings.filter(s => q ? (s.path.toLowerCase().includes(q) || s.help.toLowerCase().includes(q))
                                          : view === "all" ? true : view === "changed" ? s.set : s.basic);
    if (!rows.length) continue;
    shown += rows.length;
    const shut = !q && view !== "changed" && closed.has(g.key);
    const changed = rows.filter(s => s.set).length;
    const after = allRestart.has(g.key) ? '<span class="after" title="every setting here takes effect after a restart">↻ after a restart</span>' : "";
    sections.push(g);
    html += `<section class="${shut ? "closed" : ""}" data-group="${esc(g.key)}" id="s_${esc(g.key)}"><h2><div>${esc(g.title)}${changed && view !== "changed" ? `<em>${changed} set</em>` : ""}${after}</div> <span>${rows.length}</span></h2>
             <div class="rows">${rows.map(row).join("")}</div></section>`;
  }
  $("#list").innerHTML = html || `<div class="empty">${query ? `Nothing matches "${esc(query)}".` : "Nothing set in config.json yet: everything is at its default."}</div>`;
  // presets are for browsing, not for a search or the list of your changes
  $("#presets").hidden = !!query || view === "changed";
  $("#count").textContent = query ? `${shown} setting${shown === 1 ? "" : "s"} match` : view === "changed" ? `${shown} set in config.json` : "";
  const jump = $("#jump");
  jump.hidden = view !== "all" || !!query;      // the long list is the one worth jumping around
  jump.innerHTML = `<option value="">Jump to…</option>` + sections.map(g => `<option value="${esc(g.key)}">${esc(g.title)}</option>`).join("");
}

function update(entry) {
  for (const g of data.groups) {
    const i = g.settings.findIndex(s => s.path === entry.path);
    if (i >= 0) g.settings[i] = entry;
  }
  // a preset stays "in use" only while every one of its values still holds
  const now = {};
  for (const g of data.groups) for (const s of g.settings) now[s.path] = s.value;
  for (const p of data.presets) p.active = Object.entries(p.values).every(([k, v]) => now[k] === v);
  presets();
  const old = document.querySelector(`[data-row="${CSS.escape(entry.path)}"]`);
  if (old) old.outerHTML = row(entry);
}

function flash(path, good) {
  const el = document.querySelector(`[data-row="${CSS.escape(path)}"]`);
  if (!el) return;
  el.classList.add(good ? "saved" : "failed");
  requestAnimationFrame(() => setTimeout(() => el.classList.remove("saved", "failed"), 60));
}

async function save(path, value) {
  const out = await send({action: "set", path, value});
  if (out.entry) update(out.entry);
  flash(path, out.ok);
  toast(out.ok ? `${path}: ${out.message}` : out.message, !out.ok);
  if (!out.ok) setTimeout(load, 900);
}

$("#list").addEventListener("change", e => {
  const el = e.target, path = el.dataset.path;
  if (!path) return;
  if (el.type === "checkbox") save(path, el.checked);
  else if (el.type === "range" || el.type === "number") { if (el.value !== "") save(path, el.value); }
  else if (el.type === "password") { if (el.value) save(path, el.value); }
  else save(path, el.value);
});
$("#list").addEventListener("input", e => {
  if (e.target.type === "range") e.target.nextElementSibling.textContent = e.target.value;
});
$("#list").addEventListener("click", async e => {
  const h = e.target.closest("section > h2");
  if (h) {
    const key = h.parentElement.dataset.group;
    h.parentElement.classList.toggle("closed");
    closed.has(key) ? closed.delete(key) : closed.add(key);
    try { localStorage.setItem("luna.settings.closed", JSON.stringify([...closed])); } catch (err) {}
    return;
  }
  const r = e.target.closest("[data-reset]");
  if (r) {
    const out = await send({action: "reset", path: r.dataset.reset});
    if (out.entry) update(out.entry);
    toast(out.ok ? `${r.dataset.reset}: ${out.message}` : out.message, !out.ok);
  }
});
$("#presets").addEventListener("click", async e => {
  const b = e.target.closest("[data-preset]");
  if (!b) return;
  const p = data.presets.find(x => x.name === b.dataset.preset);
  if (p && !confirm(`${p.label} changes ${p.count} settings:\n\n` +
                    Object.entries(p.values).map(([k, v]) => `  ${k} = ${v}`).join("\n"))) return;
  const out = await send({action: "preset", name: b.dataset.preset});
  toast(out.message, !out.ok);
  load();
});
$("#q").addEventListener("input", e => { query = e.target.value.trim(); render(); });
$("#jump").addEventListener("change", e => {
  const s = document.getElementById("s_" + e.target.value);
  if (s) { s.classList.remove("closed"); s.scrollIntoView({behavior: "smooth", block: "start"}); }
  e.target.value = "";
});
const views = [["#vb", "basic"], ["#va", "all"], ["#vc", "changed"]];
for (const [id, v] of views)
  $(id).addEventListener("click", () => { view = v; for (const [i, w] of views) $(i).classList.toggle("on", w === v); render(); });
load();
</script>
</body></html>
"""
