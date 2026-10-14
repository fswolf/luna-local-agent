"""Which model server (LM Studio or llama-server), its URL and key, and
the embedding and reranking servers.

Part of the config package (it was one config.py); see config/__init__.py.
"""
import json
import os

from .base import BASE_DIR, LM_URL, setting

# -------------------------
# Which model server
# -------------------------
# LM Studio, or llama.cpp's own llama-server (llama/start.sh), checked
# once at startup. Both speak the same OpenAI-style API, so everything
# that talks to the model just uses LM_URL; what differs is what each
# can do beyond it - llama-server exposes token probabilities, control
# vectors and the rest, LM Studio doesn't - and LLM_BACKEND is what
# those features check.
#
#   "llm": { "backend": "auto",
#            "lmstudio_url": "http://localhost:1234/v1/chat/completions",
#            "llama_url":    "http://127.0.0.1:8080/v1/chat/completions" }
#
# auto prefers llama-server when it's running - starting it is a
# deliberate act, LM Studio is the one that's usually just open - and
# falls back to LM Studio. Neither answering keeps LM Studio's address,
# so the startup error names the server most people will have.
_llm_cfg = setting("llm", {})
LM_STUDIO_URL = str(_llm_cfg.get("lmstudio_url", LM_URL))
LLAMA_URL = str(_llm_cfg.get("llama_url",
                             "http://127.0.0.1:8080/v1/chat/completions"))
LLM_BACKEND_WANTED = str(_llm_cfg.get("backend", "auto")).lower()
# The model id sent with every request. Empty: what the server has loaded
# (LM Studio: the one marked loaded; otherwise the first it lists). Set it
# on a server holding several - LM Studio with JIT loading, Ollama, vLLM -
# and if that model isn't there she says so instead of using another.
LLM_MODEL = str(_llm_cfg.get("model", "") or "").strip()


def _root(url):
    return url.split("/v1/")[0]


# llama/start.sh makes a random key the first time it runs and starts
# the server with it. Every request has to carry it, because a server
# on localhost is reachable by any web page open in the browser - and
# this one can write files (saved slots) and burn the GPU. LM Studio
# never sees it.
LLAMA_KEY_FILE = os.path.join(BASE_DIR, "llama", ".api_key")


def _llama_key():
    try:
        with open(LLAMA_KEY_FILE) as f:
            for line in f:
                line = line.strip()

                if line and not line.startswith("#"):
                    return line
    except OSError:
        pass

    return ""


LLAMA_API_KEY = _llama_key()
_LLAMA_HEADERS = {"Authorization": f"Bearer {LLAMA_API_KEY}"} if LLAMA_API_KEY else {}


def _answers(url, timeout=0.7, headers=None):
    import urllib.request

    try:
        request = urllib.request.Request(url, headers=headers or {})

        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def _pick_backend():
    """(backend, chat url). llama-server answers /props and LM Studio
    answers /api/v0/models; nothing else answers both, so each is
    recognised by the door only it has."""
    llama = ("llama", LLAMA_URL)
    studio = ("lmstudio", LM_STUDIO_URL)

    if LLM_BACKEND_WANTED.startswith("llama"):
        return llama

    if LLM_BACKEND_WANTED.startswith("lm"):
        return studio

    if _answers(_root(LLAMA_URL) + "/props", headers=_LLAMA_HEADERS):
        return llama

    return studio


LLM_BACKEND, LM_URL = _pick_backend()

# An API key for a model server that wants one (LM Studio with auth, vLLM
# --api-key, any OpenAI-compatible endpoint): llm.api_key in config.json,
# or better, outside the repo in ~/.config/ai-voice/llm.json as
# {"api_key": "..."}. llama/start.sh's own key is used for llama-server.
def _llm_key():
    try:
        with open(os.path.expanduser("~/.config/ai-voice/llm.json"), encoding="utf-8") as f:
            key = str((json.load(f) or {}).get("api_key") or "").strip()
            if key:
                return key
    except (OSError, ValueError):
        pass
    return str(_llm_cfg.get("api_key", "") or "").strip()


LLM_API_KEY = _llm_key()

# Sent with every request to the model server.
if LLM_BACKEND == "llama":
    LLM_HEADERS = dict(_LLAMA_HEADERS)
elif LLM_API_KEY:
    LLM_HEADERS = {"Authorization": f"Bearer {LLM_API_KEY}"}
else:
    LLM_HEADERS = {}

# The embedding server (started by llama/start.sh) for recalling facts by meaning.
# Optional: nothing needs it, and fact recall falls back to matching
# words whenever it isn't answering.
EMBED_URL = str(_llm_cfg.get("embed_url", "http://127.0.0.1:8081/v1/embeddings"))
EMBED_HEADERS = dict(_LLAMA_HEADERS)
# Qwen3-Embedding is trained with an instruction on the query side and
# none on the documents; other embedding models want this empty.
EMBED_QUERY_PREFIX = str(_llm_cfg.get(
    "embed_query_prefix",
    "Instruct: Given something the user just said, retrieve remembered "
    "facts about the user that are relevant to it\nQuery: ",
))
# How alike a fact must be to travel on meaning alone. Cosine, 0-1.
EMBED_MIN_SCORE = float(_llm_cfg.get("embed_min_score", 0.35))

# The reranker (also from llama/start.sh, :8082) re-orders the
# embedding's best matches by reading each one beside what was said.
# Optional too: when it isn't answering the embedding order stands.
# rerank_candidates is how many of the embedding's matches it reads.
RERANK_URL = str(_llm_cfg.get("rerank_url", "http://127.0.0.1:8082/v1/rerank"))
RERANK_CANDIDATES = int(_llm_cfg.get("rerank_candidates", 24))


def llm_backend_label():
    return "llama.cpp" if LLM_BACKEND == "llama" else "LM Studio"

