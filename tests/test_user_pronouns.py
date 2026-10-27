"""The "user" block in agent.json: her prompts say he, she or they, and
the user's name, instead of assuming Ryan."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.offline  # noqa: F401,E402

import config  # noqa: E402
from config import base  # noqa: E402


class Who(unittest.TestCase):
    def test_pronoun_words(self):
        self.assertEqual(base._who({"name": "Shannon", "pronouns": "she/her"})[:2],
                         ("Shannon", ("she", "her", "her")))
        self.assertEqual(base._who({"pronouns": "he"}), ("", ("he", "him", "his"), True))
        self.assertEqual(base._who({"pronouns": "They/Them"})[1], ("they", "them", "their"))
        self.assertEqual(base._who({"pronouns": "xe/xem/xyr"})[1], ("xe", "xem", "xyr"))

    def test_missing_or_odd_is_he(self):
        for block in (None, {}, "she", {"pronouns": "??"}, {"pronouns": 5}):
            self.assertEqual(base._who(block)[1], ("he", "him", "his"), block)
            self.assertFalse(base._who(block)[2], block)      # not stated to her as theirs

    def test_name_is_tidied(self):
        self.assertEqual(base._who({"name": "  Shan \n non "})[0], "Shan non")
        self.assertEqual(len(base._who({"name": "x" * 99})[0]), 40)


class Prompts(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(config, k) for k in ("USER", "USER_NAME", "USER_THEY", "USER_THEM", "USER_THEIR")}
        for k, v in dict(USER="Shannon", USER_NAME="Shannon", USER_THEY="she",
                         USER_THEM="her", USER_THEIR="her").items():
            setattr(config, k, v)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(config, k, v)

    def test_toy_line(self):
        from plugins import _toys

        line = _toys.prompt_line("Lush 3", "lovense_vibrate")
        self.assertIn("when Shannon asks", line)
        self.assertIn("call the tool", line)
        self.assertNotRegex(line, r"\b(he|him|his)\b")

    def test_user_line(self):
        saved = (base.USER_NAME, base._USER_GAVE_PRONOUNS)
        try:
            base.USER_NAME, base._USER_GAVE_PRONOUNS = "Shannon", True
            base.USER_THEY, base.USER_THEM, base.USER_THEIR = "she", "her", "her"
            self.assertEqual(config.user_line(), "You're talking with Shannon (she/her/her).\n")
            base._USER_GAVE_PRONOUNS = False        # a name alone: no pronouns claimed for her
            self.assertEqual(config.user_line(), "You're talking with Shannon.\n")
            base.USER_NAME = ""
            self.assertEqual(config.user_line(), "")
        finally:
            base.USER_NAME, base._USER_GAVE_PRONOUNS = saved
            base.USER_THEY, base.USER_THEM, base.USER_THEIR = (self.saved["USER_THEY"], self.saved["USER_THEM"],
                                                                self.saved["USER_THEIR"])



class FullBodyGestures(unittest.TestCase):
    """A gesture marked full: true (her legs) is only offered to her while
    the portrait shows all of her."""

    def setUp(self):
        from life import gestures

        self.g = gestures
        self.saved = (config.PORTRAIT_FRAME, dict(gestures._files))
        gestures._files.update(at=1e18, found={
            "wave": {"about": "hello", "private": False, "left": True, "full": False},
            "knee_lift": {"about": "ticklish", "private": False, "left": True, "full": True}})

    def tearDown(self):
        config.PORTRAIT_FRAME = self.saved[0]
        self.g._files.clear()
        self.g._files.update(self.saved[1])

    def offered(self):
        from unittest import mock

        with mock.patch.object(self.g, "mode", return_value="tags"), \
             mock.patch.object(self.g, "_three_d", return_value=True), \
             mock.patch.object(self.g, "clips", return_value=[]):
            return self.g.prompt_line(), set(self.g._prototypes())

    def test_only_in_full_body(self):
        config.PORTRAIT_FRAME = "bust"
        line, protos = self.offered()
        self.assertIn("[wave]", line)
        self.assertNotIn("knee_lift", line)
        self.assertNotIn("knee_lift", protos)
        config.PORTRAIT_FRAME = "full"
        line, protos = self.offered()
        self.assertIn("[knee_lift]", line)
        self.assertIn("knee_lift", protos)


if __name__ == "__main__":
    unittest.main()
