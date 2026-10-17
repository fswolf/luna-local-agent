"""Game turns knowing where she is: her own older notes about the room
come back, and her guide (luna-knowledge/<game>/) is looked up by the
room's name. Temporary folders and databases; nothing of yours is read.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
import knowledge  # noqa: E402

GUIDE = """# A game: map
Audience: Luna

## Cloud Nine Nest
Rain on the window.
- Doors: east to the Sanctuary.

## Somewhere else
- Troll Room: south to the Cellar.
- Living Room (trophy case, lamp): east to the Kitchen.
- Forest (1): east to the path.
- Forest (2): west to the path.
- Forest Path: north to the clearing.
"""

SPOILERS = """# Solutions
Spoilers: yes

- Troll Room: kill the troll with the sword.
"""


class Guide(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "game"))
        for name, text in (("01-map.md", GUIDE), ("02-spoilers.md", SPOILERS)):
            with open(os.path.join(self.tmp, "game", name), "w") as f:
                f.write(text)
        self.patch = mock.patch.object(config, "KNOWLEDGE_FOLDERS", [self.tmp])
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def test_a_heading_brings_its_section(self):
        self.assertEqual(knowledge.about("game", "cloud nine nest"),
                         "Rain on the window.\n- Doors: east to the Sanctuary.")

    def test_a_list_item_by_its_name(self):
        self.assertEqual(knowledge.about("game", "Troll Room"), "Troll Room: south to the Cellar.")
        self.assertEqual(knowledge.about("game", "Living Room"),
                         "Living Room (trophy case, lamp): east to the Kitchen.")

    def test_rooms_sharing_a_name_all_come(self):
        found = knowledge.about("game", "Forest")
        self.assertIn("Forest (1)", found)
        self.assertIn("Forest (2)", found)
        self.assertNotIn("Forest Path", found)     # another room, not "Forest"

    def test_spoilers_never_come_unasked(self):
        self.assertNotIn("sword", knowledge.about("game", "Troll Room"))

    def test_nothing_known_or_nothing_asked(self):
        self.assertEqual(knowledge.about("game", "Nowhere"), "")
        self.assertEqual(knowledge.about("game", ""), "")
        self.assertEqual(knowledge.about("no-such-game", "Troll Room"), "")

    def test_only_inside_the_knowledge_folder(self):
        self.assertEqual(knowledge.about("../game", "Troll Room"), "")
        self.assertEqual(knowledge.about("/etc", "passwd"), "")

    def test_long_sections_are_cut(self):
        self.assertLessEqual(len(knowledge.about("game", "Cloud Nine Nest", limit=12)), 12)


class GuideSearch(unittest.TestCase):
    """Vibe City's guide: the best passages from its folder for what she's
    working on, by words here (no embedding server in the tests)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.city, other = os.path.join(self.tmp, "city"), os.path.join(self.tmp, "private")
        os.makedirs(self.city)
        os.makedirs(other)
        files = {os.path.join(self.city, "power.md"): "Power plants\nPower lines carry power to zones.",
                 os.path.join(self.city, "water.md"): "Water pumps\nPumps on the shore need power.",
                 os.path.join(self.city, "cheats.md"): "Spoilers: yes\nPower: type the money cheat.",
                 os.path.join(other, "notes.md"): "My power bill and my private notes."}
        for path, text in files.items():
            with open(path, "w") as f:
                f.write(text)
        items = [{"path": path, "heading": text.split("\n")[0], "text": text, "vec": None}
                 for path, text in files.items()]
        self.patches = [mock.patch.object(config, "KNOWLEDGE_FOLDERS", [self.tmp]),
                        mock.patch.object(knowledge, "_load", return_value=items),
                        mock.patch.object(knowledge, "_embedder", return_value=None),
                        mock.patch.object(knowledge, "enabled", return_value=True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def test_best_passages_from_that_folder_only(self):
        found = knowledge.guide("city", "add power lines to the new zones")
        self.assertIn("Power lines carry power", found)
        self.assertNotIn("private notes", found)       # another folder: never
        self.assertNotIn("money cheat", found)         # a spoiler file: never

    def test_no_folder_or_nothing_asked(self):
        self.assertEqual(knowledge.guide("nowhere", "power"), "")
        self.assertEqual(knowledge.guide("city", ""), "")
        self.assertEqual(knowledge.guide("../private", "power"), "")


class OlderNotesAboutHere(unittest.TestCase):
    def setUp(self):
        import projects
        self.projects = projects
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(projects, "DB_FILE", os.path.join(self.tmp, "projects.db"),
)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def test_an_old_note_about_this_room_comes_back(self):
        pid = self.projects.game_project("zork", "points")
        self.projects.log(pid, "found", "Troll Room: a troll blocks the east exit")
        for i in range(20):
            self.projects.log(pid, "found", f"Forest: tree number {i}")
        here = self.projects.game_block(pid, recent=5, here="Troll Room")
        away = self.projects.game_block(pid, recent=5, here="Kitchen")
        self.assertIn("earlier, about Troll Room:", here)
        self.assertIn("a troll blocks the east exit", here)
        self.assertNotIn("troll", away)
        self.assertIn("tree number 19", here)           # the recent ones still come


class ZorkRoom(unittest.TestCase):
    def test_the_room_comes_from_the_status_line(self):
        from plugins import zork
        screen = ("> north\nNorth of House   Score: 0   Moves: 3\n\nYou are facing the north side.\n"
                  "> east\nBehind House   Score: 0   Moves: 4\n\nA window is slightly ajar.")
        self.assertEqual(zork._room(screen), "Behind House")
        self.assertEqual(zork._room("(nothing yet - a new game)"), "")


if __name__ == "__main__":
    unittest.main()
