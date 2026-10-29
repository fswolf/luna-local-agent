"""While you were out (life/away.py): what happened while you were away rides
along in her hello when presence sees you come back - only for you, said once.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from core import turnctx  # noqa: E402
from life import away  # noqa: E402


class Notes(unittest.TestCase):
    def setUp(self):
        away._items.clear(); away._said.clear()

    def tearDown(self):
        away._items.clear(); away._said.clear()

    def test_since_and_said_once(self):
        away.note("reminder", 'a reminder went off: "call mom"', now=1000)
        away.note("job", 'the scheduled job "backup" ran: all four moved', now=2000)
        self.assertEqual([i["kind"] for i in away.since(1500, now=2100)], ["job"])
        text = away.block(500, now=2100)
        self.assertIn("call mom", text)
        self.assertIn("backup", text)
        away.clear(2000)
        self.assertEqual(away.block(500, now=2100), "")

    def test_nothing_says_nothing(self):
        self.assertEqual(away.block(0), "")
        away.note("job", "   ")                       # empty: not noted
        self.assertEqual(away.since(0), [])

    def test_yesterday_says_so(self):
        import time as t
        now = t.mktime((2026, 10, 29, 9, 0, 0, 0, 0, -1))
        then = t.mktime((2026, 10, 28, 23, 40, 0, 0, 0, -1))
        self.assertEqual(away._clock(then, now), "yesterday 11:40 pm")
        self.assertEqual(away._clock(now - 60, now), "8:59 am")

    def test_old_and_too_many_drop(self):
        away.note("job", "ancient", now=0)
        away.note("job", "recent", now=away.MAX_AGE + 10)
        self.assertEqual([i["text"] for i in away.since(0, now=away.MAX_AGE + 20)], ["recent"])
        for n in range(away.KEEP + 5):
            away.note("job", f"n{n}", now=1e9 + n)
        self.assertEqual(len(away._items), away.KEEP)


class Greeting(unittest.TestCase):
    """presence._greet: the report for you, none of it for a guest."""

    def setUp(self):
        away._items.clear(); away._said.clear()
        from senses import presence
        self.presence = presence
        self.saved = dict(presence._state)
        presence._state.update(model="m", stranger=False)

    def tearDown(self):
        away._items.clear(); away._said.clear()
        self.presence._state.clear()
        self.presence._state.update(self.saved)

    def _greet(self, who, gap=3600):
        from core import assistant, history, interrupts
        from mind import mood
        import llm
        import ui
        from voice import speech

        seen = {}

        def ask(trigger, model, **kw):
            seen["trigger"], seen["speaker"] = trigger, turnctx.current().speaker
            return "Welcome back!"

        p = self.presence
        p._state["who"] = who
        with mock.patch.object(p.time, "sleep"), \
                mock.patch.object(p._tracker, "present", True), \
                mock.patch.object(assistant, "busy", return_value=False), \
                mock.patch.object(interrupts, "recording", return_value=False), \
                mock.patch.object(mood, "away", return_value=0), \
                mock.patch.object(llm, "ask", side_effect=ask), \
                mock.patch.object(ui, "add_message"), mock.patch.object(ui, "set_status"), \
                mock.patch.object(history, "add_message") as added, mock.patch.object(history, "save"), \
                mock.patch.object(speech, "speak"), \
                mock.patch.object(config, "USER", "Ryan", create=True):
            p._greet(gap)
        self.history_calls = added.call_args_list
        return seen

    def test_you_hear_what_happened(self):
        away.note("reminder", 'a reminder went off: "take the bins out"')
        seen = self._greet(None)
        self.assertIn("While they were away", seen["trigger"])
        self.assertIn("take the bins out", seen["trigger"])
        self.assertIsNone(seen["speaker"])
        self.assertEqual(away.since(0), [])           # said: not again next time

    def test_a_guest_hears_none_of_it(self):
        away.note("job", 'the scheduled job "backup" failed: no route to host')
        with mock.patch("senses.people._not_owner", side_effect=lambda n: n):
            seen = self._greet("Shannon")
        self.assertNotIn("backup", seen["trigger"])
        self.assertEqual(seen["speaker"], "Shannon")
        self.assertEqual(len(away.since(0)), 1)       # still waiting for you

    def test_the_news_goes_in_history_for_a_follow_up(self):
        away.note("job", 'the scheduled job "backup" failed: no route to host')
        from core import history
        seen = self._greet(None)
        user_line = [c.args[1] for c in self.history_calls if c.args[0] == "user"][0]
        self.assertIn("no route to host", user_line)
        self.assertIn("backup", seen["trigger"])

    def test_held_for_later_in_a_heavy_moment(self):
        away.note("job", "news")
        from life import offers
        with mock.patch.object(offers, "_quiet_now", return_value="heavy moment"):
            seen = self._greet(None)
        self.assertNotIn("news", seen["trigger"])
        self.assertEqual(len(away.since(0)), 1)       # kept for a better turn

    def test_only_from_while_you_were_gone(self):
        away.note("reminder", "long before", now=1.0)
        seen = self._greet(None, gap=60)
        self.assertNotIn("long before", seen["trigger"])


class Sources(unittest.TestCase):
    def setUp(self):
        away._items.clear(); away._said.clear()

    def tearDown(self):
        away._items.clear(); away._said.clear()

    def test_a_job_notes_its_report(self):
        from plugins import cron
        job = {"name": "backup", "task": "move the dumps", "speak": False, "_busy": True, "_once": False}
        with mock.patch("core.assistant.respond_to_job", return_value="Moved them.\nAll 4 databases are on the NAS."):
            cron._fire(job)
        self.assertIn("All 4 databases are on the NAS", away.since(0)[0]["text"])

    def test_a_failed_job_says_so(self):
        from plugins import cron
        job = {"name": "backup", "task": "x", "speak": False, "_busy": True, "_once": False}
        with mock.patch("core.assistant.respond_to_job", side_effect=RuntimeError("model gone")):
            cron._fire(job)
        self.assertIn("failed: model gone", away.since(0)[0]["text"])

    def test_a_reminder_notes_itself(self):
        from life import reminders
        import llm
        import ui
        from voice import speech
        with mock.patch.object(llm, "ask", return_value="Bins!"), \
                mock.patch.object(ui, "add_message"), mock.patch.object(ui, "set_status"), \
                mock.patch.object(speech, "speak"):
            reminders._deliver("m", ["take the bins out"])
        self.assertIn("take the bins out", away.since(0)[0]["text"])

    def test_her_hello_can_carry_an_offer(self):
        from life import offers
        with turnctx.begin(source="greeting"):
            self.assertEqual(offers._quiet_now(), "")
        with turnctx.begin(source="greeting", speaker="Shannon"):
            self.assertEqual(offers._quiet_now(), "not your own turn")


class YourNextTurn(unittest.TestCase):
    """No greeting (no camera): your next own turn carries it, once."""

    def setUp(self):
        away._items.clear(); away._said.clear()

    def tearDown(self):
        away._items.clear(); away._said.clear()

    def test_quiet_things_ride_on_your_turn_once(self):
        away.note("job", 'the scheduled job "backup" ran: fine', quiet=True)
        away.note("reminder", "said to your face", quiet=False)
        with turnctx.begin(source="typed"):
            first = away.line()
            again = away.line()                  # same turn, prompt built twice
        self.assertIn("backup", first)
        self.assertNotIn("said to your face", first)
        self.assertEqual(first, again)
        with turnctx.begin(source="typed"):
            self.assertNotIn("Mention", away.line())   # said once (kept only as a reference)

    def test_a_follow_up_still_has_the_details(self):
        away.note("job", 'the scheduled job "backup" failed: no route to host', quiet=True)
        with turnctx.begin(source="typed"):
            self.assertIn("While", away.line())
        with turnctx.begin(source="typed"):
            later = away.line()
        self.assertIn("no route to host", later)
        self.assertIn("don't bring it up again", later)
        with mock.patch.object(away.time, "time", return_value=away.time.time() + away.FOLLOW_UP + 5), \
                turnctx.begin(source="typed"):
            self.assertEqual(away.line(), "")    # and then it's gone

    def test_not_for_guests_jobs_or_chat(self):
        away.note("job", "news", quiet=True)
        for fields in ({"source": "typed", "speaker": "Shannon"}, {"source": "discord", "remote": "discord"},
                       {"source": "job:x", "job": "x", "private": False}):
            with turnctx.begin(**fields):
                self.assertEqual(away.line(), "")
        self.assertEqual(len(away._items), 1)    # still waiting for you

    def test_held_in_a_heavy_moment(self):
        away.note("job", "news", quiet=True)
        from life import offers
        with mock.patch.object(offers, "_quiet_now", return_value="heavy moment"), \
                turnctx.begin(source="voice"):
            self.assertEqual(away.line(), "")
        self.assertEqual(len(away._items), 1)


if __name__ == "__main__":
    unittest.main()
