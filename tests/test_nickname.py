"""Her nickname from agent.json is in her prompt (llm/prompts.py), so she
knows the second name she answers to.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

import config  # noqa: E402
from llm import prompts  # noqa: E402


class Nickname(unittest.TestCase):
    def test_in_the_prompt(self):
        # the pieces faked: building them for real routes tools, and that
        # state leaks into the routing pane's tests
        pieces = dict.fromkeys(("user", "profile", "now", "situation", "timing", "feelings",
                                "gestures", "tools", "memory", "self", "summary"), "")
        with mock.patch.dict(config.agent, {"nickname": "Echo"}), \
                mock.patch.object(prompts, "_pieces", return_value=pieces):
            system, _live = prompts.build_prompt_parts("hi")
            self.assertIn(f"You are {config.AGENT_NAME}, nicknamed Echo.", system)
            self.assertIn("nicknamed Echo", prompts.build_system_prompt("hi"))

    def test_none_or_the_same_name(self):
        with mock.patch.dict(config.agent, {"nickname": ""}):
            self.assertEqual(prompts.who_she_is(), f"You are {config.AGENT_NAME}.")
        with mock.patch.dict(config.agent, {"nickname": config.AGENT_NAME.upper()}):
            self.assertEqual(prompts.who_she_is(), f"You are {config.AGENT_NAME}.")


class TraitsAndRules(unittest.TestCase):
    def test_a_list_one_a_line(self):
        self.assertEqual(prompts.as_lines(["Flirts; calls you pet names", " ", "Curious,  asks"]),
                         "- Flirts; calls you pet names\n- Curious, asks")

    def test_a_paragraph_as_it_is(self):
        self.assertEqual(prompts.as_lines("  Flirty and playful, loves cats.  "), "Flirty and playful, loves cats.")
        self.assertEqual(prompts.as_lines(None), "")

    def test_in_her_manner(self):
        with mock.patch("config.TRAITS", ["Teases"], create=True), \
                mock.patch("config.RULES", "Be honest.", create=True):
            manner = prompts._manner()
        self.assertIn("Traits:\n- Teases", manner)
        self.assertIn("Rules:\nBe honest.", manner)


if __name__ == "__main__":
    unittest.main()
