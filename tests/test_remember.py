"""Asking her to remember (mind/longterm.py, tools/memory.py, llm/turns.py):
the names she calls you aren't a sign of a leaked reply, a refusal says
why, and "remember this" without a remember_fact call still gets kept.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from mind import longterm  # noqa: E402


class Asked(unittest.TestCase):
    def test_telling_her(self):
        for said in ("Remember this: your mind runs on UnraidTower's RX 7900 XT",
                     "remember that I have an RTX 7800", "don't forget I work nights",
                     "keep this in mind", "make a note: the router password changed",
                     "iv told you this many times Remeber this your brain runs on a server",
                     "rember that I moved", "remmber this", "dont forget my birthday"):
            self.assertTrue(longterm.asked_to_remember(said), said)

    def test_not_telling_her(self):
        for said in ("I remember when we met", "do you remember my birthday?",
                     "did you remember to remind me?", "do you remeber my dog?", "I keep forgetting things",
                     "the rubber duck", "a reminder for later", ""):
            self.assertFalse(longterm.asked_to_remember(said), said)


class Refusals(unittest.TestCase):
    def test_a_pet_name_is_a_fact(self):
        self.assertEqual(longterm.why_not("Ryan likes being called Senpai and Daddy"), "")

    def test_reasons(self):
        self.assertIn("reply", longterm.why_not("Mrrp~ okay, got it"))
        self.assertIn("too long", longterm.why_not("x" * 400))
        self.assertIn("one line", longterm.why_not("one\ntwo"))

    def test_the_tool_says_why(self):
        from tools import memory
        with mock.patch.object(longterm, "add_fact", return_value=False):
            self.assertIn("reads like part of your reply", memory._remember_fact("Mrrp~ okay"))
            self.assertIn("already know", memory._remember_fact("Ryan has a cat"))


class TheSafetyNet(unittest.TestCase):
    def run_turn(self, text, called):
        seen = []
        with mock.patch("llm.turns._generate", lambda *x: "ok"), \
                mock.patch("tools.specs", lambda *x, **k: []), mock.patch("tools.begin_turn"), \
                mock.patch("llm.turns.turn_prompt", lambda *x, **k: ("SYSTEM", "")), \
                mock.patch("llm.turns._tool_rounds", lambda *x: "Got it!"), \
                mock.patch.dict("llm.turns._last_raw", {"called": set(called)}), \
                mock.patch("llm.turns._calibrate", lambda answer, *x: answer), \
                mock.patch("llm.turns._record_thoughts"), \
                mock.patch("core.history.add_message"), mock.patch("core.history.save"), \
                mock.patch("core.history.maybe_summarize"), mock.patch("core.transcript.add"), \
                mock.patch("training.dataset.note_turn"), \
                mock.patch("life.reminders.extract_in_background"), \
                mock.patch.object(longterm, "extract_in_background",
                                  lambda *a, **k: seen.append((a, k))):
            import llm
            from llm import session
            with mock.patch.object(session, "_tools_supported", True):
                llm.ask(text, "fake", tools_allowed=[], remember=True)
        return seen

    def test_kept_when_she_didnt_call_the_tool(self):
        seen = self.run_turn("Remember this: my new card is an RTX 7800", called=())
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0][1].get("asked"))

    def test_not_twice_when_she_did(self):
        self.assertEqual(self.run_turn("remember that I have an RTX 7800", called={"remember_fact"}), [])

    def test_not_for_ordinary_talk(self):
        self.assertEqual(self.run_turn("how was your day?", called=()), [])


if __name__ == "__main__":
    unittest.main()
