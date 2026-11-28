"""plugins/_game.py player_said: what you said in the chat reaches her game turns."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.offline  # noqa: F401,E402

from core import history  # noqa: E402
from plugins import _game  # noqa: E402

NOW = datetime(2026, 11, 28, 20, 0, 0)


def msg(role, text, minutes):
    return {"role": role, "content": text, "timestamp": (NOW - timedelta(minutes=minutes)).isoformat()}


class PlayerSaid(unittest.TestCase):
    def setUp(self):
        _game._said_seen.clear()

    def said(self, msgs):
        with mock.patch.object(history, "get_messages_full", return_value=msgs):
            return _game.player_said(now=NOW)

    def test_your_recent_words_reach_her_turn(self):
        out = self.said([msg("user", "go play zork", 30), msg("assistant", "On it!", 29),
                         msg("user", "forget the leaves, move the rug in the living room", 3),
                         msg("assistant", "Ooh, okay!", 3), msg("user", "then open the trap door", 0.2)])
        self.assertIn('3 min ago: "forget the leaves, move the rug in the living room"', out)
        self.assertIn('just now: "then open the trap door"', out)
        self.assertNotIn("go play zork", out)                 # older than ten minutes
        self.assertNotIn("Ooh", out)                          # only yours
        self.assertLess(out.index("move the rug"), out.index("trap door"))   # oldest first
        self.assertIn("you still decide", out)

    def test_nothing_said_nothing_added(self):
        self.assertEqual(self.said([msg("user", "go play zork", 30)]), "")
        self.assertEqual(self.said([msg("user", "(started the app)", 1)]), "")
        self.assertEqual(self.said([]), "")

    def test_seen_ones_are_marked(self):
        msgs = [msg("user", "move the rug", 2)]
        self.assertNotIn("(seen before)", self.said(msgs))
        self.assertIn('2 min ago (seen before): "move the rug"', self.said(msgs))

    def test_at_most_three(self):
        out = self.said([msg("user", f"tip {i}", 5 - i) for i in range(5)])
        self.assertEqual(out.count("- "), 3)
        self.assertNotIn("tip 0", out)


if __name__ == "__main__":
    unittest.main()
