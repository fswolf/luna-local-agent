"""Email logins (tools/mail.py): one login is kept open between calls, a
server's "not now" is told apart from a wrong password, and the hints name
the actual server, never Gmail unless it is Gmail.

    python -m unittest discover tests        (from the repo folder)
"""
import imaplib
import os
import smtplib
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from tools import mail  # noqa: E402

PRIVATE = {"user": "me@example.com", "password": "x", "imap_host": "mail.privateemail.com",
           "smtp_host": "mail.privateemail.com", "imap_port": 993, "smtp_port": 465}
GMAIL = {**PRIVATE, "user": "me@gmail.com", "imap_host": "imap.gmail.com", "smtp_host": "smtp.gmail.com"}
BUSY = imaplib.IMAP4.error(b"[UNAVAILABLE] Temporary authentication failure. [dovecot-proxy-11]")
WRONG = imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Authentication failed.")


def fresh():
    with mail._lock:
        mail._drop()
        if mail._conn["timer"]:
            mail._conn["timer"].cancel()
        mail._conn.update(timer=None, used=0.0)
        mail._cool.update(until=0.0, error=None)


def box():
    b = mock.MagicMock()
    b.noop.return_value = ("OK", [b""])
    b.select.return_value = ("OK", [b"3"])
    return b


class Messages(unittest.TestCase):
    def test_busy_is_not_a_wrong_password(self):
        out = mail._fail("check email", BUSY, PRIVATE)
        self.assertIn("mail.privateemail.com", out)
        self.assertIn("temporary", out)
        self.assertNotIn("Gmail", out)
        self.assertNotIn("app password", out)

    def test_wrong_password_names_the_server(self):
        out = mail._fail("check email", WRONG, PRIVATE)
        self.assertIn("refused the login", out)
        self.assertIn("mail.privateemail.com", out)
        self.assertNotIn("Google", out)

    def test_app_password_only_for_providers_that_need_one(self):
        self.assertIn("Google accounts need an app password", mail._fail("check email", WRONG, GMAIL))

    def test_smtp(self):
        self.assertEqual(mail._kind(smtplib.SMTPAuthenticationError(535, b"bad")), "refused")
        self.assertEqual(mail._kind(smtplib.SMTPAuthenticationError(454, b"try later")), "busy")

    def test_server_words_without_bytes_noise(self):
        out = mail._fail("check email", BUSY, PRIVATE)
        self.assertIn("([UNAVAILABLE] Temporary", out)
        self.assertNotIn("b'", out)

    def test_later_errors_mentioning_auth_are_not_a_wrong_password(self):
        e = imaplib.IMAP4.error("command SEARCH illegal in state AUTH, only allowed in states SELECTED")
        self.assertEqual(mail._kind(e), "other")
        e.at_login = True
        self.assertEqual(mail._kind(e), "refused")

    def test_recipients_refused_is_not_the_network(self):
        e = smtplib.SMTPRecipientsRefused({"x@y": (550, b"no such user")})
        self.assertEqual(mail._kind(e), "other")
        self.assertEqual(mail._kind(smtplib.SMTPServerDisconnected("gone")), "dropped")

    def test_network_and_folder(self):
        self.assertEqual(mail._kind(ConnectionRefusedError()), "network")
        self.assertEqual(mail._kind(imaplib.IMAP4.abort("socket error")), "dropped")
        self.assertIn("inside the mailbox", mail._fail("check email", mail._NoFolder(
            "there's no folder called 'PrivateMail' (folders are inside the mailbox; INBOX is the usual one)"), PRIVATE))


class KeptOpen(unittest.TestCase):
    def setUp(self):
        fresh()
        self.addCleanup(fresh)

    def test_one_login_for_several_calls(self):
        b = box()
        with mock.patch.object(mail, "_imap", return_value=b) as login:
            for _ in range(3):
                with mail._mailbox(PRIVATE, "INBOX"):
                    pass
        self.assertEqual(login.call_count, 1)
        b.logout.assert_not_called()

    def test_dead_or_idle_connection_logs_in_again(self):
        first, second = box(), box()
        first.noop.side_effect = imaplib.IMAP4.abort("gone")
        with mock.patch.object(mail, "_imap", side_effect=[first, second]) as login:
            with mail._mailbox(PRIVATE, "INBOX"):
                pass
            with mail._mailbox(PRIVATE, "INBOX") as b:
                self.assertIs(b, second)
        self.assertEqual(login.call_count, 2)

    def test_other_account_logs_in_again(self):
        with mock.patch.object(mail, "_imap", side_effect=[box(), box()]) as login:
            with mail._mailbox(PRIVATE, "INBOX"):
                pass
            with mail._mailbox(GMAIL, "INBOX"):
                pass
        self.assertEqual(login.call_count, 2)

    def test_error_midway_drops_it(self):
        b = box()
        with mock.patch.object(mail, "_imap", return_value=b):
            with self.assertRaises(imaplib.IMAP4.abort):
                with mail._mailbox(PRIVATE, "INBOX"):
                    raise imaplib.IMAP4.abort("eof")
        self.assertIsNone(mail._conn["box"])
        b.logout.assert_called_once()

    def test_busy_server_is_left_alone_for_a_while(self):
        with mock.patch.object(mail, "_imap", side_effect=BUSY) as login:
            for _ in range(3):
                with self.assertRaises(Exception) as ctx:
                    with mail._mailbox(PRIVATE, "INBOX"):
                        pass
        self.assertEqual(login.call_count, 1)
        self.assertEqual(mail._kind(ctx.exception), "busy")
        self.assertIn("seconds", mail._fail("check email", ctx.exception, PRIVATE))

    def test_wrong_password_not_retried_until_the_file_changes(self):
        with mock.patch.object(mail, "_imap", side_effect=[WRONG, box()]) as login:
            for _ in range(2):
                with self.assertRaises(Exception) as ctx:
                    with mail._mailbox(PRIVATE, "INBOX"):
                        pass
            self.assertEqual(login.call_count, 1)
            self.assertIn("minutes", mail._fail("check email", ctx.exception, PRIVATE))
            with mail._mailbox({**PRIVATE, "password": "new"}, "INBOX"):
                pass
        self.assertEqual(login.call_count, 2)

    def test_missing_folder_keeps_the_login(self):
        b = box()
        b.select.return_value = ("NO", [b"no such folder"])
        with mock.patch.object(mail, "_imap", return_value=b):
            with self.assertRaises(mail._NoFolder):
                with mail._mailbox(PRIVATE, "PrivateMail"):
                    pass
        self.assertIs(mail._conn["box"], b)

    def test_check_email_through_it(self):
        b = box()
        b.uid.return_value = ("OK", [b""])
        with mock.patch.object(mail, "account", return_value=dict(PRIVATE)), \
                mock.patch.object(mail, "_imap", return_value=b):
            self.assertEqual(mail._check_email(), "No unread email in INBOX.")
            self.assertEqual(mail._check_email(), "No unread email in INBOX.")
        b.logout.assert_not_called()


if __name__ == "__main__":
    unittest.main()
