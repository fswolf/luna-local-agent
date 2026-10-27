"""State that several threads share: her walk-away, the on-screen
conversation, the microphone count. Each test races real threads at it.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import threading
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402


def _race(fn, n=16):
    """Run fn on n threads released together."""
    gate = threading.Barrier(n)

    def go():
        gate.wait()
        fn()

    threads = [threading.Thread(target=go) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)


class WalkAway(unittest.TestCase):
    def setUp(self):
        from mind import mood
        self.mood = mood
        self.patches = [mock.patch.object(config, "MOOD_ENABLED", True),
                        mock.patch.object(config, "MOOD_WALK_AWAY", True, create=True),
                        mock.patch.object(config, "MOOD_WALK_AWAY_AFTER", 3, create=True),
                        mock.patch.object(mood, "_announce"),
                        mock.patch.object(mood, "_save")]
        for p in self.patches:
            p.start()
        mood._away.update(until=0.0, said=False, hostile=0, last=0.0)

    def tearDown(self):
        self.mood._away.update(until=0.0, said=False, hostile=0, last=0.0)
        for p in self.patches:
            p.stop()

    def test_two_appraisals_finishing_together_walk_her_out_once(self):
        self.mood._away.update(hostile=2, last=__import__("time").time())
        with mock.patch.object(self.mood, "_withdraw") as withdraw:
            _race(lambda: self.mood._count_hostility(0, -1))
        self.assertEqual(withdraw.call_count, 1)
        self.assertTrue(self.mood._away["until"])

    def test_coming_back_happens_once(self):
        self.mood._away.update(until=1.0)                    # long past
        _race(self.mood.away)
        self.assertEqual(self.mood._announce.call_count, 1)

    def test_one_leaving_line(self):
        self.mood._away.update(until=9e12)
        said = []
        _race(lambda: said.append(self.mood.leaving_line()))
        self.assertEqual(sum(1 for s in said if s), 1)


class Conversation(unittest.TestCase):
    def setUp(self):
        import ui
        self.ui = ui
        ui.clear()

    def tearDown(self):
        self.ui.clear()

    def test_drawing_while_messages_come_and_go(self):
        from ui.conversation_pane import _conversation_lines as conversation_lines
        ui, errors, stop = self.ui, [], threading.Event()

        def draw():
            while not stop.is_set():
                try:
                    conversation_lines()
                except Exception as e:      # noqa: BLE001 - any is a failure
                    errors.append(e)
                    return

        painter = threading.Thread(target=draw)
        painter.start()

        def talk():
            for _ in range(200):
                ui.begin_message("luna")
                ui.add_message("system", "tool ran")
                ui.extend_message("hi")
                ui.end_message()
                ui.begin_message("luna")
                ui.end_message()            # empty: dropped

        _race(talk, n=4)
        stop.set()
        painter.join(5)
        self.assertEqual(errors, [])

    def test_the_public_names_stay_what_they_were(self):
        import ui.app, ui.approval, ui.conversation_pane, ui.help, ui.messages, ui.tools_pane  # noqa: F401,E401
        self.assertIsInstance(self.ui.conversation, list)      # not a submodule of that name
        self.assertIsInstance(self.ui.state, dict)
        for name in ("add_message", "begin_message", "extend_message", "replace_message", "end_message",
                     "set_status", "set_mode", "set_model", "set_mood", "set_memory", "set_voice",
                     "set_voice_server", "set_controls", "init", "render", "clear", "toggle_mouse",
                     "mouse_enabled", "ask_approval", "approving", "run", "stop", "scroll_report"):
            self.assertTrue(callable(getattr(self.ui, name, None)), name)

    def test_clear_closes_the_open_message(self):
        self.ui.begin_message("luna")
        self.ui.clear()
        self.ui.extend_message("lost")      # nothing open: ignored, not an IndexError
        self.assertEqual(self.ui.conversation, [])
        self.assertIsNone(self.ui.view.streaming)


class Microphone(unittest.TestCase):
    def test_every_stream_is_counted_and_restart_waits_for_them(self):
        from voice import speech

        class FakeStream:
            def __init__(self, **kw):
                pass

            def start(self):
                pass

            def stop(self):
                pass

            def close(self):
                pass

        with mock.patch.object(speech.sd, "InputStream", FakeStream, create=True), \
                mock.patch.object(speech.sd, "_terminate", create=True) as terminate, \
                mock.patch.object(speech.sd, "_initialize", create=True):
            streams = []
            _race(lambda: streams.append(speech._open_mic(512)))
            self.assertEqual(speech._mic_streams[0], 16)
            speech._reset_portaudio()
            terminate.assert_not_called()               # a mic is open: not now
            _race(lambda: speech._close_mic(streams.pop()))
            self.assertEqual(speech._mic_streams[0], 0)
            speech._reset_portaudio()
            terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
