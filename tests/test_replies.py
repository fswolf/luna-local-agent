"""Cleaning a reply: her reasoning never reaches the screen or the voice,
however the model marks it. No model, no network.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from llm import streaming  # noqa: E402


def _stream(pieces):
    shown, spoken = [], []
    n = streaming._Narrator(on_text=shown.append, on_sentence=spoken.append)
    for p in pieces:
        n.feed(p)
    return n.finish(), spoken


class Reasoning(unittest.TestCase):
    def test_a_closed_block_is_cut(self):
        self.assertEqual(streaming._content({"content": "<think>hmm</think>Hello there."}), "Hello there.")

    def test_an_unclosed_block_is_held_back(self):
        self.assertEqual(streaming._content({"content": "Hello. <think>still going"}), "Hello.")

    def test_a_close_with_no_open_means_it_was_reasoning(self):
        # What a model does when it thinks without opening the tag: the
        # server can't tell, and </think> is the only sign.
        msg = {"content": "The hat is cozy. Let me look around.</think>The nest is warm today."}
        self.assertEqual(streaming._content(msg), "The nest is warm today.")
        self.assertEqual(streaming._content({"content": "Bigger plans! Let me see~ </think>"}), "")

    def test_streamed_the_reply_starts_again_after_it(self):
        answer, spoken = _stream(["The hat is cozy. ", "Let me look ", "around.</thi", "nk>The nest ",
                                  "is warm today, and the rain is soft."])
        self.assertEqual(answer, "The nest is warm today, and the rain is soft.")
        self.assertEqual(spoken[-1], "The nest is warm today, and the rain is soft.")

    def test_its_kept_for_the_thought_log(self):
        streaming._last_raw["thinking"] = []
        streaming._note_thinking("Let me look around.</think>Hi there.")
        self.assertIn("Let me look around.", streaming._last_raw["thinking"][-1]["text"])

    def test_plain_replies_are_untouched(self):
        answer, spoken = _stream(["Hello there. ", "How was your day today?"])
        self.assertEqual(answer, "Hello there. How was your day today?")


if __name__ == "__main__":
    unittest.main()
