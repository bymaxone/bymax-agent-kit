"""What the brief shows both reviewers about a delta: its code with the prose elided, what the
claims checker settled, and which tests this delta wrote as against what a merge carried in."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
import review_delta
import review_evidence
# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FlowBench


class BriefTests(FlowBench):
    """The first round's brief, read from a campaign started in the fixture repository."""

    def test_the_first_round_brief_carries_the_code_view(self):
        """The round that reads the WHOLE delta used to receive none of the three views: they
        were built inside correction_brief, which returns early on round one, while the
        changelog said every reviewer receives them. Round one is where 'these checks read
        NOTHING in N changed files of other kinds' matters most — on a repository of languages
        they cannot read, that sentence is what stops silence from reading as clean."""
        self.start()
        self.checks()
        brief = self.flow('prompt').stdout
        self.assertIn('prose elided', brief)
        self.assertIn('Prose in this delta', brief)

    def test_the_first_round_brief_names_the_tests_the_delta_changed(self):
        """The note read a key only a correction round sets, and the round it was first shown
        on round one it said "No test changed in this delta. Recorded reason: ." about a
        delta that changed four test files. It reads the diff now, on every round."""
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_x.py').write_text('def test_x(): assert 1 == 1\n')
        self.commit('a candidate that adds a test')
        self.start()
        self.checks()
        brief = self.flow('prompt').stdout
        self.assertIn('Tests changed in this delta: tests/test_x.py', brief)
        self.assertNotIn('Recorded reason: .', brief)


