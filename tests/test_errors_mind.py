"""Error handling in mind/: the failures that used to print over the
screen, loop, overflow or lose a file, each held to what it does now.
Temp files only; nothing here reaches a real server.

    python -m unittest tests.test_errors_mind        (from the repo folder)
"""
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import urllib3  # noqa: E402

import config  # noqa: E402
from core import logbook  # noqa: E402
from mind import factstore, knowledge, longterm, mood, notebook, pages, reflect, webpage, websearch  # noqa: E402
from mind.mood import core as mood_core, files as mood_files, saving, walkaway  # noqa: E402

INF = float("inf")


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def patch(self, *args, **kw):
        p = mock.patch.object(*args, **kw) if not isinstance(args[0], str) else mock.patch(*args, **kw)
        value = p.start()
        self.addCleanup(p.stop)
        return value


# ---------------------------------------------------------------------------
# Mood
# ---------------------------------------------------------------------------
class MoodNumbers(Temp):
    def setUp(self):
        super().setUp()
        self.patch(config, "MOOD_ENABLED", True)
        self.patch(config, "MOOD_INTENSITY", 1.0, create=True)
        self.patch(config, "MOOD_WALK_AWAY", True, create=True)
        self.patch("mind.mood.saving.STATE_FILE", os.path.join(self.dir, "mood.json"))
        self.patch("mind.mood.show._announce", lambda: None)
        self.timers = []
        test = self

        class FakeTimer:
            def __init__(self, interval, fn):
                test.timers.append(interval)
                self.daemon = False

            def start(self):
                pass

        self.patch(walkaway.threading, "Timer", FakeTimer)
        mood.reset()
        self.addCleanup(lambda: mood_core.S.away_state.update(until=0.0, said=False, hostile=0))

    def hostile(self):
        with mock.patch("mind.mood.appraise._appraise", return_value=(0, 0, -1, None, 0)):
            mood._apply_exchange("you're useless", "ok", "model")

    def test_infinite_walk_away_after_does_not_raise(self):
        """int(inf) here printed a traceback over the screen every turn."""
        self.patch(config, "MOOD_WALK_AWAY_AFTER", INF, create=True)
        self.hostile()                      # no exception, no thread traceback
        self.assertEqual(self.timers, [])   # 1000 hostile turns, not one

    def test_infinite_walk_away_minutes_is_clamped(self):
        self.patch(config, "MOOD_WALK_AWAY_AFTER", 1, create=True)
        self.patch(config, "MOOD_WALK_AWAY_MINUTES", INF, create=True)
        self.hostile()
        self.assertEqual(len(self.timers), 1)
        self.assertLessEqual(self.timers[0], 24 * 3600 + 1)
        self.assertLess(walkaway.away(), 24 * 3600 + 1)

    def test_exchange_thread_logs_instead_of_raising(self):
        with mock.patch("mind.mood.appraise._appraise", side_effect=RuntimeError("boom")), \
                mock.patch.object(logbook, "exception") as logged:
            mood._apply_exchange("hi", "hello", "model")
        logged.assert_called_once()

    def test_bad_grudge_minutes_in_moods_json(self):
        self.patch(config, "MOOD_WALK_AWAY", False, create=True)
        self.patch("mind.mood.core._extra", lambda name: {"row": ["a", "b", "c"], "minutes": "20m"}
                   if name == "grudge" else dict(mood_files._FALLBACK[name]))
        mood_core.S.warmth = -0.9
        self.hostile()
        self.assertLessEqual(mood_core._grudging(), 24 * 3600)


