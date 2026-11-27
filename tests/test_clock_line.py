"""situation.clock: the minute in her prompt only when the message is about
time, unless set to exact (llm/prompts.py, core/timeutil.py)."""
import unittest
from datetime import datetime
from unittest import mock

import config
from core import timeutil
from llm import prompts

NIGHT = datetime(2026, 11, 26, 2, 43)


class Clock(unittest.TestCase):
    def now(self, query, setting="part of day"):
        with mock.patch.object(config, "SITUATION_CLOCK", setting, create=True), \
             mock.patch.object(timeutil, "now", return_value=NIGHT), \
             mock.patch("core.timewords.now", return_value=NIGHT):
            return prompts._now(query)

    def test_part_of_day_has_no_minute(self):
        line = self.now("bend forward for me")
        self.assertNotIn("02:43", line)
        self.assertIn("Thursday 26 November 2026, the middle of the night", line)
        self.assertIn("tomorrow is Friday 27 November", line)

    def test_about_time_gets_the_minute(self):
        for q in ("what time is it?", "remind me in 20 minutes", "set an alarm for 7am",
                  "is it 3:30 yet", "how late is it", "what are we doing tonight"):
            self.assertIn("02:43", self.now(q), q)

    def test_ordinary_words_dont(self):
        for q in ("I am tired", "hello luna", "check the server", "*hugs you* I'm home"):
            self.assertNotIn("02:43", self.now(q), q)

    def test_roleplay_words_dont(self):
        for q in ("*kisses your lips softly and tenderly reminding you how much he loves you*",
                  "every time I see you I smile", "*checks the time* come here",
                  "(remind me later) hi", "I had the best time"):
            self.assertNotIn("02:43", self.now(q), q)

    def test_asking_outside_an_action_still_does(self):
        for q in ("*yawns* what time is it", "remind me at 5", "*stretches* set a timer"):
            self.assertIn("02:43", self.now(q), q)

    def test_exact_setting(self):
        self.assertIn("02:43", self.now("hello luna", "exact"))

    def test_day_keeps_the_date_lines(self):
        day = timeutil.describe_day(NIGHT).split("\n")
        full = timeutil.describe_now(NIGHT).split("\n")
        self.assertEqual(day[1:], full[1:])


class Example(unittest.TestCase):
    """The worked tool call in front of a conversation without one
    (llm/replay.py _demonstration): the day, not the minute."""

    def demo(self, setting):
        from llm import replay

        with mock.patch.object(config, "SITUATION_CLOCK", setting, create=True), \
             mock.patch.object(timeutil, "now", return_value=NIGHT), \
             mock.patch("core.timewords.now", return_value=NIGHT), \
             mock.patch.object(replay, "datetime", wraps=datetime) as dt:
            dt.now.return_value = NIGHT
            return replay._demonstration()

    def test_part_of_day(self):
        msgs = self.demo("part of day")
        self.assertEqual(msgs[0]["content"], "what day is it?")
        self.assertEqual(msgs[-1]["content"], "It's Thursday the 26th.")
        self.assertTrue(all("02:43" not in str(m.get("content")) for m in msgs))
        self.assertIn("the middle of the night", msgs[2]["content"])

    def test_exact(self):
        msgs = self.demo("exact")
        self.assertEqual(msgs[0]["content"], "what time is it?")
        self.assertIn("02:43", msgs[-1]["content"])


if __name__ == "__main__":
    unittest.main()
