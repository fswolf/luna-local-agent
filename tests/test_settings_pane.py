"""The settings pane (ui/settings_pane.py) and what it stands on: every
setting described in config/schema.py, values typed by what the setting
is, and changes saved to a temporary config.json (yours is never touched).

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from config.schema import SCHEMA, SECTIONS  # noqa: E402
from ui import settings_pane  # noqa: E402
from ui.shared import view  # noqa: E402

KINDS = {"bool", "int", "float", "text", "choice", "list", "dict", "secret"}


def _example_paths():
    with open(os.path.join(config.BASE_DIR, "config.example.json")) as f:
        return dict(settings_pane._leaves(json.load(f)))


class Schema(unittest.TestCase):
    def test_every_setting_is_described(self):
        missing = sorted((set(config.SETTINGS) | set(_example_paths())) - set(SCHEMA))
        self.assertEqual(missing, [], "add these to config/schema.py")

    def test_entries_are_well_formed(self):
        for path, entry in SCHEMA.items():
            self.assertIn(entry[0], KINDS, path)
            self.assertTrue(entry[1].strip(), f"{path} has no explanation")
            self.assertNotIn("—", entry[1], f"{path}: no em dashes")
            if entry[0] == "choice" and len(entry) > 2:
                self.assertTrue(entry[2], f"{path}: a choice with no choices")

    def test_every_section_has_a_title(self):
        for path in SCHEMA:
            if not path.startswith("plugins."):
                self.assertIn(path.split(".")[0], SECTIONS, path)


class Pane(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "config.json")
        with open(self.file, "w") as f:
            json.dump({"mood": {"emotes": True}, "llm": {"api_key": "sk-secret"}}, f)
        self.saved = dict(config.settings)
        config.settings.clear()
        config.settings.update({"mood": {"emotes": True}, "llm": {"api_key": "sk-secret"}})
        self.patches = [mock.patch.object(config, "CONFIG_FILE", self.file),
                        mock.patch.object(config, "MOOD_EMOTES", True),
                        mock.patch.object(config, "_plugins_cfg", {})]
        for p in self.patches:
            p.start()
        view.set_filter, view.set_cursor, view.set_scroll, view.set_editing, view.set_status = "", 0, 0, None, ""

    def tearDown(self):
        for p in self.patches:
            p.stop()
        config.settings.clear()
        config.settings.update(self.saved)
        shutil.rmtree(self.tmp, ignore_errors=True)
        view.set_filter = ""

    def _file(self):
        with open(self.file) as f:
            return json.load(f)

    def _select(self, path):
        view.set_filter = path
        rows = [row[0] for row in settings_pane._rows()]
        view.set_cursor = rows.index(path)

    def test_lists_every_setting(self):
        paths = settings_pane._all_paths()
        self.assertGreaterEqual(len(paths), len(SCHEMA))
        self.assertIn("stt.mode", paths)
        self.assertIn("plugins.twitch.lewd", paths)

    def test_filter_matches_name_and_explanation(self):
        view.set_filter = "lewd"
        found = [row[0] for row in settings_pane._rows()]
        self.assertIn("plugins.twitch.lewd", found)
        self.assertNotIn("stt.mode", found)

    def test_plugins_get_a_heading_each(self):
        self.assertEqual(settings_pane._section("plugins.twitch.lewd"), ("plugins.twitch", "Plugin: twitch"))

    def test_space_flips_a_switch(self):
        self._select("mood.emotes")
        settings_pane.flip()
        self.assertIs(self._file()["mood"]["emotes"], False)
        self.assertIs(config.MOOD_EMOTES, False)

    def test_space_steps_a_choice(self):
        self._select("long_term_memory.backend")
        with mock.patch.object(config, "LONG_TERM_MEMORY_BACKEND", "json", create=True):
            settings_pane.flip()
        self.assertIn(self._file()["long_term_memory"]["backend"], ("json", "sqlite"))

    def test_a_setting_outside_the_table_saves_for_a_restart(self):
        self._select("plugins.twitch.lewd")
        settings_pane.flip()
        self.assertIs(self._file()["plugins"]["twitch"]["lewd"], True)
        self.assertIn("after a restart", view.set_status)

    def test_lists_are_saved_as_lists(self):
        value, _live = config.save_any("knowledge.folders", "notes, ~/docs , manuals")
        self.assertEqual(value, ["notes", "~/docs", "manuals"])
        self.assertEqual(self._file()["knowledge"]["folders"], ["notes", "~/docs", "manuals"])

    def test_numbers_are_checked(self):
        self._select("stt.silence_seconds")
        settings_pane.edit()
        settings_pane.finish_edit("abc")
        self.assertIn("isn't one", view.set_status)
        self.assertNotIn("stt", self._file())

    def test_choices_are_checked(self):
        with self.assertRaises(ValueError):
            config.save_any("portrait.fan.framing", "sideways")

    def test_nested_blocks_stay_in_the_file(self):
        with self.assertRaises(ValueError):
            config.save_any("mcp.servers", "anything")

    def test_secrets_are_hidden(self):
        self.assertEqual(settings_pane._show("llm.api_key", "sk-secret", "secret"), settings_pane._HIDDEN)
        self.assertNotIn("sk-secret", "".join(t for _s, t in settings_pane._fragments()))

    def test_x_goes_back_to_the_default(self):
        config.save_any("plugins.twitch.lewd", "true")
        self._select("plugins.twitch.lewd")
        settings_pane.reset()
        self.assertNotIn("lewd", self._file()["plugins"]["twitch"])


if __name__ == "__main__":
    unittest.main()