class GrudgeForever(Temp):
    def setUp(self):
        super().setUp()
        self.file = os.path.join(self.dir, "mood.json")
        self.patch("mind.mood.saving.STATE_FILE", self.file)
        self.patch("mind.mood.show._announce", lambda: None)
        self.addCleanup(setattr, mood_core.S, "grudge_until", 0.0)

    def test_save_survives_an_infinite_grudge(self):
        """round(inf) in _save failed every typed turn with OverflowError."""
        mood_core.S.grudge_until = INF
        saving._save()
        with open(self.file) as f:
            saved = json.load(f)
        self.assertLessEqual(saved["grudge_until"], time.time() + 24 * 3600 + 5)
        self.assertLessEqual(mood.layers()["grudge"], 24 * 3600)

    def test_save_survives_nan(self):
        mood_core.S.energy = float("nan")
        try:
            saving._save()          # logged, not raised
        finally:
            mood_core.S.energy = 0.0

    def test_restore_clamps_infinity_from_the_file(self):
        with open(self.file, "w") as f:
            f.write('{"energy": 0, "warmth": 0, "desire": 0, "grudge_until": Infinity, "at": %f}' % time.time())
        self.assertTrue(saving._restore())
        self.assertLessEqual(mood_core.S.grudge_until, time.time() + 24 * 3600 + 5)

    def test_set_mood_grudge_is_clamped(self):
        mood.set_mood(grudge_minutes=1e300)
        self.assertLessEqual(mood_core.S.grudge_until, time.time() + 24 * 3600 + 5)


class MoodsFile(unittest.TestCase):
    def test_non_number_edge_is_named(self):
        data = json.loads(json.dumps(mood_files._FALLBACK))
        data["energy"]["edges"] = ["low", 0.35]
        with self.assertRaises(ValueError) as caught:
            mood_files._check(data)
        self.assertIn("energy.edges", str(caught.exception))

    def test_bad_numbers_fall_back_at_use(self):
        data = json.loads(json.dumps(mood_files._FALLBACK))
        data["lewd"]["enter"] = "high"
        data["states"] = {"calm": {"voice": {"speed": "fast", "pitch": None}, "face": {"smile": "big"}}}
        with mock.patch.object(mood_files, "moods", return_value=data), \
                mock.patch("mind.mood.show.moods", return_value=data), \
                mock.patch("mind.mood.core.moods", return_value=data), \
                mock.patch.object(config, "MOOD_ENABLED", True), \
                mock.patch.object(config, "MOOD_VOICE", True, create=True):
            mood.label()
            speed, pitch = mood.voice_tint()
            self.assertTrue(0.9 < speed < 1.1)
            mood.face()


# ---------------------------------------------------------------------------
# memory.json
# ---------------------------------------------------------------------------
class MemoryFile(Temp):
    def setUp(self):
        super().setUp()
        self.file = os.path.join(self.dir, "memory.json")
        self.patch(longterm, "MEMORY_FILE", self.file)
        p = mock.patch.dict(longterm.memory, {"long_term_facts": []}, clear=True)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.dict(longterm._disk, {"mtime": None, "blocked": ""})
        p.start()
        self.addCleanup(p.stop)
        self.patch(longterm, "backend", lambda: "json")
        self.patch(longterm, "_guest", lambda: None)
        self.patch(longterm, "_announce", lambda: None)
        self.told = self.patch(logbook, "tell")

    def write(self, text):
        with open(self.file, "w") as f:
            f.write(text)
        os.utime(self.file, (time.time() + 5, time.time() + 5))     # a different mtime

    def read(self):
        with open(self.file) as f:
            return json.load(f)

    def test_unreadable_file_is_kept_before_it_is_written_over(self):
        self.write('{"long_term_facts": ["Ryan lives in Lacombe", ')    # half a file
        self.assertTrue(longterm.add_fact("Ryan has a cat named Mew"))
        kept = [n for n in os.listdir(self.dir) if n.startswith("memory.json.bad-")]
        self.assertEqual(len(kept), 1)
        with open(os.path.join(self.dir, kept[0])) as f:
            self.assertIn("Lacombe", f.read())
        self.assertEqual(self.read()["long_term_facts"], ["Ryan has a cat named Mew"])
        self.told.assert_called()

    def test_edits_made_elsewhere_are_kept(self):
        """The memory manager's edits used to be undone by the next save."""
        longterm.add_fact("Ryan streams as a VTuber")
        self.write(json.dumps({"long_term_facts": ["Ryan streams as a VTuber", "Ryan uses Fedora"],
                               "user_preferences": {"tone": "short"}}))
        longterm.add_fact("Ryan has a cat named Mew")
        saved = self.read()
        self.assertEqual(saved["long_term_facts"],
                         ["Ryan streams as a VTuber", "Ryan uses Fedora", "Ryan has a cat named Mew"])
        self.assertEqual(saved["user_preferences"], {"tone": "short"})

    def test_failed_write_leaves_the_old_file(self):
        longterm.add_fact("Ryan streams as a VTuber")
        with mock.patch.object(longterm.json, "dump", side_effect=OSError("disk full")):
            longterm.add_fact("Ryan has a cat named Mew")
        self.assertEqual(self.read()["long_term_facts"], ["Ryan streams as a VTuber"])

    def test_extraction_thread_never_raises(self):
        class Inline:
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                self.target()

        with mock.patch.object(config, "LONG_TERM_MEMORY_ENABLED", True), \
                mock.patch.object(longterm.threading, "Thread", Inline), \
                mock.patch.object(longterm, "_extract_fact", side_effect=sqlite3.OperationalError("locked")), \
                mock.patch.object(logbook, "exception") as logged:
            longterm.extract_in_background("model", "hi", "hello")
        logged.assert_called_once()


