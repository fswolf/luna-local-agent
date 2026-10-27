"""plugins/ask.py: she asks a bigger model only when you tell her to.
No network: the call itself is replaced.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from core import turnctx  # noqa: E402
from plugins import ask  # noqa: E402


class Ask(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.patches = [
            mock.patch.object(ask, "_call", lambda p, q: self.calls.append((p, q)) or f"{p} says 42"),
            mock.patch.object(ask, "_key", lambda p: "k" if p in ("claude", "grok") else ""),
            mock.patch.object(ask, "_lewd", lambda: False),
            mock.patch.object(ask, "settings", lambda: {"provider": "claude", "models": {},
                                                        "daily_cap": 3, "max_tokens": 600}),
        ]
        for p in self.patches:
            p.start()
        ask._used.update(day="", count=0)
        ask.start()

    def tearDown(self):
        ask.stop()
        for p in self.patches:
            p.stop()

    def run_tool(self, said, question="what is 6x7?", **turn):
        ask.on_user_text(said)
        with turnctx.begin(**turn):
            return ask._run(question)

    def test_only_when_you_ask(self):
        self.assertIn("didn't ask", self.run_tool("what's 6 times 7?"))
        self.assertEqual(self.calls, [])
        self.assertIn("claude says 42", self.run_tool("ask Claude what 6 times 7 is"))
        self.assertIn("grok says 42", self.run_tool("can you check with grok?"))
        self.assertIn("claude says 42", self.run_tool("ask your big brother"))      # the default

    def test_a_message_is_good_for_a_follow_up_not_more(self):
        ask.on_user_text("ask claude about heat pumps")
        with turnctx.begin():
            self.assertIn("Claude answered", ask._run("how do heat pumps work?"))
            self.assertIn("Claude answered", ask._run("are they good in Alberta winters?"))
            self.assertIn("didn't ask", ask._run("and a third?"))

    def test_not_for_anyone_else(self):
        for turn in ({"private": False}, {"speaker": "guest"}, {"remote": "discord"}, {"job": "nightly"}):
            self.assertIn("Only the user's", self.run_tool("ask claude", **turn), turn)
        self.assertEqual(self.calls, [])

    def test_not_in_the_lewd_row(self):
        with mock.patch.object(ask, "_lewd", lambda: True):
            self.assertIn("Not now", self.run_tool("ask claude"))
        self.assertEqual(self.calls, [])

    def test_daily_cap(self):
        for _ in range(3):
            self.assertTrue(ask.ask("claude", "q")[0])
        ok, why = ask.ask("claude", "q")
        self.assertFalse(ok)
        self.assertIn("3 questions", why)

    def test_off_means_off(self):
        ask.stop()
        ask.on_user_text("ask claude")
        self.assertFalse(ask.running())
        import tools
        self.assertNotIn("ask_bigger_model", tools.names())

    def test_the_command(self):
        self.assertEqual(ask.command("what is 6x7?"), "Claude: claude says 42")
        self.assertEqual(ask.command("with grok what is 6x7?"), "Grok: grok says 42")
        self.assertIn("no ChatGPT key", ask.command("with openai hi"))
        self.assertEqual(ask._used["count"], 2)                                # that one didn't count
        self.assertIn("keys      claude, grok", ask.command(""))

    def test_only_the_question_goes(self):
        self.run_tool("ask claude", question="  what is 6x7?  ")
        self.assertEqual(self.calls, [("claude", "what is 6x7?")])


if __name__ == "__main__":
    unittest.main()
