"""The envelope: what a prose pass may change, checked rather than trusted."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
import review_prose as prose                                        # noqa: E402

START = ('LIMIT = 10\n'
         '# Six attempts at this rule, and it guards the limit.\n'
         'def over(value):\n'
         '    """Whether value exceeds the limit."""\n'
         '    return value > LIMIT\n')


class Bench:

    def __init__(self, case, text=START, name='thing.py'):
        self.where = Path(tempfile.mkdtemp())
        case.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.where)]))
        self.name = name
        (self.where / name).write_text(text)
        subprocess.run(['git', 'init', '-q', str(self.where)], check=True)
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A',
                                     'commit', '-q', '-m', 'x']):
            subprocess.run(['git', '-C', str(self.where), *args], check=True)

    def write(self, text):
        (self.where / self.name).write_text(text)

    def offences(self):
        return prose.offences(cwd=str(self.where))


class EnvelopeTests(unittest.TestCase):

    def test_correcting_a_comment_is_allowed(self):
        bench = Bench(self)
        bench.write(START.replace('# Six attempts at this rule, and it guards the limit.',
                                  '# Guards the limit because callers pass unbounded input.'))
        self.assertEqual(bench.offences(), [])

    def test_deleting_prose_is_allowed(self):
        """Cutting is the point: a sentence that cannot stay true is better gone."""
        bench = Bench(self)
        bench.write(START.replace('# Six attempts at this rule, and it guards the limit.\n', ''))
        self.assertEqual(bench.offences(), [])

    def test_changing_a_line_of_code_is_refused(self):
        """The outcome that would be worse than the defect: reviewers are told this pass
        touched no behaviour, so a behaviour edit inside it is a false statement to them."""
        bench = Bench(self)
        bench.write(START.replace('return value > LIMIT', 'return value >= LIMIT'))
        found = bench.offences()
        self.assertEqual(len(found), 1)
        self.assertIn('is code, not prose', found[0])
        self.assertIn('value >= LIMIT', found[0])

    def test_adding_prose_is_refused(self):
        """An improved comment is new surface nothing checks, which is the loop restarting."""
        bench = Bench(self)
        bench.write(START + '# One more thought about why this exists.\n')
        found = bench.offences()
        self.assertEqual(len(found), 1)
        self.assertIn('prose grew by 1', found[0])

    def test_a_shorter_correction_that_also_edits_code_is_still_refused(self):
        """Both halves are checked: cutting prose does not buy a code edit."""
        bench = Bench(self)
        bench.write('LIMIT = 10\ndef over(value):\n    return value >= LIMIT\n')
        found = bench.offences()
        self.assertTrue(any('is code, not prose' in f for f in found), found)

    def test_markdown_is_prose_throughout(self):
        bench = Bench(self, text='It reads the limit from LIMIT.\n', name='README.md')
        bench.write('It reads the limit from the constant beside it.\n')
        self.assertEqual(bench.offences(), [])

    def test_markdown_growth_is_refused_like_any_other(self):
        bench = Bench(self, text='It reads the limit.\n', name='README.md')
        bench.write('It reads the limit.\nAnd here is more about it.\n')
        self.assertTrue(any('prose grew' in f for f in bench.offences()))

    def test_a_clean_tree_is_inside_the_envelope(self):
        self.assertEqual(Bench(self).offences(), [])


class PrepareTests(unittest.TestCase):

    def test_the_task_carries_the_rule_and_the_added_prose(self):
        bench = Bench(self)
        bench.write(START + '# A newly added sentence about the limit.\n')
        subprocess.run(['git', '-C', str(bench.where), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(bench.where), '-c', 'user.email=a@b.invalid',
                        '-c', 'user.name=A', 'commit', '-q', '-m', 'y'], check=True)
        task = prose.prepare('HEAD~1', 'HEAD', cwd=str(bench.where))
        self.assertIn('Keep every sentence that says WHY', task)
        self.assertIn('A newly added sentence about the limit.', task)
        self.assertIn('thing.py', task)

    def test_a_delta_with_no_added_prose_produces_no_task(self):
        """No task is the right answer, not an empty one: a pass with nothing to read is a
        subagent call that costs time and returns opinion."""
        bench = Bench(self)
        bench.write(START.replace('LIMIT = 10', 'LIMIT = 11'))
        subprocess.run(['git', '-C', str(bench.where), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(bench.where), '-c', 'user.email=a@b.invalid',
                        '-c', 'user.name=A', 'commit', '-q', '-m', 'y'], check=True)
        self.assertEqual(prose.prepare('HEAD~1', 'HEAD', cwd=str(bench.where)), '')


if __name__ == '__main__':
    unittest.main()
