"""Luna, download and go: what the Luna launchers (Luna.sh, Luna.command,
Luna.cmd) run once uv has made her a private Python.

First run (or after an update changes her packages): a small Luna-styled
setup window shows installer/install.py working, step by step, then she
starts. Later runs go straight to her (launch.py --web).

Standard library only: this runs before any of her packages are installed.

    python app/bootstrap.py            set up if needed, then start her
    python app/bootstrap.py --setup    run the setup again (repair)
    python app/bootstrap.py --no-window  print the setup page's address instead of opening it
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WIN = os.name == "nt"
MAC = sys.platform == "darwin"

# The installer's steps, in the order it runs them, so the page can show
# what's coming and a bar. A step it skips just never lights up.
STEPS = ["Checking this machine", "System packages", "Luna's Python environment",
         "Her voice (kokoro-reader)", "Her brain (the model server)", "Her model",
         "Launchers", "Health check"]
# The first run leaves the model to the Connect card in her window
INSTALL_ARGS = ["--yes", "--no-system", "--backend", "skip", "--model", "skip"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def data_dir():
    """Luna's own folder for the launcher's things: uv, its Python, this
    log. Her settings and memories stay in her own folder, as always."""
    if WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        path = os.path.join(base, "Luna")
    elif MAC:
        path = os.path.expanduser("~/Library/Application Support/Luna")
    else:
        path = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "luna")
    os.makedirs(path, exist_ok=True)
    return path


DATA = data_dir()
MARK = os.path.join(DATA, "setup.json")
LOG = os.path.join(DATA, "setup.log")


def fingerprint():
    """What decides whether setup has to run again: her package list and the
    installer itself. An update that changes either sets it up again."""
    h = hashlib.sha256()
    for rel in ("installer/requirements.txt", "installer/install.py"):
        try:
            with open(os.path.join(ROOT, rel), "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    h.update(ROOT.encode())
    return h.hexdigest()[:16]


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def her_python():
    """The Python her packages went into (install.json remembers it)."""
    py = load(os.path.join(ROOT, "install.json")).get("venv_python")
    return py if py and os.path.exists(py) else None


def needs_setup():
    return load(MARK).get("fingerprint") != fingerprint() or not her_python()


# ---------------------------------------------------------------------------
# What the setup page shows
# ---------------------------------------------------------------------------
class Progress:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        """A fresh page (a first run, or Try again). Keeps the lock: the page
        may be reading under it right now."""
        self.ended = None              # when it finished or failed: the clock stops
        self.steps = [{"title": t, "state": "todo", "lines": []} for t in STEPS]
        self.log = []                  # every line, for "show details"
        self.phase = "setup"           # setup | starting | ready | failed
        self.message = "Getting Luna ready..."
        self.ready_url = ""
        self.missing = []              # system packages to install by hand: (what, command)
        self.started = time.time()

    def snapshot(self):
        """The status as JSON, made under the lock: the installer's thread
        changes these lists as it goes."""
        with self.lock:
            return json.dumps({"steps": self.steps, "log": self.log[-400:], "log_total": len(self.log),
                               "phase": self.phase, "message": self.message, "ready_url": self.ready_url,
                               "missing": self.missing, "log_path": LOG,
                               "elapsed": int((self.ended or time.time()) - self.started)})

    def current(self):
        return next((s for s in reversed(self.steps) if s["state"] == "doing"), None)

    def line(self, raw):
        """One line of the installer's output."""
        text = ANSI.sub("", raw.rstrip("\r\n"))
        with self.lock:
            self.log.append(text)
            stripped = text.strip()
            if stripped.startswith("== "):
                title = stripped[3:].strip()
                if title == "Summary":
                    self._finish_current()
                    return
                self._finish_current()
                step = next((s for s in self.steps if s["title"] == title), None)
                if step is None:           # a step this list doesn't know (Extras, Live2D...)
                    step = {"title": title, "state": "todo", "lines": []}
                    done = [i for i, s in enumerate(self.steps) if s["state"] != "todo"]
                    self.steps.insert(done[-1] + 1 if done else 0, step)
                step["state"] = "doing"
                self.message = title
                return
            step = self.current()
            if not step or not stripped:
                return
            mark = stripped[:1]
            if mark in "✓!✗":
                kind = {"✓": "ok", "!": "warn", "✗": "fail"}[mark]
                step["lines"].append({"kind": kind, "text": stripped[1:].strip()})
                if kind == "fail":
                    step["bad"] = True
                elif kind == "warn":
                    step["warned"] = True
                if step["title"] == "System packages" and kind == "warn":
                    self._missing(stripped[1:].strip())

    def _missing(self, text):
        """--no-system: the installer says what's missing and the command for it."""
        self.missing.append(text)

    def _finish_current(self):
        step = self.current()
        if step:
            step["state"] = ("bad" if step.get("bad") else "warn" if step.get("warned")
                             else "done" if step["lines"] else "skip")

    def set(self, **kw):
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, v)
            if self.phase in ("ready", "failed") and self.ended is None:
                self.ended = time.time()

    def retry(self):
        """Try again, once: a second click while it starts does nothing."""
        with self.lock:
            if self.phase != "failed":
                return False
            self.phase = "setup"
        return True


