"""Her game notes checked against the game: a note that puts a door or
stairs where the game's Ways out line shows none is turned back when she
writes it, and an old one is taken out of her turn (plugins/_notecheck.py).
From her real Pokemon run: 27 turns pressing A at x 1, y 3 because of her
own note. Temporary databases; nothing of yours is read.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from plugins import _notecheck as nc  # noqa: E402

BEDROOM = ("[POKEMON RED]\n"
           "Where: your house (upstairs), x 1, y 3, facing left (the map is 8 steps wide, 8 tall)\n"
           "Ways out (stand on stairs; walk out through a door): to your house (downstairs) at x 7, y 1 (6 right, 2 up)\n"
           "Player: ASH  ·  money ¥3000  ·  badges 0/8\n")
TOWN = ("Where: Pallet Town, x 5, y 6, facing down\n"
        "Ways out (stand on stairs; walk out through a door): to your house (downstairs) at x 5, y 5 (1 up); "
        "to Professor Oak's lab at x 12, y 11 (7 right, 5 down)\n")
PLACES = ["Pallet Town", "your house (downstairs)", "your house (upstairs)", "Professor Oak's lab"]

HER_NOTE = "Professor Oak's lab door is at bottom left of upstairs room - x=1, y=3"
HER_PLAN = "Move to x=1, y=3 and enter Oak's lab to get my first Pokémon"


class Reading(unittest.TestCase):
    def test_where_and_exits(self):
        self.assertEqual(nc.where(BEDROOM), ("your house (upstairs)", 1, 3))
        self.assertEqual(nc.exits(BEDROOM), [("your house (downstairs)", 7, 1)])
        self.assertEqual(len(nc.exits(TOWN)), 2)
        self.assertIsNone(nc.exits("Where: Pallet Town, x 1, y 1"))      # no line: nothing known, nothing checked

    def test_stamp_once(self):
        once = nc.stamp("stairs at x 7, y 1", BEDROOM)
        self.assertEqual(once, "[your house (upstairs)] stairs at x 7, y 1")
        self.assertEqual(nc.stamp(once, TOWN), once)
        self.assertEqual(nc.stamped(once), "your house (upstairs)")


class Checking(unittest.TestCase):
    def wrong(self, text, screen=BEDROOM, now=False):
        return nc.problem(text, screen, now=now, places=PLACES)

    def test_her_real_notes_are_wrong(self):
        self.assertIn("ways out are: to your house (downstairs) at x 7, y 1", self.wrong(HER_NOTE))
        self.assertTrue(self.wrong(HER_PLAN, now=True))
        self.assertTrue(self.wrong("the door is at x1, y3", now=True))

    def test_right_or_unrelated_notes_pass(self):
        self.assertFalse(self.wrong("stairs at x 7, y 1", now=True))
        self.assertFalse(self.wrong("the stairs are at x=7 y=2", now=True))           # a step off
        self.assertFalse(self.wrong("pressed A at x 1, y 3 and nothing happened", now=True))   # no door named
        self.assertFalse(self.wrong("the stairs are top right", now=True))             # no spot
        self.assertFalse(self.wrong("Oak's lab door is at x 12, y 11 in Pallet Town", now=True))   # another map

    def test_old_notes_only_about_this_map(self):
        self.assertFalse(self.wrong("door at x 1, y 3"))                               # unknown map, old: left alone
        city = "Where: Celadon City, x 1, y 1\nWays out: " + "; ".join(f"to map {i} at x {i * 3}, y 9" for i in range(8))
        self.assertFalse(self.wrong("door at x 40, y 2", screen=city, now=True))       # the list may be cut short
        self.assertTrue(self.wrong("[your house (upstairs)] door at x 1, y 3"))
        self.assertFalse(self.wrong("[Pallet Town] door at x 1, y 3"))
        self.assertTrue(self.wrong(HER_NOTE, screen=BEDROOM))
        self.assertFalse(self.wrong("[your house (upstairs)] door at x 1, y 3", screen=TOWN))


class InHerTurn(unittest.TestCase):
    def setUp(self):
        from mind import projects
        self.projects = projects
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(projects, "DB_FILE", os.path.join(self.tmp, "projects.db"))
        self.patch.start()
        self.pid = projects.game_project("pokemon", "8 badges")
        self.check = {"check": lambda t, now: nc.problem(t, BEDROOM, now=now, places=PLACES),
                      "stamp": lambda t: nc.stamp(t, BEDROOM)}

    def tearDown(self):
        self.projects.set_checker(self.pid, None)
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def test_wrong_notes_leave_her_turn_and_the_plan_clears(self):
        p = self.projects
        p.log(self.pid, "found", "Title screen: A advances")
        p.log(self.pid, "found", HER_NOTE)
        p.set_next(self.pid, HER_PLAN)
        block = p.game_block(self.pid, here="your house (upstairs)", check=lambda t, plan: self.check["check"](t, plan))
        self.assertNotIn("x=1, y=3", block)
        self.assertIn("A advances", block)
        self.assertIn("2 of your notes", block)
        self.assertEqual(p.get(self.pid)["next"], "")
        self.assertEqual([e["kind"] for e in p.entries(self.pid)], ["found", "wrong"])     # kept, marked
        again = p.game_block(self.pid, here="your house (upstairs)", check=lambda t, plan: "")
        self.assertNotIn("x=1, y=3", again)                                           # gone for good

    def test_game_note_turns_a_wrong_one_back_and_stamps_the_rest(self):
        import tools.introspect as ti
        from core import turnctx
        self.projects.set_checker(self.pid, self.check)
        with mock.patch.object(turnctx, "current", lambda: mock.Mock(project_id=self.pid)):
            said = ti._game_note(found=HER_NOTE, decided="go down the stairs at x 7, y 1", next=HER_PLAN)
        self.assertIn("Noted (decided)", said)
        self.assertIn("Not saved", said)
        self.assertIn("x 7, y 1", said)
        self.assertIn("name that place", said)
        self.assertEqual([e["text"] for e in self.projects.entries(self.pid)],
                         ["[your house (upstairs)] go down the stairs at x 7, y 1"])
        self.assertEqual(self.projects.get(self.pid)["next"], "")

    def test_your_commands_fix_a_wrong_note(self):
        import commands
        import ui
        p, said = self.projects, []
        p.log(self.pid, "found", "Upstairs in Professor Oak's house is his lab")
        p.set_next(self.pid, "go back upstairs to the lab")
        note = p.entries(self.pid)[0]["id"]
        with mock.patch.object(ui, "add_message", side_effect=lambda who, text: said.append(text)), \
                mock.patch.object(p, "enabled", lambda: True, create=True):
            commands.handle(f"/projects show {self.pid}")
            self.assertIn(f"[{note}]", said[-1])
            commands.handle(f"/projects wrong {note}")
            commands.handle(f"/projects unplan {self.pid}")
            commands.handle("/projects wrong 999")
        self.assertIn("No note 999", said[-1])
        self.assertEqual(p.entries(self.pid)[0]["kind"], "wrong")
        self.assertEqual(p.get(self.pid)["next"], "")
        self.assertNotIn("Oak's house", p.game_block(self.pid))

    def test_without_a_checker_nothing_changes(self):
        import tools.introspect as ti
        from core import turnctx
        with mock.patch.object(turnctx, "current", lambda: mock.Mock(project_id=self.pid)):
            self.assertEqual(ti._game_note(found=HER_NOTE), "Noted (found).")
            self.assertEqual(ti._game_note(found=12), "Noted (found).")              # not a string: still a note


class GameBoy(unittest.TestCase):
    def test_the_checker_follows_her_last_move(self):
        from plugins import gameboy
        with mock.patch.dict(gameboy._state, screen=BEDROOM), mock.patch.object(gameboy, "_reader", lambda: None):
            ck = gameboy._note_checker()
            self.assertTrue(ck["check"](HER_NOTE, True))
            gameboy._state["screen"] = TOWN
            self.assertFalse(ck["check"]("lab door at x 12, y 11", True))
            self.assertEqual(ck["stamp"]("x"), "[Pallet Town] x")


if __name__ == "__main__":
    unittest.main()
