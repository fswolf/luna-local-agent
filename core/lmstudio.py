"""Whether the model server is actually there, and which model it's holding.

LM Studio or llama-server - config.LLM_BACKEND says which was found at
startup. The name is history; the two speak the same API for
everything here except context_length(), which asks each its own way.

The TTS server has had reachability tracking since the kokoro-reader
migration: a failed request flips a flag, the header shows [offline],
and it recovers on its own when the server comes back. LM Studio had
none of that. It was checked once at startup and never again, so if it
crashed, or you unloaded the model to free VRAM, or swapped to a
different one, every turn from then on failed with a raw error and no
indication of why.

That is the same problem twice, so this is the same solution twice.
"""
import re
import threading
import time

import requests

from config import LM_URL, LLM_BACKEND, LLM_HEADERS, LLM_MODEL

MODELS_URL = LM_URL.replace("/chat/completions", "/models")
# LM Studio's own (non-OpenAI) endpoint: the only place it reports the
# context length a model was actually loaded with.
NATIVE_MODELS_URL = LM_URL.split("/v1/")[0] + "/api/v0/models"
# llama-server's equivalent: what it was started with, n_ctx included.
PROPS_URL = LM_URL.split("/v1/")[0] + "/props"

_lock = threading.Lock()

ok = False
error = ""
model = ""
# Set when the loaded model changes underneath us, so the turn that
# notices can say so rather than silently answering as someone else.
changed_to = ""


def label():
    """The Model row: what's loaded, or why nothing is."""
    tag = " · llama.cpp" if LLM_BACKEND == "llama" else ""

    with _lock:
        if ok:
            return (model or "unknown") + tag

        if not model:
            return f"offline ({error})" if error else "offline"

        return f"{model}{tag} [offline]"


