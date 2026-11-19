"""Sticky notes for her reminders (life/stickynotes.py)."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from life import reminders, stickynotes  # noqa: E402


class Notes(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.p = [mock.patch.object(stickynotes, "_emit", lambda k, **d: self.events.append((k, d))),
                  mock.patch.object(config, "PORTRAIT_STICKY_NOTES", True, create=True)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_write_and_show(self):
        stickynotes.wrote("take the laundry out")
        stickynotes.show(["take the laundry out", "call mom"])
        self.assertEqual(self.events, [("note", {"mode": "write", "text": "take the laundry out"}),
                                       ("note", {"mode": "show", "text": "take the laundry out (+1)"})])

    def test_long_text_cut(self):
        stickynotes.wrote("word " * 40)
        text = self.events[0][1]["text"]
        self.assertLessEqual(len(text), stickynotes.MAX_WORDS + 2)
        self.assertTrue(text.endswith("..."))

    def test_off(self):
        with mock.patch.object(config, "PORTRAIT_STICKY_NOTES", False, create=True):
            stickynotes.wrote("x")
            stickynotes.show(["x"])
        self.assertEqual(self.events, [])

    def test_reminders_add_writes_alarms_dont(self):
        with mock.patch.object(reminders, "save"), mock.patch.object(reminders, "_reminders", []):
            reminders.add("feed the cat", datetime.now() + timedelta(hours=1), None)
            reminders.add("wake up", datetime.now() + timedelta(hours=8), None, kind="alarm")
        self.assertEqual(self.events, [("note", {"mode": "write", "text": "feed the cat"})])


class Delivery(unittest.TestCase):
    def test_note_goes_up_once_she_has_her_words(self):
        order = []
        with mock.patch.object(reminders, "_sticky", lambda what, arg: order.append(what)), \
                mock.patch("llm.ask", lambda *a, **k: order.append("ask") or "hey, laundry!"), \
                mock.patch("ui.add_message"), mock.patch("ui.set_status"), \
                mock.patch("voice.speech.speak"), mock.patch.object(reminders, "_note_away"):
            reminders._deliver(None, ["laundry"])
        self.assertEqual(order[:2], ["ask", "show"])


if __name__ == "__main__":
    unittest.main()
