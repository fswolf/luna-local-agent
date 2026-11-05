"""/portrait sounds: gesture sounds on, off and their volume, saved and sent
to an open portrait straight away. config.json isn't touched: save_setting
is replaced with one that only sets the value.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.offline  # noqa: F401,E402

import config  # noqa: E402
from commands import portrait  # noqa: E402


class Sounds(unittest.TestCase):
    def setUp(self):
        self.saved = {}

        def save(path, raw):
            value = config._coerce(path, raw)
            setattr(config, config.SETTINGS[path][0], value)
            self.saved[path] = value
            return value, True

        for k, v in (("PORTRAIT_SOUNDS", True), ("PORTRAIT_SOUND_VOLUME", 0.8)):
            p = mock.patch.object(config, k, v)
            p.start()
            self.addCleanup(p.stop)
        for p in (mock.patch.object(config, "save_setting", save), mock.patch("ui.add_message")):
            p.start()
            self.addCleanup(p.stop)

    def run_cmd(self, text):
        with mock.patch("web.livefeed.emit") as emit:
            self.assertTrue(portrait.handle(text))
        return emit

    def test_off_and_on(self):
        self.run_cmd("/portrait sounds off").assert_called_with("sounds", on=False, volume=0.8)
        self.assertIs(config.PORTRAIT_SOUNDS, False)
        self.run_cmd("/portrait sounds on").assert_called_with("sounds", on=True, volume=0.8)

    def test_volume_as_percent_or_fraction(self):
        self.run_cmd("/portrait sounds 50%")
        self.assertAlmostEqual(config.PORTRAIT_SOUND_VOLUME, 0.5)
        self.run_cmd("/portrait sounds off")
        self.run_cmd("/portrait sounds 0.3").assert_called_with("sounds", on=True, volume=0.3)   # a volume turns them back on
        self.run_cmd("/portrait sounds 30")
        self.assertAlmostEqual(config.PORTRAIT_SOUND_VOLUME, 0.3)

    def test_junk_changes_nothing(self):
        self.run_cmd("/portrait sounds loud").assert_not_called()
        self.assertEqual(self.saved, {})

    def test_settings_page_tells_the_portrait(self):
        from ui import settings_pane
        with mock.patch("web.livefeed.emit") as emit:
            settings_pane._after("portrait.sounds", False)
        emit.assert_called_once()
        self.assertEqual(emit.call_args[0][0], "sounds")


if __name__ == "__main__":
    unittest.main()
