"""When she walks away, every connected toy stops at once, even with
stop_on_interrupt off (mind/mood/walkaway.py, plugins.panic(always=True)).

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402


class WalkingAwayStopsToys(unittest.TestCase):
    def test_walking_away_stops_everything(self):
        from mind.mood import walkaway
        import plugins
        with mock.patch.object(plugins, "panic") as panic, \
                mock.patch("mind.mood.drift._nudge"), \
                mock.patch("threading.Timer"):
            walkaway._withdraw(10)
        panic.assert_called_once_with(always=True)

    def test_a_failing_stop_never_stops_her_walking_away(self):
        from mind.mood import walkaway
        import plugins
        with mock.patch.object(plugins, "panic", side_effect=RuntimeError("socket gone")), \
                mock.patch("mind.mood.drift._nudge") as nudge, \
                mock.patch("threading.Timer"):
            walkaway._withdraw(10)
        nudge.assert_called()

    def test_panic_always_reaches_old_and_new_hooks(self):
        import plugins
        new, old = mock.Mock(), mock.Mock(side_effect=[TypeError("no args"), None])
        plugin = mock.Mock()
        plugin.name = "x"
        with mock.patch.object(plugins, "_each_running", return_value=[(plugin, new), (plugin, old)]):
            plugins.panic(always=True)
        new.assert_called_once_with(always=True)
        self.assertEqual(old.call_args_list, [mock.call(always=True), mock.call()])

    def test_toys_stop_even_with_stop_on_interrupt_off(self):
        from plugins import buttplug, lovense
        for module, stop in ((lovense, "stop_all_toys"), (buttplug, "stop_all_devices")):
            with mock.patch.dict(module._state, connected=True), \
                    mock.patch.object(config, "plugin_settings", return_value={"stop_on_interrupt": False}), \
                    mock.patch.object(module, stop) as stopped:
                module.panic()                      # HOME with the setting off: left alone
                stopped.assert_not_called()
                module.panic(always=True)           # she walked away: stopped
                stopped.assert_called_once()


if __name__ == "__main__":
    unittest.main()
