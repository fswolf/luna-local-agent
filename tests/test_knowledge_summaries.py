"""What each knowledge file covers: written while idle, listed by browse,
a lift in search (mind/knowledge.py). Temporary folders and databases."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from mind import knowledge  # noqa: E402

FILES = {
    "game/00-index.md": "# The game\nAudience: Luna\n\nA guide to the game: the map, the puzzles and how to play it.\n",
    "game/01-map.md": "# Map\n\n## Cloud Nine Nest\nRain on the window, doors east to the Sanctuary.\n",
    "game/02-solutions.md": "# Solutions\nSpoilers: yes\n\nKill the troll with the sword, then take the lamp.\n",
    "network.md": "# My network\n\nThe NUC is the web server; Jellyfin runs on the tower on port 8096.\n",
    "game/03-items.md": "# Items\nAudience: Luna\nKeywords: lamp, sword\nSummary: Every item in the game and where it is.\n\n- Lamp: in the living room.\n",
}


class Summaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.docs = os.path.join(self.tmp, "docs")
        for rel, text in FILES.items():
            path = os.path.join(self.docs, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
        self.patches = [
            mock.patch.object(config, "KNOWLEDGE_FOLDERS", [self.docs]),
            mock.patch.object(config, "KNOWLEDGE_SUMMARIES", True, create=True),
            mock.patch.object(knowledge, "db_path", return_value=os.path.join(self.tmp, "k.db")),
            mock.patch.object(knowledge, "_embedder", return_value=None),
        ]
        for p in self.patches:
            p.start()
        knowledge.index(force=True)
        self.asked = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def ask(self, prompt):
        self.asked.append(prompt)
        name = prompt.split(": ", 1)[1].split("\n", 1)[0]
        return f"Summary: covers {name}."

    def test_written_once_index_in_its_own_words(self):
        written = knowledge.write_summaries(self.ask)
        self.assertEqual(len(written), 5)
        self.assertEqual(len(self.asked), 3)        # the index file and the Summary: line needed no model call
        self.assertEqual(knowledge.summaries()[os.path.join(self.docs, "game", "03-items.md")],
                         "Every item in the game and where it is.")
        have = knowledge.summaries()
        index = os.path.join(self.docs, "game", "00-index.md")
        self.assertEqual(have[index], "A guide to the game: the map, the puzzles and how to play it.")
        self.assertEqual(have[os.path.join(self.docs, "network.md")], "covers network.md.")
        self.assertEqual(knowledge.summaries_due(), [])
        self.assertEqual(knowledge.write_summaries(self.ask), [])   # nothing new: nothing asked
        self.assertEqual(len(self.asked), 3)

    def test_spoiler_files_are_asked_not_to_give_it_away(self):
        knowledge.write_summaries(self.ask)
        spoiler = [p for p in self.asked if "02-solutions.md" in p][0]
        self.assertIn("don't give away the solutions", spoiler)
        self.assertNotIn("don't give away", [p for p in self.asked if "network.md" in p][0])

    def test_a_changed_file_is_rewritten_a_gone_one_dropped(self):
        knowledge.write_summaries(self.ask)
        net = os.path.join(self.docs, "network.md")
        with open(net, "a") as f:
            f.write("\nThe router is at the usual address.\n")
        os.remove(os.path.join(self.docs, "game", "01-map.md"))
        knowledge.index()
        self.assertEqual(knowledge.summaries_due(), [net])
        self.assertNotIn(os.path.join(self.docs, "game", "01-map.md"), knowledge.summaries())

    def test_a_failed_call_stops_the_pass(self):
        def down(prompt):
            raise RuntimeError("server down")
        self.assertIsNone(knowledge.write_summaries(down))

    def test_browse(self):
        knowledge.write_summaries(self.ask)
        top = knowledge.browse()
        self.assertIn("- game/ (4 files): A guide to the game", top)
        self.assertIn("- network.md: covers network.md.", top)
        one = knowledge.browse("game")
        self.assertIn("game (4 files", one)
        self.assertIn("- game/01-map.md: covers 01-map.md.", one)
        self.assertIn("No folder 'nope'", knowledge.browse("nope"))

    def test_nested_folders(self):
        os.makedirs(os.path.join(self.docs, "games"))
        shutil.move(os.path.join(self.docs, "game"), os.path.join(self.docs, "games", "zork"))
        knowledge.index()
        knowledge.write_summaries(self.ask)
        top = knowledge.browse()
        self.assertIn("- games/ (4 files): folders: zork", top)
        games = knowledge.browse("games")
        self.assertIn("- games/zork/ (4 files): A guide to the game", games)
        self.assertIn("- games/zork/01-map.md: covers 01-map.md.", knowledge.browse("games/zork"))
        # a game's guide is still found one folder down
        self.assertEqual(knowledge._guide_dirs("zork"), [os.path.join(self.docs, "games", "zork")])
        self.assertIn("Sanctuary", knowledge.about("zork", "cloud nine nest"))

    def test_off_writes_nothing(self):
        with mock.patch.object(config, "KNOWLEDGE_SUMMARIES", False):
            self.assertEqual(knowledge.summaries_due(), [])

    def test_lift_favours_the_file_whose_summary_fits(self):
        knowledge.write_summaries(self.ask)
        net = os.path.join(self.docs, "network.md")
        other = os.path.join(self.docs, "game", "01-map.md")
        with mock.patch.object(knowledge, "_summary_vecs", return_value={net: [1.0, 0.0], other: [0.0, 1.0]}):
            lift = knowledge._summary_lift([1.0, 0.0])
        self.assertAlmostEqual(lift[net], knowledge.SUMMARY_LIFT)
        self.assertEqual(lift[other], 0.0)


if __name__ == "__main__":
    unittest.main()
