"""The tool loop (llm/rounds.py): a round after a tool that comes back
empty. No model, no server.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from core import interrupts  # noqa: E402
from llm import rounds  # noqa: E402

CALL = {"id": "c1", "type": "function",
        "function": {"name": "ask_bigger_model", "arguments": '{"question": "hi?"}'}}


def _payload():
    return {"model": "m", "messages": [{"role": "user", "content": "ask claude something"}],
            "tools": [{"type": "function", "function": {"name": "ask_bigger_model"}}]}


class AfterATool(unittest.TestCase):
    def run_turn(self, replies):
        sent = []

        def answer(payload, narrator=None):
            sent.append(payload)
            return replies.pop(0)

        with mock.patch.object(rounds, "_chat_completion", side_effect=answer), \
                mock.patch.object(rounds.tools, "call", return_value="Claude answered:\nLocal is good."), \
                mock.patch.object(rounds.tools, "refresh", return_value=None), \
                mock.patch.object(rounds, "_log_tool_call"):
            with interrupts.using(kind="typed"):
                return rounds._tool_rounds(_payload(), "m"), sent

    def test_an_empty_round_after_the_preamble_is_asked_again(self):
        said, sent = self.run_turn([
            {"content": "Let me ask Claude.", "tool_calls": [CALL]},
            {"content": ""},                              # the answer never came
            {"content": "Claude says local is good."},
        ])
        self.assertEqual(said, "Let me ask Claude. Claude says local is good.")
        self.assertEqual(len(sent), 3)
        self.assertNotIn("tools", sent[2])                # the retry offers no tools
        self.assertIn("using it", sent[2]["messages"][-1]["content"])

    def test_a_real_answer_after_the_tool_needs_no_retry(self):
        said, sent = self.run_turn([
            {"content": "Let me ask Claude.", "tool_calls": [CALL]},
            {"content": "Claude says local is good."},
        ])
        self.assertEqual(said, "Let me ask Claude. Claude says local is good.")
        self.assertEqual(len(sent), 2)

    def test_no_preamble_and_an_empty_answer_still_asks_for_the_result(self):
        said, sent = self.run_turn([
            {"content": "", "tool_calls": [CALL]},
            {"content": ""},
            {"content": "Claude says local is good."},
        ])
        self.assertEqual(said, "Claude says local is good.")
        self.assertIn("using it", sent[2]["messages"][-1]["content"])


if __name__ == "__main__":
    unittest.main()
