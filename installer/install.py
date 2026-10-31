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
    --extras a,b         wakeword, mcp, portrait, live2d, embeddings, reranker, chat, camera, voices  (or "all")
    --model X            auto (default: picked for your GPU's memory), skip, or a size: 4b, 9b-q4, 9b, 27b...
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
RERANK_URL = ("https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/resolve/main/"
              "qwen3-reranker-0.6b-q8_0.gguf")
CUBISM_URL = "https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js"

EXTRAS = {
    "wakeword": (["openwakeword"], "\"hey Luna\" instead of a key press"),
    "mcp": (["mcp"], "tools from MCP servers (OBS, Home Assistant, ComfyUI...), and the Zork, Minecraft and REALITI games"),
    "portrait": (["pillow"], "portrait tools: Live2D import, textures"),
    "live2d": ([], "Live2D's runtime saved locally, so the portrait works offline"),
    "embeddings": ([], "recall by meaning: a 600 MB embedding model (llama.cpp backend)"),
    "reranker": ([], "sharper recall: a 640 MB reranker beside the embedding model (skip on 16 GB machines)"),
    "chat": (["websocket-client"], "the pomf.tv stream-chat plugin"),
    "documents": (["pypdf"], "PDFs in her knowledge folder (Markdown, text, Word and web pages need nothing)"),
    "toys": (["websocket-client"], "the Buttplug plugin: toys of most brands through Intiface Central"),
    "camera": (["opencv-python-headless"], "look_at_camera: one webcam picture when you ask (off until you switch it on)"),
    "voices": (["speechbrain"], "tell people in the house apart by voice (/people enroll voice)"),
    "stations": (["cryptography", "segno"], "talk to her from another room on an old phone or tablet (relay stations)"),
    "satellites": (["aioesphomeapi"], "EXPERIMENTAL: ESPHome voice satellites (Satellite1, Voice PE) as relay stations"),
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


# Some CDNs (Live2D's among them) answer Python's default user agent
# with 403 Forbidden, so say what we are in words a CDN accepts.
USER_AGENT = "Mozilla/5.0 (compatible; luna-installer; +https://github.com/fswolf/luna-local-agent)"


def _curl(url, tmp):
    """Second try with the system curl, which every Mac and most Linux
    boxes have - different TLS stack, different fingerprint."""
    curl = shutil.which("curl")
    if not curl:
        return False
    return subprocess.run([curl, "-fsSL", "--retry", "2", "-A", USER_AGENT, "-o", tmp, url]).returncode == 0


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    print(f"  {D}downloading {url}{X}")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as r, open(tmp, "wb") as f:
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
        print(f"  {D}{e} - trying curl{X}")
        if _curl(url, tmp):
            os.replace(tmp, dest)
            return True
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
            with open("/proc/bus/pci/devices", encoding="utf-8") as f:
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
                  "wl-clipboard": "the clipboard tool (Wayland)", "unrar": "importing .rar Live2D models",
                  "frotz": "playing Zork (its dfrotz interpreter)"}
# the command that shows an optional package is already there, when it isn't the package's name
_PROVIDES = {"frotz": "dfrotz", "wl-clipboard": "wl-copy"}


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
        optional = [p for p in OPTIONAL_LINUX if not installed(pm, p)
                    and not shutil.which(_PROVIDES.get(p, p)) and not shutil.which(f"/usr/games/{_PROVIDES.get(p, p)}")]
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
        if not good and set(todo) - set(missing):
            # an optional one this distro doesn't carry (frotz, unrar) mustn't cost the needed ones
            warn("retrying with only the packages Luna needs")
            good = run(install + missing) if missing else True
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
    # Kokoro on Apple's GPU (mps) is unreliable: PyTorch's istft on MPS
    # fails on some sentences ("window overlap add min: 0"), so the server
    # answers 500 and she goes quiet. The voice is small; an Apple-silicon
    # CPU runs it faster than real time. GPUs elsewhere are fine.
    device = {"cuda": "cuda", "rocm": "cuda", "mps": "cpu"}.get(gpu, "cpu")
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
                   ("llama", "llama.cpp's own server - builds it here, unlocks the research features"),
                   ("skip", "skip - I'll set one up myself")]
        if SYSTEM == "Windows":
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
        if SYSTEM == "Windows":
            warn("the llama.cpp build script is Linux and macOS only so far - use LM Studio here")
            note("model server", False, "llama.cpp: not on Windows yet")
            return
        if SYSTEM == "Darwin":
            kind = "metal"
            if not shutil.which("cmake"):
                print("  needs Apple's compiler and cmake first:")
                print("    xcode-select --install")
                print("    brew install cmake bash      (Homebrew: https://brew.sh)")
        else:
            kind = "rocm" if detect_gpu()[0] == "rocm" else "vulkan"
        print(f"  building llama.cpp ({kind}) - this takes a few minutes")
        good = run(["bash", os.path.join(ROOT, "llama", "install.sh"), kind])
        note("model server", good, "llama.cpp built - put a model in llama/models and run llama/start.sh"
             if good else "llama.cpp build failed - see above")
    else:
        note("model server", False, "skipped")


