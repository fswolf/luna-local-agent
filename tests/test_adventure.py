"""The text adventure library (/adventure): a game is a folder in games/
with one story file; its name is the folder's; about.json tells her about
it; Zork is the same game here as under /zork; she plays one at a time.
No dfrotz and no model: a temporary games folder.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from plugins import _game, _zgame, adventure  # noqa: E402


class Library(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.games = os.path.join(self.tmp, "games")
        for folder, files in {"Planet-Fall": ["planetfall.z3"], "zork": ["zork1.z3"],
                              "chess": ["board.py"], "two": ["a.z3", "b.z5"]}.items():
            os.makedirs(os.path.join(self.games, folder))
            for f in files:
                open(os.path.join(self.games, folder, f), "wb").close()
        with open(os.path.join(self.games, "Planet-Fall", "about.json"), "w") as f:
            json.dump({"title": "Planetfall", "start_at": "Deck Nine"}, f)
        self.patches = [mock.patch.object(adventure, "GAMES", self.games),
                        mock.patch.object(_zgame, "HERE", self.tmp),
                        mock.patch.object(adventure, "SAVES", os.path.join(self.tmp, "agent", "games")),
                        mock.patch.dict(_zgame.REGISTRY, {}, clear=True)]   # its own games, none from other tests
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp)

    def test_a_folder_with_one_story_file_is_a_game(self):
        # code folders and a folder with two story files aren't
        self.assertEqual(adventure.library(), [("planet_fall", "Planet-Fall"), ("zork", "zork")])

    def test_about_json_names_it_and_its_saves_are_in_adventures(self):
        g = adventure.game("planet_fall")
        self.assertEqual((g.title, g.start_at, g.cmd, g.play_tool), ("Planetfall", "Deck Nine", "adventure", "play_adventure"))
        self.assertEqual(g.saves, os.path.join(self.tmp, "agent", "games", "planet_fall"))
        self.assertTrue(g.story().endswith("planetfall.z3"))
        self.assertIn("planet_fall_command", g.prompt("- n", "s", "", "p"))

    def test_the_old_zork_saves_are_the_librarys_after_the_tidy(self):
        old = os.path.join(self.tmp, "agent", "zork")
        os.makedirs(old)
        open(os.path.join(old, "autosave.qzl"), "wb").close()
        _game.tidy(os.path.join(self.tmp, "agent"))
        self.assertTrue(os.path.isfile(os.path.join(adventure.game("zork").saves, "autosave.qzl")))

    def test_picked_by_number_name_or_title(self):
        self.assertEqual(adventure._match("1"), "planet_fall")
        self.assertEqual(adventure._match("planetfall"), "planet_fall")     # the title
        self.assertEqual(adventure._match("Zork"), "zork")
        self.assertEqual(adventure._match("trinity"), "")

    def test_one_game_at_a_time(self):
        g, z = adventure.game("planet_fall"), adventure.game("zork")
        with mock.patch.object(z, "connected", True), mock.patch.object(g, "connected", True), \
                mock.patch.dict(z.state, playing=True), mock.patch.object(_zgame._game, "session_over"):
            g.set_playing(True)
            self.assertFalse(z.state["playing"])
            self.assertTrue(g.state["playing"])
        g.state["playing"] = False

    def test_two_folders_with_one_name_are_one_game(self):
        os.makedirs(os.path.join(self.games, "zork-2"))
        os.makedirs(os.path.join(self.games, "zork_2"))
        for f in ("zork-2/a.z3", "zork_2/b.z3"):
            open(os.path.join(self.games, f), "wb").close()
        self.assertEqual([n for n, _ in adventure.library()].count("zork_2"), 1)

    def test_no_switching_games_from_inside_a_turn(self):
        g, z = adventure.game("planet_fall"), adventure.game("zork")
        with mock.patch.dict(g.turn, active=True), mock.patch.object(adventure, "_pick") as pick:
            said = adventure._play("zork")
        pick.assert_not_called()
        self.assertIn("middle of a turn of Planetfall", said)
        self.assertIsNot(g, z)

    def test_a_game_that_wont_load_leaves_the_library_on(self):
        g = adventure.game("planet_fall")
        with mock.patch.object(adventure, "_picked", return_value="planet_fall"), \
                mock.patch.object(g, "start", return_value=(False, "needs dfrotz")), \
                mock.patch.dict(adventure._on, running=False):
            ok, said = adventure.start(None)
            self.assertTrue(ok and adventure.running())
        self.assertIn("didn't load (needs dfrotz)", said)

    def test_stop_playing_is_two_words(self):
        g = adventure.game("planet_fall")
        with mock.patch.object(adventure, "_picked", return_value="planet_fall"), \
                mock.patch.object(g, "command", return_value="paused") as cmd:
            adventure.command("stop playing")
        cmd.assert_called_once_with("stop playing")


class CarryOver(unittest.TestCase):
    """An update keeps the old /zork or /starcross settings: they become the library's."""

    def run_with(self, plugins):
        saved = {}
        with mock.patch.dict(adventure.config.settings, {"plugins": plugins}), \
                mock.patch.object(adventure.config, "save_any", side_effect=lambda k, v: saved.update({k: v})):
            return adventure.carry_over(), saved

    def test_the_old_zork_block_becomes_the_librarys(self):
        got, saved = self.run_with({"zork": {"enabled": True, "step_seconds": 10, "speak": False, "port": 1}})
        self.assertEqual(got, "zork")
        self.assertEqual(saved, {"plugins.adventure.enabled": True, "plugins.adventure.step_seconds": 10,
                                 "plugins.adventure.speak": False, "plugins.adventure.game": "zork"})

    def test_starcross_when_theres_no_zork(self):
        self.assertEqual(self.run_with({"starcross": {"enabled": True}})[0], "starcross")

    def test_once_and_never_over_a_library_block(self):
        self.assertEqual(self.run_with({"adventure": {}, "zork": {"enabled": True}}), ("", {}))
        self.assertEqual(self.run_with({}), ("", {}))


if __name__ == "__main__":
    unittest.main()
