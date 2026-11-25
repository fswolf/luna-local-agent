"""A /command's answer is marked (ui.Asked) so the chat page shows it open;
tool logs and her own lines aren't."""
import contextlib
import unittest
from unittest import mock

import commands
import ui
from ui import shared


AREAS = ("app", "life", "memory", "patches", "people", "plugins", "portrait", "reminders", "settings", "voice")


def areas(first):
    """Every command area faked, the first answering with `first`."""
    import types
    return [mock.patch.object(commands, n, types.SimpleNamespace(handle=first if n == "app" else (lambda t: False)),
                              create=True) for n in AREAS]


class AskedLines(unittest.TestCase):

    def setUp(self):
        self.saved = list(shared.conversation)
        shared.conversation.clear()
        self.addCleanup(lambda: (shared.conversation.clear(), shared.conversation.extend(self.saved)))
        p = mock.patch("ui.messages._refresh")
        p.start()
        self.addCleanup(p.stop)

    def test_a_commands_answer_is_asked(self):
        def fake(text):
            ui.add_message("system", "Recipes (2):\n  1. a\n  2. b")
            return True
        with contextlib.ExitStack() as stack:
            for p in areas(fake):
                stack.enter_context(p)
            self.assertTrue(commands.handle("/skills"))
        speaker, text = shared.conversation[-1]
        self.assertIsInstance(text, ui.Asked)
        self.assertEqual(text, "Recipes (2):\n  1. a\n  2. b")

    def test_other_lines_are_not(self):
        ui.add_message("system", "run_command() -> exit 0")
        self.assertNotIsInstance(shared.conversation[-1][1], ui.Asked)
        with ui.answering():
            ui.add_message("user", "hi")
        self.assertNotIsInstance(shared.conversation[-1][1], ui.Asked)

    def test_the_flag_ends_with_the_command(self):
        def boom(text):
            raise RuntimeError("boom")
        with contextlib.ExitStack() as stack:
            for p in areas(boom):
                stack.enter_context(p)
            commands.handle("/x")
        self.assertIsInstance(shared.conversation[-1][1], ui.Asked)      # the failure line answers it
        ui.add_message("system", "later")
        self.assertNotIsInstance(shared.conversation[-1][1], ui.Asked)

    def test_the_page_gets_the_mark(self):
        from web import chat_web
        shared.conversation.extend([("system", ui.Asked("asked")), ("system", "log")])
        s = chat_web.state(version=-1, have=-1, epoch=ui.view.epoch, wait=0)
        self.assertIn(["system", "asked", 1], s["msgs"])
        self.assertIn(["system", "log"], s["msgs"])


if __name__ == "__main__":
    unittest.main()
