"""Error handling in the pages and side tools: web/, memory-manager/,
thought-viewer/, training/, introspection/, installer/.

Nothing here prints over the screen, loops, or throws away a file it
couldn't read. Servers are started on 127.0.0.1 by the tests themselves;
files go to temporary folders.

    python -m unittest tests.test_errors_web        (from the repo folder)
"""
import concurrent.futures
import contextlib
import http.client
import importlib.util
import io
import json
import os
import queue
import shutil
import socket
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from web import livefeed  # noqa: E402  (first: web.gaze imports it back)
from web import gaze, holofan, satellites, station  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, *path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, *path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Circular(dict):
    """A value even default=str can't send: JSON refuses the loop first."""


def _circular():
    d = {}
    d["me"] = d
    return d


# ---------------------------------------------------------------------------
# web/livefeed.py
# ---------------------------------------------------------------------------
class Emit(unittest.TestCase):
    def setUp(self):
        self.snap = mock.patch.dict(livefeed._snapshot, clear=True)
        self.snap.start()

    def tearDown(self):
        self.snap.stop()

    def test_unsendable_event_is_dropped_not_kept(self):
        with mock.patch.object(livefeed, "logbook") as log:
            livefeed.emit("mood", label=_circular())
        self.assertNotIn("mood", livefeed._snapshot)       # never replayed to the next page
        log.warn.assert_called_once()

    def test_odd_values_go_as_text(self):
        q = queue.Queue()
        with mock.patch.object(livefeed, "_subs", {q}):
            livefeed.emit("mood", label="calm", seen={1}, where=types.SimpleNamespace())
        line = q.get_nowait()
        self.assertTrue(line.startswith(b"data: ") and line.endswith(b"\n\n"))
        self.assertEqual(json.loads(line[6:])["label"], "calm")
        self.assertIn("mood", livefeed._snapshot)

    def test_nobody_watching_costs_nothing(self):
        with mock.patch.object(livefeed, "_line") as line:
            livefeed.emit("tok", s="x")
        line.assert_not_called()


