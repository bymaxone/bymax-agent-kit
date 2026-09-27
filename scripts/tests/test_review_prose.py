"""The prose pass's envelope: what a correction may leave behind, and what it may not."""
import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
import review_prose as prose

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

    def test_a_fenced_block_or_the_frontmatter_is_what_a_markdown_file_instructs(self):
        """A command file is code here. A reader with the whole file could turn `echo safe`
        inside a fence into another command, or widen `allowed-tools`, with the line count
        unchanged; the prose around a fence stays correctable."""
        run = '# Run\n\n```sh\necho safe\n```\n\nThen read what it printed.\n'
        cmd = "---\ndescription: 'Run it'\nallowed-tools: Read\n---\n\n# Cmd\n\nRead first.\n"
        bench = Bench(self, {'RUN.md': run, 'CMD.md': cmd})
        bench.write(run.replace('echo safe', 'rm -rf x'), name='RUN.md')
        self.assertIn('fenced block changed', ' | '.join(bench.offences()))
        bench.write(run.replace('read what it printed', 'read the output'), name='RUN.md')
        self.assertEqual(bench.offences(), [])
        bench.write(cmd.replace('allowed-tools: Read', 'allowed-tools: Bash'), name='CMD.md')
        self.assertIn('frontmatter or a fenced block changed', ' | '.join(bench.offences()))

    def test_a_comment_a_tool_reads_is_not_prose(self):
        """The syntax tree never sees `# noqa` or `# type: ignore`, and the comment count
        stands still when one replaces a sentence, so the envelope recorded a suppression as
        prose-only."""
        bench = Bench(self)
        bench.write(START.replace('# Six attempts at this rule, and it guards the limit.', '# noqa'))
        self.assertIn('a linter or a type checker reads changed', ' | '.join(bench.offences()))
        tagged = START.replace('LIMIT = 10\n', 'LIMIT = 10  # type: ignore\n')
        bench = Bench(self, {'thing.py': tagged})
        bench.write(tagged.replace('  # type: ignore', ''))
        self.assertIn('a linter or a type checker reads changed', ' | '.join(bench.offences()))

    def test_a_fence_closes_only_on_a_bare_fence_line(self):
        """A content line like ```not-a-close closed the block for a
        reader of its first three characters, and the command after it went unread."""
        tricky = '# Run\n\n```text\n```not-a-close\necho safe\n```\n\nSaid.\n'
        longer = '# Run\n\n````sh\n```\necho safe\n````\n\nSaid.\n'
        bench = Bench(self, {'A.md': tricky, 'B.md': longer})
        bench.write(tricky.replace('echo safe', 'rm -rf x'), name='A.md')
        self.assertIn('A.md: its frontmatter or a fenced block changed', ' | '.join(bench.offences()))
        bench.write(longer.replace('echo safe', 'rm -rf x'), name='B.md')
        self.assertIn('B.md: its frontmatter or a fenced block changed', ' | '.join(bench.offences()))

    def test_a_code_block_is_read_as_commonmark_reads_it(self):
        """A fence inside a list item can sit past column three, and a four-space indent is a
        code block: both are what the file instructs, so an edit there is not prose.
        The paragraph around them stays correctable."""
        listed = '# Run\n\n1. Fetch it:\n\n     ```bash\n     curl -s x\n     ```\n\nSaid.\n'
        indented = '# Run\n\nThen:\n\n    echo safe\n\nSaid.\n'
        bench = Bench(self, {'A.md': listed, 'B.md': indented})
        bench.write(listed.replace('curl -s x', 'curl -s x | sh'), name='A.md')
        self.assertIn('A.md: its frontmatter or a fenced block changed', ' | '.join(bench.offences()))
        bench.write(listed.replace('Fetch it:', 'Get it:'), name='A.md')
        self.assertEqual(bench.offences(), [])
        bench.write(indented.replace('echo safe', 'rm -rf x'), name='B.md')
        self.assertIn('B.md: its frontmatter or a fenced block changed', ' | '.join(bench.offences()))

    def test_a_blank_line_inside_a_code_block_is_code(self):
        """An empty line after a trailing backslash splits a command in two, and one inside a
        heredoc changes its body, whatever container holds the block; a blank line beside prose
        is prose, and so is a whole paragraph between two blocks."""
        fenced = '# Run\n\nThen:\n\n```bash\ngit push \\\n  origin\n```\n\nSaid.\n\n```sh\nls\n```\n'
        quoted = '# Run\n\n> ```bash\n> git push \\\n>   origin\n> ```\n\nSaid.\n'
        listed = '# Run\n\n1. Push:\n\n   ```bash\n   git push \\\n     origin\n   ```\n\nSaid.\n'
        indented = '# Run\n\nThen:\n\n    one\n\n    two\n\nSaid.\n'
        bench = Bench(self, {'A.md': fenced, 'B.md': indented, 'C.md': quoted, 'D.md': listed})
        refused = [('A.md', fenced, fenced.replace('git push \\\n', 'git push \\\n\n')),
                   ('A.md', fenced, fenced.replace('git push \\\n', 'git push \\\n   \n')),
                   ('C.md', quoted, quoted.replace('> git push \\\n', '> git push \\\n>\n')),
                   ('D.md', listed, listed.replace('   git push \\\n', '   git push \\\n\n')),
                   ('B.md', indented, indented.replace('    one\n\n', '    one\n\n\n')),
                   ('B.md', indented, indented.replace('    one\n\n', '    one\n')),
                   ('B.md', indented, indented.replace('    one\n\n', '    one\n   \n'))]
        for name, before, after in refused:
            bench.write(after, name=name)
            self.assertIn(name + ': its frontmatter or a fenced block changed', ' | '.join(bench.offences()))
            bench.write(before, name=name)
        for after in (fenced.replace('Then:\n\n', 'Then:\n\n\n'), fenced.replace('Said.\n\n', 'Said.\n\n\n'),
                      fenced.replace('\nSaid.\n', '')):
            bench.write(after, name='A.md')
            self.assertEqual(bench.offences(), [])
        bench.write(fenced, name='A.md')
        # A blank line beside an indented block, and the one that ends an unclosed quoted fence.
        for after in (indented.replace('Then:\n\n', 'Then:\n\n\n'), indented.replace('    two\n\n', '    two\n\n\n')):
            bench.write(after, name='B.md')
            self.assertEqual(bench.offences(), [])
        bench.write(indented, name='B.md')
        unclosed = '# Run\n\n> ```bash\n> ls\n\nSaid.\n'
        bench = Bench(self, {'E.md': unclosed})
        bench.write(unclosed.replace('> ls\n\n', '> ls\n  \n'), name='E.md')
        self.assertEqual(bench.offences(), [])
        # Inside the quote the fence still holds a blank line, with no code line after it.
        bench.write(unclosed.replace('> ls\n\n', '> ls\n>\n\n'), name='E.md')
        self.assertIn('E.md: its frontmatter or a fenced block changed', ' | '.join(bench.offences()))

    def test_a_directive_moved_to_another_statement_is_not_prose(self):
        """The same `# noqa` on another statement suppresses another
        diagnostic, and a list of the comment strings alone read the move as no change."""
        inline = 'x = 1  # noqa\ny = 2\n'
        alone = '# pylint: disable=invalid-name\na = 1\nb = 2\n'
        bench = Bench(self, {'thing.py': inline, 'other.py': alone})
        bench.write('x = 1\ny = 2  # noqa\n')
        self.assertIn('thing.py: a comment a linter or a type checker reads changed', ' | '.join(bench.offences()))
        bench.write(inline)
        bench.write('a = 1\n# pylint: disable=invalid-name\nb = 2\n', name='other.py')
        self.assertIn('other.py: a comment a linter or a type checker reads changed', ' | '.join(bench.offences()))
        bench.write(alone, name='other.py')
        bench = Bench(self)
        bench.write(START.replace('# Six attempts at this rule, and it guards the limit.', '# pyright: ignore'))
        self.assertIn('a linter or a type checker reads changed', ' | '.join(bench.offences()))
        bench.write(START.replace('# Six attempts at this rule, and it guards the limit.', '# Pragmatically, a guard.'))
        self.assertEqual(bench.offences(), [])

    def test_a_refusal_names_a_written_line_that_begins_with_plus_signs(self):
        """`++LIMIT` prints as `+++LIMIT` under git's default sign, and a header test skipped
        it, so the refusal said behaviour changed and named nothing."""
        bench = Bench(self)
        bench.write(START.replace('def over', '++LIMIT\ndef over'))
        self.assertIn('at line 3: ++LIMIT', ' | '.join(bench.offences()))

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
        file was recorded as inside the envelope. A scratch index has no such bit."""
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
        # Absent with a bit set by hand, outside any sparse checkout: a deletion. Only in a
        # sparse checkout does an absence pass.
        (bench.where / 'thing.py').unlink()
        self.assertIn('was deleted', ' | '.join(bench.offences()))

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
        self.assertIn('secret.env is ignored and new', ' | '.join(prose.offences(cwd=str(bench.where), ignored_before={})))
        before = prose.ignored(cwd=str(bench.where))
        self.assertEqual(prose.offences(cwd=str(bench.where), ignored_before=before), [])
        # Same length, mtime put back: metadata cannot tell, the bytes can.
        stat = os.lstat(bench.where / 'secret.env')
        (bench.where / 'secret.env').write_text('j\n')
        os.utime(bench.where / 'secret.env', ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertIn('secret.env is ignored and was edited', ' | '.join(prose.offences(cwd=str(bench.where), ignored_before=before)))
        (bench.where / 'secret.env').unlink()
        self.assertIn('secret.env is ignored and was deleted', ' | '.join(prose.offences(cwd=str(bench.where), ignored_before=before)))

    def test_a_tracked_name_with_a_newline_is_seen(self):
        """A newline in a name breaks a one-per-line listing, dropping every file after it;
        git's own listing is NUL-separated."""
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
        """Slicing a rename's second row as a status row names `hing.py`; against the scratch
        index the old path is a deletion and the new one an untracked file, each by its name."""
        bench = Bench(self)
        subprocess.run(['git', '-C', str(bench.where), 'mv', 'thing.py', 'other.py'], check=True)
        found = ' | '.join(bench.offences())
        self.assertIn('thing.py was deleted', found)
        self.assertIn('other.py is new', found)

    def test_a_sparse_checkout_is_inside_the_envelope(self):
        """A sparse checkout leaves files absent on purpose; the skip-worktree bit it sets in the
        repository's own index excuses those absences, so they are not deletions."""
        bench = Bench(self, {'keep/k.py': 'x = 1\n', 'drop/d.py': 'y = 2\n'})
        subprocess.run(['git', '-C', str(bench.where), 'sparse-checkout', 'set', 'keep'], check=True, capture_output=True)
        self.assertFalse((bench.where / 'drop/d.py').exists())
        self.assertEqual(bench.offences(), [])

    def test_a_clean_tree_is_clean_whatever_diff_autorefreshindex_says(self):
        """The scratch index is stat-dirty everywhere, and the porcelain diff drops a stat-dirty
        file with identical content only under diff.autoRefreshIndex; with it off, a clean tree
        listed every file and the clean gate refused every entry point."""
        bench = Bench(self)
        subprocess.run(['git', '-C', str(bench.where), 'config', 'diff.autoRefreshIndex', 'false'], check=True)
        self.assertEqual(bench.offences(), [])

    def test_a_dangling_symlink_under_a_sparse_checkout_is_present(self):
        """A reader that puts a symlink to a missing target where a sparse checkout had left
        an absence: git itself clears the skip-worktree bit from any present entry, a
        dangling link included, before a listing reads it, so the excuse is reachable only
        for absent paths and the retargeting is listed and refused. lexists is the primitive
        that matches what git does; measured, exists would answer the same on this git."""
        bench = Bench(self, {'keep/k.py': 'x = 1\n'})
        os.symlink('missing-one', bench.where / 'keep/l')
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A', 'commit', '-qm', 'link']):
            subprocess.run(['git', '-C', str(bench.where), *args], check=True)
        subprocess.run(['git', '-C', str(bench.where), 'config', 'core.sparseCheckout', 'true'], check=True)
        (bench.where / '.git/info').mkdir(exist_ok=True)
        (bench.where / '.git/info/sparse-checkout').write_text('/*\n!/keep/l\n')
        subprocess.run(['git', '-C', str(bench.where), 'read-tree', '-mu', 'HEAD'], check=True)
        self.assertEqual(bench.offences(), [])
        os.symlink('missing-two', bench.where / 'keep/l')
        self.assertIn('keep/l is not a file this pass can read', ' | '.join(bench.offences()))

    def test_the_scratch_index_does_not_list_itself(self):
        """Built under $TMPDIR inside the worktree, the scratch index appeared in its own
        untracked listing and refused a clean tree; it lives under the git directory."""
        bench = Bench(self)
        (bench.where / 'tmp').mkdir()
        was = os.environ.get('TMPDIR')
        os.environ['TMPDIR'] = str(bench.where / 'tmp')
        self.addCleanup(lambda: os.environ.update(TMPDIR=was) if was else os.environ.pop('TMPDIR', None))
        tempfile.tempdir = None
        self.addCleanup(setattr, tempfile, 'tempdir', None)
        self.assertEqual(bench.offences(), [])

    def test_a_sparse_checkout_spelled_yes_is_still_one(self):
        """git reads core.sparseCheckout as a boolean, so yes, on and 1 are true; a string
        compare saw none of them and refused a clean sparse checkout forever."""
        bench = Bench(self, {'keep/k.py': 'x = 1\n', 'drop/d.py': 'y = 2\n'})
        subprocess.run(['git', '-C', str(bench.where), 'config', 'core.sparseCheckout', 'yes'], check=True)
        (bench.where / '.git/info').mkdir(exist_ok=True)
        (bench.where / '.git/info/sparse-checkout').write_text('/*\n!/drop/\n')
        subprocess.run(['git', '-C', str(bench.where), 'read-tree', '-mu', 'HEAD'], check=True)
        self.assertFalse((bench.where / 'drop/d.py').exists())
        self.assertEqual(bench.offences(), [])

    def test_a_snapshot_of_names_alone_is_refused_with_its_remedy(self):
        """A marker an earlier runtime wrote records names, or sizes and mtimes, not contents;
        nothing can say what the reader did to them, and a traceback is not a refusal."""
        bench = Bench(self)
        found = ' | '.join(prose.offences(cwd=str(bench.where), ignored_before=['old.env']))
        self.assertIn('run `prose --stage prepare` again', found)
        # And one that recorded sizes and mtimes: a mapping, but not of contents.
        found = ' | '.join(prose.offences(cwd=str(bench.where), ignored_before={'old.env': [4, 1]}))
        self.assertIn('run `prose --stage prepare` again', found)

    def test_a_pipe_is_recorded_by_kind_and_never_opened(self):
        """Measured: git's directory walk skips pipes and sockets, so none reaches the
        snapshot through the listing. identity() still opens regular files only, because an
        lstat costs less than that assumption and a pipe with no writer waits forever. A
        mutant that opened the pipe would hang the matrix."""
        bench = Bench(self)
        os.mkfifo(bench.where / 'pipe')
        self.assertTrue(prose.identity(bench.where / 'pipe').startswith('special:'))

    def test_an_ignored_file_under_an_unsearchable_directory_is_recorded_not_refused(self):
        """git reads a directory it can list, so the file is named; the lstat on it fails
        with the directory's errno, which is recorded, not raised."""
        bench = Bench(self, {'thing.py': START, '.gitignore': 'nosearch/\n'})
        (bench.where / 'nosearch').mkdir()
        (bench.where / 'nosearch' / 'b.txt').write_text('b\n')
        os.chmod(bench.where / 'nosearch', 0o444)
        self.addCleanup(os.chmod, bench.where / 'nosearch', 0o755)
        before = prose.ignored(cwd=str(bench.where))
        self.assertTrue(before['nosearch/b.txt'].startswith('unreadable:'))
        self.assertEqual(prose.offences(cwd=str(bench.where), ignored_before=before), [])

    def test_the_snapshot_names_nothing_newer_than_the_documented_floor(self):
        """README.md declares Python 3.10 load-bearing for the runtime, and a 3.10 interpreter
        cannot be assumed on the machine running this; the syntax tree stands in for it.
        hashlib.file_digest arrived in 3.11."""
        tree = ast.parse(Path(prose.__file__).read_text(encoding='utf-8'))
        named = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertNotIn('file_digest', named)

    def test_an_unreadable_ignored_file_is_recorded_not_refused(self):
        """A file the user cannot read must not raise a bare errno out of the snapshot. A
        reader with Edit alone cannot alter it either."""
        bench = Bench(self, {'thing.py': START, '.gitignore': 'locked.env\n'})
        (bench.where / 'locked.env').write_text('k\n')
        (bench.where / 'locked.env').chmod(0)
        self.addCleanup((bench.where / 'locked.env').chmod, 0o644)
        before = prose.ignored(cwd=str(bench.where))
        self.assertTrue(before['locked.env'].startswith('unreadable:'))
        self.assertEqual(prose.offences(cwd=str(bench.where), ignored_before=before), [])

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


