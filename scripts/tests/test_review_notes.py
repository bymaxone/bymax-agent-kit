"""Lines naming a name the delta removed: which refuse the candidate, and which are reported for
a reviewer to judge because every clause naming the name also says it is gone."""
from pathlib import Path
import sys
import unittest

# The fixture tree is test_review_claims's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_claims import Tree, claims


class RemovalNoteTests(unittest.TestCase):
    """A line saying the name is gone is reported, never refused and never passed in silence."""

    # Notes, and live claims that hold the word: no reading of the sentence tells them apart for
    # every sentence, so each is a reviewer's to judge.
    REPORTED = ('`OLD_HELPER` was removed; use `NEW_HELPER`.', 'Deleted `OLD_HELPER` in 2.0.',
                'OLD_HELPER is gone — read NEW_HELPER.', 'Removed `A_HELPER`, `B_HELPER`, and `OLD_HELPER`.',
                '`OLD_HELPER` is no longer exported.', '**Removed** `OLD_HELPER`.',
                '`OLD_HELPER` removes the entry.', 'Removed `NEW_HELPER` and `OLD_HELPER` stays.',
                "We haven't removed `OLD_HELPER` yet.", '`OLD_HELPER` was removed; call `NEW_HELPER` first.',
                'Deleted `review_flow.py` and `OLD_HELPER`.')
    # A clause naming the name with no removal word outside a quoted span asserts it.
    REFUSED = ('Call `OLD_HELPER` first.', 'Set `OLD_HELPER` first. The old cache was removed.',
               '`OLD_HELPER` runs `git worktree remove`.', 'Run `OLD_HELPER --deleted` to list them.',
               '`OLD_HELPER` was removed. Call `OLD_HELPER` first.',
               '`OLD_HELPER` was removed — call `OLD_HELPER` instead.',
               '`OLD_HELPER` was removed; call `OLD_HELPER` first.')

    def test_a_line_saying_the_name_is_gone_is_reported_not_refused(self):
        """Every clause naming the name must say it is gone, outside every quoted span, for the
        line to be reported; one clause that does not makes it a live claim that refuses."""
        for line in self.REPORTED:
            with self.subTest(line):
                self.assertTrue(claims.records_removal(line, 'OLD_HELPER'))
        for line in self.REFUSED:
            with self.subTest(line):
                self.assertFalse(claims.records_removal(line, 'OLD_HELPER'))
        # And through the search over the tree: one refuses, the other is reported.
        tree = Tree(self, {'a.py': 'OLD_HELPER = 1\n'},
                    {'a.py': '', 'README.md': self.REPORTED[0] + '\n', 'USAGE.md': self.REFUSED[0] + '\n'})
        self.assertEqual(tree.retired(), [('USAGE.md', 'OLD_HELPER')])
        self.assertEqual(claims.noted_removals(tree.base, tree.head, cwd=str(tree.where)),
                         [('README.md', 'OLD_HELPER', self.REPORTED[0])])


if __name__ == '__main__':
    unittest.main()
