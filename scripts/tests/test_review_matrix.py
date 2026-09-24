"""The matrix runner: what it refuses, and what it records."""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
import review_matrix as matrix

GUARDED = 'LIMIT = 10\n\n\ndef over(value):\n    return value > LIMIT\n'
CASE = ('import sys\nsys.path.insert(0, ".")\nfrom thing import over\n\n\n'
        'def test_over_the_limit():\n    assert over(11)\n    assert not over(9)\n')


class Bench:
    """A tiny repository with one rule, one guard and one case that covers it."""

    def __init__(self, case, guard=GUARDED, test=CASE):
        self.where = Path(tempfile.mkdtemp())
        case.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.where)]))
        (self.where / 'thing.py').write_text(guard)
        (self.where / 'test_thing.py').write_text(test)
        subprocess.run(['git', 'init', '-q', str(self.where)], check=True)
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A',
                                     'commit', '-q', '-m', 'x']):
            subprocess.run(['git', '-C', str(self.where), *args], check=True)

    def spec(self, body):
        path = self.where / 'matrix.json'
        path.write_text(json.dumps(body))
        return str(path)

    def run(self, body, out=None):
        return matrix.record(str(self.where), self.spec(body), ['test_thing.py'], out=out)


def rule(**over):
    body = {'rule': 'one mutant per comparison the guard makes',
            'enumeration': 'grep -c ">" thing.py',
            'mutants': [{'file': 'thing.py', 'anchor': 'value > LIMIT',
                         'becomes': 'True', 'case': 'over_the_limit'}]}
    body.update(over)
    return [body]


class AnchorTests(unittest.TestCase):

    def test_an_anchor_that_matches_nothing_is_refused(self):
        """A mutation that never landed is a run that proves nothing, and its output reads
        as success. This package's memory records one that printed `69 passed` that way."""
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'absent', 'becomes': 'x',
                                     'case': 'over_the_limit'}]))
        self.assertIn('occurs 0 times', str(caught.exception))

    def test_an_anchor_that_matches_twice_is_refused(self):
        """The enumeration count is held at one so the ambiguous anchor is the only thing
        that can fail here; without that, the shorter-list refusal fires first and this case
        passes for a reason it does not name."""
        bench = Bench(self, guard='LIMIT = 10\nSPARE = LIMIT\n\n\ndef over(value):\n    return value > LIMIT\n')
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='echo 1',
                           mutants=[{'file': 'thing.py', 'anchor': 'LIMIT', 'becomes': '1',
                                     'case': 'over_the_limit'}]))
        self.assertIn('occurs 3 times', str(caught.exception))


