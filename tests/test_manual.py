"""Her own manual (tools/manual.py): questions about Luna answered from
her docs, with the real commands.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
import tools  # noqa: E402
from tools import manual  # noqa: E402


class Manual(unittest.TestCase):
    def test_chess_question_finds_the_chess_commands(self):
        out = manual._read_manual("how do I play chess with you")
        self.assertIn("/chess on", out)
        self.assertIn("docs/games.md", out)

    def test_heading_matters(self):
        top = manual.search("wake word", 1)[0][1]
        self.assertIn("wake word", (top["heading"] + top["text"]).lower())

    def test_nothing_found_says_so(self):
        out = manual._read_manual("zzqx flibbertigibbet")
        self.assertIn("not sure", out)

    def test_always_offered(self):
        self.assertEqual(tools.group_of("read_manual"), "Help")
        self.assertIn("Help", config.TOOLS_CORE)

    def test_reindexes_only_when_a_doc_changes(self):
        first = manual._items()
        self.assertIs(manual._items(), first)


if __name__ == "__main__":
    unittest.main()
