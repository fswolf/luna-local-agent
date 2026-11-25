"""The reminder safety net: it catches a reminder she claimed and never set,
reads the time as you said it, and leaves alone a turn that scheduled a job."""
import unittest
from datetime import datetime

import tools
from life import reminders


class TimeWords(unittest.TestCase):

    def test_the_time_words_are_read_as_said(self):
        due, repeat = reminders.schedule_from({"when": "every Sunday at 4am", "text": "check the backups"},
                                              now=datetime(2026, 11, 25, 15, 0))
        self.assertEqual(due, datetime(2026, 11, 29, 4, 0))
        self.assertEqual(repeat, {"at": "04:00", "weekday": 6})

    def test_the_older_shape_still_works(self):
        due, repeat = reminders.schedule_from({"kind": "in", "amount": 10, "unit": "minutes", "text": "stretch"},
                                              now=datetime(2026, 11, 25, 15, 0))
        self.assertEqual(due, datetime(2026, 11, 25, 15, 10))
        self.assertIsNone(repeat)

    def test_words_it_cant_read_set_nothing(self):
        self.assertEqual(reminders.schedule_from({"when": "whenever", "text": "x"}), (None, None))
        self.assertIsNone(reminders.phrase_from({"when": "in 5 minutes", "text": ""}))

    def test_the_prompt_says_a_job_is_not_a_reminder(self):
        self.assertIn("job to be scheduled", reminders._PROMPT)
        self.assertNotIn('"kind"', reminders._PROMPT)


class ScheduledJobsAreNotMissedReminders(unittest.TestCase):

    def test_scheduling_tools_switch_the_net_off(self):
        from plugins import cron  # noqa: F401  registers its tools
        for name in ("schedule_job", "list_jobs", "cancel_job", "approve_job_script", "set_reminder"):
            self.assertIn(name, tools.SCHEDULES)
        self.assertNotIn("run_command", tools.SCHEDULES)


if __name__ == "__main__":
    unittest.main()
