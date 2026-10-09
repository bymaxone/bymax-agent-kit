"""The regression measurement is taken once per candidate and read back for every later question."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
import review_evidence


class RegressionCacheTests(unittest.TestCase):
    """A repository with one changed test file, and a counting stand-in for the slow measurement."""

    def setUp(self):
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        self.repo, self.directory = Path(box.name, 'repo'), Path(box.name, 'campaign')
        self.repo.mkdir()
        self.directory.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True)
        (self.repo / 'test_a.py').write_text('def test_a():\n    assert True\n')
        self.state = dict(review_base='b' * 40, head='h' * 40, regression_tests=['test_a.py'])
        self.calls = []
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        patch = mock.patch.object(review_evidence, 'failing_before', side_effect=self.measure)
        patch.start()
        self.addCleanup(patch.stop)
        self.outcome = (['test_a.py::test_a'], [])

    def measure(self, base, changed, names):
        self.calls.append((base, tuple(changed), tuple(names)))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def ask(self):
        return review_evidence.failing_before_kept(self.directory, self.state, ['test_a.py'])

    def test_a_second_question_about_the_same_candidate_is_not_measured_again(self):
        """The measurement runs every node of the changed files against the base's tree, which
        on a large module is ten minutes, and five commands ask it about one candidate."""
        first = self.ask()
        second = self.ask()
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), 1)

    def test_changed_bytes_in_a_test_file_are_measured_again(self):
        """The key holds the files' bytes, so an edit the head does not show cannot be answered
        from a measurement of the file as it was."""
        self.ask()
        (self.repo / 'test_a.py').write_text('def test_a():\n    assert False\n')
        self.ask()
        self.assertEqual(len(self.calls), 2)

    def test_another_candidate_or_base_is_measured_again(self):
        self.ask()
        self.state = dict(self.state, head='i' * 40)
        self.ask()
        self.state = dict(self.state, review_base='c' * 40)
        self.ask()
        self.assertEqual(len(self.calls), 3)

    def test_a_refused_measurement_is_never_replayed(self):
        """Only a completed measurement is stored: a refusal must reach the next caller as the
        measurement being taken, not as an answer someone remembered."""
        self.outcome = SystemExit('could not collect')
        with self.assertRaises(SystemExit):
            self.ask()
        self.outcome = (['test_a.py::test_a'], [])
        self.ask()
        self.assertEqual(len(self.calls), 2)

    def test_a_record_that_cannot_be_read_is_measured_again(self):
        self.ask()
        next(self.directory.glob('failing-before-*.json')).write_text('{not json')
        self.ask()
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
