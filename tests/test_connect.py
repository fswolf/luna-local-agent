"""Connect a model (web/connect.py): what answers where, what's saved, and
the page. Fake servers on 127.0.0.1 only; no real model server.

    python -m unittest discover tests        (from the repo folder)
"""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.offline  # noqa: F401,E402  (first: no real servers)

from web import connect  # noqa: E402


def fake(kind, models=("qwen",), key=""):
    """A model server: "llama" (has /props), "studio" (has /api/v0/models) or "plain"."""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if key and self.headers.get("Authorization") != f"Bearer {key}":
                self.send_response(401)
                self.end_headers()
                return
            path = self.path.split("?")[0]
            if path == "/v1/models":
                body = {"data": [{"id": m} for m in models]}
            elif path == "/props" and kind == "llama":
                body = {}
            elif path == "/api/v0/models" and kind == "studio":
                body = {"data": []}
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def local_urlopen():
    """tests/offline.py stops urlopen for the whole run; these classes talk
    only to the fakes they start on 127.0.0.1, so they get a real one (no proxy)."""
    import urllib.request

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return mock.patch.object(urllib.request, "urlopen",
                             lambda req, timeout=None: opener.open(req, timeout=timeout))


class Addresses(unittest.TestCase):
    def test_what_people_type(self):
        b = connect.base_of
        self.assertEqual(b("192.168.1.50:8080"), "http://192.168.1.50:8080")
        self.assertEqual(b("box"), "http://box:8080")
        self.assertEqual(b("http://box:1234/v1/chat/completions"), "http://box:1234")
        self.assertEqual(b(" https://ai.example.com:443/ "), "https://ai.example.com:443")
        self.assertEqual(b("[::1]:8080"), "http://[::1]:8080")
        for bad in ("", "  ", "a b", "http://", "box:99999", "ftp://x", None):
            self.assertIsNone(b(bad), bad)


class Probe(unittest.TestCase):
    def setUp(self):
        self.servers = []
        self.net = local_urlopen()
        self.net.start()
        self.cfg = mock.patch.object(connect, "llm_settings", return_value={})     # not this checkout's config.json
        self.cfg.start()

    def tearDown(self):
        self.cfg.stop()
        self.net.stop()
        for s in self.servers:
            s.shutdown()
            s.server_close()

    def serve(self, *a, **k):
        server, base = fake(*a, **k)
        self.servers.append(server)
        return base

    def test_kinds(self):
        self.assertEqual(connect.probe(self.serve("llama"))["kind"], "llama.cpp")
        self.assertEqual(connect.probe(self.serve("studio"))["kind"], "LM Studio")
        p = connect.probe(self.serve("plain", models=("a", "b")))
        self.assertEqual((p["ok"], p["kind"], p["model"]), (True, "model server", "a"))

    def test_nothing_loaded_isnt_enough(self):
        p = connect.probe(self.serve("studio", models=()))
        self.assertFalse(p["ok"])
        self.assertIn("no model is loaded", p["why"])

    def test_a_key(self):
        base = self.serve("llama", key="sekrit")
        self.assertTrue(connect.probe(base)["needs_key"])
        self.assertIn("didn't take", connect.probe(base, "wrong")["why"])
        self.assertTrue(connect.probe(base, "sekrit")["ok"])

    def test_a_pinned_model_must_be_there(self):
        """llm.model: main.py asks for that one or none, so another isn't connected."""
        base = self.serve("llama", models=("a", "b"))
        with mock.patch.object(connect, "llm_settings", return_value={"model": "c"}):
            p = connect.probe(base)
        self.assertFalse(p["ok"])
        self.assertIn("doesn't have c", p["why"])
        with mock.patch.object(connect, "llm_settings", return_value={"model": "b"}):
            self.assertEqual(connect.probe(base)["model"], "b")

    def test_typed_address_uses_the_key_she_has(self):
        base = self.serve("llama", key="fromfile")
        connect.S.__init__()
        with mock.patch.object(connect, "saved_key", return_value=""), \
                mock.patch.object(connect, "llama_key", return_value="fromfile"), \
                mock.patch.object(connect, "save") as saved:
            r = connect.try_address(json.dumps({"address": base}).encode())
        self.assertTrue(r["ok"])
        saved.assert_called_once()

    def test_nothing_there(self):
        p = connect.probe("http://127.0.0.1:9", timeout=0.5)
        self.assertEqual((p["ok"], p["why"]), (False, "nothing answered there"))


