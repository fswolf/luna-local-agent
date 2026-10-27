"""Her game memories: a feeling line per game, the write-up's closing
lines, the mood a session leaves her in, and the notebook in the memory
manager."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.offline  # noqa: F401,E402

from mind import notebook  # noqa: E402
from mind import reflect  # noqa: E402


class Notebook(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(notebook, "DB_FILE", os.path.join(self.dir.name, "nb.db"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.dir.cleanup()

    def played(self, game, title, summary):
        notebook.play_turn(game, title, "went north")
        notebook.play_end(game)
        session = notebook.play_to_write(20)[0]
        ep = notebook.add_episode(session["started"], session["ended"], 1, summary)
        notebook.play_written(session["id"], ep)
        return ep


class Feelings(Notebook):
    def test_set_forget(self):
        notebook.set_game_feeling("zork", "Zork I", "  I love   the  grues. ")
        self.assertEqual(notebook.game_feelings()["zork"]["feeling"], "I love the grues.")
        self.assertTrue(notebook.forget_game_feeling("zork"))
        self.assertFalse(notebook.forget_game_feeling("zork"))
        self.assertEqual(notebook.game_feelings(), {})

    def test_which_games_still_need_one(self):
        ep = self.played("zork", "Zork I", "I opened the mailbox.")
        self.assertEqual(notebook.play_episodes(), {ep: "Zork I"})
        self.assertEqual(notebook.played_without_feeling(), [("zork", "Zork I", "I opened the mailbox.")])
        notebook.set_game_feeling("zork", "Zork I", "Fond of it.")
        self.assertEqual(notebook.played_without_feeling(), [])

    def test_forgotten_stays_forgotten_until_she_plays_again(self):
        self.played("zork", "Zork I", "I opened the mailbox.")
        notebook.set_game_feeling("zork", "Zork I", "Fond.")
        notebook.forget_game_feeling("zork")
        self.assertEqual(notebook.played_without_feeling(), [])     # the backfill won't redo it
        notebook.set_game_feeling("zork", "Zork I", "New run, new feeling.")
        notebook.forget_game_feeling("zork")
        self.assertEqual(notebook.get("game_feelings_forgotten"), ["zork"])

    def test_backfill_takes_a_bare_sentence(self):
        self.played("zork", "Zork I", "I opened the mailbox.")
        with mock.patch.object(reflect, "_ask", return_value="I keep thinking about that white house. It was odd."), \
             mock.patch.object(reflect, "_model", return_value="m"), mock.patch.object(reflect, "_yield"):
            reflect.feel_about_games("m")
        self.assertEqual(notebook.game_feelings()["zork"]["feeling"], "I keep thinking about that white house.")

    def test_backfill_from_her_notes(self):
        self.played("realiti", "REALITI Relax", "I curled up in the nest.")
        with mock.patch.object(reflect, "_ask", return_value="Feeling: It felt like a hug."), \
             mock.patch.object(reflect, "_model", return_value="m"), mock.patch.object(reflect, "_yield"):
            reflect.feel_about_games("m")
        self.assertEqual(notebook.game_feelings()["realiti"]["feeling"], "It felt like a hug.")


class WriteUp(Notebook):
    def test_parsing_the_closing_lines(self):
        notes, feeling, verdict = reflect._play_notes(
            "I got into the house.\nThe grue got me.\n\n**Feeling:** Annoyed, but I want a rematch.\nVerdict: Mixed.")
        self.assertEqual(notes, "I got into the house. The grue got me.")
        self.assertEqual(feeling, "Annoyed, but I want a rematch.")
        self.assertEqual(verdict, "mixed")
        self.assertEqual(reflect._play_notes("Just notes."), ("Just notes.", "", ""))

    def test_a_session_becomes_an_episode_a_feeling_and_a_mood(self):
        notebook.play_turn("zork", "Zork I", "took the lamp")
        notebook.play_end("zork")
        reply = "I found the lamp and the trophy case.\nFeeling: Proud of that run.\nVerdict: enjoyed"
        with mock.patch.object(reflect, "_ask", return_value=reply), \
             mock.patch.object(reflect, "_model", return_value="m"), mock.patch.object(reflect, "_yield"), \
             mock.patch("mind.mood.note_play") as nudge:
            reflect.summarize_play("m")
        ep = notebook.episodes(1)[0]
        self.assertEqual(ep["summary"], "I found the lamp and the trophy case. Proud of that run.")
        self.assertEqual(notebook.game_feelings()["zork"]["feeling"], "Proud of that run.")
        nudge.assert_called_once_with("enjoyed", "Zork I")

    def test_an_old_session_leaves_the_mood_alone(self):
        old = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        with mock.patch("mind.mood.note_play") as nudge:
            reflect._play_mood({"ended": old, "title": "Zork I"}, "frustrated")
            reflect._play_mood({"ended": datetime.now().isoformat(), "title": "Zork I"}, "mixed")
        nudge.assert_not_called()


class Mood(unittest.TestCase):
    def test_how_a_session_moves_her(self):
        from mind import mood

        with mock.patch("mind.mood.drift._nudge") as nudge:
            mood.note_play("enjoyed", "Zork I")
            mood.note_play("mixed", "Zork I")
            mood.note_play("frustrated", "Zork I")
        (up, down) = [c.kwargs for c in nudge.call_args_list]
        self.assertGreater(up["energy"], 0)
        self.assertLess(down["energy"], 0)


class Prompt(Notebook):
    def test_she_always_knows_how_she_feels(self):
        from llm import prompts

        notebook.set_game_feeling("zork", "Zork I", "I want my rematch with the grue.")
        block = prompts.build_self_prompt("hello")
        self.assertIn("Zork I: I want my rematch with the grue.", block)


class Manager(Notebook):
    def setUp(self):
        super().setUp()
        import importlib.util

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory-manager", "manager.py")
        spec = importlib.util.spec_from_file_location("manager", path)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_state_and_edits(self):
        ep = self.played("zork", "Zork I", "I opened the mailbox.")
        notebook.set_game_feeling("zork", "Zork I", "Fond.")
        lid = notebook.add_lesson("Check the map before going underground.")
        nb = self.m.notebook_state()
        self.assertEqual(nb["feelings"][0]["feeling"], "Fond.")
        self.assertEqual(nb["episodes"][0]["game"], "Zork I")
        self.assertEqual(nb["lessons"][0]["id"], lid)
        self.m.apply("nb_feeling", {"game": "zork", "feeling": "Obsessed."})
        self.assertEqual(notebook.game_feelings()["zork"]["feeling"], "Obsessed.")
        self.m.apply("nb_lesson_retire", {"id": lid})
        self.assertEqual(self.m.notebook_state()["retired_lessons"][0]["id"], lid)
        self.m.apply("nb_lesson_restore", {"id": lid})
        self.m.apply("nb_episode_forget", {"id": ep})
        self.m.apply("nb_feeling_forget", {"game": "zork"})
        nb = self.m.notebook_state()
        self.assertEqual((nb["episodes"], nb["feelings"], len(nb["lessons"])), ([], [], 1))
        with self.assertRaises(ValueError):
            self.m.apply("nb_feeling", {"game": "zork", "feeling": " "})


if __name__ == "__main__":
    unittest.main()
