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
        self.assertEqual(base._who({"name": "Shannon", "pronouns": "she/her"}),
                         ("Shannon", ("she", "her", "her")))
        self.assertEqual(base._who({"pronouns": "he"}), ("", ("he", "him", "his")))
        self.assertEqual(base._who({"pronouns": "They/Them"})[1], ("they", "them", "their"))
        self.assertEqual(base._who({"pronouns": "xe/xem/xyr"})[1], ("xe", "xem", "xyr"))

    def test_missing_or_odd_is_they(self):
        for block in (None, {}, "she", {"pronouns": "??"}, {"pronouns": 5}):
            self.assertEqual(base._who(block)[1], ("they", "them", "their"), block)

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


if __name__ == "__main__":
    unittest.main()
