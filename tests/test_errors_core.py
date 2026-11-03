"""Error handling in core/ and llm/: the failures that used to print over
the screen, loop, hang a turn or lose a file, each held to what it does
now. Nothing here reaches a real server.

    python -m unittest tests.test_errors_core        (from the repo folder)
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import requests  # noqa: E402

import config  # noqa: E402
from core import assistant, chatroom, control, firstrun, history, lmstudio, logbook, mcpclient  # noqa: E402
from llm import streaming, turns  # noqa: E402


class JobTimer(unittest.TestCase):
    """A game turn's time limit is a typed setting; Timer(1e12) raised
    OverflowError in its own thread, every turn."""

    def _limit(self, value):
        made = []

        class FakeTimer:
            def __init__(self, interval, fn):
                made.append(interval)
                self.daemon = False

            def start(self):
                pass

            def cancel(self):
                pass

        with mock.patch.object(assistant.threading, "Timer", FakeTimer), \
                mock.patch.object(assistant, "_gone", return_value=None), \
                mock.patch.object(assistant, "ask", return_value="ok"), \
                mock.patch.object(assistant, "ui"):
            assistant.respond_to_job("p", "m", "game", [], speak=False, time_limit=value)
        return made

    def test_huge_limit_is_clamped(self):
        self.assertEqual(self._limit(1e12), [86400])
        self.assertEqual(self._limit(float("inf")), [86400])

    def test_nan_or_nothing_means_no_timer(self):
        self.assertEqual(self._limit(float("nan")), [])
        self.assertEqual(self._limit(None), [])
        self.assertEqual(self._limit(-5), [])

    def test_ordinary_limit_kept(self):
        self.assertEqual(self._limit(150), [150.0])


class FirstRunBrokenAgentFile(unittest.TestCase):
    """A typo in agent.json reads as {} - which looked like a first start,
    and the setup then wrote a lone user block over the whole file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "agent.json")
        with open(self.file, "w") as f:
            f.write('{"name": "Luna", "personality": "kind",}')     # trailing comma
        self.patch = mock.patch.object(config, "AGENT_FILE", self.file)
        self.patch.start()
        self.agent = dict(config.agent)
        config.agent.clear()

    def tearDown(self):
        self.patch.stop()
        config.agent.clear()
        config.agent.update(self.agent)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_not_needed_when_unreadable(self):
        self.assertFalse(firstrun.needed())

    def test_save_refuses_and_leaves_file(self):
        with open(self.file) as f:
            before = f.read()
        with self.assertRaises(ValueError):
            firstrun.save_user("Ryan", "he/him")
        with open(self.file) as f:
            self.assertEqual(f.read(), before)

    def test_missing_file_is_still_a_first_start(self):
        os.remove(self.file)
        self.assertTrue(firstrun.needed())


class HistoryFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "conversation.json")
        self.patches = [mock.patch.object(history, "HISTORY_DIR", self.tmp),
                        mock.patch.object(history, "HISTORY_FILE", self.file),
                        mock.patch.object(logbook, "tell")]
        for p in self.patches:
            p.start()
        self.saved = (history._data, history._hold_saves, history._retry_after)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        history._data, history._hold_saves, history._retry_after = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, text):
        with open(self.file, "w") as f:
            f.write(text)

    def test_corrupt_file_is_set_aside_not_overwritten(self):
        self._write('{"summary": "x", "messages": [')
        history.load()
        self.assertEqual(history._data["messages"], [])
        backups = [n for n in os.listdir(self.tmp) if n.startswith("conversation.json.bad-")]
        self.assertEqual(len(backups), 1)
        with open(os.path.join(self.tmp, backups[0])) as f:
            self.assertIn('"summary": "x"', f.read())
        logbook.tell.assert_called()

    def test_wrong_shape_and_bad_messages(self):
        self._write("[1, 2]")
        history.load()
        self.assertEqual(history._data, {"summary": "", "messages": []})

        self._write(json.dumps({"summary": 5, "messages": [
            {"role": "user", "content": "hi"}, "junk", {"content": "no role"}]}))
        history.load()
        self.assertEqual(history.get_messages(), [{"role": "user", "content": "hi"}])
        self.assertEqual(history.get_summary(), "")

    def test_save_is_atomic_and_failure_is_told(self):
        history.load()
        history._data = {"summary": "", "messages": [{"role": "user", "content": "hi"}]}
        history.save()
        with open(self.file) as f:
            self.assertEqual(json.load(f)["messages"][0]["content"], "hi")
        self.assertFalse(os.path.exists(self.file + ".tmp"))

        with mock.patch("builtins.open", side_effect=OSError("disk full")):
            history.save()
        logbook.tell.assert_called()
        with open(self.file) as f:
            self.assertEqual(json.load(f)["messages"][0]["content"], "hi")

    def test_summary_failure_backs_off(self):
        history._data = {"summary": "", "messages": [
            {"role": "user", "content": str(i)} for i in range(config.MAX_RAW_MESSAGES + 5)]}
        history._retry_after = 0.0
        with mock.patch.object(history, "_summarize_chunk", side_effect=RuntimeError("down")):
            history._fold("m")
        self.assertGreater(history._retry_after, 0)
        with mock.patch.object(history.threading, "Thread") as thread:
            history.maybe_summarize("m")
        thread.assert_not_called()


