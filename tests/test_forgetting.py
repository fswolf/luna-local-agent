"""Forgotten stays forgotten (mind/forgetting.py), and a guess stays a
guess until it's confirmed (the trust column in mind/factstore.py)."""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from tests.facts_tmp import use_temp_facts


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        use_temp_facts(self, self.dir)
        from mind import factstore, forgetting, longterm
        self.store, self.fg, self.lt = factstore, forgetting, longterm
        for name, value in (("_guest", lambda: None), ("_announce", lambda: None)):
            p = mock.patch.object(longterm, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(forgetting, "_names", lambda: {"ryan", "luna"})
        p.start()
        self.addCleanup(p.stop)


class Fingerprints(Base):
    def test_rewordings_of_the_same_fact(self):
        tomb = self.fg.marks("Ryan works at the bakery")
        for again in ("Ryan worked at the bakery", "Ryan still works at a bakery",
                      "Ryan used to work at the bakery"):
            self.assertTrue(self.fg.same_fact(self.fg.marks(again), tomb), again)
        for other in ("Ryan likes bread", "Ryan works from home", "The bakery on Main Street closed"):
            self.assertFalse(self.fg.same_fact(self.fg.marks(other), tomb), other)

    def test_no_words_are_kept(self):
        self.store.bury(self.fg.marks("Ryan works at the bakery"))
        db = sqlite3.connect(self.store.DB_FILE)
        self.assertNotIn("bakery", " ".join(r[0] for r in db.execute("SELECT marks FROM forgotten")))
        db.close()

    def test_clean_takes_only_the_sentences_that_carry_it(self):
        tombs = [self.fg.marks("Ryan works at the bakery")]
        text = "We talked about Godot. He said he works at the bakery downtown. Then we played Zork."
        self.assertEqual(self.fg.clean(text, tombs), "We talked about Godot. Then we played Zork.")
        untouched = "Line one.  Two spaces.\n\nLine three."
        self.assertIs(self.fg.clean(untouched, tombs), untouched)

    def test_one_word_facts_only_take_sentences_about_someone(self):
        tombs = [self.fg.marks("Ryan likes anime")]
        self.assertEqual(self.fg.clean("Anime came up on stream. He loves anime.", tombs), "Anime came up on stream.")


class Forget(Base):
    def test_forgotten_fact_is_not_learned_again(self):
        self.lt.add_fact("Ryan works at the bakery")
        removed, _ = self.lt.forget_fact("bakery")
        self.assertEqual(removed, "Ryan works at the bakery")
        self.assertEqual(len(self.swept), 1)                       # and the sweep was started
        self.assertFalse(self.lt.add_fact("Ryan worked at the bakery"))
        self.assertIn("forget", self.lt.why_not("Ryan worked at the bakery"))
        with mock.patch.object(self.lt, "_ask_extractor", lambda m, p: "NEW | work | Ryan works at the bakery"):
            self.lt._extract_fact_sqlite("m", "u", "a")
        self.assertEqual(self.store.active_facts(), [])

    def test_asking_for_it_back_lifts_it(self):
        import tools.memory as tm
        self.lt.add_fact("Ryan works at the bakery")
        self.lt.forget_fact("bakery")
        self.assertIn("Not saved", tm._remember_fact("Ryan works at the bakery"))
        self.assertIn("Saved", tm._remember_fact("Ryan works at the bakery", again="true"))
        self.assertEqual(self.store.tombstones(), [])
        self.lt.forget_fact("bakery")
        with mock.patch.object(self.lt, "_ask_extractor", lambda m, p: "NEW | work | Ryan works at the bakery"):
            self.lt._extract_fact_sqlite("m", "remember I work at the bakery", "a", asked=True)
        self.assertEqual(self.store.active_facts(), ["Ryan works at the bakery"])

    def test_replace_never_brings_it_back(self):
        self.lt.add_fact("Ryan has a 6950 XT")
        self.lt.add_fact("Ryan works at the bakery")
        self.lt.forget_fact("bakery")
        self.assertFalse(self.store.replace("Ryan has a 6950 XT", "Ryan works at the bakery"))
        self.assertIn("Ryan has a 6950 XT", self.store.active_facts())


class Sweep(Base):
    """The stores themselves, pointed at temp files."""

    def setUp(self):
        super().setUp()
        from core import history, transcript
        from mind import notebook, thoughtlog
        self.tombs = [self.fg.marks("Ryan works at the bakery")]
        t = os.path.join(self.dir, "transcript.jsonl")
        with open(t, "w") as f:
            for role, text in (("user", "I work at the bakery. Also I like Zork."), ("assistant", "Bakery, got it!"),
                               ("user", "Forget that I work at the bakery.")):
                f.write(json.dumps({"at": "2026-11-18T01:00:00", "role": role, "text": text}) + "\n")
        for target, name, value in (
                (transcript, "TRANSCRIPT_FILE", t), (notebook, "DB_FILE", os.path.join(self.dir, "nb.db")),
                (thoughtlog, "DB_FILE", os.path.join(self.dir, "th.db")),
                (history, "_data", {"summary": "Ryan said he works at the bakery. He likes Zork.",
                                    "messages": [{"role": "user", "content": "I work at the bakery now."}]}),
                (history, "save", lambda: None)):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.history, self.transcript, self.notebook, self.thoughtlog = history, transcript, notebook, thoughtlog

    def test_every_store(self):
        nb, fg = self.notebook, self.fg
        nb.add_episode("2026-11-17T20:00:00", "2026-11-17T21:00:00", 4,
                       "He told me he works at the bakery. We played chess.")
        nb.add_episode("2026-11-17T22:00:00", "2026-11-17T23:00:00", 2, "He works at the bakery.")
        c = self.thoughtlog._conn()
        c.execute("INSERT INTO thoughts (timestamp, user_text, reasoning, answer) VALUES "
                  "('t', 'I work at the bakery.', 'He works at the bakery. Note it.', 'Got it.')")
        c.commit()
        c.close()
        self.store.add("Ryan worked at the bakery")                                 # a reworded copy
        self.store.add("Ryan works at the bakery on Main")
        self.store.replace("Ryan works at the bakery on Main", "Ryan has a cat")     # kept as history...
        done = {f.__name__: f(self.tombs) for f in (fg._facts, fg._history, fg._transcript, fg._episodes,
                                                     fg._thoughts)}
        self.assertEqual([r[1] for r in self.store.rows()], ["Ryan has a cat"])
        self.assertEqual([r[1] for r in self.store.rows(retired=True)], [])        # ...and gone with it
        self.assertEqual(self.history._data["summary"], "He likes Zork.")
        self.assertEqual(self.history._data["messages"], [])
        with open(self.transcript.TRANSCRIPT_FILE) as f:
            lines = [json.loads(l)["text"] for l in f]
        self.assertEqual(lines, ["Also I like Zork.", "Bakery, got it!"])     # "forget that I work..." went too
        self.assertEqual([e["summary"] for e in nb.episodes()], ["We played chess."])
        c = self.thoughtlog._conn()
        self.assertEqual(c.execute("SELECT user_text, reasoning FROM thoughts").fetchone(), ("", "Note it."))
        c.close()
        self.assertTrue(all(done.values()))

    def test_empty_columns_are_left_alone(self):
        c = self.thoughtlog._conn()
        c.execute("INSERT INTO thoughts (timestamp, user_text, reasoning, answer) VALUES ('t', NULL, 'Fine.', NULL)")
        c.execute("INSERT INTO thought_tokens (id, data) VALUES (1, x'00')")
        c.commit()
        c.close()
        self.assertEqual(self.fg._thoughts(self.tombs), 0)
        c = self.thoughtlog._conn()
        self.assertEqual(c.execute("SELECT count(*) FROM thought_tokens").fetchone()[0], 1)    # tokens kept
        c.close()

    def test_tool_calls_stay_valid_json(self):
        self.store.bury(self.tombs[0])
        self.history.add_message("assistant", "Done.", tools=[
            {"name": "forget_fact", "arguments": '{"about": "Ryan works at the bakery"}',
             "result": "Forgotten: Ryan works at the bakery"},
            {"name": "get_datetime", "arguments": "{}", "result": "It's 4 AM."}])
        calls = self.history._data["messages"][-1]["tools"]
        self.assertEqual(json.loads(calls[0]["arguments"]), {"about": ""})
        self.assertEqual(calls[0]["result"], "")
        self.assertEqual(calls[1], {"name": "get_datetime", "arguments": "{}", "result": "It's 4 AM."})
        self.history.record_tool_use("remember_fact", '{"fact": "Ryan works at the bakery"}', "Saved: Ryan works at the bakery")
        self.assertEqual(self.history._data["messages"][-1]["tools"][-1]["result"], "")

    def test_what_she_writes_afterwards(self):
        self.store.bury(self.tombs[0])
        self.history.add_message("assistant", "Okay, forgotten that you work at the bakery. Want to play?")
        self.history.add_message("user", "Good. I do work at the bakery though, haha.")
        said = [m["content"] for m in self.history._data["messages"][-2:]]
        self.assertEqual(said, ["Want to play?", "Good. I do work at the bakery though, haha."])  # his words kept
        self.assertIsNone(self.notebook.add_episode("a", "b", 1, "He works at the bakery."))


class Trust(Base):
    def extract(self, reply, asked=False):
        with mock.patch.object(self.lt, "_ask_extractor", lambda m, p: reply):
            self.lt._extract_fact_sqlite("m", "u", "a", asked=asked)

    def test_a_guess_until_it_comes_up_again(self):
        self.extract("NEW | food | Ryan hates mushrooms")
        self.assertEqual(self.store.details(["Ryan hates mushrooms"]), {"Ryan hates mushrooms": ("", "", False)})
        self.extract("NEW | food | Ryan hates mushrooms")
        self.assertEqual(self.store.details(["Ryan hates mushrooms"]), {})

    def test_asked_and_deliberate_facts_are_sure(self):
        import tools.memory as tm
        self.extract("NEW | pets | Ryan has a cat", asked=True)
        tm._remember_fact("Ryan streams as a VTuber")
        self.assertEqual(self.store.details(self.store.active_facts()), {})

    def test_confirm_verb_and_tool(self):
        import tools.memory as tm
        self.extract("NEW | food | Ryan hates mushrooms")
        self.extract("CONFIRM | Ryan hates mushrooms (not sure)")
        self.assertEqual(self.store.details(["Ryan hates mushrooms"]), {})
        self.extract("NEW | food | Ryan likes olives")
        self.assertIn("Confirmed", tm._confirm_fact("olives"))
        self.assertIn("Already confirmed", tm._confirm_fact("olives"))

    def test_she_sees_not_sure(self):
        from llm import prompts
        self.extract("NEW | food | Ryan hates mushrooms")
        self.lt.add_fact("Ryan streams as a VTuber")
        with mock.patch.object(prompts.people, "guest", lambda: None), \
                mock.patch.object(prompts.config, "preference_lines", lambda: []), \
                mock.patch("mind.pages.prompt_block", lambda q: ""), \
                mock.patch("mind.knowledge.prompt_block", lambda q: ""):
            block = prompts.build_memory_prompt("mushrooms")
        self.assertIn("- Ryan hates mushrooms (not sure)", block)
        self.assertIn("don't state them as true", block)
        self.assertIn("- Ryan streams as a VTuber\n", block)

    def test_pages_and_profiles_skip_guesses(self):
        self.extract("NEW | food | Ryan hates mushrooms")
        self.lt.add_fact("Ryan streams as a VTuber")
        self.assertEqual([r[1] for r in self.store.rows(sure_only=True)], ["Ryan streams as a VTuber"])

    def test_old_database_counts_as_sure(self):
        path = os.path.join(self.dir, "old.db")
        db = sqlite3.connect(path)
        db.executescript("CREATE TABLE facts (id INTEGER PRIMARY KEY, fact TEXT NOT NULL, subject TEXT NOT NULL "
                         "DEFAULT '', created_at TEXT NOT NULL, superseded_at TEXT, superseded_by INTEGER, "
                         "embedding BLOB); INSERT INTO facts(fact, created_at) VALUES ('Ryan has a cat', 'x');")
        db.commit()
        db.close()
        with mock.patch.object(self.store, "DB_FILE", path), mock.patch.object(self.store, "_db", None):
            self.assertEqual(self.store.details(["Ryan has a cat"]), {})
            self.assertEqual(self.store.tombstones(), [])
            self.store._db.close()


class Manager(Base):
    def test_confirm_and_delete(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "manager", os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory-manager", "manager.py"))
        manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manager)
        self.lt.add_fact("Ryan hates mushrooms", sure=False)
        fid = self.store.rows()[0][0]
        self.assertFalse(manager.state()["active"][0]["sure"])
        manager.apply("confirm", {"id": fid})
        self.assertTrue(manager.state()["active"][0]["sure"])
        manager.apply("delete", {"id": fid})
        self.assertEqual(manager.state()["forgotten"], 1)
        self.assertEqual(len(self.swept), 1)
        manager.apply("add", {"fact": "Ryan hates mushrooms"})                 # you adding it brings it back
        self.assertEqual(manager.state()["forgotten"], 0)


if __name__ == "__main__":
    unittest.main()