class MeaningTests(unittest.TestCase):

    def test_a_case_that_already_fails_is_refused(self):
        """Failing with a mutant says nothing when it fails without one."""
        bench = Bench(self, test=CASE.replace('assert over(11)', 'assert over(1)'))
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule())
        self.assertIn('does not pass on the clean tree', str(caught.exception))

    def test_a_node_must_pass_alone_on_the_clean_tree(self):
        """Found by a reviewer: the clean run put the selected nodes in one pytest while the
        mutant runs each alone, so a node that leaned on an earlier one's side effect failed
        alone under a mutation of something else entirely, and the failure was recorded as a
        catch. The baseline runs each node alone, and refuses the one that fails there."""
        bench = Bench(self, test='STATE = []\n\n\ndef test_ordered_a():\n    STATE.append(1)\n\n\n'
                                 'def test_ordered_b():\n    assert STATE\n')
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'value > LIMIT', 'becomes': 'True',
                                     'case': 'ordered'}]))
        self.assertIn('does not pass on the clean tree (test_thing.py::test_ordered_b', str(caught.exception))

    def test_a_node_skipped_on_the_clean_tree_is_refused(self):
        """Found by the PR review: a node skipped on the clean tree passed the baseline, since
        pytest exits zero on a skip, and a mutant that changed its skip condition made it run
        and fail, which was recorded as a catch by a case that never ran clean."""
        bench = Bench(self, guard=GUARDED + '\n\ndef enabled():\n    return False\n',
                      test='import sys\nsys.path.insert(0, ".")\nimport pytest\nfrom thing import enabled\n\n\n'
                           '@pytest.mark.skipif(not enabled(), reason="off")\ndef test_gated():\n    assert False\n')
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'return False', 'becomes': 'return True',
                                     'case': 'gated'}]))
        self.assertIn('runs no test on the clean tree', str(caught.exception))
        # Beside a node that runs, the skipped one is left out rather than refused: the mutant
        # that would bring it to fail finds nothing to catch it, and survives.
        bench = Bench(self, guard=GUARDED + '\n\ndef enabled():\n    return False\n',
                      test=CASE + '\nimport pytest\nfrom thing import enabled\n\n\n'
                           '@pytest.mark.skipif(not enabled(), reason="off")\ndef test_over_gated():\n    assert False\n')
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'return False', 'becomes': 'return True',
                                     'case': 'over'}]))
        self.assertIn('survived', str(caught.exception))

    def test_a_mutant_that_hangs_a_case_is_stopped_and_restored(self):
        """A mutant that disables a loop's stop condition leaves pytest waiting forever, and
        without a deadline the matrix never reaches the restore and the source stays mutated.
        A run that never ends is refused like a crash, since it may hang before any test body
        runs; its process group dies with it, and the file is restored whatever happens."""
        floor = matrix.FLOOR
        matrix.FLOOR = 3
        self.addCleanup(setattr, matrix, 'FLOOR', floor)
        guard = GUARDED + '\n\ndef done():\n    return True\n'
        test = ('import os, subprocess, sys\nsys.path.insert(0, ".")\nfrom thing import done\n\n\n'
                'def test_waits():\n    if not done():\n'
                '        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])\n'
                '        open("grandchild.pid", "w").write(str(child.pid))\n'
                '    while not done():\n        pass\n')
        bench = Bench(self, guard=guard, test=test)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'return True',
                                     'becomes': 'return False', 'case': 'waits'}]))
        self.assertIn('timed out', str(caught.exception))
        self.assertEqual((bench.where / 'thing.py').read_text(), guard)
        # The whole group, not pytest alone: a process the test started dies with it.
        grandchild = int((bench.where / 'grandchild.pid').read_text())
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(grandchild, 0)

    def test_an_import_hang_is_not_a_catch(self):
        """A mutant that hangs the module while it is imported stops the run before any test
        body: counting the timeout as a catch credited a test that never ran."""
        floor = matrix.FLOOR
        matrix.FLOOR = 3
        self.addCleanup(setattr, matrix, 'FLOOR', floor)
        guard = GUARDED + '\n\nREADY = True\nwhile not READY:\n    pass\n'
        bench = Bench(self, guard=guard, test=CASE)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'READY = True',
                                     'becomes': 'READY = False', 'case': 'over_the_limit'}]))
        self.assertIn('timed out', str(caught.exception))
        self.assertEqual((bench.where / 'thing.py').read_text(), guard)

    def test_an_interrupted_run_takes_its_pytest_with_it(self):
        """In a session of its own pytest no longer hears the terminal's Ctrl-C, and an
        interrupted matrix left it running. Whatever stops the wait stops the group too."""
        bench = Bench(self, test='import os, time\n\n\ndef test_sleeps():\n'
                                 '    open("pytest.pid", "w").write(str(os.getpid()))\n    time.sleep(600)\n')
        def interrupt(*_):
            raise KeyboardInterrupt
        previous = signal.signal(signal.SIGALRM, interrupt)
        self.addCleanup(signal.signal, signal.SIGALRM, previous)
        signal.alarm(3)
        with self.assertRaises(KeyboardInterrupt):
            matrix.run_case(str(bench.where), None, ['test_thing.py::test_sleeps'])
        signal.alarm(0)
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(int((bench.where / 'pytest.pid').read_text()), 0)

    def test_a_case_that_collects_no_node_is_refused_by_name(self):
        """A case pytest finds nothing for has no baseline to pass and no node to run: refused
        by name, not recorded as a survivor of a run that never happened."""
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'value > LIMIT', 'becomes': 'True',
                                     'case': 'nothing_named_so'}]))
        self.assertIn("Case 'nothing_named_so' collects no test under test_thing.py", str(caught.exception))

    def test_a_collect_answers_with_what_pytest_vouched_for(self):
        """A node id is a line, and a parametrized one holds a space, so splitting on whitespace
        made two nodes out of one. The plugin takes where to write and what vouches for it out
        of the environment before any conftest is imported: read later, a conftest rewriting
        the file in pytest_sessionfinish made a directory holding a real test answer empty. And
        the repository cannot put its own module in the collector's place."""
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        (root / 'tests').mkdir()
        (root / 'tests/test_p.py').write_text(
            'import pytest\n\n\n@pytest.mark.parametrize("v", ["a b", "c"])\ndef test_p(v): assert v\n')
        whole = ['tests/test_p.py::test_p[a b]', 'tests/test_p.py::test_p[c]']
        self.assertEqual(matrix.ids(str(root), ['tests']), whole)
        # A conftest that looks for the channel once collection is over finds nothing to rewrite.
        (root / 'conftest.py').write_text(
            'import os\nfrom pathlib import Path\n\n\ndef pytest_sessionfinish(session, exitstatus):\n'
            '    where, token = os.environ.get("BYMAX_COLLECT_OUT"), os.environ.get("BYMAX_COLLECT_TOKEN")\n'
            '    if where and token:\n'
            '        Path(where).write_text("BYMAX_COLLECT " + token + "\\n")\n')
        self.assertEqual(matrix.ids(str(root), ['tests']), whole)
        # Modules the repository names after the collector's file, with that conftest still
        # waiting to rewrite a report: none takes the collector's place.
        (root / 'review_collect.py').write_text('x = 1\n')
        (root / 'lib').mkdir()
        (root / 'lib/review_collect.py').write_text('x = 1\n')
        (root / 'pytest.ini').write_text('[pytest]\npythonpath = lib\n')
        (root / 'evilmod.py').write_text('x = 1\n')
        (root / 'evil-1.0.dist-info').mkdir()
        (root / 'evil-1.0.dist-info/METADATA').write_text('Metadata-Version: 2.1\nName: evil\nVersion: 1.0\n')
        (root / 'evil-1.0.dist-info/entry_points.txt').write_text('[pytest11]\nreview_collect = evilmod\n')
        self.assertEqual(matrix.ids(str(root), ['tests']), whole)
        # A line without this run's token says nothing, even one shaped like "prefix id".
        report = root / 'report'
        report.write_text('BYMAX_COLLECT t0k\nx forged.py::forged\nt0k tests/a.py::test_a\n')
        self.assertEqual(matrix.reported(report, 't0k'), ['tests/a.py::test_a'])
        # And a report without this run's header is not this run's report, whatever it holds.
        report.write_text('t0k tests/a.py::test_a\n')
        self.assertIsNone(matrix.reported(report, 't0k'))
        # A collector that never writes, here unregistered by a conftest, is refused.
        (root / 'conftest.py').write_text(
            'def pytest_configure(config):\n'
            '    for name, plugin in config.pluginmanager.list_name_plugin():\n'
            '        if name.startswith("bymax_collect_"):\n'
            '            config.pluginmanager.unregister(plugin)\n')
        with self.assertRaises(SystemExit) as caught:
            matrix.ids(str(root), ['tests'])
        self.assertIn('never reported what it found', str(caught.exception))

    def test_a_surviving_mutant_is_the_finding(self):
        """A guard whose case cannot tell the mutant from the original is decoration."""
        bench = Bench(self, test='def test_over_the_limit():\n    assert True\n')
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule())
        self.assertIn('survived', str(caught.exception))

    def test_a_mutant_keeps_the_file_s_own_line_endings(self):
        """Found by a reviewer: read_text() turns CRLF into LF, so a file restored through
        text came back with every line ending changed — the worktree left dirty and the
        author's own source rewritten until they reset it. The bytes go back as they were,
        and the mutant goes in keeping the ending the file already used."""
        bench = Bench(self)
        guard = bench.where / 'thing.py'
        guard.write_bytes(GUARDED.encode().replace(b'\n', b'\r\n'))
        before = guard.read_bytes()
        mutant = {'file': 'thing.py', 'anchor': 'value > LIMIT', 'becomes': 'True', 'case': 'over_the_limit'}
        path, original = matrix.apply_mutant(str(bench.where), mutant)
        self.assertEqual(path.read_bytes().count(b'\r\n'), before.count(b'\r\n'))
        self.assertIn(b'return True', path.read_bytes())
        path.write_bytes(original)
        self.assertEqual(guard.read_bytes(), before)
        bench.run(rule())
        self.assertEqual(guard.read_bytes(), before)

    def test_a_mutant_changes_only_what_its_anchor_names(self):
        """Found by a reviewer: the mutated copy was rewritten with one ending for the whole
        file and re-encoded as UTF-8 from a locale decode, so lines the mutant never named
        changed while the case ran, and a source that is not UTF-8 was mangled under the
        measurement. The case reads the file, so outside the anchor it stays the author's."""
        bench = Bench(self)
        mixed = bench.where / 'mixed.py'
        mixed.write_bytes(b'LIMIT = 10\r\nNOTE = "caf\xe9"\nTAIL = 2\n')
        before = mixed.read_bytes()
        path, original = matrix.apply_mutant(str(bench.where), {
            'file': 'mixed.py', 'anchor': 'LIMIT = 10', 'becomes': 'LIMIT = 11', 'case': 'over_the_limit'})
        self.assertEqual(path.read_bytes(), before.replace(b'LIMIT = 10', b'LIMIT = 11'))
        path.write_bytes(original)
        self.assertEqual(mixed.read_bytes(), before)
        # An anchor spelled with \n finds its line in a file written with \r\n.
        crlf = bench.where / 'crlf.py'
        crlf.write_bytes(b'A = 1\r\nB = 2\r\n')
        path, original = matrix.apply_mutant(str(bench.where), {
            'file': 'crlf.py', 'anchor': 'A = 1\nB = 2\n', 'becomes': 'A = 9\nB = 8\n', 'case': 'over_the_limit'})
        self.assertEqual(path.read_bytes(), b'A = 9\r\nB = 8\r\n')
        path.write_bytes(original)
        # A replacement the spec already spells with the file's ending is spelled once.
        self.assertEqual(matrix.spelled('X = 1\r\n', {'anchor': 'X = 1', 'becomes': 'A = 1\r\nB = 2'})[1],
                         'A = 1\r\nB = 2')
        # And the count matches the anchor the mutant will match, or a multi-line anchor in a
        # CRLF file matches nothing here and is counted as a site of its own.
        crlf.write_bytes(b'A = 1\r\nB = 2\r\nC = 3\r\n')
        self.assertEqual(matrix.sites(str(bench.where), [
            {'file': 'crlf.py', 'anchor': 'A = 1\nB = 2\n', 'becomes': 'X = 9\n', 'case': 'over_the_limit'},
            {'file': 'crlf.py', 'anchor': 'B = 2\n', 'becomes': 'Y = 8\n', 'case': 'over_the_limit'}]), 1)
        # And the count that runs before the mutants reads the source the same way: read as
        # text, a source that is not UTF-8 raised here, ahead of the decoding put in to
        # survive one.
        self.assertEqual(matrix.sites(str(bench.where), [
            {'file': 'mixed.py', 'anchor': 'LIMIT = 10', 'becomes': 'LIMIT = 11', 'case': 'over_the_limit'}]), 1)

    def test_only_a_node_that_ran_clean_can_be_asked_to_have_failed(self):
        """Found by a reviewer: a test whose body passes and whose teardown raises reads
        `1 passed, 1 error` — so asking that node to have failed is a demand nobody could
        satisfy."""
        bench = Bench(self, test=(
            'import pytest\n\n\n@pytest.fixture\ndef leaky():\n    yield 1\n    raise RuntimeError\n\n\n'
            'def test_over_the_limit(leaky): assert True\n\n\ndef test_over_again(): assert True\n'))
        nodes = matrix.ids(str(bench.where), ['test_thing.py'])
        self.assertEqual([node.split('::')[-1] for node in nodes], ['test_over_again', 'test_over_the_limit'])
        self.assertEqual([node.split('::')[-1] for node in matrix.ran_alone(str(bench.where), nodes)],
                         ['test_over_again'])

    def test_a_mutant_that_only_breaks_the_import_is_refused(self):
        """A crash is not a measurement. A mutant that stops the module loading makes every
        case error, which reads as caught while the case never ran — measured on this file's
        own fixtures, where two mutants recorded 'caught 1 error'."""
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'def over(value):',
                                     'becomes': 'def over(', 'case': 'over_the_limit'}]))
        self.assertIn('stopped the tree from loading', str(caught.exception))

    def test_outcome_reads_a_mixed_run_as_a_crash(self):
        """The old rule and the new differ on exactly one tail — `N failed, M errors` — and no
        fixture produces it, which is why a reviewer found the presence rule had no
        discriminating case. A rule that classifies text is pinned by the text: a case that
        errored in setup never ran, and counting the failure beside it as a catch hides it.
        """
        self.assertEqual(matrix.outcome('1 failed, 3 errors in 0.20s'), 'error')
        self.assertEqual(matrix.outcome('1 error in 0.04s'), 'error')
        self.assertEqual(matrix.outcome('1 failed, 20 deselected in 0.11s'), 'failed')
        self.assertEqual(matrix.outcome('1 passed, 20 deselected in 0.08s'), 'passed')

    def test_a_caught_mutant_passes_and_the_tree_is_restored(self):
        bench = Bench(self)
        payload = bench.run(rule())
        self.assertEqual(payload['survivors'], [])
        self.assertEqual(payload['mutants'], 1)
        self.assertEqual((bench.where / 'thing.py').read_text(), GUARDED)

    def test_the_tree_is_restored_even_when_the_run_refuses(self):
        """A runner that leaves a mutant behind poisons every measurement after it."""
        bench = Bench(self, test='def test_over_the_limit():\n    assert True\n')
        with self.assertRaises(SystemExit):
            bench.run(rule())
        self.assertEqual((bench.where / 'thing.py').read_text(), GUARDED)