# ---------------------------------------------------------------------------
# 5b. Her model, picked for this machine
#
# Which model and how big is the question most people stall on, so the
# installer answers it: it reads how much video memory there is and
# picks the biggest Qwen model that fits with room for her context and
# her eyes (the vision adapter). Qwen 3.5/3.6: Apache-2.0, tool calling,
# vision. The files are bartowski's GGUFs on Hugging Face.
# ---------------------------------------------------------------------------
HF = "https://huggingface.co/{repo}/resolve/main/{file}"

# (key, label, repo, file, GB, mmproj or "", least VRAM it wants, context, LM Studio name@quant)
MODELS = (
    ("27b-q6", "Qwen3.5 27B, Q6_K", "bartowski/Qwen_Qwen3.5-27B-GGUF", "Qwen_Qwen3.5-27B-Q6_K.gguf", 23.7,
     "mmproj-Qwen_Qwen3.5-27B-f16.gguf", 30, 16384, "qwen3.5-27b@q6_k"),
    ("27b", "Qwen3.5 27B, Q4_K_M", "bartowski/Qwen_Qwen3.5-27B-GGUF", "Qwen_Qwen3.5-27B-Q4_K_M.gguf", 18.0,
     "mmproj-Qwen_Qwen3.5-27B-f16.gguf", 22, 16384, "qwen3.5-27b@q4_k_m"),
    ("9b", "Qwen3.5 9B, Q8_0", "bartowski/Qwen_Qwen3.5-9B-GGUF", "Qwen_Qwen3.5-9B-Q8_0.gguf", 9.8,
     "mmproj-Qwen_Qwen3.5-9B-f16.gguf", 14, 16384, "qwen3.5-9b@q8_0"),
    ("9b-q6", "Qwen3.5 9B, Q6_K", "bartowski/Qwen_Qwen3.5-9B-GGUF", "Qwen_Qwen3.5-9B-Q6_K.gguf", 8.0,
     "mmproj-Qwen_Qwen3.5-9B-f16.gguf", 11, 16384, "qwen3.5-9b@q6_k"),
    ("9b-q4", "Qwen3.5 9B, Q4_K_M", "bartowski/Qwen_Qwen3.5-9B-GGUF", "Qwen_Qwen3.5-9B-Q4_K_M.gguf", 6.2,
     "", 7.5, 8192, "qwen3.5-9b@q4_k_m"),
    ("4b", "Qwen3.5 4B, Q6_K", "bartowski/Qwen_Qwen3.5-4B-GGUF", "Qwen_Qwen3.5-4B-Q6_K.gguf", 3.8,
     "mmproj-Qwen_Qwen3.5-4B-f16.gguf", 6, 8192, "qwen3.5-4b@q6_k"),
    ("4b-q4", "Qwen3.5 4B, Q4_K_M", "bartowski/Qwen_Qwen3.5-4B-GGUF", "Qwen_Qwen3.5-4B-Q4_K_M.gguf", 3.0,
     "", 0, 8192, "qwen3.5-4b@q4_k_m"),
)

