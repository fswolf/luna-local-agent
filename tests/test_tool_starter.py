"""A fresh install's first start switches the rarer tools off (tools.STARTER_OFF),
once; an install that already chose keeps its choice; and a call to a
switched-off tool tells the owner how to switch it on.

    python -m unittest discover tests        (from the repo folder)
"""
import unittest
from unittest import mock

import config
import tools


class Starter(unittest.TestCase):
    def setUp(self):
        self.saved = list(config.TOOLS_DISABLED)
        self.addCleanup(setattr, config, "TOOLS_DISABLED", self.saved)

    def test_fresh_install_gets_the_lean_set(self):
        config.TOOLS_DISABLED = []
        with mock.patch.object(config, "_stored", return_value=None), \
                mock.patch.object(config, "_store") as store:
            self.assertTrue(tools.starter_set())
        store.assert_called_once_with("tools.disabled", sorted(tools.STARTER_OFF))
        self.assertFalse(tools.enabled("run_command"))
        self.assertTrue(tools.enabled("web_search"))
        self.assertTrue(tools.enabled("remember_fact"))

    def test_an_install_that_chose_keeps_it(self):
        config.TOOLS_DISABLED = []
        with mock.patch.object(config, "_stored", return_value=[]), \
                mock.patch.object(config, "_store") as store:
            self.assertFalse(tools.starter_set())
        store.assert_not_called()
        self.assertTrue(tools.enabled("run_command"))

    def test_every_starter_tool_exists(self):
        for name in tools.STARTER_OFF:
            self.assertIn(name, tools._REGISTRY, name)

    def test_the_shipped_config_leaves_the_choice_to_the_first_start(self):
        # config.json starts as a copy of config.example.json: an off-list
        # in there would stop starter_set from ever running
        import json
        import os

        path = os.path.join(config.BASE_DIR, "config.example.json")
        with open(path, encoding="utf-8") as f:
            self.assertNotIn("disabled", json.load(f).get("tools", {}))

    def test_switched_off(self):
        config.TOOLS_DISABLED = ["run_command"]
        self.assertTrue(tools.switched_off("run_command"))
        self.assertFalse(tools.switched_off("web_search"))
        self.assertFalse(tools.switched_off("no_such_tool"))


if __name__ == "__main__":
    unittest.main()
