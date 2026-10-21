"""The first-start questions (firstrun.py): name, pronouns, a preset,
written to a temporary agent.json (yours is never touched).

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
import firstrun  # noqa: E402
from config import base  # noqa: E402

KEYS = ("USER_NAME", "USER_THEY", "USER_THEM", "USER_THEIR", "_USER_GAVE_PRONOUNS", "USER")


class FirstRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "agent.json")
        with open(self.file, "w") as f:
            json.dump({"name": "Luna", "personality": "kind"}, f)
        self.saved = {k: (getattr(base, k), getattr(config, k, None)) for k in KEYS}
        self.agent = dict(config.agent)
        config.agent.clear()
        config.agent.update({"name": "Luna", "personality": "kind"})
        self.said = []
        self.patches = [mock.patch.object(config, "AGENT_FILE", self.file),
                        mock.patch("ui.add_message", lambda who, text: self.said.append((who, text))),
                        mock.patch("settings_web.preset", return_value=(True, "Companion: 8 settings changed", None))]
        self.preset = self.patches[2]
        for p in self.patches:
            p.start()
        firstrun._state["step"] = None

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for k, (b, c) in self.saved.items():
            setattr(base, k, b)
            if not k.startswith("_"):
                setattr(config, k, c)
        config.agent.clear()
        config.agent.update(self.agent)
        firstrun._state["step"] = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self):
        with open(self.file) as f:
            return json.load(f)

    def test_the_whole_thing(self):
        self.assertTrue(firstrun.maybe_start())
        for line in ("Shannon", "2", "2"):
            self.assertTrue(firstrun.handle(line))
        self.assertFalse(firstrun.active())
        saved = self._file()
        self.assertEqual(saved["user"], {"name": "Shannon", "pronouns": "she/her"})
        self.assertEqual(saved["personality"], "kind")          # the rest of agent.json kept
        self.assertEqual(config.USER_NAME, "Shannon")
        self.assertIn("Shannon (she/her", base.user_line())
        import settings_web
        settings_web.preset.assert_called_once_with("companion")
        self.assertFalse(firstrun.needed())

    def test_own_pronouns_and_no_preset(self):
        firstrun.maybe_start()
        firstrun.handle("Ryan")
        firstrun.handle("xe/xem/xyr")
        firstrun.handle("skip")
        self.assertEqual(self._file()["user"]["pronouns"], "xe/xem/xyr")
        import settings_web
        settings_web.preset.assert_not_called()

    def test_skip_writes_an_empty_user_so_it_never_asks_again(self):
        firstrun.maybe_start()
        firstrun.handle("/skip")
        self.assertEqual(self._file()["user"], {})
        self.assertFalse(firstrun.maybe_start())

    def test_other_commands_still_work_mid_setup(self):
        firstrun.maybe_start()
        self.assertFalse(firstrun.handle("/settings"))
        self.assertTrue(firstrun.active())

    def test_a_bad_preset_answer_asks_again(self):
        firstrun.maybe_start()
        firstrun.handle("Ryan")
        firstrun.handle("skip")
        self.assertTrue(firstrun.handle("purple"))
        self.assertTrue(firstrun.active())

    def test_not_asked_when_agent_json_knows_you(self):
        config.agent["user"] = {"name": "Ryan"}
        self.assertFalse(firstrun.maybe_start())


if __name__ == "__main__":
    unittest.main()
