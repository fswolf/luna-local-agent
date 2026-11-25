"""ask_memory (mind/recall.py): one question, her facts, conclusions, notes
and past conversations searched together, one answer - and on someone
else's turn, only what's theirs. No model: the answer is written here.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import unittest
from unittest import mock

from tests.offline import FAKE  # noqa: F401  (first: no real servers)
from tests.test_conclusions import Base, ago


class Recall(Base):
    def setUp(self):
        super().setUp()
        import config
        from core import transcript, turnctx
        from mind import factstore, reflect, recall
        from senses import people
        self.r, self.turnctx = recall, turnctx
        self.people["Shannon"]["facts"] = ["Shannon drinks green tea", "Shannon paints on weekends"]
        path = os.path.join(self.dir, "transcript.jsonl")
        with open(path, "w") as f:
            for role, text in (("user", "I take my coffee black with two sugars"), ("assistant", "Noted, black."),
                               ("user", "[Shannon] I only drink green tea, never coffee"), ("assistant", "Tea it is."),
                               ("user", "the coffee machine broke again"), ("assistant", "Oh no!")):
                f.write(json.dumps({"at": ago(days=2), "role": role, "text": text}) + "\n")
        for target, name, value in (
                (transcript, "TRANSCRIPT_FILE", path), (config, "TRANSCRIPT_ENABLED", True),
                (config, "USER", "Ryan"), (config, "SELF_EPISODES", True),
                (people, "facts", lambda n: list((self.people.get(n) or {}).get("facts") or [])),
                (people, "session_guest", lambda n: None),
                (reflect, "_tcache", {"key": None, "size": 0, "entries": [], "file": None})):
            p = mock.patch.object(target, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch("mind.embedmem.rank", lambda q, texts: None)
        p.start()
        self.addCleanup(p.stop)
        factstore.add("Ryan takes his coffee black with two sugars")
        factstore.add("Ryan has a Radeon card")
        self.nb.add_episode(ago(days=3), ago(days=3), 6, "We talked about his coffee machine breaking down.")
        self.c._run(lambda c: c.executemany(
            "INSERT INTO conclusions (person, text, kind, sources, created) VALUES (?,?,?,?,?)",
            [(self.c.OWNER, "Ryan needs coffee before he talks about code", "inferred", "[]", ago(days=1)),
             ("Shannon", "Shannon avoids coffee entirely", "said", "[]", ago(days=1))]))
        self.asked = []

    def ask(self, question, about="", reply="Black, two sugars - he told you.", **turn):
        with self.turnctx.begin(**turn):
            return self.r.answer(question, about,
                                 ask=lambda p: self.asked.append(p) or (reply(p) if callable(reply) else reply))

    def test_your_turn_searches_everything_and_answers_once(self):
        said = self.ask("how does Ryan take his coffee?")
        self.assertTrue(said.startswith("Black, two sugars - he told you.\n(from: "))
        p = self.asked[0]
        for line in ("Ryan takes his coffee black with two sugars", "(your read, ", "coffee machine breaking down",
                     "Ryan: I take my coffee black", "Shannon: I only drink green tea"):
            self.assertIn(line, p)
        self.assertNotIn("Radeon", p)                         # only what bears on it
        self.assertNotIn("Shannon drinks green tea", p)       # nobody named: not her facts
        self.assertIn("1 fact, 1 conclusion, 1 note on a conversation", said)

    def test_naming_someone_brings_in_what_she_has_on_them(self):
        self.ask("does Shannon drink coffee?")
        self.assertIn("What you know about Shannon (facts)", self.asked[0])
        self.assertIn("(they told you, ", self.asked[0])
        self.assertIn("Shannon avoids coffee entirely", self.asked[0])

    def test_on_their_turn_only_whats_theirs(self):
        self.ask("what does Ryan drink? coffee?", speaker="Shannon")
        p = self.asked[0]
        self.assertIn("Shannon drinks green tea", p)
        self.assertIn("Shannon avoids coffee entirely", p)
        self.assertIn("Shannon: I only drink green tea", p)
        for his in ("black with two sugars", "before he talks about code", "coffee machine", "machine broke"):
            self.assertNotIn(his, p)

    def test_met_this_session_gets_their_facts_and_nothing_kept(self):
        with mock.patch("senses.people.session_guest", lambda n: {"name": n}):
            self.ask("what do I drink?", speaker="Shannon")
        self.assertNotIn("concluded", self.asked[0])
        self.assertNotIn("Past exchanges", self.asked[0])

    def test_not_for_chat_or_a_stranger(self):
        from senses import people
        self.assertIn("Not available", self.ask("coffee?", private=False))
        self.assertIn("Not available", self.ask("coffee?", speaker=people.STRANGER))
        self.assertEqual(self.asked, [])

    def test_nothing_found_asks_nobody(self):
        self.assertIn("Nothing in your memory", self.ask("what is the airspeed of a swallow"))
        self.assertEqual(self.asked, [])

    def test_the_lines_themselves_when_the_model_cant(self):
        def down(prompt):
            raise OSError("server down")
        said = self.ask("how does Ryan take his coffee?", reply=down)
        self.assertIn("Couldn't sum it up", said)
        self.assertIn("- Ryan takes his coffee black with two sugars", said)
        self.assertIn("Couldn't sum it up", self.ask("how does Ryan take his coffee?", reply=""))

    def test_a_question_about_nobody_but_them_gets_what_she_has_on_them(self):
        self.ask("what do you know about Shannon?")
        p = self.asked[0]
        self.assertIn("Shannon paints on weekends", p)
        self.assertIn("Shannon avoids coffee entirely", p)
        self.assertNotIn("Your notes on past conversations", p)     # any old notes: left out
        self.assertNotIn("word for word", p)

    def test_by_meaning_when_the_embedding_server_is_up(self):
        def rank(query, texts):
            self.assertEqual(query, "how does take his coffee?")    # who it's about doesn't steer it
            return sorted(((0.9 if "coffee" in t else 0.1), t) for t in texts)[::-1]
        with mock.patch("mind.embedmem.rank", rank):
            self.ask("how does Ryan take his coffee?")
        self.assertNotIn("Radeon", self.asked[0])
        self.assertIn("black with two sugars", self.asked[0])

    def test_the_tool(self):
        import tools
        from senses import people
        self.assertIn("ask_memory", tools._REGISTRY)
        self.assertIn("ask_memory", people.GUEST_MEMORY_TOOLS)
        self.assertNotIn("ask_memory", people.GUEST_TOOLS)
        self.assertIn("Ask a question", tools._REGISTRY["ask_memory"]["run"](question=" "))


if __name__ == "__main__":
    unittest.main()
