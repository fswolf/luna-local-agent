"""shell.sudo: off, sudo is refused before any popup; on, every sudo in the
command (and in scripts it runs) goes through askpass on the user's screen.
A fake askpass stands in for the dialog; nothing here touches real sudo.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from tools import shell  # noqa: E402


class SudoOff(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(config, "SHELL_SUDO", False, create=True)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_refused_before_asking(self):
        with mock.patch("ui.ask_approval", side_effect=AssertionError("no popup")) as _:
            out = shell._run_command.__wrapped__("sudo systemctl restart kokoro") \
                if hasattr(shell._run_command, "__wrapped__") else shell._run_command("sudo systemctl restart kokoro")
        self.assertIn("sudo is off", out)

    def test_plain_commands_unwrapped(self):
        self.assertEqual(shell._argv("ls")[-1], "ls")

    def test_spots_sudo(self):
        for c in ("sudo ls", "cd /x && sudo ls", "echo hi; sudo -n true", "(sudo ls)"):
            self.assertTrue(shell._wants_sudo(c), c)
        for c in ("pseudo ls", "echo sudoers", "ls /etc/sudo.conf"):
            self.assertFalse(shell._wants_sudo(c), c)


@unittest.skipIf(os.name == "nt", "no sudo on Windows")
class SudoOn(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(config, "SHELL_SUDO", True, create=True)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_wraps_and_sets_askpass(self):
        argv = shell._argv("sudo ls")
        self.assertIn("sudo -A", argv[-1])
        env = shell._env("sudo ls")
        self.assertEqual(env["SUDO_ASKPASS"], shell.ASKPASS)
        self.assertEqual(env["LUNA_SUDO_COMMAND"], "sudo ls")
        self.assertTrue(os.access(shell.ASKPASS, os.X_OK))

    def test_scripts_inherit_it(self):
        # a fake "sudo" on PATH that reports how it was called; the wrapper must add -A,
        # also for a script the command runs
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "sudo")
            with open(fake, "w") as f:
                f.write('#!/bin/sh\necho "called: $*"\n')
            os.chmod(fake, 0o755)
            script = os.path.join(d, "inner.sh")
            with open(script, "w") as f:
                f.write("#!/bin/bash\nsudo whoami\n")
            os.chmod(script, 0o755)
            env = dict(shell._env("x"), PATH=d + os.pathsep + os.environ["PATH"])
            out = subprocess.run(shell._argv(f"sudo id; {script}"), env=env,
                                 capture_output=True, text=True).stdout
        self.assertIn("called: -A id", out)
        self.assertIn("called: -A whoami", out)


if __name__ == "__main__":
    unittest.main()
