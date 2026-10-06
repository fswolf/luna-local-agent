"""Start Luna - and her voice server first, if the installer set one up.

    ./start.sh   /   luna   /   luna.cmd   (they all end up here)

Any arguments are passed on to main.py. The voice server is started
only if it isn't already answering, and stopped again when she exits -
one that was already running before is left alone.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
WIN = os.name == "nt"


def up(url):
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            return r.status < 500
    except Exception:
        return False


def state():
    try:
        with open(os.path.join(ROOT, "install.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def log_dir():
    base = os.environ.get("LOCALAPPDATA") if WIN else os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    path = os.path.join(base or os.path.expanduser("~"), "ai-voice")
    os.makedirs(path, exist_ok=True)
    return path


def start_voice(v):
    """kokoro-reader in the background. Returns the process, or None."""
    port = int(v.get("port", 8899))
    if up(f"http://127.0.0.1:{port}/health"):
        return None
    if not (os.path.exists(v.get("python", "")) and os.path.exists(v.get("server", ""))):
        print("Her voice server isn't where the installer left it - run the installer again.", file=sys.stderr)
        return None
    env = dict(os.environ, KOKORO_HOST="127.0.0.1", KOKORO_PORT=str(port),
               KOKORO_DEVICE=v.get("device", "cpu"))
    if env["KOKORO_DEVICE"] == "cpu":
        env.pop("KOKORO_DEVICE")
    log = open(os.path.join(log_dir(), "kokoro.log"), "a", encoding="utf-8")
    flags = subprocess.CREATE_NO_WINDOW if WIN else 0
    proc = subprocess.Popen([v["python"], v["server"]], cwd=os.path.dirname(v["server"]), env=env,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=flags)
    print("Starting her voice...", end="", flush=True)
    for _ in range(40):            # the model loads on the first start - give it a moment
        if proc.poll() is not None:
            print(f" it stopped - see {log.name}")
            return None
        if up(f"http://127.0.0.1:{port}/health"):
            print(" ready.")
            return proc
        time.sleep(0.5)
        print(".", end="", flush=True)
    print(" still loading (first start downloads the model) - she'll find it when it's up.")
    return proc


def python():
    """The venv's Python: the one the installer made, else whichever runs this."""
    s = state()
    py = s.get("venv_python")
    if py and os.path.exists(py):
        return py
    for cand in (os.environ.get("VIRTUAL_ENV"), os.path.expanduser("~/ai-voice-venv"),
                 os.path.join(ROOT, "ai-voice-venv"), os.path.join(ROOT, "venv"), os.path.join(ROOT, ".venv")):
        if cand:
            p = os.path.join(cand, "Scripts", "python.exe") if WIN else os.path.join(cand, "bin", "python")
            if os.path.exists(p):
                return p
    return sys.executable


def main():
    s = state()
    voice = None
    v = s.get("voice", {})
    if v.get("mode") == "managed":
        voice = start_voice(v)

    warnings = []
    if not (up("http://127.0.0.1:8080/health") or up("http://localhost:1234/v1/models")):
        warnings.append("No model server - open LM Studio's Local Server, or run llama/start.sh.")
    if v.get("mode") != "managed" and not up("http://127.0.0.1:8899/health"):
        if v.get("mode") != "none":
            warnings.append("No voice server on :8899 - she'll start text-only.")
    if warnings:
        print("Starting anyway:\n  " + "\n  ".join(warnings), file=sys.stderr)

    try:
        code = subprocess.call([python(), os.path.join(ROOT, "main.py"), *sys.argv[1:]], cwd=ROOT)
    except KeyboardInterrupt:
        code = 130
    finally:
        if voice and voice.poll() is None:
            voice.terminate()
            try:
                voice.wait(5)
            except subprocess.TimeoutExpired:
                voice.kill()
    sys.exit(code)


if __name__ == "__main__":
    main()
