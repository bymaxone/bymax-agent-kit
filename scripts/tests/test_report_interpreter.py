"""Gate layer for the interpreter the standup collector runs on: the `python3` a machine has,
since the plugin asks for no more than that."""
import ast
from pathlib import Path
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / 'plugins/bymax-report/scripts'


def barred(tree):
    """The annotations in a module spelled with `|`, which Python before 3.10 cannot evaluate."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parts = [node.returns]
        elif isinstance(node, (ast.AnnAssign, ast.arg)):
            parts = [node.annotation]
        else:
            continue
        found += [part for part in parts if part is not None and any(
            isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(part))]
    return found


class InterpreterTests(unittest.TestCase):
    """No module in the collector's directory evaluates an annotation spelled with `|` on import."""

    def test_an_annotation_spelled_with_a_bar_is_never_evaluated(self):
        """`str | None` evaluated at import raises before Python 3.10, and a module the collector
        imports without deferring its annotations crashes it there before it reads anything."""
        for path in sorted(SCRIPTS.glob('*.py')):
            tree = ast.parse(path.read_text())
            deferred = any(isinstance(node, ast.ImportFrom) and node.module == '__future__'
                           and any(alias.name == 'annotations' for alias in node.names)
                           for node in tree.body)
            with self.subTest(module=path.name):
                self.assertTrue(deferred or not barred(tree),
                                '%s evaluates an annotation spelled with | on import' % path.name)


if __name__ == '__main__':
    unittest.main()
