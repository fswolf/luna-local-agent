"""Real time beside record time in facts.db: when a fact was true, kept
apart from when she learned it (mind/factstore.py, docs/memory.md)."""
import sqlite3
import tempfile
import unittest
from unittest import mock

from tests.facts_tmp import use_temp_facts


class ValidTime(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.folder = folder
        use_temp_facts(self, folder)
        from mind import factstore, longterm
        self.store, self.longterm = factstore, longterm
        self.guest = mock.patch.object(longterm, "_guest", return_value=None)
        self.guest.start()
        self.addCleanup(self.guest.stop)
        quiet = mock.patch.object(longterm, "_announce", lambda: None)
        quiet.start()
        self.addCleanup(quiet.stop)

    def test_when_keeps_only_real_dates(self):
        w = self.store.when
        self.assertEqual(w("2026-11-14"), "2026-11-14")
        self.assertEqual(w("2026-3"), "2026-03")
        self.assertEqual(w("2019"), "2019")
        for bad in ("last week", "2026-13", "2026-02-30", "yesterday-ish", "", None, "12"):
            self.assertEqual(w(bad), "", bad)
        self.assertRegex(w("today"), r"^\d{4}-\d\d-\d\d$")

    def test_change_keeps_the_old_fact_with_its_end(self):
        self.longterm.add_fact("Ryan's server card is an RX 6950 XT", since="2026-10")
        old, cands = self.longterm.update_fact("server card 6950", "Ryan's server card is an RX 7900 XT",
                                               since="2026-11-14")
        self.assertEqual(old[1], "Ryan's server card is an RX 7900 XT")
        self.assertEqual(self.store.active_facts(), ["Ryan's server card is an RX 7900 XT"])
        past = self.store.history("server card")
        self.assertEqual([(f["active"], f["since"], f["until"]) for f in past],
                         [(False, "2026-10", "2026-11-14"), (True, "2026-11-14", "")])

    def test_mistake_rewrites_in_place(self):
        self.longterm.add_fact("Ryan lives in Lacomb")
        self.longterm.update_fact("lives in Lacomb", "Ryan lives in Lacombe", mistake=True)
        self.assertEqual(self.store.counts(), (1, 0))

    def test_change_without_a_date_falls_back_to_record_time(self):
        self.longterm.add_fact("Ryan streams on Tuesdays")
        self.longterm.update_fact("streams on Tuesdays", "Ryan streams on Thursdays")
        old = [f for f in self.store.history("streams") if not f["active"]][0]
        self.assertEqual((old["since"], old["until"]), ("", ""))
        self.assertTrue(old["retired"])

    def test_restore_clears_the_end(self):
        self.store.add("Ryan has a cat", since="2020")
        self.store.replace("Ryan has a cat", "Ryan has two cats", since="2025")
        retired = self.store.rows(retired=True)[0][0]
        self.store.restore_row(retired)
        self.assertEqual(self.store.row_details([retired]), {retired: ("2020", "", True)})

    def test_prompt_and_tool_show_the_dates(self):
        self.store.add("Ryan's server card is an RX 7900 XT", since="2026-11-14")
        self.store.add("Ryan streams as a VTuber")
        facts = self.store.active_facts()
        known = self.longterm.details(facts)
        shown = [self.longterm.shown(f, known.get(f)) for f in facts]
        self.assertEqual(shown, ["Ryan's server card is an RX 7900 XT (since 2026-11-14)",
                                 "Ryan streams as a VTuber"])

    def test_recall_past_tool(self):
        import tools.memory as tm
        self.store.add("Ryan's server card is an RX 6950 XT")
        self.store.replace("Ryan's server card is an RX 6950 XT", "Ryan's server card is an RX 7900 XT",
                           since="2026-11-14")
        out = tm._recall_facts("server card", past=True)
        self.assertIn("BEFORE: Ryan's server card is an RX 6950 XT", out)
        self.assertIn("to 2026-11-14", out)
        self.assertIn("NOW: Ryan's server card is an RX 7900 XT", out)
        said = tm._remember_fact("Ryan has a Steam Deck", since="last spring")
        self.assertIn("wasn't understood", said)
        self.assertIn("Ryan has a Steam Deck", self.store.active_facts())

    def test_extractor_since_segment(self):
        lm = self.longterm
        self.store.add("Ryan's server card is an RX 6950 XT")
        replies = iter(["REPLACE | Ryan's server card is an RX 6950 XT | Ryan's server card is an RX 7900 XT "
                        "| since 2026-11-14",
                        "NEW | hobby | Since 2019 Ryan has streamed as a VTuber",
                        "NEW | gear | Ryan has a Steam Deck | since last spring"])
        with mock.patch.object(lm, "_ask_extractor", lambda m, p: next(replies)):
            for _ in range(3):
                lm._extract_fact_sqlite("m", "u", "a")
        active = self.store.active_facts()
        self.assertIn("Since 2019 Ryan has streamed as a VTuber", active)
        self.assertIn("Ryan has a Steam Deck", active)
        self.assertNotIn("since last spring", " ".join(active))
        self.assertEqual(self.store.details(active).get("Ryan's server card is an RX 7900 XT"), ("2026-11-14", "", False))   # the extractor guessed it

    def test_a_date_for_something_already_known(self):
        import tools.memory as tm
        self.store.add("Ryan has a cat")
        self.assertIn("Saved", tm._remember_fact("Ryan has a cat", since="2020"))
        self.assertEqual(self.store.details(["Ryan has a cat"]), {"Ryan has a cat": ("2020", "", True)})
        self.assertIn("Not saved", tm._remember_fact("Ryan has a cat", since="2021"))   # a date is never overwritten here
        said = tm._update_fact("has a cat", "Ryan has a cat", since="2019")
        self.assertIn("Unchanged", said)
        self.assertEqual(self.store.counts(), (1, 0))                                  # no history row for nothing
        self.assertEqual(self.store.details(["Ryan has a cat"]), {"Ryan has a cat": ("2019", "", True)})

    def test_booleans_sent_as_words(self):
        import tools.memory as tm
        self.store.add("Ryan streams on Tuesdays")
        self.assertNotIn("NOW:", tm._recall_facts("streams", past="false"))
        self.assertIn("Updated", tm._update_fact("streams on Tuesdays", "Ryan streams on Thursdays", mistake="false"))
        self.assertEqual(self.store.counts(), (1, 1))

    def test_column_added_by_another_process(self):
        real = sqlite3.connect

        class Racing:                    # the memory manager adds the column between our look and our ALTER
            def __init__(self, db):
                self.db = db

            def execute(self, sql, *args):
                if sql.startswith("ALTER TABLE"):
                    raise sqlite3.OperationalError("duplicate column name: valid_from")
                return self.db.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(self.db, name)

        import os
        path = os.path.join(self.folder, "race.db")
        db = real(path)
        db.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, fact TEXT NOT NULL, subject TEXT NOT NULL "
                   "DEFAULT '', created_at TEXT NOT NULL, superseded_at TEXT, superseded_by INTEGER, embedding BLOB)")
        db.commit()
        db.close()
        with mock.patch.object(self.store, "DB_FILE", path), \
                mock.patch.object(self.store.sqlite3, "connect", lambda *a, **k: Racing(real(*a, **k))):
            opened = self.store._open()
            opened.close()

    def test_old_database_gains_the_columns(self):
        import os
        path = os.path.join(self.folder, "old.db")
        db = sqlite3.connect(path)
        db.executescript("CREATE TABLE facts (id INTEGER PRIMARY KEY, fact TEXT NOT NULL, subject TEXT NOT NULL "
                         "DEFAULT '', created_at TEXT NOT NULL, superseded_at TEXT, superseded_by INTEGER, "
                         "embedding BLOB); INSERT INTO facts(fact, created_at) VALUES ('Ryan has a cat', '2026-01-01');")
        db.commit()
        db.close()
        with mock.patch.object(self.store, "DB_FILE", path), mock.patch.object(self.store, "_db", None):
            self.assertEqual(self.store.active_facts(), ["Ryan has a cat"])
            self.assertTrue(self.store.add("Ryan has a dog", since="2024"))
            self.assertEqual(self.store.details(["Ryan has a dog"]), {"Ryan has a dog": ("2024", "", True)})
            self.store._db.close()


if __name__ == "__main__":
    unittest.main()
