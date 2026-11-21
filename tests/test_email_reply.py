"""Replying to an email goes back to whoever sent it (tools/mail.py): she
answered a message by mailing the inbox's own address, the To line of the
email she'd read.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from email.message import EmailMessage
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from tools import mail  # noqa: E402

ACCOUNT = {"user": "support@shop.example", "password": "x", "from": "Luna <support@shop.example>",
           "imap_host": "imap", "smtp_host": "smtp", "imap_port": 993, "smtp_port": 465}


def original(sender="Sam <sam@mail.example>", reply_to=None):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, "Shop <support@shop.example>", "Test email"
    m["Message-ID"] = "<abc@mail.example>"
    if reply_to:
        m["Reply-To"] = reply_to
    return m


class Reply(unittest.TestCase):
    def send(self, msg_in, **kwargs):
        sent = []
        server = mock.MagicMock()
        server.__enter__.return_value = server
        server.send_message.side_effect = sent.append
        with mock.patch.object(mail, "account", return_value=dict(ACCOUNT)), \
                mock.patch.object(mail, "_mailbox", return_value=mock.MagicMock()), \
                mock.patch.object(mail, "_fetch", return_value=[("33", msg_in)]), \
                mock.patch.object(mail, "_approve_send", return_value=True), \
                mock.patch.object(mail.smtplib, "SMTP_SSL", return_value=server):
            out = mail._send_email(body="hello", **kwargs)
        return out, sent[0] if sent else None

    def test_back_to_the_sender_not_ourselves(self):
        out, msg = self.send(original(), to="support@shop.example", reply_to="33")
        self.assertEqual(msg["To"], "sam@mail.example")
        self.assertEqual(msg["Subject"], "Re: Test email")
        self.assertEqual(msg["In-Reply-To"], "<abc@mail.example>")

    def test_no_address_given(self):
        _out, msg = self.send(original(), reply_to="33")
        self.assertEqual(msg["To"], "sam@mail.example")

    def test_their_reply_to_wins(self):
        _out, msg = self.send(original(reply_to="desk@mail.example"), reply_to="33")
        self.assertEqual(msg["To"], "desk@mail.example")

    def test_someone_else_named_stays(self):
        _out, msg = self.send(original(), to="boss@mail.example", reply_to="33")
        self.assertEqual(msg["To"], "boss@mail.example")

    def test_registered_as_the_tool(self):
        import inspect
        import tools
        params = inspect.signature(tools._REGISTRY["send_email"]["run"]).parameters
        self.assertEqual(list(params), ["body", "to", "subject", "reply_to"])   # the tool, not a helper

    def test_through_the_tool_call(self):
        import json
        import tools
        with mock.patch.object(mail, "account", side_effect=RuntimeError("no login here")):
            out = tools.call("send_email", json.dumps({"body": "hi", "reply_to": "33"}))
        self.assertNotIn("wrong arguments", out)

    def test_a_new_email_needs_an_address(self):
        out, msg = self.send(original(), to="")
        self.assertIsNone(msg)
        self.assertIn("No valid address", out)


if __name__ == "__main__":
    unittest.main()