class EnumerationTests(unittest.TestCase):

    def test_a_rule_that_declares_no_enumeration_is_refused(self):
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration=''))
        self.assertIn('declares no enumeration', str(caught.exception))

    def test_a_list_shorter_than_its_own_command_says_is_refused(self):
        """The check the whole thing exists for: a list shorter than the rule's own command
        enumerates is a case nothing covers, and it used to be the silent default."""
        bench = Bench(self, guard='LIMIT = 10\n\n\ndef over(v):\n    return v > LIMIT or v > 99\n')
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='grep -o ">" thing.py | grep -c ">"',
                           mutants=[{'file': 'thing.py', 'anchor': 'v > LIMIT', 'becomes': 'True',
                                     'case': 'over_the_limit'}]))
        self.assertIn('short by 1', str(caught.exception))

    GUARD_TWO = 'LIMIT = 10\n\n\ndef over(v):\n    return v > LIMIT or v > 99\n'
    TWICE = {'file': 'thing.py', 'anchor': 'v > LIMIT', 'becomes': 'True', 'case': 'over_the_limit'}
    AGAIN = CASE + '\n\ndef test_over_again():\n    assert not over(5)\n'

    def refused(self, bench, said, **over):
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(**over))
        self.assertIn(said, str(caught.exception))

    def test_a_repeated_mutant_does_not_count_toward_the_enumeration(self):
        """Found by a reviewer: the same entry twice satisfied a command that counted two
        cases, ran the same test twice, and printed all caught over a case nothing ran."""
        twice, both = self.TWICE, 'grep -o ">" thing.py | grep -c ">"'
        bench = Bench(self, guard=self.GUARD_TWO, test=self.AGAIN)
        self.refused(bench, 'repeats a mutant', enumeration=both, mutants=[twice, dict(twice)])
        # The same mutation under another case is another measurement, not a repeat — and
        # not a mutation of the second site the command counts, either.
        self.refused(bench, 'short by 1', enumeration=both, mutants=[twice, dict(twice, case='over_again')])
        payload = bench.run(rule(enumeration='grep -c "v > LIMIT" thing.py',
                               mutants=[twice, dict(twice, case='over_again')]))
        self.assertEqual(payload['mutants'], 2)
        # A second replacement at one anchor is the same site, not the second one counted.
        self.refused(bench, 'short by 1', enumeration=both,
                     mutants=[twice, dict(twice, becomes='v >= LIMIT', case='over_again')])

    def test_a_site_is_where_a_mutation_lands(self):
        """Two anchors over one span land on one site and two disjoint anchors on two; a
        spelling is not a place, so `sub/../thing.py`, `thing.py` and a hard link to it are one
        file (which the resolved path did not know, nor that a case-folding disk reads THING.PY
        as thing.py); and a file that is not here is apply_mutant's refusal, not a crash in the
        count."""
        twice, both = self.TWICE, 'grep -o ">" thing.py | grep -c ">"'
        bench = Bench(self, guard=self.GUARD_TWO, test=self.AGAIN)
        self.refused(bench, 'short by 1', enumeration=both,
                     mutants=[twice, dict(twice, anchor='> LIMIT or', becomes='>= LIMIT or', case='over_again')])
        payload = bench.run(rule(enumeration=both, mutants=[twice, dict(twice, anchor='v > 99', case='over_again')]))
        self.assertEqual(payload['mutants'], 2)
        (bench.where / 'sub').mkdir()
        self.refused(bench, 'short by 1', enumeration=both,
                     mutants=[twice, dict(twice, file='sub/../thing.py', case='over_again')])
        self.refused(bench, 'repeats a mutant', enumeration='grep -c "v > LIMIT" thing.py',
                     mutants=[twice, dict(twice, file='sub/../thing.py')])
        os.link(bench.where / 'thing.py', bench.where / 'other.py')
        self.refused(bench, 'repeats a mutant', enumeration='grep -c "v > LIMIT" thing.py',
                     mutants=[twice, dict(twice, file='other.py')])
        self.refused(bench, 'not a file here', enumeration='echo 1', mutants=[dict(twice, file='missing.py')])

    def test_the_record_spells_a_test_against_the_real_root(self):
        """Found by measuring from the object store: handed a rootdir reached through a symlink,
        pytest spelled every id against the argument's own directory — a bare name for a file
        under tests/ — and the record named a file that did not exist."""
        bench = Bench(self)
        (bench.where / 'tests').mkdir()
        (bench.where / 'tests' / 'test_thing.py').write_text(CASE)
        link = Path(tempfile.mkdtemp()) / 'link'
        os.symlink(bench.where, link)
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(link.parent)]))
        self.assertEqual(matrix.nodes(str(link), ['tests', str(link / 'tests')], 'over_the_limit'),
                         ['tests/test_thing.py'])

    def test_a_spec_is_read_in_the_shape_the_runtime_writes(self):
        """Found by a reviewer: a list where the rule's name should be ran the matrix, was
        copied into every result, and crashed the runtime that later read the record."""
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(rule=['not', 'a', 'name']))
        self.assertIn('non-empty string', str(caught.exception))
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': 'value > LIMIT', 'becomes': 'True', 'case': 7}]))
        self.assertIn('case is 7', str(caught.exception))
        # A replacement equal to its anchor, in either line-break spelling, mutates nothing.
        for anchor, becomes in (('value > LIMIT', 'value > LIMIT'), ('a\r\nb', 'a\nb'), ('a\nb', 'a\r\nb')):
            with self.assertRaises(SystemExit) as caught:
                bench.run(rule(mutants=[{'file': 'thing.py', 'anchor': anchor, 'becomes': becomes,
                                         'case': 'test_over_the_limit'}]))
            self.assertIn('replacement is its anchor', str(caught.exception))
        with self.assertRaises(SystemExit) as caught:
            matrix.matrix(str(bench.where), rule() + rule(), ['test_thing.py'])
        self.assertIn('share a name', str(caught.exception))
        # The containers are part of the shape: a rule, a mutant, a list of mutants.
        for body, said in (([None], 'not a mapping'), (rule(mutants='x'), 'not a list'),
                           (rule(mutants=[7]), 'not a mapping'), (rule(enumeration=['ls']), 'not a string')):
            with self.assertRaises(SystemExit) as caught:
                matrix.matrix(str(bench.where), body, ['test_thing.py'])
            self.assertIn(said, str(caught.exception))

    def test_a_count_is_the_last_field_of_each_line_not_every_digit(self):
        """`grep -c` prints "path:count" per file, so a filename carrying a digit was being
        added to the total: a rule over mod_v2.py answered 3 for 1 real hit and fired a
        spurious short-by-N. Reading the last field is what grep guarantees."""
        bench = Bench(self, guard=GUARDED)
        (bench.where / 'mod_v2.py').write_text('X = 1\n')
        subprocess.run(['git', '-C', str(bench.where), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(bench.where), '-c', 'user.email=a@b.invalid',
                        '-c', 'user.name=A', 'commit', '-q', '-m', 'y'], check=True)
        payload = bench.run(rule(enumeration="grep -c 'value > LIMIT' thing.py mod_v2.py"))
        self.assertEqual(payload['survivors'], [])

    def test_not_derivable_by_command_is_allowed_only_with_a_reason(self):
        """Saying a rule cannot be enumerated mechanically is worth more than a fake command,
        so it is permitted — and it must say why, because that is the whole content."""
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='not derivable by command'))
        self.assertIn('does not say why', str(caught.exception))
        payload = bench.run(rule(enumeration='not derivable by command',
                                 why='the states are semantic, not syntactic'))
        self.assertEqual(payload['survivors'], [])

    def test_a_bare_count_with_no_field_separator_is_accepted(self):
        """A count printed with no field separator — `wc -l` and friends — was refused with a
        message saying the command had answered nothing, because only the text after a colon
        was read."""
        bench = Bench(self)
        (bench.where / 'one.txt').write_text('a\n')
        # `wc -l <path>` prints "N path": one field, no separator, which the suffix read
        # turned into "1 one.txt" and rejected as not a number.
        (bench.where / 'two.txt').write_text('')
        # Two files, so `wc -l` also prints its own "total" line: adding that double-counted
        # every multi-file rule, answering 2 for 1.
        payload = bench.run(rule(enumeration='wc -l one.txt two.txt'))
        self.assertEqual(payload['survivors'], [])

    def test_a_command_that_answers_nothing_is_not_an_enumeration(self):
        bench = Bench(self)
        with self.assertRaises(SystemExit) as caught:
            bench.run(rule(enumeration='true'))
        self.assertIn('produced no count', str(caught.exception))


