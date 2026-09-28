"""Lines naming a name the delta removed: which refuse the candidate, and which are reported for
a reviewer to judge because every clause naming the name also says it is gone."""
from pathlib import Path
import sys
import unittest

# The fixture tree is test_review_claims's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_claims import Tree, claims


class RemovalNoteTests(unittest.TestCase):
    """A line whose every clause naming the name says it is gone is reported, not refused."""

    # Notes, and live claims that hold the word: no reading of the sentence tells them apart for
    # every sentence, so each is a reviewer's to judge.
    REPORTED = ('`OLD_HELPER` was removed; use `NEW_HELPER`.', 'Deleted `OLD_HELPER` in 2.0.',
                'OLD_HELPER is gone — read NEW_HELPER.', 'Removed `A_HELPER`, `B_HELPER`, and `OLD_HELPER`.',
                '`OLD_HELPER` is no longer exported.', '**Removed** `OLD_HELPER`.',
                '`OLD_HELPER` removes the entry.', 'Removed `NEW_HELPER` and `OLD_HELPER` stays.',
                "We haven't removed `OLD_HELPER` yet.", '`OLD_HELPER` was removed; call `NEW_HELPER` first.',
                'Deleted `review_flow.py` and `OLD_HELPER`.', '`OLD_HELPER` was renamed to `NEW_HELPER`.',
                'Rename `OLD_HELPER` to `NEW_HELPER`.', 'Replaced `OLD_HELPER` with `NEW_HELPER`.',
                '`NEW_HELPER` supersedes `OLD_HELPER`.', '`OLD_HELPER` moved to `review_git.py`.',
                '`OLD_HELPER` is now `NEW_HELPER`.', '`OLD_HELPER` — removed in 2.0.',
                '`OLD_HELPER` was moved to `review_git.py`.',
                # A target a reader cannot mistake for anything but a name or a file, quoted or not.
                '`OLD_HELPER` is now called `NEW_HELPER`.', '`OLD_HELPER` is now named NEW_HELPER.',
                '`OLD_HELPER` moved to review_git.py.', '`OLD_HELPER` was moved to scripts/review_git.py.')
    # A clause naming the name with no removal word outside a quoted span asserts it.
    REFUSED = ('Call `OLD_HELPER` first.', 'Set `OLD_HELPER` first. The old cache was removed.',
               '`OLD_HELPER` runs `git worktree remove`.', 'Run `OLD_HELPER --deleted` to list them.',
               '`OLD_HELPER` was removed. Call `OLD_HELPER` first.',
               '`OLD_HELPER` was removed — call `OLD_HELPER` instead.',
               '`OLD_HELPER` was removed; call `OLD_HELPER` first.', '`OLD_HELPER` — call it first.',
               '`OLD_HELPER` — removed; `OLD_HELPER` — call it.',
               # A move or a new state is a note only with a target: these describe the name as live.
               '`OLD_HELPER` is now enabled by default.', '`OLD_HELPER` moved to the top of the list.',
               # The move or the new state has to be the name's own: another name's does not retire it.
               '`OLD_HELPER` remains enabled because `CACHE_MODE` is now `NEW_MODE`.',
               '`OLD_HELPER` reads `x.py` since `CACHE` moved to `y.py`.',
               # Unquoted, the target has to be spelled like code or like a file to be one.
               '`OLD_HELPER` is now called twice.', '`OLD_HELPER` is now called by the loader.',
               '`OLD_HELPER` moved to e.g. the top.')

    def test_a_line_saying_the_name_is_gone_is_reported_not_refused(self):
        """Every clause naming the name must say it is gone, outside every quoted span, for the
        line to be reported; one clause that does not makes it a live claim that refuses."""
        for line in self.REPORTED:
            with self.subTest(line):
                self.assertTrue(claims.records_removal(line, 'OLD_HELPER'))
        for line in self.REFUSED:
            with self.subTest(line):
                self.assertFalse(claims.records_removal(line, 'OLD_HELPER'))
        # A replacement is a note, not a claim of removal: its new name is still in the tree by design.
        self.assertFalse(claims.claimed('Replaced the loader with `NEW_HELPER`.', 'NEW_HELPER'))
        # And through the search over the tree: one refuses, the other is reported.
        tree = Tree(self, {'a.py': 'OLD_HELPER = 1\n'},
                    {'a.py': '', 'README.md': self.REPORTED[0] + '\n', 'USAGE.md': self.REFUSED[0] + '\n'})
        self.assertEqual(tree.retired(), [('USAGE.md', 'OLD_HELPER')])
        self.assertEqual(claims.noted_removals(tree.base, tree.head, cwd=str(tree.where)),
                         [('README.md', 'OLD_HELPER', self.REPORTED[0])])

    def test_the_command_line_prints_what_it_reports(self):
        """noted_removals() had no line in the command's output, so a reader of the report never
        saw the notes it existed to hand them."""
        import contextlib
        import io
        tree = Tree(self, {'a.py': 'OLD_HELPER = 1\n'}, {'a.py': '', 'README.md': self.REPORTED[0] + '\n'})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            claims.report(tree.base, tree.head, cwd=str(tree.where))
        self.assertIn('NOTED    README.md says OLD_HELPER is gone', out.getvalue())

    def test_a_markdown_suffix_is_read_in_any_case(self):
        """README.MD is live documentation. Matched by case, it was neither read as prose nor
        searched, and a removed name it still asserted refused nothing."""
        tree = Tree(self, {'a.py': 'OLD_HELPER = 1\n'},
                    {'a.py': '', 'README.MD': 'Call `OLD_HELPER` first.\n'})
        self.assertEqual(tree.retired(), [('README.MD', 'OLD_HELPER')])


if __name__ == '__main__':
    unittest.main()
