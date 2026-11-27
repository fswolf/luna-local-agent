"""Training her patches: the export (training/export.py), the patches on disk
and the model check (training/patches.py, server/llama/start.sh), and /patches.
Everything in temporary folders; agent/dataset/ and server/llama/patches/ untouched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401

from training import dataset, export, patches  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def put(path, data=None):
    with open(path, "w") as f:
        if data is not None:
            json.dump(data, f)


def read(path):
    with open(path) as f:
        return f.read()


def row(i, approved=True, kind="gesture", reply="Hi there [wave]"):
    return {"id": f"ex{i:04d}", "kind": kind, "approved": approved, "reply": reply,
            "messages": [{"role": "system", "content": "You are Luna."}, {"role": "user", "content": f"hello {i}"}]}


class Export(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        rows = [row(i) for i in range(60)] + [row(100, approved=None), row(101, approved=False),
                                               row(102, kind="habit"), row(103, reply="  ")]
        with open(os.path.join(self.tmp, "examples.jsonl"), "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)
        self.p = [mock.patch.object(dataset, "FOLDER", self.tmp),
                  mock.patch.object(dataset, "FILE", os.path.join(self.tmp, "examples.jsonl"))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_approved_only_split_and_stable(self):
        out = os.path.join(self.tmp, "export")
        n_train, n_test, paths = export.export("gesture", out)
        self.assertEqual(n_train + n_test, 60)              # waiting, dropped, habit and empty left out
        self.assertTrue(1 <= n_test <= 15)
        conv = json.loads(read(paths["train"]).splitlines()[0])
        self.assertEqual([m["role"] for m in conv["messages"]], ["system", "user", "assistant"])
        self.assertEqual(conv["messages"][-1]["content"], "Hi there [wave]")
        test_before = read(paths["test"])
        export.export("gesture", out)
        self.assertEqual(read(paths["test"]), test_before)    # the same ones held back every time
        with self.assertRaises(ValueError):
            export.export("nonsense", out)


class OnDisk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for name, made_for in (("gesture-a", "Qwen-9B"), ("habit-b", "Other"), ("old-c", None)):
            put(os.path.join(self.tmp, name + ".gguf"))
            if made_for:
                put(os.path.join(self.tmp, name + ".json"), {"kind": name.split("-")[0], "for": made_for, "examples": 300})
        with open(os.path.join(self.tmp, ".current_model"), "w") as f:
            f.write("Qwen-9B\n")
        self.p = mock.patch.object(patches, "FOLDER", self.tmp)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_only_the_ones_made_for_this_model_fit(self):
        got = {p["name"]: p["fits"] for p in patches.local()}
        self.assertEqual(got, {"gesture-a": True, "habit-b": False, "old-c": False})

    def test_strength_while_running(self):
        live = [{"id": 0, "path": "patches/gesture-a.gguf", "scale": 1.0}, {"id": 1, "path": "patches/x.gguf", "scale": 0.7}]
        with mock.patch.object(patches, "_call", side_effect=[live, None]) as call:
            p = patches.set_scale("gesture", "0.5")
        self.assertEqual(p["scale"], 0.5)
        call.assert_called_with("POST", [{"id": 0, "scale": 0.5}, {"id": 1, "scale": 0.7}])   # the other kept as it was
        with mock.patch.object(patches, "_call", side_effect=OSError):
            with self.assertRaises(ValueError):
                patches.set_scale("gesture", 1)

    def test_command(self):
        from commands import patches as cmd

        with mock.patch.object(patches, "_call", return_value=[{"id": 0, "path": "patches/gesture-a.gguf", "scale": 1}]), \
                mock.patch("ui.add_message") as say:
            self.assertTrue(cmd.handle("/patches"))
        text = say.call_args[0][1]
        self.assertIn("gesture-a  [gesture, 300 examples]  loaded, id 0, strength 1", text)
        self.assertIn("habit-b", text)
        self.assertIn("made for Other", text)

    def test_command_with_her_model_on_another_machine(self):
        # the desktop has no patch files; the server reports what it loaded
        from commands import patches as cmd

        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        live = [{"id": 0, "path": "/home/you/luna/llama/patches/habit-qwen-9b-n14.gguf", "scale": 1}]
        with mock.patch.object(patches, "FOLDER", empty), mock.patch.object(patches, "_call", return_value=live), \
                mock.patch("ui.add_message") as say:
            cmd.handle("/patches")
        text = say.call_args[0][1]
        self.assertIn("model: her model server", text)
        self.assertIn("habit-qwen-9b-n14  loaded on her model server, id 0, strength 1", text)
        self.assertNotIn("none trained yet", text)


try:
    import jinja2  # noqa: F401
except ImportError:
    jinja2 = None


class Style(unittest.TestCase):
    """A style patch: text from agent/dataset/style/[name]/ in pieces, your chat examples mixed in."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        with open(os.path.join(self.tmp, "examples.jsonl"), "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in [row(i, kind="habit", reply="Mrrp~") for i in range(20)]
                         + [row(50, approved=False)])
        for p in (mock.patch.object(dataset, "FOLDER", self.tmp),
                  mock.patch.object(dataset, "FILE", os.path.join(self.tmp, "examples.jsonl")),
                  mock.patch.object(export, "STYLE", os.path.join(self.tmp, "style"))):
            p.start()
            self.addCleanup(p.stop)

    def book(self, name="", text=None):
        folder = os.path.join(self.tmp, "style", name)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "book.txt"), "w") as f:
            f.write(text if text is not None else "\n\n".join(f"Paragraph {i}. " + "She smiled. " * 40
                                                                for i in range(200)))

    def test_pieces_cut_between_paragraphs(self):
        text = "\n\n".join(f"P{i} " + "word " * 100 for i in range(40))
        pieces = export.chunks(text, size=2000)
        self.assertTrue(all(len(p) <= 2000 for p in pieces))
        self.assertTrue(all(p.startswith("P") for p in pieces))          # never split mid-paragraph
        self.assertEqual(export.chunks("x" * 5000, size=2000)[0], "x" * 2000)   # a wall of text is cut
        self.assertEqual(export.chunks("Chapter One"), [])                # too short to learn from

    def test_export_mixes_in_your_chat(self):
        self.book("novels")
        pieces, chat, n_test, paths = export.export_style("novels", os.path.join(self.tmp, "export"))
        self.assertTrue(paths["train"].endswith("style-novels-train.jsonl"))
        rows = [json.loads(line) for line in read(paths["train"]).splitlines()]
        self.assertEqual(sum("text" in r for r in rows), pieces)
        self.assertEqual(sum("messages" in r for r in rows), chat)
        self.assertTrue(0 < chat < 20)                                     # approved ones, not the held-back ones
        self.assertGreater(pieces, n_test)

    def test_no_text_or_a_bad_name(self):
        with self.assertRaises(ValueError):
            export.export_style("", os.path.join(self.tmp, "export"))
        for bad in ("../secrets", "my books", ".hidden", "a/b"):
            with self.assertRaises(ValueError, msg=bad):
                export.style_folder(bad)
        self.assertTrue(export.style_folder("dark-romance_2").endswith("dark-romance_2"))

    def test_a_book_with_one_paragraph_per_line_keeps_them(self):
        text = "\n".join(f"Line {i} of the book, a paragraph of its own." + " More." * 20 for i in range(30))
        piece = export.chunks(text, size=3000)[0]
        self.assertIn("\n\nLine 1 of", piece)                       # paragraph breaks kept
        wrapped = "First paragraph wrapped\nover two lines." + " x" * 300 + "\n\nSecond one."
        self.assertIn("wrapped over two lines", export.chunks(wrapped)[0])   # wrapping joined as before

    def test_text_is_learned_whole(self):
        sys.path.insert(0, os.path.join(HERE, "training"))
        import train

        class Tok:
            eos_token_id = 0

            def __call__(self, text, add_special_tokens=False):
                return mock.Mock(input_ids=[ord(c) for c in text])

        r = train.encode_text(Tok(), "Once upon a time", 8192)
        self.assertEqual(r["labels"], r["input_ids"])
        self.assertEqual(r["input_ids"][-1], 0)                            # ends with end-of-text
        self.assertEqual(len(train.encode_text(Tok(), "x" * 100, 10)["input_ids"]), 10)


