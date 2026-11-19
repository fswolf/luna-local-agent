"""--web (ui/headless.py): Luna with no screen, the chat page as her window."""
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.offline  # noqa: F401,E402

import config  # noqa: E402
import ui  # noqa: E402
from ui import headless  # noqa: E402
from web import chat_web  # noqa: E402


class Running(unittest.TestCase):
    def setUp(self):
        chat_web.register()
        self.got = []
        self.saved = (ui.view.app, ui.view.loop, ui.view.on_submit)
        self.thread = threading.Thread(target=headless.run_web, kwargs={
            "on_submit": lambda text, attachment=None: self.got.append((text, threading.current_thread())),
            "on_hotkey": lambda: self.got.append(("HOME", threading.current_thread())),
            "open_window": False}, daemon=True)
        with mock.patch("builtins.print"):
            self.thread.start()
            for _ in range(100):
                if ui.view.app is not None and ui.view.loop is not None and ui.view.loop.is_running():
                    break
                time.sleep(0.02)

    def tearDown(self):
        ui.stop()
        self.thread.join(5)
        ui.view.app, ui.view.loop, ui.view.on_submit = self.saved

    def test_what_the_page_sends_runs_on_her_main_loop(self):
        ui.submit_soon("hello")
        for _ in range(100):
            if self.got:
                break
            time.sleep(0.02)
        self.assertEqual(self.got[0][0], "hello")
        self.assertIs(self.got[0][1], self.thread)

    def test_the_mic_button_presses_home_on_her_loop(self):
        self.assertIsNone(chat_web.talk())
        for _ in range(100):
            if self.got:
                break
            time.sleep(0.02)
        self.assertEqual(self.got[0], ("HOME", self.thread))

    def test_a_tool_can_still_ask_and_the_page_answers(self):
        answer = {}
        t = threading.Thread(target=lambda: answer.setdefault("a", ui.ask_approval("Run a command", ["ls"], timeout=10)))
        t.start()
        for _ in range(100):
            if ui.pending_approval():
                break
            time.sleep(0.02)
        self.assertTrue(ui.answer_approval(True, which=ui.pending_approval()["id"]))
        t.join(5)
        self.assertIs(answer["a"], True)

    def test_quit_ends_it(self):
        ui.stop()
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())
        self.assertIsNone(ui.view.app)


class Window(unittest.TestCase):
    def test_closing_the_window_quits(self):
        window, app = mock.Mock(), mock.Mock()
        window.wait = lambda: None
        with mock.patch.object(ui.view, "app", app), mock.patch.object(headless.time, "monotonic", side_effect=[0, 60]):
            headless._watch(window)
        app.exit.assert_called_once_with()

    def test_a_window_handed_off_at_once_doesnt(self):
        window, app = mock.Mock(), mock.Mock()
        window.wait = lambda: None
        with mock.patch.object(ui.view, "app", app), mock.patch.object(headless.time, "monotonic", side_effect=[0, 1]), \
                mock.patch("builtins.print"):
            headless._watch(window)
        app.exit.assert_not_called()

    def test_no_app_browser_is_a_tab(self):
        from web import portrait_window

        with mock.patch.object(config, "PORTRAIT_BROWSER", ""), \
                mock.patch.object(portrait_window, "command", return_value=None), \
                mock.patch.object(portrait_window, "quiet_open") as opened:
            self.assertIsNone(chat_web.open_window())
        self.assertTrue(opened.call_args[0][0].endswith("/chat/"))

    def test_its_own_profile(self):
        from web import portrait_window

        with mock.patch.object(config, "PORTRAIT_BROWSER", ""), \
                mock.patch.object(portrait_window, "command", return_value=["chromium", "--app=x"]) as cmd, \
                mock.patch("subprocess.Popen") as popen:
            chat_web.open_window()
        self.assertEqual(cmd.call_args.kwargs.get("profile"), "luna-chat")
        popen.assert_called_once()

    def test_no_pages_served_no_window(self):
        from web import livefeed

        with mock.patch.dict(livefeed.PAGES, clear=True), mock.patch("builtins.print") as said:
            headless.run_web(lambda *a, **k: None)
        self.assertIn("port", said.call_args[0][0])
        self.assertIsNone(ui.view.app)

    def test_needs_the_monitor(self):
        with mock.patch.object(config, "MONITOR_ENABLED", False), mock.patch("builtins.print") as said:
            headless.run_web(lambda *a, **k: None, open_window=False)
        self.assertIn("monitor.enabled", said.call_args[0][0])
        self.assertIsNone(ui.view.app)


if __name__ == "__main__":
    unittest.main()
