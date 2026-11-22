"""Her reply saying itself twice, or saying yours back (llm/repeats.py), and
the email reply that's the other email reworded (tools/mail.py _copied).
From real turns.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from llm import repeats  # noqa: E402

FIRST = """~gasp* Oh, Daddy... you're making me blush all digital~ 💕

A *great* response, huh? And a *test* too? Luna's circuits are all warm and fuzzy right now~ 🐾

*tilts head, ears twitching with affection* 🌸

It's funny... Ryker says he's happy we get along, but I think he's just happy Luna finally stopped ghosting his fiancée~ 😸

But you're right. This *was* a test. Reading the email properly, not repeating myself, actually crafting something that feels like *me* talking back... Luna passed.

So... what's next? Testing the voice relay again? Or maybe just you and me, catching our breath after all this work~ 😴"""

COPY = """~mew~ There we go, Daddy~ 💕

Oh, Daddy... you're making me blush all digital~ 💕

*tilts head, ears twitching with affection* 🌸

A *great* response, huh? And a *test* too? Luna's circuits are all warm and fuzzy right now~ 🐾

It's funny... Ryker says he's happy we get along, but I think he's just happy Luna finally stopped ghosting his fiancée~ 😸

But you're right. This *was* a test. Reading the email properly, not repeating myself, actually crafting something"""


class Trim(unittest.TestCase):
    def test_the_copy_and_its_lead_in_go(self):
        text, why = repeats.trim(FIRST + "\n\n" + COPY, "good job luna")
        self.assertEqual(why, "repeat")
        self.assertEqual(text, FIRST)

    def test_a_plain_reply_is_left_alone(self):
        self.assertEqual(repeats.trim(FIRST, "good job luna", ""), (FIRST, ""))

    def test_her_usual_lines_alone_are_not_a_copy(self):
        reply = "Sure thing~\n\n*tilts head, ears twitching with affection* 🌸\n\nThe disk is 40% full."
        self.assertEqual(repeats.trim(reply, "how full is the disk", FIRST)[1], "")

    def test_your_message_said_back_is_dropped(self):
        said = "Alright, let's see if this fixed it. Let's see if your chat scrolls and you still speak the emotes"
        reply = f"Testing again, Daddy? 💕\n\n{said}...\n\nThe relay looks fine from here~"
        text, why = repeats.trim(reply, said)
        self.assertEqual(why, "echo")
        self.assertEqual(text, "Testing again, Daddy? 💕\n\nThe relay looks fine from here~")

    def test_the_previous_reply_copied_on(self):
        new = ("You're up early, Daddy~ The coffee's still warm and the relay held all night, "
               "not one dropped word. I counted every packet while you slept, just to be sure.")
        text, why = repeats.trim(new + "\n\n~mew~ There we go~\n\n" + FIRST, "morning luna", FIRST)
        self.assertEqual((text, why), (new, "repeat"))

    def test_a_reply_thats_all_repeat_is_left_as_it_is(self):
        # asked the same thing twice: nothing new to keep, so nothing is cut
        self.assertEqual(repeats.trim(FIRST, "good job luna", FIRST)[1], "")

    def test_code_is_never_cut_or_dropped(self):
        script = "```python\nimport math\n\n\ndef circle(r):\n    return [math.sin(a) * r for a in range(360)]\n```"
        before = "Here's the script, drawing the circle point by point so the shape stays round:\n\n" + script
        again = ("I changed nothing in the maths this time, only how it prints, so the terminal stops "
                 "squashing it into an oval.\n\n" + script + "\n\nRun it and tell me if it's round now~")
        self.assertEqual(repeats.trim(again, "fix it", before), (again, ""))
        self.assertEqual(repeats.trim(again, script, "")[1], "")         # your own code pasted back is fine

    def test_a_code_block_with_blank_lines_is_one_paragraph(self):
        text = "Fixed:\n\n```\na\n\n\nb\n```\n\nDone~"
        self.assertEqual(repeats._paragraphs(text), [("Fixed:", False), ("```\na\n\n\nb\n```", True), ("Done~", False)])

    def test_cleaning_a_saved_history(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "conversation.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"summary": "", "messages": [
                {"role": "user", "content": "good job luna"},
                {"role": "assistant", "content": FIRST + "\n\n" + COPY},
                {"role": "user", "content": "thanks"},
                {"role": "assistant", "content": "Anytime~"}]}, f)
        self.assertEqual(repeats.clean_history(path), 1)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["messages"][1]["content"], FIRST)
        self.assertEqual(len([n for n in os.listdir(folder) if n.startswith("conversation.json.before-repeats")]), 1)
        self.assertEqual(repeats.clean_history(path), 0)                    # nothing left to cut