# The same sizes, uncensored: huihui-ai's abliterated Qwen3.5 (refusals taken out
# of the weights, nothing else retrained), quantised by mradermacher, with the
# vision files. This is what most people run her on, so it's the default;
# --standard (or "standard" when asked) keeps Qwen's own release.
#   key: (label, repo, file, GB, mmproj, LM Studio name)
_HUIHUI = "mradermacher/Huihui-Qwen3.5-{b}-abliterated-GGUF"
UNCENSORED = {
    "27b-q6": ("Qwen3.5 27B uncensored, Q6_K", _HUIHUI.format(b="27B"), "Huihui-Qwen3.5-27B-abliterated.Q6_K.gguf",
               22.1, "Huihui-Qwen3.5-27B-abliterated.mmproj-f16.gguf"),
    "27b": ("Qwen3.5 27B uncensored, Q4_K_M", _HUIHUI.format(b="27B"), "Huihui-Qwen3.5-27B-abliterated.Q4_K_M.gguf",
            16.5, "Huihui-Qwen3.5-27B-abliterated.mmproj-f16.gguf"),
    "9b": ("Qwen3.5 9B uncensored, Q8_0", _HUIHUI.format(b="9B"), "Huihui-Qwen3.5-9B-abliterated.Q8_0.gguf",
           9.5, "Huihui-Qwen3.5-9B-abliterated.mmproj-f16.gguf"),
    "9b-q6": ("Qwen3.5 9B uncensored, Q6_K", _HUIHUI.format(b="9B"), "Huihui-Qwen3.5-9B-abliterated.Q6_K.gguf",
              7.4, "Huihui-Qwen3.5-9B-abliterated.mmproj-f16.gguf"),
    "9b-q4": ("Qwen3.5 9B uncensored, Q4_K_M", _HUIHUI.format(b="9B"), "Huihui-Qwen3.5-9B-abliterated.Q4_K_M.gguf",
              5.6, ""),
    "4b": ("Qwen3.5 4B uncensored, Q6_K", _HUIHUI.format(b="4B"), "Huihui-Qwen3.5-4B-abliterated.Q6_K.gguf",
           3.5, "Huihui-Qwen3.5-4B-abliterated.mmproj-f16.gguf"),
    "4b-q4": ("Qwen3.5 4B uncensored, Q4_K_M", _HUIHUI.format(b="4B"), "Huihui-Qwen3.5-4B-abliterated.Q4_K_M.gguf",
              2.7, ""),
}


def variant(m, uncensored=True):
    """The table row as downloaded: the uncensored files for its size, or
    Qwen's own (the row as it is)."""
    if not uncensored or m[0] not in UNCENSORED:
        return m
    label, repo, file, size, mmproj = UNCENSORED[m[0]]
    quant = file.rsplit(".", 2)[-2].lower()
    return (m[0], label, repo, file, size, mmproj, m[6], m[7], f"{repo}@{quant}")


def _gb(n):
    return round(n / (1 << 30), 1)


def detect_vram():
    """(GB of memory her model can use, where that came from), or (0, why)."""
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10).stdout
            mib = max(int(x) for x in out.split() if x.strip().isdigit())
            return round(mib / 1024, 1), "NVIDIA"
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    if SYSTEM == "Darwin":
        try:
            ram = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
        except (OSError, ValueError):
            return 0, "couldn't read this Mac's memory"
        if platform.machine() != "arm64":
            return 0, "Intel Mac: the model runs on the CPU"
        # Apple Silicon shares memory with everything else: about two thirds is hers
        return round(_gb(ram) * 0.65, 1), f"Apple Silicon, {_gb(ram)} GB shared"
    if SYSTEM == "Linux":
        import glob

        sizes = []
        for f in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
            try:
                with open(f, encoding="utf-8") as fh:
                    sizes.append(int(fh.read().strip()))
            except (OSError, ValueError):
                continue
        if sizes:
            return _gb(max(sizes)), "AMD"
    if WIN:
        try:
            import winreg

            best = 0
            key = r"SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as root:
                for i in range(64):
                    try:
                        with winreg.OpenKey(root, f"{i:04d}") as sub:
                            best = max(best, int(winreg.QueryValueEx(sub, "HardwareInformation.qwMemorySize")[0]))
                    except OSError:
                        continue
            if best:
                return _gb(best), "graphics card"
        except Exception:
            pass
    return 0, "no graphics memory found"


