"""The claims checker, against trees built to make each check the only thing standing.

Every case here is a synthetic repository rather than this one's history: the deltas that
motivated the checker were squash-merged, so their commits are unreachable objects and a test
anchored to them would pass today and vanish at the next gc. What the history proved is
recorded in the module's docstring; what keeps it working is here.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
import review_claims as claims                                     # noqa: E402


def run(where, *args):
    subprocess.run(['git', '-C', str(where), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Tree:
    """A two-commit repository: whatever `before` says, then whatever `after` says."""

    def __init__(self, case, before, after):
        self.where = Path(tempfile.mkdtemp())
        case.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.where)]))
        run(self.where, 'init', '-q')
        run(self.where, 'config', 'user.email', 'case@example.invalid')
        run(self.where, 'config', 'user.name', 'Case')
        self.base = self.commit(before)
        self.head = self.commit(after)

    def commit(self, files):
        for name, text in files.items():
            path = self.where / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        run(self.where, 'add', '-A')
        run(self.where, 'commit', '-q', '-m', 'x', '--allow-empty')
        return subprocess.run(['git', '-C', str(self.where), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip()

    def retired(self):
        return claims.retired(self.base, self.head, cwd=str(self.where))

    def unkept(self):
        return claims.unkept(self.base, self.head, cwd=str(self.where))


class RetiredNameTests(unittest.TestCase):

    def test_a_comment_naming_a_constant_this_delta_deleted_is_reported(self):
        """The case the module exists for, and the one an added-lines-only version missed.

        The sentence is not new — it is older than the delta and survived it. What changed is
        the code underneath it. A checker that reads only what the delta added reports nothing
        here, which is how the first version of this function passed against the real history
        it was written from.
        """
        tree = Tree(self, {'a.py': 'FOREIGN = (1,)\n\n# reads FOREIGN, not the tuple\nX = 1\n'},
                    {'a.py': '# reads FOREIGN, not the tuple\nX = 1\n'})
        self.assertEqual(tree.retired(), [('a.py', 'FOREIGN')])

    def test_a_name_that_still_exists_somewhere_else_is_not_reported(self):
        """Moved is not deleted. The check is about a name nothing defines any more, so a
        constant that migrated to another module is silence, not a finding."""
        tree = Tree(self, {'a.py': 'FOREIGN = (1,)\n# reads FOREIGN\n', 'b.py': 'Y = 2\n'},
                    {'a.py': '# reads FOREIGN\n', 'b.py': 'FOREIGN = (1,)\nY = 2\n'})
        self.assertEqual(tree.retired(), [])

    def test_a_function_that_moved_to_another_module_is_not_reported(self):
        """The existing moved-name case uses a CONSTANT, which resolves through the second
        half of the alive pattern. The def/class half carried a \\b that git grep reads
        literally, so every moved function read as removed and the gate refused a correct
        refactor. One case per alternative, or one of them is never exercised."""
        tree = Tree(self, {'a.py': 'def helper_one(x):\n    return x\n# calls helper_one\n',
                           'b.py': 'Y = 2\n'},
                    {'a.py': '# calls helper_one\n',
                     'b.py': 'def helper_one(x):\n    return x\nY = 2\n'})
        self.assertEqual(tree.retired(), [])

    def test_a_function_removed_outright_is_still_reported(self):
        """The other side of the same alternative: moved is silence, gone is a finding."""
        tree = Tree(self, {'a.py': 'def helper_one(x):\n    return x\n# calls helper_one\n'},
                    {'a.py': '# calls helper_one\n'})
        self.assertEqual(tree.retired(), [('a.py', 'helper_one')])

    def test_an_ordinary_english_word_is_not_read_as_a_reference(self):
        """Measured on this delivery's own candidate: deleting a module orphaned its
        `prepare()` and five files were accused for containing the English word — a README, a
        command, an example. The gate refused the candidate that added it. A name is a
        reference when it is spelled like code, not when it is spelled like a word."""
        tree = Tree(self, {'a.py': 'def prepare(x):\n    return x\n',
                           'README.md': 'Run this to prepare the commit message.\n'},
                    {'a.py': 'X = 1\n', 'README.md': 'Run this to prepare the commit message.\n'})
        self.assertEqual(tree.retired(), [])

    def test_a_deleted_name_nobody_mentions_is_not_reported(self):
        """Deleting a constant and its every mention is the correct edit, and correct edits
        must be silent or the check trains its reader to skip it."""
        tree = Tree(self, {'a.py': 'FOREIGN = (1,)\n# reads FOREIGN\nX = 1\n'},
                    {'a.py': 'X = 1\n'})
        self.assertEqual(tree.retired(), [])

    def test_a_deleted_name_left_in_markdown_is_reported(self):
        """Documentation is where this defect was measured at scale, so a .md mention counts
        exactly as a comment does."""
        tree = Tree(self, {'a.py': 'FOREIGN = (1,)\n', 'README.md': 'We keep FOREIGN here.\n'},
                    {'a.py': 'X = 1\n', 'README.md': 'We keep FOREIGN here.\n'})
        self.assertEqual(tree.retired(), [('README.md', 'FOREIGN')])

    def test_a_mention_only_inside_a_fenced_block_is_not_reported(self):
        """A fenced block is an example about somebody else's repository. Asserting nothing,
        it cannot assert something false — measured as a false positive before this exclusion
        existed, on this repository's own documentation."""
        tree = Tree(self, {'a.py': 'FOREIGN = (1,)\n',
                           'README.md': 'Example:\n\n```py\nFOREIGN = (1,)\n```\n'},
                    {'a.py': 'X = 1\n',
                     'README.md': 'Example:\n\n```py\nFOREIGN = (1,)\n```\n'})
        self.assertEqual(tree.retired(), [])