# ---------------------------------------------------------------------------
# facts.db
# ---------------------------------------------------------------------------
class FactsDb(Temp):
    def setUp(self):
        super().setUp()
        self.patch(factstore, "DB_FILE", os.path.join(self.dir, "facts.db"))
        self.patch(factstore, "_db", None)
        self.patch(factstore, "_unavailable", None)
        self.patch(logbook, "tell")

    def tearDown(self):
        if factstore._db is not None:
            factstore._db.close()

    def test_corrupt_file_means_unavailable_not_a_crash(self):
        with open(factstore.DB_FILE, "wb") as f:
            f.write(b"this is not a database" * 100)
        self.assertFalse(factstore.available())
        self.assertTrue(factstore.why_unavailable())

    def test_failed_replace_rolls_back(self):
        if not factstore.available():
            self.skipTest("no FTS5 in this sqlite")
        factstore.add("Ryan has a 6950 XT")
        factstore._db.execute("CREATE TRIGGER no_retire BEFORE UPDATE OF superseded_at ON facts "
                              "BEGIN SELECT RAISE(ABORT, 'nope'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            factstore.replace("Ryan has a 6950 XT", "Ryan has a 7900 XTX")
        self.assertFalse(factstore._db.in_transaction)
        self.assertEqual(factstore.active_facts(), ["Ryan has a 6950 XT"])


# ---------------------------------------------------------------------------
# Notebook, reflection
# ---------------------------------------------------------------------------
class Bookkeeping(Temp):
    def test_strict_get_raises_on_a_db_error(self):
        # a directory where the file should be: sqlite can't open it
        self.patch(notebook, "DB_FILE", self.dir)
        self.assertEqual(notebook.get("tidy_done", []), [])
        with self.assertRaises(sqlite3.Error):
            notebook.get("tidy_done", [], strict=True)

    def test_tidy_does_not_overwrite_its_list_on_a_db_error(self):
        self.patch(reflect, "_yield", lambda: None)
        with mock.patch.object(notebook, "get", side_effect=sqlite3.OperationalError("locked")), \
                mock.patch.object(notebook, "put") as put, \
                mock.patch("mind.longterm.backend", return_value="sqlite"), \
                mock.patch("mind.factstore.available", return_value=True), \
                mock.patch("mind.factstore.rows", return_value=[]):
            with self.assertRaises(sqlite3.Error):
                reflect.tidy_facts("model")
        put.assert_not_called()


class ReflectBackoff(Temp):
    def setUp(self):
        super().setUp()
        self.patch(reflect, "_yield", lambda: None)
        self.patch(reflect, "_failed", {})
        self.patch(reflect, "_feeling_tries", {})
        self.patch(config, "SELF_EPISODES", True, create=True)
        self.patch(notebook, "played_without_feeling", return_value=[("zork", "Zork", "I got eaten by a grue.")])
        self.patch(notebook, "set_game_feeling")

    def test_an_empty_feeling_is_not_asked_for_ever(self):
        asked = self.patch(reflect, "_ask", return_value="")
        for _ in range(10):
            reflect.feel_about_games("model")
        self.assertEqual(asked.call_count, reflect.FEELING_TRIES)

    def test_a_failed_job_rests(self):
        self.patch(reflect, "_ask", side_effect=ConnectionError("server down"))
        reflect.feel_about_games("model")
        self.assertTrue(reflect._resting("games"))
        self.assertFalse(reflect._resting("episodes"))

    def test_dream_due_with_huge_hours(self):
        self.patch(config, "SELF_REFLECT_HOURS", INF, create=True)
        with mock.patch.object(notebook, "get", side_effect=lambda k, d=None, **kw:
                               "2020-01-01T00:00:00" if k == "dream_at" else d):
            self.assertIn(reflect._dream_due(), (True, False))

    def test_idle_minutes_clamped(self):
        self.patch(config, "SELF_IDLE_MINUTES", INF, create=True)
        self.assertEqual(reflect._idle_minutes(), 7 * 24 * 60)


# ---------------------------------------------------------------------------
# Knowledge watcher, pages, the web
# ---------------------------------------------------------------------------
class Stop(Exception):
    pass


class KnowledgeWatch(unittest.TestCase):
    def test_watch_survives_and_clamps(self):
        waits = []

        def wait(seconds):
            waits.append(seconds)
            raise Stop()

        with mock.patch.object(knowledge, "enabled", return_value=True), \
                mock.patch.object(knowledge, "index", side_effect=RuntimeError("boom")), \
                mock.patch.object(knowledge._wake, "wait", side_effect=wait), \
                mock.patch.object(config, "KNOWLEDGE_RESCAN_MINUTES", INF, create=True), \
                mock.patch.object(logbook, "exception") as logged:
            with self.assertRaises(Stop):
                knowledge._watch()
        logged.assert_called_once()
        self.assertEqual(waits, [24 * 3600])


class PagesLimit(unittest.TestCase):
    def test_infinite_pages_in_prompt(self):
        with mock.patch.object(pages, "enabled", return_value=True), \
                mock.patch.object(config, "current", return_value=INF), \
                mock.patch.object(pages, "pages", return_value={}):
            self.assertEqual(pages.relevant("hello"), [])


class WebFetch(unittest.TestCase):
    def test_raw_read_errors_are_caught(self):
        response = mock.Mock(status_code=200, headers={"Content-Type": "text/html"})
        response.raw.read.side_effect = urllib3.exceptions.ReadTimeoutError(None, "x", "read timed out")
        with mock.patch.object(webpage, "_tidy_url", return_value=("https://example.com/", "")), \
                mock.patch.object(webpage, "_get", return_value=(response, "https://example.com/")):
            text, why = webpage.fetch("https://example.com/")
        self.assertIsNone(text)
        self.assertIn("download failed", why)


class WebSearch(unittest.TestCase):
    def test_missing_package_does_not_print(self):
        out = io.StringIO()
        with mock.patch.dict(sys.modules, {"ddgs": None}), \
                mock.patch.object(logbook, "tell") as told, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.assertEqual(websearch.search("weather", 3), [])
        self.assertEqual(out.getvalue(), "")
        told.assert_called_once()


if __name__ == "__main__":
    unittest.main()
