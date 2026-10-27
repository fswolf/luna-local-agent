"""The /commands (commands/): each area answers its own, a plain message
goes to her, and the moved code still runs.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import commands  # noqa: E402
import ui  # noqa: E402


class Dispatch(unittest.TestCase):
    def setUp(self):
        commands.setup("test-model", None)
        self.said = []
        p = mock.patch.object(ui, "add_message", side_effect=lambda who, text: self.said.append(text))
        p.start()
        self.addCleanup(p.stop)

    def test_a_message_is_not_a_command(self):
        self.assertFalse(commands.handle("hello luna, how was your day?"))

    def test_an_unknown_slash_is_not_a_command(self):
        self.assertFalse(commands.handle("/nosuchthing"))

    def test_safe_commands_run_and_answer(self):
        for text in ("/keys", "/scroll", "/reminders", "/alarms", "/when tomorrow at 9",
                     "/portrait models", "/plugins", "/mood", "/situation", "/lessons", "/skills",
                     "/projects", "/episodes", "/facts", "/presence", "/people"):
            self.said.clear()
            try:
                handled = commands.handle(text)
            except Exception as e:                      # a moved branch missing a name
                self.fail(f"{text}: {type(e).__name__}: {e}")
            self.assertTrue(handled, text)
            self.assertTrue(self.said, f"{text} said nothing")

    def test_every_area_is_asked(self):
        from commands import app, life, memory, people, plugins, portrait, reminders, settings, voice

        for area in (app, life, memory, people, plugins, portrait, reminders, settings, voice):
            self.assertFalse(area.handle("just talking"), area.__name__)


if __name__ == "__main__":
    unittest.main()
