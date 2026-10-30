"""Her trained patches, in llama/patches/ (docs/patches.md).

Each patch is <name>.gguf with <name>.json beside it, written by
training/train.sh: {"kind", "for", "base", "examples", "trained", ...}.
"for" is the GGUF it was trained for, by file name. A patch only fits that
model, so llama/start.sh loads only the ones whose "for" is the model it's
starting (and writes that model's name to llama/patches/.current_model).
Change the model and the old patches simply stay out until one is trained
for the new one.

Here: what's there, what fits, and, while llama-server runs, what's loaded
and how strongly (its /lora-adapters).
"""
import json
import os
import urllib.request

import config

FOLDER = os.path.join(config.BASE_DIR, "llama", "patches")


def current_model():
    """The GGUF llama/start.sh last started, by file name (no .gguf), or ''."""
    try:
        with open(os.path.join(FOLDER, ".current_model"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def local():
    """[{name, file, kind, for, examples, trained, fits}] for every patch on disk."""
    out, model = [], current_model()
    try:
        names = sorted(f[:-5] for f in os.listdir(FOLDER) if f.endswith(".gguf"))
    except OSError:
        return []
    for name in names:
        meta = {}
        try:
            with open(os.path.join(FOLDER, name + ".json"), encoding="utf-8") as f:
                meta = json.load(f) or {}
        except (OSError, ValueError):
            pass
        made_for = str(meta.get("for") or "")
        out.append({"name": name, "file": os.path.join(FOLDER, name + ".gguf"), "kind": str(meta.get("kind") or "?"),
                    "for": made_for, "examples": meta.get("examples"), "trained": str(meta.get("trained") or ""),
                    "fits": bool(made_for) and made_for == model})
    return out


def _root():
    return str(getattr(config, "LLAMA_URL", "http://127.0.0.1:8080/v1/chat/completions")).split("/v1/")[0]


def _auth():
    key = str(getattr(config, "LLAMA_API_KEY", "") or "")
    return {"Authorization": f"Bearer {key}"} if key else {}


def _call(method="GET", body=None):
    req = urllib.request.Request(_root() + "/lora-adapters", method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **_auth()})
    with urllib.request.urlopen(req, timeout=3) as r:
        text = r.read().decode() or "null"
    return json.loads(text)


def loaded():
    """[{id, path, scale}] llama-server has loaded, or None when it isn't answering."""
    try:
        rows = _call()
    except Exception:
        return None
    return [{"id": r.get("id"), "path": str(r.get("path") or ""), "scale": r.get("scale")} for r in rows or []]


def set_scale(which, scale):
    """Change one loaded patch's strength while she runs (0 = off, 1 = full).
    which: its id or (part of) its name. Returns the patch, or ValueError."""
    scale = max(0.0, min(2.0, float(scale)))
    rows = loaded()
    if rows is None:
        raise ValueError("llama-server isn't answering")
    pick = next((r for r in rows if str(r["id"]) == str(which)), None) or \
        next((r for r in rows if str(which).lower() in os.path.basename(r["path"]).lower()), None)
    if not pick:
        raise ValueError(f"no loaded patch {which!r}")
    # the whole list goes back: one left out would drop to 0
    _call("POST", [{"id": r["id"], "scale": scale if r["id"] == pick["id"] else r["scale"]} for r in rows])
    return dict(pick, scale=scale)
