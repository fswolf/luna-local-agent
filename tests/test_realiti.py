"""REALITI turns: one action per turn, and a refusal she can understand
and doesn't pay for. No world, no Node: a fake tool stands in.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import tools  # noqa: E402
from plugins import realiti  # noqa: E402

NO_ROOM = 'Error from realiti: {"ok":false,"error":"ROOM_OUTSIDE_SLICE"}'


class Turn(unittest.TestCase):
    def setUp(self):
        self.replies = []
        name = "realiti__realiti_go"

        def go(**kw):
            return self.replies.pop(0)

        self.patches = [mock.patch.dict(tools._REGISTRY, {name: {"run": go}}),
                        mock.patch.dict(realiti._state, tools=[name]),
                        mock.patch.object(realiti._transcript, "write")]
        for p in self.patches:
            p.start()
        realiti._watch_tools()
        self.go = tools._REGISTRY[name]["run"]
        realiti._turn.update(active=True, acted=False, did=[], lines=[])

    def tearDown(self):
        realiti._turn.update(active=False, acted=False, did=[], lines=[])
        for p in self.patches:
            p.stop()

    def test_a_refusal_comes_with_what_it_means(self):
        self.replies = [NO_ROOM]
        reply = self.go(place="through__cloud_nine_nest.to.no_ask_sanctuary")
        self.assertIn("realiti_rooms lists them", reply)
        self.assertIn("realiti_rooms lists them", realiti._turn["lines"][-1])   # and next turn sees it

    def test_a_refusal_doesnt_use_up_her_one_thing(self):
        self.replies = [NO_ROOM, '{"ok":true}']
        self.go(place="through__x")
        self.assertNotEqual(self.go(place="No-Ask Sanctuary"), realiti.ONE_THING)
        self.replies = ['{"ok":true}']
        self.assertEqual(self.go(place="Kite Field"), realiti.ONE_THING)     # but a real one does

    def test_unknown_codes_and_plain_errors_pass_through(self):
        self.assertEqual(realiti._refusal_code('Error from realiti: {"error":"NEW_THING"}'), "NEW_THING")
        self.assertIsNone(realiti._refusal_code("Error from realiti: boom"))
        self.assertIsNone(realiti._refusal_code('{"ok":true}'))
        self.assertEqual(realiti._refusal("Error from realiti: boom", "Error from realiti: boom"),
                         "the world said no: boom")


if __name__ == "__main__":
    unittest.main()
