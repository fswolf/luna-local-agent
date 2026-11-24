"""Her tray icon (app/tray.py): the menu follows her state, the icon is read
without Pillow, and it ends when she does. No D-Bus and no tray here.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import tray  # noqa: E402


def luna(**state):
    l = tray.Luna("http://127.0.0.1:1")
    l.state = {"name": "Luna", "status": "Idle", "rows": [["Model", "qwen"]], **state}
    return l


class Menu(unittest.TestCase):
    def keys(self, l):
        return [e[0] for e in tray.items(l)]

    def test_chat_first_quit_last(self):
        menu = tray.items(luna())
        self.assertEqual(menu[0][:2], ("chat", "Open chat"))
        self.assertEqual(menu[-1][:2], ("quit", "Quit Luna"))
        self.assertNotIn("status", self.keys(luna()))
        self.assertNotIn("model", self.keys(luna()))

    def test_tooltip_keeps_status_and_model(self):
        self.assertEqual(tray.tooltip(luna()), ("Luna", "Idle · qwen"))

    def test_talk_only_with_push_to_talk(self):
        self.assertNotIn("talk", self.keys(luna()))
        self.assertIn("talk", self.keys(luna(can_talk=True)))
        talk = dict((e[0], e[1]) for e in tray.items(luna(can_talk=True, mic=True)))["talk"]
        self.assertEqual(talk, "Done talking")

    def test_stop_only_when_busy_and_voice_checked(self):
        idle = {e[0]: e for e in tray.items(luna(voice_on=False))}
        self.assertFalse(idle["stop"][3])
        self.assertFalse(idle["voice"][4])
        busy = {e[0]: e for e in tray.items(luna(busy=True, voice_on=True))}
        self.assertTrue(busy["stop"][3])
        self.assertTrue(busy["voice"][4])

    def test_stop_for_anything_stoppable_not_only_your_turns(self):
        greeting = {e[0]: e for e in tray.items(luna(busy=False, stoppable=True))}
        self.assertTrue(greeting["stop"][3])
        idle = {e[0]: e for e in tray.items(luna(busy=False, stoppable=False))}
        self.assertFalse(idle["stop"][3])

    def test_actions(self):
        l = luna()
        with mock.patch.object(l, "act") as act, mock.patch.object(l, "open_chat") as chat:
            for key in ("chat", "portrait", "voice", "quit", "status", "bogus"):
                tray.run_action(l, key)
        chat.assert_called_once_with()
        self.assertEqual([c.args[0] for c in act.call_args_list], ["portrait", "voice", "quit"])

    def test_gone_after_quiet(self):
        l = luna()
        self.assertFalse(l.gone())
        l.seen -= tray.GONE + 1
        self.assertTrue(l.gone())
        self.assertFalse(l.refresh())            # nothing on port 1


class Icon(unittest.TestCase):
    def test_png_matches_pillow(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("no Pillow to compare with")
        w, h, rgba = tray.read_png(tray.LOGO)
        im = Image.open(tray.LOGO).convert("RGBA")
        self.assertEqual((w, h), im.size)
        self.assertEqual(rgba, im.tobytes())

    def test_argb_sizes(self):
        maps = tray.argb_pixmaps()
        self.assertIn(22, [m[0] for m in maps])
        for w, h, data in maps:
            self.assertEqual(len(data), w * h * 4)

    def test_a_margin_like_the_other_icons(self):
        """The disc fills its square: drawn smaller, with clear corners and edges."""
        w, h, data = next(m for m in tray.argb_pixmaps() if m[0] == 32)
        alpha = data[0::4]
        self.assertEqual(alpha[0], 0)                                   # a corner
        self.assertEqual(max(alpha[:w * 2]), 0)                         # the top two rows
        self.assertGreater(alpha[(h // 2) * w + w // 2], 200)           # the middle

if __name__ == "__main__":
    unittest.main()
