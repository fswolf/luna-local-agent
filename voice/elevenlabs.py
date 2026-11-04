"""Her voice from ElevenLabs instead of a speech server at home.

Off unless tts.provider is "elevenlabs". Everything else about her voice
stays the same - chunking, emoji left unspoken, mood speed and pitch,
volume, lip sync - only where the sound comes from changes. It is the one
part of her that then leaves the house: each sentence she says is sent to
ElevenLabs to be spoken, so the docs say so plainly.

The key lives outside the repo, like every other credential:

    ~/.config/ai-voice/elevenlabs.json   {"api_key": "..."}

or the ELEVENLABS_API_KEY environment variable. The voice, model and the
optional voice settings are ordinary settings in config.json:

    "tts": {
        "provider": "elevenlabs",
        "elevenlabs": {"voice_id": "...", "model": "eleven_flash_v2_5"}
    }

/voice lists the voices on the account and `/voice <name>` picks one.
"""
import json
import os

import numpy as np
import requests

import config
from core import logbook, safe

API = "https://api.elevenlabs.io"
CREDENTIALS_FILE = os.path.expanduser("~/.config/ai-voice/elevenlabs.json")
RATE = 24000                       # pcm_24000: raw 16-bit mono, the rate Kokoro uses too
# ElevenLabs takes speed from 0.7 to 1.2; her mood and tts.speed are squeezed into that.
SPEED_RANGE = (0.7, 1.2)


def enabled():
    return str(getattr(config, "TTS_PROVIDER", "kokoro")).lower() == "elevenlabs"


def api_key():
    """The key, or "" - from the environment, else the credentials file."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(CREDENTIALS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as e:
        logbook.warn("tts", "%s can't be read: %s", CREDENTIALS_FILE, e)
        return ""
    return str(data.get("api_key") or "").strip() if isinstance(data, dict) else ""


def why_not():
    """What's missing before she can speak through ElevenLabs, or ""."""
    if not api_key():
        return f"no ElevenLabs API key - put {{\"api_key\": \"...\"}} in {CREDENTIALS_FILE}"
    if not voice_id():
        return "no ElevenLabs voice picked - /voice lists yours, /voice <name> picks one"
    return ""


def voice_id():
    return str(getattr(config, "ELEVENLABS_VOICE_ID", "") or "").strip()


def _headers():
    return {"xi-api-key": api_key(), "Accept": "application/json"}


def _explain(response):
    """An ElevenLabs refusal in words: the message from its JSON when there
    is one, otherwise the status."""
    detail = ""
    try:
        data = response.json()
        body = data.get("detail", data) if isinstance(data, dict) else data
        if isinstance(body, dict):
            detail = str(body.get("message") or body.get("status") or body)
        else:
            detail = str(body)
    except ValueError:
        detail = (response.text or "").strip()
    detail = detail.replace("\n", " ")[:200]
    hint = {401: "the API key was refused", 402: "the account is out of credit",
            404: "no voice with that id", 429: "too many requests or out of quota"}.get(response.status_code, "")
    return f"ElevenLabs said no (HTTP {response.status_code}{': ' + hint if hint else ''}){': ' + detail if detail else ''}"


def synthesize(text, speed=1.0):
    """One chunk of her words -> (float32 samples in [-1, 1], sample rate).
    Raises RuntimeError with a readable reason; tts.py turns that into the
    same handling a local server's failure gets."""
    missing = why_not()
    if missing:
        raise RuntimeError(missing)

    settings = {"speed": safe.number(speed, 1.0, *SPEED_RANGE)}
    for key, value in (("stability", getattr(config, "ELEVENLABS_STABILITY", None)),
                       ("similarity_boost", getattr(config, "ELEVENLABS_SIMILARITY", None))):
        if value is not None and value != "":
            settings[key] = safe.number(value, 0.5, 0.0, 1.0)

    try:
        response = requests.post(
            f"{API}/v1/text-to-speech/{voice_id()}",
            params={"output_format": f"pcm_{RATE}"},
            headers=dict(_headers(), **{"Content-Type": "application/json"}),
            json={"text": text, "model_id": getattr(config, "ELEVENLABS_MODEL", "") or "eleven_flash_v2_5",
                  "voice_settings": settings},
            timeout=(10, 60),
        )
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"couldn't reach ElevenLabs: {e}") from e

    if response.status_code >= 400:
        raise RuntimeError(_explain(response))

    raw = response.content or b""
    if len(raw) % 2:
        raw = raw[:-1]                     # half a sample at the end of a cut-off reply
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return np.clip(samples, -1.0, 1.0), RATE


def health():
    """(ok, why) - can she speak through ElevenLabs right now? One cheap
    request: the first page of the account's voices."""
    missing = why_not()
    if missing:
        return False, missing
    try:
        response = requests.get(f"{API}/v2/voices", params={"page_size": 1, "include_total_count": "false"},
                                headers=_headers(), timeout=10)
    except requests.exceptions.RequestException as e:
        return False, f"couldn't reach ElevenLabs: {e}"
    if response.status_code >= 400:
        return False, _explain(response)
    return True, ""


def voices(limit=100):
    """[(name, voice_id, category)] on the account (premade ones included),
    or raises RuntimeError."""
    if not api_key():
        raise RuntimeError(why_not())
    out, token = [], None
    for _ in range(5):                                  # 5 pages of 100 is plenty to pick from
        params = {"page_size": 100, "include_total_count": "false"}
        if token:
            params["next_page_token"] = token
        try:
            response = requests.get(f"{API}/v2/voices", params=params, headers=_headers(), timeout=10)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"couldn't reach ElevenLabs: {e}") from e
        if response.status_code >= 400:
            raise RuntimeError(_explain(response))
        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("ElevenLabs didn't answer with a list of voices") from None
        for v in (data.get("voices") or []) if isinstance(data, dict) else []:
            if isinstance(v, dict) and v.get("voice_id"):
                out.append((str(v.get("name") or "?"), str(v["voice_id"]), str(v.get("category") or "")))
        token = data.get("next_page_token") if isinstance(data, dict) else None
        if not (isinstance(data, dict) and data.get("has_more") and token) or len(out) >= limit:
            break
    return out[:limit]


def find(name, listed):
    """A voice from voices() by name (any case, or the start of it) or by id."""
    wanted = str(name).strip().lower()
    for n, vid, _ in listed:
        if wanted in (n.lower(), vid.lower()):
            return n, vid
    starts = [(n, vid) for n, vid, _ in listed if n.lower().startswith(wanted)]
    return starts[0] if len(starts) == 1 else None
