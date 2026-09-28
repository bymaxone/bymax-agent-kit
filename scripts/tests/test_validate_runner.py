"""The behavioural suite's runner in validate.sh: modules run side by side, and one that fails
still fails the validation. The block is read from validate.sh and run against fixture modules,
so the case tests the lines the gate runs."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PASSING = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n'
FAILING = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_no(self):\n        self.fail("x")\n'


def reported(done):
    """The runner's lines, sorted, with unittest's timing cut from each `Ran` count."""
    return sorted(re.sub(r' in [0-9.]+s$', '', line) for line in done.stdout.splitlines())


def runner():
    """The lines of validate.sh that run the suite, from its log directory to its removal."""
    text = (ROOT / 'scripts/validate.sh').read_text()
    start = text.index('test_jobs="${BYMAX_TEST_JOBS:-6}"')
    end = text.index('rm -rf "${test_logs}"', start) + len('rm -rf "${test_logs}"')
    return text[start:end]


class RunnerTests(unittest.TestCase):
    """What the runner reports, over a directory of fixture modules."""

    def run_over(self, modules, jobs=None, timeout=120):
        """Run the runner block in a fresh directory holding `modules`, with BYMAX_TEST_JOBS set to `jobs`."""
        where = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ['rm', '-rf', str(where)])
        (where / 'scripts/tests').mkdir(parents=True)
        for name, text in modules.items():
            (where / 'scripts/tests' / name).write_text(text)
        script = ("RED=''; NC=''\nfail() { echo \"FAIL $1\"; }\nok() { echo \"OK $1\"; }\n" + runner())
        env = {k: v for k, v in os.environ.items() if k != 'BYMAX_TEST_JOBS'}
        if jobs is not None:
            env['BYMAX_TEST_JOBS'] = jobs
        return subprocess.run(['bash', '-c', script], cwd=where, capture_output=True, text=True,
                              timeout=timeout, env=env)

    def test_a_module_that_fails_is_named_and_fails_the_validation(self):
        """Run side by side, a failure is in a file of its own: the runner must still read it."""
        done = self.run_over({'test_a.py': PASSING, 'test_b.py': FAILING, 'test_c.py': PASSING})
        self.assertIn('FAIL test_b: regression tests failed', done.stdout)
        self.assertIn('OK test_a: Ran 1 test', done.stdout)
        self.assertNotIn('FAIL test_a', done.stdout)

    def test_a_directory_with_no_module_fails(self):
        """A glob that matched nothing ran nothing, which is not a passing suite."""
        done = self.run_over({})
        self.assertEqual(reported(done), ['FAIL no test module ran'])

    def test_the_modules_it_runs_are_the_ones_discover_runs(self):
        """unittest discover's default pattern is test*.py over importable names; the runner's too."""
        done = self.run_over({'test_a.py': PASSING, 'testb.py': PASSING, 'b_test.py': FAILING,
                              'test-c.py': FAILING})
        self.assertEqual(reported(done), ['OK test_a: Ran 1 test', 'OK testb: Ran 1 test'])

    def test_a_width_that_is_not_a_positive_integer_is_refused_before_any_module_runs(self):
        """A zero or negative width, or one that is not a number, made the polling loop wait forever."""
        for jobs in ('0', '-1', 'abc', '1.5', '08', '2 '):
            with self.subTest(jobs=jobs):
                done = self.run_over({'test_a.py': PASSING}, jobs=jobs, timeout=30)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn(f"BYMAX_TEST_JOBS must be a positive integer, got '{jobs}'", done.stderr)
                self.assertNotIn('OK test_a', done.stdout)

    def test_a_positive_width_runs_the_modules(self):
        """The refusal is for a width the loop cannot honour, not for a narrow one."""
        done = self.run_over({'test_a.py': PASSING, 'test_b.py': PASSING}, jobs='1')
        self.assertEqual(done.returncode, 0)
        self.assertEqual(reported(done), ['OK test_a: Ran 1 test', 'OK test_b: Ran 1 test'])


if __name__ == '__main__':
    unittest.main()