class GeneratedCopyTests(unittest.TestCase):
    """The Codex mirror is a copy of the plugin sources, so every sentence in it exists twice.

    Measured on the delta that added this module: reading the mirror produced four removal
    claims, each a file flagging its own copy, and doubled every other count. A generated copy
    asserts nothing of its own.
    """

    MIRROR = 'codex/plugins/bymax-codex/references/upstream/thing.py'

    def test_a_dangling_name_in_the_mirror_alone_is_not_reported(self):
        tree = Tree(self, {'a.py': 'FOREIGN = (1,)\n', self.MIRROR: '# reads FOREIGN\n'},
                    {'a.py': 'X = 1\n', self.MIRROR: '# reads FOREIGN\n'})
        self.assertEqual(tree.retired(), [])

    def test_a_dangling_name_the_source_asserts_is_still_reported(self):
        """The exclusion must remove the copy, not the subject: the authored file still
        answers for its own sentence."""
        tree = Tree(self, {'a.py': 'FOREIGN = (1,)\n# reads FOREIGN\n',
                           self.MIRROR: '# reads FOREIGN\n'},
                    {'a.py': '# reads FOREIGN\n', self.MIRROR: '# reads FOREIGN\n'})
        self.assertEqual(tree.retired(), [('a.py', 'FOREIGN')])

    def test_a_removal_claim_answered_only_by_the_mirror_is_not_reported(self):
        """The phrase surviving in a generated copy is the copy being stale, not a promise
        broken — regenerating the mirror is what answers it, and the commit that does so is
        the one that would be blamed here."""
        tree = Tree(self, {'a.py': 'X = 1  # most likely never joined\n',
                           self.MIRROR: 'X = 1  # most likely never joined\n'},
                    {'a.py': 'X = 1\n',
                     self.MIRROR: 'X = 1  # most likely never joined\n',
                     'NOTES.md': 'We removed `most likely never joined` from it.\n'})
        self.assertEqual(tree.unkept(), [])


    def test_a_claim_the_mirror_repeats_is_reported_once(self):
        """The mirror copies the source, so a sentence written in a plugin file is also a
        sentence in its copy. Counting the copy reports the same claim twice and names the
        generated file as an author — found by a surviving mutant, not by reading: removing
        this filter changed no other case.
        """
        tree = Tree(self, {'a.py': 'X = 1  # most likely never joined\n'},
                    {'a.py': 'X = 1  # most likely never joined\n',
                     'NOTES.md': 'We removed `most likely never joined` from it.\n',
                     self.MIRROR.replace('thing.py', 'NOTES.md'):
                         'We removed `most likely never joined` from it.\n'})
        self.assertEqual([name for name, _, _ in tree.unkept()], ['NOTES.md'])


