"""Training her patches: the export (training/export.py), the patches on disk
and the model check (training/patches.py, llama/start.sh), and /patches.
Everything in temporary folders; agent/dataset/ and llama/patches/ untouched.
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


try:
    import jinja2  # noqa: F401
except ImportError:
    jinja2 = None


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
            def apply_chat_template(self, msgs, tokenize=False, add_generation_prompt=False):
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


@unittest.skipUnless(shutil.which("bash"), "no bash")
class StartScript(unittest.TestCase):
    """llama/start.sh's patch block, on its own."""

    def test_loads_only_patches_for_the_model_it_starts(self):
        text = read(os.path.join(HERE, "llama", "start.sh"))
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
