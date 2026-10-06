"""Shared plumbing for the injection experiments: where things are, and a
private llama-server that can be restarted with a control vector in it.

llama-server only takes control vectors at startup - there is no API to
switch one on mid-run - so every condition in an experiment is its own
short-lived server. Luna's own server has to be stopped first: the 16 GB
card holds one copy of the model, not two.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLAMA = os.path.join(ROOT, "llama")
HERE = os.path.dirname(os.path.abspath(__file__))
VECTORS = os.path.join(HERE, "vectors")
RESULTS = os.path.join(HERE, "results")

PORT = 8086          # not Luna's 8080, so a forgotten experiment can't pose as her
HOST = "127.0.0.1"


def env():
    """llama/server.env as a dict - the same file start.sh sources."""
    out = {}

    with open(os.path.join(LLAMA, "server.env")) as f:
        for line in f:
            m = re.match(r"\s*([A-Z_]+)=(.*)", line)

            if m:
                words = shlex.split(m.group(2), comments=True)
                out[m.group(1)] = words[0] if words else ""

    return out


def model_path():
    """The chat model, found the way start.sh finds it."""
    e = env()

    if e.get("MODEL"):
        return e["MODEL"]

    import fnmatch

    pattern = (e.get("MODEL_MATCH") or "*defiant*fable*") + ".gguf"
    roots = [os.path.join(LLAMA, "models"),
             os.path.expanduser("~/.lmstudio/models"),
             os.path.expanduser("~/.cache/lm-studio/models"),
             os.path.expanduser("~/.var/app/ai.lmstudio.lm-studio/.lmstudio/models")]
    found = []

    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            if dirpath[len(root):].count(os.sep) > 5:
                continue

            found += [os.path.join(dirpath, f) for f in files
                      if fnmatch.fnmatch(f.lower(), pattern.lower()) and "mmproj" not in f.lower()]

    if len(found) != 1:
        sys.exit(f"Need exactly one model matching {pattern}, found {len(found)} - "
                 "set MODEL= in llama/server.env.")

    return found[0]


def binary(name):
    path = os.path.join(LLAMA, "bin", name)

    if not os.access(path, os.X_OK):
        sys.exit(f"{name} isn't built - run llama/install.sh (it builds it now).")

    return path


def api_key():
    try:
        with open(os.path.join(LLAMA, ".api_key")) as f:
            return f.read().strip()
    except OSError:
        return ""


def headers():
    key = api_key()

    return {"Authorization": f"Bearer {key}"} if key else {}


def n_layers(path=None):
    """How many layers the model has - read from the GGUF itself, with
    the llama.cpp checkout's own reader. 32 for the 9B if it can't tell."""
    sys.path.insert(0, os.path.join(LLAMA, "llama.cpp", "gguf-py"))

    try:
        import gguf

        reader = gguf.GGUFReader(path or model_path())
        arch = bytes(reader.fields["general.architecture"].parts[-1]).decode()
        field = reader.fields[f"{arch}.block_count"]

        return int(field.parts[field.data[0]][0])
    except Exception:
        return 32


def bands(layers):
    """Early, middle and late thirds, skipping the first couple of
    layers (still mostly reading tokens) and the last (about to write
    them)."""
    if layers < 9:  # too few to split - every band is all of them
        return {k: (1, max(1, layers - 1)) for k in ("early", "middle", "late")}

    a, b = 2, layers - 2
    third = (b - a) // 3

    return {"early": (a, a + third - 1), "middle": (a + third, a + 2 * third - 1),
            "late": (a + 2 * third, b - 1)}


def luna_server_up():
    try:
        return requests.get("http://127.0.0.1:8080/health", timeout=1).ok
    except requests.RequestException:
        return False


class Server:
    """A private llama-server for one condition. Use as a context manager."""

    def __init__(self, vector=None, scale=1.0, layers=None, ctx=4096):
        e = env()
        self.args = [binary("llama-server"), "-m", model_path(), "--host", HOST,
                     "--port", str(PORT), "-c", str(ctx), "-np", "1",
                     "-ngl", e.get("NGL", "99"), "-t", e.get("THREADS", "8"),
                     "--jinja", "--reasoning-format", "deepseek", "-fa", "auto",
                     "--cors-origins", "localhost", "--no-webui"]

        if api_key():
            self.args += ["--api-key-file", os.path.join(LLAMA, ".api_key")]

        if vector:
            self.args += ["--control-vector-scaled", f"{vector}:{scale}"]

            if layers:
                self.args += ["--control-vector-layer-range", str(layers[0]), str(layers[1])]

        self.proc = None

    def __enter__(self):
        self.log = open(os.path.join(RESULTS, "server.log"), "a")
        self.proc = subprocess.Popen(self.args, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + 180

        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("llama-server exited while loading - see introspection/results/server.log")

            try:
                if requests.get(f"http://{HOST}:{PORT}/health", timeout=1).ok:
                    return self
            except requests.RequestException:
                pass

            time.sleep(0.5)

        raise RuntimeError("llama-server didn't come up in 3 minutes")

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                self.proc.kill()

        self.log.close()

    def chat(self, messages, **params):
        body = dict(messages=messages, **params)
        r = requests.post(f"http://{HOST}:{PORT}/v1/chat/completions",
                          json=body, headers=headers(), timeout=300)
        r.raise_for_status()

        return r.json()["choices"][0]


def persona():
    """Luna as she is in agent/agent.json - the experiments ask *her*."""
    try:
        with open(os.path.join(ROOT, "agent", "agent.json")) as f:
            agent = json.load(f)
    except (OSError, ValueError):
        agent = {}

    name = agent.get("name") or "Luna"
    who = agent.get("personality") or ""

    return name, f"You are {name}. {who}".strip()


os.makedirs(VECTORS, exist_ok=True)
os.makedirs(RESULTS, exist_ok=True)
