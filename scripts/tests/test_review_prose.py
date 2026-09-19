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
        found = ' | '.join(bench.offences())
        # Asserted by what it says, not by how many it says: an edited line is an addition
        # AND a removal, and pinning the count made this case fail when removals started
        # being read — which was the defect, not the fix.
        self.assertIn('adds code, not prose', found)
        self.assertIn('value >= LIMIT', found)
        self.assertIn('removes code, not prose', found)
        self.assertIn('value > LIMIT', found)

    def test_adding_prose_is_refused(self):
        """An improved comment is new surface nothing checks, which is the loop restarting."""
        bench = Bench(self)
        bench.write(START + '# One more thought about why this exists.\n')
        self.assertIn('prose grew by 1', ' | '.join(bench.offences()))

    def test_a_shorter_correction_that_also_edits_code_is_still_refused(self):
        """Both halves are checked: cutting prose does not buy a code edit."""
        bench = Bench(self)
        bench.write('LIMIT = 10\ndef over(value):\n    return value >= LIMIT\n')
        found = bench.offences()
        self.assertTrue(any('code, not prose' in f for f in found), found)

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

    def test_deleting_a_line_of_code_is_refused(self):
        """The hole the first reviewer found: reading only added lines let a deletion — of a
        line, or of a whole source file — pass as prose only."""
        bench = Bench(self)
        bench.write('LIMIT = 10\n# Six attempts at this rule, and it guards the limit.\n'
                    'def over(value):\n    """Whether value exceeds the limit."""\n')
        self.assertIn('removes code, not prose', ' | '.join(bench.offences()))

    def test_a_file_this_pass_cannot_read_is_refused(self):
        """Only Python and Markdown are classified. A changed .ts or .sh cannot be shown to
        be prose, and saying so is the difference between silence and a false statement."""
        bench = Bench(self)
        (bench.where / 'script.sh').write_text('exit 1\n')
        self.assertIn('not a file this pass can read', ' | '.join(bench.offences()))

    def test_growth_in_one_file_is_not_paid_for_by_a_cut_in_another(self):
        """Summing across files let an added comment be bought with an unrelated deletion."""
        bench = Bench(self)
        bench.write(START.replace('# Six attempts at this rule, and it guards the limit.\n', ''))
        (bench.where / 'other.py').write_text('# a\n# b\n# c\nY = 1\n')
        self.assertTrue(any('other.py: prose grew' in f for f in bench.offences()))


class WorkingDirectoryTests(unittest.TestCase):

    def test_the_envelope_answers_the_same_from_a_subdirectory(self):
        """An envelope whose verdict depends on where it was invoked approves a code edit by
        being run one directory down."""
        bench = Bench(self)
        (bench.where / 'sub').mkdir()
        bench.write(START.replace('return value > LIMIT', 'return value >= LIMIT'))
        from_top = prose.offences(cwd=str(bench.where))
        from_sub = prose.offences(cwd=str(bench.where / 'sub'))
        self.assertTrue(any('code, not prose' in f for f in from_top), from_top)
        self.assertEqual(from_sub, from_top)


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
