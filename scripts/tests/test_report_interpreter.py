"""Gate layer for the interpreter the standup collector runs on: the `python3` a machine has,
since the plugin asks for no more than that. macOS ships 3.9, so every module the collector
loads is held to what 3.9 can read and run."""
import ast
import os
from pathlib import Path
import shutil
import subprocess
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / 'plugins/bymax-report/scripts'
FLOOR = (3, 9)


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


def older_python():
    """A python3 on this machine older than 3.10, or None: the interpreter the floor is for."""
    for candidate in ('/usr/bin/python3', shutil.which('python3.9') or ''):
        if not candidate or not os.access(candidate, os.X_OK):
            continue
        done = subprocess.run([candidate, '-c', 'import sys; print(sys.version_info[:2] < (3, 10))'],
                              capture_output=True, text=True)
        if done.stdout.strip() == 'True':
            return candidate
    return None


class InterpreterTests(unittest.TestCase):
    """What 3.9 cannot read or evaluate never reaches a module the collector loads."""

    def test_every_module_is_written_in_the_grammar_of_the_floor(self):
        """A `match` statement or any other form newer than the floor is a syntax error there,
        before the collector reads anything."""
        for path in sorted(SCRIPTS.glob('*.py')):
            with self.subTest(module=path.name):
                ast.parse(path.read_text(), feature_version=FLOOR)

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

    def test_the_collector_runs_on_an_older_python_where_one_is_installed(self):
        """The checks above read the source; this runs `--help` on the floor where one exists,
        so a library call newer than the floor on that path is caught too."""
        older = older_python()
        if older is None:
            self.skipTest('no python3 older than 3.10 on this machine')
        done = subprocess.run([older, str(SCRIPTS / 'collect.py'), '--help'], capture_output=True,
                              text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == '__main__':
    unittest.main()