P = Progress()


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

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "progress.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/logo.png":
            with open(os.path.join(ROOT, "web", "luna-logo.png"), "rb") as f:
                self._send(200, f.read(), "image/png")
        elif path == "/status":
            self._send(200, P.snapshot())
        else:
            self._send(404, "{}")

    def do_POST(self):
        if self.path == "/retry" and P.retry():
            threading.Thread(target=work, daemon=True).start()
            self._send(200, "{}")
        elif self.path == "/quit":
            self._send(200, "{}")
            threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
        else:
            self._send(404, "{}")


# ---------------------------------------------------------------------------
# The work
# ---------------------------------------------------------------------------
def write_log(text):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


def install_args():
    """INSTALL_ARGS, keeping the choices an earlier install made: a voice
    on another machine, or none, stays that way (the installer's default
    would set one up here)."""
    args = list(INSTALL_ARGS)
    v = load(os.path.join(ROOT, "install.json")).get("voice") or {}
    if v.get("mode") == "external" and v.get("url"):
        args += ["--voice", "url:" + v["url"]]
    elif v.get("mode") == "none":
        args += ["--voice", "skip"]
    return args


def run_installer():
    """installer/install.py, unattended, its output fed to the page. True
    when it got her a Python with her packages in it."""
    py = sys.executable
    if WIN and os.path.basename(py).lower() == "pythonw.exe":
        # the launcher runs this windowless; the installer's output wants a console Python (hidden)
        py = os.path.join(os.path.dirname(py), "python.exe")
    cmd = [py, "-u", os.path.join(ROOT, "installer", "install.py"), *install_args()]
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", NO_COLOR="1", LUNA_APP="1")
    env.pop("WT_SESSION", None)                       # no colours: it's going to a page, not a terminal
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        env["VIRTUAL_ENV"] = sys.prefix               # the installer reuses the venv this runs in
    write_log(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} setup: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1,
                                **({"creationflags": subprocess.CREATE_NO_WINDOW} if WIN else {}))
    except OSError as e:
        P.line(f"  ✗ couldn't start the installer: {e}")
        return False
    for raw in proc.stdout:
        write_log(raw.rstrip("\n"))
        P.line(raw)
    proc.wait()
    P.line("== Summary")
    return proc.returncode == 0 and her_python() is not None


def monitor_url():
    """Where her pages are served (config.json's monitor.port)."""
    port = 8792
    for name in ("config.json", "config.example.json"):
        try:
            port = int((load(os.path.join(ROOT, name)).get("monitor") or {}).get("port", port))
            break
        except (TypeError, ValueError):
            continue
    return f"http://127.0.0.1:{port}"


def answers(url):
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def start_luna(py):
    """launch.py --web: she goes off on her own and opens her chat window."""
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if WIN else {"start_new_session": True}
    return subprocess.Popen([py, os.path.join(ROOT, "launch.py"), "--web"], cwd=ROOT,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **flags)


def remember(key, value):
    """Note something the setup made in install.json, the installer's record,
    so installer/uninstall.py can take it away again."""
    path = os.path.join(ROOT, "install.json")
    state = load(path)
    state[key] = value
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass


