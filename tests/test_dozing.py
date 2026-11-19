"""She dozes off late at night (life/dozing.py). Nothing real is touched: the
clock, the idle time and presence are faked and the portrait events caught.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from life import coffee, dozing, reading  # noqa: E402


class Dozing(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.idle = 0.0
        self.here = None                    # presence off
        self.hour = 23
        dozing._state.update(on=False, since=0.0, by_hand=False, quiet_from=None, spent=None, away=False,
                             ended=None, startled=False, token=0)
        reading._state.update(on=False, since=0.0, next=0.0, by_hand=False, quiet_from=None, spent=None, away=False, ended=None)
        coffee._state.update(on=False)
        emit = lambda kind, **d: self.events.append((kind, d))
        later = lambda s, fn: fn()          # the timers at once
        self.patches = [
            mock.patch.object(dozing, "_emit", emit),
            mock.patch.object(reading, "_emit", emit),
            mock.patch.object(dozing, "_later", later),
            mock.patch.object(reading.threading, "Timer", lambda s, f: mock.Mock(start=f)),
            mock.patch.object(dozing, "_idle", lambda: self.idle),
            mock.patch.object(dozing, "_present", lambda: self.here),
            mock.patch.object(dozing, "_watching", lambda: True),
            mock.patch.object(dozing, "_busy", lambda: False),
            mock.patch.object(dozing, "_not_now", lambda: False),
            mock.patch.object(dozing, "_walked_away", lambda: False),
            mock.patch.object(dozing, "_coffee", lambda: False),
            mock.patch.object(dozing, "night", lambda hour=None: 22 <= self.hour or self.hour < 6),
            mock.patch.object(config, "PORTRAIT_DOZING", True, create=True),
            mock.patch.object(config, "PORTRAIT_DOZING_AFTER", 20, create=True),
            mock.patch.object(config, "PORTRAIT_DOZING_MINUTES", 90, create=True),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        dozing._state.update(on=False)
        reading._state.update(on=False)

    def kinds(self, kind, key="on", name=None):
        return [d.get(key) for k, d in self.events if k == kind and (name is None or d.get("name") == name)]

    def test_late_and_quiet(self):
        self.idle = 19 * 60
        dozing.tick(now=1000)
        self.assertFalse(dozing.asleep())
        self.idle = 20 * 60
        dozing.tick(now=1060)
        self.assertTrue(dozing.asleep())
        self.assertEqual(self.kinds("prop", name="blanket"), [True])
        self.assertEqual(self.kinds("doze"), [True])
        self.assertIn("sleepy_lean", self.kinds("gesture", "name"))

    def test_not_in_the_day(self):
        self.hour = 15
        self.idle = 3 * 3600
        dozing.tick(now=1000)
        self.assertFalse(dozing.asleep())

    def test_you_wake_her(self):
        self.idle = 1200
        dozing.tick(now=1000)
        self.idle = 5                       # you said something
        dozing.tick(now=1200)
        self.assertFalse(dozing.asleep())
        names = self.kinds("gesture", "name")
        self.assertEqual(names[-2:], ["wake_startle", "stretch"])
        self.assertEqual(self.kinds("doze"), [True, False])
        self.assertEqual(self.kinds("prop", name="blanket"), [True, False])
        self.assertIn("when he woke you", dozing.describe())

    def test_a_blanket_put_on_by_hand_stays(self):
        with mock.patch.object(dozing, "_blanket_on", lambda: True):
            dozing.begin(now=10)
            dozing.wake()
        self.assertEqual(self.kinds("prop", name="blanket"), [])

    def test_wakes_on_her_own(self):
        self.idle = 1200
        dozing.tick(now=1000)
        self.idle = 1200 + 91 * 60
        dozing.tick(now=1000 + 91 * 60)
        self.assertFalse(dozing.asleep())
        self.assertNotIn("wake_startle", self.kinds("gesture", "name"))
        self.assertIn("stretch", self.kinds("gesture", "name"))
        # the same quiet stretch doesn't put her straight back to sleep
        self.idle = 1200 + 92 * 60
        dozing.tick(now=1000 + 92 * 60)
        self.assertFalse(dozing.asleep())

    def test_presence_back(self):
        self.here = False
        self.idle = 1200
        dozing.tick(now=1000)
        self.idle = 1300
        dozing.tick(now=1100)
        self.assertTrue(dozing.asleep())
        self.here = True                    # walked back in, said nothing yet
        dozing.tick(now=1110)
        self.assertFalse(dozing.asleep())

    def test_falls_asleep_over_her_book(self):
        reading._state.update(on=True, since=900, quiet_from=400)
        self.idle = 1200
        dozing.tick(now=1000)
        self.assertTrue(dozing.asleep())
        self.assertFalse(reading.holding())
        self.assertNotIn("book_read_lookup", self.kinds("gesture", "name"))
        self.assertEqual(self.kinds("prop", name="book_open"), [False])

    def test_by_hand_any_hour(self):
        self.hour = 14
        self.assertTrue(dozing.begin(now=50))
        self.assertFalse(dozing.begin(now=60))
        self.assertIn("dozed off", dozing.describe(now=200))
        self.assertTrue(dozing.wake())
        self.assertFalse(dozing.wake())

    def test_woken_before_her_eyes_close(self):
        timers = []
        with mock.patch.object(dozing, "_later", lambda s, fn: timers.append(fn)):
            dozing.begin(now=10)
            dozing.wake()
            for fn in timers:
                fn()
        self.assertEqual(self.kinds("doze"), [False])          # the late "eyes shut" never lands

    def test_night(self):
        with mock.patch.object(config, "PORTRAIT_DOZING_FROM", 22, create=True), \
                mock.patch.object(config, "PORTRAIT_DOZING_TO", 6, create=True):
            self.patches[-4].stop()
            try:
                self.assertTrue(dozing.night(23) and dozing.night(2))
                self.assertFalse(dozing.night(6) or dozing.night(21))
            finally:
                self.patches[-4].start()


class Command(unittest.TestCase):
    def test_doze_command(self):
        from commands import life

        with mock.patch.object(dozing, "begin", return_value=True) as b, mock.patch.object(dozing, "wake", return_value=True) as w, \
                mock.patch("ui.add_message"):
            self.assertTrue(life.handle("/doze"))
            self.assertTrue(life.handle("/doze off"))
        b.assert_called_once_with()
        w.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
