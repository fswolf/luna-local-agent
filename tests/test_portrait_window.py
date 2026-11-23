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



@unittest.skipIf(os.name == "nt", "process groups are POSIX")
class ClosedWithHer(unittest.TestCase):
    """Quitting closes every window she opened, and what each one started
    (a browser's helpers, a Flatpak's sandbox): real processes, no browser."""

    def test_close_takes_them_all(self):
        import time

        from web import portrait_window as pw

        script = "sleep 30 & echo $! > {}; wait"
        marks = [tempfile.mktemp() for _ in range(2)]
        with mock.patch("config.PORTRAIT_BROWSER", "", create=True), \
                mock.patch.object(pw, "command", side_effect=[["sh", "-c", script.format(m)] for m in marks]):
            procs = [pw.open_app("http://x/", 1, 1, f"t{i}") for i, _ in enumerate(marks)]
        for _ in range(50):
            if all(os.path.exists(m) and open(m).read().strip() for m in marks):
                break
            time.sleep(0.05)
        children = [int(open(m).read()) for m in marks]
        pw.close()
        for p in procs:
            p.wait(5)
        time.sleep(0.2)
        for child in children:                    # the sleep it started went with it (gone, or a zombie
            try:                                  # nobody has reaped yet)
                with open(f"/proc/{child}/stat") as f:
                    self.assertEqual(f.read().rsplit(")", 1)[1].split()[0], "Z")
            except FileNotFoundError:
                pass
        self.assertEqual(pw._opened, [])


class OneWindowAProfile(unittest.TestCase):
    """Asking again while the window is open brings it to the front: Firefox
    refuses a second start on a profile it holds ("already running, but is not
    responding"), and a Chromium one would open a second window."""

    def setUp(self):
        from web import portrait_window as pw

        self.pw = pw
        pw._mine.clear()
        self.addCleanup(pw._mine.clear)

    def test_open_again_comes_to_the_front(self):
        proc = mock.Mock(pid=4242)
        proc.poll.return_value = None
        with mock.patch("config.PORTRAIT_BROWSER", "", create=True), \
                mock.patch.object(self.pw, "command", return_value=["firefox", "x"]), \
                mock.patch.object(self.pw, "_holder", return_value=None), \
                mock.patch("subprocess.Popen", return_value=proc) as start, \
                mock.patch.object(self.pw, "_raise", return_value=True) as front:
            self.assertIs(self.pw.open_app("http://x/", 1, 1, "luna-chat"), proc)
            self.assertIs(self.pw.open_app("http://x/", 1, 1, "luna-chat"), proc)
            proc.poll.return_value = 0                         # closed: the next one opens anew
            self.pw.open_app("http://x/", 1, 1, "luna-chat")
        self.assertEqual(start.call_count, 2)
        front.assert_called_once_with(4242)

    def test_a_window_left_by_an_earlier_run(self):
        import tempfile

        folder = tempfile.mkdtemp()
        os.symlink(f"127.0.1.1:+{os.getpid()}", os.path.join(folder, "lock"))          # Firefox's
        with mock.patch.object(self.pw, "_profile_dirs", return_value=[folder]):
            self.assertEqual(self.pw._holder("x"), os.getpid())
            with mock.patch("subprocess.Popen") as start, \
                    mock.patch.object(self.pw, "_raise", return_value=False) as front:
                self.assertIsNone(self.pw.open_app("http://x/", 1, 1, "x"))
            start.assert_not_called()
            front.assert_called_once_with(os.getpid())
        os.remove(os.path.join(folder, "lock"))
        os.symlink("host-999999999", os.path.join(folder, "SingletonLock"))          # a dead one
        with mock.patch.object(self.pw, "_profile_dirs", return_value=[folder]):
            self.assertIsNone(self.pw._holder("x"))

    def test_hyprland_focuses_its_window(self):
        def run(cmd, **kw):
            out = '[{"pid": 4243, "address": "0xabc"}]' if list(cmd[:2]) == ["hyprctl", "-j"] else ""
            return mock.Mock(stdout=out, returncode=0)

        with mock.patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "x"}), \
                mock.patch("shutil.which", return_value="/usr/bin/hyprctl"), \
                mock.patch.object(self.pw, "_group", return_value={4242, 4243}), \
                mock.patch("subprocess.run", side_effect=run) as ran:
            self.assertTrue(self.pw._raise(4242))
        self.assertEqual(list(ran.call_args.args[0]), ["hyprctl", "dispatch", "focuswindow", "address:0xabc"])


if __name__ == "__main__":
    unittest.main()
