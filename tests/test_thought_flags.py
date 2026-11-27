"""mind/thoughtlog.py: "low confidence" and "overconfident" only on a shaky
fact, each model's usual certainty (baselines), and the one-time recount of
turns kept under the old rule."""
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zlib
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.offline  # noqa: F401,E402

from mind import thoughtlog  # noqa: E402


def runs(words):
    """Token runs for an answer: (text, "a", logprob) per word."""
    return [[(w, "a", math.log(p)) for w, p in words]]


SURE = 0.9
SHAKY_WORDS = runs([("I ", SURE), ("was ", SURE), ("hoping ", 0.1), ("the ", 0.1), ("patch ", 0.1), ("helps", SURE)])
SHAKY_FACT = runs([("The ", SURE), ("card ", SURE), ("has ", SURE), ("16 ", 0.1), ("GB ", 0.1), ("of ", 0.1), ("VRAM", SURE)])


class Flags(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        for p in (mock.patch.object(thoughtlog, "DB_FILE", os.path.join(self.dir, "th.db")),
                  mock.patch.object(thoughtlog, "enabled", return_value=True),
                  mock.patch("config.SELF_HEDGE_BELOW", 0.6, create=True)):
            p.start()
            self.addCleanup(p.stop)

    def record(self, answer, tokens, tools=()):
        return thoughtlog.record("hi", [{"text": "thinking", "called": []}], answer, tools=tools, tokens=tokens,
                                 model="m")

    def test_unsure_wording_is_not_flagged(self):
        flags = self.record("I was hoping the patch helps", SHAKY_WORDS)
        self.assertFalse([f for f in flags if f.startswith(("low confidence", "overconfident"))])

    def test_a_shaky_fact_is(self):
        flags = self.record("The card has 16 GB of VRAM", SHAKY_FACT)
        self.assertTrue(any(f.startswith("low confidence") for f in flags))
        self.assertTrue(any(f.startswith("overconfident") for f in flags))

    def test_hedged_or_from_a_tool_is_not_overconfident(self):
        flags = self.record("I think the card has 16 GB of VRAM", SHAKY_FACT)
        self.assertFalse(any(f.startswith("overconfident") for f in flags))
        flags = self.record("The card has 16 GB of VRAM", SHAKY_FACT, tools=["run_command"])
        self.assertFalse(any(f.startswith("overconfident") for f in flags))

    def test_each_models_usual(self):
        conn = thoughtlog._conn()
        rows = [("small", 0.40 + i / 1000) for i in range(100)] + [("big", 0.80 + i / 1000) for i in range(100)] \
            + [("new", 0.5)] * 5
        conn.executemany("INSERT INTO thoughts (timestamp, model, conf, flags) VALUES ('t', ?, ?, '[]')", rows)
        conn.commit()
        conn.close()
        b = thoughtlog.baselines()
        self.assertEqual(set(b), {"small", "big"})                 # "new" hasn't enough replies yet
        self.assertAlmostEqual(b["small"]["median"], 0.45, places=2)
        self.assertLess(b["small"]["low"], b["small"]["median"])
        self.assertGreater(b["big"]["low"], b["small"]["high"])

    def test_usual_follows_new_turns(self):
        conn = thoughtlog._conn()
        conn.executemany("INSERT INTO thoughts (timestamp, model, conf, flags) VALUES ('t', 'm', ?, '[]')",
                         [(0.4,)] * 40)
        conn.commit()
        self.assertAlmostEqual(thoughtlog.baselines()["m"]["median"], 0.4)
        conn.executemany("INSERT INTO thoughts (timestamp, model, conf, flags) VALUES ('t', 'm', ?, '[]')",
                         [(0.8,)] * 300)
        conn.commit()
        conn.close()
        self.assertAlmostEqual(thoughtlog.baselines()["m"]["median"], 0.8)   # its last 300, after the new turns

    def test_a_turn_without_token_data_keeps_its_flag(self):
        conn = thoughtlog._conn()
        conn.execute("DELETE FROM meta")
        conn.execute("INSERT INTO thoughts (timestamp, answer, tools, source, flags) VALUES "
                     "('t', 'I was hoping', '[]', 'typed', ?)", (json.dumps(["low confidence: x"]),))
        conn.commit()
        conn.close()
        thoughtlog._conn().close()
        raw = sqlite3.connect(os.path.join(self.dir, "th.db")).execute("SELECT flags FROM thoughts").fetchone()[0]
        self.assertEqual(json.loads(raw), ["low confidence: x"])

    def test_old_turns_are_recounted_once(self):
        path = os.path.join(self.dir, "th.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE thoughts (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, "
                     "source TEXT, user_text TEXT, reasoning TEXT, answer TEXT, tools TEXT, rounds INTEGER, "
                     "seconds REAL, mood_e TEXT, mood_w TEXT)")
        conn.execute("CREATE TABLE thought_tokens (id INTEGER PRIMARY KEY, data BLOB)")
        old = ["low confidence: 3 uncertain tokens", "overconfident: sounded sure", "promised a tool: x"]
        for rid, (answer, tokens) in enumerate((("I was hoping the patch helps", SHAKY_WORDS),
                                                 ("The card has 16 GB of VRAM", SHAKY_FACT)), 1):
            conn.execute("INSERT INTO thoughts (id, timestamp, source, answer, tools) VALUES (?, 't', 'typed', ?, '[]')",
                         (rid, answer))
            conn.execute("INSERT INTO thought_tokens VALUES (?, ?)",
                         (rid, zlib.compress(json.dumps(tokens).encode())))
        conn.commit()
        conn.execute("ALTER TABLE thoughts ADD COLUMN flags TEXT DEFAULT '[]'")
        conn.execute("UPDATE thoughts SET flags=?", (json.dumps(old),))
        conn.commit()
        conn.close()
        thoughtlog._conn().close()                                   # opening it recounts
        got = dict(sqlite3.connect(path).execute("SELECT id, flags FROM thoughts").fetchall())
        self.assertEqual(json.loads(got[1]), ["promised a tool: x"])   # wording: both taken off, the rest kept
        self.assertEqual(json.loads(got[2]), old)                      # a shaky fact: kept
        conn = sqlite3.connect(path)
        conn.execute("UPDATE thoughts SET flags=? WHERE id=1", (json.dumps(old),))
        conn.commit()
        conn.close()
        thoughtlog._conn().close()                                   # only once
        self.assertEqual(json.loads(sqlite3.connect(path).execute("SELECT flags FROM thoughts WHERE id=1").fetchone()[0]),
                         old)


if __name__ == "__main__":
    unittest.main()
