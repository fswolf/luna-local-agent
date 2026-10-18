"""Touch talk: a click on her portrait reaches touches.py, and she
answers it in one short line - gathered, rate-limited, never over you."""
import http.client
import json
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.offline  # noqa: F401,E402

import config  # noqa: E402
import touches  # noqa: E402


class Gathering(unittest.TestCase):
    def setUp(self):
        touches._pending.clear()
        touches._state.update(model="m", timer=None, last=0.0)
        self.saved = config.PORTRAIT_TOUCH_TALK
        config.PORTRAIT_TOUCH_TALK = True

    def tearDown(self):
        config.PORTRAIT_TOUCH_TALK = self.saved
        if touches._state["timer"]:
            touches._state["timer"].cancel()
        touches._state["timer"] = None
        touches._pending.clear()

    def test_pokes_become_one_touch(self):
        with mock.patch.object(touches, "_answer") as answer:
            for zone in ("head", "head", "nose", "bogus"):
                touches.note(zone)
            touches._state["timer"].cancel()
            touches._fire()
        answer.assert_called_once_with({"head": 2, "nose": 1})
        self.assertEqual(touches.describe({"head": 2, "nose": 1}), "on the head, 2 times and on the nose")
        self.assertEqual(touches.describe({"tummy": 1}), "on the tummy")

    def test_off_or_too_soon_says_nothing(self):
        with mock.patch.object(touches, "_answer") as answer:
            config.PORTRAIT_TOUCH_TALK = False
            self.assertFalse(touches.note("head"))
            config.PORTRAIT_TOUCH_TALK = True
            touches.note("head")
            touches._state["timer"].cancel()
            touches._state["last"] = __import__("time").monotonic()     # she just answered one
            touches._fire()
        answer.assert_not_called()

    def test_her_line_is_one_line(self):
        self.assertEqual(touches.clean("<think>hmm</think>\n\n\"Hey! Hands to yourself~\"\nAnd more."),
                         "Hey! Hands to yourself~")
        self.assertEqual(touches.clean("<think>never closed"), "")


class Answering(unittest.TestCase):
    """_answer with the model, screen and voice stood in."""

    def run_answer(self, reply, busy=False):
        import assistant

        added = []
        with mock.patch.object(touches, "_quiet_now", return_value=not busy), \
             mock.patch.object(touches, "_request", return_value=reply) as request, \
             mock.patch("history.get_messages_full", return_value=[]), \
             mock.patch("history.add_message", side_effect=lambda r, c, **k: added.append((r, c))), \
             mock.patch("history.save"), mock.patch("transcript.add"), \
             mock.patch("mood.note_exchange") as mood_heard, \
             mock.patch("llm.build_system_prompt", return_value="SYSTEM"), \
             mock.patch("speech.Player") as player, \
             mock.patch("ui.add_message"), mock.patch("ui.begin_message"), mock.patch("ui.extend_message"), \
             mock.patch("ui.end_message"), mock.patch("ui.set_status"):
            touches._state.update(model="m", last=0.0)
            touches._answer({"head": 1})
        self.assertFalse(assistant._turn.locked())          # always let go
        return request, added, mood_heard, player

    def test_she_answers_and_remembers(self):
        request, added, mood_heard, player = self.run_answer("Mm~ more pats, please.")
        note = request.call_args.args[0][-1]["content"]
        self.assertIn("touched you on the head", note)
        self.assertEqual(added, [("user", "*touches you on the head*"), ("assistant", "Mm~ more pats, please.")])
        mood_heard.assert_called_once()
        player.return_value.say.assert_called_once_with("Mm~ more pats, please.")

    def test_not_while_busy(self):
        request, added, _m, player = self.run_answer("hi", busy=True)
        request.assert_not_called()
        self.assertEqual(added, [])


class Endpoint(unittest.TestCase):
    """POST /portrait/touch on the live monitor."""

    def setUp(self):
        import livefeed

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), livefeed._Handler)
        self.port = self.server.server_address[1]
        self.patch = mock.patch.object(livefeed, "port", return_value=self.port)
        self.patch.start()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.patch.stop()

    def post(self, body, kind="application/json", origin=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": kind, "Host": f"127.0.0.1:{self.port}"}
        if origin:
            headers["Origin"] = origin
        c.request("POST", "/portrait/touch", body=body, headers=headers)
        status = c.getresponse().status
        c.close()
        return status

    def test_only_json_from_her_own_page(self):
        with mock.patch.object(touches, "note") as note:
            self.assertEqual(self.post(json.dumps({"zone": "head"})), 204)
            self.assertEqual(self.post("zone=head", kind="application/x-www-form-urlencoded"), 400)
            self.assertEqual(self.post(json.dumps({"zone": "head"}), origin="http://evil.example"), 403)
        note.assert_called_once_with("head")


if __name__ == "__main__":
    unittest.main()
