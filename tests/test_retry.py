"""↻, try again (llm/retry.py): her last reply thrown away and the same
message answered afresh, only where that's safe to do twice. Temp files.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests.offline import FAKE  # noqa: F401  (first: no real servers)

import config
import ui
from core import history, transcript
from llm import retry


class Retry(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        for p in (mock.patch.object(history, "HISTORY_FILE", os.path.join(self.dir, "h.json")),
                  mock.patch.object(history, "_data", {"summary": "", "messages": []}),
                  mock.patch.object(transcript, "TRANSCRIPT_DIR", self.dir),
                  mock.patch.object(transcript, "TRANSCRIPT_FILE", os.path.join(self.dir, "t.jsonl")),
                  mock.patch.object(config, "TRANSCRIPT_ENABLED", True, create=True),
                  mock.patch("core.assistant.busy", return_value=False)):
            p.start()
            self.addCleanup(p.stop)
        self.conv = list(ui.conversation)
        self.addCleanup(self.restore_ui)
        ui.conversation.clear()
        ui.view.streaming = None
        retry.forget()
        self.me = config.AGENT_NAME.lower()

    def restore_ui(self):
        ui.conversation[:] = self.conv

    def turn(self, said, answer, ok=True):
        """What llm/turns.py does at the end of one of your turns."""
        ui.conversation.append(("user", said))
        ui.conversation.append((self.me, answer))
        history.add_message("user", said)
        history.add_message("assistant", answer)
        transcript.add("user", said)
        transcript.add("assistant", answer)
        retry.note(said, answer, history.tail(2), ok=ok)

    def test_take_undoes_the_turn_everywhere(self):
        self.turn("hello luna", "Hi there~")
        self.turn("how's the NUC?", "It's fine, load is low.")
        self.assertEqual(retry.available(), 3)
        text, why = retry.take()
        self.assertEqual(text, "how's the NUC?")
        self.assertEqual([m["content"] for m in history._data["messages"]], ["hello luna", "Hi there~"])
        self.assertEqual(ui.conversation[-1], ("user", "how's the NUC?"))       # your message stays on screen
        self.assertEqual([e["text"] for e in transcript._load()], ["hello luna", "Hi there~"])
        self.assertIsNone(retry.available())                                    # until the new reply lands

    def test_not_after_a_tool_or_a_file_or_a_guest(self):
        self.turn("run the scan", "Done, two findings.", ok=False)
        self.assertIsNone(retry.available())
        self.assertIsNone(retry.take()[0])
        self.assertEqual(len(history._data["messages"]), 2)                     # nothing changed

    def test_not_when_something_came_after(self):
        self.turn("hello", "Hi~")
        history.add_message("user", "(started the app)")                        # a greeting since
        history.add_message("assistant", "Welcome back!")
        self.assertIsNone(retry.available())
        self.assertIsNone(retry.take()[0])
        self.assertEqual(len(history._data["messages"]), 4)

    def test_a_system_line_after_it_is_fine_anything_else_isnt(self):
        self.turn("hello", "Hi~")
        ui.conversation.append(("system", "Kept as a good example."))          # /good's answer
        self.assertEqual(retry.available(), 1)
        text, _undo = retry.take()
        self.assertEqual(ui.conversation, [("user", "hello"), ("system", "Kept as a good example.")])
        self.turn("hey", "Hey~")
        ui.conversation.append(("chat:viewer", "lol"))                          # stream chat
        self.assertIsNone(retry.available())


    def test_a_failed_retry_puts_the_first_reply_back(self):
        self.turn("hello", "Hi~")
        text, undo = retry.take()
        retry.put_back(undo, ConnectionError("server down"))
        self.assertEqual([m["content"] for m in history._data["messages"]], ["hello", "Hi~"])
        self.assertEqual([e["text"] for e in transcript._load()], ["hello", "Hi~"])
        self.assertEqual(ui.conversation[-2:], [(self.me, "Hi~"), ("system", mock.ANY)])
        self.assertIn("first reply is back", ui.conversation[-1][1])

    def test_a_failed_retry_through_respond(self):
        from core import assistant
        self.turn("hello", "Hi~")
        with mock.patch.object(assistant, "_respond", side_effect=ConnectionError("down")):
            self.assertIsNone(assistant.respond(None, "model", retry=True))
        self.assertEqual([m["content"] for m in history._data["messages"]], ["hello", "Hi~"])

    def test_not_while_she_has_walked_away(self):
        self.turn("hello", "Hi~")
        with mock.patch("mind.mood.away", return_value=True):
            self.assertIsNone(retry.available())

    def test_the_transcript_marker_folds_for_every_reader(self):
        self.turn("a", "b")
        self.turn("c", "d")
        retry.take()
        transcript.add("user", "c")
        transcript.add("assistant", "e")
        with open(transcript.TRANSCRIPT_FILE) as f:
            self.assertIn('"withdrawn"', f.read())                             # appended, never edited
        self.assertEqual([e["text"] for e in transcript._load()], ["a", "b", "c", "e"])
        from mind import reflect
        with mock.patch.dict(reflect._tcache, {"key": None, "size": 0, "entries": [], "file": None}):
            self.assertEqual([e["text"] for e in reflect._read_transcript()], ["a", "b", "c", "e"])


class Respond(unittest.TestCase):
    """core/assistant.py: a retry runs the same words, and her mood doesn't
    hear them a second time."""

    def test_retry_runs_the_same_words_once_quietly(self):
        from core import assistant
        with mock.patch.object(retry, "take", return_value=("how's the NUC?", None)), \
             mock.patch.object(assistant, "_respond", return_value="New reply") as run, \
             mock.patch.object(assistant, "_drift_mood") as drift, \
             mock.patch.object(assistant, "_plugins_hear") as hear:
            self.assertEqual(assistant.respond(None, "model", retry=True), "New reply")
        self.assertEqual(run.call_args.args[0], "how's the NUC?")
        self.assertTrue(run.call_args.kwargs["retry"])
        drift.assert_not_called()
        hear.assert_not_called()

    def test_retry_that_cant_says_why(self):
        from core import assistant
        with mock.patch.object(retry, "take", return_value=(None, "her last reply used a tool")), \
             mock.patch.object(assistant, "_respond") as run, \
             mock.patch.object(ui, "add_message") as said:
            self.assertIsNone(assistant.respond(None, "model", retry=True))
        run.assert_not_called()
        self.assertIn("used a tool", said.call_args.args[1])

    def test_no_second_mood_reading(self):
        from core import assistant
        with mock.patch.object(assistant, "ask", return_value="New reply"), \
             mock.patch.object(assistant, "_note_mood") as mood, \
             mock.patch.object(assistant, "_heavy_from"), \
             mock.patch.object(assistant.speech, "Player"), \
             mock.patch.object(ui, "begin_message"), mock.patch.object(ui, "end_message"), \
             mock.patch.object(ui, "replace_message"), mock.patch.object(ui, "set_status"):
            stop = mock.Mock()
            assistant._respond("hi", "model", "typed", stop, retry=True)
            mood.assert_not_called()
            assistant._respond("hi", "model", "typed", stop)
            mood.assert_called_once()


class Pairing(unittest.TestCase):
    """training/dataset.py: thumbs down, ↻, thumbs up on the new one = one
    example, the bad reply and the good one in its place."""

    def setUp(self):
        from training import dataset
        self.d = dataset
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        for p in (mock.patch.object(dataset, "FOLDER", self.dir),
                  mock.patch.object(dataset, "FILE", os.path.join(self.dir, "examples.jsonl")),
                  mock.patch.dict(dataset._recent, clear=True), mock.patch.dict(dataset._rated, clear=True),
                  mock.patch.dict(dataset._last, clear=True), mock.patch.dict(dataset._replacing, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def note(self, reply, user="how's the NUC?"):
        with mock.patch.object(self.d, "_ui_ref", return_value=(0, reply)):
            self.d.note_turn("system", [], {"role": "user", "content": f"(note)\n{user}"}, reply)

    def test_down_retry_up_is_one_fix(self):
        self.note("It is on fire.")
        self.d.rate(0, "It is on fire.", False)
        self.d.retrying(0, "It is on fire.", "how's the NUC?")
        self.note("It's fine, load is low.")
        ex = self.d.rate(0, "It's fine, load is low.", True)
        self.assertTrue(ex.get("paired"))
        rows = self.d.examples()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["source"], rows[0]["reply"], rows[0]["original"], rows[0]["approved"]),
                         ("fix", "It's fine, load is low.", "It is on fire.", True))

    def test_up_without_a_down_is_just_good(self):
        self.note("It is on fire.")
        self.d.retrying(0, "It is on fire.", "how's the NUC?")
        self.note("It's fine.")
        self.d.rate(0, "It's fine.", True)
        self.assertEqual([r["source"] for r in self.d.examples()], ["good"])

    def test_a_different_message_isnt_paired(self):
        self.note("It is on fire.")
        self.d.rate(0, "It is on fire.", False)
        self.d.retrying(0, "It is on fire.", "how's the NUC?")
        self.note("Hi!", user="hello")                     # the retry failed; the next turn is another message
        self.d.rate(0, "Hi!", True)
        self.assertEqual(sorted(r["source"] for r in self.d.examples()), ["bad", "good"])


class Unrate(unittest.TestCase):
    """A lit thumb clicked again (or /unrate) takes the rating back."""
    setUp, note = Pairing.setUp, Pairing.note

    def test_up_taken_back(self):
        self.note("It's fine.")
        self.d.rate(0, "It's fine.", True)
        self.assertEqual(self.d.unrate(0, "It's fine."), "up")
        self.assertEqual(self.d.examples(), [])
        self.assertEqual(self.d.rateable(0, [["luna", "It's fine."]]), {0: ""})
        self.d.rate(0, "It's fine.", False)                # and it can be rated again
        self.assertEqual([r["source"] for r in self.d.examples()], ["bad"])

    def test_down_and_fix_taken_back(self):
        self.note("It is on fire.")
        self.d.rate(0, "It is on fire.", False, "It's fine.")
        self.assertEqual(self.d.unrate(0, "It is on fire."), "fix")
        self.assertEqual(self.d.examples(), [])

    def test_the_paired_up_taken_back_leaves_the_down(self):
        self.note("It is on fire.")
        self.d.rate(0, "It is on fire.", False)
        self.d.retrying(0, "It is on fire.", "how's the NUC?")
        self.note("It's fine, load is low.")
        self.d.rate(0, "It's fine, load is low.", True)
        self.assertEqual(self.d.unrate(0, "It's fine, load is low."), "up")
        rows = self.d.examples()
        self.assertEqual([(r["source"], r["reply"], r["original"], r["approved"], r["rated"]) for r in rows],
                         [("bad", "It is on fire.", None, False, "down")])
        got = self.d.rateable(0, [["luna", "It is on fire."], ["luna", "It's fine, load is low."]])
        self.assertEqual(got, {0: "down", 1: ""})

    def test_the_paired_down_taken_back_clears_both(self):
        self.note("It is on fire.")
        self.d.rate(0, "It is on fire.", False)
        self.d.retrying(0, "It is on fire.", "how's the NUC?")
        self.note("It's fine, load is low.")
        self.d.rate(0, "It's fine, load is low.", True)
        self.d.unrate(0, "It is on fire.")
        self.assertEqual(self.d.examples(), [])
        got = self.d.rateable(0, [["luna", "It is on fire."], ["luna", "It's fine, load is low."]])
        self.assertEqual(got, {0: "", 1: ""})

    def test_nothing_to_take_back(self):
        self.note("Hi!")
        with self.assertRaises(ValueError):
            self.d.unrate(0, "Hi!")

    def test_console_fix_then_good_keeps_the_fix_lit(self):
        self.note("Hi!")
        with mock.patch.object(self.d, "_ui_ref", return_value=(0, "Hi!")):
            self.d.keep("fix", reply="Hey you~")
            with self.assertRaises(ValueError):
                self.d.keep("good")                         # already kept: nothing changes
            self.assertEqual(self.d.rateable(0, [["luna", "Hi!"]]), {0: "fix"})
            self.assertEqual(self.d.unrate(), "fix")

    def test_off_screen_says_what_it_was(self):
        self.note("Hi!")
        with mock.patch.object(self.d, "_ui_ref", return_value=(0, "Hi!")):
            self.d.keep("fix", reply="Hey you~")
        self.d._recent.clear()                              # scrolled out of what she keeps track of
        with mock.patch.object(self.d, "_ui_ref", return_value=None):
            self.assertEqual(self.d.unrate(), "fix")
        self.assertEqual(self.d.examples(), [])

    def test_console_good_then_unrate(self):
        self.note("Hi!")
        with mock.patch.object(self.d, "_ui_ref", return_value=(0, "Hi!")):
            self.d.keep("good")
            self.assertEqual(self.d.rateable(0, [["luna", "Hi!"]]), {0: "up"})   # the page shows /good too
            self.assertEqual(self.d.unrate(), "up")
        self.assertEqual(self.d.examples(), [])


if __name__ == "__main__":
    unittest.main()