def pick_model(vram):
    """The biggest model that fits vram GB (the smallest when nothing does)."""
    for m in MODELS:
        if vram >= m[6]:
            return m
    return MODELS[-1]


def _model_by_key(key):
    return next((m for m in MODELS if m[0] == key), None)


def _write_local_env(values):
    """llama/server.local.env: this machine's model, read after server.env."""
    path = os.path.join(ROOT, "llama", "server.local.env")
    lines = ["# Written by the installer for this machine (not committed). Edit freely."]
    lines += [f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}" for k, v in values.items()]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def model(state):
    step("Her model")
    choice = (ARGS.model or "auto").lower()
    if choice == "skip" or state.get("backend") == "skip":
        note("model", False, "skipped")
        return

    vram, where = detect_vram()

    # an install from before the uncensored choice existed has a model and no
    # flavour: that model is Qwen's own, and a re-run mustn't swap it for another
    flavour = state.get("flavour") or ("standard" if state.get("model") else "uncensored")
    uncensored = not ARGS.standard and flavour != "standard"

    # run again: the model from last time stays unless one is asked for by name
    done = _model_by_key(state.get("model") or "")
    if done:
        done = variant(done, uncensored)
    if choice == "auto" and done:
        here = os.path.exists(os.path.join(ROOT, "llama", "models", done[3]))
        if state.get("backend") != "llama" or here:
            state["flavour"] = "uncensored" if uncensored else "standard"
            ok(f"{done[1]} (set up last time; --model <size> picks another)")
            return

    m = _model_by_key(choice) if choice != "auto" else pick_model(vram)
    if m is None:
        warn(f"no model called {choice} - picking for this machine")
        m = pick_model(vram)

    if not ARGS.yes and choice == "auto" and not ARGS.standard:
        uncensored = choose("Uncensored or standard?", [
            ("uncensored", "Uncensored (abliterated): answers anything you ask, the usual pick for a companion"),
            ("standard", "Standard: Qwen's own release, which turns down some requests")],
            "uncensored" if uncensored else "standard") == "uncensored"
    state["flavour"] = "uncensored" if uncensored else "standard"

    key, label, repo, file, size, mmproj, _least, ctx, lms_name = variant(m, uncensored)
    if vram:
        ok(f"{vram} GB to work with ({where})")
    else:
        warn(f"{where} - picking a small model that also runs on the CPU (slower)")
    print(f"  {label}: {size} GB{', with vision' if mmproj else ''}, {ctx // 1024}k context")

    if not ARGS.yes and choice == "auto":
        rows = [variant(r, uncensored) for r in MODELS]
        options = [(r[0], f"{r[1]} ({r[4]} GB{', sees' if r[5] else ''})"
                    + (" - too big for this machine" if vram and r[6] > vram else "")) for r in rows]
        key = choose("Which model?", options, key)
        key, label, repo, file, size, mmproj, _least, ctx, lms_name = variant(_model_by_key(key), uncensored)

    if state.get("backend") == "llama":
        dest_dir = os.path.join(ROOT, "llama", "models")
        dest = os.path.join(dest_dir, file)
        got = os.path.exists(dest) or (ask(f"Download {label} ({size} GB) into llama/models?")
                                       and download(HF.format(repo=repo, file=file), dest))
        if got and mmproj and not os.path.exists(os.path.join(dest_dir, mmproj)):
            download(HF.format(repo=repo, file=mmproj), os.path.join(dest_dir, mmproj))
        if not got:
            note("model", False, "not downloaded - put a GGUF in llama/models")
            return
        local = os.path.join(ROOT, "llama", "server.local.env")
        if os.path.exists(local) and not ask("llama/server.local.env exists - point it at this model?", default=False):
            note("model", True, f"{label} in llama/models (server.local.env left as it was)")
            return
        mm = os.path.join(dest_dir, mmproj) if mmproj and os.path.exists(os.path.join(dest_dir, mmproj)) else "off"
        _write_local_env({"MODEL": dest, "MMPROJ": mm, "CTX": ctx, "ALIAS": ""})
        state["model"] = key
        note("model", True, f"{label}, set in llama/server.local.env")
        return

    # LM Studio: its own command line can fetch it
    lms = shutil.which("lms") or next((p for p in (os.path.expanduser("~/.lmstudio/bin/lms"),
                                                  os.path.expanduser("~/.lmstudio/bin/lms.exe"))
                                       if os.path.exists(p)), None)
    if lms and ask(f"Download {label} with LM Studio ({size} GB)?"):
        good = run([lms, "get", lms_name, "--gguf"])
        state["model"] = key if good else state.get("model")
        note("model", good, f"{label} in LM Studio - load it and start the server"
             if good else "LM Studio couldn't fetch it - search it in the app")
    else:
        print(f"  In LM Studio: search \"{lms_name.split('@')[0]}\" and pick {lms_name.split('@')[1].upper()}.")
        note("model", False, f"get {label} in LM Studio")


