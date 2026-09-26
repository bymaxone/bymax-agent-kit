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

    def test_a_python_file_is_read_in_the_encoding_it_declares(self):
        """A Latin-1 source declared by PEP 263 is valid Python. Decoded by the process locale
        it raised before retired() could answer, and every step that asks it stopped."""
        tree = Tree(self, {'a.py': 'OLD_HELPER = 1\n'}, {'a.py': ''})
        (tree.where / 'b.py').write_bytes(b'# -*- coding: latin-1 -*-\n# OLD_HELPER is kept\n'
                                          b'NAME = "caf\xe9"\n')
        run(tree.where, 'add', '-A')
        run(tree.where, 'commit', '-q', '-m', 'a Latin-1 source')
        tree.head = claims.git('rev-parse', 'HEAD', cwd=str(tree.where)).strip()
        self.assertIn('caf\xe9', claims.git('show', tree.head + ':b.py', cwd=str(tree.where)))
        self.assertEqual(tree.retired(), [('b.py', 'OLD_HELPER')])

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

    def test_an_annotated_constant_is_a_definition(self):
        """`LIMIT: int = 3` assigns LIMIT as `LIMIT = 3` does. One case per read: annotated in
        the base and removed, the definition read must count it; moved and annotated, the alive
        grep must find it; annotated in place, nothing was removed and the gate must not say so."""
        tree = Tree(self, {'a.py': 'LIMIT_MAX: int = 1\n# reads LIMIT_MAX\n'},
                    {'a.py': '# reads LIMIT_MAX\n'})
        self.assertEqual(tree.retired(), [('a.py', 'LIMIT_MAX')])
        tree = Tree(self, {'a.py': 'LIMIT_MAX = 1\n# reads LIMIT_MAX\n', 'b.py': 'Y = 2\n'},
                    {'a.py': '# reads LIMIT_MAX\n', 'b.py': 'LIMIT_MAX: int = 1\nY = 2\n'})
        self.assertEqual(tree.retired(), [])
        tree = Tree(self, {'a.py': 'LIMIT_MAX = 1\n# reads LIMIT_MAX\n'},
                    {'a.py': 'LIMIT_MAX: int = 1\n# reads LIMIT_MAX\n'})
        self.assertEqual(tree.retired(), [])

    def test_text_shaped_like_a_definition_defines_nothing(self):
        """A docstring line `FLAG: set FLAG=1` and a dict entry `ERR_ONE: f(retry=0),` look like
        annotated assignments to a regex. Rewording or removing either removes no definition,
        and the refusing tier must not say it did; nor may such a line elsewhere keep a name
        alive that the delta really removed."""
        doc = '"""Environment:\n    BYMAX_FLAG: turns it on, as in BYMAX_FLAG=1.\n"""\n'
        tree = Tree(self, {'a.py': doc + 'import os\n', 'README.md': 'Set `BYMAX_FLAG`.\n'},
                    {'a.py': doc.replace('turns it on, as in BYMAX_FLAG=1.', 'set it to 1.') + 'import os\n',
                     'README.md': 'Set `BYMAX_FLAG`.\n'})
        self.assertEqual(tree.retired(), [])
        table = 'from errs import ERR_ONE\n\nTABLE = {\n    ERR_ONE: dict(retry=False),\n}\n# ERR_ONE retries\n'
        tree = Tree(self, {'a.py': table},
                    {'a.py': table.replace('    ERR_ONE: dict(retry=False),\n', '')})
        self.assertEqual(tree.retired(), [])
        tree = Tree(self, {'a.py': 'OLD_LIMIT = 1\n# reads OLD_LIMIT\n',
                           'b.py': 'def f():\n    """Limits.\n\n    OLD_LIMIT: was = 2.\n    """\n'},
                    {'a.py': '# reads OLD_LIMIT\n',
                     'b.py': 'def f():\n    """Limits.\n\n    OLD_LIMIT: was = 2.\n    """\n'})
        self.assertEqual(tree.retired(), [('a.py', 'OLD_LIMIT'), ('b.py', 'OLD_LIMIT')])

    def test_only_a_constant_case_assignment_is_a_definition(self):
        """A lowercase name assigned is a variable, in both reads: removing
        `tmp_value = 1` is not removing a definition a sentence could still assert."""
        tree = Tree(self, {'a.py': 'tmp_value = 1\n# tmp_value is scratch\n'},
                    {'a.py': '# tmp_value is scratch\n'})
        self.assertEqual(tree.retired(), [])

    def test_a_name_the_file_imports_is_alive(self):
        """Replacing a constant with an import of it removes nothing the prose can still name.
        Dropping an import is not a definition removed: the name usually lives in a package no
        search here can read."""
        for head in ('from dependency import LIMIT_MAX\n', 'from dependency import OTHER as LIMIT_MAX\n',
                     'import LIMIT_MAX\n', 'import LIMIT_MAX.sub\n'):
            with self.subTest(head):
                tree = Tree(self, {'a.py': 'LIMIT_MAX = 1\n# reads LIMIT_MAX\n'},
                            {'a.py': head + '# reads LIMIT_MAX\n'})
                self.assertEqual(tree.retired(), [])
        tree = Tree(self, {'a.py': 'from dependency import OLD_LIMIT\n# uses OLD_LIMIT\n'},
                    {'a.py': '# uses OLD_LIMIT\n'})
        self.assertEqual(tree.retired(), [])

    def test_a_wildcard_import_keeps_a_name_alive(self):
        """`from pathlib import *` in place of `class Path` still binds Path at run time, and
        which names a wildcard binds is the imported module's to say. Without it, the class
        removed is a name lost."""
        # In the file the class left, and in another file the search for where it went reads.
        for head in ({'a.py': 'from pathlib import *\n# builds a Path\n', 'b.py': ''},
                     {'a.py': '# builds a Path\n', 'b.py': 'from pathlib import *\nPath\n'}):
            with self.subTest(head):
                tree = Tree(self, {'a.py': 'class Path:\n    pass\n# builds a Path\n', 'b.py': ''}, head)
                self.assertEqual(tree.retired(), [])
        tree = Tree(self, {'a.py': 'class Path:\n    pass\n# builds a Path\n'}, {'a.py': '# builds a Path\n'})
        self.assertEqual(tree.retired(), [('a.py', 'Path')])

    def test_a_name_the_file_assigns_is_alive(self):
        """A def refactored into a binding still binds the name a sentence names; a bare
        annotation and a name only read bind nothing."""
        for head in ('old_helper = print\n', 'old_helper: object = print\n',
                     'old_helper, other = print, len\n', '[old_helper, *rest] = [print]\n',
                     'for old_helper in [print]:\n    pass\n', 'with open(__file__) as old_helper:\n    pass\n',
                     '(old_helper := print)\n', 'try:\n    pass\nexcept Exception as old_helper:\n    pass\n',
                     # Held as strings on their nodes, never as a name in a store position.
                     'def process(old_helper):\n    return old_helper\n', 'run = lambda old_helper: 0\n',
                     'def process(*old_helper):\n    pass\n', 'def process(*, old_helper):\n    pass\n',
                     'def process(**old_helper):\n    pass\n', 'def process[old_helper]():\n    pass\n',
                     'match print:\n    case old_helper:\n        pass\n',
                     'match print:\n    case int() as old_helper:\n        pass\n',
                     'match []:\n    case [*old_helper]:\n        pass\n',
                     'match {}:\n    case {**old_helper}:\n        pass\n'):
            with self.subTest(head):
                tree = Tree(self, {'a.py': 'def old_helper(x):\n    return x\n# calls old_helper\n'},
                            {'a.py': head + '# calls old_helper\n'})
                self.assertEqual(tree.retired(), [])
        # Binding nothing.
        for head in ('old_helper: object\n', 'value = old_helper\n'):
            with self.subTest(head):
                tree = Tree(self, {'a.py': 'def old_helper(x):\n    return x\n# calls old_helper\n'},
                            {'a.py': head + '# calls old_helper\n'})
                self.assertEqual(tree.retired(), [('a.py', 'old_helper')])

    def test_a_name_moved_in_any_shape_the_tree_counts_is_alive(self):
        """The tree counts a name after a semicolon or in a chained assignment, so the search
        for where it went must reach those lines too: a pattern anchored at the start of a line
        did not, and a constant that only moved read as removed."""
        for shape in ('FIRST = LIMIT_MAX = 3\n', 'import os; LIMIT_MAX = 3\n'):
            with self.subTest(shape):
                tree = Tree(self, {'a.py': shape, 'b.py': '', 'README.md': 'Uses `LIMIT_MAX`.\n'},
                            {'a.py': '', 'b.py': shape, 'README.md': 'Uses `LIMIT_MAX`.\n'})
                self.assertEqual(tree.retired(), [])

    def test_only_the_tree_makes_a_name_lost(self):
        """Text shaped like a definition is not one, so the text read of a file that does not
        parse only keeps a name alive. The base's tree decides what was lost; a head that does
        not parse narrows it by its text; a base that does not parse contributes nothing."""
        cases = (
            ('removed from a base that parses', 'OLD_LIMIT = 1\n', 'print "x"\n', ['README.md']),
            ('kept in the text of a head that does not parse',
             'OLD_LIMIT = 3\ndef old_helper(x):\n    return x\n',
             'OLD_LIMIT = 3\ndef old_helper(x):\n    return x\nprint "x"\n', []),
            ('removed, with a docstring in the same file shaped like it',
             'OLD_LIMIT = 1\ndef f():\n    """Uses it.\n\n    OLD_LIMIT: was = 1.\n    """\n',
             'def f():\n    """Uses it.\n\n    OLD_LIMIT: was = 1.\n    """\n', ['README.md', 'a.py']),
            ('a docstring reworded beside a line that does not parse',
             '"""Environment:\n    OLD_LIMIT: on, as in OLD_LIMIT=1.\n"""\n',
             '"""Environment:\n    OLD_LIMIT: set it to 1.\n"""\nprint "x"\n', []),
            ('a keyword argument dropped beside a line that does not parse',
             'import os\nos.environ.update(dict(\n    OLD_LIMIT="/opt",\n))\n', 'print "x"\n', []),
            ('removed, a longer name kept beside a line that does not parse',
             'OLD_LIMIT = 1\nOLD_LIMIT_MAX = 2\n', 'OLD_LIMIT_MAX = 2\nprint "x"\n', ['README.md']),
            ('removed, a longer name ending in it kept beside a line that does not parse',
             'OLD_LIMIT = 1\nNEW_OLD_LIMIT = 2\n', 'NEW_OLD_LIMIT = 2\nprint "x"\n', ['README.md']),
            ('a chained definition beside a line that does not parse',
             'FIRST = OLD_LIMIT = 1\n', 'FIRST = OLD_LIMIT = 1\nprint "x"\n', []),
            ('a definition after a semicolon beside a line that does not parse',
             'x = 1; OLD_LIMIT = 2\n', 'x = 1; OLD_LIMIT = 2\nprint "x"\n', []),
            ('a one-line compound definition beside a line that does not parse',
             'if True: OLD_LIMIT = 2\n', 'if True: OLD_LIMIT = 2\ndef broken(:\n', []),
            ('a base that does not parse, ported', 'OLD_LIMIT = 1\nprint "x"\n', 'print("x")\n', []),
            ('a base that does not parse, half-written', 'OLD_LIMIT = 1\ndef broken(:\n', 'def broken(:\n', []),
        )
        for label, before, after, lost in cases:
            with self.subTest(label):
                tree = Tree(self, {'a.py': before, 'README.md': 'Uses `OLD_LIMIT` and `old_helper`.\n'},
                            {'a.py': after, 'README.md': 'Uses `OLD_LIMIT` and `old_helper`.\n'})
                self.assertEqual(tree.retired(), [(where, 'OLD_LIMIT') for where in lost])

    def test_a_name_moved_into_a_file_that_does_not_parse_is_alive(self):
        """The text keeps a name alive where the tree cannot read the file at all, in any shape."""
        for shape in ('LIMIT_MAX = 3\n', 'FIRST = LIMIT_MAX = 3\n'):
            with self.subTest(shape):
                tree = Tree(self, {'a.py': shape, 'b.py': 'print "x"\n', 'README.md': 'Uses `LIMIT_MAX`.\n'},
                            {'a.py': '', 'b.py': shape + 'print "x"\n', 'README.md': 'Uses `LIMIT_MAX`.\n'})
                self.assertEqual(tree.retired(), [])

    def test_a_leading_bom_is_python(self):
        """A BOM is valid Python, so a file carrying one is read by its tree: a removal from it
        is reported, and adding one beside a reworded docstring or a dropped keyword argument
        reads nothing as removed."""
        tree = Tree(self, {'a.py': '\ufeffOLD_LIMIT = 1\n', 'README.md': 'Uses `OLD_LIMIT`.\n'},
                    {'a.py': '\ufeff\n', 'README.md': 'Uses `OLD_LIMIT`.\n'})
        self.assertEqual(tree.retired(), [('README.md', 'OLD_LIMIT')])
        doc = '"""Environment:\n    BYMAX_FLAG: turns it on, as in BYMAX_FLAG=1.\n"""\n'
        tree = Tree(self, {'a.py': doc, 'README.md': 'Set `BYMAX_FLAG`.\n'},
                    {'a.py': '\ufeff' + doc.replace('turns it on, as in BYMAX_FLAG=1.', 'set it to 1.'),
                     'README.md': 'Set `BYMAX_FLAG`.\n'})
        self.assertEqual(tree.retired(), [])
        tree = Tree(self, {'a.py': 'import os\nos.environ.update(dict(\n    BYMAX_HOME="/opt",\n))\n',
                           'README.md': 'Set `BYMAX_HOME`.\n'},
                    {'a.py': '\ufeffimport os\nos.environ.update(dict())\n', 'README.md': 'Set `BYMAX_HOME`.\n'})
        self.assertEqual(tree.retired(), [])

    def test_a_comment_after_code_is_read_for_what_it_names(self):
        """The line stays code for the split, and the comment on it still asserts: a removed
        name left in `value = 2  # uses OLD_NAME` is a dangling reference like any other. Only
        the comment is read, so a name in the code before it is the suite's to catch."""
        tree = Tree(self, {'a.py': 'OLD_NAME = 1\nvalue = 2  # uses OLD_NAME\n'},
                    {'a.py': 'value = 2  # uses OLD_NAME\n'})
        self.assertEqual(tree.retired(), [('a.py', 'OLD_NAME')])
        tree = Tree(self, {'a.py': 'OLD_NAME = 1\nvalue = OLD_NAME  # a note\n'},
                    {'a.py': 'value = OLD_NAME  # a note\n'})
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

    def test_a_command_block_in_markdown_is_code(self):
        """A fenced `bash` block in a command file is what a model runs verbatim. Filed under
        prose with the rest of the file, a delta changing one was told it had changed no code;
        the sentence around it is still prose."""
        tree = Tree(self, {'cmd.md': '# Push\n\n```bash\ngit push origin HEAD\n```\n'},
                    {'cmd.md': '# Push it\n\n```bash\ngit push -u origin HEAD\n```\n'})
        split = claims.split_delta(tree.base, tree.head, cwd=str(tree.where))
        self.assertEqual(sorted(text for _, _, text in split['code']),
                         ['git push -u origin HEAD', 'git push origin HEAD'])
        self.assertEqual(sorted(text for _, _, text in split['prose']), ['# Push', '# Push it'])

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

    def test_a_path_git_quotes_is_read_as_itself(self):
        """Git quotes a non-ASCII path it prints one to a line, and the quoted spelling names no
        file: a dangling mention in café.md went unreported, a def moved to café.py read as
        removed, and a removal claimed of text surviving in café.md went unchecked."""
        tree = Tree(self, {'a.py': 'OLD_NAME = 1\n', 'café.md': 'Uses `OLD_NAME`.\n'},
                    {'a.py': '', 'café.md': 'Uses `OLD_NAME`.\n'})
        self.assertEqual(tree.retired(), [('café.md', 'OLD_NAME')])
        tree = Tree(self, {'a.py': 'def old_helper(x):\n    return x\n', 'README.md': 'Calls `old_helper`.\n'},
                    {'café.py': 'def old_helper(x):\n    return x\n', 'README.md': 'Calls `old_helper`.\n'})
        self.assertEqual(tree.retired(), [])
        tree = Tree(self, {'café.md': 'Said most likely never joined.\n'},
                    {'café.md': 'Said most likely never joined.\n',
                     'NOTES.md': 'We removed `most likely never joined` from the message.\n'})
        self.assertEqual(tree.unkept(), [('NOTES.md', 'most likely never joined', 'café.md')])

    def test_release_history_asserts_nothing_live(self):
        """A changelog is append-only: an entry naming a symbol since removed is true of the
        release it records. Only the file named CHANGELOG.md, in any case and directory, is
        history; the same sentence in a README is a live claim."""
        for name in ('CHANGELOG.md', 'docs/ChangeLog.md', 'CHANGELOG.markdown'):
            with self.subTest(name):
                tree = Tree(self, {'a.py': 'OLD_HELPER = 1\n', name: 'Version 1 added `OLD_HELPER`.\n'},
                            {'a.py': '', name: 'Version 1 added `OLD_HELPER`.\n'})
                self.assertEqual(tree.retired(), [])
        tree = Tree(self, {'a.py': 'OLD_HELPER = 1\n', 'README.md': 'Version 1 added `OLD_HELPER`.\n'},
                    {'a.py': '', 'README.md': 'Version 1 added `OLD_HELPER`.\n'})
        self.assertEqual(tree.retired(), [('README.md', 'OLD_HELPER')])

    def test_a_markdown_file_in_either_spelling_is_read(self):
        """README.markdown is prose the way README.md is: a dangling mention there is found by
        the search over the tree, and its words are read, not skipped as a file of no kind."""
        tree = Tree(self, {'a.py': 'OLD_HELPER = 1\n', 'README.markdown': 'Set `OLD_HELPER` first.\n'},
                    {'a.py': '', 'README.markdown': 'Set `OLD_HELPER` first.\n'})
        self.assertEqual(tree.retired(), [('README.markdown', 'OLD_HELPER')])
        # Changed by the delta, it is a file this module reads, and its lines are prose.
        tree = Tree(self, {'README.markdown': 'Old.\n'}, {'README.markdown': 'New.\n'})
        self.assertEqual(claims.opaque(tree.base, tree.head, cwd=str(tree.where)), [])
        self.assertEqual(claims.marks('README.markdown', 'New.\n'), claims.marks('README.md', 'New.\n'))

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
