"""The tools pane's switches (ui/tools_pane.py): space on a tool held back
by a setting (send_email and email.send, read_page and web_search.fetch_pages
...) switches the setting with it (_GATES), and a plugin that brings tools
has its own switch in their group.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: F401,E402  (first: no real servers)

import config  # noqa: E402
import tools  # noqa: E402
from ui import tools_pane as pane  # noqa: E402


class SendToggle(unittest.TestCase):
    def setUp(self):
        self.state = {"EMAIL_SEND": False, "login": True, "enabled": True}
        self.said = []

        def save(path, raw):
            self.assertEqual(path, "email.send")
            self.state["EMAIL_SEND"] = raw == "true"
            return raw == "true", True

        def rows():
            ready = self.state["login"] and self.state["EMAIL_SEND"]
            why = "sending is off" if self.state["login"] else "no login in email.json"
            return [("send_email", self.state["enabled"], ready, "" if ready else why, 195, None)]

        for target, value in (
                (config, {"save_setting": mock.Mock(side_effect=save)}),
                (tools, {"set_enabled": mock.Mock(side_effect=lambda n, on: self.state.update(enabled=on))}),
                (pane, {"_tool_rows": rows, "add_message": lambda who, text: self.said.append(text),
                        "_refresh": lambda: None})):
            for name, fake in value.items():
                patcher = mock.patch.object(target, name, fake)
                patcher.start()
                self.addCleanup(patcher.stop)
        gate = mock.patch.object(config, "EMAIL_SEND", False, create=True)
        gate.start()
        self.addCleanup(gate.stop)
        config.save_setting.side_effect = lambda path, raw: (save(path, raw),
                                                             setattr(config, "EMAIL_SEND", raw == "true"))[0]
        pane.view.tool_cursor = 0

    def test_space_switches_sending_on(self):
        pane._tool_toggle()
        self.assertTrue(self.state["EMAIL_SEND"])
        self.assertIn("still asks you first", self.said[-1])

    def test_and_off_again(self):
        pane._tool_toggle()
        pane._tool_toggle()
        self.assertFalse(self.state["EMAIL_SEND"])
        self.assertFalse(self.state["enabled"])

    def test_no_login_stays_off(self):
        self.state["login"] = False
        pane._tool_toggle()
        self.assertFalse(self.state["EMAIL_SEND"])          # put back: the switch wasn't what was missing
        self.assertIn("no login", self.said[-1])


class Gates(unittest.TestCase):
    def test_every_gate_is_a_real_tool_and_a_live_setting(self):
        for name, gate in pane._GATES.items():
            self.assertIn(name, tools._REGISTRY, name)
            self.assertIn(gate, config.SETTINGS, gate)
            self.assertTrue(config.SETTINGS[gate][1], f"{gate} needs a restart")

    def test_off_keeps_a_setting_others_use(self):
        said, saved = [], []
        rows = [("read_page", True, True, "", 10, None), ("research", True, True, "", 10, None)]
        with mock.patch.object(pane, "_tool_rows", return_value=rows), \
                mock.patch.object(pane, "add_message", lambda who, text: said.append(text)), \
                mock.patch.object(tools, "set_enabled"), \
                mock.patch.object(config, "save_setting", side_effect=lambda *a: saved.append(a)):
            self.assertTrue(pane._gate_toggle("read_page", True, True))
        self.assertEqual(saved, [])
        self.assertIn("stays on for research", said[-1])


class PluginRows(unittest.TestCase):
    def test_a_plugin_with_tools_gets_a_switch_in_their_group(self):
        import plugins
        plugins.load()
        rows = {(label, m[0]): m for label, members, _l, _t in pane._tool_groups() for m in members}
        row = rows.get(("Offline library", "kiwix plugin"))
        self.assertIsNotNone(row)
        self.assertEqual(row[5], "plugin:kiwix")


if __name__ == "__main__":
    unittest.main()
