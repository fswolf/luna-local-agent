"""Finding the toy servers: only something that answers like Intiface or
the Lovense Remote app counts, and what's found is saved for /… on. A
fake Remote app on a local port; no network beyond this machine.

    python -m unittest discover tests        (from the repo folder)
"""
import http.server
import json
import os
import sys
import threading
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from plugins import _toyscan  # noqa: E402


class FakeRemote(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.dumps({"code": 200, "data": {"toys": json.dumps({"a1": {"name": "lush"}})}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class NotLovense(FakeRemote):
    def do_POST(self):
        self.send_response(404)
        self.end_headers()


def serve(handler):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Lovense(unittest.TestCase):
    def find(self, handler):
        server = serve(handler)
        port = server.server_address[1]
        FAKE.append(f"http://127.0.0.1:{port}")
        try:
            # tests/offline.py blocks urlopen for the whole run; this fake app is ours, on this machine
            import urllib.request
            local = lambda req, timeout=None, context=None: urllib.request.build_opener().open(req, timeout=timeout)  # noqa: E731
            with mock.patch("urllib.request.urlopen", local), \
                    mock.patch.object(_toyscan, "hosts", return_value=["127.0.0.1"]), \
                    mock.patch.object(_toyscan, "LOVENSE_HTTP", port), \
                    mock.patch.object(_toyscan, "LOVENSE_HTTPS", 1):
                return _toyscan.find_lovense(wake=False), port
        finally:
            FAKE.remove(f"http://127.0.0.1:{port}")
            server.shutdown()

    def test_the_remote_app_is_found_with_its_toys(self):
        found, port = self.find(FakeRemote)
        self.assertEqual(found, [("127.0.0.1", port, False, ["lush"])])

    def test_something_else_on_the_port_isnt(self):
        found, _port = self.find(NotLovense)
        self.assertEqual(found, [])


class Intiface(unittest.TestCase):
    def test_only_a_buttplug_server_counts(self):
        with mock.patch.object(_toyscan, "hosts", return_value=["127.0.0.1", "192.168.0.40", "192.168.0.9"]), \
                mock.patch.object(_toyscan, "open_on", return_value=["192.168.0.40", "192.168.0.9"]), \
                mock.patch.object(_toyscan, "_intiface_at",
                                  side_effect=lambda ip: "Intiface Central" if ip.endswith(".40") else ""):
            self.assertEqual(_toyscan.find_intiface(wake=False),
                             [("ws://192.168.0.40:12345", "Intiface Central")])

    def test_private_addresses_only(self):
        self.assertTrue(_toyscan._private("192.168.0.40"))
        self.assertFalse(_toyscan._private("8.8.8.8"))


class Saving(unittest.TestCase):
    def test_the_one_found_is_saved(self):
        from plugins import buttplug
        with mock.patch.object(buttplug, "_client", return_value=object()), \
                mock.patch.object(_toyscan, "find_intiface", return_value=[("ws://192.168.0.40:12345", "Intiface")]), \
                mock.patch.object(buttplug.config, "_store") as store, \
                mock.patch.object(buttplug, "settings", return_value={"url": "ws://127.0.0.1:12345"}):
            reply = buttplug.command("find")
        store.assert_called_once_with("plugins.buttplug.url", "ws://192.168.0.40:12345")
        self.assertIn("saved", reply)


if __name__ == "__main__":
    unittest.main()
