"""Connect a model: what her window shows when no model server answers.

Luna thinks with a model on a model server (LM Studio, llama.cpp, Ollama,
vLLM: anything that speaks the OpenAI API), and without one she can't
start. Started with --web (the app, ./start_web.sh), launch.py opens this
instead of quitting: a small page in her window that

- keeps looking where config.json says, and where LM Studio and llama.cpp
  usually are on this computer, and goes on the moment one has a model;
- says how to get LM Studio going here;
- takes the address of a server on another computer (and its key, when it
  wants one), tries it, and saves it.

What it finds is saved in config.json's llm section (an API key goes in
~/.config/ai-voice/llm.json, outside the repo), so next time she starts
straight away. Standard library only, like launch.py.

    python web/connect.py      the page on its own (prints its address)
"""
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(ROOT, "config.json")
EXAMPLE = os.path.join(ROOT, "config.example.json")
KEYS = os.path.expanduser("~/.config/ai-voice/llm.json")
LLAMA_KEY = os.path.join(ROOT, "server", "llama", ".api_key")
LOOK_EVERY = 2.0
# While the page is up, its address is here: the app's setup window
# (app/bootstrap.py) reads it to know she's waiting on this, not stuck.
SHOWING = os.path.join((os.environ.get("LOCALAPPDATA") if os.name == "nt" else
                        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"))
                       or os.path.expanduser("~"), "ai-voice", "connect.url")
WINDOW = (720, 860)

# Where a model server on this computer usually is: (what, base address)
LOCAL = (("LM Studio", "http://localhost:1234"), ("llama.cpp", "http://127.0.0.1:8080"))


# ---------------------------------------------------------------------------
# config.json and the key file
# ---------------------------------------------------------------------------
def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def llm_settings():
    return (_read(CONFIG) or _read(EXAMPLE)).get("llm") or {}


def saved_key():
    return str(_read(KEYS).get("api_key") or "").strip()


def llama_key():
    """The key server/llama/start.sh made for llama.cpp on this computer."""
    try:
        with open(LLAMA_KEY, encoding="utf-8") as f:
            return next((l.strip() for l in f if l.strip() and not l.startswith("#")), "")
    except OSError:
        return ""


_saving = threading.Lock()      # the look-around and the page's Connect can both find one at once


def save(found, key=""):
    """Point her at what was found: llm.backend and its address in
    config.json (her other settings left as they are), the key outside it."""
    with _saving:
        _save(found, key)


def _save(found, key):
    cfg = _read(CONFIG) if os.path.exists(CONFIG) else _read(EXAMPLE)
    llm = cfg.setdefault("llm", {})
    if not isinstance(llm, dict):
        llm = cfg["llm"] = {}
    chat = found["base"] + "/v1/chat/completions"
    backend, field = ("llama", "llama_url") if found["kind"] == "llama.cpp" else ("lmstudio", "lmstudio_url")
    wanted = str(llm.get("backend", "auto")).lower()
    already = base_of(llm.get(field)) == found["base"] and (wanted == "auto" or wanted.startswith(backend[:2]))
    if not already or not os.path.exists(CONFIG):       # what config.json says finds it already: left alone
        llm["backend"], llm[field] = backend, chat      # (LM Studio, or any other OpenAI-style server)
        tmp = CONFIG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, CONFIG)
    if key:
        keys = _read(KEYS)
        keys["api_key"] = key
        os.makedirs(os.path.dirname(KEYS), exist_ok=True)
        with open(KEYS, "w", encoding="utf-8") as f:
            json.dump(keys, f, indent=2)
        try:
            os.chmod(KEYS, 0o600)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Looking for a server
# ---------------------------------------------------------------------------
def base_of(address):
    """http://host:port from whatever was typed: "192.168.1.50:8080",
    "box", "http://box:1234/v1/chat/completions"... None if it isn't one.
    No port: llama.cpp's 8080."""
    text = str(address or "").strip()
    if not text or any(c.isspace() for c in text):
        return None
    if "://" not in text:
        text = "http://" + text
    m = re.match(r"^(https?)://([^/:?#]+|\[[0-9a-fA-F:]+\])(?::(\d{1,5}))?(?:[/?#].*)?$", text)
    if not m:
        return None
    scheme, host, port = m.groups()
    if port and not 0 < int(port) < 65536:
        return None
    return f"{scheme}://{host}:{port or 8080}"


