"""The config package: every setting on one namespace, and /set changing
the value everyone reads. Writes go to a temporary config.json; yours is
never touched.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402


class Namespace(unittest.TestCase):
    def test_base_dir_is_the_repo(self):
        self.assertTrue(os.path.isdir(os.path.join(config.BASE_DIR, "config")))
        self.assertEqual(config.CONFIG_FILE, os.path.join(config.BASE_DIR, "config.json"))

    def test_no_section_is_named_like_a_setting(self):
        # Importing config.voice (a module) would replace a setting called
        # config.voice: that happened once, in the ui package.
        import importlib
        import pkgutil
        sections = [m.name for m in pkgutil.iter_modules(config.__path__)]
        for name in sections:
            for other in sections:
                self.assertNotIn(name, vars(importlib.import_module(f"config.{other}")), other)

    def test_every_live_setting_has_its_constant(self):
        missing = [path for path, (name, _live) in config.SETTINGS.items()
                   if name and not hasattr(config, name)]
        self.assertEqual(missing, [])


class SetAtRunTime(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "config.json")
        with open(self.file, "w") as f:
            json.dump({"mood": {"emotes": True}}, f)
        self.saved = dict(config.settings)
        self.patches = [mock.patch.object(config, "CONFIG_FILE", self.file),
                        mock.patch.object(config, "MOOD_EMOTES", True),
                        mock.patch.object(config, "_plugins_cfg", dict(config._plugins_cfg))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        config.settings.clear()
        config.settings.update(self.saved)
        shutil.rmtree(self.tmp)

    def test_set_changes_what_everyone_reads(self):
        value, live = config.save_setting("mood.emotes", "false")
        self.assertIs(value, False)
        self.assertTrue(live)
        self.assertIs(config.MOOD_EMOTES, False)                 # the namespace modules read
        self.assertIs(config.current("mood.emotes"), False)
        with open(self.file) as f:
            self.assertIs(json.load(f)["mood"]["emotes"], False)  # and the file

    def test_a_plugin_switch_reaches_plugin_settings(self):
        config.set_plugin_enabled("example_test", True)
        self.assertTrue(config.plugin_settings("example_test")["enabled"])
        with open(self.file) as f:
            self.assertTrue(json.load(f)["plugins"]["example_test"]["enabled"])

    def test_unknown_or_wrong_shape_is_refused(self):
        with self.assertRaises(ValueError):
            config.save_setting("no.such.setting", "1")
        with self.assertRaises(ValueError):
            config.save_setting("mood.emotes", "maybe")


if __name__ == "__main__":
    unittest.main()
