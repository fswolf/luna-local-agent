"""History sized to the window (core/history.py limits()).

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from core import history  # noqa: E402


class Scale(unittest.TestCase):
    def setUp(self):
        self.saved = (config.MAX_RAW_MESSAGES, config.SUMMARY_MAX_CHARS,
                      config.HISTORY_AUTO_SCALE, config.HISTORY_SCALE_CAP, dict(history._scaled))
        config.MAX_RAW_MESSAGES, config.SUMMARY_MAX_CHARS = 15, 2500
        config.HISTORY_AUTO_SCALE, config.HISTORY_SCALE_CAP = True, 60

    def tearDown(self):
        (config.MAX_RAW_MESSAGES, config.SUMMARY_MAX_CHARS,
         config.HISTORY_AUTO_SCALE, config.HISTORY_SCALE_CAP, scaled) = self.saved
        history._scaled.clear()
        history._scaled.update(scaled)

    def window(self, n, tools=9300):
        history._scaled.update(at=time.monotonic(), window=n, tools=tools)

    def test_small_window_keeps_the_settings(self):
        self.window(16384)
        self.assertEqual(history.limits(), (15, 2500))

    def test_32k_with_every_tool_is_about_medium(self):
        self.window(32768)
        keep, chars = history.limits()
        self.assertTrue(25 <= keep <= 45, keep)
        self.assertTrue(3000 <= chars <= 8000, chars)

    def test_big_window_stops_at_the_cap(self):
        self.window(131072)
        self.assertEqual(history.limits(), (60, config.HISTORY_SCALE_SUMMARY_CAP))

    def test_never_below_the_settings(self):
        config.MAX_RAW_MESSAGES = 80
        self.window(32768)
        self.assertEqual(history.limits()[0], 80)

    def test_tools_that_fill_the_window_change_nothing(self):
        self.window(32768, tools=30000)
        self.assertEqual(history.limits(), (15, 2500))

    def test_switched_off(self):
        config.HISTORY_AUTO_SCALE = False
        self.window(131072)
        self.assertEqual(history.limits(), (15, 2500))

    def test_unknown_window_keeps_the_settings(self):
        self.window(0)
        self.assertEqual(history.limits(), (15, 2500))

    def test_the_knobs_are_settings(self):
        self.window(32768)
        before = history.limits()[0]
        saved = config.HISTORY_SCALE_USE
        try:
            config.HISTORY_SCALE_USE = 0.5
            self.assertLess(history.limits()[0], before)
        finally:
            config.HISTORY_SCALE_USE = saved

    def test_explain_shows_the_sum(self):
        self.window(32768)
        out = history.explain()
        self.assertEqual(out["left"], 32768 - out["tools"] - out["prompt"] - out["reply"] - out["results"])
        self.assertTrue(out["scaled"])

    def test_settings_page_asks(self):
        import json
        from web import settings_web
        real = history._measure
        history._measure = lambda fresh=False: (32768, 9300)
        try:
            status, _, body = settings_web.handle("GET", "/api/scale", b"")
        finally:
            history._measure = real
        self.assertEqual(status, 200)
        self.assertIn("keep", json.loads(body))

    def test_a_prompt_never_carries_more_than_fits(self):
        self.window(16384)
        saved = list(history._data.get("messages", []))
        try:
            history._data["messages"] = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
                                         for i in range(80)]
            past = history.recent()
            self.assertLessEqual(len(past), 15 + config.SUMMARIZE_CHUNK)
            self.assertEqual(past[0]["role"], "user")
            self.assertEqual(past[-1]["content"], "79")
        finally:
            history._data["messages"] = saved

    def test_far_over_folds_more_at_once(self):
        saved = (dict(history._data), history._summarize_chunk, history.save, history._summarizing)
        try:
            history._data.update(summary="", messages=[{"role": "user", "content": str(i)} for i in range(80)])
            history._summarize_chunk = lambda model, chunk: f"{len(chunk)} folded"
            history.save = lambda: None
            history._fold("m", keep=15, chars=2500)
            self.assertEqual(len(history._data["messages"]), 80 - 4 * config.SUMMARIZE_CHUNK)
        finally:
            history._data.clear(); history._data.update(saved[0])
            history._summarize_chunk, history.save, history._summarizing = saved[1], saved[2], saved[3]


if __name__ == "__main__":
    unittest.main()