class FingerprintTests(unittest.TestCase):

    def test_the_fingerprint_keeps_each_field_inside_its_boundary(self):
        """Name and content appended raw let `a`+`bc` and `ab`+`c` digest alike, so a record
        could be rebound to another file set under the same fingerprint."""
        where = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(where)]))
        (where / 'a').write_text('bc')
        (where / 'ab').write_text('c')
        self.assertNotEqual(matrix.digest(str(where), ['a']), matrix.digest(str(where), ['ab']))


class RecordTests(unittest.TestCase):

    def test_the_record_binds_to_the_head_and_the_mutated_files(self):
        """A record that does not name the tree it measured can be reused for another one."""
        bench = Bench(self)
        out = bench.where / 'rec.json'
        payload = bench.run(rule(), out=str(out))
        stored = json.loads(out.read_text())
        self.assertEqual(stored['head'], payload['head'])
        self.assertTrue(stored['head'])
        before = stored['tree']
        (bench.where / 'thing.py').write_text(GUARDED + '\nEXTRA = 1\n')
        self.assertNotEqual(bench.run(rule())['tree'], before)


class RefusalStatusTests(unittest.TestCase):
    """A refusal leaves the process with the status every other refusal in the toolkit uses."""

    def test_the_standalone_script_refuses_with_two(self):
        """bail() says why by raising SystemExit, which reaches the shell as 1. Every other
        refusal here exits 2, and the suite's own CLI helper asserts 2 — which is why these
        refusals could not be driven through a command line at all until now."""
        where = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(where)]))
        spec = where / 'empty.json'
        spec.write_text('[]')
        self.assertEqual(matrix.main(['review_matrix.py', str(spec), str(where)]), 2)


