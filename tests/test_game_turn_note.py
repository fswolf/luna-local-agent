"""A game's turn goes without the clock (a 9B answered the time instead of
playing), and emoji variation selectors don't knock the conversation pane's
lines out of place."""
import unittest
from unittest import mock

from tests.offline import FAKE  # noqa: F401  (first: no real servers)


class GameTurnNote(unittest.TestCase):
    def note(self, **turn):
        from core import turnctx
        from llm import prompts

        with mock.patch.object(prompts, "stable_prompt", return_value=True), \
                turnctx.begin(source="job:gameboy", private=False, job="gameboy", **turn):
            return prompts.build_prompt_parts("", "", private=False)[1]

    def test_no_clock_on_a_game_turn(self):
        self.assertNotIn("Right now:", self.note(clock=False))

    def test_a_scheduled_job_keeps_it(self):
        self.assertIn("Right now:", self.note(clock=True))

    def test_your_own_turns_keep_it(self):
        from llm import prompts

        with mock.patch.object(prompts, "stable_prompt", return_value=True):
            self.assertIn("Right now:", prompts.build_prompt_parts("", "", private=False)[1])


class Terminal(unittest.TestCase):
    def test_variation_selector_dropped(self):
        from ui.text import for_terminal

        self.assertEqual(for_terminal("morning ☀️ dear 🌸"), "morning ☀ dear 🌸")


if __name__ == "__main__":
    unittest.main()