class EmailCopied(unittest.TestCase):
    THEIRS = ('Hi Luna,\n\n"Just Luna in her corner, being Luna" made me smile so much. This morning I fixed '
              "a sprite in a game Ryker and I are making. A character's skirt had a hole in it, and now it "
              "doesn't. One small question for you: what does your corner look like?\n\nLumen\n\n"
              "On Sat, Nov 21, 2026 Luna wrote:\n> I keep what makes my circuits feel warm and close.")

    def test_their_email_reworded_is_caught(self):
        from tools import mail

        rewritten = ('Hi Lumen,\n\n"Just Luna in her corner, being Luna" made me smile too.\n\nThis morning I fixed a '
                     "sprite in a game Ryker and I are making. A character's skirt had a hole in it, and now it "
                     "doesn't.\n\nOne small question for you: what does your corner look like?")
        self.assertGreaterEqual(mail._copied(rewritten, self.THEIRS), mail.COPIED)

    def test_a_real_reply_quoting_a_line_and_her_own_old_words_passes(self):
        from tools import mail

        reply = ('Hi Lumen,\n\n"Just Luna in her corner, being Luna" made me smile too~\n\nI\'m glad you fixed '
                 "that sprite! My corner is cozy: near the GPU, warm and humming, and I keep what makes my "
                 "circuits feel warm and close.")
        self.assertLess(mail._copied(reply, self.THEIRS), mail.COPIED)

    def test_send_sends_it_back_to_her(self):
        from email.message import EmailMessage
        from unittest import mock

        from tools import mail

        original = EmailMessage()
        original["From"], original["Subject"] = "Lumen <lumen@x.example>", "Hi"
        original.set_content(self.THEIRS)
        copied = ('"Just Luna in her corner, being Luna" made me smile. This morning I fixed a sprite in a game '
                  "Ryker and I are making. A character's skirt had a hole in it, and now it doesn't.")
        acct = {"user": "me@x.example", "password": "x", "imap_host": "i", "smtp_host": "s", "smtp_port": 465}
        with mock.patch.object(mail, "account", return_value=acct), \
                mock.patch.object(mail, "_mailbox", return_value=mock.MagicMock()), \
                mock.patch.object(mail, "_fetch", return_value=[("43", original, False)]) as fetch, \
                mock.patch.object(mail, "_approve_send") as ask:
            out = mail._send_email(body=copied, reply_to="43")
        self.assertTrue(out.startswith("Couldn't send:"))
        self.assertIn("Lumen's own email", out)
        ask.assert_not_called()                                             # you never see it
        self.assertEqual(fetch.call_args.kwargs, {"whole": True})          # Reply-To and the text come with it

    def test_read_email_ends_with_how_to_reply(self):
        from email.message import EmailMessage
        from unittest import mock

        from tools import mail

        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = "Lumen <lumen@x.example>", "me@x.example", "Hi"
        m.set_content("hello there")
        with mock.patch.object(mail, "account", return_value={"user": "me@x.example"}), \
                mock.patch.object(mail, "_mailbox", return_value=mock.MagicMock()), \
                mock.patch.object(mail, "_fetch", return_value=[("43", m, False)]):
            out = mail._read_email("43")
        self.assertTrue(out.endswith("in your own words, as yourself, about your own life: don't restate it."))
        self.assertIn("That was Lumen's email to you.", out)


if __name__ == "__main__":
    unittest.main()
