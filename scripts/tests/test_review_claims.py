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
import review_claims as claims


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
        self.head = self.commit(after, drop=[n for n in before if n not in after])

    def commit(self, files, drop=()):
        """Write these files and commit. `drop` removes one, because a name absent from the
        second mapping is not deleted by writing the first — which made a whole-file-deletion
        case pass over an empty list, vacuously, and let its mutant survive.
        """
        for name in drop:
            (self.where / name).unlink()
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

    def test_an_async_definition_is_a_definition(self):
        """Found by a reviewer: neither the definition read nor the alive grep knew `async def`,
        so a function made async read as removed and blocked a valid candidate. One case per
        read: moved and made async, the alive grep must find it; async in the base and removed,
        the definition read must have counted it. The conversion in place is the report's own."""
        tree = Tree(self, {'a.py': 'def fetch_data(x):\n    return x\n# calls fetch_data\n', 'b.py': 'Y = 2\n'},
                    {'a.py': '# calls fetch_data\n', 'b.py': 'async def fetch_data(x):\n    return x\nY = 2\n'})
        self.assertEqual(tree.retired(), [])
        tree = Tree(self, {'a.py': 'async def fetch_data(x):\n    return x\n# calls fetch_data\n'},
                    {'a.py': '# calls fetch_data\n'})
        self.assertEqual(tree.retired(), [('a.py', 'fetch_data')])
        tree = Tree(self, {'a.py': 'def fetch_data(x):\n    return x\n# calls fetch_data\n'},
                    {'a.py': 'async def fetch_data(x):\n    return x\n# calls fetch_data\n'})
        self.assertEqual(tree.retired(), [])

    def test_a_definition_removed_in_a_rename_is_still_reported(self):
        """Found by a reviewer: git reports a rename as its destination alone, so a definition
        removed in the same commit sat in a path the base does not have, nothing read it as
        removed, and the check reported that it had passed. Renames are not detected here."""
        whole = ('def old_helper(x):\n    return x\n\n\ndef kept_one(x):\n    return x + 1\n\n\n'
                 'def kept_two(x):\n    return x + 2\n\n\ndef kept_three(x):\n    return x + 3\n')
        tree = Tree(self, {'a.py': whole, 'README.md': '# doc\n\nCalls old_helper for the thing.\n'},
                    {'b.py': whole.split('\n\n\n', 1)[1], 'README.md': '# doc\n\nCalls old_helper for the thing.\n'})
        self.assertEqual(tree.retired(), [('README.md', 'old_helper')])

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

    def test_a_camel_case_class_is_a_reference(self):
        """Requiring CONSTANT_CASE or an underscore dropped every CamelCase class and every
        acronym-led one, so a dangling `Envelope` went unreported while `HARD_LIMIT` was
        caught. A capitalised name of four characters or more counts; the single-word
        lowercase function stays a stated gap, because deciding it needs the sentence."""
        tree = Tree(self, {'a.py': 'class Envelope:\n    pass\n# builds an Envelope\n'},
                    {'a.py': '# builds an Envelope\n'})
        self.assertEqual(tree.retired(), [('a.py', 'Envelope')])

    def test_the_removal_check_reports_and_never_refuses(self):
        """The tier demotion, asserted rather than described. Measured across the last 40
        mainline commits the removal check flags one — a backticked shell command read as the
        subject of a sentence beside it — and one wrong refusal in forty is a delivery blocked
        by mistake, so it is read and not obeyed."""
        tree = Tree(self, {'a.py': 'X = 1  # most likely never joined\n'},
                    {'a.py': 'X = 1  # most likely never joined\n',
                     'NOTES.md': 'We removed `most likely never joined` from it.\n'})
        self.assertTrue(tree.unkept())
        self.assertEqual(claims.report(tree.base, tree.head, cwd=str(tree.where)), 0)

    def test_an_affirmative_claim_after_a_dash_is_still_a_claim(self):
        """The em dash bounds a clause, which the disposition asserting it had only a console
        probe behind: reverting the boundary left four suites green. This repository's prose
        uses the dash as its dominant clause break, so without it the dominant form was read
        as a denial and silently ignored."""
        survives = {'a.py': 'X = 1  # most likely never joined\n'}
        tree = Tree(self, survives, dict(survives, **{
            'NOTES.md': 'This does not rename the helper — we removed `most likely never '
                        'joined` from it.\n'}))
        self.assertEqual([n for n, _, _ in tree.unkept()], ['NOTES.md'])

    def test_a_code_line_ending_in_a_comment_is_still_code(self):
        """The commonest edit there is. Marking the whole line prose because it ENDS in a
        comment filed a production change under prose, and the code view then told a reviewer
        the delta changed no code while a line of code had changed — the brief asserting what
        the tree does not support, which is the defect this whole delivery is about."""
        tree = Tree(self, {'a.py': 'enabled = check()\n'},
                    {'a.py': 'enabled = later()  # explanation\n'})
        split = claims.split_delta(tree.base, tree.head, cwd=str(tree.where))
        self.assertEqual(split['prose'], [])
        self.assertIn('enabled = later()  # explanation',
                      [text.strip() for _, at, text in split['code'] if at > 0])

    def test_a_change_with_no_lines_is_neither_added_nor_removed(self):
        """A file that changed while no line did gets coordinate 0, because naming a line
        would invent one; the brief marks it ? rather than calling it an addition."""
        tree = Tree(self, {'bin.dat': 'x'}, {'bin.dat': 'x'})
        import subprocess as sp
        sp.run(['chmod', '+x', str(tree.where / 'bin.dat')], check=True)
        sp.run(['git', '-C', str(tree.where), 'add', '-A'], check=True)
        sp.run(['git', '-C', str(tree.where), '-c', 'user.email=a@b.invalid',
                '-c', 'user.name=A', 'commit', '-q', '-m', 'mode'], check=True)
        head = sp.run(['git', '-C', str(tree.where), 'rev-parse', 'HEAD'],
                      capture_output=True, text=True).stdout.strip()
        split = claims.split_delta(tree.head, head, cwd=str(tree.where))
        self.assertEqual([(n, at) for n, at, _ in split['code']], [('bin.dat', 0)])

    def test_a_removed_line_is_numbered_where_it_was(self):
        """Found by the independent reviewer, not the author. Reading only the added coordinate numbered
        a removal by where it is NOT: a line deleted from old line 2 printed as `- a.ts:1`,
        because the new side had already moved on. A removal is located on the side that
        lost it."""
        tree = Tree(self, {'a.ts': 'const x = 1\nconst y = 2\nconst z = 3\n'},
                    {'a.ts': 'const x = 1\nconst z = 3\n'})
        split = claims.split_delta(tree.base, tree.head, cwd=str(tree.where))
        self.assertEqual([(n, at) for n, at, _ in split['code']], [('a.ts', -2)])

    def test_a_content_line_beginning_with_plus_signs_is_kept(self):
        """A prefix increment `++n` prints as `+++n` under git's default indicator, and the
        header test dropped it: the reviewer's delta lacked the one line that changed. Both
        walkers, both signs."""
        tree = Tree(self, {'a.ts': 'let n = 0\n', 'b.ts': 'let m = 0\n--m\n',
                           'c.py': 'count = 0\n', 'd.py': 'total = 0\n--total\n'},
                    {'a.ts': 'let n = 0\n++n\n', 'b.ts': 'let m = 0\n',
                     'c.py': 'count = 0\n++count\n', 'd.py': 'total = 0\n'})
        split = claims.split_delta(tree.base, tree.head, cwd=str(tree.where))
        self.assertIn(('a.ts', 2, '++n'), split['code'])
        self.assertIn(('b.ts', -2, '--m'), split['code'])
        self.assertIn(('c.py', 2, '++count'), split['code'])
        self.assertIn(('d.py', -2, '--total'), split['code'])

    def test_a_whole_file_deletion_is_marked_as_a_removal(self):
        """A file that disappears entirely still reports its lines as removals."""
        tree = Tree(self, {'a.ts': 'const x = 1\n', 'keep.py': 'X = 1\n'},
                    {'keep.py': 'X = 1\n'})
        split = claims.split_delta(tree.base, tree.head, cwd=str(tree.where))
        self.assertEqual([(n, at) for n, at, _ in split['code'] if n == 'a.ts'], [('a.ts', -1)])

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

    def test_a_renamed_file_this_module_cannot_read_is_named_on_both_sides(self):
        """A rename changed both paths, and naming one of them tells the reader that the other
        side stayed put — the same detection that hid a removed definition from the check."""
        whole = 'const a = 1\nconst b = 2\nconst c = 3\nconst d = 4\nconst e = 5\n'
        tree = Tree(self, {'a.ts': whole}, {'b.ts': whole + 'const f = 6\n'})
        self.assertEqual(self.opaque(tree), ['a.ts', 'b.ts'])

    def test_a_readable_file_is_not_named(self):
        tree = Tree(self, {'a.py': 'X = 1\n'}, {'a.py': 'X = 2\n'})
        self.assertEqual(self.opaque(tree), [])

    EXAMPLES = (
        ('a backtick fence', '```\nOLD_HELPER()\n```'),
        ('a tilde fence', '~~~\nOLD_HELPER()\n~~~'),
        ('a fence indented under nothing', '  ```\n  OLD_HELPER()\n  ```'),
        ('a fence inside a list item', '- Example:\n\n  ```\n  OLD_HELPER()\n  ```'),
        ('a fence closed only by one as long', '````\nOLD_HELPER()\n```\nstill code\n````'),
        ('a fence with an info string', '```python\nOLD_HELPER()\n```'),
        ('a fence nobody closed', '```\nOLD_HELPER()'),
        ('a fence of the other character inside one', '```\n~~~\nOLD_HELPER()\n~~~\n```'),
        ('an indented block', '    OLD_HELPER()'),
        ('an indented block of several lines', '    one()\n    OLD_HELPER()'),
        ('an indented block after a list closed', '- Status\n\nDone.\n\n    OLD_HELPER()'),
        ('a block indented with a tab', '\tOLD_HELPER()'),
        ('a fence a line with an info string does not close', '```\n``` still open\nOLD_HELPER()\n```'),
        ('a fence four spaces in, which is an indented line and opens nothing',
         '    ```\n    OLD_HELPER()'),
        ('a marker inside an indented block, which opens no list', '    - OLD_HELPER: yes'),
        ('a numbered marker inside an indented block', '    1. OLD_HELPER()'),
        ('a fence inside a block quote', '> Example:\n>\n> ```py\n> OLD_HELPER()\n> ```'),
        ('a fence inside a nested block quote', '> > ```\n> > OLD_HELPER()\n> > ```'),
        ('a quoted fence with no space after the marker', '>```\n>OLD_HELPER()\n>```'),
        ('a quoted fence three spaces in', '   > ~~~\n   > OLD_HELPER()\n   > ~~~'),
        ('an indented block inside a block quote', '>\n>     OLD_HELPER()'),
        ('a quoted fence inside a list item', '- item\n\n  > ```\n  > OLD_HELPER()\n  > ```'),
        ('a quote marker four spaces in, which is an indented block', '    > OLD_HELPER()'),
        ('a quote four columns into a list item, measured from its content',
         '- item\n\n    > ```\n    > OLD_HELPER()\n    > ```'),
        ('a block after a quote that closed the list item', '- item\n> quote\n\n    OLD_HELPER()'),
        ('a block after a quote a blank line below the list item',
         '- item\n\n> quotation\n\n    OLD_HELPER()'),
        ('a quoted block reached by two tabs after the marker', '>\n>\t\tOLD_HELPER()'),
        ('a space and a tab after a marker two columns in, which reach a block',
         '  > \tOLD_HELPER()'),
        ('a tab in a nested quote, measured from the line and not the level', '> >\n> > \tOLD_HELPER()'),
        ('a block after a quote that left an item quote', '- item\n\n  > quote\n> more\n\n    OLD_HELPER()'),
        ('a block after a quote that left an item quote with no blank line', '- item\n  > quote\n> more\n\n    OLD_HELPER()'),
        ('a block after an empty quote, where no paragraph is open', '>\n    OLD_HELPER()'),
        ('a block right after a closed fence', '```\nx\n```\n    OLD_HELPER()'),
        ('a fence in a list item after a lazy line', '- item\nlazy text\n    ```\n    OLD_HELPER()'),
        ('a block after a heading that closed the list item',
         '- Install it\n## Usage\n\n    OLD_HELPER()'),
        ('a block right under a heading, where no paragraph is open',
         '## Usage\n    ```\n    OLD_HELPER()\n    ```'),
        ('a block right under a thematic break',
         '---\n    OLD_HELPER()'),
        ('a block under a list item a blank line closed',
         '  1. one\n\n    ```\n    OLD_HELPER()\n    ```'),
        ('a fence inside the inner of two items opened on one line',
         '- 1. one\n      ```\n      OLD_HELPER()\n      ```'),
        ('a fence in the outer item after the inner one closed',
         '- a\n  - b\n\n  ```\n  OLD_HELPER()\n  ```'),
        ('a fence that ends a quoted paragraph rather than continuing it',
         '> para\n```\nOLD_HELPER()\n```'),
        ('a block after a closing raw-text tag, which starts no HTML block',
         '</pre> text\n\n    OLD_HELPER()'),
        ('a fence under a declaration CommonMark does not start',
         '<!>\n```\nOLD_HELPER()\n```'),
        ('a fence after an item a blank-line HTML block ended with',
         '- a\n\n  <div>\n```\nOLD_HELPER()\n```'),
        ('a fence under a paragraph a lone inline tag cannot interrupt',
         'para\n<span>\n```\nOLD_HELPER()\n```'),
        ('a fence under a paragraph an indented tag continues',
         'text\n    <div>\n```\nOLD_HELPER()\n```'),
        ('a fence opened on a list marker line',
         '1. ```sh\n   OLD_HELPER()\n   ```'),
        ('a block after an empty item that could not interrupt a paragraph',
         'Title\n-  \n\n    OLD_HELPER()'),
        ('a block right under a marker with nothing after it', '-\n      OLD_HELPER()'),
        ('a block after five spaces behind a marker',
         '-     OLD_HELPER()'),
        ('a block after an empty item a blank line ended',
         'Intro\n\n-\n\n    OLD_HELPER()'),
        ('a block after an empty ordered item a blank line ended',
         '1.\n\n    OLD_HELPER()'),
        ('a block after a setext underline read as an empty item',
         '- Setup\n  -\n\n      OLD_HELPER()'),
        ('a block right under an empty item that follows a paragraph item',
         '- a\n-\n      OLD_HELPER()'),
        ('a second marker past a wide gap, which is a block',
         '1.     2. OLD_HELPER()'),
        ('a block after an empty nested quote', '> >\n    OLD_HELPER()'),
        ('a marker four columns past the content it reaches, which is a block',
         '   *  x\n      # deep\n\t- OLD_HELPER()'),
        ('a fence under a closing raw-text tag, which opens a paragraph',
         '</pre> text\n```\nOLD_HELPER()\n```'),
        ('a block after an HTML block that closed a list item',
         '- Install it\n<div>\n\n    OLD_HELPER()'),
        ('a fence after a line that left the item a comment opened in',
         '- a\n\n  <!--\nbar\n```\nOLD_HELPER()\n```'),
        ('a block after a comment that ran over a blank line inside its item',
         '- a\n\n  <!--\n\n  still comment\n  -->\n\n      OLD_HELPER()'),
        ('a fence under a paragraph that opens with an inline tag',
         '<b>bold</b> text\n```\nOLD_HELPER()\n```'),
        ('a block after a comment that closed on its own line',
         '<!-- a note -->\n\n    OLD_HELPER()'),
        ('a block after an HTML block a blank line ended',
         '<div>\n\n    OLD_HELPER()'),
        ('a block after a comment closed on a later line',
         '<!--\nx\n-->\n\n    OLD_HELPER()'),
        ('a block after a thematic break spelled with list markers',
         '- a\n- - -\n\n    OLD_HELPER()'),
    )

    ASSERTIONS = (
        ('a mention on its own', 'The OLD_HELPER is gone.'),
        ('a continuation four spaces under a list marker',
         '- Status\n\n    We removed OLD_HELPER from the API.'),
        ('a nested list item', '- Status\n    - and OLD_HELPER went with it'),
        ('the wrapped second line of a sentence',
         'A paragraph about it\n    that says OLD_HELPER is gone.'),
        ('the prose after a fence four spaces in, which never opened',
         '    ```\nWe removed OLD_HELPER from the API.'),
        ('a mention inside a block quote', '> We removed OLD_HELPER.'),
        ('a lazy line continuing a quoted paragraph', '> A paragraph\nthat says OLD_HELPER is gone.'),
        ('the prose after a quote whose fence never closed',
         '> ```\n> example()\nWe removed OLD_HELPER from the API.'),
        ('a quoted line three spaces past the marker, which is not a block',
         '>\n>    We removed OLD_HELPER from the API.'),
        ('a quote marker four spaces under a paragraph, which continues it',
         'A paragraph\n    > ```\n    > OLD_HELPER()'),
        ('a lazy line four spaces in after a quoted paragraph', '> para\n    We removed OLD_HELPER.'),
        ('a tab after the marker, which is two columns from it', '>\tWe removed OLD_HELPER.'),
        ('a space and a tab after the marker', '> \tWe removed OLD_HELPER.'),
        ('a tab after a marker two columns in', '  >\tWe removed OLD_HELPER.'),
        ('a nested quote whose tabs leave a paragraph', '> >\n>\t> \tWe removed OLD_HELPER.'),
        ('a quote after an item quote whose fence never closed', '- item\n\n  > ```\n  > code\n> We removed OLD_HELPER.'),
        ('a fence four columns in under a quoted paragraph', '> para\n>      ```\n> We removed OLD_HELPER.'),
        ('a fence four columns in under a paragraph', 'A paragraph\n    ```\nWe removed OLD_HELPER.'),
        ('a quote line after a lazy line, continuing its paragraph', '> para\nlazy text\n>     We removed OLD_HELPER.'),
        ('a quote nested past the depth the walk reads', '>' * 2000 + ' We removed OLD_HELPER.'),
        ('prose after a heading closed the item a fence opened in',
         '- Install it\n## Usage\n\n    ```\n    keep()\n\nCall OLD_HELPER to reset.'),
        ('prose that leaves the item its fence opened in',
         '1. item\n\n      ```\nWe removed OLD_HELPER.'),
        ('a list item that ends a quoted paragraph',
         '> para\n- item\n\n    We removed OLD_HELPER.'),
        ('a quote marker four spaces under a quoted paragraph',
         '> para\n    > We removed OLD_HELPER.'),
        ('text inside an HTML block',
         '<div>\n    We removed OLD_HELPER.\n</div>'),
        ('a comment running over a blank line',
         '<!--\n\n    We removed OLD_HELPER.\n-->'),
        ('a heading four columns in, which continues the paragraph',
         'Run the following:\n    # install\n    OLD_HELPER --init'),
        ('a thematic break four columns in, which continues the paragraph',
         'Run the following:\n    ---\n    OLD_HELPER --init'),
        ('a heading four columns past an item paragraph',
         '- Setup:\n  run this\n      # install\n      OLD_HELPER --init'),
        ('an HTML start four columns in, continuing a quoted paragraph',
         '>.\n    <!\n>     OLD_HELPER'),
        ('a pre tag closed on itself, which starts no HTML block',
         '> Note:\n> <pre/>\n    We removed OLD_HELPER.'),
        ('an item whose marker is followed by five spaces',
         '-     Install it\n\n    We removed OLD_HELPER.'),
        ('an empty item, whose content starts one past its marker',
         '-  \n  ---\n    We removed OLD_HELPER.'),
        ('a bare marker, which still opens an item',
         '-\n  ***\n    We removed OLD_HELPER.'),
        ('the outer item a closed inner one returns to',
         '- a\n  - b\n\n  c\n\n    We removed OLD_HELPER.'),
        ('a processing instruction running over a blank line',
         '<?php\n\n    We removed OLD_HELPER.\n?>'),
        ('a declaration running over a blank line',
         '<!DOCTYPE x\n\n    We removed OLD_HELPER.\n>'),
        ('an item opened by a marker and a tab',
         '1.\tStep one\n\n\tMore about OLD_HELPER.'),
        ('prose after a fence closed inside the item its marker line opened',
         '1. ```sh\n   x()\n   ```\n   We removed OLD_HELPER.'),
        ('an ordered marker not numbered 1, which continues a paragraph',
         'Title\n2. two\n    ```\n    We removed OLD_HELPER.'),
        ('a tag four columns in, continuing a quoted paragraph',
         '>.\n    <div>\n>     We removed OLD_HELPER.'),
        ('an ordered marker that leaves a quoted paragraph and opens a list',
         '> Tip: read the docs.\n2. Install\n\n    We removed OLD_HELPER.'),
        ('a lazy tag line inside a quoted item, which only continues it',
         '> 1. Step\n    <div>\n    We removed OLD_HELPER.'),
        ('a lazy fence line inside a quoted item, which only continues it',
         '> 1. q\n    ```\n    We removed OLD_HELPER.'),
        ('a tab after a marker behind a quote',
         '> - > \tWe removed OLD_HELPER.'),
        ('a marker four columns in under a wide item, which continues it',
         '-    Install it\n    -     We removed OLD_HELPER.'),
        ('a tab after a marker, measured from the line',
         '-\tStep one\n\n      We removed OLD_HELPER.'),
        ('a CDATA block running over a blank line',
         '<![CDATA[\n\n    We removed OLD_HELPER.\n]]>'),
        ('a list opened by the line that closed a quote',
         '   > q\n2. two\n\n    We removed OLD_HELPER.'),
        ('an empty item that cannot interrupt a paragraph, and what continues it',
         'Title\n1. \n       We removed OLD_HELPER.'),
        ('indented text in a comment over a blank line inside its item',
         '- a\n\n  <!--\n\n      We removed OLD_HELPER.\n  -->'),
        ('raw text in a pre block over a blank line',
         '<pre>\n\n    We removed OLD_HELPER.\n</pre>'),
        ('a paragraph a lazy HTML tag cannot interrupt',
         '> para\n<span>\n    We removed OLD_HELPER.'),
    )

    def test_a_name_inside_a_code_block_is_an_example(self):
        """Every regex spelling tried for this fixed a shape and broke another. The shapes are
        listed in EXAMPLES and ASSERTIONS above and walked here, so a new spelling has to
        answer all of them at once."""
        for name, shown in self.EXAMPLES:
            with self.subTest(name):
                self.assertNotIn('OLD_HELPER', claims.prose('README.md', '# doc\n\n' + shown + '\n'))
        for name, said in self.ASSERTIONS:
            with self.subTest(name):
                self.assertIn('OLD_HELPER', claims.prose('README.md', '# doc\n\n' + said + '\n'))

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
        """Found by the independent reviewer on the first round it was able to run.

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