def _get(url, key="", timeout=3.0):
    """(status, parsed JSON or None). Status 0: nothing answered."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            body = r.read(1 << 20)
            try:
                return r.status, json.loads(body or b"null")
            except ValueError:
                return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


def probe(base, key="", timeout=3.0):
    """What answers at base: {"ok", "kind", "base", "model", "why", "needs_key"}.
    ok only with a model to talk to: a server with nothing loaded can't
    answer her yet."""
    out = {"ok": False, "kind": "", "base": base, "model": "", "why": "", "needs_key": False}
    status, data = _get(base + "/v1/models", key, timeout)
    if status in (401, 403):
        out.update(needs_key=True, why="it wants an API key" if not key else "it didn't take that key")
        return out
    if status != 200 or not isinstance(data, dict):
        out["why"] = "nothing answered there" if status == 0 else f"it answered {status}, not a model list"
        return out
    ids = [m.get("id", "") for m in data.get("data") or [] if isinstance(m, dict) and m.get("id")]
    # llama-server has /props (and wants its key there too); LM Studio has its own API
    if _get(base + "/props", key, timeout)[0] in (200, 401, 403):
        out["kind"] = "llama.cpp"
    elif _get(base + "/api/v0/models", key, timeout)[0] == 200:
        out["kind"] = "LM Studio"
    else:
        out["kind"] = "model server"
    if not ids:
        out["why"] = f"{out['kind']} is running, but no model is loaded yet"
        return out
    pinned = str(llm_settings().get("model") or "").strip()
    if pinned and pinned not in ids:
        # llm.model: she asks for that one or none (core/lmstudio.py), so another won't do
        out["why"] = f"{out['kind']} is running, but doesn't have {pinned} (llm.model in config.json)"
        return out
    out.update(ok=True, model=pinned or ids[0])
    return out


def places():
    """Where to look, in order: config.json's addresses first, then this
    computer's usual ports. [(what, base, key)]"""
    llm, seen, out = llm_settings(), set(), []
    configured = [("llama.cpp", llm.get("llama_url")), ("LM Studio", llm.get("lmstudio_url"))]
    if str(llm.get("backend", "auto")).lower().startswith("lm"):
        configured.reverse()
    for what, url in configured + list(LOCAL):
        base = base_of(url) if url else None
        if base and base not in seen:
            seen.add(base)
            local = re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:|$)", base)
            key = llama_key() if what == "llama.cpp" and local else saved_key()
            out.append((what, base, key))
    return out


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.looking = []          # [{what, base, why}] the last look round
        self.found = None          # probe() of the one she connected to
        self.closed = False        # "Not now"

    def snapshot(self):
        with self.lock:
            return json.dumps({"looking": self.looking, "found": self.found, "os": sys.platform})


S = State()


def use(found, key=""):
    """Save it and tell the page; the caller's wait() sees S.found and goes on."""
    save(found, key)
    with S.lock:
        S.found = found


def look_once():
    seen = []
    for what, base, key in places():
        with S.lock:
            if S.found:
                return True
        p = probe(base, key, timeout=1.5)
        if p["ok"]:
            use(p)                           # a key found with it is already where it came from
            return True
        seen.append({"what": what, "base": base, "why": p["why"]})
    with S.lock:
        S.looking = seen
    return False


def try_address(body):
    """The page's Connect button: {"address", "key"}."""
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        data = {}
    base = base_of(data.get("address"))
    if not base:
        return {"ok": False, "why": "that doesn't look like an address - something like 192.168.1.50:8080"}
    key = str(data.get("key") or "").strip()
    p = probe(base, key or saved_key())
    if p["ok"]:
        use(p, key)
    return p


class Page(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ours(self):
        """Only this page, from this computer (the same rule as her other pages)."""
        here = f"127.0.0.1:{self.server.server_address[1]}"
        origin = self.headers.get("Origin")
        return self.headers.get("Host") == here and (origin is None or origin.split("://", 1)[-1] == here)

    def do_GET(self):
        if not self._ours():
            return self._send(403, "{}")
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "connect.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/logo.png":
            with open(os.path.join(HERE, "luna-logo.png"), "rb") as f:
                self._send(200, f.read(), "image/png")
        elif path == "/status":
            self._send(200, S.snapshot())
        else:
            self._send(404, "{}")

    def do_POST(self):
        if not self._ours():
            return self._send(403, "{}")
        body = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 1 << 16))
        if self.path == "/try":
            self._send(200, json.dumps(try_address(body)))
        elif self.path == "/close":
            with S.lock:
                S.closed = True
            self._send(200, "{}")
        else:
            self._send(404, "{}")


def _open(url):
    """The page in a window of its own, like her chat (web/portrait_window.py)."""
    sys.path.insert(0, ROOT)
    try:
        from web import portrait_window

        cmd = portrait_window.command(url, *WINDOW, profile="luna-connect")
    except Exception:
        cmd = None
    if cmd:
        import subprocess

        try:
            return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL,
                                    **({"creationflags": 0x08000000} if os.name == "nt"
                                       else {"start_new_session": True}))
        except OSError:
            pass
    import webbrowser

    webbrowser.open(url)
    return None


def wait(show=True, say=print):
    """Show the page and look until a server with a model answers. True:
    connected (config.json says where), go on and start her. False: "Not
    now", or her window closed."""
    if look_once():
        return True
    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    window = _open(url) if show else None
    opened = time.monotonic()
    say(f"No model server answering - her window asks where one is ({url}).")
    try:
        os.makedirs(os.path.dirname(SHOWING), exist_ok=True)
        with open(SHOWING, "w", encoding="utf-8") as f:
            f.write(url)
    except OSError:
        pass
    try:
        while True:
            if look_once():
                time.sleep(2.5)                     # long enough for the page to say who she found
                return True
            if S.closed:
                return False
            if window is not None and window.poll() is not None:
                if time.monotonic() - opened < 5:
                    window = None                   # handed to a browser already open: it's a tab now
                else:
                    return False                    # closed: like "Not now"
            time.sleep(LOOK_EVERY)
    finally:
        if window is not None and window.poll() is None:
            window.terminate()
        server.shutdown()
        server.server_close()
        try:
            os.remove(SHOWING)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(0 if wait(show="--no-window" not in sys.argv) else 1)