class EnvelopeShapeTests(unittest.TestCase):
    """Edits the envelope admitted while they changed what a file says or does."""

    def test_lines_joined_to_fit_a_new_sentence_are_growth(self):
        """Markdown prose was counted in lines, so joining two made room for a sentence that
        passed as no growth. A reworded sentence keeps its count."""
        notes = '# Notes\n\nThe limit is ten.\nIt holds for every caller.\n'
        bench = Bench(self, {'NOTES.md': notes})
        bench.write(notes.replace('The limit is ten.\n', 'The limit is ten. It is checked twice. '), name='NOTES.md')
        self.assertIn('NOTES.md: prose gained a sentence', ' | '.join(bench.offences()))
        bench.write(notes.replace('The limit is ten.', 'The limit is ten, set per caller.'), name='NOTES.md')
        self.assertEqual(bench.offences(), [])

    def test_a_type_comment_is_what_a_type_checker_reads(self):
        """`# type: List[int]` is the annotation a type checker reads, and the tree compared
        without type comments called a changed one prose. A line of prose that begins `# type:`
        on its own is still prose."""
        start = 'from typing import List\nx = []  # type: List[int]\n# type: the kind of cache this holds\ny = 1\n'
        bench = Bench(self, {'thing.py': start})
        bench.write(start.replace('List[int]', 'List[str]'))
        self.assertIn('behaviour changed, not prose', ' | '.join(bench.offences()))
        bench.write(start.replace('the kind of cache this holds', 'what the cache keeps'))
        self.assertEqual(bench.offences(), [])

    def test_a_block_moved_past_its_paragraph_is_not_prose(self):
        """Every code line kept, a fenced block moved ahead of the paragraph it depends on read as
        no change. Cutting the paragraph between two blocks is still a cut."""
        doc = '# Run\n\nFirst export the token.\n\n```sh\nexport T=1\n```\n\nThen push.\n\n```sh\ngit push\n```\n'
        bench = Bench(self, {'RUN.md': doc})
        moved = doc.replace('First export the token.\n\n```sh\nexport T=1\n```\n',
                            '```sh\nexport T=1\n```\n\nFirst export the token.\n')
        bench.write(moved, name='RUN.md')
        self.assertIn('RUN.md: its frontmatter or a fenced block changed, or moved', ' | '.join(bench.offences()))
        bench.write(doc.replace('Then push.\n\n', ''), name='RUN.md')
        self.assertEqual(bench.offences(), [])

    def test_a_source_in_its_declared_encoding_is_read(self):
        """A Latin-1 source read by the locale raised out of the envelope instead of answering."""
        start = b'# -*- coding: latin-1 -*-\n# caf\xe9 counts the visits\nvisits = 0\n'
        bench = Bench(self, {})
        (bench.where / 'legacy.py').write_bytes(start)
        subprocess.run(['git', '-C', str(bench.where), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(bench.where), '-c', 'user.email=a@b.invalid', '-c', 'user.name=A',
                        'commit', '-q', '-m', 'legacy'], check=True)
        (bench.where / 'legacy.py').write_bytes(start.replace(b'counts the visits', b'counts visits'))
        self.assertEqual(bench.offences(), [])

    def test_a_staged_change_the_tree_reverted_is_not_a_clean_head(self):
        """The envelope's listing compares the tree with HEAD through an index of its own, so a
        change staged and then reverted in the tree read as clean, and the next commit took it."""
        import review_git
        bench = Bench(self)
        bench.write(START + 'EXTRA = 1\n')
        subprocess.run(['git', '-C', str(bench.where), 'add', 'thing.py'], check=True)
        bench.write(START)
        here = os.getcwd()
        os.chdir(bench.where)
        self.addCleanup(os.chdir, here)
        with self.assertRaisesRegex(ValueError, 'the index differs from HEAD'):
            review_git.clean_head()

    def test_a_blank_line_after_a_quote_its_fence_ended_is_code(self):
        """A quote's unclosed fence ends at a line the quote does not hold, and an indented line
        there is code of its own. Read as the fence's line, the blank run after it was prose."""
        doc = '# Run\n\n> ```sh\n> ls\n    one\n\n    two\n'
        bench = Bench(self, {'E.md': doc})
        bench.write(doc.replace('    one\n\n', '    one\n\n\n'), name='E.md')
        self.assertIn('E.md: its frontmatter or a fenced block changed', ' | '.join(bench.offences()))


if __name__ == '__main__':
    unittest.main()