class Server(unittest.TestCase):
    """A request that fails is a log line, never stderr."""

    def serve(self, handler, server_cls):
        server = server_cls(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_handler_bug_is_logged_quietly(self):
        class Broken(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                raise KeyError("a bug")

        err = io.StringIO()
        with mock.patch.object(livefeed, "logbook") as log, contextlib.redirect_stderr(err):
            port = self.serve(Broken, livefeed._Server)
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", "/")
            with self.assertRaises(Exception):
                c.getresponse()
            c.close()
            for _ in range(50):
                if log.exception.called:
                    break
                threading.Event().wait(0.05)
        self.assertEqual(err.getvalue(), "")
        log.exception.assert_called_once()

    def test_page_hanging_up_is_not_an_error(self):
        server = livefeed._Server.__new__(livefeed._Server)
        with mock.patch.object(livefeed, "logbook") as log:
            try:
                raise BrokenPipeError("gone")
            except BrokenPipeError:
                server.handle_error(None, ("127.0.0.1", 1))
        log.exception.assert_not_called()
        log.debug.assert_called_once()

    def test_negative_length_doesnt_wait_for_the_page(self):
        port = self.serve(livefeed._Handler, livefeed._Server)
        with mock.patch.object(livefeed, "port", return_value=port):
            s = socket.create_connection(("127.0.0.1", port), timeout=5)
            s.sendall((f"POST /portrait/touch HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                       "Content-Type: application/json\r\nContent-Length: -5\r\n\r\n{}").encode())
            reply = s.recv(100)          # times out (5 s) if it read until the page hung up
            s.close()
        self.assertTrue(reply.startswith(b"HTTP/1.0 400"), reply)

    def test_length_clamped(self):
        h = types.SimpleNamespace(headers={"Content-Length": "-1"})
        self.assertEqual(livefeed._Handler._length(h, 10), 0)
        h.headers["Content-Length"] = "999"
        self.assertEqual(livefeed._Handler._length(h, 10), 10)
        h.headers["Content-Length"] = "lots"
        self.assertEqual(livefeed._Handler._length(h, 10), 0)


class Gone(unittest.TestCase):
    def test_high_socket_number(self):
        """select() refuses a socket numbered 1024 or more; the page isn't gone."""
        a, b = socket.socketpair()
        try:
            high = os.dup2(a.fileno(), 1500)
        except OSError:
            a.close()
            b.close()
            self.skipTest("can't open a file number that high here")
        conn = socket.socket(fileno=high)
        try:
            self.assertFalse(livefeed._Handler._gone(types.SimpleNamespace(connection=conn)))
            b.close()
            self.assertTrue(livefeed._Handler._gone(types.SimpleNamespace(connection=conn)))
        finally:
            conn.close()
            a.close()


# ---------------------------------------------------------------------------
# web/gaze.py
# ---------------------------------------------------------------------------
class GazeLoop(unittest.TestCase):
    def test_survives_an_error(self):
        class Stop(BaseException):
            pass

        calls = {"step": 0, "sleep": 0}

        def step(last):
            calls["step"] += 1
            raise RuntimeError("camera went away")

        def sleep(_s):
            calls["sleep"] += 1
            if calls["sleep"] > 6:
                raise Stop()

        with mock.patch.object(gaze, "_gaze_step", step), mock.patch.object(gaze.time, "sleep", sleep), \
                mock.patch.object(gaze, "logbook") as log:
            with self.assertRaises(Stop):
                gaze._gaze_loop()
        self.assertGreaterEqual(calls["step"], 3)          # it kept going
        log.exception.assert_called_once()                 # and said so once, not every time

    def test_hyprctl_error_as_json(self):
        out = types.SimpleNamespace(returncode=0, stdout='{"error": "no instance"}')
        with mock.patch("shutil.which", return_value="/usr/bin/hyprctl"), \
                mock.patch("subprocess.run", return_value=out):
            self.assertIsNone(gaze.gaze_target())


# ---------------------------------------------------------------------------
# web/station.py, web/satellites.py, web/holofan.py
# ---------------------------------------------------------------------------
class StationErrors(unittest.TestCase):
    def handle(self, error):
        server = station._Server.__new__(station._Server)
        with mock.patch.object(station, "logbook") as log:
            try:
                raise error
            except Exception:
                server.handle_error(None, ("192.168.1.5", 1))
        return log

    def test_dropped_connection_is_quiet(self):
        log = self.handle(ConnectionResetError("reset"))
        log.info.assert_called_once()
        log.exception.assert_not_called()

    def test_bug_keeps_its_traceback(self):
        log = self.handle(KeyError("turn"))
        log.exception.assert_called_once()


class Satellites(unittest.TestCase):
    def test_a_loop_that_ends_says_why(self):
        device = types.SimpleNamespace(name="kitchen", status="starting")
        f = concurrent.futures.Future()
        f.set_exception(ValueError("bad key"))
        with mock.patch.object(satellites, "logbook"):
            satellites._ended(device)(f)
        self.assertIn("bad key", device.status)

    def test_cancelled_is_not_an_error(self):
        device = types.SimpleNamespace(name="kitchen", status="connected")
        f = concurrent.futures.Future()
        f.cancel()
        satellites._ended(device)(f)
        self.assertEqual(device.status, "connected")

    def test_bad_port_is_one_device(self):
        with mock.patch.object(satellites, "logbook"):
            d = satellites.Device({"host": "10.0.0.5", "port": "sixty"})
        self.assertEqual(d.port, satellites.PORT)


class FanRate(unittest.TestCase):
    def test_fps(self):
        for value, want in (("fast", 15.0), (float("nan"), 15.0), (100, 25.0), (1, 8.0), (None, 15.0),
                            ("12", 12.0), (float("inf"), 25.0)):
            with mock.patch.object(holofan, "_setting", return_value=value):
                self.assertEqual(holofan._fps(), want, value)


# ---------------------------------------------------------------------------
# memory-manager/manager.py
# ---------------------------------------------------------------------------
class MemoryManager(unittest.TestCase):
    def setUp(self):
        self.mm = _load("luna_memory_manager_test", "memory-manager", "manager.py")
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.file = os.path.join(self.dir, "memory.json")
        for p in (mock.patch.object(self.mm, "MEMORY_FILE", self.file),
                  mock.patch.object(self.mm, "backend", return_value="json")):
            p.start()
            self.addCleanup(p.stop)

    def test_unreadable_file_is_never_overwritten(self):
        broken = '{"long_term_facts": ["likes tea"], "user_preferences": {"a": 1},'   # cut short
        with open(self.file, "w") as f:
            f.write(broken)
        for action, body in (("add", {"fact": "new"}), ("prefs", {"text": "{}"}), ("delete", {"id": 0})):
            with self.assertRaises(ValueError):
                self.mm.apply(action, body)
        with open(self.file) as f:
            self.assertEqual(f.read(), broken)
        self.assertIn("can't be read", self.mm.state()["warning"])

    def test_saves_whole(self):
        with open(self.file, "w") as f:
            json.dump({"long_term_facts": ["likes tea"], "other": True}, f)
        self.mm.apply("add", {"fact": "has a cat"})
        with open(self.file) as f:
            data = json.load(f)
        self.assertEqual(data["long_term_facts"], ["likes tea", "has a cat"])
        self.assertTrue(data["other"])
        self.assertFalse(os.path.exists(self.file + ".tmp"))

    def test_missing_file_starts_empty(self):
        self.mm.apply("add", {"fact": "first"})
        with open(self.file) as f:
            self.assertEqual(json.load(f)["long_term_facts"], ["first"])

    def test_length(self):
        self.assertEqual(self.mm._length({"Content-Length": "-3"}), 0)
        self.assertEqual(self.mm._length({"Content-Length": str(10 ** 12)}), self.mm.MAX_BODY)


# ---------------------------------------------------------------------------
# thought-viewer/viewer.py
# ---------------------------------------------------------------------------
class ThoughtViewer(unittest.TestCase):
    def setUp(self):
        self.tv = _load("luna_thought_viewer_test", "thought-viewer", "viewer.py")

    def test_numbers_from_the_address(self):
        self.assertEqual(self.tv._int("abc"), 0)
        self.assertEqual(self.tv._int(""), 0)
        self.assertEqual(self.tv._int("-4"), 0)
        self.assertEqual(self.tv._int("7"), 7)
        self.assertEqual(self.tv._int(9), 9)
        self.assertEqual(self.tv._int("9" * 40), self.tv.MAX_ID)   # not OverflowError in SQLite

    def test_length(self):
        self.assertEqual(self.tv._length({"Content-Length": "-1"}), 0)
        self.assertEqual(self.tv._length({}), 0)
        self.assertEqual(self.tv._length({"Content-Length": "x"}), 0)


# ---------------------------------------------------------------------------
# training/dataset.py
# ---------------------------------------------------------------------------
class DatasetBadLine(unittest.TestCase):
    def setUp(self):
        from training import dataset

        self.ds = dataset
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        for p in (mock.patch.object(dataset, "FOLDER", self.dir),
                  mock.patch.object(dataset, "FILE", os.path.join(self.dir, "examples.jsonl"))):
            p.start()
            self.addCleanup(p.stop)
        with open(dataset.FILE, "w") as f:
            f.write(json.dumps({"id": "a", "kind": "habit", "reply": "hi", "approved": True}) + "\n")
            f.write('{"id": "b", "kind": "hab\n')                       # cut short by a crash
            f.write(json.dumps({"id": "c", "kind": "habit", "reply": "yo", "approved": None}) + "\n")

    def test_others_still_read(self):
        self.assertEqual([r["id"] for r in self.ds.examples()], ["a", "c"])
        self.assertEqual(self.ds.counts()["habit"], {"approved": 1, "waiting": 1, "dropped": 0})

    def test_bad_line_kept_through_changes(self):
        self.assertTrue(self.ds.remove("a"))
        self.assertTrue(self.ds.update("c", approved=True))
        with open(self.ds.FILE) as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], '{"id": "b", "kind": "hab')
        self.assertEqual(json.loads(lines[1])["approved"], True)


# ---------------------------------------------------------------------------
# installer/install.py, introspection/lab.py
# ---------------------------------------------------------------------------
class Installer(unittest.TestCase):
    def test_unreadable_config_is_said_and_left_alone(self):
        install = _load("luna_installer_errors", "installer", "install.py")
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        with open(os.path.join(d, "config.json"), "w") as f:
            f.write('{"tts": {"url": 1},}')
        with mock.patch.object(install, "ROOT", d), mock.patch.object(install, "warn") as warn:
            install.set_config("tts", "url", "http://x")
        warn.assert_called_once()
        with open(os.path.join(d, "config.json")) as f:
            self.assertEqual(f.read(), '{"tts": {"url": 1},}')

    def test_curl_has_time_limits(self):
        install = _load("luna_installer_errors2", "installer", "install.py")
        with mock.patch.object(install.shutil, "which", return_value="/usr/bin/curl"), \
                mock.patch.object(install.subprocess, "run") as run:
            run.return_value.returncode = 0
            install._curl("http://127.0.0.1:1/x", "/tmp/nothing")
        cmd = run.call_args.args[0]
        self.assertIn("--connect-timeout", cmd)
        self.assertIn("--speed-time", cmd)


class LabServer(unittest.TestCase):
    def test_failed_start_stops_the_server(self):
        try:
            import requests  # noqa: F401
            lab = _load("luna_lab_test", "introspection", "lab.py")
        except Exception as e:      # needs the llama folder layout; skip without it
            self.skipTest(f"lab can't load here: {e}")
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        proc = mock.Mock()
        proc.poll.side_effect = [1, 1, 1]          # exits while loading
        server = lab.Server.__new__(lab.Server)
        server.args, server.proc = ["llama-server"], None
        with mock.patch.object(lab, "RESULTS", d), mock.patch.object(lab.subprocess, "Popen", return_value=proc):
            with self.assertRaises(RuntimeError):
                server.__enter__()
        self.assertTrue(server.log.closed)


if __name__ == "__main__":
    unittest.main()
