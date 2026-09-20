"""The prose pass's envelope: what a correction may leave behind, and what it may not."""
import os
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
         '    return value > LIMIT  # strict, because LIMIT itself is allowed\n')
NOTES = '# Notes\n\nThe limit is ten.\n'


class Bench:
    """A one-commit repository the pass then edits in place."""

    def __init__(self, case, files=None):
        self.where = Path(tempfile.mkdtemp())
        case.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.where)]))
        for name, text in (files or {'thing.py': START}).items():
            (self.where / name).parent.mkdir(parents=True, exist_ok=True)
            (self.where / name).write_text(text)
        subprocess.run(['git', 'init', '-q', str(self.where)], check=True)
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A',
                                     'commit', '-q', '-m', 'x']):
            subprocess.run(['git', '-C', str(self.where), *args], check=True)

    def write(self, text, name='thing.py'):
        (self.where / name).write_text(text)

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

    def test_correcting_a_docstring_is_allowed(self):
        bench = Bench(self)
        bench.write(START.replace('"""Whether value exceeds the limit."""',
                                  '"""Whether value is over the limit, strictly."""'))
        self.assertEqual(bench.offences(), [])

    def test_correcting_the_comment_on_a_line_of_code_is_allowed(self):
        """The commonest edit there is, and the one a line-based envelope could not admit:
        the line is code, so any change to it read as a code change. The syntax tree does
        not carry the comment, so the tree is identical and the edit is inside."""
        bench = Bench(self)
        bench.write(START.replace('# strict, because LIMIT itself is allowed',
                                  '# strict: a value AT the limit is inside it'))
        self.assertEqual(bench.offences(), [])

    def test_changing_a_line_of_code_is_refused(self):
        """The outcome that would be worse than the defect: reviewers are told this pass
        touched no behaviour, so a behaviour edit inside it is a false statement to them."""
        bench = Bench(self)
        bench.write(START.replace('return value > LIMIT', 'return value >= LIMIT'))
        found = ' | '.join(bench.offences())
        self.assertIn('behaviour changed, not prose', found)
        self.assertIn('value >= LIMIT', found)

    def test_changing_the_code_beside_a_comment_is_refused(self):
        """Same line as the allowed case above, other half of it."""
        bench = Bench(self)
        bench.write(START.replace('return value > LIMIT  # strict',
                                  'return value >= LIMIT  # strict'))
        self.assertIn('behaviour changed', ' | '.join(bench.offences()))

    def test_deleting_a_line_of_code_is_refused(self):
        bench = Bench(self)
        bench.write(START.replace('LIMIT = 10\n', ''))
        self.assertIn('behaviour changed', ' | '.join(bench.offences()))

    def test_reordering_statements_is_refused(self):
        """Nothing was added or removed, so a line-based check might pass it; the tree is
        ordered, so it does not."""
        bench = Bench(self)
        head, _, tail = START.partition('def over(value):\n')
        bench.write('def over(value):\n' + tail + head)
        self.assertIn('behaviour changed', ' | '.join(bench.offences()))

    def test_adding_prose_is_refused(self):
        """An improved comment is new surface nothing checks, which is the loop restarting."""
        bench = Bench(self)
        bench.write(START + '# One more thought about why this exists.\n')
        self.assertIn('prose grew by 1', ' | '.join(bench.offences()))

    def test_a_shorter_correction_that_also_edits_code_is_still_refused(self):
        bench = Bench(self)
        bench.write(START.replace('# Six attempts at this rule, and it guards the limit.\n', '')
                         .replace('value > LIMIT', 'value >= LIMIT'))
        self.assertIn('behaviour changed', ' | '.join(bench.offences()))

    def test_markdown_is_prose_throughout_and_may_not_grow(self):
        bench = Bench(self, {'NOTES.md': NOTES})
        bench.write('# Notes\n\nThe limit is ten, strictly.\n', name='NOTES.md')
        self.assertEqual(bench.offences(), [])
        bench.write(NOTES + '\nAnd one more thing.\n', name='NOTES.md')
        self.assertIn('prose grew by 1', ' | '.join(bench.offences()))

    def test_a_file_this_pass_cannot_read_is_refused(self):
        bench = Bench(self, {'app.ts': 'export const limit = 10 // ten\n'})
        bench.write('export const limit = 10 // the limit\n', name='app.ts')
        self.assertIn('nothing here can show its change is prose', ' | '.join(bench.offences()))

    def test_a_new_file_is_refused(self):
        """Asserted by the refusal's own words: 'is new' alone also matched the growth
        refusal's 'is new surface', so the mutant that dropped this branch survived on it."""
        bench = Bench(self)
        bench.write('# a whole new file of prose\n', name='more.py')
        self.assertIn('more.py is new: a pass corrects prose that exists', ' | '.join(bench.offences()))

    def test_a_deleted_file_is_refused(self):
        bench = Bench(self)
        (bench.where / 'thing.py').unlink()
        self.assertIn('was deleted', ' | '.join(bench.offences()))

    def test_growth_in_one_file_is_not_paid_for_by_a_cut_in_another(self):
        bench = Bench(self, {'thing.py': START, 'NOTES.md': NOTES})
        bench.write(START.replace('# Six attempts at this rule, and it guards the limit.\n', ''))
        bench.write(NOTES + '\nAnd one more thing.\n', name='NOTES.md')
        self.assertIn('NOTES.md: prose grew by 1', ' | '.join(bench.offences()))

    def test_a_file_that_does_not_parse_is_refused(self):
        """Nothing can show a change is prose in a file with no syntax tree."""
        bench = Bench(self)
        bench.write(START.replace('def over(value):', 'def over(value'))
        self.assertIn('does not parse', ' | '.join(bench.offences()))

    def test_a_coding_declaration_or_shebang_change_is_refused(self):
        """The two comments Python itself reads: a cookie changed from utf-8 to latin-1 passed
        as prose while changing what the file prints."""
        text = '#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nX = "e"\n'
        bench = Bench(self, {'mod.py': text})
        bench.write(text.replace('utf-8', 'latin-1'), name='mod.py')
        self.assertIn('coding declaration changed', ' | '.join(bench.offences()))
        bench.write(text.replace('python3', 'sh'), name='mod.py')
        self.assertIn('coding declaration changed', ' | '.join(bench.offences()))

    def test_a_docstring_that_mentions_an_encoding_is_still_prose(self):
        """PEP 263 reads a cookie from a comment only; matching the word anywhere refused a
        reworded docstring, which is a refusal the envelope cannot show."""
        text = '"""Reads a stream with a declared encoding: utf-8 is assumed."""\nX = 1\n'
        bench = Bench(self, {'mod.py': text})
        bench.write('"""Reads a stream with its declared character set."""\nX = 1\n', name='mod.py')
        self.assertEqual(bench.offences(), [])

    def test_a_second_line_coding_comment_after_code_is_prose(self):
        """Python reads a cookie on line two only when line one is blank or a comment; after
        code it is an ordinary comment, and rewording it is inside the envelope."""
        text = 'x = 1\n# coding: old wording\n'
        bench = Bench(self, {'mod.py': text})
        bench.write('x = 1\n# coding: new wording\n', name='mod.py')
        self.assertEqual(bench.offences(), [])

    def test_a_hidden_untracked_file_is_still_an_offence(self):
        """status.showUntrackedFiles=no empties a plain listing; the envelope asks for every
        untracked file explicitly, or a file the reader created would pass unseen."""
        bench = Bench(self)
        subprocess.run(['git', '-C', str(bench.where), 'config', 'status.showUntrackedFiles', 'no'], check=True)
        bench.write('# a whole new file of prose\n', name='more.py')
        self.assertIn('more.py is new', ' | '.join(bench.offences()))

    def test_a_reader_edit_in_an_assume_unchanged_file_is_seen(self):
        """git status honours the assume-unchanged bit, and a reader's behaviour edit in such a
        file was recorded as inside the envelope. The listing compares bytes with HEAD."""
        bench = Bench(self)
        subprocess.run(['git', '-C', str(bench.where), 'update-index', '--assume-unchanged', 'thing.py'], check=True)
        bench.write(START.replace('value > LIMIT', 'value >= LIMIT'))
        self.assertIn('behaviour changed', ' | '.join(bench.offences()))

    def test_a_reader_edit_in_a_skip_worktree_file_is_seen(self):
        """The skip-worktree bit hides a path from git status like assume-unchanged does. A
        scratch index carries no such bit, so a present file is compared like any other; the
        bit excuses an absence and nothing else."""
        bench = Bench(self)
        subprocess.run(['git', '-C', str(bench.where), 'update-index', '--skip-worktree', 'thing.py'], check=True)
        bench.write(START.replace('value > LIMIT', 'value >= LIMIT'))
        self.assertIn('behaviour changed', ' | '.join(bench.offences()))
        # Absent with the bit: what a sparse checkout does on purpose, so not a change.
        (bench.where / 'thing.py').unlink()
        self.assertEqual(bench.offences(), [])

    def test_a_crlf_file_under_text_auto_is_not_a_change(self):
        """Hashing the bytes outside the index normalised CRLF that git's safe-crlf rule keeps
        when the index blob already carries it, and refused a clean tree forever. The listing
        asks git, which applies its own conversion against the scratch index."""
        bench = Bench(self, {'win.py': 'x = 1\r\n'})
        (bench.where / '.gitattributes').write_text('* text=auto\n')
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A', 'commit', '-qm', 'attrs']):
            subprocess.run(['git', '-C', str(bench.where), *args], check=True)
        self.assertEqual(bench.offences(), [])

    def test_an_ignored_file_the_pass_created_is_an_offence(self):
        """An ignored file never reaches a candidate, so one that predates the pass is not a
        change; one the reader creates is a file it left, seen by comparing the set before
        and after."""
        bench = Bench(self, {'thing.py': START, '.gitignore': 'secret.env\n'})
        (bench.where / 'secret.env').write_text('k\n')
        self.assertEqual(bench.offences(), [])
        self.assertIn('secret.env is ignored and new', ' | '.join(prose.offences(cwd=str(bench.where), ignored_before=set())))
        self.assertEqual(prose.offences(cwd=str(bench.where), ignored_before={'secret.env'}), [])

    def test_a_tracked_name_with_a_newline_is_seen(self):
        """A newline in a name broke the one-per-line protocol of the previous listing and
        silently dropped every file after it; git's own listing is NUL-separated."""
        name = 'a\nb.py'
        bench = Bench(self, {name: 'x = 1\n'})
        subprocess.run(['git', '-C', str(bench.where), 'update-index', '--assume-unchanged', name], check=True)
        bench.write('x = 2\n', name=name)
        self.assertIn('behaviour changed', ' | '.join(bench.offences()))

    def test_a_mode_only_change_is_seen(self):
        """chmod +x leaves the text equal, so neither the tree nor the growth check moves; git
        lists the file, and a listed file with identical text is a mode or line-ending
        change, which is not prose."""
        bench = Bench(self)
        subprocess.run(['git', '-C', str(bench.where), 'update-index', '--assume-unchanged', 'thing.py'], check=True)
        (bench.where / 'thing.py').chmod(0o755)
        self.assertIn('changed in mode or line endings', ' | '.join(bench.offences()))

    def test_a_staged_rename_names_both_paths(self):
        """The previous listing sliced a rename's second row as a status row and named
        `hing.py`; against the scratch index the old path is a deletion and the new one an
        untracked file, each by its own name."""
        bench = Bench(self)
        subprocess.run(['git', '-C', str(bench.where), 'mv', 'thing.py', 'other.py'], check=True)
        found = ' | '.join(bench.offences())
        self.assertIn('thing.py was deleted', found)
        self.assertIn('other.py is new', found)

    def test_a_sparse_checkout_is_inside_the_envelope(self):
        """A sparse checkout leaves files absent on purpose; its patterns are reapplied to the
        scratch index, so those absences are not deletions."""
        bench = Bench(self, {'keep/k.py': 'x = 1\n', 'drop/d.py': 'y = 2\n'})
        subprocess.run(['git', '-C', str(bench.where), 'sparse-checkout', 'set', 'keep'], check=True, capture_output=True)
        self.assertFalse((bench.where / 'drop/d.py').exists())
        self.assertEqual(bench.offences(), [])

    def test_a_clean_tree_is_inside_the_envelope(self):
        self.assertEqual(Bench(self).offences(), [])

    def test_the_envelope_answers_the_same_from_a_subdirectory(self):
        bench = Bench(self)
        (bench.where / 'deep').mkdir()
        bench.write(START.replace('value > LIMIT', 'value >= LIMIT'))
        was = os.getcwd()
        os.chdir(bench.where / 'deep')
        self.addCleanup(os.chdir, was)
        self.assertIn('behaviour changed', ' | '.join(prose.offences(cwd=str(bench.where / 'deep'))))


class PrepareTests(unittest.TestCase):

    def two_commits(self, before, after):
        bench = Bench(self, {'thing.py': before})
        bench.write(after)
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A',
                                     'commit', '-q', '-m', 'y']):
            subprocess.run(['git', '-C', str(bench.where), *args], check=True)
        revs = subprocess.run(['git', '-C', str(bench.where), 'rev-list', 'HEAD'],
                              capture_output=True, text=True).stdout.split()
        return bench, revs[1], revs[0]

    def test_the_task_carries_the_rule_and_the_added_prose(self):
        bench, base, head = self.two_commits('LIMIT = 10\n', START)
        task = prose.prepare(base, head, cwd=str(bench.where))
        self.assertIn('Keep every sentence that says WHY', task)
        self.assertIn('--- thing.py', task)
        self.assertIn('Six attempts at this rule', task)

    def test_a_delta_with_no_added_prose_produces_no_task(self):
        bench, base, head = self.two_commits('LIMIT = 10\n', 'LIMIT = 11\n')
        self.assertEqual(prose.prepare(base, head, cwd=str(bench.where)), '')


if __name__ == '__main__':
    unittest.main()
