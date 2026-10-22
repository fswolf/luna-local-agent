"""The tools pane's on/off switch for your own MCP servers (config.json's
mcp.servers): a row at the top of the server's group, and set_server
connecting or disconnecting it and saving the choice. No real server: the
connection is faked and the save is caught.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
import mcpclient  # noqa: E402
from ui import tools_pane  # noqa: E402


class ServerSwitch(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.servers = {"bridge": {"url": "https://example.test/mcp"}}
        self.patches = [mock.patch.object(config, "MCP_SERVERS", self.servers, create=True),
                        mock.patch.object(config, "_store", lambda path, v: self.saved.append((path, v)))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        mcpclient._servers.pop("bridge", None)

    def row(self):
        groups = tools_pane._with_plugin_switches([])
        group = [g for g in groups if g[0] == "MCP: bridge"]
        self.assertEqual(len(group), 1)
        return group[0][1][0]

    def test_row(self):
        label, on, ready, why, _cost, path = self.row()
        self.assertEqual((label, on, ready, path), ("bridge server", True, True, "mcpserver:bridge"))
        self.assertIn("not connected", why)
        self.servers["bridge"]["enabled"] = False
        self.assertFalse(self.row()[1])
        mcpclient._servers["bridge"] = {"session": object()}
        self.assertIn("space disconnects", self.row()[3])

    def test_off_and_on(self):
        with mock.patch.object(mcpclient, "disconnect_server") as off:
            ok, message = mcpclient.set_server("bridge", False)
        off.assert_called_once_with("bridge")
        self.assertTrue(ok)
        self.assertEqual(self.saved, [("mcp.servers.bridge.enabled", False)])
        self.assertIs(self.servers["bridge"]["enabled"], False)

        with mock.patch.object(mcpclient, "connect_server", return_value=(True, "8 tools", [])):
            ok, message = mcpclient.set_server("bridge", True)
        self.assertTrue(ok)
        self.assertIn("8 tools", message)
        self.assertEqual(self.saved[-1], ("mcp.servers.bridge.enabled", True))

    def test_failed_connect_not_saved(self):
        with mock.patch.object(mcpclient, "connect_server", return_value=(False, "refused", [])):
            ok, message = mcpclient.set_server("bridge", True)
        self.assertFalse(ok)
        self.assertEqual(self.saved, [])
        self.assertFalse(mcpclient.set_server("nope", True)[0])


class SmallContext(unittest.TestCase):
    def test_compact(self):
        out = mcpclient._compact('{"messages": [{"id": 1, "to": null, "body": "hi", "mentions": [], "attachments": []}]}')
        self.assertEqual(out, '{"messages":[{"id":1,"body":"hi"}]}')
        self.assertEqual(mcpclient._compact("plain text {"), "plain text {")
        self.assertEqual(mcpclient._compact("{not json"), "{not json")

    def test_limit(self):
        class R:
            content = [type("C", (), {"type": "text", "text": "x" * 3000})()]
        self.assertIn("2000 more characters cut", mcpclient._text_of(R(), 1000))

    def test_prompt_lines(self):
        servers = {"bridge": {"url": "u", "prompt": "Read your   inbox first."}, "other": {"url": "u"}}
        with mock.patch.object(config, "MCP_SERVERS", servers, create=True), \
             mock.patch.object(mcpclient, "connected", lambda n: True):
            with mock.patch.object(mcpclient, "_any_enabled", lambda n: True):
                self.assertEqual(mcpclient.prompt_lines(True), "\nRead your inbox first.\n")
            with mock.patch.object(mcpclient, "_any_enabled", lambda n: False):
                self.assertEqual(mcpclient.prompt_lines(True), "")    # every tool of it switched off
            self.assertEqual(mcpclient.prompt_lines(False), "")       # never in stream chat
        with mock.patch.object(config, "MCP_SERVERS", servers, create=True), \
             mock.patch.object(mcpclient, "connected", lambda n: False):
            self.assertEqual(mcpclient.prompt_lines(True), "")        # not while it's off


class PaneShrinks(unittest.TestCase):
    def test_scroll_clamped(self):
        # a scroll and selection left past the end once the list got shorter
        tools_pane.view.tool_scroll, tools_pane.view.tool_cursor = 10 ** 6, 10 ** 6
        point = tools_pane._tool_cursor_point()
        lines = tools_pane._tool_line_count()
        self.assertLess(point.y, max(1, lines))
        self.assertLess(tools_pane.view.tool_cursor, max(1, len(tools_pane._tool_rows())))


if __name__ == "__main__":
    unittest.main()
