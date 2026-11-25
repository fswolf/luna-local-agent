"""Conclusions (mind/conclusions.py): what she works out about a person from
reading back their conversations while idle, marked said or inferred, with
the exchanges it came from. No model: the replies are written here.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from tests.offline import FAKE  # noqa: F401  (first: no real servers)
from tests.facts_tmp import use_temp_facts


def ago(**kw):
    return (datetime.now() - timedelta(**kw)).isoformat(timespec="seconds")


def turns(*pairs, start=None):
    """Transcript entries: (said, answer) pairs a minute apart, from `start`."""
    at = datetime.fromisoformat(start or ago(hours=3))
    out = []
    for said, answer in pairs:
        stamp = at.isoformat(timespec="seconds")
        out += [{"at": stamp, "role": "user", "text": said}, {"at": stamp, "role": "assistant", "text": answer}]
        at += timedelta(minutes=1)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        use_temp_facts(self, self.dir)
        from mind import conclusions, forgetting, notebook, profiles
        from senses import people
        self.c, self.nb, self.fg, self.profiles = conclusions, notebook, forgetting, profiles
        self.people = {"Shannon": {"name": "Shannon", "facts": []}}
        for target, name, value in (
                (notebook, "DB_FILE", os.path.join(self.dir, "nb.db")),
                (people, "everyone", lambda: dict(self.people)),
                (people, "is_owner", lambda n: str(n).lower() == "ryan"),
                (profiles, "_owner_name", lambda: "Ryan"),
                (forgetting, "_names", lambda: {"ryan", "luna", "shannon"}),
                (conclusions, "enabled", lambda: True),
                (conclusions, "_due", {"key": None, "answer": False})):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch("mind.embedmem.vectors", lambda texts: None)     # by words: no embedding server
        p.start()
        self.addCleanup(p.stop)

    def run_pass(self, entries, reply, **kw):
        self.prompts = []

        def ask(prompt):
            self.prompts.append(prompt)
            return reply(prompt) if callable(reply) else reply
        return self.c.write(ask, entries, **kw)


class Whose(Base):
    def test_each_exchange_goes_to_the_one_who_said_it(self):
        entries = turns(("I hate workarounds", "Noted."),
                        ("[Shannon] I paint on weekends", "Lovely!"),
                        ("[someone new] who are you", "I'm Luna."),
                        ("[Dave] hi", "Hi Dave."),                      # met only that session
                        ("[Ryan] typed at the desk", "Hey."),           # the owner by name is the owner
                        ("(A task you set yourself: \"check mail\")", "Done."),
                        ("*touches you on the head*", "Mm."))
        found = self.c.exchanges(entries)
        self.assertEqual({p: [x[1] for x in xs] for p, xs in found.items()},
                         {self.c.OWNER: ["I hate workarounds", "typed at the desk"],
                          "Shannon": ["I paint on weekends"]})
        self.assertEqual(found["Shannon"][0][2], "Lovely!")

    def test_a_user_line_with_no_answer_is_skipped(self):
        entries = turns(("first", "one"))
        entries.insert(0, {"at": ago(hours=4), "role": "user", "text": "lost"})
        self.assertEqual([x[1] for x in self.c.exchanges(entries)[self.c.OWNER]], ["first"])


class Pass(Base):
    def chat(self, n=8, **kw):
        return turns(*[(f"thing {i} about the build", f"answer {i}") for i in range(n)], **kw)

    def test_said_and_inferred_with_their_exchanges(self):
        entries = self.chat()
        reply = ("SAID: Ryan builds Luna on his own machines. (#2)\n"
                 "INFERRED: Ryan wants the root cause of a bug, not a workaround. (#1, #3)\n"
                 "INFERRED: Ryan dislikes being asked which option to pick. (#4)\n"   # one exchange: not enough
                 "**SAID:** Ryan streams on Thursdays (1 and 5)")
        done = self.run_pass(entries, reply)
        self.assertEqual((done["read"], done["failed"]), (8, False))
        got = {r["text"]: (r["kind"], r["sources"]) for r in self.c.rows(self.c.OWNER)}
        at = [e["at"] for e in entries if e["role"] == "user"]
        self.assertEqual(got, {
            "Ryan builds Luna on his own machines.": ("said", [at[1]]),
            "Ryan wants the root cause of a bug, not a workaround.": ("inferred", [at[0], at[2]]),
            "Ryan streams on Thursdays": ("said", [at[0], at[4]])})
        self.assertIn("#8 (", self.prompts[0])
        self.assertIn("Ryan: thing 0 about the build", self.prompts[0])

    def test_read_once(self):
        entries = self.chat()
        self.run_pass(entries, "NONE")
        self.assertFalse(self.c.due(entries))
        self.assertEqual(self.run_pass(entries, "NONE")["read"], 0)
        more = entries + self.chat(6, start=ago(minutes=30))
        self.assertTrue(self.c.due(more))
        self.assertEqual(self.run_pass(more, "NONE")["read"], 6)

    def test_a_few_wait_until_they_have_gone_quiet(self):
        self.assertFalse(self.c.due(self.chat(3)))
        self.assertTrue(self.c.due(self.chat(3, start=ago(days=2))))
        self.assertFalse(self.c.due(self.chat(10, start=ago(days=40))))     # older than the backlog

    def test_batches_and_a_limit_per_pass(self):
        entries = self.chat(45)
        done = self.run_pass(entries, "NONE", limit=2)
        self.assertEqual((done["read"], len(self.prompts)), (2 * self.c.BATCH, 2))
        self.assertEqual(self.run_pass(entries, "NONE")["read"], 0)    # the last 5: too few, and still recent
        self.assertEqual(self.run_pass(entries + self.chat(1, start=ago(minutes=5)), "NONE")["read"], 6)

    def test_you_first_then_whoever_has_most(self):
        entries = turns(*[(f"[Shannon] line {i}", "ok") for i in range(7)]) + self.chat(6, start=ago(hours=1))
        self.run_pass(entries, "NONE")
        self.assertIn("conversations with Ryan", self.prompts[0])
        self.assertIn("conversations with Shannon", self.prompts[1])
        self.assertIn("Shannon: line 0", self.prompts[1])

    def test_a_failed_call_reads_nothing(self):
        def boom(prompt):
            raise OSError("server down")
        entries = self.chat()
        self.assertTrue(self.run_pass(entries, boom)["failed"])
        self.assertTrue(self.c.due(entries))

    def test_nothing_she_has_already_or_a_fact_says(self):
        from mind import factstore
        factstore.add("Ryan streams on Thursdays")
        self.run_pass(self.chat(), "INFERRED: Ryan cares about the root cause of bugs. (#1, #2)")
        self.run_pass(self.chat(8, start=ago(hours=1)),
                      "INFERRED: Ryan cares about the root cause of bugs! (#1, #2)\n"
                      "SAID: Ryan streams on Thursdays. (#3)")
        self.assertEqual([r["text"] for r in self.c.rows()], ["Ryan cares about the root cause of bugs."])

    def test_outdated_and_wrong_ones_are_set_aside_and_shown(self):
        self.run_pass(self.chat(), "SAID: Ryan runs Luna on LM Studio. (#1)\n"
                                   "INFERRED: Ryan prefers long detailed answers. (#2, #3)")
        lm, long_ = [r["id"] for r in reversed(self.c.rows())]
        self.assertTrue(self.c.mark_wrong(long_))
        self.assertFalse(self.c.mark_wrong(long_))
        self.run_pass(self.chat(8, start=ago(hours=1)), "OUTDATED: C1 (#4)\n"
                      "INFERRED: Ryan prefers long detailed answers. (#5, #6)")   # set aside: not again
        self.assertIn("C1. (said) Ryan runs Luna on LM Studio.", self.prompts[0])
        self.assertIn("- Ryan prefers long detailed answers.", self.prompts[0].split("Set aside as wrong")[1])
        self.assertEqual(self.c.rows(), [])
        why = {r["id"]: r["why"] for r in self.c.rows(retired=True)}
        self.assertTrue(why[lm].startswith("outdated by what was said "))
        self.assertEqual(why[long_], "marked wrong")
        self.assertTrue(self.c.restore(long_))
        self.assertFalse(self.c.restore(long_))

    def test_an_outdated_one_can_come_true_again_but_a_wrong_one_cant(self):
        self.run_pass(self.chat(), "SAID: Ryan runs Luna on LM Studio. (#1)")
        old = self.c.rows()[0]["id"]
        self.run_pass(self.chat(8, start=ago(hours=2)), "OUTDATED: C1 (#2)")
        self.run_pass(self.chat(8, start=ago(hours=1)), "SAID: Ryan runs Luna on LM Studio. (#3)")
        self.assertEqual([r["text"] for r in self.c.rows()], ["Ryan runs Luna on LM Studio."])
        self.assertNotIn("LM Studio", self.prompts[0].split("Set aside as wrong")[1])
        self.assertTrue(self.c.mark_wrong(old, "on the memory page"))       # the outdated one, now wrong
        self.assertEqual(self.c.get(old)["why"], "marked wrong on the memory page")
        self.assertIn("LM Studio", self.c._prompt(self.c.OWNER, self.c.exchanges(self.chat(1))[self.c.OWNER], [],
                                                     self.c._wrong(self.c.OWNER)))

    def test_two_exchanges_in_one_second_across_a_batch_edge(self):
        entries = turns(*[(f"line {i}", "ok") for i in range(self.c.BATCH + 1)])
        entries[-2]["at"] = entries[-1]["at"] = entries[-4]["at"] = entries[-3]["at"]   # #20 and #21: one second
        self.run_pass(entries, "NONE", limit=1)
        self.assertEqual(self.c._marks()[self.c.OWNER][1], 1)
        later = entries + self.chat(5, start=ago(minutes=5))
        self.assertEqual([x[1] for x in self.c.unread(self.c.exchanges(later)[self.c.OWNER],
                                                      self.c._marks()[self.c.OWNER])][0], f"line {self.c.BATCH}")
        self.assertEqual(self.run_pass(later, "NONE")["read"], 6)

    def test_someone_forgotten_while_she_reads_keeps_nothing(self):
        entries = turns(*[(f"[Shannon] line {i}", "ok") for i in range(8)])

        def forget_meanwhile(prompt):
            self.people.pop("Shannon")
            return "SAID: Shannon paints on weekends. (#1)"
        self.run_pass(entries, forget_meanwhile)
        self.assertEqual((self.c.rows(), self.c._marks()), ([], {}))

    def test_the_exchanges_behind_one(self):
        entries = self.chat()
        self.run_pass(entries, "INFERRED: Ryan likes building things himself. (#2, #4)")
        cid = self.c.rows()[0]["id"]
        self.assertEqual([x[1] for x in self.c.sources_text(cid, entries)],
                         ["thing 1 about the build", "thing 3 about the build"])
        from commands import memory
        with mock.patch("mind.reflect._transcript", lambda: entries):
            said = memory._conclusions(f"why {cid}")
        self.assertIn("thing 3 about the build", said)
        self.assertIn("Ryan likes building things himself.", memory._conclusions("me"))
        self.assertIn("Set aside", memory._conclusions(f"wrong {cid}"))
        self.assertIn("No conclusions yet", memory._conclusions(""))
        self.assertIn(f"#{cid} Ryan likes building", memory._conclusions("ryan"))   # only set aside ones: still found
        self.assertIn("No conclusions about shannon", memory._conclusions("shannon"))


class Forgetting(Base):
    def test_a_forgotten_fact_takes_the_conclusions_carrying_it(self):
        self.run_pass(turns(*[(f"x{i}", "y") for i in range(8)]),
                      "SAID: Ryan works at the bakery downtown. (#1)\nSAID: Ryan streams on Thursdays. (#2)")
        self.assertEqual(self.fg._conclusions([self.fg.marks("Ryan works at the bakery")]), 1)
        self.assertEqual([r["text"] for r in self.c.rows()], ["Ryan streams on Thursdays."])

    def test_forgetting_a_person_takes_theirs(self):
        self.run_pass(turns(*[(f"[Shannon] line {i}", "ok") for i in range(8)]),
                      "SAID: Shannon paints on weekends. (#1)")
        self.assertTrue(self.c.rows("Shannon"))
        self.assertEqual(self.c.forget_person("Shannon"), 1)
        self.assertEqual((self.c.rows("Shannon"), self.c._marks()), ([], {}))


class IntoTheProfile(Base):
    def test_her_read_rides_beside_the_facts_and_a_new_one_rewrites_it(self):
        from mind import factstore
        for f in ("Ryan has a Radeon card", "Ryan streams on Thursdays", "Ryan lives in Canada"):
            factstore.add(f)
        asked = []
        ask = lambda prompt: asked.append(prompt) or "Ryan is a builder who streams and wants straight answers."
        self.assertEqual(self.profiles.write(ask), ["Ryan"])
        self.assertNotIn("concluded", asked[0])
        self.run_pass(turns(*[(f"x{i}", "y") for i in range(8)]),
                      "INFERRED: Ryan wants straight answers without fuss. (#1, #2)")
        self.assertEqual(self.profiles.write(ask), ["Ryan"])        # her conclusions changed under it
        self.assertIn("- (your read) Ryan wants straight answers without fuss.", asked[1])
        self.assertIn("never against a fact", asked[1])
        self.assertEqual(self.profiles.write(ask), [])


class TranscriptCache(unittest.TestCase):
    """mind/reflect.py reads the transcript once and then only what was added."""

    def test_a_rewritten_file_is_read_again_even_when_it_grew(self):
        from core import transcript
        from mind import reflect
        path = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        line = lambda text: json.dumps({"at": "2026-11-25T01:00:00", "role": "user", "text": text}) + "\n"
        with open(path, "w") as f:
            f.write(line("I work at the bakery") + line("hi"))
        with mock.patch.object(transcript, "TRANSCRIPT_FILE", path), \
                mock.patch.dict(reflect._tcache, {"key": None, "size": 0, "entries": [], "file": None}):
            self.assertEqual(len(reflect._transcript()), 2)
            with open(path + ".new", "w") as f:          # a forget's rewrite, then more said
                f.write(line("hi") + line("a much longer line than the forgotten one was"))
            os.replace(path + ".new", path)
            self.assertEqual([e["text"] for e in reflect._transcript()],
                             ["hi", "a much longer line than the forgotten one was"])


if __name__ == "__main__":
    unittest.main()
