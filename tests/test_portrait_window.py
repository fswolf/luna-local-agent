"""Which window /portrait opens (portrait_window.command): an app window with
no address bar wherever the machine allows one.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

class PortraitWindow(unittest.TestCase):
    def setUp(self):
        import portrait_window

        self.m = portrait_window
        self.home = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"HOME": self.home})
        p.start()
        self.addCleanup(p.stop)

    def which(self, *have):
        return mock.patch("shutil.which", side_effect=lambda b: f"/usr/bin/{b}" if b in have else None)

    def test_chromium_on_the_path(self):
        with self.which("brave-browser", "firefox"):
            cmd = self.m.command("http://x/", 420, 560)
        self.assertEqual(cmd[0], "brave-browser")
        self.assertIn("--app=http://x/", cmd)

    def test_flatpak_brave(self):
        with self.which("flatpak"), \
                mock.patch.object(self.m, "_flatpak_has", side_effect=lambda a: a == "com.brave.Browser"):
            cmd = self.m.command("http://x/", 420, 560)
        self.assertEqual(cmd[:3], ["flatpak", "run", "com.brave.Browser"])
        self.assertIn("--app=http://x/", cmd)

    def test_firefox_gets_a_chromeless_profile(self):
        with self.which("firefox"), mock.patch.object(self.m, "_flatpak_has", return_value=False):
            cmd = self.m.command("http://x/", 420, 560)
        self.assertEqual(cmd[0], "/usr/bin/firefox")
        profile = cmd[cmd.index("--profile") + 1]
        with open(os.path.join(profile, "chrome", "userChrome.css")) as f:
            self.assertIn("#nav-bar", f.read())
        with open(os.path.join(profile, "user.js")) as f:
            self.assertIn("legacyUserProfileCustomizations", f.read())

    def test_nothing_at_all(self):
        with self.which(), mock.patch.object(self.m, "_flatpak_has", return_value=False):
            self.assertIsNone(self.m.command("http://x/", 420, 560))


if __name__ == "__main__":
    unittest.main()