class BriefShowsTheDeltaTests(unittest.TestCase):
    """What the brief RENDERS, which no case reached until now.

    Both reviewers found the same hole from two directions: the matrix mutates review_claims
    and review_matrix, so the two halves of the brief that live in review_delta were uncovered. Replacing
    the removal check's call with `[]` and collapsing the three-state marker to a constant both
    left the suite green, and each restores a defect a reviewer had already filed once.
    """

    def setUp(self):
        """Enter a two-commit repository: both functions read the process cwd, not an argument."""
        self.where = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.where, ignore_errors=True))
        for command in (['init', '-q'], ['config', 'user.email', 'c@example.invalid'],
                        ['config', 'user.name', 'C']):
            subprocess.run(['git', '-C', str(self.where)] + command, check=True)
        was = os.getcwd()
        os.chdir(self.where)
        self.addCleanup(os.chdir, was)

    def commit(self, files, drop=()):
        for name in drop:
            (self.where / name).unlink()
        for name, text in files.items():
            (self.where / name).write_text(text)
        subprocess.run(['git', '-C', str(self.where), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(self.where), 'commit', '-q', '-m', 'x',
                        '--allow-empty'], check=True)
        return subprocess.run(['git', '-C', str(self.where), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip()

    def test_what_a_merge_carried_in_is_told_from_what_this_delta_wrote(self):
        """Asking whether head's bytes match a side the merge brought in got this wrong: a
        test this delta wrote that the other side wrote identically vanished from the list,
        and the matrix gate went silent about it. The question is provenance."""
        run = lambda *args: subprocess.run(['git', '-C', str(self.where), *args], check=True,
                                           capture_output=True)
        head = lambda: subprocess.run(['git', '-C', str(self.where), 'rev-parse', 'HEAD'],
                                      capture_output=True, text=True).stdout.strip()
        shared = {'test_shared.py': 'def test_shared():\n    assert True\n'}
        start = self.commit(dict(shared))
        # The other side adds a test of its own, and one whose bytes match what this delta
        # writes below.
        run('checkout', '-q', '-b', 'other', start)
        self.commit(dict(shared, **{'test_theirs.py': 'def test_theirs():\n    assert True\n',
                                    'test_same.py': 'def test_same():\n    assert True\n'}))
        run('checkout', '-q', '-')
        base = self.commit(dict(shared))
        self.commit(dict(shared, **{'test_mine.py': 'def test_mine():\n    assert True\n',
                                    'test_same.py': 'def test_same():\n    assert True\n'}))
        run('merge', '-q', '--no-edit', 'other')
        self.assertEqual(review_evidence.tests_changed(base, head())[0],
                         ['test_mine.py', 'test_same.py'])
        # A test both sides changed is resolved by hand in the merge, and somebody typing a
        # resolution is this delta writing the file, however much of it came from either side.
        (self.where / 'test_shared.py').write_text('def test_shared():\n    assert 2\n')
        run('add', '-A')
        run('-c', 'user.email=c@example.invalid', '-c', 'user.name=C', 'commit', '-q',
            '--amend', '--no-edit')
        self.assertEqual(review_evidence.tests_changed(base, head())[0],
                         ['test_mine.py', 'test_same.py', 'test_shared.py'])
        # And a file edited after the merge is this delta's, however it arrived.
        self.commit({'test_theirs.py': 'def test_theirs():\n    assert 1\n'})
        self.assertEqual(review_evidence.tests_changed(base, head())[0],
                         ['test_mine.py', 'test_same.py', 'test_shared.py', 'test_theirs.py'])

    def test_a_branch_already_merged_upstream_is_still_this_delta(self):
        """Found by a reviewer: excluding what a named ref already held dropped the work of a
        branch whose commits the base branch had merged, and the gate fell silent on a delta
        that really did change a test. Nothing is excluded by what another ref holds."""
        run = lambda *args: subprocess.run(['git', '-C', str(self.where), *args], check=True,
                                           capture_output=True)
        base = self.commit({'test_old.py': 'def test_old():\n    assert 1\n'})
        run('checkout', '-q', '-b', 'feature')
        self.commit({'test_old.py': 'def test_old():\n    assert 1\n',
                     'test_new.py': 'def test_new():\n    assert 1\n'})
        run('checkout', '-q', '-')
        run('merge', '-q', '--no-ff', '--no-edit', 'feature')
        run('update-ref', 'refs/remotes/origin/main', 'HEAD')
        run('checkout', '-q', 'feature')
        head = subprocess.run(['git', '-C', str(self.where), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(review_evidence.tests_changed(base, head)[0], ['test_new.py'])

    def test_work_merged_in_off_the_first_parent_line_is_not_read_as_written_here(self):
        """The stated limit, pinned so it stays a contract rather than a hole: only the
        first-parent line counts, and work merged in with `--no-ff` is off it."""
        run = lambda *args: subprocess.run(['git', '-C', str(self.where), *args], check=True,
                                           capture_output=True)
        base = self.commit({'test_t.py': 'def test_t():\n    assert 1\n'})
        run('checkout', '-q', '-b', 'topic')
        self.commit({'test_t.py': 'def test_t():\n    assert 2\n'})
        run('checkout', '-q', '-')
        run('merge', '-q', '--no-ff', '--no-edit', 'topic')
        head = subprocess.run(['git', '-C', str(self.where), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(review_evidence.tests_changed(base, head)[0], [])

    def test_the_brief_shows_a_removal_claim_the_check_only_reports(self):
        """An independent reviewer found that nothing on the flow path executed the removal check, so its rows
        reached nobody while the brief said they did. The fix was to RUN it; this is what
        fails when it stops being run — replacing the call with `[]` passes every other case.
        """
        base = self.commit({'a.py': 'X = 1  # most likely never joined\n'})
        head = self.commit({'a.py': 'X = 1  # most likely never joined\n',
                            'NOTES.md': 'We removed `most likely never joined` from it.\n'})
        said = review_delta.claims_coverage({'review_base': base, 'head': head})
        self.assertIn('REPORTED, not refusing', said)
        self.assertIn('most likely never joined', said)

    def test_the_code_view_marks_an_addition_a_removal_and_a_change_with_no_line(self):
        """A removal reached reviewers through the format an addition uses, and a file that
        changed without any line changing was then announced as one too. Three states, three
        marks: collapsing the expression to any single constant fails here.
        """
        base = self.commit({'a.py': 'A = 1\nB = 2\n', 'bin.dat': 'x'})
        head = self.commit({'a.py': 'A = 1\nC = 3\n', 'bin.dat': 'x'})
        subprocess.run(['chmod', '+x', str(self.where / 'bin.dat')], check=True)
        head = self.commit({})
        shown = review_delta.code_view({'review_base': base, 'head': head})
        marks = {line.strip()[0] for line in shown.split('\n') if line.startswith('  ')}
        self.assertEqual(marks, {'+', '-', '?'}, shown)


if __name__ == '__main__':
    unittest.main()
