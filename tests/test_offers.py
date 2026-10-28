"""Offers (life/offers.py): things she notices on her own and offers, once,
on your next turn. Watchers are faked; the notebook is a dict.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from core import turnctx  # noqa: E402
from life import offers  # noqa: E402

DISK = {"key": "disk:home", "kind": "machine", "cooldown": 12 * 3600, "text": "the home disk is nearly full."}
BDAY = {"key": "date:abc:2026-11-03", "kind": "date", "cooldown": 24 * 3600, "text": 'you remember "x".'}


class Offers(unittest.TestCase):
    def setUp(self):
        self.book = {}
        self.patches = [
            mock.patch("mind.notebook.get", lambda k, d=None: self.book.get(k, d)),
            mock.patch("mind.notebook.put", lambda k, v: self.book.__setitem__(k, v)),
            mock.patch.object(offers, "_scan_soon", lambda: None),
            mock.patch.object(offers, "settings", lambda: dict(offers.DEFAULTS)),
            mock.patch("mind.mood.walkaway.away", lambda: False),
            mock.patch("mind.mood.heavy.level", lambda now=None: 0),
        ]
        for p in self.patches:
            p.start()
        offers._found[:] = [DISK, BDAY]

    def tearDown(self):
        for p in self.patches:
            p.stop()
        offers._found[:] = []

    def turn(self, **kw):
        kw.setdefault("source", "typed")
        with turnctx.begin(**kw):
            first = offers.line()
            self.assertEqual(offers.line(), first)          # the prompt built again: same offer
            return first

    def test_one_offer_on_your_turn(self):
        line = self.turn()
        self.assertIn("home disk is nearly full", line)
        self.assertIn("Do it only if they say yes", line)

    def test_not_for_anyone_else(self):
        for kw in ({"source": "greeting"}, {"source": "reminder"}, {"speaker": "mike"}, {"private": False},
                   {"source": "job:x", "job": "x"}, {"remote": "discord"}):
            self.assertEqual(self.turn(**kw), "", kw)
        self.assertEqual(self.book, {})                     # nothing was marked asked

    def test_held_back_in_a_heavy_moment_or_the_lewd_row(self):
        with mock.patch("mind.mood.heavy.level", lambda now=None: 2):
            self.assertEqual(self.turn(), "")
        with mock.patch("mind.mood.core.S.label", "heated"):
            self.assertEqual(self.turn(), "")

    def test_gap_and_daily_limit(self):
        self.assertIn("disk", self.turn())
        self.assertEqual(self.turn(), "")                   # two hours apart
        st = self.book["offers"]
        st["last"] = 0
        self.assertIn("remember", self.turn())              # the disk waits its cooldown; the date is next
        st["last"], st["count"] = 0, 3
        self.assertEqual(self.turn(), "")                   # three a day

    def test_dont_ask_again(self):
        self.turn()
        self.assertTrue(offers.recently_offered())
        self.assertEqual(offers.stop(), "disk:home")
        self.book["offers"]["last"] = 0
        self.book["offers"]["asked"] = {}
        self.assertNotIn("disk", self.turn())               # muted for good
        self.assertEqual(offers.unmute_all(), 1)

    def test_a_broken_notebook_never_breaks_a_turn(self):
        with mock.patch("mind.notebook.get", side_effect=OSError("disk gone")):
            self.assertEqual(self.turn(), "")

    def test_muting_a_date_mutes_it_every_year(self):
        offers._found[:] = [BDAY]
        self.turn()
        self.assertEqual(offers.stop(), "date:abc")
        self.book["offers"]["last"] = 0
        offers._found[:] = [dict(BDAY, key="date:abc:2027-11-03")]
        self.assertEqual(self.turn(), "")

    def test_a_disk_that_stays_full_comes_up_less(self):
        offers._found[:] = [DISK]
        self.book["offers"] = {"asked": {"disk:home": [0.0, 3]}, "muted": [], "day": "", "count": 0, "last": 0.0}
        with mock.patch("time.time", return_value=13 * 3600.0):
            self.assertEqual(self.turn(), "")               # past twelve hours, but it's been raised 3 times
        with mock.patch("time.time", return_value=73 * 3600.0):
            self.assertIn("disk", self.turn())

    def test_a_failed_scan_still_finishes(self):
        offers._scan["running"] = True
        with mock.patch.object(offers, "settings", side_effect=RuntimeError("bad config")):
            with self.assertRaises(RuntimeError):
                offers.scan()
        self.assertFalse(offers._scan["running"])          # the next turn can scan again

    def test_a_date_twice_at_most(self):
        offers._found[:] = [BDAY]
        for _ in range(2):
            self.assertIn("remember", self.turn())
            self.book["offers"]["last"] = 0
            self.book["offers"]["asked"][BDAY["key"]][0] = 0
        self.assertEqual(self.turn(), "")


class Dates(unittest.TestCase):
    TODAY = date(2026, 10, 27)

    def test_reading_dates(self):
        cases = {"Shannon's birthday is March 3": date(2027, 3, 3),
                 "the car is in for service on November 4th": date(2026, 11, 4),
                 "renew the domain by 2026-11-30": date(2026, 11, 30),
                 "started the job on 2019-05-01": None,          # a full date in the past is a record
                 "our anniversary is the 2nd of Nov": date(2026, 11, 2),
                 "flight on Oct 30, 2026": date(2026, 10, 30),
                 "concert on Oct 1, 2026": None,                 # passed, with a year: gone
                 "born May 3, 1990": date(2027, 5, 3),           # a year long gone: every year
                 "lives in Hamar 3 days a week": None,           # not a month inside a word
                 "likes coffee black": None,
                 "may be late on fridays": None}
        for text, want in cases.items():
            self.assertEqual(offers.date_in(text, self.TODAY), want, text)

    def test_watch_dates(self):
        facts = ["Shannon's birthday is November 2", "likes cats", "the dentist is on October 28",
                 "the server arrives on December 25"]
        with mock.patch("mind.factstore.available", lambda: True), \
             mock.patch("mind.factstore.active_facts", lambda: facts), \
             mock.patch("life.reminders.pending", lambda: [{"due_at": "2026-10-28T09:00:00"}]), \
             mock.patch.object(offers, "settings", lambda: dict(offers.DEFAULTS)):
            found = offers.watch_dates(self.TODAY)
        self.assertEqual(len(found), 1)                     # the dentist has a reminder; Dec 25 is too far
        self.assertIn("in 6 days", found[0]["text"])
        self.assertIn("Monday November 2", found[0]["text"])


if __name__ == "__main__":
    unittest.main()
