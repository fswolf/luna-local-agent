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
        from web import portrait_window

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

    def test_the_studio_has_a_profile_of_its_own(self):
        with self.which("chromium", "firefox"):
            cmd = self.m.command("http://x/", 1600, 960, profile="luna-studio")
        self.assertTrue(any(c.startswith("--user-data-dir=") and c.endswith("luna-studio") for c in cmd))
        with self.which("firefox"), mock.patch.object(self.m, "_flatpak_has", return_value=False):
            cmd = self.m.command("http://x/", 1600, 960, profile="luna-studio")
        self.assertTrue(cmd[cmd.index("--profile") + 1].endswith("luna-studio-firefox"))

    def test_mac_chrome_in_applications(self):
        want = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        with self.which(), mock.patch.object(self.m.sys, "platform", "darwin"), \
                mock.patch("os.path.isfile", side_effect=lambda p: p == want):
            cmd = self.m.command("http://x/", 420, 560)
        self.assertEqual(cmd[0], want)
        self.assertIn("--app=http://x/", cmd)

    def test_mac_firefox_in_applications(self):
        want = "/Applications/Firefox.app/Contents/MacOS/firefox"
        with self.which(), mock.patch.object(self.m.sys, "platform", "darwin"), \
                mock.patch("os.path.isfile", side_effect=lambda p: p == want):
            cmd = self.m.command("http://x/", 420, 560)
        self.assertEqual(cmd[0], want)
        self.assertIn("--profile", cmd)

    def test_windows_edge(self):
        env = {"PROGRAMFILES": "C:/PF", "PROGRAMFILES(X86)": "C:/PF86", "LOCALAPPDATA": "C:/LA"}
        with self.which(), mock.patch.object(self.m.sys, "platform", "win32"), \
                mock.patch.dict(os.environ, env), \
                mock.patch("os.path.isfile", side_effect=lambda p: p.endswith("msedge.exe") and p.startswith("C:/PF86")):
            cmd = self.m.command("http://x/", 420, 560)
        self.assertTrue(cmd[0].endswith("msedge.exe"))
        self.assertIn("--app=http://x/", cmd)

    def test_nothing_at_all(self):
        with self.which(), mock.patch.object(self.m, "_flatpak_has", return_value=False):
            self.assertIsNone(self.m.command("http://x/", 420, 560))


if __name__ == "__main__":
    unittest.main()
