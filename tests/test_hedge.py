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

    def test_banter_leaves_no_note_for_next_turn(self):
        from llm.prompts import _calibration_note
        _calibration_note["text"] = ""
        self._calibrated("*softens* Unless you'd rather I stay awake with you?", "softens")
        self.assertEqual(_calibration_note["text"], "")     # "only 57% sure, be upfront" taught her to say it
        self._calibrated("It has 20 GB of VRAM.", "20 GB of")
        self.assertIn("sure", _calibration_note["text"])
        _calibration_note["text"] = ""

    def test_what_isnt_a_specific(self):
        with mock.patch("config.user_preferences", return_value={"nicknames": ["Daddy", "Senpai"]}):
            for say, span in (("*smirks*  You idiot.", "You idiot"),             # two spaces after an action
                              ("Always ready, Daddy~ Everything okay?", "ready, Daddy"),
                              ('She paused. "Hold onto it," she said.', '"Hold onto it'),
                              ("You're making me blush~ \U0001f43e That was sweet.", "That was"),
                              ("**The** part I like.", "The"),
                              ("**Tip**: Make it louder.", "Make it")):
                self.assertFalse(second_look._unsure_of_a_specific(say, span), say)
        self.assertTrue(second_look._unsure_of_a_specific("It's on port 8096 for Jellyfin.", "port 8096"))

    def test_the_span_is_kept_whole(self):
        runs = [[("We", "a", 0.0)] + [(w, "a", -3.0) for w in (" at", " 4", ".5", " GB")] + [(".", "a", 0.0)]]
        with mock.patch.object(thoughtlog, "SHAKY_RUN", 3):
            self.assertEqual(thoughtlog.confidence(runs)["span"], "at 4.5 GB")


class WhenToLookAgain(unittest.TestCase):
    """The vote and the deeper look: a reply under adaptive.rethink_below gets
    another look, whatever it's about; one above it only when an unsure run
    holds a specific (a number, a name)."""

    def run_vote(self, answer, span, conf=0.82, bar=0.75):
        shape = {"conf": conf, "shaky": f'4 uncertain tokens in a row in the answer, "{span}"', "span": span}
        raw = {"tokens": [[("x", "a", -1.0)]], "thinking": [], "exchanges": []}
        with mock.patch.object(second_look, "_last_raw", raw), \
                mock.patch.object(thoughtlog, "confidence", return_value=shape), \
                mock.patch.object(second_look, "_chat_completion", side_effect=RuntimeError("offline")) as asked, \
                mock.patch.object(second_look, "_log_tool_call"), \
                mock.patch.object(second_look.livefeed, "emit"), \
                mock.patch("config.ADAPTIVE_RETHINK_BELOW", bar, create=True), \
                mock.patch("config.ADAPTIVE_VOTES", 2, create=True):
            second_look._vote({"messages": []}, [], answer, None, None)
        return asked.call_count

    def test_sure_banter_gets_no_vote(self):
        self.assertEqual(self.run_vote("*leans in closer, voice warm* Stay up with me?", "leans in closer, voice"), 0)

    def test_a_shaky_specific_gets_one_even_when_sure(self):
        self.assertEqual(self.run_vote("The card has 20 GB of VRAM.", "20 GB of"), 2)

    def test_the_vote_is_for_facts_only(self):
        # it only swaps an answer whose facts differ: on banter it would ask
        # twice more and always keep the first, so it isn't asked
        self.assertEqual(self.run_vote("*pets your head* Welcome back~", "pets your", conf=0.38, bar=0.40), 0)

    def rethink(self, answer, conf, bar, second=None, shape2=None):
        shapes = iter([{"conf": conf, "shaky": "", "span": "x"}, shape2 or {}])
        raw = {"tokens": [[("x", "a", -1.0)]], "thinking": [], "exchanges": []}

        class Quiet:
            def finish(self):
                return second or ""
        with mock.patch.object(second_look, "_last_raw", raw), \
                mock.patch.object(thoughtlog, "confidence", side_effect=lambda t: next(shapes)), \
                mock.patch.object(second_look, "_Narrator", return_value=Quiet()), \
                mock.patch.object(second_look, "_chat_completion", return_value={}) as asked, \
                mock.patch.object(second_look, "_log_tool_call"), \
                mock.patch.object(second_look, "_same_answer", return_value=False), \
                mock.patch.object(second_look.livefeed, "emit"), \
                mock.patch("config.ADAPTIVE_RETHINK_BELOW", bar, create=True), \
                mock.patch("config.ADAPTIVE_MIN_GAIN", 0.05, create=True), \
                mock.patch("config.ADAPTIVE_DEEP_BUDGET", 1024, create=True), \
                mock.patch("config.ADAPTIVE_SPEAK_CORRECTIONS", True, create=True):
            out = second_look._rethink({"messages": []}, [], answer, None, None, held=True)
        return asked.call_count, out

    def test_rethink_under_the_bar_whatever_it_is_about(self):
        # Ryan, 2026-11-27: a fresh try at a shaky everyday reply is often better
        asked, _ = self.rethink("*pets your head* Welcome back~", conf=0.38, bar=0.40,
                                second="*nuzzles your hand* Missed you~",
                                shape2={"conf": 0.5, "shaky": "4 uncertain tokens", "span": "nuzzles your"})
        self.assertEqual(asked, 1)

    def test_a_surer_everyday_reply_replaces_the_first(self):
        # its own unsure word choice doesn't block it; only a shaky fact would
        _, out = self.rethink("*pets your head* Welcome back~", conf=0.38, bar=0.40,
                              second="*nuzzles your hand* Missed you~",
                              shape2={"conf": 0.5, "shaky": "4 uncertain tokens", "span": "nuzzles your"})
        self.assertTrue(out["corrected"])
        _, out = self.rethink("*pets your head* Welcome back~", conf=0.38, bar=0.40,
                              second="It's 9:41, welcome back~",
                              shape2={"conf": 0.5, "shaky": "4 uncertain tokens", "span": "9:41"})
        self.assertFalse(out["corrected"])

    def test_the_bar_fits_the_model(self):
        # at 0.40, the Q8 9B's ordinary 44% reply is its normal: no second look
        asked, out = self.rethink("Oh, you silly senpai~ You came crawling back already?", conf=0.44, bar=0.40)
        self.assertEqual((asked, out), (0, None))

    def test_the_deeper_look_follows_the_same_rule(self):
        shape = {"conf": 0.44, "shaky": "", "span": "leans in"}
        raw = {"tokens": [[("x", "a", -1.0)]], "thinking": [], "exchanges": []}
        with mock.patch.object(second_look, "_last_raw", raw), \
                mock.patch.object(thoughtlog, "confidence", return_value=shape), \
                mock.patch("config.ADAPTIVE_RETHINK_BELOW", 0.40, create=True), \
                mock.patch.object(second_look, "_chat_completion") as asked:
            self.assertIsNone(second_look._rethink({"messages": []}, [], "Still on PHP? *leans in*", None, None))
        asked.assert_not_called()
    def test_auto_picks_the_vote_for_a_fact_and_rethink_for_the_rest(self):
        def pick(mode, answer, span):
            with mock.patch("config.ADAPTIVE_MODE", mode, create=True), \
                    mock.patch.object(second_look, "_last_raw", {"tokens": [[("x", "a", -1.0)]]}), \
                    mock.patch.object(thoughtlog, "confidence", return_value={"conf": 0.3, "span": span, "shaky": "x"}):
                return second_look._second_look_for(answer)
        self.assertEqual(pick("auto", "The card has 20 GB of VRAM.", "20 GB of"), "vote")
        self.assertEqual(pick("auto", "*pets your head* Welcome back~", "pets your"), "rethink")
        self.assertEqual(pick("vote", "*pets your head* Welcome back~", "pets your"), "vote")
        self.assertEqual(pick("rethink", "The card has 20 GB of VRAM.", "20 GB of"), "rethink")


