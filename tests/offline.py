"""Imported first by every test module: the tests never reach a real server.

LM Studio, llama-server, the embedding server or ComfyUI may well be
running on this machine, and importing config (backend detection) or
running a turn would happily ask them things. Only a fake server a test
starts itself (added to FAKE) answers. Patched once, for the whole run.
"""
import os
import sys
import urllib.error
import urllib.request
from unittest import mock

import requests

# Packages that need hardware or weigh gigabytes (an audio device for
# sounddevice, CTranslate2 models for faster-whisper) and that no test
# uses for real: when they aren't installed - on GitHub's test machines,
# say - an empty stand-in lets the modules that import them load.
_STANDINS = {
    "sounddevice": "def get_stream(): return None\ndef stop(): pass\n"
                   "def _terminate(): pass\ndef _initialize(): pass\n"
                   "class InputStream:\n    def __init__(self, **kw): pass\n"
                   "class OutputStream(InputStream): pass\n",
    "faster_whisper": "class WhisperModel:\n    def __init__(self, *a, **kw): pass\n",
}
for _name, _code in _STANDINS.items():
    try:
        __import__(_name)
    except Exception:            # missing, or (sounddevice) no PortAudio on the machine
        import types

        _module = types.ModuleType(_name)
        exec(_code, _module.__dict__)
        sys.modules[_name] = _module

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAKE = []
_real_request = requests.sessions.Session.request


def _offline(self, method, url, *args, **kwargs):
    if any(str(url).startswith(base) for base in FAKE):
        return _real_request(self, method, url, *args, **kwargs)
    raise requests.ConnectionError(f"tests stay offline: {url}")


def _no_urlopen(*args, **kwargs):
    raise urllib.error.URLError("tests stay offline")


mock.patch.object(requests.sessions.Session, "request", _offline).start()
mock.patch.object(urllib.request, "urlopen", _no_urlopen).start()
