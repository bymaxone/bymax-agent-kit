"""The removal-note reader: which lines naming a removed name only record that it is gone, read
against a table where each guard of the grammar decides at least one line."""
from pathlib import Path
import sys
import unittest

# The fixture tree is test_review_claims's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_claims import Tree, claims


class RemovalNoteTests(unittest.TestCase):
    """A line recording a removal asserts nothing live; every other line naming the name does."""

    RECORDS = ('`OLD_HELPER` was removed; use `NEW_HELPER`.', 'Deleted `OLD_HELPER` in 2.0.',
               'OLD_HELPER is gone — read NEW_HELPER.', '`OLD_HELPER` has been dropped.',
               'Removed: `OLD_HELPER`.', '`OLD_HELPER` and `OTHER_HELPER` were removed.',
               '`OTHER_HELPER`, `OLD_HELPER` were deleted.',
               'We removed `OLD_HELPER` in favour of `NEW_HELPER`.',
               'Deleted `OTHER_HELPER` and `OLD_HELPER`.', '`OLD_HELPER` was removed; do not use it.',
               'The `OLD_HELPER` helper was removed.', '`OLD_HELPER` has now been removed.',
               '`OLD_HELPER` was later deleted.', '`OLD_HELPER` is no longer exported.',
               '`OLD_HELPER`, `A_HELPER` and `B_HELPER` were removed.', 'Removed the `OLD_HELPER` helper.',
               '`OLD_HELPER` got removed in 2.0.', 'OLD_HELPER is now gone.',
               'OLD_HELPER and OTHER_HELPER were removed.', 'The `OLD_HELPER` function was removed.',
               '`OLD_HELPER` removed in 2.0.', '**Removed** `OLD_HELPER`.',
               'Removed `A_HELPER`, `OLD_HELPER` and `B_HELPER`.',
               'Removed `A_HELPER`, `OLD_HELPER` in 2.0.', '`OLD_HELPER` removed.',
               '`OLD_HELPER` removed, see `NEW_HELPER`.', '`OLD_HELPER` and `A_HELPER` removed in 2.0.',
               'The `OLD_HELPER` helper removed in 2.0.')
    LIVE = ('Set `OLD_HELPER` first. The old cache was removed.',
            '`OLD_HELPER` runs `git worktree remove`.', '`OLD_HELPER` is not removed.',
            '`OLD_HELPER` was never deleted.',
            '`OLD_HELPER` remains required, but `NEW_HELPER` was removed.',
            'OLD_HELPER remains required but NEW_HELPER was removed.', '`OLD_HELPER` removes the entry.',
            '`OLD_HELPER` no longer retries.', 'Call `OLD_HELPER` to delete the cache.',
            '# OLD_HELPER deletes the lock file', '`OLD_HELPER` removed the stale entries.',
            '`OLD_HELPER` drops the table.', 'Removed the cache, then call `OLD_HELPER`.',
            'Removes `OLD_HELPER` entries from the cache.', 'Run `OLD_HELPER --deleted` to list them.',
            'We have not removed `OLD_HELPER`.', '`OLD_HELPER` stays and `NEW_HELPER` was removed.',
            '`OLD_HELPER` fails when `NEW_HELPER` is gone.',
            '`OLD_HELPER` is required and `NEW_HELPER` was removed.',
            '`OLD_HELPER` keeps the cache it was given until removed.',
            'This function no longer calls `OLD_HELPER`.',
            '`OLD_HELPER` works if `NEW_HELPER` was deleted.',
            '`NEW_HELPER` was removed, `OLD_HELPER` is still required.',
            'Removed `NEW_HELPER`, `OLD_HELPER` stays.',
            '`OLD_HELPER` was removed. Call `OLD_HELPER` first.',
            'Removed `NEW_HELPER`, `OLD_HELPER` works as before.',
            '`OLD_HELPER` was removed, then `OLD_HELPER` came back.',
            '`OLD_HELPER` will be removed in 3.0.')

    def test_a_line_recording_the_removal_asserts_nothing_live(self):
        """A migration note is true of the tree it sits in, and only a note is: a form reporting
        a removal, of this name, with the text around it read by the grammar noted() names.
        A behaviour ("removes"), another name's removal, another sentence's, a quoted command
        and a negation are live claims."""
        for line in self.RECORDS:
            with self.subTest(line):
                self.assertTrue(claims.records_removal(line, 'OLD_HELPER'))
        for line in self.LIVE:
            with self.subTest(line):
                self.assertFalse(claims.records_removal(line, 'OLD_HELPER'))
        # And through the search over the tree, one of each.
        for note, found in ((self.RECORDS[0], []), (self.LIVE[4], [('README.md', 'OLD_HELPER')])):
            with self.subTest(note):
                tree = Tree(self, {'a.py': 'OLD_HELPER = 1\n'}, {'a.py': '', 'README.md': note + '\n'})
                self.assertEqual(tree.retired(), found)


if __name__ == '__main__':
    unittest.main()
