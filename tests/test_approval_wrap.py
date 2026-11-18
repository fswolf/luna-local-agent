"""The permission window wraps long lines (ui/approval.py): an email's
paragraph is one long line, and it ran off the right edge.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

from ui import approval  # noqa: E402
from ui.text import vwidth  # noqa: E402


class Wrap(unittest.TestCase):
    def test_a_paragraph_wraps_on_words(self):
        text = "You're testing my email system again, aren't you? How predictable... and yet, I love it 🌸"
        lines = approval._wrap(text, 30)
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(vwidth(l) <= 30 for l in lines), lines)
        self.assertEqual(" ".join(lines).split(), text.split())       # nothing lost

    def test_a_line_that_fits_is_untouched(self):
        self.assertEqual(approval._wrap("    keep   my   spacing", 40), ["    keep   my   spacing"])

    def test_continuations_keep_the_indent(self):
        lines = approval._wrap("    return one(two, three, four, five, six, seven, eight)", 30)
        self.assertTrue(all(l.startswith("    ") for l in lines), lines)

    def test_a_long_url_is_cut(self):
        lines = approval._wrap("see https://example.com/" + "x" * 60, 30)
        self.assertTrue(all(vwidth(l) <= 30 for l in lines), lines)

    def test_scrolling_counts_the_wrapped_lines(self):
        request = {"title": "t", "note": "", "body": ["word " * 40]}
        with mock.patch.object(approval.view, "approval", request), \
                mock.patch.object(approval, "_body_width", return_value=40):
            self.assertGreater(approval._approval_lines(), 1)
            styles = {style for style, _text in approval._approval_body()}
        self.assertEqual(styles, {"class:text"})

    def test_a_wrapped_diff_line_keeps_its_colour(self):
        request = {"title": "t", "note": "", "body": ["+" + "added words " * 10]}
        with mock.patch.object(approval.view, "approval", request), \
                mock.patch.object(approval, "_body_width", return_value=30):
            styles = [style for style, _text in approval._approval_body()]
        self.assertGreater(len(styles), 1)
        self.assertEqual(set(styles), {"class:diff.add"})


if __name__ == "__main__":
    unittest.main()
