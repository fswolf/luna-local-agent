"""The app launcher's setup page (app/bootstrap.py): the installer's output
becomes steps with marks, the commands for missing system packages are
picked out, and the page and its status answer. No installer is run.

    python -m unittest discover tests        (from the repo folder)
"""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp()
with mock.patch.dict(os.environ, {"XDG_DATA_HOME": _tmp, "LOCALAPPDATA": _tmp}):
    from app import bootstrap as b  # noqa: E402

OUTPUT = """Luna - local AI companion - installer  /x

\033[95m== Checking this machine\033[0m
  ✓ Python 3.12 on Linux x86_64
  ! GPU: none found

== System packages
  ✓ git
  needed: portaudio19-dev (audio)
  ! install these yourself: sudo apt-get install -y portaudio19-dev

== Extras

== Luna's Python environment
  ✓ using /venv
  ✗ some packages failed - see above

== Launchers
  ✓ the Luna app starts her - nothing to add

== Summary
  ✓ python packages
"""


class Steps(unittest.TestCase):
    def setUp(self):
        b.P.reset()
        for line in OUTPUT.splitlines(True):
            b.P.line(line)
        self.s = json.loads(b.P.snapshot())
        self.by = {st["title"]: st for st in self.s["steps"]}

    def test_marks_become_states(self):
        self.assertEqual(self.by["Checking this machine"]["state"], "warn")
        self.assertEqual(self.by["System packages"]["state"], "warn")
        self.assertEqual(self.by["Luna's Python environment"]["state"], "bad")
        self.assertEqual(self.by["Launchers"]["state"], "done")
        self.assertEqual(self.by["Her model"]["state"], "todo")     # skipped: never lit

    def test_unknown_step_lands_in_order(self):
        titles = [st["title"] for st in self.s["steps"]]
        self.assertLess(titles.index("System packages"), titles.index("Extras"))
        self.assertLess(titles.index("Extras"), titles.index("Luna's Python environment"))
        self.assertEqual(self.by["Extras"]["state"], "skip")          # nothing said: skipped

    def test_colours_stripped_and_logged(self):
        self.assertIn("== Checking this machine", self.s["log"])
        self.assertFalse(any("\033" in l for l in self.s["log"]))

    def test_missing_command(self):
        self.assertEqual(self.s["missing"], ["install these yourself: sudo apt-get install -y portaudio19-dev"])

    def test_summary_lines_go_nowhere(self):
        self.assertEqual([l["text"] for l in self.by["Launchers"]["lines"]],
                         ["the Luna app starts her - nothing to add"])


class SameAsTheInstaller(unittest.TestCase):
    def test_every_step_the_page_lists_is_one_the_installer_has(self):
        """The page's list is a copy of the installer's step titles: renaming
        one there must rename it here, or it never lights up."""
        import re

        with open(os.path.join(b.ROOT, "installer", "install.py"), encoding="utf-8") as f:
            titles = set(re.findall(r'step\("([^"]+)"\)', f.read()))
        self.assertEqual([t for t in b.STEPS if t not in titles], [])

    def test_its_args_are_ones_the_installer_takes(self):
        with open(os.path.join(b.ROOT, "installer", "install.py"), encoding="utf-8") as f:
            source = f.read()
        for arg in b.INSTALL_ARGS:
            if arg.startswith("--"):
                self.assertIn(f'"{arg}"', source)

    def test_what_it_makes_goes_in_the_install_record(self):
        root = tempfile.mkdtemp()
        with open(os.path.join(root, "install.json"), "w") as f:
            json.dump({"venv": "/v"}, f)
        with mock.patch.object(b, "ROOT", root):
            b.remember("desktop", "/apps/luna.desktop")
        with open(os.path.join(root, "install.json")) as f:
            self.assertEqual(json.load(f), {"venv": "/v", "desktop": "/apps/luna.desktop"})

    def test_uninstall_knows_the_apps_folder(self):
        sys.path.insert(0, os.path.join(b.ROOT, "installer"))
        import uninstall

        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": _tmp, "LOCALAPPDATA": _tmp}):
            self.assertEqual(os.path.normcase(uninstall.app_dir()).lower(), os.path.normcase(b.data_dir()).lower())


class Retry(unittest.TestCase):
    def test_once_and_only_after_failing(self):
        b.P.reset()
        self.assertFalse(b.P.retry())                   # still setting up
        b.P.set(phase="failed")
        self.assertTrue(b.P.retry())
        self.assertFalse(b.P.retry())                   # a second click: nothing
        self.assertEqual(b.P.phase, "setup")

    def test_clock_stops_when_done(self):
        b.P.reset()
        b.P.set(phase="ready")
        self.assertIsNotNone(b.P.ended)


class Setup(unittest.TestCase):
    def test_needs_setup_until_marked(self):
        with mock.patch.object(b, "MARK", os.path.join(_tmp, "mark.json")), \
                mock.patch.object(b, "her_python", return_value=sys.executable):
            self.assertTrue(b.needs_setup())
            with open(b.MARK, "w") as f:
                json.dump({"fingerprint": b.fingerprint()}, f)
            self.assertFalse(b.needs_setup())
        with mock.patch.object(b, "MARK", os.path.join(_tmp, "mark.json")), \
                mock.patch.object(b, "her_python", return_value=None):
            self.assertTrue(b.needs_setup())            # marked, but her Python is gone

    def test_keeps_an_earlier_voice(self):
        for voice, extra in (({"mode": "external", "url": "http://box:8899"}, ["--voice", "url:http://box:8899"]),
                             ({"mode": "none"}, ["--voice", "skip"]),
                             ({"mode": "managed"}, []), (None, [])):
            with mock.patch.object(b, "load", return_value={"voice": voice}):
                self.assertEqual(b.install_args(), b.INSTALL_ARGS + extra)

    def test_monitor_url_from_config(self):
        self.assertTrue(b.monitor_url().startswith("http://127.0.0.1:"))


class Page(unittest.TestCase):
    def test_serves_page_and_status(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), b.Page)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]

        def get(path):       # http.client: the suite's offline guard stops urlopen
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", path)
            body = c.getresponse().read()
            c.close()
            return body
        try:
            self.assertIn(b"Setting up Luna", get("/"))
            self.assertIn("steps", json.loads(get("/status")))
            self.assertEqual(get("/logo.png")[:4], b"\x89PNG")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
