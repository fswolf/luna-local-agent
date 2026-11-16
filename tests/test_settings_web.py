"""The settings page (web/settings_web.py) and the presets (config/presets.py):
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
from web import settings_web  # noqa: E402
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

    def test_unpairing_a_station_uses_its_own_field(self):
        # The device went in "key" once, the same field as the page's key,
        # so every unpair was refused as "out of date" and the phone stayed.
        forgotten = []
        with mock.patch("web.station.forget", lambda d: forgotten.append(d) or True), \
             mock.patch("web.station.panel", lambda: {"devices": []}):
            code, out = self._post(key=settings_web.KEY, action="station_forget", device="abc123")
        self.assertEqual(code, 200, out)
        self.assertTrue(out["ok"])
        self.assertEqual(forgotten, ["abc123"])

    def test_the_page_never_lets_a_body_replace_its_key(self):
        _code, _kind, html = settings_web.handle("GET", "/", b"")
        self.assertIn("Object.assign({}, body, {key: KEY})", html)   # the key goes last
        self.assertNotIn("station_forget\", key:", html)
        self.assertIn("freshKey", html)                             # recovers after a restart

    def test_pages_cant_be_framed_by_other_sites(self):
        from web import livefeed

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


def _own_code(root):
    """Luna's own .py files: the root's scripts and her packages - never a
    virtualenv, a model folder or anything else that happens to sit here."""
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if name.endswith(".py"):
            yield path
        elif name != "tests" and os.path.isfile(os.path.join(path, "__init__.py")):
            for folder, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d != "vendor"]
                yield from (os.path.join(folder, f) for f in files if f.endswith(".py"))


class LiveSettings(unittest.TestCase):
    """A setting marked as applying at once must be read from config each
    time. `from config import X` (or X = config.X at the top of a file)
    takes a copy at startup, so the page says "saved" and nothing changes."""

    def test_nothing_copies_a_live_setting(self):
        import ast

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        live = {name: path for path, (name, now) in config.SETTINGS.items() if name and now}
        startup_only = {("main.py", "VOICE"), ("voice/ptt.py", "STT_MODE"),     # a banner; /mode's own copy
                        ("voice/listen.py", "STT_MODE")}                    # /mic's first reading, then kept up
        found = []
        for path in _own_code(root):
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "config":
                    found += [(rel, a.name) for a in node.names if a.name in live]
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    found += [(rel, n.attr) for n in ast.walk(node.value)
                              if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                              and n.value.id == "config" and n.attr in live]
        self.assertEqual([f for f in found if f not in startup_only], [])


class Browse(unittest.TestCase):
    """Browse... by a path setting: a folder browser served by Luna."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "pokemon"))
        os.makedirs(os.path.join(self.dir, ".hidden"))
        for name in ("tetris.gb", "zelda.GBC", "notes.txt"):
            open(os.path.join(self.dir, name), "w").close()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_file_picker_lists_folders_and_its_files(self):
        out = settings_web.browse("plugins.gameboy.rom", self.dir)
        self.assertTrue(out["ok"])
        self.assertEqual([d["name"] for d in out["dirs"]], ["pokemon"])          # no hidden ones
        self.assertEqual([f["name"] for f in out["files"]], ["tetris.gb", "zelda.GBC"])
        self.assertEqual(out["files"][0]["path"], os.path.join(self.dir, "tetris.gb"))

    def test_a_folder_picker_lists_only_folders(self):
        out = settings_web.browse("plugins.gameboy.saves", self.dir)
        self.assertEqual(out["files"], [])
        self.assertEqual(out["parent"], os.path.dirname(self.dir))

    def test_starts_from_the_nearest_folder_that_exists(self):
        out = settings_web.browse("plugins.gameboy.rom", os.path.join(self.dir, "gone", "x.gb"))
        self.assertEqual(out["path"], self.dir)

    def test_only_settings_with_a_button(self):
        self.assertFalse(settings_web.browse("voice", self.dir)["ok"])
        self.assertEqual(settings_web.entry("plugins.gameboy.roms").get("pick"), "folder")
        self.assertNotIn("pick", settings_web.entry("voice"))

    def test_every_picker_is_a_real_path_setting(self):
        for path, (kind, _ext) in settings_web.PICKERS.items():
            self.assertIn(path, SCHEMA)
            self.assertIn(SCHEMA[path][0], ("text", "list"), path)
            self.assertIn(kind, ("file", "folder"), path)

    def test_any_file_when_no_kinds_are_named(self):
        out = settings_web.browse("plugins.zork.interpreter", self.dir)
        self.assertEqual(len(out["files"]), 3)

    def test_needs_the_key(self):
        body = json.dumps({"action": "browse", "setting": "plugins.gameboy.rom", "at": self.dir}).encode()
        status, _ctype, _out = settings_web.handle("POST", "/api", body)
        self.assertEqual(status, 403)
        body = json.dumps({"action": "browse", "setting": "plugins.gameboy.rom", "at": self.dir,
                           "key": settings_web.KEY}).encode()
        status, _ctype, out = settings_web.handle("POST", "/api", body)
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(out)["files"]), 2)


