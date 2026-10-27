"""main.handle_input is one long function: importing a module inside it
that main.py already imports at the top (`import config` in the /camera
branch) makes that name local to the whole function, and every branch
above the import then fails with "cannot access local variable". /settings
did, and took the app down with it.

    python -m unittest discover tests        (from the repo folder)
"""
import ast
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# main.py, and the commands/ modules its command branches moved into: each
# command module is one handle() with a branch per command, the same shape
FILES = [os.path.join(ROOT, "main.py")] + sorted(glob.glob(os.path.join(ROOT, "commands", "*.py")))


def _own_nodes(func):
    """The function's statements, not those of functions nested in it."""
    stack = list(func.body)
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                stack.append(child)


class NoShadowing(unittest.TestCase):
    def test_no_top_level_module_is_imported_again_inside_a_function(self):
        bad = []
        for path in FILES:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            top = {(a.asname or a.name).split(".")[0] for n in tree.body
                   if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
            for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                for node in _own_nodes(func):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        bad += [f"{os.path.basename(path)} {func.name}: line {node.lineno} imports {a.name}"
                                for a in node.names if (a.asname or a.name).split(".")[0] in top]
        self.assertEqual(bad, [])

if __name__ == "__main__":
    unittest.main()
