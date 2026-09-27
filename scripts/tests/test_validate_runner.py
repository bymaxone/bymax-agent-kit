"""The behavioural suite's runner in validate.sh: modules run side by side, and one that fails
still fails the validation. The block is read from validate.sh and run against fixture modules,
so the case tests the lines the gate runs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PASSING = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n'
FAILING = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_no(self):\n        self.fail("x")\n'


def runner():
    """The lines of validate.sh that run the suite, from its log directory to its removal."""
    text = (ROOT / 'scripts/validate.sh').read_text()
    start = text.index('test_logs="$(mktemp -d)"')
    end = text.index('rm -rf "${test_logs}"', start) + len('rm -rf "${test_logs}"')
    return text[start:end]


class RunnerTests(unittest.TestCase):
    """What the runner reports, over a directory of fixture modules."""

    def run_over(self, modules):
        where = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ['rm', '-rf', str(where)])
        (where / 'scripts/tests').mkdir(parents=True)
        for name, text in modules.items():
            (where / 'scripts/tests' / name).write_text(text)
        script = ('fail() { echo "FAIL $1"; }\nok() { echo "OK $1"; }\n' + runner())
        return subprocess.run(['bash', '-c', script], cwd=where, capture_output=True, text=True, timeout=120)

    def test_a_module_that_fails_is_named_and_fails_the_validation(self):
        """Run side by side, a failure is in a file of its own: the runner must still read it."""
        done = self.run_over({'test_a.py': PASSING, 'test_b.py': FAILING, 'test_c.py': PASSING})
        self.assertIn('FAIL test_b: regression tests failed', done.stdout)
        self.assertIn('OK test_a: Ran 1 test', done.stdout)
        self.assertNotIn('FAIL test_a', done.stdout)

    def test_a_directory_with_no_module_fails(self):
        """A glob that matched nothing ran nothing, which is not a passing suite."""
        done = self.run_over({})
        self.assertIn('FAIL no test module ran', done.stdout)


if __name__ == '__main__':
    unittest.main()
