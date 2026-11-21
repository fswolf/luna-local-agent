"""Connect a model: what her window shows when no model server answers.

Luna thinks with a model on a model server (LM Studio, llama.cpp, Ollama,
vLLM: anything that speaks the OpenAI API), and without one she can't
start. Started with --web (the app, ./start_web.sh), launch.py opens this
instead of quitting: a small page in her window that

- keeps looking where config.json says, and where LM Studio and llama.cpp
  usually are on this computer, and goes on the moment one has a model;
- on Linux and macOS, sets one up here with a click: llama.cpp's ready-made
  release and a model sized for the graphics card (installer/install.py
  --only llama), then starts it;
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


def key_for(what, base):
    """The key Luna herself would send there (config/server.py): for llama.cpp,
    llm.json's on another computer when it has one, else server/llama/.api_key
    (start.sh's, or one copied from the server); for anything else, llm.json's."""
    if what != "llama.cpp":
        return saved_key()
    local = re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:|$)", base)
    return (not local and saved_key()) or llama_key()


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
            out.append((what, base, key_for(what, base)))
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
        # "Set it up for me": idle | running | starting | failed, the step it's on,
        # its last line, what went wrong, and the whole log for "details"
        self.setup = {"state": "idle", "step": "", "line": "", "errors": [], "log": []}
        self.start = None          # wait()'s start: starts the server set up here
        self.server = None         # ...and the process it returned (launch.py stops it)
        self.installer = None      # the installer while it runs (stopped if she goes on without it)

    def snapshot(self):
        with self.lock:
            setup = dict(self.setup, log=self.setup["log"][-300:])
            return json.dumps({"looking": self.looking, "found": self.found, "os": sys.platform,
                               "can_setup": can_setup(), "setup": setup})


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


# ---------------------------------------------------------------------------
# "Set it up for me": llama.cpp and a model on this computer
# ---------------------------------------------------------------------------
def can_setup():
    """llama.cpp's ready-made releases and server/llama/start.sh cover Linux and
    macOS; on Windows it's LM Studio for now."""
    return sys.platform.startswith("linux") or sys.platform == "darwin"


def _local_env_model():
    """The model server/llama/server.local.env points at, when that file is there."""
    try:
        with open(os.path.join(ROOT, "server", "llama", "server.local.env"), encoding="utf-8") as f:
            for line in f:
                m = re.match(r'\s*MODEL\s*=\s*"?([^"\n]*)"?', line)
                if m:
                    return m.group(1).strip()
    except OSError:
        pass
    return ""


def llama_ready():
    """llama.cpp is here and a model for it was downloaded."""
    server = os.path.join(ROOT, "server", "llama", "bin", "llama-server")
    model = _local_env_model()
    return os.path.exists(server) and bool(model) and os.path.exists(model)


def _set(**kw):
    with S.lock:
        S.setup.update(kw)


def run_setup(standard=False):
    """The installer's model-server steps, unattended, fed to the page; then
    point her at it and start it. Runs in a thread of its own."""
    import subprocess

    _set(state="running", step="Starting", line="", errors=[], log=[])
    cmd = [sys.executable, "-u", os.path.join(ROOT, "installer", "install.py"), "--only", "llama", "--yes",
           "--no-system", "--backend", "llama", "--prebuilt", "--model", "auto"] + (["--standard"] if standard else [])
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", NO_COLOR="1")
    env.pop("WT_SESSION", None)
    try:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
    except OSError as e:
        _set(state="failed", errors=[f"couldn't run the installer: {e}"])
        return
    with S.lock:
        S.installer = proc
    for raw in proc.stdout:
        text = re.sub(r"\x1b\[[0-9;]*m", "", raw.rstrip("\r\n"))
        with S.lock:
            S.setup["log"].append(text)
            stripped = text.strip()
            if stripped.startswith("== "):
                if stripped[3:] != "Summary":
                    S.setup["step"], S.setup["line"] = stripped[3:], ""
            elif stripped.startswith("✗"):
                S.setup["errors"].append(stripped[1:].strip())
            elif stripped.startswith("downloading "):
                S.setup["file"] = stripped.rsplit("/", 1)[-1]
                S.setup["line"] = f"downloading {S.setup['file']}"
            elif re.match(r"\d+% of \d+ MB$", stripped) and S.setup.get("file"):
                S.setup["line"] = f"{S.setup['file']}: {stripped}"
            elif stripped:
                S.setup["line"] = stripped.lstrip("✓! ").strip()
    proc.wait()
    with S.lock:
        S.installer = None
        elsewhere = S.found is not None
    if elsewhere:
        # she found another server meanwhile (LM Studio switched on, an address typed): that one stands
        _set(state="done")
        return
    if proc.returncode != 0 or not llama_ready():
        with S.lock:
            if not S.setup["errors"]:
                S.setup["errors"].append("it didn't finish - the details below say why")
            S.setup["state"] = "failed"
        return
    save({"kind": "llama.cpp", "base": "http://127.0.0.1:8080"})
    _set(state="starting", step="Starting the model", line="loading it onto the graphics card...")
    started = S.start() if S.start else None
    with S.lock:
        S.server = started
        if started is None:
            S.setup.update(state="failed", errors=["it's set up, but llama.cpp didn't start: "
                                                   "server/llama/server.log says why"])
        else:
            S.setup["state"] = "done"


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
    if key:
        p = probe(base, key)
    else:
        # nothing typed: the keys she already has, llm.json's then server/llama/.api_key
        for known in dict.fromkeys(k for k in (saved_key(), llama_key(), "") if k is not None):
            p = probe(base, known)
            if not p["needs_key"]:
                break
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
        elif self.path == "/setup":
            try:
                standard = bool(json.loads(body or b"{}").get("standard"))
            except (ValueError, AttributeError):
                standard = False
            with S.lock:
                busy = S.setup["state"] in ("running", "starting")
            if can_setup() and not busy:
                threading.Thread(target=run_setup, args=(standard,), daemon=True, name="connect-setup").start()
            self._send(200, "{}")
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


def wait(show=True, say=print, start=None):
    """Show the page and look until a server with a model answers. True:
    connected (config.json says where), go on and start her. False: "Not
    now", or her window closed. start: starts the model server once "Set it
    up for me" has put one here, returning its process (or None); that
    process is S.server afterwards, for the caller to stop when she exits."""
    S.start = start
    if look_once():
        return True
    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    window = _open(url) if show else None
    opened = time.monotonic()
    say(f"No model server answering - the window asks where one is ({url}).")
    try:
        os.makedirs(os.path.dirname(SHOWING), exist_ok=True)
        with open(SHOWING, "w", encoding="utf-8") as f:
            f.write(url)
    except OSError:
        pass
    try:
        while True:
            if look_once():
                # the server "Set it up" started: its process is handed over once start() returns
                for _ in range(240):
                    with S.lock:
                        if S.setup["state"] != "starting":
                            break
                    time.sleep(0.5)
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
        with S.lock:
            installer = S.installer
        if installer is not None and installer.poll() is None:
            installer.terminate()                   # not needed any more: "Not now", or another server answered
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
