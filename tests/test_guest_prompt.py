"""Someone else's turn (a housemate, a guest, a stranger) gets none of the
owner's notes in the prompt: his episodes, the summary of his older talk,
his projects, her recipes for his machine, his knowledge passages, his
screen and his reminders. Her lessons stay - they're about her.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.offline  # noqa: F401,E402

from core import turnctx  # noqa: E402
from llm import prompts  # noqa: E402

OWNERS = ("EPISODE-LAST", "EPISODE-OLD", "SUMMARY-OLD", "PROJECT-X", "RECIPE-Y", "KNOWLEDGE-Z")


class GuestPrompt(unittest.TestCase):
    def build(self, speaker):
        from mind import knowledge, notebook, projects, skills
        patches = [
            mock.patch.object(notebook, "relevant_lessons", lambda q: ["LESSON-MINE"]),
            mock.patch.object(notebook, "latest_episode", lambda: {"ended": "2026-11-01T10:00:00", "summary": "EPISODE-LAST"}),
            mock.patch.object(notebook, "relevant_episodes", lambda q: [{"ended": "2026-10-01T10:00:00", "summary": "EPISODE-OLD"}]),
            mock.patch.object(notebook, "game_feelings", lambda: {}),
            mock.patch.object(projects, "prompt_block", lambda q: "PROJECT-X"),
            mock.patch.object(skills, "prompt_block", lambda q: ("RECIPE-Y", [1])),
            mock.patch.object(knowledge, "prompt_block", lambda q: "KNOWLEDGE-Z"),
            mock.patch.object(prompts.history, "get_summary", lambda: "SUMMARY-OLD"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with turnctx.begin(source="voice", speaker=speaker):
            return prompts.build_system_prompt("hello")

    def test_owner_gets_his_notes(self):
        text = self.build(None)
        for marker in OWNERS + ("LESSON-MINE",):
            self.assertIn(marker, text)

    def test_someone_else_gets_none_of_them(self):
        for speaker in ("Shannon", "someone new"):
            text = self.build(speaker)
            for marker in OWNERS:
                self.assertNotIn(marker, text, (speaker, marker))
            self.assertIn("LESSON-MINE", text)         # hers, not his


class GuestSituation(unittest.TestCase):
    """The live lines: his screen and his reminders stay out on someone
    else's turn; the music and what she's holding are the room's."""

    def test_window_and_reminders_are_his(self):
        from mind import situation
        found = [("window", "Focused window: WINDOW-A"), ("music", "Playing: MUSIC-B"),
                 ("reminders", "Next reminder: REMIND-C"), ("hands", "In your hands: HANDS-D")]
        with mock.patch.object(situation, "_read", lambda: found), \
                mock.patch.object(situation, "enabled", lambda: True):
            situation._cache["at"] = 0.0
            with turnctx.begin(source="voice"):
                mine = situation.block()
            with turnctx.begin(source="voice", speaker="Shannon"):
                theirs = situation.block()
        situation._cache["at"] = 0.0
        for marker in ("WINDOW-A", "MUSIC-B", "REMIND-C", "HANDS-D"):
            self.assertIn(marker, mine)
        self.assertNotIn("WINDOW-A", theirs)
        self.assertNotIn("REMIND-C", theirs)
        self.assertIn("MUSIC-B", theirs)
        self.assertIn("HANDS-D", theirs)


if __name__ == "__main__":
    unittest.main()
