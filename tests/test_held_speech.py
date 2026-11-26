"""Held speech and corrections (llm/turns.py, llm/second_look.py): she speaks
once the reply has been checked, a corrected reply is never half-said, and the
answer she settles on replaces the first instead of being added after it."""
import unittest
from unittest import mock

from llm import second_look, turns


class Held(unittest.TestCase):
    def setUp(self):
        self.said = []
        self.raw = {"exchanges": []}
        p = mock.patch.object(turns, "_last_raw", self.raw)
        p.start()
        self.addCleanup(p.stop)
        self.speech = turns._HeldSpeech(self.said.append)

    def test_nothing_is_said_until_released(self):
        self.speech("One.")
        self.speech("Two.")
        self.assertEqual(self.said, [])
        self.speech.release()
        self.assertEqual(self.said, ["One.", "Two."])
        self.speech("Three.")
        self.assertEqual(self.said, ["One.", "Two.", "Three."])

    def test_a_dropped_reply_is_never_said(self):
        self.speech("The wrong answer.")
        self.speech.drop()
        self.assertEqual(self.said, [])
        self.speech("After.")           # anything later (a hedge line) still goes out
        self.assertEqual(self.said, ["After."])

    def test_a_retry_forgets_the_failed_attempt(self):
        self.speech("Half a broken")
        self.speech.forget()
        self.speech("The retry.")
        self.speech.release()
        self.assertEqual(self.said, ["The retry."])

    def test_a_tool_round_releases_before_the_tool_runs(self):
        from llm import rounds
        heard_before_tool = []

        def chat(payload, narrator):
            narrator.feed("Let me check that for you. ")
            return {"content": "Let me check that for you.",
                    "tool_calls": [{"id": "1", "function": {"name": "system_health", "arguments": "{}"}}]}

        def emit(event, **k):
            if event == "tool":                  # the moment the tool starts
                heard_before_tool.extend(self.said)
                raise StopIteration              # only the order matters

        with mock.patch.object(rounds, "_chat_completion", side_effect=chat), \
                mock.patch.object(rounds, "_last_raw", {"called": set(), "exchanges": [], "thinking": [], "tokens": []}), \
                mock.patch.object(rounds.livefeed, "emit", side_effect=emit):
            with self.assertRaises(StopIteration):
                rounds._tool_rounds({"messages": [], "tools": []}, "m", None, self.speech)
        self.assertEqual(heard_before_tool, ["Let me check that for you."])

    def test_a_tool_call_lets_her_talk_as_she_goes(self):
        self.speech("Let me check.")
        self.raw["exchanges"] = [{"name": "system_health"}]
        self.speech("All good.")
        self.assertEqual(self.said, ["Let me check.", "All good."])


class Correction(unittest.TestCase):
    def setUp(self):
        self.said = []

    def speak(self, held):
        with mock.patch("config.ADAPTIVE_PREFIX", "Hang on, let me correct that.", create=True):
            return second_look._say_correction("It's on port 8096.", self.said.append, held)

    def test_held_says_only_the_answer(self):
        self.assertEqual(self.speak(held=True), "It's on port 8096.")
        self.assertEqual(" ".join(self.said), "It's on port 8096.")

    def test_already_spoken_owns_up_first(self):
        self.speak(held=False)
        self.assertTrue(" ".join(self.said).startswith("Hang on, let me correct that."))

    def test_nothing_goes_to_the_screen(self):
        # the bubble is swapped for the final answer at the end of the turn,
        # never added to: _say_correction takes no on_text at all
        import inspect
        self.assertNotIn("on_text", inspect.signature(second_look._say_correction).parameters)


class BracketActions(unittest.TestCase):
    def test_her_own_brackets_become_actions(self):
        from life import gestures
        with mock.patch.object(gestures, "names", return_value=("wave", "top_off")):
            gestures._tag_cache.clear()
            self.assertEqual(gestures.strip("Oh wow [blushing] really?"), "Oh wow *blushing* really?")
            self.assertEqual(gestures.strip("[gets into position] There."), "*gets into position* There.")
            self.assertEqual(gestures.strip("Hi [wave] there"), "Hi there")          # a real tag is still cut
            for left in ("It's [01:23] now", "see [1]", "[the docs](https://x.y)", "use arr[index] there",
                         "`x = [foo, bar]`", "```python\nnames = [first, second]\n```", "```\nopen = [still, streaming]",
                         "a [[wiki link]] here"):
                self.assertEqual(gestures.strip(left), left)
            self.assertEqual(gestures.strip("[sighs] Fine: `d[key]`"), "*sighs* Fine: `d[key]`")
        gestures._tag_cache.clear()