@unittest.skipIf(jinja2 is None, "jinja2 isn't installed")
class Masking(unittest.TestCase):
    """training/train.py learns only her last reply (no model or GPU: a stand-in template)."""

    def test_only_the_last_reply_is_learned(self):
        sys.path.insert(0, os.path.join(HERE, "training"))
        import train

        tmpl = jinja2.Template("{%- for m in messages %}<|im_start|>{{ m.role }}\n"
                               "{% if m.role == 'assistant' and loop.last %}<think>\n\n</think>\n\n{% endif %}"
                               "{{ m.content }}<|im_end|>\n{% endfor %}"
                               "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}")

        class Tok:
            def apply_chat_template(self, msgs, tools=None, tokenize=False, add_generation_prompt=False):
                return tmpl.render(messages=msgs, add_generation_prompt=add_generation_prompt)

            def __call__(self, text, add_special_tokens=False):
                return mock.Mock(input_ids=[ord(c) for c in text])

        tok = Tok()
        prefix = train.reply_prefix(tok)
        self.assertEqual(prefix, "<think>\n\n</think>\n\n")
        msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "old"}, {"role": "user", "content": "q"},
                {"role": "assistant", "content": "Mrrp [wave]"}]
        r = train.encode(tok, msgs, prefix, 8192)
        learned = "".join(chr(i) for i, lab in zip(r["input_ids"], r["labels"]) if lab != -100)
        self.assertEqual(learned, "Mrrp [wave]<|im_end|>\n")            # not "old", not the think block
        self.assertIsNone(train.encode(tok, msgs, prefix, 20))          # too long: left out


