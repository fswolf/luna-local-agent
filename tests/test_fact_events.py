"""Her memory's audit log (fact_events in mind/factstore.py): every change
to a fact is a row saying what, when and who; a forget leaves the date and
none of the words, there or anywhere the sweep reaches.

    python -m unittest discover tests        (from the repo folder)
"""
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

from tests.facts_tmp import use_temp_facts


class Log(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        use_temp_facts(self, self.dir)
        from mind import factstore, forgetting
        self.store, self.fg = factstore, forgetting
        p = mock.patch.object(forgetting, "_names", lambda: {"ryan", "luna"})
        p.start()
        self.addCleanup(p.stop)

    def log(self, fact_id=None):
        """[(action, fact_id, fact, detail, by)], oldest first."""
        return [e[2:] for e in reversed(self.store.events(fact_id=fact_id))]

    def words(self):
        db = sqlite3.connect(self.store.DB_FILE)
        try:
            return " ".join(f + " " + d for f, d in db.execute("SELECT fact, detail FROM fact_events"))
        finally:
            db.close()

    def test_each_kind_of_change(self):
        s = self.store
        with s.acting("her tools"):
            s.add("Ryan has a Radeon card", sure=False)
            s.confirm("Ryan has a Radeon card")
            s.set_since("Ryan has a Radeon card", "2026-11")
            s.update("Ryan has a Radeon card", "Ryan has a Radeon RX 7900 XT")
            s.replace("Ryan has a Radeon RX 7900 XT", "Ryan has a Radeon RX 9070", since="2026-11-14")
        with s.acting("memory page"):
            s.retire_row(2)
            s.restore_row(2)
            s.set_row(2, "Ryan has an RX 9070 XT", "hardware")
        self.assertEqual([(a, i, by) for a, i, _f, _d, by in self.log()], [
            ("added", 1, "her tools"), ("confirmed", 1, "her tools"), ("dated", 1, "her tools"),
            ("corrected", 1, "her tools"), ("replaced", 2, "her tools"), ("retired", 1, "her tools"),
            ("retired", 2, "memory page"), ("restored", 2, "memory page"), ("edited", 2, "memory page")])
        details = {(a, i): d for a, i, _f, d, _by in self.log()}
        self.assertEqual(details[("added", 1)], "not sure")
        self.assertEqual(details[("corrected", 1)], "was: Ryan has a Radeon card")
        self.assertEqual(details[("replaced", 2)], "was #1, changed 2026-11-14")
        self.assertEqual(details[("retired", 1)], "replaced by #2")
        self.assertEqual(details[("edited", 2)], "was: Ryan has a Radeon RX 9070; subject (none) -> hardware")
        self.assertEqual([a for a, *_ in self.log(fact_id=2)], ["replaced", "retired", "restored", "edited"])

    def test_nothing_changed_writes_nothing(self):
        s = self.store
        s.add("Ryan likes tea")
        s.add("Ryan likes tea")                 # known already, and confirmed
        s.confirm_row(1)                        # confirmed already
        s.restore_row(1)                        # active already
        s.set_row(1, "Ryan likes tea", "")      # the same words
        self.assertEqual([a for a, *_ in self.log()], ["added"])

    def test_who_is_per_thread(self):
        s, seen = self.store, []
        with s.acting("her tools"):
            t = threading.Thread(target=lambda: seen.append(s._by.get()))
            t.start()
            t.join()
            s.add("Ryan likes tea")
        s.add("Ryan likes coffee")
        self.assertEqual(seen, [""])            # a new thread starts as nobody, not as her
        self.assertEqual([by for *_, by in self.log()], ["her tools", "unknown"])

    def test_a_forget_keeps_the_date_and_none_of_the_words(self):
        s = self.store
        s.add("Ryan works at the bakery")
        s.update("Ryan works at the bakery", "Ryan works at the bakery downtown")
        s.add("Ryan likes tea")
        with s.acting("her tools"):
            s.remove("Ryan works at the bakery downtown")
        self.assertNotIn("bakery", self.words())
        self.assertEqual([(a, i, f) for a, i, f, _d, _by in self.log(fact_id=1)],
                         [("added", 1, ""), ("corrected", 1, ""), ("forgotten", 1, "")])
        self.assertIn(("added", 2, "Ryan likes tea", "", "unknown"), self.log())   # the rest untouched

    def test_the_sweep_reaches_the_log(self):
        """A reworded copy forgotten by fingerprint, and old words kept in a
        correction on a row that wasn't deleted ("was: ...")."""
        s = self.store
        s.add("Ryan worked at the bakery")
        s.add("Ryan used to bake")
        s.update("Ryan used to bake", "Ryan works at the bakery")
        s.update("Ryan works at the bakery", "Ryan works from home")     # row 2 stays, its history had it
        tombs = [self.fg.marks("Ryan works at the bakery")]
        self.fg._facts(tombs)                   # row 1 deleted: its rows emptied as it went
        self.assertEqual(self.fg._log(tombs), 2)    # row 2's correction to it, and the one away from it
        self.assertNotIn("bakery", self.words())
        self.assertIn("Ryan works from home", self.words())     # the new words stay, the "was:" went
        self.assertIn("was: Ryan used to bake", self.words())

    def test_unforgetting_is_logged(self):
        s = self.store
        s.bury(self.fg.marks("Ryan works at the bakery"))
        with s.acting("her tools"):
            self.assertTrue(s.add("Ryan works at the bakery", again=True))
        self.assertEqual([(a, by) for a, _i, _f, _d, by in self.log()],
                         [("unforgotten", "her tools"), ("added", "her tools")])
        s.bury(self.fg.marks("Ryan likes tea"))
        s.unbury_all()
        self.assertEqual(self.log()[-1][0], "unforgotten")

    def test_the_log_is_trimmed(self):
        s = self.store
        with mock.patch.object(s, "KEEP_EVENTS", 3):
            for n in range(6):
                s.add(f"Ryan owns {n} cats")
        self.assertEqual([f for _a, _i, f, _d, _by in self.log()],
                         ["Ryan owns 3 cats", "Ryan owns 4 cats", "Ryan owns 5 cats"])


class Callers(unittest.TestCase):
    """The names in the log come from whoever drives the change."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        use_temp_facts(self, self.dir)
        from mind import factstore, longterm
        self.store, self.lt = factstore, longterm
        for name, value in (("_guest", lambda: None), ("_announce", lambda: None)):
            p = mock.patch.object(longterm, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_her_tool(self):
        import tools
        self.assertIn("Saved", tools._REGISTRY["remember_fact"]["run"](fact="Ryan likes tea"))
        self.assertEqual(self.store.events()[0][2:], ("added", 1, "Ryan likes tea", "", "her tools"))

    def test_the_memory_page(self):
        import importlib.util
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location("manager_t", os.path.join(here, "memory-manager", "manager.py"))
        manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manager)
        manager.apply("add", {"fact": "Ryan likes tea"})
        manager.apply("retire", {"id": 1})
        self.assertEqual([(e[2], e[6]) for e in self.store.events()], [("retired", "memory page"), ("added", "memory page")])
        self.assertEqual(manager.state()["history"][0]["action"], "retired")


if __name__ == "__main__":
    unittest.main()