class Saving(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfg, self.keys = os.path.join(self.dir, "config.json"), os.path.join(self.dir, "keys", "llm.json")
        with open(self.cfg, "w") as f:
            json.dump({"voice": "af_bella", "llm": {"backend": "auto", "llama_url": "http://127.0.0.1:8080/v1/chat/completions",
                                                     "lmstudio_url": "http://localhost:1234/v1/chat/completions"}}, f)
        self.p = [mock.patch.object(connect, "CONFIG", self.cfg), mock.patch.object(connect, "KEYS", self.keys)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def read(self):
        with open(self.cfg) as f:
            return json.load(f)

    def test_another_computers_llama(self):
        connect.save({"kind": "llama.cpp", "base": "http://192.168.1.50:8080"}, key="k1")
        cfg = self.read()
        self.assertEqual(cfg["llm"]["backend"], "llama")
        self.assertEqual(cfg["llm"]["llama_url"], "http://192.168.1.50:8080/v1/chat/completions")
        self.assertEqual(cfg["voice"], "af_bella")                   # the rest left alone
        with open(self.keys) as f:
            self.assertEqual(json.load(f), {"api_key": "k1"})
        self.assertNotIn("k1", open(self.cfg).read())               # never in config.json

    def test_any_other_server_goes_in_lmstudio_url(self):
        connect.save({"kind": "model server", "base": "http://box:11434"})
        llm = self.read()["llm"]
        self.assertEqual((llm["backend"], llm["lmstudio_url"]), ("lmstudio", "http://box:11434/v1/chat/completions"))

    def test_what_config_already_finds_is_left_as_it_was(self):
        before = os.path.getmtime(self.cfg)
        os.utime(self.cfg, (before - 100, before - 100))
        connect.save({"kind": "LM Studio", "base": "http://localhost:1234"})
        self.assertEqual(self.read()["llm"]["backend"], "auto")
        self.assertEqual(os.path.getmtime(self.cfg), before - 100)


class Places(unittest.TestCase):
    def test_config_first_then_the_usual_ports_once_each(self):
        llm = {"backend": "lmstudio", "lmstudio_url": "http://box:1234/v1/chat/completions",
               "llama_url": "http://127.0.0.1:8080/v1/chat/completions"}
        with mock.patch.object(connect, "llm_settings", return_value=llm), \
                mock.patch.object(connect, "saved_key", return_value=""), mock.patch.object(connect, "llama_key", return_value=""):
            bases = [b for _w, b, _k in connect.places()]
        self.assertEqual(bases, ["http://box:1234", "http://127.0.0.1:8080", "http://localhost:1234"])


class Keys(unittest.TestCase):
    """The key each place gets is the one Luna would send (config/server.py)."""

    def test_which_key_where(self):
        with mock.patch.object(connect, "saved_key", return_value="json"), \
                mock.patch.object(connect, "llama_key", return_value="file"):
            self.assertEqual(connect.key_for("llama.cpp", "http://192.168.1.50:8080"), "json")
            self.assertEqual(connect.key_for("llama.cpp", "http://127.0.0.1:8080"), "file")
            self.assertEqual(connect.key_for("LM Studio", "http://localhost:1234"), "json")
        # a key copied from the server into server/llama/.api_key, and no llm.json
        with mock.patch.object(connect, "saved_key", return_value=""), \
                mock.patch.object(connect, "llama_key", return_value="file"):
            self.assertEqual(connect.key_for("llama.cpp", "http://192.168.1.50:8080"), "file")


class Page(unittest.TestCase):
    def setUp(self):
        connect.S.__init__()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), connect.Page)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def ask(self, method, path, body=None, origin=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if origin:
            headers["Origin"] = origin
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        out = r.status, r.read()
        c.close()
        return out

    def test_page_status_and_logo(self):
        self.assertIn(b"Connect Luna", self.ask("GET", "/")[1])
        self.assertIn("looking", json.loads(self.ask("GET", "/status")[1]))
        self.assertEqual(self.ask("GET", "/logo.png")[1][:4], b"\x89PNG")

    def test_other_sites_cant_use_it(self):
        self.assertEqual(self.ask("POST", "/try", b'{"address":"x"}', origin="http://evil.example")[0], 403)
        self.assertEqual(self.ask("POST", "/close", b"{}", origin="http://evil.example")[0], 403)
        self.assertFalse(connect.S.closed)

    def test_a_bad_address_is_said(self):
        r = json.loads(self.ask("POST", "/try", b'{"address":"not an address"}')[1])
        self.assertFalse(r["ok"])
        self.assertIn("doesn't look like an address", r["why"])

    def test_not_now(self):
        self.ask("POST", "/close", b"{}")
        self.assertTrue(connect.S.closed)


class Waiting(unittest.TestCase):
    def test_one_already_there_goes_straight_on(self):
        connect.S.__init__()
        with mock.patch.object(connect, "places", return_value=[("LM Studio", "http://x", "")]), \
                mock.patch.object(connect, "probe", return_value={"ok": True, "kind": "LM Studio", "base": "http://x",
                                                                   "model": "q", "why": "", "needs_key": False}), \
                mock.patch.object(connect, "save") as saved, mock.patch.object(connect, "_open") as opened:
            self.assertTrue(connect.wait(show=True, say=lambda *_: None))
        opened.assert_not_called()                     # no window when there's nothing to ask
        saved.assert_called_once()

    def test_not_now_ends_it(self):
        connect.S.__init__()
        connect.S.closed = True
        with mock.patch.object(connect, "look_once", return_value=False), mock.patch.object(connect, "LOOK_EVERY", 0.01), \
                mock.patch.object(connect, "SHOWING", os.path.join(tempfile.mkdtemp(), "connect.url")):
            self.assertFalse(connect.wait(show=False, say=lambda *_: None))


class SetItUp(unittest.TestCase):
    """"Set it up for me": the installer's output reaches the page, and a
    finished setup points her at llama.cpp and starts it. A stand-in installer."""

    FAKE = r"""import os, sys
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print("== Model server")
print("  downloading llama.cpp")
print("    50% of 35 MB")
if "--standard" in sys.argv:
    print("  ✗ pretend it failed")
    sys.exit(1)
os.makedirs(os.path.join(root, "server", "llama", "bin"), exist_ok=True)
open(os.path.join(root, "server", "llama", "bin", "llama-server"), "w").close()
model = os.path.join(root, "server", "llama", "models", "m.gguf")
os.makedirs(os.path.dirname(model), exist_ok=True)
open(model, "w").close()
with open(os.path.join(root, "server", "llama", "server.local.env"), "w") as f:
    f.write('MODEL="%s"\n' % model)
print("== Model")
print("  ✓ Qwen3.5 4B")
print("== Summary")
print("  ✓ model server")
"""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "installer"))
        with open(os.path.join(self.root, "installer", "install.py"), "w", encoding="utf-8") as f:
            f.write(self.FAKE)
        connect.S.__init__()
        self.p = [mock.patch.object(connect, "ROOT", self.root), mock.patch.object(connect, "save")]
        self.saved = None
        for p in self.p:
            started = p.start()
            if p is self.p[1]:
                self.saved = started

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_done_then_started(self):
        server = object()
        connect.S.start = lambda: server
        connect.run_setup()
        s = json.loads(connect.S.snapshot())["setup"]
        self.assertEqual(s["state"], "done")
        self.assertIn("    50% of 35 MB", s["log"])
        self.assertIs(connect.S.server, server)
        self.saved.assert_called_once_with({"kind": "llama.cpp", "base": "http://127.0.0.1:8080"})
        self.assertTrue(connect.llama_ready())

    def test_a_failure_is_said(self):
        connect.S.start = lambda: self.fail("nothing to start")
        connect.run_setup(standard=True)
        s = connect.S.setup
        self.assertEqual(s["state"], "failed")
        self.assertEqual(s["errors"], ["pretend it failed"])
        self.saved.assert_not_called()

    def test_set_up_but_wont_start(self):
        connect.S.start = lambda: None
        connect.run_setup()
        self.assertEqual(connect.S.setup["state"], "failed")
        self.assertIn("didn't start", connect.S.setup["errors"][0])

    def test_another_server_found_meanwhile_stands(self):
        connect.S.start = lambda: self.fail("nothing to start: she has one")
        connect.S.found = {"ok": True, "kind": "LM Studio", "base": "http://localhost:1234", "model": "q"}
        connect.run_setup()
        self.assertEqual(connect.S.setup["state"], "done")
        self.saved.assert_not_called()

    def test_only_where_it_can(self):
        with mock.patch.object(connect.sys, "platform", "win32"):
            self.assertFalse(connect.can_setup())
        with mock.patch.object(connect.sys, "platform", "darwin"):
            self.assertTrue(connect.can_setup())


if __name__ == "__main__":
    unittest.main()
