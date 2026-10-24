"""Bracketed stage directions become *actions* (replystyle.tidy), and
nothing else changes.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import replystyle  # noqa: E402

CASES = [
    ("Alright, Senpai~:(bounces lightly) ...Got it~", "Alright, Senpai~ *bounces lightly* ...Got it~"),
    ("down about $36.70 today~:(winks)", "down about $36.70 today~ *winks*"),
    ("Steve~?~:(giggles softly, eyes narrowing playfully) ...", "Steve~?~ *giggles softly, eyes narrowing playfully* ..."),
    ("distract myself~?:(giggles softly, tail swaying)", "distract myself~? *giggles softly, tail swaying*"),
    ("Fine.(sighs) ok", "Fine.*sighs* ok"),
    ("(bends forward, looking back)", "*bends forward, looking back*"),
]
UNTOUCHED = [
    "**$4,139.80 per troy ounce** (as of Oct 3, 2026) - down",
    "check (the KITCO page) first",
    "I use it (sometimes) a lot",
    "see (https://example.com/a)",
    "print(items) and f(x)",
    "```\nfoo (runs fast)\n```",
    "use `x (runs)` here",
    "*giggles* fine",
]


class Tidy(unittest.TestCase):
    def test_actions_in_brackets(self):
        for before, after in CASES:
            self.assertEqual(replystyle.tidy(before), after, before)

    def test_everything_else_stays(self):
        for text in UNTOUCHED:
            self.assertEqual(replystyle.tidy(text), text, text)

    def test_same_length_so_streaming_never_jumps(self):
        for before, _after in CASES:
            self.assertEqual(len(replystyle.tidy(before)), len(before))

    def test_half_written_aside_waits(self):
        self.assertEqual(replystyle.tidy("Senpai~:(bounces li"), "Senpai~:(bounces li")


if __name__ == "__main__":
    unittest.main()
