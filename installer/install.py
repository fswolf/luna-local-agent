"""Install Luna: Linux, macOS or Windows.

    ./installer/install.sh            Linux / macOS
    .\\installer\\install.ps1           Windows (PowerShell)
    python installer/install.py       anywhere with Python 3.10+

Safe to run again: it repairs and updates rather than starting over.
Nothing outside this folder (and kokoro-reader's, next to it) is touched
without asking first - system packages show the exact command and wait.

    --yes                take every default, ask nothing
    --backend X          lmstudio (default), llama, or skip
    --voice X            install (default), url:http://host:port, or skip
    --gpu X              auto (default), cpu, cuda, rocm - for the voice server
    --extras a,b         wakeword, mcp, portrait, live2d, embeddings, chat  (or "all")
    --no-system          don't install system packages, just say which are missing
    --check              only run the health check
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import venv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "installer")
STATE = os.path.join(ROOT, "install.json")
SYSTEM = platform.system()          # Linux, Darwin, Windows
WIN = SYSTEM == "Windows"
KOKORO_REPO = os.environ.get("LUNA_KOKORO_REPO", "https://github.com/fswolf/kokoro-reader.git")
TORCH_CPU = "https://download.pytorch.org/whl/cpu"
TORCH_ROCM = os.environ.get("LUNA_TORCH_ROCM", "https://download.pytorch.org/whl/rocm6.4")
TORCH_CUDA_WIN = os.environ.get("LUNA_TORCH_CUDA", "https://download.pytorch.org/whl/cu128")
EMBED_URL = ("https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/"
             "Qwen3-Embedding-0.6B-Q8_0.gguf")
CUBISM_URL = "https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js"

EXTRAS = {
    "wakeword": (["openwakeword"], "\"hey Luna\" instead of a key press"),
    "mcp": (["mcp"], "tools from MCP servers (OBS, Home Assistant, ComfyUI...)"),
    "portrait": (["pillow"], "portrait tools: Live2D import, textures"),
    "live2d": ([], "Live2D's runtime saved locally, so the portrait works offline"),
    "embeddings": ([], "recall by meaning: a 600 MB embedding model (llama.cpp backend)"),
    "chat": (["websocket-client"], "the pomf.tv stream-chat plugin"),
}

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
COLOR = sys.stdout.isatty() and not WIN or os.environ.get("WT_SESSION")
P, G, Y, R, D, X = (("\033[95m", "\033[92m", "\033[93m", "\033[91m", "\033[2m", "\033[0m") if COLOR
                    else ("",) * 6)
ARGS = None
REPORT = []          # (step, ok, note) for the summary


def step(title):
    print(f"\n{P}== {title}{X}")


def ok(msg):
    print(f"  {G}✓{X} {msg}")


def warn(msg):
    print(f"  {Y}!{X} {msg}")


def fail(msg):
    print(f"  {R}✗{X} {msg}")


def note(name, good, text=""):
    REPORT.append((name, good, text))


def ask(question, default=True):
    if ARGS.yes:
        return default
    hint = "Y/n" if default else "y/N"
    try:
        answer = input(f"  {question} [{hint}] ").strip().lower()
    except EOFError:
        return default
    return default if not answer else answer.startswith("y")


def choose(question, options, default):
    """options: [(key, label)]"""
    if ARGS.yes:
        return default
    print(f"  {question}")
    for i, (key, label) in enumerate(options, 1):
        mark = " (default)" if key == default else ""
        print(f"    {i}. {label}{D}{mark}{X}")
    try:
        raw = input("  > ").strip()
    except EOFError:
        return default
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1][0]
    return next((k for k, _l in options if raw == k), default)


def run(cmd, cwd=None, env=None, quiet=False):
    """Run a command, streaming its output unless quiet. True on success."""
    printable = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)
    print(f"  {D}$ {printable}{X}")
    try:
        out = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env,
                             stdout=subprocess.PIPE if quiet else None,
                             stderr=subprocess.STDOUT if quiet else None, text=True)
    except FileNotFoundError:
        fail(f"{cmd[0]} isn't installed")
        return False
    if out.returncode and quiet and out.stdout:
        print("\n".join("    " + l for l in out.stdout.strip().splitlines()[-15:]))
    return out.returncode == 0


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def venv_python(path):
    return os.path.join(path, "Scripts", "python.exe") if WIN else os.path.join(path, "bin", "python")


def http_ok(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    print(f"  {D}downloading {url}{X}")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total and sys.stdout.isatty():
                    print(f"\r    {got * 100 // total}% of {total // (1 << 20)} MB", end="", flush=True)
        if total and sys.stdout.isatty():
            print()
        os.replace(tmp, dest)
        return True
    except Exception as e:
        fail(f"download failed: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


# ---------------------------------------------------------------------------
# 1. What's here
# ---------------------------------------------------------------------------
def detect_gpu():
    if shutil.which("nvidia-smi"):
        return "cuda", "NVIDIA"
    if SYSTEM == "Darwin":
        return "mps" if platform.machine() == "arm64" else "cpu", "Apple " + platform.machine()
    if SYSTEM == "Linux":
        try:
            with open("/proc/bus/pci/devices") as f:
                data = f.read()
        except OSError:
            data = ""
        amd = "1002" in "".join(line.split("\t")[1][:4] for line in data.splitlines() if "\t" in line)
        if amd:
            return ("rocm" if shutil.which("rocminfo") else "cpu"), "AMD" + ("" if shutil.which("rocminfo")
                                                                             else " (no ROCm - voice on CPU)")
    return "cpu", "none found"


def check_system():
    step("Checking this machine")
    v = sys.version_info
    if v < (3, 10):
        fail(f"Python {v.major}.{v.minor} - Luna needs 3.10 or newer (3.12 recommended)")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor} on {SYSTEM} {platform.machine()}")
    if v >= (3, 14):
        warn("Python 3.14+ is newer than some speech packages support yet - 3.12 is the safe choice")
    gpu, label = detect_gpu()
    ok(f"GPU: {label}")
    free = shutil.disk_usage(ROOT).free // (1 << 30)
    (ok if free >= 10 else warn)(f"{free} GB free here (about 6 GB needed, more for models)")
    return gpu


# ---------------------------------------------------------------------------
# 2. System packages
# ---------------------------------------------------------------------------
def package_manager():
    for pm, install in (("dnf", ["sudo", "dnf", "install", "-y"]), ("apt-get", ["sudo", "apt-get", "install", "-y"]),
                        ("pacman", ["sudo", "pacman", "-S", "--needed", "--noconfirm"]),
                        ("zypper", ["sudo", "zypper", "install", "-y"]), ("brew", ["brew", "install"])):
        if shutil.which(pm):
            if os.geteuid() == 0 if hasattr(os, "geteuid") else False:
                install = [c for c in install if c != "sudo"]
            return pm, install
    return None, None


# what each package manager calls the things she needs, and what for
PACKAGES = {
    "dnf": {"portaudio-devel": "audio", "python3-devel": "building evdev", "gcc": "building evdev",
            "espeak-ng": "the voice", "git": "fetching the voice server"},
    "apt-get": {"portaudio19-dev": "audio", "python3-dev": "building evdev", "build-essential": "building evdev",
                "python3-venv": "virtual environments", "espeak-ng": "the voice",
                "git": "fetching the voice server"},
    "pacman": {"portaudio": "audio", "base-devel": "building evdev", "espeak-ng": "the voice",
               "git": "fetching the voice server"},
    "zypper": {"portaudio-devel": "audio", "python3-devel": "building evdev", "gcc": "building evdev",
               "espeak-ng": "the voice", "git": "fetching the voice server"},
    "brew": {"portaudio": "audio", "espeak-ng": "the voice", "git": "fetching the voice server"},
}
OPTIONAL_LINUX = {"grim": "screenshots for vision (Wayland)", "slurp": "picking a screen region",
                  "wl-clipboard": "the clipboard tool (Wayland)", "unrar": "importing .rar Live2D models"}


def installed(pm, pkg):
    probe = {"dnf": ["rpm", "-q", pkg], "zypper": ["rpm", "-q", pkg], "apt-get": ["dpkg", "-s", pkg],
             "pacman": ["pacman", "-Q", pkg], "brew": ["brew", "list", pkg]}.get(pm)
    if not probe or not shutil.which(probe[0]):
        return False
    return subprocess.run(probe, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def system_packages():
    step("System packages")
    if WIN:
        if not shutil.which("git"):
            warn("git isn't installed - needed to fetch the voice server")
            if not ARGS.no_system and shutil.which("winget") and ask("Install it with winget?"):
                run(["winget", "install", "--id", "Git.Git", "-e", "--accept-source-agreements"])
        else:
            ok("git")
        ok("audio and the voice's espeak come bundled with the Python packages on Windows")
        return True

    pm, install = package_manager()
    if not pm:
        warn("no known package manager - make sure PortAudio, espeak-ng and git are installed")
        note("system packages", False, "unknown package manager")
        return False
    wanted = dict(PACKAGES[pm])
    # evdev compiles against the headers of the Python the venv uses, which
    # isn't always the system's default python3 (Fedora 44 ships 3.14; the
    # venv may well be 3.12).
    mm = f"{sys.version_info.major}.{sys.version_info.minor}"
    if pm == "dnf":
        wanted[f"python{mm}-devel"] = "building evdev"
        wanted.pop("python3-devel", None)
    elif pm == "apt-get":
        wanted[f"python{mm}-dev"] = "building evdev"
        wanted[f"python{mm}-venv"] = "virtual environments"
        wanted.pop("python3-dev", None)
        wanted.pop("python3-venv", None)
    missing = [p for p in wanted if not installed(pm, p)]
    if SYSTEM == "Linux":
        optional = [p for p in OPTIONAL_LINUX if not installed(pm, p) and not shutil.which(p.split("-")[0])]
    else:
        optional = []
    for p in wanted:
        if p not in missing:
            ok(f"{p}")
    if not missing and not optional:
        note("system packages", True)
        return True
    if missing:
        print(f"  needed: {', '.join(f'{p} ({wanted[p]})' for p in missing)}")
    if optional:
        print(f"  {D}optional: {', '.join(f'{p} ({OPTIONAL_LINUX[p]})' for p in optional)}{X}")
    if ARGS.no_system:
        warn("--no-system: install those yourself")
        note("system packages", not missing, "skipped" if missing else "")
        return not missing
    todo = list(missing)
    if optional and ask("Install the optional ones too?", default=True):
        todo += optional
    if todo and ask(f"Run: {' '.join(install + todo)} ?"):
        if pm == "apt-get":   # a stale package list 404s on the first download
            run([c for c in install if c not in ("install", "-y")] + ["update", "-q"], quiet=True)
        good = run(install + todo)
        if not good and pm == "dnf" and "unrar" in todo:
            warn("unrar is in RPM Fusion on Fedora - retrying without it")
            todo.remove("unrar")
            good = run(install + todo)
        note("system packages", good)
        return good
    note("system packages", not missing, "you said no")
    return not missing


# ---------------------------------------------------------------------------
# 3. Luna's Python environment
# ---------------------------------------------------------------------------
def find_venv(state):
    """Reuse what's there: the one install.json remembers, an active one,
    or the names the README used to suggest."""
    candidates = [state.get("venv"), os.environ.get("VIRTUAL_ENV"),
                  os.path.expanduser("~/ai-voice-venv"), os.path.join(ROOT, "ai-voice-venv"),
                  os.path.join(ROOT, "venv"), os.path.join(ROOT, ".venv")]
    for c in candidates:
        if c and os.path.exists(venv_python(c)):
            return c
    return os.path.join(ROOT, ".venv")


def pip(py, *args, quiet=True):
    return run([py, "-m", "pip", "install", "--disable-pip-version-check", *args], quiet=quiet)


def python_env(state, extras):
    step("Luna's Python environment")
    path = find_venv(state)
    py = venv_python(path)
    if os.path.exists(py):
        ok(f"using {path}")
    else:
        print(f"  creating {path}")
        try:
            venv.EnvBuilder(with_pip=True).create(path)
        except Exception as e:
            fail(f"couldn't create it: {e}" + (" - install python3-venv" if SYSTEM == "Linux" else ""))
            note("python environment", False, str(e))
            return None
    state["venv"] = path
    run([py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip"], quiet=True)

    # Silero VAD needs PyTorch, but only a little of it on the CPU. The
    # default Linux/Windows wheel brings 2+ GB of CUDA she never uses.
    have_torch = subprocess.run([py, "-c", "import torch"], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL).returncode == 0
    if not have_torch and SYSTEM != "Darwin":
        print("  PyTorch (CPU build - only voice detection uses it here)")
        if not pip(py, "torch", "torchaudio", "--index-url", TORCH_CPU):
            warn("couldn't reach PyTorch's CPU index - the regular (much bigger) build will come from PyPI")

    print("  Luna's packages")
    good = pip(py, "-r", os.path.join(HERE, "requirements.txt"))
    names = sorted({p for e in extras for p in EXTRAS[e][0]})
    if names:
        print(f"  extras: {', '.join(names)}")
        good = pip(py, *names) and good
    (ok if good else fail)("packages installed" if good else "some packages failed - see above")
    note("python packages", good)
    return py if good else None


# ---------------------------------------------------------------------------
# 4. The voice: kokoro-reader
# ---------------------------------------------------------------------------
def voice(state, gpu_choice):
    step("Her voice (kokoro-reader)")
    mode = ARGS.voice
    if mode == "install" and http_ok("http://127.0.0.1:8899/health") and not state.get("kokoro_dir"):
        ok("a voice server is already answering on :8899 - using that one")
        state["voice"] = {"mode": "external", "url": "http://127.0.0.1:8899"}
        note("voice", True, "existing server on :8899")
        return
    if mode == "skip":
        warn("skipped - she'll be text-only until a TTS server answers on tts.url")
        state["voice"] = {"mode": "none"}
        note("voice", False, "skipped")
        return
    if mode.startswith("url:"):
        url = mode[4:].rstrip("/")
        state["voice"] = {"mode": "external", "url": url}
        set_config("tts", "url", url)
        (ok if http_ok(url + "/health") else warn)(f"pointing her at {url}")
        note("voice", True, url)
        return

    kdir = state.get("kokoro_dir") or os.path.join(os.path.dirname(ROOT), "kokoro-reader")
    if os.path.isdir(os.path.join(kdir, ".git")):
        ok(f"kokoro-reader at {kdir}")
        run(["git", "-C", kdir, "pull", "--ff-only", "-q"], quiet=True)
    elif os.path.isdir(os.path.join(kdir, "server")):
        ok(f"kokoro-reader at {kdir}")
    else:
        if not shutil.which("git"):
            fail("git isn't installed - can't fetch kokoro-reader")
            note("voice", False, "no git")
            return
        if not run(["git", "clone", "--depth", "1", KOKORO_REPO, kdir]):
            note("voice", False, "clone failed")
            return
    server = os.path.join(kdir, "server")
    kvenv = os.path.join(server, ".venv")
    kpy = venv_python(kvenv)
    if not os.path.exists(kpy):
        venv.EnvBuilder(with_pip=True).create(kvenv)
    run([kpy, "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip"], quiet=True)

    gpu = gpu_choice
    device = {"cuda": "cuda", "rocm": "cuda", "mps": "mps"}.get(gpu, "cpu")
    have_torch = subprocess.run([kpy, "-c", "import torch"], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL).returncode == 0
    if not have_torch:
        if gpu == "rocm":
            print("  PyTorch for AMD (ROCm) - a big download")
            good = pip(kpy, "torch", "--index-url", TORCH_ROCM)
        elif gpu == "cuda" and WIN:
            print("  PyTorch for NVIDIA (CUDA) - a big download")
            good = pip(kpy, "torch", "--index-url", TORCH_CUDA_WIN)
        elif gpu == "cuda" or SYSTEM == "Darwin":
            print("  PyTorch" + (" for NVIDIA - a big download" if gpu == "cuda" else ""))
            good = pip(kpy, "torch")
        else:
            print("  PyTorch (CPU build) - the voice runs about real time on CPU")
            good = pip(kpy, "torch", "--index-url", TORCH_CPU)
        if not good:
            device = "cpu"
            if gpu in ("cuda", "rocm"):
                warn("the GPU build didn't install - trying the CPU build")
                good = pip(kpy, "torch", "--index-url", TORCH_CPU)
            if not good:
                warn("couldn't reach PyTorch's own index - the regular build will come from PyPI")
    good = pip(kpy, "-r", os.path.join(server, "requirements.txt"))
    (ok if good else fail)(f"voice server ready ({device})" if good else "voice server packages failed")
    state["kokoro_dir"] = kdir
    state["voice"] = {"mode": "managed", "python": kpy, "server": os.path.join(server, "kokoro_server.py"),
                      "device": device, "port": 8899}
    set_config("tts", "url", "http://127.0.0.1:8899")
    note("voice", good, "the launcher starts it with Luna; the model downloads on first use (~400 MB)")


# ---------------------------------------------------------------------------
# 5. The brain
# ---------------------------------------------------------------------------
def backend(state):
    step("Her brain (the model server)")
    choice = ARGS.backend
    if choice is None:
        options = [("lmstudio", "LM Studio - an app with a model browser; easiest"),
                   ("llama", "llama.cpp's own server - builds it here (Linux), unlocks the research features"),
                   ("skip", "skip - I'll set one up myself")]
        if SYSTEM != "Linux":
            options = [o for o in options if o[0] != "llama"]
        choice = choose("Which model server?", options, "lmstudio")
    state["backend"] = choice

    if choice == "lmstudio":
        up = http_ok("http://localhost:1234/v1/models")
        if up:
            ok("LM Studio's server is answering on :1234")
        else:
            print("  1. Install LM Studio: https://lmstudio.ai")
            print("  2. Download a model (a 7-14B instruct model with tool calling - Qwen works well)")
            print("  3. Developer tab -> start the server (port 1234)")
        note("model server", up, "LM Studio" if up else "install LM Studio and start its server")
    elif choice == "llama":
        if SYSTEM != "Linux":
            warn("the llama.cpp build script is Linux-only so far - use LM Studio on this system")
            note("model server", False, "llama.cpp: Linux only")
            return
        kind = "rocm" if detect_gpu()[0] == "rocm" else "vulkan"
        print(f"  building llama.cpp ({kind}) - this takes a few minutes")
        good = run(["bash", os.path.join(ROOT, "llama", "install.sh"), kind])
        note("model server", good, "llama.cpp built - put a model in llama/models and run llama/start.sh"
             if good else "llama.cpp build failed - see above")
    else:
        note("model server", False, "skipped")


# ---------------------------------------------------------------------------
# 6. Extras that aren't pip packages
# ---------------------------------------------------------------------------
def extras_files(extras):
    if "live2d" in extras:
        step("Live2D runtime")
        dest = os.path.join(ROOT, "portrait", "vendor", "live2dcubismcore.min.js")
        if os.path.exists(dest):
            ok("already here")
        else:
            print("  Live2D's own code, under their licence: https://www.live2d.com/eula/")
            note("live2d runtime", download(CUBISM_URL, dest))
    if "embeddings" in extras:
        step("Embedding model")
        dest = os.path.join(ROOT, "llama", "models", os.path.basename(EMBED_URL))
        if os.path.exists(dest):
            ok("already here")
        elif ask("Download the 600 MB embedding model?"):
            note("embedding model", download(EMBED_URL, dest), "used by llama/start.sh")


# ---------------------------------------------------------------------------
# 7. Launchers
# ---------------------------------------------------------------------------
def launchers(state):
    step("Launchers")
    launch = os.path.join(ROOT, "launch.py")
    py = state["venv_python"]
    if WIN:
        cmd = os.path.join(ROOT, "luna.cmd")
        with open(cmd, "w", encoding="utf-8") as f:
            f.write(f'@echo off\r\ncd /d "{ROOT}"\r\n"{py}" "{launch}" %*\r\n')
        ok(f"luna.cmd - double-click it, or run it from a terminal")
        if ask("Add a Start menu shortcut?"):
            menu = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs",
                                "Luna.lnk")
            ps = (f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{menu}");'
                  f'$s.TargetPath="{cmd}";$s.WorkingDirectory="{ROOT}";$s.Save()')
            if run(["powershell", "-NoProfile", "-Command", ps], quiet=True):
                state["shortcut"] = menu
                ok("Start menu: Luna")
        note("launcher", True, "luna.cmd")
        return

    script = os.path.join(ROOT, "start.sh")
    os.chmod(script, 0o755)
    ok("start.sh")
    bindir = os.path.expanduser("~/.local/bin")
    link = os.path.join(bindir, "luna")
    if ask(f"Add a 'luna' command ({link})?"):
        os.makedirs(bindir, exist_ok=True)
        if os.path.islink(link) or not os.path.exists(link):
            if os.path.islink(link):
                os.remove(link)
            os.symlink(script, link)
            state["command"] = link
            ok("type 'luna' in any terminal" + ("" if bindir in os.environ.get("PATH", "")
                                                 else f" (add {bindir} to your PATH)"))
        else:
            warn(f"{link} already exists and isn't ours - left alone")
    if SYSTEM == "Darwin":
        cmd = os.path.join(ROOT, "Luna.command")
        with open(cmd, "w") as f:
            f.write(f'#!/bin/bash\nexec "{script}" "$@"\n')
        os.chmod(cmd, 0o755)
        ok("Luna.command - double-click it in Finder")
    elif ask("Add Luna to your app launcher?"):
        apps = os.path.expanduser("~/.local/share/applications")
        os.makedirs(apps, exist_ok=True)
        entry = os.path.join(apps, "luna.desktop")
        with open(entry, "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Luna\nComment=Local AI voice companion\n"
                    f'Exec="{script}"\nPath={ROOT}\nTerminal=true\nCategories=Utility;\n'
                    + (f"Icon={os.path.join(ROOT, 'assets', 'icon.png')}\n"
                       if os.path.exists(os.path.join(ROOT, "assets", "icon.png")) else ""))
        state["desktop"] = entry
        ok("app launcher: Luna (opens in a terminal)")
    note("launcher", True, "luna / start.sh")


# ---------------------------------------------------------------------------
# config.json - only the keys the installer owns, everything else untouched
# ---------------------------------------------------------------------------
def set_config(section, key, value):
    path = os.path.join(ROOT, "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return
    if cfg.get(section, {}).get(key) == value:
        return
    cfg.setdefault(section, {})[key] = value
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# 8. Health check
# ---------------------------------------------------------------------------
def health(state):
    step("Health check")
    py = state.get("venv_python") or venv_python(find_venv(state))
    probe = ("import importlib,json\n"
             "mods=['requests','numpy','scipy','sounddevice','silero_vad','faster_whisper','prompt_toolkit','ddgs']\n"
             "bad={}\n"
             "for m in mods:\n"
             "  try: importlib.import_module(m)\n"
             "  except Exception as e: bad[m]=str(e)[:120]\n"
             "print(json.dumps(bad))")
    try:
        out = subprocess.run([py, "-c", probe], capture_output=True, text=True, timeout=180)
        bad = json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else {"python": out.stderr[-200:]}
    except Exception as e:
        bad = {"python": str(e)}
    if bad:
        for m, e in bad.items():
            fail(f"{m}: {e}")
            if m == "sounddevice":
                print("    (PortAudio missing - install the system packages step's audio package)")
    else:
        ok("every package imports")
    note("imports", not bad, ", ".join(bad) if bad else "")

    lm = http_ok("http://localhost:1234/v1/models")
    ll = http_ok("http://127.0.0.1:8080/health")
    (ok if lm or ll else warn)("model server: " + ("llama.cpp :8080" if ll else "LM Studio :1234" if lm
                                                   else "none running yet (start LM Studio's server or llama/start.sh)"))
    v = state.get("voice", {})
    if v.get("mode") == "managed":
        ok("voice: the launcher starts kokoro-reader with her")
    elif v.get("mode") == "external":
        (ok if http_ok(v["url"] + "/health") else warn)(f"voice: {v['url']}")


def summary():
    print(f"\n{P}== Summary{X}")
    for name, good, text in REPORT:
        print(f"  {G + '✓' if good else Y + '!'}{X} {name}{D}{' - ' + text if text else ''}{X}")
    start = "luna.cmd" if WIN else ("luna  (or ./start.sh)" if os.path.exists(os.path.expanduser("~/.local/bin/luna"))
                                    else "./start.sh")
    print(f"\n  Start her with: {P}{start}{X}")
    print("  Run this installer again any time to repair or update.\n")


# ---------------------------------------------------------------------------
def main():
    global ARGS
    ap = argparse.ArgumentParser(description="Install Luna.", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 2)[-1])
    ap.add_argument("--yes", "-y", action="store_true")
    ap.add_argument("--backend", choices=["lmstudio", "llama", "skip"])
    ap.add_argument("--voice", default="install")
    ap.add_argument("--gpu", default="auto", choices=["auto", "cpu", "cuda", "rocm", "mps"])
    ap.add_argument("--extras", default=None)
    ap.add_argument("--no-system", action="store_true")
    ap.add_argument("--check", action="store_true")
    ARGS = ap.parse_args()

    print(f"{P}Luna - local AI companion - installer{X}  {D}{ROOT}{X}")
    state = load_state()
    if ARGS.check:
        health(state)
        return

    gpu = check_system()
    if ARGS.gpu != "auto":
        gpu = ARGS.gpu

    if ARGS.extras is None:
        if ARGS.yes:
            extras = ["mcp", "portrait"]
        else:
            step("Extras")
            extras = []
            for key, (_pkgs, what) in EXTRAS.items():
                if key == "embeddings" and ARGS.backend not in (None, "llama"):
                    continue
                if ask(f"{key}: {what}?", default=key in ("mcp", "portrait")):
                    extras.append(key)
    else:
        extras = [e for e in (EXTRAS if ARGS.extras == "all" else ARGS.extras.split(",")) if e in EXTRAS]
    state["extras"] = extras

    system_packages()
    py = python_env(state, extras)
    if py:
        state["venv_python"] = py
    save_state(state)
    voice(state, gpu)
    save_state(state)
    backend(state)
    extras_files(extras)
    if py:
        launchers(state)
    save_state(state)
    health(state)
    summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  stopped - run it again to carry on where it left off")
        sys.exit(130)