class WorkingDirectoryTests(unittest.TestCase):
    """The answer must not depend on where the process was started.

    Every pathspec and every file read resolved against the caller's cwd, so running from a
    subdirectory answered about a subtree — measured on this repository's own history, the
    checker reported nothing from `scripts/` for a delta it refuses from the top. Silence
    read as cleanliness.
    """

    def test_the_same_delta_answers_the_same_from_a_subdirectory(self):
        tree = Tree(self, {'a.py': 'FOREIGN = (1,)\n', 'sub/b.py': '# reads FOREIGN\n'},
                    {'a.py': 'X = 1\n', 'sub/b.py': '# reads FOREIGN\n'})
        from_top = claims.retired(tree.base, tree.head, cwd=str(tree.where))
        from_sub = claims.retired(tree.base, tree.head, cwd=str(tree.where / 'sub'))
        self.assertEqual(from_top, [('sub/b.py', 'FOREIGN')])
        self.assertEqual(from_sub, from_top)


class OpaqueFileTests(unittest.TestCase):
    """What this module cannot read has to be said, not skipped.

    Only Python and Markdown are classified. On a TypeScript, Rust or shell repository every
    changed file is unreadable here, and a checker that stays silent about them reports a real
    code delta as changing no code.
    """

    def opaque(self, tree):
        return claims.opaque(tree.base, tree.head, cwd=str(tree.where))

    def test_a_changed_file_of_another_language_is_named(self):
        tree = Tree(self, {'a.ts': 'const x = 1\n'}, {'a.ts': 'const x = 2\n'})
        self.assertEqual(self.opaque(tree), ['a.ts'])

    def test_a_readable_file_is_not_named(self):
        tree = Tree(self, {'a.py': 'X = 1\n'}, {'a.py': 'X = 2\n'})
        self.assertEqual(self.opaque(tree), [])

    def test_the_generated_mirror_is_not_named_either(self):
        """A generated copy is not a file whose claims nobody read; it is a copy."""
        mirror = 'codex/plugins/bymax-codex/references/upstream/vendored.ts'
        tree = Tree(self, {mirror: 'const x = 1\n'}, {mirror: 'const x = 2\n'})
        self.assertEqual(self.opaque(tree), [])

    def test_a_deleted_line_is_counted_on_the_side_it_left(self):
        """Counting only additions told both reviewers that a correction which removed four
        lines of live code had changed no code at all, and made the prose:code ratio in their
        brief wrong for the same reason."""
        tree = Tree(self, {'a.py': '# a reason worth keeping\nX = 1\nY = 2\n'},
                    {'a.py': '# a reason worth keeping\nX = 1\n'})
        split = claims.split_delta(tree.base, tree.head, cwd=str(tree.where))
        self.assertEqual([row[2] for row in split['code']], ['Y = 2'])
        self.assertEqual(split['prose'], [])

    def test_a_deleted_comment_is_counted_as_prose_not_code(self):
        """The other side of the same walk: a removed comment is a removed line of prose."""
        tree = Tree(self, {'a.py': '# a reason worth keeping\nX = 1\n'},
                    {'a.py': 'X = 1\n'})
        split = claims.split_delta(tree.base, tree.head, cwd=str(tree.where))
        self.assertEqual([row[2] for row in split['prose']], ['# a reason worth keeping'])
        self.assertEqual(split['code'], [])

    def test_an_unreadable_file_removal_is_counted_as_a_removal(self):
        """Taking the line number from the + side for both signs printed deleted TypeScript
        as an addition, which made the brief's own +/- header false for every file the
        module cannot read."""
        tree = Tree(self, {'a.ts': 'const x = 1\nconst y = 1\n'}, {'a.ts': 'const x = 1\n'})
        split = claims.split_delta(tree.base, tree.head, cwd=str(tree.where))
        self.assertTrue(all(at < 0 for _, at, _ in split['code']), split['code'])

    def test_a_change_with_no_text_diff_is_still_a_change(self):
        """A binary file, a mode change or a pure rename produces no diff rows, and counting
        zero of them announced "this delta changed no code" about a delta that changed two
        files."""
        tree = Tree(self, {'bin.dat': 'x'}, {'bin.dat': 'x'})
        import subprocess as sp
        sp.run(['chmod', '+x', str(tree.where / 'bin.dat')], check=True)
        sp.run(['git', '-C', str(tree.where), 'add', '-A'], check=True)
        sp.run(['git', '-C', str(tree.where), '-c', 'user.email=a@b.invalid',
                '-c', 'user.name=A', 'commit', '-q', '-m', 'mode'], check=True)
        head = sp.run(['git', '-C', str(tree.where), 'rev-parse', 'HEAD'],
                      capture_output=True, text=True).stdout.strip()
        split = claims.split_delta(tree.head, head, cwd=str(tree.where))
        self.assertEqual([n for n, _, _ in split['code']], ['bin.dat'])

    def test_what_cannot_be_read_counts_as_code_rather_than_prose(self):
        """Unknown is not prose. Counting it as prose told both reviewers that a delta which
        changed only TypeScript had changed no code at all."""
        tree = Tree(self, {'a.ts': 'const x = 1\nconst y = 1\n'},
                    {'a.ts': 'const x = 2\nconst y = 2\n'})
        split = claims.split_delta(tree.base, tree.head, cwd=str(tree.where))
        # Counted by its real changed lines, not one row per file: announcing a 600-line
        # TypeScript delta as three lines of code is differently false, not true.
        self.assertEqual({n for n, _, _ in split['code']}, {'a.ts'})
        self.assertEqual(len(split['code']), 4)
        self.assertEqual(split['prose'], [])


