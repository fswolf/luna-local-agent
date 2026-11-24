"""Tasks she sets herself (set_task: done when due, as a full turn kept in
history), sending without asking to the addresses on email.no_ask_to, and
check_email's sender filter.

    python -m unittest tests.test_tasks_and_no_ask
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from email.message import EmailMessage
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402

import config  # noqa: E402
from life import reminders  # noqa: E402
from tools import mail  # noqa: E402

ACCOUNT = {"user": "support@shop.example", "password": "x", "from": "Shop <support@shop.example>",
           "imap_host": "imap", "smtp_host": "smtp", "imap_port": 993, "smtp_port": 465}
LUMEN = "lumenlight@mail.grokbot.com"


class Tasks(unittest.TestCase):
    def setUp(self):
        self.saved = list(reminders._reminders)
        reminders._reminders[:] = []
        p = mock.patch.object(reminders, "save")
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(lambda: reminders._reminders.__setitem__(slice(None), self.saved))

    def due(self, kind, text):
        r = reminders.add(text, datetime.now() - timedelta(seconds=1), None, kind=kind)
        return r

    def test_set_task_saves_a_task(self):
        from tools import reminders as tool
        out = tool._set_task("check email from " + LUMEN + " and reply", "every day at 6pm")
        self.assertIn("task: check email", out)
        self.assertTrue(reminders.is_task(reminders._reminders[-1]))
        self.assertEqual(reminders._reminders[-1]["repeat"], {"at": "18:00"})

    def test_a_due_task_is_done_not_mentioned(self):
        self.due("task", "check email from " + LUMEN)
        with mock.patch.object(reminders, "_deliver_task") as task, mock.patch.object(reminders, "_deliver") as say:
            reminders._scan_once("m", first_pass=False)
        task.assert_called_once_with("m", "check email from " + LUMEN, missed=False)
        say.assert_not_called()

    def test_a_task_goes_on_its_own_after_reminders(self):
        self.due("task", "sweep")
        self.due("reminder", "bins")
        with mock.patch.object(reminders, "_deliver_task") as task, mock.patch.object(reminders, "_deliver") as say:
            reminders._scan_once("m", first_pass=False)
            reminders._scan_once("m", first_pass=False)
        say.assert_called_once_with("m", ["bins"], missed=False)
        task.assert_called_once()

    def test_the_task_turn_says_do_it_and_is_a_normal_turn(self):
        asked = {}
        def ask(trigger, model, source=None, **kw):
            asked.update(trigger=trigger, source=source, kw=kw)
            return "Done - one email from Lumen, answered."
        with mock.patch("llm.ask", side_effect=ask), mock.patch("ui.add_message"), mock.patch("ui.set_status"), \
                mock.patch("voice.speech.speak"), mock.patch.object(reminders, "_note_away") as away:
            reminders._deliver_task("m", "check email from " + LUMEN)
        self.assertIn("do it now", asked["trigger"])
        self.assertNotIn("Bring", asked["trigger"])
        self.assertEqual(asked["source"], "task")
        self.assertEqual(asked["kw"], {})                       # no context=: her history and memory, stored
        self.assertIn("Lumen", away.call_args[0][1])

    def test_set_task_is_with_the_reminders(self):
        import tools
        self.assertEqual(tools.group_of("set_task"), "Reminders")       # routed with them, shown with them

    def test_a_failed_task_isnt_tried_again(self):
        r = self.due("task", "send the report")
        r["repeat"] = {"at": "18:00"}
        with mock.patch.object(reminders, "_deliver_task", side_effect=RuntimeError("boom")) as task, \
                mock.patch("ui.add_message") as said, mock.patch("ui.set_status"), \
                mock.patch.object(reminders, "_note_away"):
            reminders._scan_once("m", first_pass=False)
            reminders._scan_once("m", first_pass=False)
        task.assert_called_once()                               # not again a minute later
        self.assertIn("failed partway", said.call_args[0][1])
        self.assertGreater(datetime.fromisoformat(reminders._reminders[-1]["due_at"]), datetime.now())

    def test_a_reminder_waits_for_her_turn(self):
        import threading
        from core import assistant
        order = []
        with mock.patch("llm.ask", side_effect=lambda *a, **k: order.append("reminder") or "ok"), \
                mock.patch("ui.add_message"), mock.patch("ui.set_status"), mock.patch("voice.speech.speak"), \
                mock.patch.object(reminders, "_note_away"), mock.patch.object(reminders, "_sticky"):
            assistant._turn.acquire()
            t = threading.Thread(target=reminders._deliver, args=("m", ["bins"]))
            t.start()
            t.join(0.3)
            order.append("your turn ends")
            assistant._turn.release()
            t.join(2)
        self.assertEqual(order, ["your turn ends", "reminder"])

    def test_listed_as_a_task(self):
        r = self.due("task", "sweep")
        self.assertIn("task: sweep", reminders.describe(r))


class FiringTurnsDontReschedule(unittest.TestCase):
    """Her 18:00 reminder's own text ("6 PM daily inbox sweep") was read as a
    new reminder request by the fallback net."""

    def test_the_nets_skip_her_own_reminders_and_tasks(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llm", "turns.py")).read()
        guard = src.index('if source in ("reminder", "task"):')
        self.assertLess(guard, src.index("reminders.extract_in_background(model, text)"))
        self.assertLess(guard, src.index("longterm.extract_in_background(model, text, answer)"))


class NoAsk(unittest.TestCase):
    def send(self, to, no_ask, approve=False):
        sent = []
        server = mock.MagicMock()
        server.__enter__.return_value = server
        server.send_message.side_effect = sent.append
        with mock.patch.object(mail, "account", return_value=dict(ACCOUNT)), \
                mock.patch.object(config, "_stored", side_effect=lambda p: no_ask if p == "email.no_ask_to" else None), \
                mock.patch.object(mail, "_approve_send", return_value=approve) as asked, \
                mock.patch.object(mail.smtplib, "SMTP_SSL", return_value=server), \
                mock.patch("life.away.note") as away:
            out = mail._send_email(body="Hi Lumen", to=to, subject="hello")
        return out, sent, asked, away

    def test_on_the_list_goes_without_asking_and_is_noted(self):
        _out, sent, asked, away = self.send(LUMEN, [LUMEN.upper()])
        self.assertEqual(len(sent), 1)
        asked.assert_not_called()
        self.assertIn(LUMEN, away.call_args[0][1])

    def test_anyone_else_still_asks(self):
        out, sent, asked, _ = self.send("customer@shop.example", [LUMEN])
        asked.assert_called_once()
        self.assertEqual(sent, [])
        self.assertIn("didn't approve", out)

    def test_one_listed_and_one_not_still_asks(self):
        _out, sent, asked, _ = self.send(f"{LUMEN}, other@x.example", [LUMEN])
        asked.assert_called_once()

    def test_an_empty_list_asks(self):
        _out, _sent, asked, _ = self.send(LUMEN, [])
        asked.assert_called_once()

    def test_a_hand_edited_number_means_no_one(self):
        with mock.patch.object(config, "_stored", return_value=5):
            self.assertEqual(mail.no_ask_to(), set())

    def test_a_comma_string_in_the_file_works_too(self):
        with mock.patch.object(config, "_stored", return_value=f"{LUMEN}, b@x.example"):
            self.assertEqual(mail.no_ask_to(), {LUMEN, "b@x.example"})

    def test_a_job_still_never_sends(self):
        from core import turnctx
        with mock.patch.object(turnctx, "current", return_value=mock.Mock(job="x", seen=None, approver=None, source=None)):
            out, sent, _a, _w = self.send(LUMEN, [LUMEN])
        self.assertEqual(sent, [])
        self.assertIn("can't send", out)


class SenderFilter(unittest.TestCase):
    def test_a_name_with_a_space_works(self):
        box = mock.MagicMock()
        box.__enter__.return_value = box
        box.uid.return_value = ("OK", [b""])
        with mock.patch.object(mail, "account", return_value=dict(ACCOUNT)), \
                mock.patch.object(mail, "_mailbox", return_value=box):
            mail._check_email(sender="Lumen Light", unread_only=False)
        self.assertEqual(box.uid.call_args.args, ("search", None, "ALL", "FROM", '"Lumen Light"'))

    def test_the_server_is_asked_for_their_mail_only(self):
        box = mock.MagicMock()
        box.__enter__.return_value = box
        box.uid.return_value = ("OK", [b""])
        with mock.patch.object(mail, "account", return_value=dict(ACCOUNT)), \
                mock.patch.object(mail, "_mailbox", return_value=box):
            out = mail._check_email(sender=LUMEN + '" OR ALL')
        # the quote that would have closed the string is gone: one search term, not three
        self.assertEqual(box.uid.call_args.args, ("search", None, "UNSEEN", "FROM", f'"{LUMEN} OR ALL"'))
        self.assertIn("from " + LUMEN, out)


if __name__ == "__main__":
    unittest.main()
