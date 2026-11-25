"""Every game's saves in agent/games/ (plugins/_game.py tidy): the folders
from before it move in once, at startup, and nothing is ever overwritten.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import shutil
import tempfile
import unittest

from tests.offline import FAKE  # noqa: F401  (first: no real servers)

from plugins import _game, _zgame, adventure, chessgame


def touch(*parts):
    os.makedirs(os.path.dirname(os.path.join(*parts)), exist_ok=True)
    with open(os.path.join(*parts), "w") as f:
        f.write(parts[-1])


class Tidy(unittest.TestCase):
    def setUp(self):
        self.agent = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.agent)

    def has(self, *parts):
        return os.path.exists(os.path.join(self.agent, *parts))

    def test_the_old_folders_move_in(self):
        touch(self.agent, "chess", "games", "2026-10-23.pgn")
        touch(self.agent, "zork", "autosave.qzl")
        touch(self.agent, "adventures", "planetfall", "autosave.qzl")
        os.makedirs(os.path.join(self.agent, "starcross"))          # the old /starcross left an empty one
        touch(self.agent, "people", "shannon.json")                 # hers, never a game's
        touch(self.agent, "knowledge", "zork", "00-index.md")
        moved = _game.tidy(self.agent)
        self.assertEqual(len(moved), 3)
        for want in (("games", "chess", "games", "2026-10-23.pgn"), ("games", "zork", "autosave.qzl"),
                     ("games", "planetfall", "autosave.qzl"), ("people", "shannon.json"),
                     ("knowledge", "zork", "00-index.md")):
            self.assertTrue(self.has(*want), want)
        for gone in (("chess",), ("zork",), ("starcross",), ("adventures",)):
            self.assertFalse(self.has(*gone), gone)
        self.assertEqual(_game.tidy(self.agent), [])                 # once

    def test_saves_already_there_are_never_overwritten(self):
        touch(self.agent, "games", "zork", "autosave.qzl")
        touch(self.agent, "zork", "slot1.qzl")
        touch(self.agent, "adventures", "zork", "old.qzl")
        self.assertEqual(_game.tidy(self.agent), [])
        self.assertTrue(self.has("zork", "slot1.qzl") and self.has("adventures", "zork", "old.qzl"))
        self.assertFalse(self.has("games", "zork", "slot1.qzl"))

    def test_the_older_of_two_old_folders_wins_and_the_other_stays(self):
        touch(self.agent, "zork", "slot1.qzl")
        touch(self.agent, "adventures", "zork", "old.qzl")
        _game.tidy(self.agent)
        self.assertTrue(self.has("games", "zork", "slot1.qzl"))
        self.assertTrue(self.has("adventures", "zork", "old.qzl"))     # left, not merged into it

    def test_a_game_named_like_her_own_folders_never_takes_them(self):
        touch(self.agent, "people", "shannon.json")
        touch(self.agent, "adventures", "people", "autosave.qzl")      # a library game called "people"
        _game.tidy(self.agent)
        self.assertTrue(self.has("people", "shannon.json"))
        self.assertTrue(self.has("games", "people", "autosave.qzl"))
        self.assertFalse(self.has("games", "people", "shannon.json"))

    def test_nothing_to_do(self):
        self.assertEqual(_game.tidy(self.agent), [])
        self.assertEqual(os.listdir(self.agent), [])


class Paths(unittest.TestCase):
    def test_every_game_saves_in_agent_games(self):
        here = _zgame.HERE
        self.assertEqual(chessgame.SAVES, os.path.join(here, "agent", "games", "chess"))
        self.assertEqual(adventure.SAVES, os.path.join(here, "agent", "games"))
        z = _zgame.ZGame("t_folder", "T", story=lambda: "", goal="", intro="", examples="", feel="",
                         register=False)
        self.assertEqual(z.saves, os.path.join(here, "agent", "games", "t_folder"))


if __name__ == "__main__":
    unittest.main()
