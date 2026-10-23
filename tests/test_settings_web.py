"""The settings page (settings_web.py) and the presets (config/presets.py):
what the page is sent, what it may change, and who may change it.
Changes go to a temporary config.json (yours is never touched).

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
import settings_web  # noqa: E402
from config.presets import PRESETS  # noqa: E402
from config.schema import BASIC, SCHEMA  # noqa: E402


class Tables(unittest.TestCase):
    def test_everyday_settings_exist(self):
        self.assertEqual([p for p in BASIC if p not in SCHEMA], [])

    def test_preset_values_fit_their_settings(self):
        for name, preset in PRESETS.items():
            self.assertTrue(preset["label"] and preset["about"], name)
            for path, value in preset["values"].items():
                self.assertIn(path, SCHEMA, f"{name}: {path}")
                kind = SCHEMA[path][0]
                ok = {"bool": isinstance(value, bool), "float": isinstance(value, (int, float)),
                      "int": isinstance(value, int)}.get(kind, True)
                self.assertTrue(ok, f"{name}: {path} should be {kind}")


class Page(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "config.json")
        start = {"mood": {"intensity": 1.0}, "llm": {"api_key": "sk-secret"}}
        with open(self.file, "w") as f:
            json.dump(start, f)
        self.saved = dict(config.settings)
        config.settings.clear()
        config.settings.update(json.loads(json.dumps(start)))
        self.patches = [mock.patch.object(config, "CONFIG_FILE", self.file),
                        mock.patch.object(config, "MOOD_INTENSITY", 1.0, create=True),
                        mock.patch.object(config, "_plugins_cfg", {}),
                        mock.patch("ui.settings_pane._after")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        config.settings.clear()
        config.settings.update(self.saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self):
        with open(self.file) as f:
            return json.load(f)

    def _post(self, **data):
        code, _kind, body = settings_web.handle("POST", "/api", json.dumps(dict(data)).encode())
        return code, json.loads(body)

    def test_the_page_carries_its_key(self):
        code, kind, html = settings_web.handle("GET", "/", b"")
        self.assertEqual(code, 200)
        self.assertIn(settings_web.KEY, html)
        self.assertNotIn("__KEY__", html)

    def test_listing_has_everything_and_no_secrets(self):
        code, _kind, body = settings_web.handle("GET", "/api", b"")
        self.assertEqual(code, 200)
        self.assertNotIn("sk-secret", body)
        data = json.loads(body)
        paths = {s["path"]: s for g in data["groups"] for s in g["settings"]}
        self.assertGreaterEqual(len(paths), len(SCHEMA))
        self.assertTrue(paths["llm.api_key"]["has"])
        self.assertIsNone(paths["llm.api_key"]["value"])
        self.assertTrue(paths["mood.intensity"]["basic"])
        self.assertEqual(paths["mood.intensity"]["range"], [0, 2, 0.05])
        self.assertEqual({p["name"] for p in data["presets"]}, set(PRESETS))

    def test_a_change_needs_the_key(self):
        code, out = self._post(action="set", path="mood.intensity", value="0.5")
        self.assertEqual(code, 403)
        code, out = self._post(key="wrong", action="set", path="mood.intensity", value="0.5")
        self.assertEqual(code, 403)
        self.assertEqual(self._file()["mood"]["intensity"], 1.0)

    def test_a_change_is_checked_and_saved(self):
        code, out = self._post(key=settings_web.KEY, action="set", path="mood.intensity", value="0.5")
        self.assertEqual(code, 200, out)
        self.assertEqual(self._file()["mood"]["intensity"], 0.5)
        self.assertEqual(out["entry"]["value"], 0.5)

        code, out = self._post(key=settings_web.KEY, action="set", path="mood.intensity", value="lots")
        self.assertEqual(code, 400)
        self.assertEqual(self._file()["mood"]["intensity"], 0.5)

    def test_background(self):
        bg = os.path.join(self.tmp, "portrait", "backgrounds")
        os.makedirs(bg)
        open(os.path.join(bg, "night room.png"), "wb").close()
        with mock.patch.object(config, "BASE_DIR", self.tmp), \
             mock.patch.object(config, "PORTRAIT_BACKGROUND", "", create=True):
            entry = settings_web.entry("portrait.background")
            self.assertEqual((entry["kind"], entry["choices"]), ("background", ["night room.png"]))
            for value, stored in (("#1A1025", "#1a1025"), ("none", "none"), ("night room.png", "night room.png"),
                                  ("Seasonal", "seasonal"), ("default", "")):
                code, out = self._post(key=settings_web.KEY, action="set", path="portrait.background", value=value)
                self.assertEqual(code, 200, out)
                self.assertEqual(self._file()["portrait"]["background"], stored)
            for bad in ("../config.json", "red", "missing.png", "#12"):
                code, _out = self._post(key=settings_web.KEY, action="set", path="portrait.background", value=bad)
                self.assertEqual(code, 400, bad)
            self.assertEqual(self._file()["portrait"]["background"], "")
            os.makedirs(os.path.join(bg, "seasonal"))
            for f in ("winter-day.png", "winter-night.jpg", "notes.json"):
                open(os.path.join(bg, "seasonal", f), "wb").close()
            self.assertEqual(config.seasonal_backgrounds(), ["winter-day.png", "winter-night.jpg"])

    def test_switches_and_choices(self):
        self._post(key=settings_web.KEY, action="set", path="plugins.twitch.lewd", value=True)
        self.assertIs(self._file()["plugins"]["twitch"]["lewd"], True)
        code, _out = self._post(key=settings_web.KEY, action="set", path="portrait.frame", value="sideways")
        self.assertEqual(code, 400)

    def test_unknown_settings_and_actions_are_refused(self):
        code, _out = self._post(key=settings_web.KEY, action="set", path="nope.nothing", value="1")
        self.assertEqual(code, 400)
        code, _out = self._post(key=settings_web.KEY, action="delete_everything")
        self.assertEqual(code, 400)
        self.assertNotIn("nope", self._file())

    def test_secrets_are_written_but_never_echoed(self):
        code, out = self._post(key=settings_web.KEY, action="set", path="llm.api_key", value="sk-new")
        self.assertEqual(code, 200)
        self.assertEqual(self._file()["llm"]["api_key"], "sk-new")
        self.assertNotIn("sk-new", json.dumps(out))

    def test_reset(self):
        code, out = self._post(key=settings_web.KEY, action="reset", path="mood.intensity")
        self.assertEqual(code, 200)
        self.assertNotIn("intensity", self._file().get("mood", {}))

    def test_a_preset_saves_its_values(self):
        code, out = self._post(key=settings_web.KEY, action="preset", name="assistant")
        self.assertEqual(code, 200, out)
        saved = self._file()
        for path, value in PRESETS["assistant"]["values"].items():
            node = saved
            for part in path.split("."):
                node = node[part]
            self.assertEqual(node, value, path)
        code, _out = self._post(key=settings_web.KEY, action="preset", name="chaos")
        self.assertEqual(code, 400)

    def test_nested_blocks_never_reach_the_page(self):
        config.settings["mcp"] = {"servers": {"bridge": {"headers": {"Authorization": "Bearer sekrit"}}}}
        _code, _kind, body = settings_web.handle("GET", "/api", b"")
        self.assertNotIn("sekrit", body)

    def test_unknown_logins_are_hidden(self):
        config.settings["plugins"] = {"thing": {"token": "tok-123"}}
        with mock.patch.object(config, "_plugins_cfg", config.settings["plugins"]):
            _code, _kind, body = settings_web.handle("GET", "/api", b"")
        self.assertNotIn("tok-123", body)

    def test_a_preset_in_effect_is_marked(self):
        self._post(key=settings_web.KEY, action="preset", name="companion")
        data = json.loads(settings_web.handle("GET", "/api", b"")[2])
        active = {p["name"]: p["active"] for p in data["presets"]}
        self.assertTrue(active["companion"])
        self.assertFalse(active["assistant"])

    def test_pages_cant_be_framed_by_other_sites(self):
        import livefeed

        with open(livefeed.__file__) as f:
            src = f.read()
        self.assertIn("frame-ancestors 'self'", src)


class TerminalPane(unittest.TestCase):
    def test_everyday_first_all_on_a(self):
        from ui import settings_pane
        from ui.shared import view

        view.set_filter, view.set_all = "", False
        everyday = [r[0] for r in settings_pane._rows()]
        self.assertEqual(set(everyday), set(BASIC) & set(settings_pane._all_paths()))
        with mock.patch("ui.settings_pane._refresh"):
            settings_pane.toggle_all()
        try:
            self.assertGreater(len(settings_pane._rows()), len(everyday))
            view.set_all = False
            view.set_filter = "lewd"            # a filter searches everything
            self.assertTrue(any("lewd" in r[0] for r in settings_pane._rows()))
        finally:
            view.set_filter, view.set_all = "", False


if __name__ == "__main__":
    unittest.main()