# ---------------------------------------------------------------------------
# 6. Extras that aren't pip packages
# ---------------------------------------------------------------------------
def extras_files(extras):
    if "live2d" in extras:
        step("Live2D runtime")
        dest = os.path.join(ROOT, "portrait", "viewer", "vendor", "live2dcubismcore.min.js")
        if os.path.exists(dest):
            ok("already here")
        else:
            print("  Live2D's own code, under their licence: https://www.live2d.com/eula/")
            got = download(CUBISM_URL, dest)
            note("live2d runtime", got, "" if got else
                 "not fatal: the portrait loads it from Live2D's site instead. "
                 "To keep a copy: bash portrait/viewer/vendor/get_cubism_core.sh")
    if "embeddings" in extras:
        step("Embedding model")
        dest = os.path.join(ROOT, "llama", "models", os.path.basename(EMBED_URL))
        if os.path.exists(dest):
            ok("already here")
        elif ask("Download the 600 MB embedding model?"):
            note("embedding model", download(EMBED_URL, dest), "used by llama/start.sh")
    if "reranker" in extras:
        step("Reranker model")
        dest = os.path.join(ROOT, "llama", "models", os.path.basename(RERANK_URL))
        if os.path.exists(dest):
            ok("already here")
        elif ask("Download the 640 MB reranker model?"):
            note("reranker model", download(RERANK_URL, dest), "used by llama/start.sh (RERANK in server.env)")


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
            # pause on a crash, so the window stays open long enough to read why
            f.write(f'@echo off\r\ncd /d "{ROOT}"\r\n"{py}" "{launch}" %*\r\nif errorlevel 1 pause\r\n')
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
        with open(cmd, "w", encoding="utf-8") as f:
            f.write(f'#!/bin/bash\nexec "{script}" "$@"\n')
        os.chmod(cmd, 0o755)
        ok("Luna.command - double-click it in Finder")
    elif ask("Add Luna to your app launcher?"):
        apps = os.path.expanduser("~/.local/share/applications")
        os.makedirs(apps, exist_ok=True)
        entry = os.path.join(apps, "luna.desktop")
        with open(entry, "w", encoding="utf-8") as f:
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
    example = os.path.join(ROOT, "config.example.json")
    if not os.path.exists(path) and os.path.exists(example):
        # config.json is yours and not in git: a fresh clone starts from the defaults
        shutil.copyfile(example, path)
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
    ap.add_argument("--model", default="auto")
    ap.add_argument("--standard", action="store_true",
                    help="Qwen's own release instead of the uncensored (abliterated) one")
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
                if key in ("embeddings", "reranker") and ARGS.backend not in (None, "llama"):
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
    model(state)
    save_state(state)
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
