"""make_texture: Luna runs portrait/texture.py for you.

    > "Make the bra black lace with a pink trim."
    > "Give me three ice-blue iris options."

Same presets, same ComfyUI, same output folder (~/luna-textures) as the
command line. Only offered while ComfyUI answers, and never to stream
chat (it isn't in the chat tool ceiling).
"""
import importlib.util
import os
import time
import urllib.request

import config
from core import logbook

from . import tool

_SCRIPT = os.path.join(config.BASE_DIR, "portrait", "texture.py")
_mod = {"m": None}
_up = {"ok": None, "at": 0.0}


def _texture():
    if _mod["m"] is None:
        spec = importlib.util.spec_from_file_location("luna_texture", _SCRIPT)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _mod["m"] = m

    return _mod["m"]


def _url():
    return str(getattr(config, "COMFY_URL", "") or "http://127.0.0.1:8188")


def _available():
    # Checked at most every 30s: a turn shouldn't wait on a ComfyUI that isn't there.
    if time.monotonic() - _up["at"] > 30:
        try:
            urllib.request.urlopen(_url() + "/system_stats", timeout=0.5).close()
            _up["ok"] = True
        except Exception:
            _up["ok"] = False

        _up["at"] = time.monotonic()

    return bool(_up["ok"]) and os.path.exists(_SCRIPT)


def _parts():
    try:
        return sorted(_texture().presets())
    except Exception:
        return []


@tool(
    "make_texture",
    "Generate a texture for a part of her 3D model from its template, through ComfyUI: "
    "clothing fabric, irises, skin details. part is a preset name (bra, panties, irises, ...); "
    "description is what it should look like. Saves PNGs the user loads in VRoid; takes "
    "about half a minute each.",
    {
        "part": {"type": "string", "description": "Which preset, e.g. irises, bra, panties."},
        "description": {"type": "string", "description": "What it should look like, e.g. 'black lace with a pink trim'."},
        "count": {"type": "integer", "description": "How many versions to make, 1-4. Default 1."},
    },
    required=("part", "description"),
    available=_available,
    why=lambda: f"ComfyUI isn't answering at {_url()} (comfyui.url in config.json)",
)
def _make_texture(part, description, count=1):
    parts = _parts()

    if part not in parts:
        return f"No texture preset called {part!r}. There are: {', '.join(parts) or 'none'}."

    try:
        count = max(1, min(4, int(count or 1)))
    except (TypeError, ValueError):
        count = 1

    try:
        saved = _texture().generate(part, str(description), count=count, comfy_url=_url(),
                                    log=lambda line: logbook.info("texture", "%s", line.strip()))
    except Exception as e:
        return f"Couldn't make it: {e}"

    try:
        import ui

        ui.add_message("system", "Textures saved: " + ", ".join(saved))
    except Exception:
        pass

    return (f"Made {len(saved)} {part} texture{'s' if len(saved) != 1 else ''}: " + ", ".join(saved)
            + ". Tell the user where they are; they load them in VRoid's texture editor as a layer.")
