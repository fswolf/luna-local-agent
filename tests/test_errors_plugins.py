"""Error handling in the plugins and the game servers: a game whose server
is gone or whose turns keep failing stops and says so once; numbers from
config.json that would overflow a wait are clamped; a chat plugin
switched off and on doesn't end up with two listeners; a toy stop that
fails is said loudly and a broken cap never means full power.

No network, no devices, no model.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

from plugins import _game  # noqa: E402


def until(check, seconds=3):
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return False


class Numbers(unittest.TestCase):
    def test_turn_limit(self):
        self.assertIsNone(_game.turn_limit(0, 150))
        self.assertIsNone(_game.turn_limit(-1, 150))        # "no limit", not "cut off at once"
        self.assertEqual(_game.turn_limit(float("nan"), 150), 150)
        self.assertEqual(_game.turn_limit(1e10, 150), 3600)
        self.assertEqual(_game.turn_limit("90s", 150), 150)
        self.assertEqual(_game.turn_limit(90, 150), 90)

    def test_seconds_never_overflow_a_wait(self):
        for bad in (1e10, float("inf"), float("nan"), -5, "1.5s", None):
            value = _game.seconds(bad, 1.5, hi=60)
            self.assertTrue(0 <= value <= 60, bad)
            threading.Event().wait(min(value, 0.001))       # no OverflowError

    def test_whole(self):
        self.assertEqual(_game.whole("abc", 60), 60)
        self.assertEqual(_game.whole(float("inf"), 60), 100000)
        self.assertEqual(_game.whole(0, 60), 1)


class LoopGivesUp(unittest.TestCase):
    def setUp(self):
        self.said, self.state, self.playing = [], {}, [True]
        self.patches = [mock.patch("mind.reflect.idle_seconds", return_value=999),
                        mock.patch("plugins._playlog.finished"),
                        mock.patch.object(_game, "say", side_effect=self.said.append),
                        mock.patch.object(_game, "ERROR_PAUSE", 0.01)]
        for p in self.patches:
            p.start()
        self.loop = None

    def tearDown(self):
        if self.loop:
            self.loop.stop()
            if self.loop._thread:
                self.loop._thread.join(5)
        for p in self.patches:
            p.stop()

    def make(self, step, **kw):
        self.loop = _game.Loop("game", self.state, step, playing=lambda: self.playing[0],
                               pause=lambda: self.playing.__setitem__(0, False), title="Game", **kw)
        self.loop.start()
        self.loop.wake()
        return self.loop

    def test_stops_after_failures_in_a_row_and_says_so_once(self):
        calls = []

        def step():
            calls.append(1)
            raise RuntimeError("model went away")

        self.make(step)
        self.assertTrue(until(lambda: self.loop.wake() or not self.playing[0]))
        time.sleep(0.1)
        self.assertEqual(len(calls), _game.MAX_FAILURES)
        self.assertEqual(len(self.said), 1)
        self.assertIn("model went away", self.said[0])

    def test_a_good_turn_resets_the_count(self):
        calls = []

        def step():
            calls.append(1)
            if len(calls) % 2:
                raise RuntimeError("now and then")
            if len(calls) >= 6:
                self.playing[0] = False

        self.make(step)
        self.assertTrue(until(lambda: self.loop.wake() or len(calls) >= 6, 5))
        self.assertEqual(self.said, [])

    def test_a_server_that_is_gone_stops_play_before_a_turn(self):
        calls = []
        with mock.patch.object(_game, "server_problem", return_value="process exited"):
            self.make(lambda: calls.append(1), server="zork")
            self.assertTrue(until(lambda: not self.playing[0]))
        self.assertEqual(calls, [])
        self.assertEqual(len(self.said), 1)
        self.assertIn("process exited", self.said[0])
        self.assertIn("/game off", self.said[0])

    def test_a_bad_quiet_setting_doesnt_end_the_loop(self):
        calls = []
        self.make(lambda: calls.append(1), quiet=lambda: "20s")
        self.assertTrue(until(lambda: calls))        # the default, not a dead thread


class ChessStalls(unittest.TestCase):
    def setUp(self):
        try:
            from plugins import chessgame
        except ImportError:
            self.skipTest("pip install chess")
        if chessgame.chess is None:
            self.skipTest("pip install chess")
        self.cg = chessgame
        self.tmp = tempfile.mkdtemp()
        self.patches = [mock.patch.object(chessgame, "GAME_FILE", os.path.join(self.tmp, "game.json")),
                        mock.patch.object(chessgame, "SAVES", self.tmp),
                        mock.patch.object(chessgame, "_emit")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        import shutil

        shutil.rmtree(self.tmp)

    def test_giving_up_stalls_the_game(self):
        self.cg._g["stalled"] = False
        self.cg._stall()
        self.assertTrue(self.cg._g["stalled"])
        self.cg._nudge()
        self.assertFalse(self.cg._g["stalled"])

    def test_a_failed_pause_doesnt_leave_her_thinking(self):
        cg = self.cg
        cg._new("white")
        cg._g["board"].push_san("e4")             # her move (black)
        with mock.patch.object(cg, "settings", return_value=dict(cg.DEFAULTS, think_seconds=1e10)), \
                mock.patch.object(cg._loop, "wait", side_effect=OverflowError("too long")):
            with self.assertRaises(OverflowError):
                cg._step()
        self.assertFalse(cg._g["thinking"])

    def test_a_huge_think_time_is_clamped(self):
        cg = self.cg
        cg._new("white")
        cg._g["board"].push_san("e4")
        waited = []
        with mock.patch.object(cg, "settings", return_value=dict(cg.DEFAULTS, think_seconds=1e10)), \
                mock.patch.object(cg._loop, "wait", side_effect=waited.append), \
                mock.patch("core.assistant.respond_to_job", return_value=""), \
                mock.patch("plugins._game.record"):
            cg._step()
        self.assertLessEqual(waited[0], 60)

    def test_a_broken_save_is_kept_aside_not_written_over(self):
        cg = self.cg
        with open(cg.GAME_FILE, "w") as f:
            f.write("{not json")
        cg._g["error"] = ""
        self.assertFalse(cg._load())
        self.assertTrue(os.path.exists(cg.GAME_FILE + ".bad"))
        self.assertIn(".bad", cg._g["error"])


class ChatRestart(unittest.TestCase):
    """Off and on quickly: the old loop's stop stays set."""

    def check(self, module, target, args=()):
        old_stop = threading.Event()
        old_stop.set()
        calls = []
        with mock.patch.object(module, target, side_effect=lambda *a, **k: calls.append(1)):
            started = time.time()
            # a loop given an already-set stop returns at once, never connecting
            getattr(module, "_listen_loop" if hasattr(module, "_listen_loop") else "_poll_loop")(old_stop)
            self.assertLess(time.time() - started, 1)
        self.assertEqual(calls, [])

    def test_twitch(self):
        from plugins import twitch

        self.check(twitch, "_connect_once")

    def test_irc(self):
        from plugins import irc

        with mock.patch.object(irc, "settings", return_value=dict(irc.DEFAULTS)):
            self.check(irc, "_connect_once")

    def test_pomf(self):
        from plugins import pomf

        with mock.patch.object(pomf, "credentials", return_value=("c", "1", "k")):
            self.check(pomf, "_connect_once")

    def test_youtube(self):
        from plugins import youtube

        self.check(youtube, "_find_chat")

    def test_backoff_wait_ends_when_stopped(self):
        from plugins import twitch

        stop = threading.Event()

        def fail(_stop):
            raise OSError("down")

        with mock.patch.object(twitch, "_connect_once", side_effect=fail):
            t = threading.Thread(target=twitch._listen_loop, args=(stop,), daemon=True)
            t.start()
            time.sleep(0.1)
            stop.set()
            t.join(2)
        self.assertFalse(t.is_alive())        # not stuck in a time.sleep backoff

    def test_pomf_refused_socket_backs_off(self):
        from plugins import pomf

        stop, waits = mock.Mock(), []
        stop.is_set.side_effect = lambda: len(waits) >= 3
        stop.wait.side_effect = lambda s: waits.append(s) or False
        with mock.patch.object(pomf, "credentials", return_value=("c", "1", "k")), \
                mock.patch.object(pomf, "_connect_once", return_value=False):
            pomf._listen_loop(stop)
        self.assertGreater(waits[2], waits[0] + 2)   # growing, not 2s each time

    def test_broken_credentials_are_named(self):
        from plugins import twitch

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{oops")
        try:
            with mock.patch.object(twitch, "CREDENTIALS_FILE", f.name), \
                    mock.patch.object(twitch, "settings",
                                      return_value=dict(twitch.DEFAULTS, channel="me", post_replies=True)):
                self.assertIn("couldn't be read", twitch.why_unavailable())
        finally:
            os.remove(f.name)

    def test_pomf_odd_sender_doesnt_raise(self):
        from plugins import pomf

        room = mock.Mock()
        with mock.patch.object(pomf, "_room", room):
            pomf._handle({"type": "message", "from": "someone", "message": "hi"}, "c")
        room.saw.assert_called_once_with(None, "hi")


class Toys(unittest.TestCase):
    def test_lovense_bad_caps_are_careful(self):
        from plugins import lovense as lv

        with mock.patch.object(lv, "settings", return_value=dict(lv.DEFAULTS, max_strength="10%",
                                                                 max_seconds=float("nan"))):
            strength, seconds = lv._caps()
        self.assertLess(strength, 20)
        self.assertLess(seconds, 60)
        with mock.patch.object(lv, "settings", return_value=dict(lv.DEFAULTS)):
            self.assertEqual(lv._caps(), (20, 60))      # good settings unchanged

    def test_buttplug_nan_cap_isnt_full_power(self):
        from plugins import buttplug as bp

        with mock.patch.object(bp, "settings", return_value=dict(bp.DEFAULTS, max_intensity=float("nan"))):
            self.assertLess(bp._caps()[0], 1.0)
        with mock.patch.object(bp, "settings", return_value=dict(bp.DEFAULTS)):
            self.assertEqual(bp._caps(), (1.0, 60))

    def test_lovense_failed_stop_is_loud(self):
        from plugins import lovense as lv

        said = []
        with mock.patch.dict(lv._state, {"connected": True}), \
                mock.patch.object(lv, "_post", side_effect=RuntimeError("no route")), \
                mock.patch("ui.add_message", side_effect=lambda who, text: said.append(text)):
            ok, message = lv.stop()
            ok2, message2 = lv.stop_all_toys()
        self.assertFalse(ok)
        self.assertFalse(ok2)
        self.assertIn("COULDN'T STOP", message)
        self.assertTrue(said and "COULDN'T STOP" in said[0])
        lv._stop.clear()

    def test_lovense_infinite_seconds_is_an_answer(self):
        from plugins import lovense as lv

        with mock.patch.dict(lv._state, {"connected": True, "toys": {}}), \
                mock.patch.object(lv, "_post"), mock.patch("tools.register_external") as reg, \
                mock.patch.object(lv._toys, "blocked", return_value=""):
            lv._register_tools()
            vibrate = next(c.kwargs["run"] for c in reg.call_args_list if c.args[0] == "lovense_vibrate")
            self.assertIn("numbers", vibrate(strength=5, seconds=float("inf")))
        lv._plan.clear()
        lv._sent.clear()

    def test_buttplug_failed_stop_is_loud(self):
        from plugins import buttplug as bp

        with mock.patch.dict(bp._state, {"connected": True, "ws": None}), \
                mock.patch("ui.add_message") as shown:
            ok, message = bp.stop_all_devices()
        self.assertFalse(ok)
        self.assertIn("COULDN'T STOP", message)
        shown.assert_called_once()

    def test_buttplug_odd_messages_dont_end_the_reader(self):
        from plugins import buttplug as bp

        replies = [json.dumps(["not a dict", {"DeviceAdded": "nope"}, {"DeviceList": {"Devices": [5]}}]),
                   json.dumps([{"Ok": {"Id": 7}}])]
        slot = [threading.Event(), None]

        class WS:
            def recv(self):
                if replies:
                    return replies.pop(0)
                raise OSError("closed")

        ws = WS()
        with mock.patch.dict(bp._state, {"ws": ws, "devices": {}}), \
                mock.patch.dict(bp._waiting, {7: slot}), mock.patch.object(bp.logbook, "tell"):
            bp._reader(ws)
        self.assertTrue(slot[0].is_set())        # still reading after the odd ones


class Servers(unittest.TestCase):
    def test_zork_restart_gets_a_fresh_queue(self):
        import importlib.util

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location(
            "zork_server_t", os.path.join(here, "games", "zork", "zork_server.py"))
        try:
            with mock.patch.object(sys, "argv", ["zork_server.py"]):
                server = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(server)
        except ImportError:
            self.skipTest("pip install mcp")
        game = server.Game()
        old = game.out
        old.put(None)                  # the last dfrotz's end of output
        with mock.patch.object(server, "find_dfrotz", return_value="/bin/true"), \
                mock.patch.object(server.os.path, "exists", return_value=True), \
                mock.patch.object(server.subprocess, "Popen"), \
                mock.patch.object(server.threading, "Thread"), \
                mock.patch.object(server.Game, "_read", return_value="West of House\n>"), \
                mock.patch.object(server.Game, "_restore", return_value=""), \
                mock.patch.object(server, "transcript"):
            game.start()
        self.assertIsNot(game.out, old)
        self.assertTrue(game.out.empty())

    def test_gameboy_dead_emulator_answers_at_once(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(here, "games", "gameboy"))
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "gb_server_errors", os.path.join(here, "games", "gameboy", "gb_server.py"))
        with mock.patch.object(sys, "argv", ["gb_server.py"]):
            server = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(server)
        console = server.Console.__new__(server.Console)
        console.alive, console.broken, console.jobs = False, "tick failed", queue.Queue()
        console.thread = threading.Thread(target=lambda: None)
        started = time.time()
        with self.assertRaises(RuntimeError):
            console.do(lambda: None)
        self.assertLess(time.time() - started, 1)
        self.assertIn("tick failed", server._off(console))


if __name__ == "__main__":
    unittest.main()
