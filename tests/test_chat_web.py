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


class MicDictates(unittest.TestCase):
    """The chat page's mic puts your words in its text box; HOME still sends."""

    def setUp(self):
        import sys
        import ui
        self.ptt = mock.Mock()
        self.ptt.mode.return_value = "auto"
        # only this one entry: patch.dict(sys.modules) put the whole table
        # back afterwards, dropping every module first imported meanwhile, and
        # a later test importing one of them again failed ("cannot load
        # module more than once per process")
        had = sys.modules.get("voice.ptt")
        sys.modules["voice.ptt"] = self.ptt
        self.addCleanup(lambda: sys.modules.__setitem__("voice.ptt", had) if had is not None
                        else sys.modules.pop("voice.ptt", None))
        patches = [mock.patch.object(ui.view, "on_hotkey", mock.Mock()),
                   mock.patch.object(ui.view, "loop", None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.start = chat_web.DICTATED["id"]

    def _dictate(self, heard):
        import threading
        done = threading.Event()
        def fake(mode):
            try:
                return heard
            finally:
                done.set()
        with mock.patch("core.assistant.dictation", side_effect=fake) as dictation, \
                mock.patch("ui.set_status"):
            self.assertIsNone(chat_web.dictate("pg1"))
            self.assertTrue(done.wait(2))
            for _ in range(100):
                if chat_web.DICTATED["id"] != self.start:
                    break
                time.sleep(0.01)
        return dictation

    def test_words_wait_for_the_page_and_nothing_is_answered(self):
        with mock.patch("core.assistant.respond") as respond:
            dictation = self._dictate("turn the lights down")
        dictation.assert_called_once_with("auto")
        respond.assert_not_called()
        self.assertNotEqual(chat_web.DICTATED["id"], self.start)
        self.assertEqual((chat_web.DICTATED["page"], chat_web.DICTATED["text"]), ("pg1", "turn the lights down"))
        self.assertEqual(chat_web.state(wait=0)["dictated"]["text"], "turn the lights down")

    def test_cancelled_is_not_nothing_heard(self):
        self._dictate(None)
        self.assertIsNone(chat_web.DICTATED["text"])

    def test_hands_free_mode_keeps_the_button_switching_it(self):
        import ui
        self.ptt.mode.return_value = "open"
        with mock.patch("core.assistant.dictation") as dictation:
            self.assertIsNone(chat_web.dictate())
        dictation.assert_not_called()
        ui.view.on_hotkey.assert_called_once()

    def test_a_click_while_recording_is_home(self):
        import ui
        from core import interrupts
        stop = interrupts.open("voice")
        self.addCleanup(interrupts.close, stop)
        with mock.patch("core.assistant.dictation") as dictation:
            chat_web.dictate()
        dictation.assert_not_called()
        ui.view.on_hotkey.assert_called_once()

    def test_her_answer_to_typing_doesnt_block_dictation(self):
        import ui
        from core import interrupts
        typed = interrupts.open("typed")
        self.addCleanup(interrupts.close, typed)
        self._dictate("and another thing")
        ui.view.on_hotkey.assert_not_called()
        self.assertFalse(typed.generating.is_set())       # her reply still finishes
        self.assertEqual(chat_web.DICTATED["text"], "and another thing")


class DictateRoute(unittest.TestCase):
    def test_the_page_id_reaches_dictate_and_the_page_still_loads(self):
        with mock.patch.object(chat_web, "dictate", return_value=None) as dictate:
            code, _kind, _body = chat_web.handle("POST", "/dictate", b'{"page": "abc"}')
            self.assertEqual(code, 200)
            dictate.assert_called_once_with("abc")
            self.assertEqual(chat_web.handle("POST", "/dictate", b"not json")[0], 200)
        self.assertEqual(chat_web.handle("GET", "/", b"")[0], 200)


class SayItAgain(unittest.TestCase):
    """The speaker under her reply: says it again, holding her turn while it
    plays, as any turn of hers does; again on it stops it."""

    def setUp(self):
        import threading
        import ui
        from ui.shared import _lock
        with _lock:
            self.saved = list(ui.conversation)
            ui.conversation[:] = [("user", "hi"), ("luna", "Hello there. How are you?"), ("system", "note")]
        self.addCleanup(self._restore)
        self.epoch = ui.view.epoch
        self.heard, self.done = [], threading.Event()

        def player(stop):                              # plays until stopped, or for a second
            p = mock.Mock(say=self.heard.append)
            p.wait.side_effect = lambda: (stop.speaking.wait(1), self.done.set())
            return p
        for patch in (mock.patch("ui.conversation_pane._voice_on", return_value=True),
                      mock.patch.object(chat_web, "_player", side_effect=player),
                      mock.patch.object(chat_web, "REPLAY_WAIT", 0.2)):
            patch.start()
            self.addCleanup(patch.stop)
        chat_web._replay.update(at=None, stop=None)

    def _restore(self):
        import ui
        from ui.shared import _lock
        stop = chat_web._replay["stop"]
        if stop is not None:
            stop.stop(speaking=True)
        self.done.wait(2)
        with _lock:
            ui.conversation[:] = self.saved

    def speak(self, i, e=None):
        code, _kind, body = chat_web.handle("POST", "/speak", json.dumps({"e": self.epoch if e is None else e, "i": i}).encode())
        return code, json.loads(body)

    def test_says_her_reply_holding_her_turn(self):
        from core import assistant
        self.assertEqual(self.speak(1), (200, {"ok": True, "playing": True}))
        self.assertEqual(chat_web.replaying(), [self.epoch, 1])
        self.assertEqual(chat_web.state(wait=0)["replay"], [self.epoch, 1])
        self.assertFalse(chat_web.state(wait=0)["stoppable"])   # Send stays Send: its speaker button stops it
        self.assertTrue(assistant._turn.locked())
        chat_web._replay["stop"].stop(speaking=True)
        self.assertTrue(self.done.wait(2))
        for _ in range(100):
            if not assistant._turn.locked():
                break
            time.sleep(0.01)
        self.assertFalse(assistant._turn.locked())          # given back when it's done
        self.assertEqual(" ".join(self.heard), "Hello there. How are you?")
        self.assertIsNone(chat_web.replaying())

    def test_again_on_the_same_one_stops_it(self):
        self.speak(1)
        stop = chat_web._replay["stop"]
        self.assertEqual(self.speak(1), (200, {"ok": True, "playing": False}))
        self.assertTrue(stop.speaking.is_set())
        self.assertIsNone(chat_web.replaying())

    def test_only_her_replies_still_on_screen(self):
        self.assertEqual(self.speak(0)[0], 409)          # yours
        self.assertEqual(self.speak(2)[0], 409)          # a system line
        self.assertEqual(self.speak(9)[0], 409)          # gone
        self.assertEqual(self.speak(1, e=self.epoch + 1)[0], 409)   # before a /clear

    def test_not_over_her_turn(self):
        from core import assistant
        assistant._turn.acquire()
        try:
            self.assertEqual(self.speak(1)[0], 409)
        finally:
            assistant._turn.release()
        self.assertEqual(self.heard, [])

    def test_a_new_turn_cuts_it_short_and_goes_ahead(self):
        from core import assistant
        self.speak(1)
        stop = chat_web._replay["stop"]
        with mock.patch.object(assistant, "_respond", return_value="ok"), \
                mock.patch.object(assistant, "_gone", return_value=None), \
                mock.patch.object(assistant, "_plugins_hear"), mock.patch.object(assistant, "_drift_mood"):
            self.assertEqual(assistant.respond("hi", "m"), "ok")
        self.assertTrue(stop.speaking.is_set())

    def test_a_reminder_waits_for_it(self):
        from life import reminders
        order = []
        self.speak(1)
        with mock.patch("llm.ask", side_effect=lambda *a, **k: order.append("reminder") or "ok"), \
                mock.patch("ui.add_message"), mock.patch("ui.set_status"), mock.patch("voice.speech.speak"), \
                mock.patch.object(reminders, "_note_away"), mock.patch.object(reminders, "_sticky"):
            import threading
            t = threading.Thread(target=reminders._deliver, args=("m", ["bins"]))
            t.start()
            t.join(0.2)
            order.append("replay ends")
            chat_web._replay["stop"].stop(speaking=True)
            t.join(2)
        self.assertEqual(order, ["replay ends", "reminder"])


class StopShowsForAnything(unittest.TestCase):
    """Her greeting after a restart isn't one of your turns, but Stop must
    still show for it (and for a reminder, a reply said again...)."""

    def test_a_greeting_is_stoppable_but_not_your_turn(self):
        from core import interrupts
        stop = interrupts.open("greeting")
        self.addCleanup(interrupts.close, stop)
        for st in (chat_web.state(wait=0), chat_web.state(wait=0, head=True)):
            self.assertFalse(st["busy"])
            self.assertTrue(st["stoppable"])

    def test_nothing_going_on(self):
        from core import interrupts
        with mock.patch.object(interrupts, "_open", []):
            st = chat_web.state(wait=0)
        self.assertFalse(st["stoppable"])
