"""She reads while you're quiet (life/reading.py). Nothing real is touched: the
clock, the idle time and presence are faked and the portrait events caught.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from life import coffee  # noqa: E402
import config  # noqa: E402
from life import reading  # noqa: E402


class Reading(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.idle = 0.0
        self.here = None                    # presence off
        reading._state.update(on=False, since=0.0, next=0.0, by_hand=False, quiet_from=None, spent=None, away=False, ended=None)
        coffee._state.update(on=False)
        emit = lambda kind, **d: self.events.append((kind, d))
        self.patches = [
            mock.patch.object(reading, "_emit", emit),
            mock.patch.object(coffee, "_emit", emit),
            mock.patch.object(reading, "_idle", lambda: self.idle),
            mock.patch.object(reading, "_present", lambda: self.here),
            mock.patch.object(reading, "_watching", lambda: True),
            mock.patch.object(reading, "_busy", lambda: False),
            mock.patch.object(reading, "_not_now", lambda: False),
            mock.patch.object(reading, "_walked_away", lambda: False),
            mock.patch.object(coffee, "_walked_away", lambda: False),
            mock.patch.object(reading.threading, "Timer", lambda s, f: mock.Mock(start=f)),   # the put-down at once
            mock.patch.object(config, "PORTRAIT_READING_AFTER", 10, create=True),
            mock.patch.object(config, "PORTRAIT_READING_MINUTES", 60, create=True),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        reading._state.update(on=False)
        coffee._state.update(on=False)

    def props(self):
        return [d["on"] for k, d in self.events if k == "prop" and d["name"] == "book_open"]

    def test_waits_for_quiet(self):
        self.idle = 9 * 60
        reading.tick(now=1000)
        self.assertFalse(reading.holding())
        self.idle = 10 * 60
        reading.tick(now=1060)
        self.assertTrue(reading.holding())
        self.assertEqual(self.props(), [True])

    def test_pages_then_back(self):
        self.idle = 600
        reading.tick(now=1000)
        self.idle = 700
        reading.tick(now=1100)                       # past the first page time (35-80 s)
        self.assertTrue(any(d.get("name") in ("book_read_turn", "book_read_lookup") for k, d in self.events if k == "gesture"))
        self.idle = 5                                # you said something
        reading.tick(now=1110)
        self.assertFalse(reading.holding())
        self.assertIn(("gesture", {"name": "book_read_lookup", "src": "reading"}), self.events)
        self.assertEqual(self.props(), [True, False])

    def test_one_stretch_one_book(self):
        self.idle = 600
        reading.tick(now=1000)
        with mock.patch.object(config, "PORTRAIT_READING_MINUTES", 1, create=True):
            self.idle = 661
            reading.tick(now=1061)                   # read her minute: down
        self.assertFalse(reading.holding())
        self.idle = 900
        reading.tick(now=1300)                       # still the same quiet stretch: not again
        self.assertFalse(reading.holding())
        self.idle = 600                              # you talked at 1400, quiet since
        reading.tick(now=2000)
        self.assertTrue(reading.holding())

    def test_presence_back(self):
        self.idle, self.here = 600, False            # you're away
        reading.tick(now=1000)
        self.idle = 700
        reading.tick(now=1100)
        self.assertTrue(reading.holding())
        self.here = True                             # walked back in, haven't said anything
        self.idle = 710
        reading.tick(now=1110)
        self.assertFalse(reading.holding())

    def test_mood_and_coffee(self):
        self.idle = 600
        with mock.patch.object(reading, "_not_now", lambda: True):
            reading.tick(now=1000)
        self.assertFalse(reading.holding())
        coffee._state["on"] = True
        reading.tick(now=1000)
        self.assertFalse(reading.holding())          # not with her coffee
        coffee._state["on"] = False
        reading.tick(now=1000)
        self.assertTrue(reading.holding())
        with mock.patch.object(reading, "_not_now", lambda: True):
            reading.tick(now=1010)                   # into the lewd row: down
        self.assertFalse(reading.holding())

    def test_by_hand_and_coffee_swap(self):
        self.assertTrue(reading.begin(now=0))
        self.assertFalse(reading.begin(now=1))
        with mock.patch.object(coffee, "_mark_today", lambda: None):
            self.assertTrue(coffee.begin(now=2))     # /coffee while reading: the book goes down
        self.assertFalse(reading.holding())
        self.assertTrue(reading.begin(now=3))        # /read with coffee: the mug goes down
        self.assertFalse(coffee.holding())
        self.assertFalse(reading.page(lookup=False) is False)
        self.assertTrue(reading.finish())
        self.assertFalse(reading.finish())

    def test_quick_reread_keeps_the_book(self):
        timers = []
        with mock.patch.object(reading.threading, "Timer", lambda s, f: timers.append(f) or mock.Mock()):
            reading.begin(now=0)
            reading.finish()                         # look up, put-down in 2.6 s...
            reading.begin(now=1)                     # ...but /read again first
            timers[0]()
        self.assertTrue(reading.holding())
        self.assertEqual(self.props(), [True, True])  # no put-down under her

    def test_walked_away(self):
        self.idle = 1000                             # nobody's said anything
        reading.begin(now=0)                         # /read: stays through a mood change...
        with mock.patch.object(reading, "_not_now", lambda: True):
            reading.tick(now=5)
        self.assertTrue(reading.holding())
        with mock.patch.object(reading, "_walked_away", lambda: True):
            reading.tick(now=10)                     # ...but not through her walking off
        self.assertFalse(reading.holding())
        with mock.patch.object(coffee, "_mark_today", lambda: None):
            coffee.begin(now=0)
        with mock.patch.object(coffee, "_walked_away", lambda: True):
            coffee.tick(now=10)
        self.assertFalse(coffee.holding())

    def test_she_knows(self):
        from mind import situation

        self.assertEqual(reading.describe(now=0), "")
        reading.begin(now=0)
        line = reading.describe(now=300)
        self.assertIn("The Moonlit Library", line)
        self.assertIn("5 minutes", line)
        reading.finish()
        self.assertIn("put it down when he came back", reading.describe())
        self.assertIn("Moonlit Library", situation._hands())
        self.assertEqual(reading.describe(now=reading._state["ended"] + reading.RECENT + 1), "")
        with mock.patch.object(coffee, "_mark_today", lambda: None):
            coffee.begin(now=0)
        self.assertIn("coffee", situation._hands())


class Snapshot(unittest.TestCase):
    def test_one_per_prop(self):
        from web import livefeed

        with mock.patch.dict(livefeed._snapshot, clear=True):
            livefeed.emit("prop", name="mug", on=False)
            livefeed.emit("prop", name="book_open", on=False)
            livefeed.emit("prop", name="book_open", on=True)
            kept = {k: v["on"] for k, v in livefeed._snapshot.items() if k.startswith("prop:")}
        self.assertEqual(kept, {"prop:mug": False, "prop:book_open": True})


if __name__ == "__main__":
    unittest.main()
