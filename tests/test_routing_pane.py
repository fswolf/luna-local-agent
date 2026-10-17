"""The tools pane's routing line: what the last turn of yours sent, held
back and pulled in, and why a turn went unrouted. A fake tool pool and a
fake embedding answer; no server.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
import turnctx  # noqa: E402
from tools import routing  # noqa: E402

GROUPS = {"get_time": "Time", "calc": "Math", "a1": "Games", "b1": "Chess", "c1": "Email", "d1": "Web"}
POOL = {n: {"spec": {"function": {"name": n, "description": f"{g} tool."}}} for n, g in GROUPS.items()}


def route(scores, track=True, query="what time is it"):
    with mock.patch.object(config, "TOOLS_CORE", ["Time", "Math"]), \
            mock.patch.object(config, "TOOLS_ROUTE_GROUPS", 1), \
            mock.patch.object(config, "TOOLS_STICKY_TURNS", 0), \
            mock.patch.object(routing, "_meaning", return_value=scores):
        with turnctx.begin():
            routing.begin_turn(track=track)
            routing.choose(query, POOL, GROUPS.get, quiet=True)
            return routing


class LastTurn(unittest.TestCase):
    def setUp(self):
        routing._last = {}

    def test_routed(self):
        route({"Games": 0.9, "Chess": 0.1, "Email": 0.2, "Web": 0.3, "Time": 0.5, "Math": 0.1})
        last = routing.last()
        self.assertTrue(last["routed"])
        self.assertEqual(last["core"], {"Time", "Math"})
        self.assertIn("Games", last["sent"])
        self.assertEqual(last["held"], {"Chess", "Email", "Web"})

    def test_pulled_in_mid_turn(self):
        with mock.patch.object(config, "TOOLS_CORE", ["Time", "Math"]), \
                mock.patch.object(config, "TOOLS_ROUTE_GROUPS", 1), \
                mock.patch.object(config, "TOOLS_STICKY_TURNS", 0), \
                mock.patch.object(routing, "_meaning", return_value={"Games": 0.9}):
            with turnctx.begin():
                routing.begin_turn()
                routing.choose("play", POOL, GROUPS.get, quiet=True)
                routing.attach("Chess")
        self.assertIn("Chess", routing.last()["pulled"])
        self.assertNotIn("Chess", routing.last()["held"])

    def test_no_embedding_server(self):
        route(None)
        self.assertEqual(routing.last(), {"routed": False, "why": "server", "sent": set(GROUPS.values())})

    def test_jobs_and_chat_dont_overwrite_yours(self):
        route({"Games": 0.9})
        route(None, track=False)
        self.assertTrue(routing.last()["routed"])


class Pane(unittest.TestCase):
    def setUp(self):
        routing._last = {}
        from ui import tools_pane
        self.pane = tools_pane
        self.patches = [mock.patch("tools.budget", return_value=(1000, 1200)),
                        mock.patch("tools.grouped", return_value=[
                            ("Time", [], 100, 100), ("Math", [], 50, 50), ("Games", [], 300, 300),
                            ("Chess", [], 250, 250), ("Email", [], 200, 200), ("Web", [], 100, 100)])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def header(self):
        return self.pane._tool_header()[0][1]

    def test_header_after_a_routed_turn(self):
        route({"Games": 0.9})
        with mock.patch.object(config, "TOOLS_ROUTING", True):
            self.assertIn("routing on · embedding server up · last turn sent 450 of 1000 tokens", self.header())
            self.assertEqual(self.pane._route_mark("Time"), "always")
            self.assertEqual(self.pane._route_mark("Games"), "sent")
            self.assertEqual(self.pane._route_mark("Email"), "held back")
            self.assertEqual(self.pane._route_mark("Permissions"), "")

    def test_header_without_a_server(self):
        route(None)
        with mock.patch.object(config, "TOOLS_ROUTING", True):
            self.assertIn("no embedding server · every tool sent: 1000 tokens", self.header())
            self.assertEqual(self.pane._route_mark("Games"), "")

    def test_server_gone_since_your_last_turn(self):
        route({"Games": 0.9})
        with mock.patch.object(config, "TOOLS_ROUTING", True), \
                mock.patch.object(routing, "server_up", return_value=False):
            self.assertIn("no embedding server", self.header())
            self.assertEqual(self.pane._route_mark("Games"), "")

    def test_marks_line_up(self):
        route({"Games": 0.9})
        with mock.patch.object(config, "TOOLS_ROUTING", True), \
                mock.patch.object(self.pane, "_tool_groups", return_value=[
                    ("Time", [("get_time", True, True, "", 10, None)], 100, 100),
                    ("Games", [("a1", True, True, "", 10, None)], 300, 400)]):
            lines = "".join(t for _s, t in self.pane._tool_fragments()).splitlines()
        heads = [ln for ln in lines if ln.startswith(" Time") or ln.startswith(" Games")]
        self.assertEqual(heads[0].index("always"), heads[1].index("sent"))

    def test_header_when_switched_off(self):
        route({"Games": 0.9})
        with mock.patch.object(config, "TOOLS_ROUTING", False):
            self.assertIn("routing off · every tool sent", self.header())
            self.assertEqual(self.pane._route_mark("Games"), "")


if __name__ == "__main__":
    unittest.main()
