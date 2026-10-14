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