class UnkeptPromiseTests(unittest.TestCase):

    def test_a_claimed_removal_whose_quote_survives_is_reported(self):
        """Measured on another repository on this loop: a triage disposition certifying a
        correction, written without opening the file, whose sentence was still in HEAD. A
        claim of removal is the one claim whose subject is quoted often enough to check."""
        tree = Tree(self, {'a.py': 'X = 1  # most likely never joined\n'},
                    {'a.py': 'X = 1  # most likely never joined\n',
                     'NOTES.md': 'We removed `most likely never joined` from the message.\n'})
        found = tree.unkept()
        self.assertEqual([(n, q) for n, q, _ in found],
                         [('NOTES.md', 'most likely never joined')])

    def test_a_claimed_removal_that_actually_happened_is_silent(self):
        tree = Tree(self, {'a.py': 'X = 1  # most likely never joined\n'},
                    {'a.py': 'X = 1\n',
                     'NOTES.md': 'We removed `most likely never joined` from the message.\n'})
        self.assertEqual(tree.unkept(), [])

    def test_a_removal_word_inside_another_quote_is_not_a_promise(self):
        """Measured against this repository's mainline: a release note reading "run `claude
        plugin marketplace remove X`, then …" turned every other backticked phrase on the
        line into a claimed removal. The verb has to be in prose — outside the subject and
        outside every other quoted span — or a command that merely contains the word refuses
        a legitimate candidate. Three of the last eight mainline commits were refused this
        way before the rule said "in prose"."""
        tree = Tree(self, {'a.py': 'X = 1  # most likely never joined\n'},
                    {'a.py': 'X = 1  # most likely never joined\n',
                     'NOTES.md': 'Run `git worktree remove old` before `most likely never '
                                 'joined` can be read.\n'})
        self.assertEqual(tree.unkept(), [])

    def test_a_removal_claimed_after_its_subject_is_a_stated_gap(self):
        """The verb-last form is NOT read, and that is a decision rather than an oversight.

        A triage disposition of mine said a case pinned this form. None did, and writing one
        forced the rule to read past the subject — which refused five of the last forty
        mainline commits, every one a shell command named beside the word. In a gate a wrong
        refusal costs a delivery and a missed claim costs a sentence, so the gap is kept and
        written down here, where the next person to widen the rule will measure first.
        """
        tree = Tree(self, {'a.py': 'X = 1  # most likely never joined\n'},
                    {'a.py': 'X = 1  # most likely never joined\n',
                     'NOTES.md': 'The `most likely never joined` wording was removed.\n'})
        self.assertEqual(tree.unkept(), [])

    def test_a_command_named_before_a_removal_word_is_not_a_promise(self):
        """Measured over the last 40 mainline commits: reading the verb anywhere on the line
        refuses 8 of them and allowing it just after the subject refuses 5, every one a
        backticked shell command named in a sentence that happens to contain the word. The
        run-up alone refuses 1, which is why this check reports and never blocks."""
        tree = Tree(self, {'a.py': 'X = 1  # ack --pager\n'},
                    {'a.py': 'X = 1  # ack --pager\n',
                     'NOTES.md': 'The allowlist that `ack --pager` defeated is gone now.\n'})
        self.assertEqual(tree.unkept(), [])

    def test_a_denied_removal_is_not_a_promise(self):
        """Found by Codex, the first round of this campaign it was able to run.

        "We did not remove `X`" is the opposite of a claim, and reading it as one refuses a
        sentence written precisely to say the work was NOT done. Only the clause carrying the
        verb is read: a negation in an earlier clause is about something else.
        """
        survives = {'a.py': 'X = 1  # most likely never joined\n'}
        for denial in ('We did not remove `most likely never joined` from it.',
                       'We never removed `most likely never joined` from it.',
                       'Rather than remove `most likely never joined`, we kept it.'):
            tree = Tree(self, survives, dict(survives, **{'NOTES.md': denial + '\n'}))
            self.assertEqual(tree.unkept(), [], denial)

    def test_a_removal_asserted_in_a_later_clause_is_still_a_promise(self):
        """The negation rule reads one clause, not the whole run-up: a comma earlier in the
        sentence must not buy an exemption."""
        tree = Tree(self, {'a.py': 'X = 1  # most likely never joined\n'},
                    {'a.py': 'X = 1  # most likely never joined\n',
                     'NOTES.md': 'The list moved, and we removed `most likely never joined` '
                                 'with it.\n'})
        self.assertEqual([n for n, _, _ in tree.unkept()], ['NOTES.md'])

    def test_a_single_word_quote_is_not_treated_as_a_promise(self):
        """`FOREIGN` in a sentence about removing FOREIGN legitimately outlives the removal —
        that is what the sentence is about. Only a phrase is specific enough to check, and
        treating every quoted identifier as a broken promise would make this unusable."""
        tree = Tree(self, {'a.py': 'FOREIGN = 1\n'},
                    {'a.py': 'FOREIGN = 1\n', 'NOTES.md': 'We removed `FOREIGN` today.\n'})
        self.assertEqual(tree.unkept(), [])


