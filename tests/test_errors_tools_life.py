"""Error handling in tools/, commands/, life/ and the time parser: the
failures that used to ring an alarm three times, fire a reminder forever,
freeze the app or end the reminder scanner, each held to what it does now.
Nothing here reaches a real server.

    python -m unittest tests.test_errors_tools_life        (from the repo folder)
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
import tools  # noqa: E402
from core import timeutil, turnctx  # noqa: E402
from life import alarm, reminders  # noqa: E402
from tools import calc, files, shell  # noqa: E402


# ---------------------------------------------------------------------------
# The time parser
# ---------------------------------------------------------------------------
class ParseWhen(unittest.TestCase):
    """Out-of-range phrases are "not a time", never an OverflowError."""

    def test_far_future_is_none(self):
        for phrase in ("in 99999999 days", "in 1000000000 days", "in 10000 years",
                       "in 99999999h", "every 99999999 days", "in inf minutes"):
            self.assertEqual(timeutil.parse_when(phrase), (None, None), phrase)

    def test_ordinary_phrases_still_work(self):
        due, repeat = timeutil.parse_when("in 10 minutes")
        self.assertIsNotNone(due)
        self.assertIsNone(repeat)

    def test_too_frequent(self):
        for phrase in ("every second", "every 30 seconds", "every 0.5 minutes"):
            self.assertTrue(timeutil.too_frequent(timeutil.parse_when(phrase)[1]), phrase)

        for phrase in ("every 2 minutes", "every day at 8", "every monday at 9", "every hour"):
            self.assertFalse(timeutil.too_frequent(timeutil.parse_when(phrase)[1]), phrase)


class NextOccurrence(unittest.TestCase):
    def test_backlog_skipped_in_one_go(self):
        now = datetime.now()
        result = timeutil.next_occurrence({"amount": 1, "unit": "minutes"},
                                          now - timedelta(days=7), after=now)
        self.assertGreater(result, now)
        self.assertLessEqual(result, now + timedelta(minutes=2))

    def test_never_closer_than_a_minute(self):
        now = datetime.now()
        result = timeutil.next_occurrence({"amount": 1, "unit": "seconds"}, now, after=now)
        self.assertGreaterEqual(result, now + timedelta(seconds=59))

    def test_never_in_the_past(self):
        now = datetime.now()

        for repeat in ({"at": "08:00"}, {"weekday": 2, "at": "09:00"},
                       {"days": [0, 4], "at": "07:30"}, {"amount": 1, "unit": "months"}):
            self.assertGreater(timeutil.next_occurrence(repeat, now - timedelta(days=400), after=now), now)

    def test_hand_edited_repeats(self):
        now = datetime.now()
        self.assertIsNone(timeutil.next_occurrence({"amount": "abc", "unit": "minutes"}, now))
        self.assertIsNone(timeutil.next_occurrence({"amount": 1e30, "unit": "days"}, now))
        self.assertGreater(timeutil.next_occurrence({"weekday": 7, "at": "09:00"}, now), now)
        self.assertGreater(timeutil.next_occurrence({"amount": 5, "unit": "fortnights"}, now), now)


class DescribeRepeat(unittest.TestCase):
    def test_never_raises(self):
        for repeat in ({"amount": "abc", "unit": "minutes"}, {"weekday": 7},
                       {"days": [9, 12], "at": "08:00"}, {"unit": "minutes"}):
            self.assertIsInstance(timeutil.describe_repeat(repeat), str)

    def test_number_as_text(self):
        self.assertEqual(timeutil.describe_repeat({"amount": "30", "unit": "minutes"}),
                         "every 30 minutes")


# ---------------------------------------------------------------------------
# The reminder scanner
# ---------------------------------------------------------------------------
class ScannerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [
            mock.patch.object(reminders, "REMINDERS_DIR", self.tmp),
            mock.patch.object(reminders, "REMINDERS_FILE", os.path.join(self.tmp, "r.json")),
            mock.patch("ui.add_message"),
            mock.patch("ui.set_status"),
            mock.patch.object(reminders, "_note_away"),
        ]
        for p in self.patches:
            p.start()
        self.saved = list(reminders._reminders)
        reminders._reminders[:] = []

    def tearDown(self):
        reminders._reminders[:] = self.saved
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _due(self, text="stretch", repeat=None, kind="reminder", attempts=0):
        r = reminders.add(text, datetime.now() - timedelta(seconds=5), repeat, kind=kind)
        r["attempts"] = attempts
        return r


class Snooze(ScannerBase):
    """/snooze 99999999 raised OverflowError after the ring, which counted as
    a failed delivery: the same alarm rang three times, then was deleted."""

    def test_huge_snooze_rings_once_and_is_clamped(self):
        self._due("work", kind="alarm")

        with mock.patch.object(config, "ALARMS_ENABLED", True, create=True), \
                mock.patch.object(alarm, "ring", return_value=10 ** 9) as ring:
            reminders._scan_once("m", False)
            reminders._scan_once("m", False)

        ring.assert_called_once()
        left = reminders.pending()
        self.assertEqual(len(left), 1)
        due = datetime.fromisoformat(left[0]["due_at"])
        self.assertLessEqual(due, datetime.now() + timedelta(days=1, minutes=1))

    def test_dismiss_clamps(self):
        alarm._ringing.set()
        try:
            alarm.dismiss(10 ** 12)
            self.assertLessEqual(alarm._snoozed_for[0], 24 * 60)
        finally:
            alarm._ringing.clear()
            alarm._dismissed.clear()
            alarm._snoozed_for[0] = 0


class Failures(ScannerBase):
    def test_failure_backs_off(self):
        r = self._due()

        with mock.patch.object(reminders, "_deliver", side_effect=RuntimeError("down")) as deliver:
            reminders._scan_once("m", False)
            reminders._scan_once("m", False)        # not due again yet

        deliver.assert_called_once()
        self.assertEqual(r["attempts"], 1)
        self.assertGreater(datetime.fromisoformat(r["due_at"]), datetime.now())

    def test_repeating_reminder_survives_giving_up(self):
        r = self._due(repeat={"at": "08:00"}, attempts=reminders.MAX_DELIVERY_ATTEMPTS - 1)

        with mock.patch.object(reminders, "_deliver", side_effect=RuntimeError("down")):
            reminders._scan_once("m", False)

        self.assertEqual(reminders.count(), 1)
        self.assertEqual(r["attempts"], 0)
        self.assertGreater(datetime.fromisoformat(r["due_at"]), datetime.now())

    def test_one_off_dropped_after_giving_up(self):
        self._due(attempts=reminders.MAX_DELIVERY_ATTEMPTS - 1)

        with mock.patch.object(reminders, "_deliver", side_effect=RuntimeError("down")):
            reminders._scan_once("m", False)

        self.assertEqual(reminders.count(), 0)

    def test_after_delivery_never_delivered_again(self):
        self._due()

        with mock.patch.object(reminders, "_deliver") as deliver, \
                mock.patch.object(reminders, "_retire", side_effect=RuntimeError("disk")):
            reminders._scan_once("m", False)
            reminders._scan_once("m", False)

        deliver.assert_called_once()
        self.assertEqual(reminders.count(), 0)

    def test_repeat_with_no_next_time_is_removed(self):
        r = self._due(repeat={"amount": 1e30, "unit": "days"})

        with mock.patch.object(reminders, "_deliver"):
            reminders._scan_once("m", False)

        self.assertNotIn(r, reminders.pending())


class HandEdited(ScannerBase):
    def test_bad_records(self):
        reminders._reminders[:] = [{"text": "a", "due_at": None}, {"due_at": 5},
                                   {"text": "b", "due_at": "not a date"}]
        reminders.pending()
        reminders._due_now()
        self.assertGreater(reminders._seconds_until_next(), 0)
        for r in reminders._reminders:
            reminders.describe(r)

    def test_missing_text_delivers(self):
        reminders._reminders[:] = [{"id": "x", "due_at": (datetime.now() - timedelta(seconds=1)).isoformat()}]

        with mock.patch.object(reminders, "_deliver") as deliver:
            reminders._scan_once("m", False)

        deliver.assert_called_once()

    def test_load_tolerates_junk(self):
        for junk in ('{"a": 1}', '[1, "x", {"text": "ok", "due_at": "2030-01-01T00:00:00"}]', "\xff"):
            with open(reminders.REMINDERS_FILE, "w", encoding="latin-1") as f:
                f.write(junk)
            reminders.load()
            self.assertTrue(all(isinstance(r, dict) for r in reminders._reminders))

    def test_wait_is_finite(self):
        for value in (float("inf"), float("nan"), 1e20, -5):
            with mock.patch.object(reminders, "REMINDER_CHECK_INTERVAL_SECONDS", value):
                wait = reminders._seconds_until_next()
            self.assertTrue(0 < wait <= 3600, value)

    def test_save_failure_is_quiet(self):
        with mock.patch.object(reminders, "REMINDERS_DIR", os.path.join(self.tmp, "f", "x")), \
                mock.patch("os.makedirs", side_effect=OSError("read-only")):
            reminders.save()

    def test_extractor_thread_never_raises(self):
        with mock.patch.object(reminders, "_extract_fields",
                               return_value=("{}", {"kind": "in", "amount": 1e9, "unit": "days", "text": "x"})):
            reminders._extract_reminder("m", "remind me in 1e9 days")
        self.assertEqual(reminders.count(), 0)

    def test_extractor_refuses_every_second(self):
        with mock.patch.object(reminders, "_extract_fields",
                               return_value=("{}", {"kind": "every", "amount": 1, "unit": "seconds", "text": "x"})):
            reminders._extract_reminder("m", "remind me every second")
        self.assertEqual(reminders.count(), 0)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
class ToolCall(unittest.TestCase):
    def test_every_second_refused(self):
        with mock.patch.object(reminders, "add") as add:
            out = tools.call("set_reminder", json.dumps({"text": "x", "when": "every second"}))
        add.assert_not_called()
        self.assertTrue(out.startswith("Error: repeats"), out)

    def test_far_future_is_a_clean_answer(self):
        out = tools.call("set_reminder", json.dumps({"text": "x", "when": "in 99999999 days"}))
        self.assertIn("Couldn't read", out)

    def test_infinity_refused(self):
        for raw in ('{"number": Infinity}', '{"number": NaN}', '{"number": 1e999}'):
            self.assertIn("not valid JSON", tools.call("cancel_reminder", raw))

    def test_cancel_text(self):
        self.assertTrue(tools.call("cancel_reminder", '{"number": "abc"}').startswith("Error"))

    def test_wrong_arguments_vs_a_bug(self):
        def broken(a):
            return None + 1

        tools.tool("_test_broken", "x", {"a": {"type": "string"}})(broken)
        try:
            self.assertIn("wrong arguments", tools.call("_test_broken", '{"b": 1}'))
            self.assertIn("Error running", tools.call("_test_broken", '{"a": 1}'))
        finally:
            tools._REGISTRY.pop("_test_broken", None)


class Calculate(unittest.TestCase):
    def test_units_never_power(self):
        started = time.monotonic()
        for text in ("9**9**9 m to km", "9^9^9 m to km", "1 m to km**9**9**9"):
            out = calc._calculate(text)
            self.assertNotIn(" = ", out, text)
        self.assertLess(time.monotonic() - started, 2)

    def test_not_a_number_answers(self):
        self.assertIn("too big", calc._calculate("1e308 * 10"))
        self.assertIn("real number", calc._calculate("(-8) ** (1/3)"))
        self.assertIn("= 12", calc._calculate("3 * 4"))


class Shell(unittest.TestCase):
    def test_output_keeps_start_and_end(self):
        out = shell._Output(10)
        for _ in range(100):
            out.add(b"0123456789")
        self.assertEqual(out.total, 1000)
        text = out.text()
        self.assertTrue(text.startswith("0123456789"))
        self.assertTrue(text.endswith("0123456789"))
        self.assertIn("980 bytes left out", text)

    @unittest.skipIf(os.name == "nt" or not shutil.which("yes"), "needs bash and yes")
    def test_flood_is_stopped(self):
        approve = lambda *a: True  # noqa: E731
        with mock.patch.object(shell, "MAX_OUTPUT_BYTES", 200_000), \
                mock.patch.object(config, "SHELL_TIMEOUT", 20, create=True), \
                mock.patch.object(config, "SHELL_ENABLED", True, create=True), \
                mock.patch("ui.add_message"):
            with turnctx.begin(remote="test", approver=approve):
                started = time.monotonic()
                out = shell._run_command("yes")
        self.assertLess(time.monotonic() - started, 15)
        self.assertIn("printed more than", out)
        self.assertLess(len(out), 20_000)


class Files(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.p = [mock.patch.object(files, "HOME", self.home),
                  mock.patch.object(files, "_ask", return_value=True),
                  mock.patch.object(files, "_ask_read", return_value=True)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def _file(self, name, data):
        path = os.path.join(self.home, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_latin1_not_rewritten(self):
        path = self._file("old.txt", "caf\xe9 au lait".encode("latin-1"))
        out = files._edit_file(path, "au", "with")
        self.assertIn("isn't UTF-8", out)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), "caf\xe9 au lait".encode("latin-1"))

    def test_too_big_to_edit(self):
        path = self._file("big.log", b"x" * 100)
        with mock.patch.object(files, "MAX_EDIT_BYTES", 10):
            self.assertIn("too big", files._edit_file(path, "x", "y"))
            self.assertIn("too big", files._write_file(path, "new"))

    def test_edit_keeps_mode_and_leaves_no_temp(self):
        path = self._file("run.sh", b"echo hi\n")
        os.chmod(path, 0o755)
        self.assertIn("Edited", files._edit_file(path, "hi", "there"))
        self.assertTrue(os.stat(path).st_mode & 0o100)
        self.assertEqual(sorted(os.listdir(self.home)), ["run.sh"])


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
class Commands(unittest.TestCase):
    def setUp(self):
        self.said = []
        self.p = mock.patch("ui.add_message", side_effect=lambda who, text: self.said.append(text))
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_huge_ids_are_no_such_one(self):
        import commands

        for text in ("/lessons forget 99999999999999999999999", "/skills show 99999999999999999999999",
                     "/projects show 99999999999999999999999", "/episodes forget 99999999999999999999999"):
            self.said.clear()
            self.assertTrue(commands.handle(text))
            self.assertTrue(any(s.startswith("No ") for s in self.said), (text, self.said))

    def test_alarm_far_future_and_snooze(self):
        import commands

        with mock.patch.object(reminders, "add") as add:
            commands.handle("/alarm in 99999999 days")
            commands.handle("/alarm every 10 seconds")
        add.assert_not_called()
        commands.handle("/snooze 99999999")
        self.assertIn("1 to 1440", self.said[-1])
        commands.handle("/when in 10000 years")
        self.assertIn("not a time", self.said[-1])

    def test_failing_command_is_a_line(self):
        import commands
        from commands import app

        with mock.patch.object(app, "handle", side_effect=RuntimeError("boom")):
            self.assertTrue(commands.handle("/anything"))
        self.assertIn("boom", self.said[-1])


if __name__ == "__main__":
    unittest.main()
