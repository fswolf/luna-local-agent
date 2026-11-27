"""Pinned facts (mind/factstore.py pin_row): always in her prompt, and the
background (the extractor, the overnight tidy) never rewrites or retires
them. Throwaway facts.db.

    python -m unittest discover tests        (from the repo folder)
"""
import sqlite3
import tempfile
import unittest
from unittest import mock

import config
from tests.facts_tmp import use_temp_facts


class Pinned(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        use_temp_facts(self, self.dir)
        from mind import factstore, longterm
        self.s, self.lt = factstore, longterm
        with factstore.acting("her tools"):
            for f in ("Ryan's wife is Shannon", "The VM is at 192.168.0.186", "Ryan likes Zork",
                      "Ryan streams on Fridays", "Ryan's cat is called Mew"):
                factstore.add(f)
        self.ids = {f: i for i, f, *_ in factstore.rows()}

    def test_pin_unpin_and_the_log(self):
        s, i = self.s, self.ids["Ryan's wife is Shannon"]
        with s.acting("you"):
            self.assertEqual(s.pin_row(i), "pinned")
            self.assertEqual(s.pin_row(i), "already")
            self.assertEqual(s.pinned_facts(), ["Ryan's wife is Shannon"])
            self.assertEqual(s.pin_row(i, False), "unpinned")
        self.assertEqual(s.pinned_facts(), [])
        self.assertEqual([e[2] for e in s.events(fact_id=i)][:2], ["unpinned", "pinned"])
        self.assertEqual(s.pin_row(999), "missing")

    def test_a_cap(self):
        s = self.s
        with mock.patch.object(config, "LONG_TERM_MEMORY_PINNED_MAX", 2, create=True):
            ids = sorted(self.ids.values())
            self.assertEqual([s.pin_row(i) for i in ids[:3]], ["pinned", "pinned", "full"])

    def test_always_in_her_prompt_never_a_guests(self):
        s, lt = self.s, self.lt
        s.pin_row(self.ids["Ryan's wife is Shannon"])
        with mock.patch.object(config, "LONG_TERM_MEMORY_CONTEXT_FACTS", 2), \
             mock.patch.object(lt, "_relevant", return_value=["Ryan likes Zork"]):
            got = lt.relevant_facts("what games do I like")
            self.assertEqual(got, ["Ryan's wife is Shannon", "Ryan likes Zork"])   # oldest first
            with mock.patch.object(lt, "_guest", return_value="shannon"):
                self.assertEqual(lt.relevant_facts("hi"), ["Ryan likes Zork"])

    def test_the_background_leaves_it_alone(self):
        s = self.s
        vm = self.ids["The VM is at 192.168.0.186"]
        s.pin_row(vm)
        for who in ("extractor", "tidy"):
            with s.acting(who):
                self.assertFalse(s.replace("The VM is at 192.168.0.186", "The VM is at 192.168.0.190"))
                self.assertFalse(s.update("The VM is at 192.168.0.186", "The VM is at .186"))
                self.assertFalse(s.retire_row(vm))
                self.assertFalse(s.set_row(vm, "The VM moved", ""))
        self.assertEqual(s.pinned_facts(), ["The VM is at 192.168.0.186"])

    def test_you_or_she_can_change_it_and_the_pin_follows(self):
        s = self.s
        s.pin_row(self.ids["The VM is at 192.168.0.186"])
        with s.acting("her tools"):
            self.assertTrue(s.replace("The VM is at 192.168.0.186", "The VM is at 192.168.0.190"))
        self.assertEqual(s.pinned_facts(), ["The VM is at 192.168.0.190"])

    def test_an_old_facts_db_gets_the_column(self):
        s = self.s
        s._db.close()
        db = sqlite3.connect(s.DB_FILE)
        db.executescript("DROP TABLE facts_fts; CREATE TABLE f2 AS SELECT id, fact, subject, created_at, "
                         "superseded_at, superseded_by, embedding, valid_from, valid_to, trust FROM facts; "
                         "DROP TABLE facts; ALTER TABLE f2 RENAME TO facts;")
        db.commit()
        db.close()
        with mock.patch.object(s, "_db", None):
            self.assertEqual(s.pin_row(self.ids["Ryan likes Zork"]), "pinned")
            s._db.close()

    def test_a_guest_cant_pin(self):
        import tools
        with mock.patch.object(self.lt, "_guest", return_value="shannon"):
            self.assertIn("a guest's aren't pinned", tools.call("pin_fact", '{"about": "Shannon"}'))
        self.assertEqual(self.s.pinned_facts(), [])

    def test_her_tool(self):
        import tools
        out = tools.call("pin_fact", '{"about": "Shannon"}')
        self.assertIn("Pinned: Ryan's wife is Shannon", out)
        self.assertIn("Unpinned", tools.call("pin_fact", '{"about": "Shannon", "pin": false}'))


class Tidy(unittest.TestCase):
    """The overnight tidy-up and a pinned fact: a duplicate of it goes, a
    contradiction against it leaves both."""
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        use_temp_facts(self, self.dir)
        from mind import factstore, notebook, reflect
        self.s, self.r = factstore, reflect
        factstore.add("The VM is at 192.168.0.186")
        factstore.add("Ryan's VM uses 192.168.0.186")
        self.a, self.b = sorted(i for i, *_ in factstore.rows())
        factstore.pin_row(self.a)
        for target, kw in ((notebook, {"get": lambda k, d=None, strict=False: d}), (notebook, {"put": lambda *a: None}),
                           (reflect, {"_yield": lambda: None})):
            for name, fn in kw.items():
                p = mock.patch.object(target, name, fn)
                p.start()
                self.addCleanup(p.stop)

    def tidy(self, verdict):
        rows = sorted(self.s.rows(), key=lambda r: r[0])
        with mock.patch.object(self.r, "_pairs", return_value=[(1.0, rows[0], rows[1])]), \
             mock.patch.object(self.r, "_ask", return_value=verdict), \
             mock.patch("mind.longterm.ready", return_value=True):
            return self.r.tidy_facts("model")

    def test_a_duplicate_of_a_pinned_fact_goes(self):
        self.tidy("SAME: The VM's address is 192.168.0.186")
        self.assertEqual([f for _i, f, *_ in self.s.rows()], ["The VM is at 192.168.0.186"])

    def test_a_contradiction_never_retires_the_pin_and_he_is_told(self):
        changes = self.tidy("CONFLICT: B")
        self.assertEqual(len(self.s.rows()), 2)
        self.assertEqual(self.s.pinned_facts(), ["The VM is at 192.168.0.186"])
        self.assertTrue(changes and changes[0].startswith("kept pinned"))
        shown = []
        self.r._shout(shown.append)("Fact cleanup:\n  " + changes[0])
        self.assertEqual(len(shown), 1)

    def test_a_contradiction_in_its_favour_retires_the_other(self):
        self.tidy("CONFLICT: A")
        self.assertEqual([f for _i, f, *_ in self.s.rows()], ["The VM is at 192.168.0.186"])

    def test_a_same_verdict_that_isnt_about_both_changes_nothing(self):
        self.tidy("SAME: Ryan likes cheese")
        self.assertEqual(len(self.s.rows()), 2)

    def test_two_pins_are_never_asked_about(self):
        self.s.pin_row(self.b)
        rows = sorted(self.s.rows(), key=lambda r: r[0])
        with mock.patch.object(self.r, "_pairs", return_value=[(1.0, rows[0], rows[1])]), \
             mock.patch.object(self.r, "_ask") as ask, \
             mock.patch("mind.longterm.ready", return_value=True):
            self.r.tidy_facts("model")
        ask.assert_not_called()


if __name__ == "__main__":
    unittest.main()
