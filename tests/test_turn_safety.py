"""The safety rules that hang off a turn: who owns it, what it may do,
what it has seen. No model, no UI, no network - just the rules.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import threading
import unittest
from unittest import mock

import sys  # noqa: E402

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE as _FAKE  # noqa: E402  (first: no real servers)

import config  # noqa: E402
import tools  # noqa: E402
import turnctx  # noqa: E402
from tools import files, web  # noqa: E402

HOME = os.path.expanduser("~")


def _register(name, outside=False, group="Test"):
    calls = []

    def run(**kw):
        calls.append(turnctx.current())
        return "ok"

    tools.register_external(name, f"test tool {name}", {}, run=run, group=group, outside=outside)
    return calls


class TurnLifetime(unittest.TestCase):
    def test_turn_ends_with_its_block(self):
        with turnctx.begin(job="backup"):
            self.assertEqual(turnctx.current().job, "backup")
        self.assertIsNone(turnctx.current().job)
        self.assertFalse(turnctx.active())

    def test_other_threads_never_inherit_a_turn(self):
        seen = {}
        with turnctx.begin(job="backup", remote="discord", approver=lambda *a: True, seen="x"):
            t = threading.Thread(target=lambda: seen.update(job=turnctx.current().job,
                                                            remote=turnctx.current().remote,
                                                            approver=turnctx.current().approver,
                                                            seen=turnctx.current().seen))
            t.start()
            t.join()
        self.assertEqual(seen, {"job": None, "remote": None, "approver": None, "seen": None})

    def test_ensure_keeps_the_callers_passes(self):
        with turnctx.begin(job="backup"):
            with turnctx.ensure(source="typed") as turn:
                self.assertEqual(turn.job, "backup")

    def test_outside_a_turn_nothing_sticks(self):
        turnctx.current().seen = "page"
        self.assertIsNone(turnctx.current().seen)


class Taint(unittest.TestCase):
    def test_outside_tool_marks_its_turn_only(self):
        _register("t_outside", outside=True)
        with turnctx.begin():
            tools.call("t_outside", "{}")
            self.assertEqual(turnctx.current().seen, "t_outside")
        with turnctx.begin():
            self.assertIsNone(turnctx.current().seen)

    def test_web_asks_once_files_and_outside_content_mix(self):
        with turnctx.begin():
            self.assertTrue(web._may_send("search", "cats"))          # plain research
            turnctx.current().read_local = True
            self.assertTrue(web._may_send("search", "cats"))          # plain file reading
            turnctx.current().seen = "read_page"
            with mock.patch("ui.ask_approval", return_value=False) as asked:
                self.assertFalse(web._may_send("search", "cats"))
                asked.assert_called_once()


class FileWrites(unittest.TestCase):
    def setUp(self):
        self.jobdir = os.path.join(HOME, "luna-jobs-test")
        self.inside = os.path.join(self.jobdir, "report.txt")
        self.elsewhere = os.path.join(HOME, "notes-test.txt")
        self._dirs = config.FILES_JOB_WRITE_DIRS
        config.FILES_JOB_WRITE_DIRS = [self.jobdir]
        files.allow_all(False)

    def tearDown(self):
        config.FILES_JOB_WRITE_DIRS = self._dirs
        files.allow_all(False)

    def test_job_writes_only_in_its_folder_and_only_in_its_turn(self):
        with turnctx.begin(job="nightly"):
            self.assertTrue(files._job_may_write(self.inside))
            self.assertFalse(files._job_may_write(self.elsewhere))
        self.assertFalse(files._job_may_write(self.inside))         # turn over: no pass

    def test_job_pass_does_not_leak_to_another_thread(self):
        out = {}
        with turnctx.begin(job="nightly"):
            t = threading.Thread(target=lambda: out.update(ok=files._job_may_write(self.inside)))
            t.start()
            t.join()
        self.assertFalse(out["ok"])

    def test_allow_all_steps_aside_for_outside_content(self):
        files.allow_all(True)
        with mock.patch("ui.ask_approval", return_value=False) as asked:
            with turnctx.begin():
                self.assertTrue(files._ask("write", self.elsewhere, []))
                asked.assert_not_called()
                turnctx.current().seen = "read_page"
                self.assertFalse(files._ask("write", self.elsewhere, []))
                asked.assert_called_once()

    def test_discord_auto_approve_steps_aside_for_outside_content(self):
        with mock.patch.object(config, "FILES_AUTO_APPROVE_SOURCES", ["discord"]), \
                mock.patch("ui.ask_approval", return_value=False):
            with turnctx.begin(remote="discord"):
                self.assertTrue(files._ask("write", self.elsewhere, []))
                turnctx.current().seen = "mcp tool"
                self.assertFalse(files._ask("write", self.elsewhere, []))

    def test_discord_approver_answers_for_its_turn(self):
        asked = []
        approver = lambda kind, title, body, guarded: asked.append(kind) or False  # noqa: E731
        with turnctx.begin(remote="discord", approver=approver):
            self.assertFalse(files._ask("write", self.elsewhere, []))
        self.assertEqual(asked, ["write"])

    def test_deny_list(self):
        for path in ("~/.ssh/id_rsa", "~/.env", "~/.bashrc", "/etc/passwd"):
            with self.assertRaises(files.Refused, msg=path):
                files.resolve(path)


class Ceiling(unittest.TestCase):
    def test_a_narrow_turn_cannot_attach_tools_outside_it(self):
        _register("t_allowed", group="T1")
        _register("t_forbidden", group="T2")
        with turnctx.begin():
            tools.begin_turn(track=False)
            sent = [s["function"]["name"] for s in tools.specs(only=["t_allowed"], query="anything")]
            self.assertEqual(sent, ["t_allowed"])
            self.assertFalse(tools.attach("t_forbidden"))
            self.assertFalse(tools.attach("made_up_tool"))

    def test_routing_state_never_outlives_its_turn(self):
        _register("t_allowed2", group="T3")
        with turnctx.begin():
            tools.begin_turn()
            tools.specs(query="anything")
        with turnctx.begin():
            tools.begin_turn(track=False)
            tools.specs(only=["t_allowed2"], query="anything")
            self.assertFalse(tools.attach("t_allowed"))     # in the earlier turn's pool, not this one's


class ChatTurn(unittest.TestCase):
    """A whole stream-chat turn through llm.ask against a fake model server:
    it starts marked as outside content, and a tool outside its list is refused."""

    def test_chat_turn(self):
        import http.server
        probe = _register("t_probe", group="T4")
        forbidden = _register("t_secret", group="T5")
        plan = iter([["t_secret", "t_probe"], []])

        class Fake(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data":[{"id":"fake"}]}')

            def do_POST(self):
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls = next(plan, [])
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                def ev(d):
                    self.wfile.write(b"data: " + json.dumps(d).encode() + b"\n\n")

                if calls:
                    ev({"choices": [{"delta": {"tool_calls": [
                        {"index": i, "id": f"c{i}", "type": "function",
                         "function": {"name": n, "arguments": "{}"}} for i, n in enumerate(calls)]}}]})
                else:
                    ev({"choices": [{"delta": {"content": "Done."}}]})
                ev({"choices": [{"delta": {}, "finish_reason": "stop"}]})
                self.wfile.write(b"data: [DONE]\n\n")

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
        _FAKE.append(f"http://127.0.0.1:{srv.server_address[1]}/")

        import llm
        from llm import streaming
        with mock.patch.object(streaming, "LM_URL", url), \
                mock.patch.object(config, "ADAPTIVE_ENABLED", False, create=True):
            answer = llm.ask("hi", "fake", context=[], tools_allowed=["t_probe"], remember=False,
                             source="chat:test")
        srv.shutdown()
        srv.server_close()

        self.assertEqual(answer, "Done.")
        self.assertEqual(forbidden, [])                       # never ran
        self.assertEqual(len(probe), 1)
        self.assertEqual(probe[0].seen, "stream chat")        # started marked
        self.assertFalse(probe[0].private)


class EveryGuardReadsTheTurn(unittest.TestCase):
    """Each place that asks "who owns this turn, what has it seen" gets the
    answer from the turn. These broke silently once: they still read the
    old module globals through getattr(..., None), which never raises and
    always said "nobody, nothing"."""

    def test_shell_hands_outside_content_to_the_approver(self):
        from tools import shell
        asked = []
        approver = lambda kind, title, body, guarded: asked.append(guarded) or False  # noqa: E731
        with turnctx.begin(remote="discord", approver=approver):
            shell._run_command("echo hi")
            turnctx.current().seen = "read_page"
            shell._run_command("echo hi")
        self.assertEqual(asked, [False, True])

    def test_shell_auto_approve_steps_aside_for_outside_content(self):
        from tools import shell
        with mock.patch.object(config, "SHELL_AUTO_APPROVE_SOURCES", ["discord"], create=True), \
                mock.patch("ui.ask_approval", return_value=False) as asked, \
                mock.patch("subprocess.Popen") as ran:
            with turnctx.begin(remote="discord", seen="read_page"):
                out = shell._run_command("echo hi")
        asked.assert_called_once()
        ran.assert_not_called()
        self.assertIn("didn't approve", out)

    def test_toys_refuse_after_outside_content(self):
        from plugins import _toys
        with turnctx.begin():
            self.assertEqual(_toys.blocked(), "")
            turnctx.current().seen = "read_page"
            self.assertIn("outside content", _toys.blocked())

    def test_mcp_tools_ask_the_turns_approver(self):
        import mcpclient
        asked = []
        approver = lambda kind, title, body, guarded: asked.append(kind) or True  # noqa: E731
        with turnctx.begin(remote="discord", approver=approver):
            self.assertTrue(mcpclient._approve("srv", "do_thing", {}))
        self.assertEqual(asked, ["mcp"])

    def test_nothing_reads_the_old_globals(self):
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # state.py's globals are gone: a turn's passes are on the turn
        # (turnctx), its stop switches on its own Stop (interrupts).
        old = re.compile(r"state\.(job|remote|untrusted)\b|getattr\(state, \"(job|remote|untrusted)\"|^\s*import state\b")
        found = []
        for folder, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in (".git", "llama", "tests", "__pycache__") and not d.startswith(".")]
            for name in names:
                path = os.path.join(folder, name)
                # llm.py: the pre-split file. turnctx.py names the old globals it replaced.
                if not name.endswith(".py") or name in ("llm.py", "turnctx.py") and folder == root:
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    for n, line in enumerate(f, 1):
                        if old.search(line):
                            found.append(f"{os.path.relpath(path, root)}:{n}: {line.strip()}")
        self.assertEqual(found, [], "use turnctx.current() or interrupts.current() instead")


if __name__ == "__main__":
    unittest.main()