def menu_entry():
    """Luna in the app menu (Linux) or the Start menu (Windows), once she's
    set up, so the launcher needn't be found again."""
    try:
        if WIN:
            menu = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu",
                                "Programs", "Luna.lnk")
            target = os.path.join(HERE, "Luna.cmd")
            icon = os.path.join(HERE, "luna.ico")
            ps = (f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{menu}");'
                  f'$s.TargetPath="{target}";$s.WorkingDirectory="{ROOT}";$s.WindowStyle=7;'
                  + (f'$s.IconLocation="{icon}";' if os.path.exists(icon) else "") + "$s.Save()")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
            if os.path.exists(menu):
                remember("shortcut", menu)
        elif not MAC:
            apps = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
                                "applications")
            os.makedirs(apps, exist_ok=True)
            with open(os.path.join(apps, "luna.desktop"), "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nType=Application\nName=Luna\nComment=Local AI companion\n"
                        f"Exec=\"{os.path.join(HERE, 'luna.sh')}\"\nPath={ROOT}\n"
                        f"Icon={os.path.join(ROOT, 'web', 'luna-logo.png')}\n"
                        "Terminal=false\nCategories=Utility;Chat;\nStartupNotify=false\n")
            remember("desktop", os.path.join(apps, "luna.desktop"))
    except (OSError, subprocess.SubprocessError):
        pass


def work():
    with P.lock:
        P.reset()
    if not run_installer():
        bad = [s["title"] for s in P.steps if s["state"] == "bad"]
        P.set(phase="failed", message="Setup didn't finish" + (f" ({', '.join(bad)})" if bad else "")
              + ". The details below say why.")
        return
    with open(MARK, "w", encoding="utf-8") as f:
        json.dump({"fingerprint": fingerprint(), "root": ROOT, "when": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    menu_entry()
    P.set(phase="starting", message="All set. Starting Luna...")
    url = monitor_url() + "/chat/"
    start_luna(her_python())           # already running: it opens her window instead
    for _ in range(240):                        # her first start loads the speech models
        if answers(url + "state"):
            P.set(phase="ready", message="Luna's up.", ready_url=url)
            return
        time.sleep(0.5)
    base = os.environ.get("LOCALAPPDATA") if WIN else os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    P.set(phase="failed", message="She was set up but didn't start. Her log says why: "
          + os.path.join(base or os.path.expanduser("~"), "ai-voice", "web.log"))


def open_window(url):
    """The setup page in a small window of its own (no address bar) when a
    Chromium-style browser or Firefox is there, else a browser tab."""
    sys.path.insert(0, ROOT)
    try:
        from web import portrait_window
        cmd = portrait_window.command(url, 620, 720, profile="luna-setup")
    except Exception:
        cmd = None
    if cmd:
        try:
            return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL,
                                    **({"creationflags": subprocess.CREATE_NO_WINDOW} if WIN
                                       else {"start_new_session": True}))
        except OSError:
            pass
    import webbrowser
    webbrowser.open(url)
    return None


def setup(show=True):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    window = open_window(url) if show else None
    opened = time.time()
    if not show:
        print(f"Setup page: {url}", flush=True)

    # Stay while the page needs us: until she's up (then close our window,
    # hers is open), or the setup window closes, or a while after a failure.
    while True:
        time.sleep(0.5)
        if window is not None and window.poll() is not None and time.time() - opened < 5:
            window = None                       # closed at once: handed to a browser already open, now a tab
        if P.phase == "ready":
            time.sleep(4)                       # long enough for the page to say so
            if window is not None and window.poll() is None:
                window.terminate()
            return 0
        if window is not None and window.poll() is not None and P.phase != "setup":
            return 1                            # closed after a failure
        if P.phase == "failed" and window is None and time.time() - (P.ended or time.time()) > 3600:
            return 1


def main():
    args = sys.argv[1:]
    if "--setup" in args or needs_setup():
        sys.exit(setup(show="--no-window" not in args))
    py = her_python()
    # launch.py --web opens her window, or brings it back if she's already running
    proc = start_luna(py)
    sys.exit(0 if proc else 1)


if __name__ == "__main__":
    main()
