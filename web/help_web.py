"""The help as a page: every command and key, at /help/ on the live
monitor (the launcher pane's Help, or /help). It replaced the help pane in
the terminal; the words are still ui/help.py's.
"""
import html

NAME = "help"


def page():
    from ui import help as helptext

    out = []
    for title, rows in helptext.sections():
        out.append(f"<section><h2>{html.escape(title)}</h2>")
        for entry in rows:
            if isinstance(entry, str):
                out.append(f"<p class=note>{html.escape(entry.strip()) or '&nbsp;'}</p>")
            else:
                key, what = entry
                cls = "key" if key.startswith("(") else "cmd"
                out.append(f"<div class=row><code class={cls}>{html.escape(key)}</code>"
                           f"<span>{html.escape(what)}</span></div>")
        out.append("</section>")
    return _PAGE.replace("__BODY__", "".join(out))


def handle(method, sub, body):
    if method == "GET" and (sub or "/") == "/":
        return 200, "text/html; charset=utf-8", page()
    return 404, "text/plain; charset=utf-8", "not found"


def register():
    from web import livefeed

    livefeed.add_page(NAME, "help", lambda method, sub, body: handle(method, sub, body))


def url():
    from web import livefeed

    return f"{livefeed.url()}/{NAME}/"


_PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Luna, help</title><style>
:root{--bg:#0e0a16;--panel:#161021;--line:#2c2140;--text:#e6dcff;--dim:#9a8dbb;--accent:#c49dff;--pink:#ff8fd0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:900px;margin:0 auto;padding:24px 18px 60px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--dim);margin:0 0 18px}
input{width:100%;padding:9px 12px;border-radius:8px;border:1px solid var(--line);background:var(--panel);
color:var(--text);font:inherit;margin-bottom:16px}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:0 0 12px}
h2{font-size:15px;color:var(--accent);margin:0 0 8px}
.row{display:flex;gap:14px;padding:3px 0}
.row code{flex:0 0 190px;color:var(--pink);font:13px ui-monospace,monospace}
.row code.key{color:var(--accent)}
.note{color:var(--dim);margin:0;font-size:13px;white-space:pre-wrap}
@media(max-width:600px){.row{flex-direction:column;gap:0}.row code{flex:none}}
</style></head><body><main>
<h1>Luna: commands and keys</h1>
<p class=sub>Type these in her terminal. Most of what she does needs no command at all: just ask.</p>
<input id=q placeholder="search" autofocus>
__BODY__
</main><script>
const q = document.getElementById('q');
q.oninput = () => {
  const t = q.value.toLowerCase();
  for (const s of document.querySelectorAll('section')) {
    let any = false;
    for (const r of s.querySelectorAll('.row,.note')) {
      const hit = !t || r.textContent.toLowerCase().includes(t) || s.querySelector('h2').textContent.toLowerCase().includes(t);
      r.hidden = !hit; any = any || hit;
    }
    s.hidden = !any;
  }
};
</script></body></html>"""
