"""The model-size presets (config/presets.py, "kind": "size"): small,
medium, large. They set what fits in each prompt and never touch what the
how-she-behaves presets set, so one of each can be in use at once."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import presets  # noqa: E402
from config.presets import PRESETS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = ("small", "medium", "large")


def _example(path):
    """A value from config.example.json by dotted path, or None."""
    with open(os.path.join(ROOT, "config.example.json"), encoding="utf-8") as f:
        node = json.load(f)
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class Sizes(unittest.TestCase):
    def test_three_sizes_marked_as_size(self):
        self.assertEqual([n for n in PRESETS if presets.kind(n) == "size"], list(SIZES))

    def test_every_size_sets_the_same_settings(self):
        # switching sizes must replace every value the last one set
        keys = set(PRESETS["small"]["values"])
        for name in SIZES:
            self.assertEqual(set(PRESETS[name]["values"]), keys, name)

    def test_sizes_never_touch_what_behaviour_presets_set(self):
        size_keys = set(PRESETS["small"]["values"])
        for name, p in PRESETS.items():
            if presets.kind(name) != "size":
                self.assertEqual(size_keys & set(p["values"]), set(), name)

    def test_bigger_never_gives_less_room(self):
        for path, small in PRESETS["small"]["values"].items():
            if isinstance(small, bool):
                continue
            med, large = PRESETS["medium"]["values"][path], PRESETS["large"]["values"][path]
            self.assertTrue(small <= med <= large, path)

    def test_small_matches_the_example_config(self):
        # small is the way back to how she ships
        for path, value in PRESETS["small"]["values"].items():
            shipped = _example(path)
            if shipped is not None:
                self.assertEqual(shipped, value, path)


class Page(unittest.TestCase):
    def test_both_rows_answer_a_click(self):
        # the size row sits outside #presets: the click handler must cover both
        with open(os.path.join(ROOT, "web", "settings.html"), encoding="utf-8") as f:
            page = f.read()
        box = page[page.index('<div id="presetbox">'):]
        self.assertLess(box.index('id="presets"'), box.index('id="sizes"'))
        self.assertIn('$("#presetbox").addEventListener("click"', page)


if __name__ == "__main__":
    unittest.main()