class Streaming(unittest.TestCase):
    def test_blocking_request_has_a_timeout(self):
        seen = {}

        def post(*a, **kw):
            seen.update(kw)
            response = mock.Mock(status_code=200)
            response.json.return_value = {"choices": [{"message": {"content": "hi"}}]}
            return response

        with mock.patch.object(streaming.requests, "post", post):
            streaming._chat_completion({"messages": []})
        self.assertIsNotNone(seen.get("timeout"))

    def test_non_dict_reply_is_a_clear_error(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = ["nope"]
        with mock.patch.object(streaming.requests, "post", return_value=response):
            with self.assertRaises(RuntimeError):
                streaming._chat_completion({"messages": []})

    def test_drop_mid_stream(self):
        def lines():
            yield b'data: {"choices": [{"delta": {"content": "Hel"}}]}'
            raise requests.exceptions.ChunkedEncodingError("Connection broken")

        response = mock.MagicMock(status_code=200)
        response.__enter__.return_value = response
        response.iter_lines.return_value = lines()
        with mock.patch.object(streaming.requests, "post", return_value=response), \
                mock.patch.object(streaming.lmstudio, "mark_failed") as failed:
            got = []
            with self.assertRaises(RuntimeError) as caught:
                for delta in streaming._stream_deltas({}):
                    got.append(delta)
        self.assertEqual(got, [{"content": "Hel"}])
        self.assertIn("mid-reply", str(caught.exception))
        failed.assert_called()

    def test_odd_logprobs_dont_fail_the_turn(self):
        tokens = []
        streaming._note_tokens(tokens, {"content": "a", "_logprobs": {"content": [
            "junk",
            {"token": "a", "logprob": -2.0, "top_logprobs": [{"token": "b", "logprob": "x"}]},
        ]}})
        self.assertEqual(tokens, [["a", "a", -2.0, []]])


class ToolTemplate(unittest.TestCase):
    def test_only_a_missing_template_switches_tools_off(self):
        self.assertTrue(turns._no_tool_template(RuntimeError("This model does not support tools")))
        self.assertTrue(turns._no_tool_template(RuntimeError("Error rendering jinja template: tool_calls")))
        self.assertFalse(turns._no_tool_template(RuntimeError("Failed to parse tool call arguments")))
        self.assertFalse(turns._no_tool_template(RuntimeError("context length exceeded")))


class Mcp(unittest.TestCase):
    def test_no_loop_is_an_error_not_a_crash(self):
        with mock.patch.object(mcpclient, "_loop", None):
            mcpclient._connect("x", {"command": "true"})
        self.assertIn("didn't start", mcpclient._servers.pop("x")["error"])

    def test_one_broken_server_is_one_line(self):
        servers = {"a": {"command": "true"}, "b": {"command": "true"}}
        calls = []

        def connect(name, spec, timeout=None):
            calls.append(name)
            raise RuntimeError("boom")

        with mock.patch.object(config, "MCP_SERVERS", servers, create=True), \
                mock.patch.object(config, "MCP_ENABLED", True, create=True), \
                mock.patch.object(mcpclient, "available", return_value=True), \
                mock.patch.object(mcpclient, "_loop", object()), \
                mock.patch.object(mcpclient, "_connect", connect):
            lines = mcpclient.start()
        self.assertEqual(calls, ["a", "b"])
        self.assertEqual(len(lines), 2)
        self.assertIn("boom", lines[0])

    def test_loop_errors_go_to_the_log(self):
        with mock.patch.object(logbook, "error") as error:
            mcpclient._loop_error(None, {"message": "Task exception was never retrieved",
                                         "exception": ValueError("x")})
        error.assert_called()


class ChatRoomGuards(unittest.TestCase):
    def test_bad_numbers_are_clamped(self):
        room = chatroom.ChatRoom("t", "Ryan", {"cooldown_seconds": float("nan"),
                                               "user_cooldown_seconds": 1e300,
                                               "max_message_chars": "lots",
                                               "context_lines": float("inf")})
        self.assertEqual(room.cooldown, 8)
        self.assertEqual(room.user_cooldown, 86400)
        self.assertEqual(room.max_chars, 300)
        self.assertEqual(room.context_lines, 50)

    def test_worker_survives_an_error(self):
        room = chatroom.ChatRoom("t", "Ryan", {})
        handled = []

        def handle(*a):
            handled.append(a[2])
            if len(handled) == 1:
                raise ValueError("bad")
            room.stop()

        room._queue.put(("a", "one", 0))
        room._queue.put(("b", "two", 0))
        with mock.patch.object(room, "_handle", handle), \
                mock.patch.object(chatroom.time, "sleep"):
            room._answer_loop("m")
        self.assertEqual(handled, ["a", "b"])


class ControlAndHeader(unittest.TestCase):
    def test_failed_hotkey_is_told(self):
        server = mock.Mock()
        connection = mock.Mock()
        connection.recv.return_value = b"ptt\n"
        server.accept.side_effect = [(connection, None), OSError("closed")]

        def broken(_model):
            raise RuntimeError("no mic")

        with mock.patch.object(control, "_key", {"value": None}), \
                mock.patch.object(logbook, "tell") as tell:
            control._serve(server, "m", {"ptt": broken})
        self.assertIn("no mic", tell.call_args[0][0])

    def test_short_reasons(self):
        self.assertIn("nothing answering", lmstudio._short(requests.exceptions.ConnectionError("x" * 400)))
        self.assertEqual(lmstudio._short(requests.exceptions.ReadTimeout()), "timed out")
        self.assertLessEqual(len(lmstudio._short(ValueError("y" * 400))), 120)


if __name__ == "__main__":
    unittest.main()