TOOL_EXAMPLE = {
    "id": "t1", "kind": "habit", "approved": True, "reply": "Two new ones, nothing urgent.",
    "messages": [{"role": "system", "content": "S"}, {"role": "user", "content": "any email?"}],
    "rounds": [{"role": "assistant", "content": "One sec~",
                "tool_calls": [{"id": "", "type": "function", "function": {"name": "check_email",
                                                                           "arguments": '{"limit": 5}'}},
                               {"id": "", "type": "function", "function": {"name": "search_email",
                                                                           "arguments": "not json"}}]},
               {"role": "tool", "tool_call_id": "", "name": "check_email", "content": "2 unread"},
               {"role": "tool", "tool_call_id": "", "name": "search_email", "content": "nothing"}],
    "tools": [{"type": "function", "function": {"name": "check_email"}}],
}


class ExportTools(unittest.TestCase):
    def test_calls_and_results_between_your_message_and_her_answer(self):
        conv = export.conversation(TOOL_EXAMPLE)
        self.assertEqual([m["role"] for m in conv["messages"]],
                         ["system", "user", "assistant", "tool", "tool", "assistant"])
        calls = conv["messages"][2]["tool_calls"]
        self.assertEqual(calls[0]["function"]["arguments"], {"limit": 5})      # an object, not a string
        self.assertEqual(calls[1]["function"]["arguments"], {})
        ids = [c["id"] for c in calls]
        self.assertEqual(len(set(ids)), 2)                                      # made up, and distinct
        self.assertEqual([m["tool_call_id"] for m in conv["messages"][3:5]], ids)
        self.assertEqual(conv["tools"], TOOL_EXAMPLE["tools"])
        self.assertEqual(conv["messages"][-1]["content"], "Two new ones, nothing urgent.")

    def test_rounds_that_dont_pair_up_are_left_out(self):
        bad = dict(TOOL_EXAMPLE, rounds=TOOL_EXAMPLE["rounds"][:2])            # a call with no result
        self.assertIsNone(export.conversation(bad))
        self.assertIsNone(export.conversation(dict(TOOL_EXAMPLE, rounds=[{"role": "user", "content": "x"}])))

    def test_a_plain_example_is_as_before(self):
        self.assertEqual(export.conversation(row(1)), {"messages": [
            {"role": "system", "content": "You are Luna."}, {"role": "user", "content": "hello 1"},
            {"role": "assistant", "content": "Hi there [wave]"}]})