def probe(timeout=5):
    """Ask what's loaded. Returns the model id, or "" if unreachable."""
    global ok, error, model, changed_to

    try:
        response = requests.get(MODELS_URL, headers=LLM_HEADERS, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        ids = [m.get("id", "") for m in data.get("data") or []]
        loaded = ids[0] if ids else ""
    except Exception as e:
        _set(False, _short(e))

        return ""

    if LLM_MODEL:
        # pinned: that one or nothing, never a silent stand-in
        if LLM_MODEL not in ids:
            _set(False, f"{LLM_MODEL} isn't on the server")
            return ""
        loaded = LLM_MODEL
    elif LLM_BACKEND != "llama" and len(ids) > 1:
        # LM Studio lists every downloaded model; the one actually loaded
        # is marked in its own API. Asking for another would JIT-load it.
        try:
            for entry in requests.get(NATIVE_MODELS_URL, headers=LLM_HEADERS, timeout=2).json().get("data") or []:
                if entry.get("state") == "loaded" and entry.get("id") in ids:
                    loaded = entry["id"]
                    break
        except Exception:
            pass

    with _lock:
        previous = model

    _set(True, "", loaded)

    if previous and loaded and loaded != previous:
        with _lock:
            changed_to = loaded

    return loaded


def _set(reachable, why="", loaded=None):
    global ok, error, model

    with _lock:
        changed = reachable != ok
        ok = reachable
        error = why

        if loaded is not None:
            model = loaded

    if changed:
        try:
            import ui

            ui.set_model(label())
        except Exception:
            pass


def _short(error):
    """What the Model row says when the server is down. requests' own
    text is a paragraph ("HTTPConnectionPool(host=...): Max retries
    exceeded with url ... NewConnectionError(...)") that buries the one
    fact worth reading in a header."""
    if isinstance(error, requests.exceptions.ConnectionError) and not isinstance(
            error, requests.exceptions.Timeout):
        return f"nothing answering at {MODELS_URL.rsplit('/v1', 1)[0]}"
    if isinstance(error, requests.exceptions.Timeout):
        return "timed out"
    if isinstance(error, requests.exceptions.HTTPError) and error.response is not None:
        return f"HTTP {error.response.status_code}"
    text = str(error) or type(error).__name__
    return text if len(text) <= 120 else text[:117] + "..."


def mark_failed(why):
    """Called when a request fails mid-conversation."""
    _set(False, _short(why) if isinstance(why, BaseException) else str(why)[:120])


def mark_worked():
    if not ok:
        _set(True, "")


def take_change():
    """The new model id, once, if it changed since we last looked."""
    global changed_to

    with _lock:
        was, changed_to = changed_to, ""

    return was


def watch(interval=20):
    """Poll in the background so the header is right even between turns.

    Cheap - one GET every twenty seconds against a local server - and
    it means an unloaded model shows up in the header immediately
    instead of on the next thing you say.
    """
    def loop():
        while True:
            try:
                probe(timeout=4)
            except Exception:
                pass    # probe() reports its own failures; this only keeps the loop alive
            threading.Event().wait(interval)

    threading.Thread(target=loop, daemon=True).start()


def context_length(timeout=3):
    """Tokens the loaded model was given, or 0 if LM Studio won't say.

    This is the number every "HTTP 500" out of nowhere is really about:
    the prompt - persona, facts, summary, fifteen turns and the tool
    schemas - has to fit in it, and the schemas alone are a few
    thousand tokens now.
    """
    if LLM_BACKEND == "llama":
        try:
            response = requests.get(PROPS_URL, headers=LLM_HEADERS, timeout=timeout)
            response.raise_for_status()
            props = response.json()

            return int((props.get("default_generation_settings") or {}).get("n_ctx")
                       or props.get("n_ctx") or 0)
        except Exception:
            return 0

    try:
        response = requests.get(NATIVE_MODELS_URL, headers=LLM_HEADERS, timeout=timeout)
        response.raise_for_status()

        for entry in response.json().get("data") or []:
            if entry.get("state") == "loaded" or entry.get("loaded_context_length"):
                return int(entry.get("loaded_context_length")
                           or entry.get("max_context_length") or 0)
    except Exception:
        pass

    return 0


_senses = {"at": 0.0, "vision": None, "audio": None, "deaf_until": 0.0}


def _modalities(max_age=30):
    """What the loaded model takes besides text, as the server tells it:
    {"vision": True/False/None, "audio": True/False/None}, None where the
    server doesn't say. llama-server reports both in /props (False when it
    was started without the model's --mmproj); LM Studio marks vision
    models "type": "vlm" and says nothing about audio. Cached, so the tool
    list can ask every turn."""
    now = time.monotonic()

    if now - _senses["at"] < max_age:
        return _senses

    vision = audio = None

    try:
        if LLM_BACKEND == "llama":
            props = requests.get(PROPS_URL, headers=LLM_HEADERS, timeout=1).json()
            modalities = props.get("modalities") if isinstance(props, dict) else None

            if isinstance(modalities, dict):
                vision = bool(modalities.get("vision"))
                audio = bool(modalities.get("audio"))
        else:
            for entry in requests.get(NATIVE_MODELS_URL, headers=LLM_HEADERS, timeout=1).json().get("data") or []:
                if entry.get("state") == "loaded" and entry.get("type") in ("llm", "vlm"):
                    vision = entry.get("type") == "vlm"
                    break
    except Exception:
        pass

    _senses.update(at=now, vision=vision, audio=audio)

    return _senses


def accepts_images(max_age=30):
    """True / False if the server says whether the loaded model can see,
    None if it won't say."""
    return _modalities(max_age)["vision"]


def accepts_audio(max_age=30):
    """True / False if the server says whether the loaded model can hear
    (an omni model with its mmproj on llama-server), None if it won't say.
    False for a while after the server refused a recording (refused_audio)."""
    if time.monotonic() < _senses["deaf_until"]:
        return False
    return _modalities(max_age)["audio"]


def audio_refused():
    """Is hearing off for now because the server refused a recording?"""
    return time.monotonic() < _senses["deaf_until"]


def refused_audio():
    """The server turned a recording away after all: count the model as
    deaf for ten minutes, so the next turns go as words without asking.
    Only hearing: what it says about vision is untouched."""
    _senses["deaf_until"] = time.monotonic() + 600


# A screenshot travels as base64, hundreds of KB of it, but the model
# sees a few hundred to a couple of thousand tokens per image. Counting
# the base64 as text made every turn with a screenshot look 2-3x over
# the window, and the error hint blamed the context for it.
_IMAGE = re.compile(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]*")
_IMAGE_TOKENS = 1500
# A recording (voice/hearing.py) is the same story: 16-bit mono at
# SAMPLE_RATE, and omni models spend about 25 tokens a second on it.
_AUDIO = re.compile(r'"input_audio": \{"data": "([A-Za-z0-9+/=]*)"')
_AUDIO_TOKENS_PER_SECOND = 25


def _rate():
    try:
        import config

        return max(1, int(config.SAMPLE_RATE))
    except Exception:
        return 16000


def estimate_tokens(payload):
    """Rough size of a chat payload. 3.5 chars/token is close enough for
    English plus JSON to say "this is 90% of the window"."""
    try:
        import json

        text = json.dumps(payload)
        images = len(_IMAGE.findall(text))
        heard = sum(len(b) * 3 / 4 / (2 * _rate()) for b in _AUDIO.findall(text))
        text = _AUDIO.sub("", _IMAGE.sub("", text))

        return int(len(text) / 3.5) + images * _IMAGE_TOKENS + int(heard * _AUDIO_TOKENS_PER_SECOND)
    except Exception:
        return 0


def chore(body, max_tokens, think=0):
    """Make a background request (fact extraction, a summary, the mood
    rating) behave like the chore it is.

    Left alone, a thinking model on llama-server with REASONING_BUDGET=-1
    thinks without limit before replying NONE - a minute of the GPU
    flat out after every turn, for a one-word answer. On llama-server
    the budget goes to `think` (0 = off); LM Studio has no budget, so it
    gets room to think plus the same reasoning setting a turn uses."""
    import config

    body = dict(body)
    body.setdefault("temperature", 0.2)

    if LLM_BACKEND == "llama":
        body["reasoning_budget_tokens"] = int(think)
        body["max_tokens"] = int(max_tokens) + max(0, int(think))
    else:
        body["max_tokens"] = int(max_tokens) + 2048
        reasoning = (getattr(config, "GENERATION", None) or {}).get("reasoning")

        if reasoning:
            body["reasoning"] = reasoning

    return body
