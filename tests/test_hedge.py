"""The spoken hedge ("I'm not totally sure about that one, though.", llm/second_look.py):
only when the unsure run in her reply holds a specific - a number or a name -
never for banter that simply had many ways to be worded.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from llm import second_look  # noqa: E402
from mind import thoughtlog  # noqa: E402


class WhenToHedge(unittest.TestCase):
    def test_specifics(self):
        say = "The VRAM is sitting at 4.5 of 16 GB, and the capital is Canberra."
        self.assertTrue(second_look._unsure_of_a_specific(say, "at 4.5 of"))
        self.assertTrue(second_look._unsure_of_a_specific(say, "Canberra"))          # a name alone in the run

    def test_banter_is_not_a_guess(self):
        say = "*leans in closer, voice warm* Here's the thing though - you mentioned you're tired."
        self.assertFalse(second_look._unsure_of_a_specific(say, "leans in closer, voice"))
        self.assertFalse(second_look._unsure_of_a_specific(say, "Here's the thing"))   # a sentence start, not a name
        self.assertFalse(second_look._unsure_of_a_specific(say, ""))

    def _calibrated(self, answer, span):
        shape = {"conf": 0.4, "shaky": f'4 uncertain tokens in a row in the answer, "{span}"', "span": span}
        raw = {"tokens": [[("x", "a", -1.0)]], "exchanges": []}
        with mock.patch.object(second_look, "_last_raw", raw), \
                mock.patch.object(thoughtlog, "confidence", return_value=shape), \
                mock.patch.object(second_look, "_log_tool_call"), \
                mock.patch.object(second_look.livefeed, "emit"), \
                mock.patch("config.SELF_CALIBRATION", True, create=True), \
                mock.patch("config.SELF_HEDGE_BELOW", 0.6, create=True), \
                mock.patch("config.SELF_HEDGE_LINE", "I'm not totally sure about that one, though.", create=True):
            return second_look._calibrate(answer, None, True, None, None)

    def test_spoken_only_for_a_specific(self):
        self.assertTrue(self._calibrated("It has 20 GB of VRAM.", "20 GB of").endswith("though."))
        flirty = "*softens, eyes searching yours* Unless you'd rather I stay awake with you?"
        self.assertEqual(self._calibrated(flirty, "eyes searching yours"), flirty)

    def test_the_span_is_kept_whole(self):
        runs = [[("We", "a", 0.0)] + [(w, "a", -3.0) for w in (" at", " 4", ".5", " GB")] + [(".", "a", 0.0)]]
        with mock.patch.object(thoughtlog, "SHAKY_RUN", 3):
            self.assertEqual(thoughtlog.confidence(runs)["span"], "at 4.5 GB")


class WhenToLookAgain(unittest.TestCase):
    """The vote and the deeper look: a high-average reply with an unsure run
    gets another look only when that run holds a specific."""

    def run_vote(self, answer, span, conf=0.82):
        shape = {"conf": conf, "shaky": f'4 uncertain tokens in a row in the answer, "{span}"', "span": span}
        raw = {"tokens": [[("x", "a", -1.0)]], "thinking": [], "exchanges": []}
        with mock.patch.object(second_look, "_last_raw", raw), \
                mock.patch.object(thoughtlog, "confidence", return_value=shape), \
                mock.patch.object(second_look, "_chat_completion", side_effect=RuntimeError("offline")) as asked, \
                mock.patch.object(second_look, "_log_tool_call"), \
                mock.patch.object(second_look.livefeed, "emit"), \
                mock.patch("config.ADAPTIVE_RETHINK_BELOW", 0.75, create=True), \
                mock.patch("config.ADAPTIVE_VOTES", 2, create=True):
            second_look._vote({"messages": []}, [], answer, None, None)
        return asked.call_count

    def test_banter_gets_no_vote(self):
        self.assertEqual(self.run_vote("*leans in closer, voice warm* Stay up with me?", "leans in closer, voice"), 0)

    def test_a_shaky_specific_gets_one(self):
        self.assertEqual(self.run_vote("The card has 20 GB of VRAM.", "20 GB of"), 2)

    def test_unsure_on_average_still_does(self):
        self.assertEqual(self.run_vote("*smiles* Sure, it's running.", "smiles", conf=0.5), 2)


if __name__ == "__main__":
    unittest.main()
