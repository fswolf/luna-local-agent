"""Her lights from the room behind her (portrait.match_light, portrait/viewer/ambient.js)."""
import unittest
from unittest import mock

from tests.offline import FAKE  # noqa: F401  (first: no real servers)

import config


class MatchLightTest(unittest.TestCase):
    def test_kept_between_0_and_1(self):
        coerce = config._coerce
        self.assertEqual(coerce("portrait.match_light", "0.3"), 0.3)
        self.assertEqual(coerce("portrait.match_light", "5"), 1.0)
        self.assertEqual(coerce("portrait.match_light", "-1"), 0.0)
        with self.assertRaises(ValueError):
            coerce("portrait.match_light", "lots")

    def test_a_setting_that_applies_live(self):
        from config.schema import SCHEMA
        self.assertIn("portrait.match_light", SCHEMA)
        self.assertIn("portrait.match_light", config.SETTINGS)

    def test_the_page_gets_it(self):
        from web import livefeed
        with mock.patch.object(config, "PORTRAIT_MATCH_LIGHT", 0.25, create=True):
            self.assertEqual(livefeed.portrait_config()["match_light"], 0.25)

    def test_changing_it_tells_the_portrait(self):
        from ui import settings_pane
        from web import livefeed
        sent = []
        with mock.patch.object(livefeed, "emit", lambda kind, **d: sent.append((kind, d))):
            settings_pane._after("portrait.match_light", 0.8)
        self.assertEqual(sent, [("match_light", {"value": 0.8})])

    def test_cards_carry_it(self):
        from web import cards
        self.assertIn("portrait.match_light", cards.LOOK)


if __name__ == "__main__":
    unittest.main()
