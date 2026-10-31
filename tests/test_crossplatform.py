"""Things that work on Linux and break on Windows, kept from coming back.

Text files are opened as UTF-8: without encoding=, Windows reads and writes
them in its own code page, and her files (moods, history, notes, people's
names) are full of letters that don't fit it.
"""
import ast
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sources():
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return []
    return [f for f in out.stdout.split() if not f.startswith(("tests/", "evals/"))]


def _text_opens_without_encoding(tree):
    if any(isinstance(n, ast.FunctionDef) and n.name == "open" for n in tree.body):
        return                                     # a module with an open() of its own
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"):
            continue
        if any(k.arg == "encoding" for k in node.keywords):
            continue
        mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
        if isinstance(mode, ast.Constant) and "b" in str(mode.value):
            continue
        if node.args and isinstance(node.args[0], ast.Attribute) and node.args[0].attr == "devnull":
            continue
        yield node.lineno


class CrossPlatform(unittest.TestCase):
    def test_text_files_are_opened_as_utf8(self):
        files = _sources()
        if not files:
            self.skipTest("not a git checkout")
        found = []
        for f in files:
            with open(os.path.join(ROOT, f), encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), f)
            found += [f"{f}:{line}" for line in _text_opens_without_encoding(tree)]
        self.assertEqual(found, [], "open() a text file with encoding=\"utf-8\"")


if __name__ == "__main__":
    unittest.main()
