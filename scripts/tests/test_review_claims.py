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

    def test_a_single_word_quote_is_not_treated_as_a_promise(self):
        """`FOREIGN` in a sentence about removing FOREIGN legitimately outlives the removal —
        that is what the sentence is about. Only a phrase is specific enough to check, and
        treating every quoted identifier as a broken promise would make this unusable."""
        tree = Tree(self, {'a.py': 'FOREIGN = 1\n'},
                    {'a.py': 'FOREIGN = 1\n', 'NOTES.md': 'We removed `FOREIGN` today.\n'})
        self.assertEqual(tree.unkept(), [])


class ProseExtractionTests(unittest.TestCase):

    def test_python_prose_is_comments_and_strings_and_not_code(self):
        text = 'NAME = "value"\n# a comment about NAME\ndef f():\n    """A docstring."""\n'
        got = claims.prose('x.py', text)
        self.assertIn('a comment about NAME', got)
        self.assertIn('A docstring.', got)
        self.assertNotIn('def f()', got)

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
