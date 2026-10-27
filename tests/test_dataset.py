"""Examples for her patches (training/dataset.py), /good and /fix
(commands/patches.py) and the examples page (web/dataset_web.py).
Everything goes to a temporary folder; agent/dataset/ is never touched.

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

from training import dataset  # noqa: E402
from web import dataset_web  # noqa: E402


def a_turn(reply="Mrrp~ hello there", tools=False):
    dataset.note_turn("You are Luna.", [{"role": "user", "content": "hi"},
                                        {"role": "assistant", "content": "hey you"},
                                        {"role": "tool", "content": "{}"}],
                      {"role": "user", "content": "how are you?"}, reply, model="qwen", used_tools=tools)


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [mock.patch.object(dataset, "FOLDER", self.tmp),
                        mock.patch.object(dataset, "FILE", os.path.join(self.tmp, "examples.jsonl"))]
        for p in self.patches:
            p.start()
        dataset._last.clear()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        dataset._last.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nothing_to_keep_before_she_has_spoken(self):
        with self.assertRaises(ValueError):
            dataset.keep("good")

    def test_good_keeps_her_reply_and_what_she_saw(self):
        a_turn()
        ex = dataset.keep("good")
        self.assertEqual(ex["reply"], "Mrrp~ hello there")
        self.assertIsNone(ex["original"])
        self.assertTrue(ex["approved"])
        self.assertEqual([m["role"] for m in ex["messages"]], ["system", "user", "assistant", "user"])
        self.assertEqual(ex["messages"][-1]["content"], "how are you?")
        self.assertEqual(len(dataset.examples()), 1)

    def test_fix_keeps_your_version_and_hers(self):
        a_turn()
        ex = dataset.keep("fix", reply="I'm good, you?")
        self.assertEqual(ex["reply"], "I'm good, you?")
        self.assertEqual(ex["original"], "Mrrp~ hello there")

    def test_a_tool_turn_isnt_offered(self):
        a_turn(tools=True)
        with self.assertRaises(ValueError):
            dataset.keep("good")

    def test_one_example_per_reply(self):
        a_turn()
        first = dataset.keep("good")
        with self.assertRaises(ValueError):
            dataset.keep("good")                                   # twice: kept once
        dataset.keep("fix", reply="I'm good, you?")                # then fixed: the same example
        rows = dataset.examples()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["id"], rows[0]["source"], rows[0]["reply"], rows[0]["original"]),
                         (first["id"], "fix", "I'm good, you?", "Mrrp~ hello there"))
        a_turn("a new reply")                                     # a new turn can be kept again
        dataset.keep("good")
        self.assertEqual(len(dataset.examples()), 2)

    def test_a_keep_during_a_page_change_isnt_lost(self):
        # /good lands right between the page's read of the file and its rewrite:
        # the rewrite must not save over it.
        import threading

        a_turn()
        first = dataset.keep("good")
        a_turn("kept meanwhile")
        keeper, fired = [], []

        def keep_meanwhile(read):
            def wrapped(*a, **k):
                rows = read(*a, **k)
                if not fired:
                    fired.append(1)
                    t = threading.Thread(target=dataset.keep, args=("good",))
                    t.start()
                    t.join(0.3)             # done by now unless it has to wait its turn
                    keeper.append(t)
                return rows
            return wrapped

        hooks = [mock.patch.object(dataset, name, keep_meanwhile(getattr(dataset, name)))
                 for name in ("_read", "examples") if hasattr(dataset, name)]
        for h in hooks:
            h.start()
        try:
            dataset.update(first["id"], approved=False)
        finally:
            for h in hooks:
                h.stop()
        for t in keeper:
            t.join(5)
        replies = [r["reply"] for r in dataset.examples()]
        self.assertIn("kept meanwhile", replies)
        self.assertIn("Mrrp~ hello there", replies)

    def test_review_changes(self):
        a_turn()
        ex = dataset.keep("good")
        self.assertTrue(dataset.update(ex["id"], approved=False))
        self.assertEqual(dataset.counts()["habit"], {"approved": 0, "waiting": 0, "dropped": 1})
        self.assertTrue(dataset.update(ex["id"], reply="better"))
        row = dataset.examples()[0]
        self.assertEqual((row["reply"], row["original"]), ("better", "Mrrp~ hello there"))
        self.assertTrue(dataset.update(ex["id"], kind="gesture"))
        with self.assertRaises(ValueError):
            dataset.update(ex["id"], kind="nonsense")
        self.assertTrue(dataset.remove(ex["id"]))
        self.assertEqual(dataset.examples(), [])
        self.assertFalse(dataset.remove(ex["id"]))

    def test_the_commands(self):
        from commands import patches

        said = []
        with mock.patch("ui.add_message", lambda who, text: said.append(text)):
            self.assertTrue(patches.handle("/good"))
            a_turn()
            self.assertTrue(patches.handle("/good"))
            self.assertTrue(patches.handle("/fix"))                      # usage, keeps nothing
            self.assertTrue(patches.handle("/fix that's much better"))
            self.assertTrue(patches.handle("/examples"))
            self.assertFalse(patches.handle("/goodbye"))
        self.assertIn("Not kept", said[0])
        self.assertEqual([r["source"] for r in dataset.examples()], ["fix"])   # /good then /fix: one example

    def test_the_page(self):
        a_turn()
        ex = dataset.keep("good")
        code, _kind, html = dataset_web.handle("GET", "/", b"")
        self.assertEqual(code, 200)
        self.assertIn(dataset_web.KEY, html)
        code, _kind, body = dataset_web.handle("GET", "/api", b"")
        rows = json.loads(body)["examples"]
        self.assertEqual((rows[0]["said"], rows[0]["reply"]), ("how are you?", "Mrrp~ hello there"))
        post = lambda **d: dataset_web.handle("POST", "/api", json.dumps(d).encode())[0]
        self.assertEqual(post(action="drop", example=ex["id"]), 403)              # no key
        self.assertEqual(post(key=dataset_web.KEY, action="drop", example=ex["id"]), 200)
        self.assertFalse(dataset.examples()[0]["approved"])
        self.assertEqual(post(key=dataset_web.KEY, action="delete", example="nope"), 404)
        self.assertEqual(post(key=dataset_web.KEY, action="kind", example=ex["id"], kind="x"), 400)


if __name__ == "__main__":
    unittest.main()
