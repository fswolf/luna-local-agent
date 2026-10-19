"""The launcher's package check: what installer/requirements.txt asks
for on this platform, and saying what's missing instead of a traceback.
A temporary requirements file; nothing is installed.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import launch  # noqa: E402

REQS = """# a comment
requests>=2.32
pint>=0.24              # calculate: unit conversions
evdev>=1.7; sys_platform == "linux"
pywin32; sys_platform == 'win32'
"""


class Packages(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp()
        with os.fdopen(fd, "w") as f:
            f.write(REQS)
        self.patch = mock.patch.object(launch, "REQUIREMENTS", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        os.remove(self.path)

    def test_names_for_this_platform(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(launch.wanted_packages(), ["requests", "pint", "evdev"])
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(launch.wanted_packages(), ["requests", "pint"])

    def test_what_this_python_is_missing(self):
        with mock.patch.object(launch, "wanted_packages", return_value=["requests", "no-such-package-xyz"]):
            self.assertEqual(launch.missing_packages(sys.executable), ["no-such-package-xyz"])

    def test_a_python_that_doesnt_answer(self):
        self.assertIsNone(launch.missing_packages("/nowhere/python"))



class Settings(unittest.TestCase):
    """config.json is yours and outside git: made from config.example.json
    once, never overwritten, and tts.url decides where her voice is."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(launch, "CONFIG", os.path.join(self.dir.name, "config.json")),
                        mock.patch.object(launch, "EXAMPLE", os.path.join(self.dir.name, "config.example.json")),
                        mock.patch.object(launch, "state", return_value={})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.dir.cleanup()

    def write(self, path, data):
        import json

        with open(path, "w") as f:
            json.dump(data, f)

    def test_made_once_from_the_example(self):
        self.assertFalse(launch.seed_config())                     # no example: nothing to copy
        self.write(launch.EXAMPLE, {"tts": {"url": "http://127.0.0.1:8899"}})
        self.assertTrue(launch.seed_config())
        self.write(launch.CONFIG, {"tts": {"url": "http://192.168.0.98:8899"}})
        self.assertFalse(launch.seed_config())                     # yours is never overwritten
        self.assertEqual(launch.tts_url(), "http://192.168.0.98:8899")

    def test_where_her_voice_is(self):
        self.assertEqual(launch.tts_url(), "http://127.0.0.1:8899")
        self.assertTrue(launch._here("http://localhost:8899"))
        self.assertFalse(launch._here("http://192.168.0.98:8899"))


if __name__ == "__main__":
    unittest.main()