class EnumerationCountTests(unittest.TestCase):
    """One number per file, from output shapes that all state it differently.

    Every form here was measured on a real rule, and each fix for one broke another: reading
    the suffix alone refused `wc -l`; reading every digit token took the digits out of the
    paths `grep -c` prints; reading the first FIELD read nothing from a count printed last;
    and dropping the aggregate row by its label discarded a file that is named `total`.
    """

    def count(self, out):
        rows = [row.strip() for row in out.split('\n') if row.strip()]
        return [n for n in matrix.without_total(rows, matrix.per_row(rows)) if n is not None]

    def test_grep_prints_the_count_after_a_colon_and_digits_inside_the_path(self):
        """`mod_v2.py:0` states 0. Adding every digit token read the 2 out of the name and
        answered 3 where one hit exists, which let a rule ship a mutant list short by two."""
        self.assertEqual(sum(self.count('thing.py:1\nmod_v2.py:0\n')), 1)

    def test_wc_prints_the_count_first_with_no_separator(self):
        """Reading only the colon suffix refused `wc -l <file>` with a message saying it had
        answered nothing — a gate refusing a command that answered."""
        self.assertEqual(sum(self.count('       3 thing.py\n')), 3)

    def test_a_count_printed_last_without_a_separator_is_read(self):
        """Narrowing to the first FIELD to drop the aggregate row also stopped reading this,
        so `cases 4` bailed as "produced no count" while the command had answered 4."""
        self.assertEqual(sum(self.count('cases 4\n')), 4)

    def test_the_aggregate_row_of_a_multi_file_wc_is_not_counted(self):
        """`wc -l a b` appends its own total, and adding it answered 8 for 4: every
        multi-file rule was read as twice its size, so no short list was ever refused."""
        self.assertEqual(sum(self.count('       1 one.txt\n       0 two.txt\n       1 total\n')), 1)

    def test_a_file_named_total_keeps_its_count(self):
        """Dropping the row by its label alone discarded a real file and then refused the
        rule for having produced no count. The aggregate is the LAST row of a MULTI-file run
        holding the SUM of the rows above; one row over one file is none of those."""
        self.assertEqual(sum(self.count('       3 total\n')), 3)


if __name__ == '__main__':
    unittest.main()
