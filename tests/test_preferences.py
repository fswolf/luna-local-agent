"""Your preferences (what she calls you, nicknames, what to avoid): agent.json's
"user_preferences" block, with memory.json's old copy as the fallback.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

import config  # noqa: E402
from config import base  # noqa: E402

PREFS = {"favorite_color": "Purple", "nicknames": ["Daddy", "Senpai"], "avoid": ["excessive disclaimers"]}


class WhereTheyLive(unittest.TestCase):
    def test_agent_json_first(self):
        with mock.patch.dict(base.agent, {"user_preferences": PREFS}), \
                mock.patch.dict(base.memory, {"user_preferences": {"old": "yes"}}):
            self.assertEqual(config.user_preferences(), PREFS)

    def test_old_memory_json_copy_until_moved(self):
        with mock.patch.dict(base.agent, {}, clear=True), \
                mock.patch.dict(base.memory, {"user_preferences": {"tone": "short"}}):
            self.assertEqual(config.user_preferences(), {"tone": "short"})

    def test_none_anywhere(self):
        with mock.patch.dict(base.agent, {}, clear=True), mock.patch.dict(base.memory, {}, clear=True):
            self.assertEqual(config.user_preferences(), {})
            self.assertEqual(config.preference_lines(), [])


class AsPromptLines(unittest.TestCase):
    def test_lists_read_as_words(self):
        with mock.patch.dict(base.agent, {"user_preferences": PREFS}):
            self.assertEqual(config.preference_lines(), [
                "favorite color: Purple", "nicknames: Daddy, Senpai", "avoid: excessive disclaimers"])

    def test_in_her_prompt_on_your_turns_only(self):
        from llm import prompts
        from mind import knowledge, pages

        def build(guest):
            # facts, pages and knowledge stubbed: they'd reach for the embedding
            # server, and its "down" would stick for the tests after this one
            with mock.patch.dict(base.agent, {"user_preferences": PREFS}), \
                    mock.patch.object(prompts.longterm, "relevant_facts", return_value=[]), \
                    mock.patch.object(pages, "prompt_block", return_value=""), \
                    mock.patch.object(knowledge, "prompt_block", return_value=""), \
                    mock.patch.object(prompts.people, "guest", return_value=guest):
                return prompts.build_memory_prompt("hi")

        mine = build(None)
        self.assertIn("nicknames: Daddy, Senpai", mine)
        self.assertNotIn("['Daddy'", mine)
        self.assertNotIn("Senpai", build("Mike"))


class TheEditorChecksIt(unittest.TestCase):
    def test_must_be_a_block(self):
        from web import settings_web
        good = '{"personality": "x", "user_preferences": {"a": "b"}}'
        self.assertEqual(settings_web.check_agent(good)["user_preferences"], {"a": "b"})
        with self.assertRaises(ValueError):
            settings_web.check_agent('{"personality": "x", "user_preferences": ["a"]}')


if __name__ == "__main__":
    unittest.main()
