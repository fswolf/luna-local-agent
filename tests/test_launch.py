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


if __name__ == "__main__":
    unittest.main()