@unittest.skipIf(jinja2 is None, "jinja2 isn't installed")
class MaskingTools(unittest.TestCase):
    """A tool turn: her calls are learned where the template writes them whole,
    the results never."""

    BODY = ("{%- for m in messages %}<|im_start|>{{ 'user' if m.role == 'tool' else m.role }}\n"
            "{% if m.role == 'tool' %}<tool_response>{{ m.content }}</tool_response>"
            "{% else %}{{ THINK }}{{ m.content }}"
            "{% for c in m.tool_calls or [] %}<tool_call>{{ c.function.name }} {{ c.function.arguments | tojson }}</tool_call>{% endfor %}"
            "{% endif %}<|im_end|>\n{% endfor %}"
            "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}")

    def tok(self, think):
        tmpl = jinja2.Template(self.BODY.replace("{{ THINK }}", think))

        class Tok:
            seen_tools = []

            def apply_chat_template(self, msgs, tools=None, tokenize=False, add_generation_prompt=False):
                Tok.seen_tools.append(tools)
                return tmpl.render(messages=msgs, add_generation_prompt=add_generation_prompt)

            def __call__(self, text, add_special_tokens=False):
                return mock.Mock(input_ids=[ord(c) for c in text])

        return Tok()

    def learned(self, think):
        sys.path.insert(0, os.path.join(HERE, "training"))
        import train

        tok = self.tok(think)
        conv = export.conversation(TOOL_EXAMPLE)
        r = train.encode(tok, conv["messages"], train.reply_prefix(tok), 8192, conv["tools"])
        self.assertIn(conv["tools"], tok.seen_tools)
        return "".join(chr(i) for i, lab in zip(r["input_ids"], r["labels"]) if lab != -100)

    def test_calls_learned_when_written_whole(self):
        got = self.learned("")
        self.assertIn('One sec~<tool_call>check_email {"limit": 5}</tool_call>', got)
        self.assertIn("Two new ones, nothing urgent.<|im_end|>", got)
        self.assertNotIn("2 unread", got)                                        # results are context
        self.assertNotIn("any email?", got)

    def test_qwen_drops_thinking_from_calls_so_only_the_answer(self):
        # thinking shown only on the last message, as Qwen's template does
        got = self.learned("{% if m.role == 'assistant' and loop.last %}<think>\n\n</think>\n\n{% endif %}")
        self.assertEqual(got, "Two new ones, nothing urgent.<|im_end|>\n")


@unittest.skipUnless(shutil.which("bash"), "no bash")
class StartScript(unittest.TestCase):
    """server/llama/start.sh's patch block, on its own."""

    def test_loads_only_patches_for_the_model_it_starts(self):
        text = read(os.path.join(HERE, "server", "llama", "start.sh"))
        block = text[text.index("# Her patches: the ones made for this model"):]
        block = block[:block.index("\nfi\n") + 4]
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "patches"))
            for name, made_for in (("g", "Qwen-9B"), ("h", "Other")):
                put(os.path.join(tmp, "patches", name + ".gguf"))
                put(os.path.join(tmp, "patches", name + ".json"), {"for": made_for})
            script = "set -uo pipefail; MODEL=/m/Qwen-9B.gguf; PATCHES=auto; args=();\n" + block + '\necho "${args[*]}"'
            out = subprocess.run(["bash", "-c", script], cwd=tmp, capture_output=True, text=True, timeout=20).stdout
            self.assertEqual(out.strip(), "--lora patches/g.gguf")
            self.assertEqual(read(os.path.join(tmp, "patches", ".current_model")).strip(), "Qwen-9B")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_train_script_parses(self):
        subprocess.run(["bash", "-n", os.path.join(HERE, "training", "train.sh")], check=True)


if __name__ == "__main__":
    unittest.main()
