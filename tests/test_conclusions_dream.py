"""The night: once a night in her quiet hours (mind/reflect.py) she goes over
everything she's concluded (mind/conclusions.py dream): merges duplicates,
sets aside the older of two that contradict, lets guesses nothing backed up
fade. And a later conversation showing one again backs it up. No model.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest import mock

from tests.offline import FAKE  # noqa: F401  (first: no real servers)
from tests.test_conclusions import Base, ago, turns


def chat(n=8, start=None):
    return turns(*[(f"thing {i}", f"answer {i}") for i in range(n)], start=start)


class Backing(Base):
    def test_again_and_a_rewording_back_it_up(self):
        self.run_pass(chat(), "INFERRED: Ryan wants the root cause of a bug. (#1, #2)")
        first = self.c.rows()[0]
        self.assertEqual((first["backed"], len(first["sources"])), ("", 2))
        later = chat(8, start=ago(hours=1))
        self.run_pass(later, "AGAIN: C1 (#3, #4)\nINFERRED: Ryan wants the root cause of every bug. (#5, #6)")
        r = self.c.get(first["id"])
        at = [e["at"] for e in later if e["role"] == "user"]
        self.assertTrue(r["backed"])
        self.assertEqual(r["sources"], sorted(first["sources"] + at[2:6]))
        self.assertEqual(len(self.c.rows()), 1)                 # the rewording backed it, wasn't added
        self.assertIn("AGAIN: C<number>", self.prompts[0])


class Fading(Base):
    def add(self, text, kind, created, backed=""):
        return self.c._run(lambda c: c.execute(
            "INSERT INTO conclusions (person, text, kind, sources, created, backed) VALUES (?,?,?,?,?,?)",
            (self.c.OWNER, text, kind, "[]", created, backed)).lastrowid)

    def test_guesses_nothing_backed_up_fade_and_said_ones_dont(self):
        old = ago(days=self.c.FADE_DAYS + 1)
        guess = self.add("Ryan likes long answers", "inferred", old)
        said = self.add("Ryan lives in Alberta", "said", ago(days=400))
        backed = self.add("Ryan wants root causes", "inferred", ago(days=300), ago(days=10))
        stale = self.add("Ryan works nights", "inferred", ago(days=400), ago(days=self.c.FADE_BACKED_DAYS + 1))
        fresh = self.add("Ryan prefers Fedora", "inferred", ago(days=3))
        self.assertEqual(sorted(self.c.fade()), ["Ryan likes long answers", "Ryan works nights"])
        self.assertEqual(sorted(r["id"] for r in self.c.rows()), sorted([said, backed, fresh]))
        why = self.c.get(guess)["why"]
        self.assertEqual(why, f"faded: nothing backed it up since {old[:10]}")
        self.assertNotIn(guess, [r["id"] for r in self.c._wrong(self.c.OWNER)])     # it can come back
        self.assertTrue(self.c.get(stale)["retired"])


class Dreaming(Base):
    def seed(self, reply):
        self.run_pass(chat(), reply)
        return {r["text"]: r for r in self.c.rows()}

    def dream(self, reply):
        self.asked = []
        return self.c.dream(lambda p: self.asked.append(p) or reply)

    def test_same_ones_merge_and_keep_every_exchange(self):
        have = self.seed("INFERRED: Ryan builds most things himself. (#1, #2)\n"
                         "INFERRED: Ryan prefers to write his own tools. (#2, #3)\n"
                         "INFERRED: Ryan dislikes being asked which option to pick. (#4, #5)")
        a_t, b_t = "Ryan builds most things himself.", "Ryan prefers to write his own tools."
        n = {r["text"]: i for i, r in enumerate(self.c.rows(limit=self.c.DREAM_SHOWN), 1)}
        done = self.dream(f"**SAME:** C{n[a_t]}, C{n[b_t]} = Ryan builds his own tools, Luna included.")
        self.assertEqual(done["merged"], ["Ryan builds his own tools, Luna included."])
        merged = self.c.rows()[0]
        self.assertEqual((merged["text"], merged["kind"]), ("Ryan builds his own tools, Luna included.", "inferred"))
        self.assertEqual(merged["sources"], sorted(set(have[a_t]["sources"]) | set(have[b_t]["sources"])))
        self.assertEqual(merged["created"], min(have[a_t]["created"], have[b_t]["created"]))
        self.assertTrue(merged["backed"])                    # concluded twice: seen again
        for t in (a_t, b_t):
            self.assertEqual(self.c.get(have[t]["id"])["why"], f"merged into #{merged['id']}")
        self.assertIn("(inferred, ", self.asked[0])

    def test_of_two_that_conflict_the_newer_stays(self):
        have = self.seed("INFERRED: Ryan likes long detailed answers. (#1, #2)\n"
                         "INFERRED: Ryan likes short plain answers. (#3, #4)")
        long_, short = have["Ryan likes long detailed answers."], have["Ryan likes short plain answers."]
        self.c._run(lambda c: c.execute("UPDATE conclusions SET created=? WHERE id IN (?,?)",
                                        (ago(days=2), long_["id"], short["id"])))
        self.c.back(long_["id"], [ago(minutes=1)])           # shown again since: now the newer one
        n = {r["id"]: i for i, r in enumerate(self.c.rows(limit=self.c.DREAM_SHOWN), 1)}
        done = self.dream(f"CONFLICT: C{n[short['id']]} and C{n[long_['id']]}")
        self.assertEqual(done["contradicted"], ["Ryan likes short plain answers."])
        self.assertEqual(self.c.get(short["id"])["why"], f"contradicted by #{long_['id']}")
        self.assertEqual([r["id"] for r in self.c.rows()], [long_["id"]])

    def test_one_line_per_conclusion_and_nothing_made_up(self):
        self.seed("INFERRED: Ryan likes Zork a lot. (#1, #2)\nINFERRED: Ryan enjoys Zork. (#3, #4)\n"
                  "INFERRED: Ryan plays Planetfall. (#5, #6)")
        n = {r["text"]: i for i, r in enumerate(self.c.rows(limit=self.c.DREAM_SHOWN), 1)}
        a, b, c = n["Ryan likes Zork a lot."], n["Ryan enjoys Zork."], n["Ryan plays Planetfall."]
        done = self.dream(f"SAME: C{a}, C{b} = Ryan loves Zork.\nCONFLICT: C{b}, C{c}\n"
                          f"SAME: C{c}, C9 = nope\nCONFLICT: C{c}, C{c}")
        self.assertEqual((done["merged"], done["contradicted"]), (["Ryan loves Zork."], []))
        self.assertEqual(sorted(r["text"] for r in self.c.rows()), ["Ryan loves Zork.", "Ryan plays Planetfall."])

    def test_only_when_something_changed(self):
        self.seed("INFERRED: Ryan likes Zork a lot. (#1, #2)\nINFERRED: Ryan plays Planetfall. (#3, #4)")
        self.dream("NONE")
        self.dream("NONE")
        self.assertEqual(self.asked, [])                    # the same two: not asked again
        self.c.back(self.c.rows()[0]["id"], [ago(minutes=1)])
        self.dream("NONE")
        self.assertEqual(len(self.asked), 1)

    def test_a_failed_call_tries_again_next_time(self):
        self.seed("INFERRED: Ryan likes Zork a lot. (#1, #2)\nINFERRED: Ryan plays Planetfall. (#3, #4)")

        def boom(prompt):
            raise OSError("down")
        self.assertTrue(self.c.dream(boom)["failed"])
        self.dream("NONE")
        self.assertEqual(len(self.asked), 1)

    def test_forgetting_someone_takes_where_she_was(self):
        self.run_pass(turns(*[(f"[Shannon] line {i}", "ok") for i in range(8)]),
                      "INFERRED: Shannon paints often. (#1, #2)\nSAID: Shannon lives in Lacombe. (#3)")
        self.dream("NONE")
        self.assertIn("Shannon", self.nb.get(self.c._DREAMT))
        self.c.forget_person("Shannon")
        self.assertNotIn("Shannon", self.nb.get(self.c._DREAMT))


class Refinements(Base):
    def n(self):
        return {r["text"]: i for i, r in enumerate(self.c.rows(limit=self.c.DREAM_SHOWN), 1)}

    def test_what_they_said_outranks_a_newer_guess(self):
        self.run_pass(chat(), "SAID: Ryan works days now. (#1)\nINFERRED: Ryan works nights mostly. (#2, #3)")
        n = self.n()
        done = self.c.dream(lambda p: f"CONFLICT: C{n['Ryan works nights mostly.']}, C{n['Ryan works days now.']}")
        self.assertEqual(done["contradicted"], ["Ryan works nights mostly."])
        self.assertEqual([r["text"] for r in self.c.rows()], ["Ryan works days now."])

    def test_a_guess_folds_into_what_they_said_and_the_words_stay_theirs(self):
        self.run_pass(chat(), "SAID: Ryan builds Luna himself. (#1)\nINFERRED: Ryan likes making his own tools. (#2, #3)")
        n = self.n()
        said = next(r for r in self.c.rows() if r["kind"] == "said")
        done = self.c.dream(lambda p: f"SAME: C{n['Ryan builds Luna himself.']}, "
                                      f"C{n['Ryan likes making his own tools.']} -> Ryan builds all his own tools.")
        self.assertEqual(done["merged"], ["Ryan builds Luna himself."])
        kept = self.c.rows()
        self.assertEqual([(r["id"], r["kind"], len(r["sources"])) for r in kept], [(said["id"], "said", 3)])

    def test_a_merge_cant_bring_back_what_you_called_wrong(self):
        self.run_pass(chat(), "INFERRED: Ryan likes Zork a lot. (#1, #2)\nINFERRED: Ryan enjoys text games. (#3, #4)\n"
                              "INFERRED: Ryan hates long answers. (#5, #6)")
        self.c.mark_wrong(next(r["id"] for r in self.c.rows() if "long" in r["text"]))
        n = self.n()
        done = self.c.dream(lambda p: f"SAME: C{n['Ryan likes Zork a lot.']}, C{n['Ryan enjoys text games.']} = "
                                      "Ryan hates long answers.")
        self.assertEqual(done["merged"], [])
        self.assertEqual(len(self.c.rows()), 2)

    def test_said_again_makes_a_guess_something_they_said(self):
        self.run_pass(chat(), "INFERRED: Ryan prefers plain talk. (#1, #2)")
        self.run_pass(chat(8, start=ago(hours=1)), "SAID: Ryan prefers plain talk! (#4)\n"
                                                   "INFERRED: Ryan prefers plain talk. (#5, #6)")
        r = self.c.rows()
        self.assertEqual([(x["kind"], len(x["sources"])) for x in r], [("said", 5)])

    def test_two_lines_of_one_reply_saying_one_thing_are_one(self):
        self.run_pass(chat(), "INFERRED: Ryan prefers plain talk. (#1, #2)\nINFERRED: Ryan prefers plain talk! (#3, #4)")
        self.assertEqual([len(r["sources"]) for r in self.c.rows()], [4])

    def test_brought_back_counts_as_seen_and_a_retired_one_isnt_backed(self):
        cid = self.c._run(lambda c: c.execute(
            "INSERT INTO conclusions (person, text, kind, sources, created) VALUES (?,?,?,?,?)",
            (self.c.OWNER, "Ryan likes long answers", "inferred", "[]", ago(days=100))).lastrowid)
        self.assertEqual(self.c.fade(), ["Ryan likes long answers"])
        self.assertFalse(self.c.back(cid, [ago(minutes=1)]))
        self.assertTrue(self.c.restore(cid))
        self.assertEqual(self.c.fade(), [])


class OldTable(Base):
    def test_a_table_from_before_backing_gets_the_column(self):
        db = sqlite3.connect(self.nb.DB_FILE)
        db.execute("CREATE TABLE conclusions (id INTEGER PRIMARY KEY AUTOINCREMENT, person TEXT NOT NULL, "
                   "text TEXT NOT NULL, kind TEXT NOT NULL, sources TEXT NOT NULL, created TEXT NOT NULL, "
                   "retired TEXT NOT NULL DEFAULT '', why TEXT NOT NULL DEFAULT '')")
        db.execute("INSERT INTO conclusions (person, text, kind, sources, created) VALUES (?,?,?,?,?)",
                   (self.c.OWNER, "Ryan likes Zork", "said", "[]", ago(days=1)))
        db.commit()
        db.close()
        self.assertEqual(self.c.rows()[0]["backed"], "")


class QuietHours(unittest.TestCase):
    def setUp(self):
        import config
        from mind import notebook, reflect
        self.r, self.config, self.meta = reflect, config, {}
        for target, name, value in ((notebook, "get", lambda k, d=None, **kw: self.meta.get(k, d)),
                                    (notebook, "put", lambda k, v: self.meta.__setitem__(k, v)),
                                    (config, "SELF_DREAM_HOURS", ""), (config, "PORTRAIT_DOZING_FROM", 22),
                                    (config, "PORTRAIT_DOZING_TO", 6), (reflect, "_failed", {})):
            p = mock.patch.object(target, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)

    def at(self, hour, last_hours_ago=None):
        now = datetime(2026, 11, 26, hour, 30)
        if last_hours_ago is not None:
            self.meta["night_at"] = (now - timedelta(hours=last_hours_ago)).isoformat(timespec="seconds")
        return self.r._dream_due(now)

    def test_the_hours(self):
        for raw, want in (("", (22, 6)), ("2-6", (2, 6)), (" 23 - 5 ", (23, 5)), ("22-24", (22, 0)),
                          ("any", None), ("0-24", None), ("bedtime", (22, 6)), ("5-5", (22, 6)), ("25-3", (22, 6))):
            with mock.patch.object(self.config, "SELF_DREAM_HOURS", raw):
                self.assertEqual(self.r._quiet_hours(), want, raw)
        self.assertTrue(self.r._in_hours((22, 6), 23) and self.r._in_hours((22, 6), 5))
        self.assertFalse(self.r._in_hours((22, 6), 6) or self.r._in_hours((2, 6), 1))

    def test_once_a_night_in_her_bedtime(self):
        self.assertTrue(self.at(14))                        # never ran: now
        self.assertFalse(self.at(14, last_hours_ago=20))    # daytime
        self.assertTrue(self.at(23, last_hours_ago=20))
        self.assertFalse(self.at(3, last_hours_ago=4))      # already tonight
        self.assertTrue(self.at(14, last_hours_ago=37))     # off at night: anyway, after a day and a half

    def test_the_old_lessons_mark_counts_until_the_batch_has_its_own(self):
        self.meta["dream_at"] = datetime(2026, 11, 26, 2, 0).isoformat()
        self.assertFalse(self.at(3))

    def test_any_is_every_reflect_hours(self):
        with mock.patch.object(self.config, "SELF_DREAM_HOURS", "any"), \
                mock.patch.object(self.config, "SELF_REFLECT_HOURS", 20, create=True):
            self.assertFalse(self.at(14, last_hours_ago=19))
            self.assertTrue(self.at(14, last_hours_ago=21))

    def test_the_batch_marks_the_night_only_when_it_ran_through(self):
        jobs = ("dream", "tidy_facts", "write_pages", "write_profiles")
        ok = {"failed": False, "faded": [], "merged": [], "contradicted": [], "read": 0, "new": []}
        with mock.patch.multiple(self.r, **{j: mock.DEFAULT for j in jobs}), \
                mock.patch.object(self.r, "write_conclusions", return_value=ok), \
                mock.patch.object(self.r, "dream_conclusions", return_value=dict(ok, failed=True)):
            self.r._night("model", None)
        self.assertNotIn("night_at", self.meta)
        self.assertTrue(self.r._resting("night") and not self.r._dream_due())
        self.r._failed.clear()
        with mock.patch.multiple(self.r, **{j: mock.DEFAULT for j in jobs}), \
                mock.patch.object(self.r, "write_conclusions", return_value=ok), \
                mock.patch.object(self.r, "dream_conclusions", return_value=ok):
            self.r._night("model", None)
        self.assertIn("night_at", self.meta)


if __name__ == "__main__":
    unittest.main()
