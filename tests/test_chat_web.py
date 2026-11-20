"""The browser chat (web/chat_web.py): it mirrors the terminal's conversation,
sends through the same door as Enter, and answers a tool's question."""
import http.client
import json
import os
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.offline  # noqa: F401,E402

import ui  # noqa: E402
from web import chat_web, livefeed  # noqa: E402


class Mirror(unittest.TestCase):
    """state(): what a page gets, given what it already has."""

    def setUp(self):
        ui.clear()

    def tearDown(self):
        ui.end_message()
        ui.clear()

    def test_a_new_page_gets_the_conversation(self):
        ui.add_message("user", "hi")
        ui.add_message("luna", "hey you")
        s = chat_web.state(None, 0, None)
        self.assertTrue(s["reset"])
        self.assertEqual(s["from"], 0)
        self.assertEqual(s["msgs"], [["user", "hi"], ["luna", "hey you"]])

    def test_a_long_one_starts_near_the_end(self):
        for i in range(chat_web.KEEP + 20):
            ui.add_message("system", str(i))
        s = chat_web.state(None, 0, None)
        self.assertEqual(s["from"], 20)
        self.assertEqual(len(s["msgs"]), chat_web.KEEP)

    def test_a_streaming_reply_and_a_tool_line_above_it(self):
        ui.add_message("user", "look it up")
        ui.begin_message("luna")
        ui.extend_message("Let me")
        first = chat_web.state(None, 0, None)
        have = first["from"] + len(first["msgs"])
        ui.add_message("system", "tool: search")      # lands above the open reply
        ui.extend_message(" check.")
        s = chat_web.state(first["v"], have, first["e"], wait=0)
        self.assertFalse(s["reset"])
        whole = first["msgs"][:s["from"] - first["from"]] + s["msgs"]
        self.assertEqual(whole, [["user", "look it up"], ["system", "tool: search"], ["luna", "Let me check."]])

    def test_clear_starts_the_page_over(self):
        ui.add_message("user", "one")
        s = chat_web.state(None, 0, None)
        ui.clear()
        ui.add_message("user", "two")
        s = chat_web.state(s["v"], 1, s["e"], wait=0)
        self.assertTrue(s["reset"])
        self.assertEqual(s["msgs"], [["user", "two"]])

    def test_an_empty_reply_dropped_is_not_a_reset(self):
        ui.add_message("user", "hi")
        ui.begin_message("luna")
        s = chat_web.state(None, 0, None)
        ui.end_message()                  # nothing came: the empty bubble goes
        s = chat_web.state(s["v"], 2, s["e"], wait=0)
        self.assertFalse(s["reset"])
        self.assertEqual(s["from"] + len(s["msgs"]), 1)

    def test_it_waits_for_a_change_and_wakes_on_one(self):
        s = chat_web.state(None, 0, None)
        threading.Timer(0.2, ui.add_message, ("user", "now")).start()
        started = time.monotonic()
        later = chat_web.state(s["v"], 0, s["e"], wait=5)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(later["msgs"][-1], ["user", "now"])

    def test_nothing_new_returns_after_the_wait(self):
        s = chat_web.state(None, 0, None)
        started = time.monotonic()
        chat_web.state(s["v"], 0, s["e"], wait=0.2)
        self.assertGreaterEqual(time.monotonic() - started, 0.15)