class ProseExtractionTests(unittest.TestCase):

    def test_python_prose_is_comments_and_docstrings_and_not_data(self):
        text = 'NAME = "value"\n# a comment about NAME\ndef f():\n    """A docstring."""\n'
        got = claims.prose('x.py', text)
        self.assertIn('a comment about NAME', got)
        self.assertIn('A docstring.', got)
        self.assertNotIn('def f()', got)
        # A string literal is data the author passes to something, not an assertion. Counting
        # it read test fixtures as claims.
        self.assertNotIn('"value"', got)

    def test_markdown_prose_drops_fenced_blocks(self):
        got = claims.prose('x.md', 'Words about it.\n\n```\nCODE_HERE = 1\n```\n')
        self.assertIn('Words about it.', got)
        self.assertNotIn('CODE_HERE', got)

    def test_a_file_that_does_not_parse_answers_empty_rather_than_raising(self):
        """A half-written file is a state this runs in, and a checker that crashes on it
        becomes a checker people disable."""
        self.assertEqual(claims.prose('x.py', 'def (\n'), '')

    def test_a_suffix_it_does_not_read_answers_empty(self):
        self.assertEqual(claims.prose('x.json', '{"NAME": 1}'), '')


class ExitStatusTests(unittest.TestCase):

    def test_only_the_exact_tier_decides_the_exit_status(self):
        """A name nothing defines is a fact, and facts decide the exit status."""
        dangling = Tree(self, {'a.py': 'FOREIGN = (1,)\n# reads FOREIGN\nX = 1\n'},
                        {'a.py': '# reads FOREIGN\nX = 1\n'})
        self.assertEqual(claims.report(dangling.base, dangling.head, cwd=str(dangling.where)), 1)


if __name__ == '__main__':
    unittest.main()