if __name__ == "__main__":
    unittest.main()


class NotInHerHistory(unittest.TestCase):
    """The hedge line is added by code; replayed as her own words fifteen
    times over, she started saying it herself."""

    def test_replay_leaves_it_out(self):
        from llm import replay
        line = "I'm not totally sure about that one, though."
        with mock.patch("config.SELF_HEDGE_LINE", line, create=True):
            out = replay._replay({"role": "assistant", "content": f"It has 20 GB. {line}"})
            self.assertEqual(out[-1]["content"], "It has 20 GB.")
            mine = replay._replay({"role": "user", "content": f"you said {line}"})
            self.assertIn(line, mine[-1]["content"])          # only her side


class CheckingAfterTheReply(unittest.TestCase):
    """A check that runs after she has answered (the grounding check, the
    second look's 'go and look') asks only for what changed: the reply is
    already on screen and heard, and she used to retell all of it."""

    def test_grounding_check_asks_only_for_the_change(self):
        from mind import grounding

        loose = [("number", "8%")]
        with mock.patch.object(grounding, "check", return_value=(loose, True)), \
                mock.patch.object(grounding, "mode", return_value="check"), \
                mock.patch.object(second_look, "_last_raw", {"exchanges": []}), \
                mock.patch.object(second_look, "_calibration_note", {"text": ""}), \
                mock.patch.object(second_look, "_log_tool_call"), \
                mock.patch.object(second_look.livefeed, "emit"), \
                mock.patch.object(second_look, "_follow_through", return_value="done") as follow:
            second_look._ground("GPU at 8%.", "GPU at 8%.", None, {"tools": [{}], "messages": []},
                                [], "m", None, None)
        self.assertIn(second_look._ONLY_WHAT_CHANGED, follow.call_args[0][-1])

    def test_second_look_asks_only_for_the_change(self):
        import inspect

        from llm import turns
        self.assertIn("_ONLY_WHAT_CHANGED", inspect.getsource(turns))
        self.assertIn("don't repeat it", second_look._ONLY_WHAT_CHANGED)