class WholeTurn(unittest.TestCase):
    """Through ask(): what she says out loud, and what's returned and saved."""

    def turn(self, vote):
        from core import turnctx
        spoken, saved = [], []

        def rounds(payload, model, on_text, on_sentence):
            on_sentence("The card has 16 GB of VRAM.")
            turns._last_raw["tokens"] = [[("x", "a", -2.0)]]
            spoken.append("(first reply written)")
            return "The card has 16 GB of VRAM."

        def fake_vote(payload, base, answer, on_text, on_sentence, held=False):
            spoken.append("(vote ran, held=%s)" % held)
            return vote(on_sentence, held)

        with turnctx.begin(source=None), \
                mock.patch("llm.turns._adaptive_on", return_value=True), \
                mock.patch("config.ADAPTIVE_HOLD_SPEECH", True, create=True), \
                mock.patch("config.ADAPTIVE_MODE", "vote", create=True), \
                mock.patch("llm.turns._tool_rounds", side_effect=rounds), \
                mock.patch("llm.turns._vote", side_effect=fake_vote), \
                mock.patch("tools.specs", lambda *x, **k: []), mock.patch("tools.begin_turn"), \
                mock.patch("llm.turns.turn_prompt", lambda *x, **k: ("SYSTEM", "")), \
                mock.patch("llm.turns._calibrate", lambda answer, *x: answer), \
                mock.patch("llm.turns._ground", lambda answer, first, *x, **k: (answer, first, [], False)), \
                mock.patch("llm.turns._record_thoughts"), \
                mock.patch("core.history.add_message", side_effect=lambda role, text, **k: saved.append((role, text))), \
                mock.patch("core.history.save"), mock.patch("core.history.maybe_summarize"), \
                mock.patch("core.transcript.add"), mock.patch("training.dataset.note_turn"), \
                mock.patch("mind.longterm.extract_in_background"):
            import llm
            answer = llm.ask("how much VRAM?", "fake", on_sentence=spoken.append, remember=True)
        return answer, spoken, saved

    def test_a_correction_is_the_only_thing_said_and_kept(self):
        def corrected(on_sentence, held):
            said = second_look._say_correction("The card has 20 GB of VRAM.", on_sentence, held)
            return {"first": {}, "second": {}, "answer": "The card has 20 GB of VRAM.", "said": said,
                    "corrected": True, "conf": 0.4, "conf2": 0.9, "outcome": "corrected"}

        answer, spoken, saved = self.turn(corrected)
        self.assertEqual(answer, "The card has 20 GB of VRAM.")
        self.assertEqual(spoken, ["(first reply written)", "(vote ran, held=True)", "The card has 20 GB of VRAM."])
        self.assertEqual(saved[-1], ("assistant", "The card has 20 GB of VRAM."))

    def test_a_reply_that_stands_is_said_after_the_check(self):
        answer, spoken, saved = self.turn(lambda on_sentence, held: None)
        self.assertEqual(answer, "The card has 16 GB of VRAM.")
        self.assertEqual(spoken, ["(first reply written)", "(vote ran, held=True)", "The card has 16 GB of VRAM."])
        self.assertEqual(saved[-1], ("assistant", "The card has 16 GB of VRAM."))

class NothingCarriedOver(unittest.TestCase):
    def test_a_turn_without_tools_keeps_none_of_the_last_turns_calls(self):
        from core import turnctx
        from llm import session
        saved = []
        turns._last_raw["exchanges"] = [{"name": "run_command", "arguments": "{}", "result": "last turn"}]
        with turnctx.begin(source=None), mock.patch.object(session, "_tools_supported", False), \
                mock.patch("llm.turns._adaptive_on", return_value=False), \
                mock.patch("llm.turns._generate", lambda *x: "Just chatting."), \
                mock.patch("llm.turns.turn_prompt", lambda *x, **k: ("SYSTEM", "")), \
                mock.patch("llm.turns._calibrate", lambda answer, *x: answer), \
                mock.patch("llm.turns._ground", lambda answer, first, *x, **k: (answer, first, [], False)), \
                mock.patch("llm.turns._record_thoughts"), \
                mock.patch("core.history.add_message", side_effect=lambda role, text, **k: saved.append((role, k))), \
                mock.patch("core.history.save"), mock.patch("core.history.maybe_summarize"), \
                mock.patch("core.transcript.add"), mock.patch("training.dataset.note_turn"), \
                mock.patch("mind.longterm.extract_in_background"):
            import llm
            llm.ask("hi", "fake", remember=True)
        self.assertEqual(saved[-1][1].get("tools"), [])


if __name__ == "__main__":
    unittest.main()