if __name__ == "__main__":
    unittest.main()


class WhoSheIs(unittest.TestCase):
    """agent.json edited as text on the settings page: checked, backed up,
    saved as typed, and in her prompt from the next turn. A temporary file;
    yours is never touched."""

    GOOD = '{\n    "name": "Mira",\n    "personality": "A calm dragon who hoards books.",\n    "traits": ["dry humour"]\n}\n'

    def setUp(self):
        from config import base

        self.base = base
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "agent.json")
        with open(self.file, "w") as f:
            f.write('{"name": "Luna", "personality": "kind"}\n')
        self.before = json.loads(json.dumps(config.agent))
        self.patch = mock.patch.object(config, "AGENT_FILE", self.file)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.base.apply_agent(self.before)          # her real persona back, everywhere
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _post(self, **data):
        code, _kind, body = settings_web.handle("POST", "/api", json.dumps(dict(data, key=settings_web.KEY)).encode())
        return code, json.loads(body)

    def _read(self):
        code, _kind, body = settings_web.handle("GET", "/api/agent", b"")
        self.assertEqual(code, 200)
        return json.loads(body)

    def test_the_file_as_it_is(self):
        got = self._read()
        self.assertEqual(got["text"], '{"name": "Luna", "personality": "kind"}\n')
        self.assertTrue(got["stamp"])

    def test_a_save_is_kept_as_typed_backed_up_and_used_next_turn(self):
        from llm import prompts

        stamp = self._read()["stamp"]
        code, out = self._post(action="agent_save", text=self.GOOD, stamp=stamp)
        self.assertEqual(code, 200, out)
        with open(self.file) as f:
            self.assertEqual(f.read(), self.GOOD)             # your layout, not reformatted
        backups = os.listdir(os.path.join(self.tmp, "backups"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(config.AGENT_NAME, "Mira")
        self.assertEqual(config.agent["traits"], ["dry humour"])
        system, _live = prompts.build_prompt_parts("hi", None, True)
        self.assertIn("You are Mira.", system)
        self.assertIn("hoards books", system)
        self.assertIn("dry humour", system)
        self.assertNotEqual(out["stamp"], stamp)              # the page's next save is against this one

    def test_bad_json_says_where_and_changes_nothing(self):
        before = self._read()
        code, out = self._post(action="agent_save", text='{\n  "name": "Mira",\n  "personality": "x",\n}', stamp=before["stamp"])
        self.assertEqual(code, 400)
        self.assertRegex(out["message"], r"line [34], column")   # 3.13 points at the comma itself
        self.assertEqual(self._read()["text"], before["text"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "backups")))

    def test_valid_json_that_would_break_her(self):
        stamp = self._read()["stamp"]
        for text, words in (('{"name": "Mira"}', "personality"),
                            ('{"personality": "  "}', "personality"),
                            ('["a list"]', "{...}"),
                            ('{"personality": "x", "traits": "one string"}', "traits"),
                            ('{"personality": "x", "name": 5}', "name"),
                            ('{"personality": "x", "user": "Ryan"}', "user")):
            code, out = self._post(action="agent_save", text=text, stamp=stamp)
            self.assertEqual(code, 400, text)
            self.assertIn(words, out["message"], text)
        self.assertEqual(config.AGENT_NAME, self.before.get("name") or config.AGENT_NAME)

    def test_a_hand_edit_since_the_page_loaded_isnt_overwritten(self):
        stamp = self._read()["stamp"]
        with open(self.file, "w") as f:
            f.write('{"name": "Luna", "personality": "edited by hand"}\n')
        os.utime(self.file, ns=(int(stamp) + 10**9, int(stamp) + 10**9))
        code, out = self._post(action="agent_save", text=self.GOOD, stamp=stamp)
        self.assertEqual(code, 400)
        self.assertIn("changed outside", out["message"])
        with open(self.file) as f:
            self.assertIn("edited by hand", f.read())

    def test_saving_needs_the_key(self):
        code, _kind, body = settings_web.handle("POST", "/api", json.dumps(
            {"action": "agent_save", "text": self.GOOD}).encode())
        self.assertEqual(code, 403)
        with open(self.file) as f:
            self.assertNotIn("Mira", f.read())

    def test_the_page_has_the_editor(self):
        _code, _kind, html = settings_web.handle("GET", "/", b"")
        self.assertIn('id="agenttext"', html)


class WhoSheIsAfterwards(unittest.TestCase):
    """What follows a save: backups that don't pile up or overwrite each
    other, the file's permissions, and the parts of her that read her name
    or yours later than at start."""

    def setUp(self):
        from config import base

        self.base = base
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "agent.json")
        with open(self.file, "w") as f:
            f.write('{"name": "Luna", "personality": "kind"}\n')
        self.before = json.loads(json.dumps(config.agent))
        self.patch = mock.patch.object(config, "AGENT_FILE", self.file)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.base.apply_agent(self.before)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _save(self, name, user=""):
        text = json.dumps({"name": name, "personality": "kind", "user": {"name": user}})
        ok, message = settings_web.agent_save(text)
        self.assertTrue(ok, message)

    def test_backups_dont_overwrite_each_other_and_dont_pile_up(self):
        with mock.patch.object(settings_web, "AGENT_BACKUPS", 3):
            for n in range(5):                        # all inside the same second
                self._save(f"Name{n}")
        folder = os.path.join(self.tmp, "backups")
        kept = os.listdir(folder)
        self.assertEqual(len(kept), 3)
        names = []
        for f in kept:
            with open(os.path.join(folder, f)) as fh:
                names.append(json.load(fh)["name"])
        names.sort()
        self.assertEqual(names, ["Name1", "Name2", "Name3"])    # the newest three versions before Name4

    def test_a_private_file_stays_private(self):
        os.chmod(self.file, 0o600)
        self._save("Mira")
        self.assertEqual(os.stat(self.file).st_mode & 0o777, 0o600)

    def test_too_long_is_refused(self):
        ok, message = settings_web.agent_save('{"personality": "' + "x" * settings_web.AGENT_MAX + '"}')
        self.assertFalse(ok)

    def test_chat_rooms_answer_to_her_new_name(self):
        from core import chatroom

        room = chatroom.ChatRoom("t", "Ryan", {})
        self.assertTrue(room._named().search("hey luna"))
        self._save("Mira")
        self.assertTrue(room._named().search("hey mira"))
        self.assertFalse(room._named().search("hey luna"))

    def test_her_scratch_check_knows_your_new_name(self):
        from mind import thoughtlog

        self._save("Luna", user="Sam")
        self.assertTrue(thoughtlog._scratch_opening().match("Okay, Sam wants a timer"))