class Server(unittest.TestCase):
    """The page's requests, through the live monitor."""

    def setUp(self):
        chat_web.register()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), livefeed._Handler)
        self.port = self.server.server_address[1]
        self.patch = mock.patch.object(livefeed, "port", return_value=self.port)
        self.patch.start()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.sent = []
        self.submit = mock.patch.object(ui, "submit_soon", lambda text, att=None: self.sent.append((text, att)))
        self.submit.start()
        self.handler = mock.patch.object(ui.view, "on_submit", lambda *a, **k: None)
        self.handler.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.patch.stop()
        self.submit.stop()
        self.handler.stop()

    def ask(self, method, path, body=b"", kind="application/json", origin=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if body or method == "POST":
            headers["Content-Type"] = kind
        if origin:
            headers["Origin"] = origin
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        out = r.status, r.read()
        c.close()
        return out

    def test_the_page_and_her_header(self):
        code, body = self.ask("GET", "/chat/")
        self.assertEqual(code, 200)
        page = body.decode()
        self.assertNotIn("__BOOT__", page)
        self.assertIn('<script src="/chat/head.js"></script>', page)    # the same header as every page
        code, body = self.ask("GET", "/chat/head.js")
        self.assertEqual(code, 200)
        js = body.decode()
        self.assertNotIn("__NAV__", js)
        nav = json.loads(js.split("const NAV = ", 1)[1].split(";\n", 1)[0])
        labels = [label for label, *_ in nav]
        self.assertEqual(labels[0], "Chat")
        self.assertEqual(labels.count("Chat"), 1)
        self.assertIn("Settings", labels)
        commands = {label: command for label, _href, command, _title in nav}
        self.assertEqual((commands["Portrait"], commands["Pose studio"], commands["Settings"]), ("/portrait", "/pose", ""))

    def test_header_only_state(self):
        ui.add_message("user", "hi")
        code, body = self.ask("GET", "/chat/state?head=1")
        s = json.loads(body)
        self.assertNotIn("msgs", s)
        self.assertEqual([k for k, _v in s["rows"]][:2], ["Status", "Mood"])

    def test_the_tray_reads_her_header(self):
        """What app/tray.py's menu needs, and its looks mark it as there."""
        chat_web.TRAY["seen"] = 0.0
        s = json.loads(self.ask("GET", "/chat/state?head=1")[1])
        for key in ("status", "name", "rows", "busy", "mic", "can_talk", "voice_on"):
            self.assertIn(key, s)
        self.assertFalse(chat_web.tray_up())
        self.ask("GET", "/chat/state?head=1&tray=1")
        self.assertTrue(chat_web.tray_up())
        chat_web.TRAY["seen"] = 0.0

    def test_the_tray_menu(self):
        self.assertEqual(self.ask("POST", "/chat/tray", b'{"action":"portrait"}')[0], 200)
        self.assertEqual(self.ask("POST", "/chat/tray", b'{"action":"quit"}')[0], 200)
        self.assertEqual(self.sent, [("/portrait", None), ("/quit", None)])
        self.assertEqual(self.ask("POST", "/chat/tray", b'{"action":"rm -rf"}')[0], 400)
        with mock.patch.object(chat_web, "open_window") as opened:
            self.assertEqual(self.ask("POST", "/chat/tray", b'{"action":"chat"}')[0], 200)
        opened.assert_called_once_with()
        self.assertEqual(self.ask("POST", "/chat/tray", b'{"action":"quit"}', origin="http://evil.example")[0], 403)
        from web import settings_web
        with mock.patch.object(settings_web, "change", return_value=(True, "saved", None)) as change, \
                mock.patch("ui.conversation_pane._voice_on", return_value=True):
            self.assertEqual(self.ask("POST", "/chat/tray", b'{"action":"voice"}')[0], 200)
        change.assert_called_once_with("tts.enabled", False)

    def test_her_logo(self):
        code, body = self.ask("GET", "/chat/logo.png")
        self.assertEqual(code, 200)
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_typed_words_go_in_as_typed(self):
        code, _ = self.ask("POST", "/chat/say", json.dumps({"text": "  /help "}).encode())
        self.assertEqual(code, 200)
        self.assertEqual(self.sent, [("/help", None)])

    def test_empty_long_and_foreign(self):
        self.assertEqual(self.ask("POST", "/chat/say", b'{"text":"  "}')[0], 400)
        self.assertEqual(self.ask("POST", "/chat/say", json.dumps({"text": "x" * (chat_web.MAX_TYPED + 1)}).encode())[0], 413)
        self.assertEqual(self.ask("POST", "/chat/say", b"text=hi", kind="application/x-www-form-urlencoded")[0], 415)
        self.assertEqual(self.ask("POST", "/chat/say", b'{"text":"hi"}', origin="http://evil.example")[0], 403)
        self.assertEqual(self.sent, [])

    def test_a_file_with_the_words(self):
        boundary = "XyZ"
        form = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\nread this\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"notes.txt\"\r\n"
                f"Content-Type: text/plain\r\n\r\nthe cat is called Biscuit\r\n--{boundary}--\r\n").encode()
        code, body = self.ask("POST", "/chat/say", form, kind=f"multipart/form-data; boundary={boundary}")
        self.assertEqual(code, 200, body)
        text, attachment = self.sent[0]
        self.assertEqual(text, "read this")
        self.assertEqual(attachment.name, "notes.txt")
        self.assertIn("Biscuit", attachment.text)

    def test_too_big_is_said_not_cut(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("POST", "/chat/say", skip_host=True)
        c.putheader("Host", f"127.0.0.1:{self.port}")
        c.putheader("Content-Type", "multipart/form-data; boundary=x")
        c.putheader("Content-Length", str(chat_web.MAX_BODY + 1))
        c.endheaders()
        self.assertEqual(c.getresponse().status, 413)
        c.close()

    def test_answering_a_tool_question(self):
        got = {}
        with mock.patch.object(ui.view, "app", object()):
            t = threading.Thread(target=lambda: got.setdefault("a", ui.ask_approval("Write a file", ["notes.md"], timeout=10)))
            t.start()
            for _ in range(100):
                if ui.pending_approval():
                    break
                time.sleep(0.02)
            q = ui.pending_approval()
            self.assertEqual(q["title"], "Write a file")
            self.assertEqual(self.ask("POST", "/chat/answer", json.dumps({"id": q["id"] + 1, "answer": "yes"}).encode())[0], 409)
            self.assertEqual(self.ask("POST", "/chat/answer", json.dumps({"id": q["id"], "answer": "maybe"}).encode())[0], 400)
            self.assertEqual(self.ask("POST", "/chat/answer", json.dumps({"id": q["id"], "answer": "yes"}).encode())[0], 200)
            t.join(5)
        self.assertIs(got["a"], True)
        self.assertIsNone(ui.pending_approval())

    def test_the_mic_button_is_home(self):
        pressed = []
        with mock.patch.object(ui.view, "on_hotkey", lambda: pressed.append(1)), mock.patch.object(ui.view, "loop", None):
            self.assertEqual(self.ask("POST", "/chat/talk")[0], 200)
        self.assertEqual(pressed, [1])
        with mock.patch.object(ui.view, "on_hotkey", None):
            self.assertEqual(self.ask("POST", "/chat/talk")[0], 503)
            self.assertIs(chat_web.state(None, 0, None)["can_talk"], False)

    def test_the_mic_lights_while_she_listens(self):
        import sys
        import types

        fake = types.SimpleNamespace(listening=lambda: True)
        with mock.patch.dict(sys.modules, {"voice.ptt": fake}):
            self.assertIs(chat_web.state(None, 0, None)["mic"], True)
        with mock.patch.dict(sys.modules, {"voice.ptt": None}):
            self.assertIs(chat_web.state(None, 0, None)["mic"], False)

    def test_stop_stops_her_and_her_toys(self):
        import sys
        import types

        from core import interrupts
        import plugins

        with mock.patch.dict(sys.modules, {"voice.ptt": None}), mock.patch.object(interrupts, "home") as home, \
                mock.patch.object(plugins, "panic") as panic:
            self.assertEqual(self.ask("POST", "/chat/stop")[0], 200)
        home.assert_called_once_with()
        panic.assert_called_once_with()
        fake = types.SimpleNamespace(stop=mock.Mock())
        with mock.patch.dict(sys.modules, {"voice.ptt": fake}):
            self.assertEqual(self.ask("POST", "/chat/stop")[0], 200)
        fake.stop.assert_called_once_with()


class Command(unittest.TestCase):
    def test_slash_chat_opens_the_page(self):
        import config
        from commands import portrait

        with mock.patch.object(config, "MONITOR_ENABLED", True), \
                mock.patch.object(chat_web, "open_window") as opened, \
                mock.patch.object(ui, "add_message"):
            self.assertTrue(portrait.handle("/chat"))
        opened.assert_called_once_with()
        with mock.patch.object(config, "MONITOR_ENABLED", False), \
                mock.patch.object(chat_web, "open_window") as opened, \
                mock.patch.object(ui, "add_message") as said:
            self.assertTrue(portrait.handle("/chat"))
        opened.assert_not_called()
        self.assertIn("monitor.enabled", said.call_args[0][1])


class Pose(unittest.TestCase):
    def test_pose_opens_its_own_window(self):
        import config
        from commands import portrait
        from web import portrait_window

        with mock.patch.object(config, "MONITOR_ENABLED", True), \
                mock.patch.object(portrait_window, "open_app") as opened, mock.patch.object(ui, "add_message"):
            self.assertTrue(portrait.handle("/pose"))
        url, w, h = opened.call_args[0]
        self.assertTrue(url.endswith("/portrait/?debug=1"))
        self.assertEqual(opened.call_args.kwargs["profile"], "luna-studio")


class Switcher(unittest.TestCase):
    def test_every_page_gets_her_header(self):
        chat_web.register()
        page = livefeed.with_switcher("<html><body class=x><p>hi</p></body></html>", "live")
        self.assertIn('<body class=x><script src="/chat/head.js"></script><p>', page)
        self.assertNotIn("luna-nav", page)

    def test_without_the_chat_page_the_old_pill(self):
        with mock.patch.dict(livefeed.PAGES, clear=True):
            page = livefeed.with_switcher("<body></body>", "live")
        self.assertIn("luna-nav", page)
        self.assertNotIn("head.js", page)


if __name__ == "__main__":
    unittest.main()
