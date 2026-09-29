"""What the matrix runner counts as a test that ran, and what the campaign asks pytest about which
files hold one."""
import importlib.metadata
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
# The benches live beside this file, imported whether it is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_evidence
import review_matrix as matrix
from test_review_flow import FLOW, TEST_G, FlowBench
from test_review_matrix import Bench, rule

SUBTESTS = ('import sys, unittest\nsys.path.insert(0, ".")\nfrom thing import over\n\n\n'
            'class Sub(unittest.TestCase):\n'
            '    def test_all_skip(self):\n        for value in (11, 12):\n'
            '            with self.subTest(value=value):\n                self.skipTest("later")\n\n'
            '    def test_some_run(self):\n        for value in (11, 12):\n'
            '            with self.subTest(value=value):\n'
            '                if value == 11:\n                    self.skipTest("later")\n'
            '                self.assertTrue(over(value))\n')

# A conftest that collects YAML cases and keeps one of them out of the walk.
YAML_CONFTEST = ('import pytest\ncollect_ignore = ["cases/skip.yaml"]\n\n\n'
                 'def pytest_collect_file(parent, file_path):\n'
                 '    if file_path.suffix == ".yaml":\n'
                 '        return YamlFile.from_parent(parent, path=file_path)\n\n\n'
                 'class YamlFile(pytest.File):\n    def collect(self):\n'
                 '        yield YamlItem.from_parent(self, name=self.path.stem)\n\n\n'
                 'class YamlItem(pytest.Item):\n    def runtest(self):\n        assert True\n')


def pytest_major():
    """The major version of the pytest the matrix runs, which is this interpreter's; 0 where none
    is installed."""
    try:
        return int(importlib.metadata.version('pytest').split('.')[0])
    except importlib.metadata.PackageNotFoundError:
        return 0


# Before pytest 9, without pytest-subtests 0.14.2 or later, a subtest that passes reports nothing,
# so a case about subtests there passes or fails for another reason.
BEFORE_SUBTESTS = 'subtest cases need pytest 9, or pytest-subtests 0.14 or later; on older ' \
                  'versions a node whose subtests skip reads as not run and is refused'


def commit(where, message='more'):
    subprocess.run(['git', '-C', str(where), 'add', '-A'], check=True)
    subprocess.run(['git', '-C', str(where), '-c', 'user.email=a@b.invalid', '-c', 'user.name=A',
                    'commit', '-q', '-m', message], check=True)


class RanTests(unittest.TestCase):
    """What a clean run of one node must show before the matrix measures it or demands it."""

    @unittest.skipIf(pytest_major() < 9, BEFORE_SUBTESTS)
    def test_a_node_whose_every_subtest_skipped_did_not_run(self):
        """pytest reports a unittest node whose every subTest skipped as `1 passed, 2 skipped`,
        so it was kept as run, and a mutant that un-skipped it was recorded as a catch. A node
        where one subtest ran is still run."""
        bench = Bench(self, test=SUBTESTS)
        kept = matrix.ran_alone(str(bench.where), ['test_thing.py::Sub::test_all_skip',
                                                   'test_thing.py::Sub::test_some_run'])
        self.assertEqual(kept, ['test_thing.py::Sub::test_some_run'])

    @unittest.skipIf(pytest_major() < 9, BEFORE_SUBTESTS)
    def test_a_node_that_asserts_after_every_subtest_skipped_is_refused(self):
        """Nothing pytest reports tells an assertion after all-skipped subtests from a return
        there, so the node reads as one that did not run: the refusal is the chosen direction,
        and a node that stops refusing it has found a signal that must be stated."""
        bench = Bench(self, test=SUBTESTS + '\n    def test_assert_after(self):\n'
                                            '        for value in (11, 12):\n'
                                            '            with self.subTest(value=value):\n'
                                            '                self.skipTest("later")\n'
                                            '        self.assertTrue(over(12))\n')
        self.assertEqual(matrix.ran_alone(str(bench.where), ['test_thing.py::Sub::test_assert_after']), [])

    def test_a_case_that_only_expects_to_fail_is_refused_by_what_it_did(self):
        """The refusal is right for a case whose every node is an expected failure; it said the
        nodes were skipped, and quotes the clean run now."""
        bench = Bench(self, test='import pytest\n\n\ndef test_over_the_limit():\n    pytest.xfail("later")\n')
        with self.assertRaises(SystemExit) as refused:
            bench.run(rule(enumeration='echo 1'))
        self.assertIn('expected to fail', str(refused.exception))
        self.assertIn('1 xfailed', str(refused.exception))

    def test_a_node_whose_every_subtest_expected_to_fail_did_not_run(self):
        """`1 passed, 2 xfailed` exits zero with no subtest run, as an all-skip node does."""
        self.assertFalse(matrix.ran_clean(0, '1 passed, 2 xfailed in 0.02s'))
        self.assertTrue(matrix.ran_clean(0, '1 passed, 1 xfailed, 1 subtests passed in 0.02s'))

    def test_a_child_a_passing_test_started_does_not_outlive_the_run(self):
        """A child the test started in the run's group and did not wait for survived the
        run, since the group was killed only on a timeout or an interruption. It could write to
        the tree after the mutant was restored."""
        bench = Bench(self, test='import subprocess, sys\n\n\ndef test_leaves_a_child():\n'
                                 '    subprocess.Popen([sys.executable, "-c", "import time, pathlib; '
                                 'time.sleep(2); pathlib.Path(\'late.txt\').write_text(\'x\')"])\n')
        code, tail = matrix.run_case(str(bench.where), None, ['test_thing.py'])
        self.assertIn('1 passed', tail)
        time.sleep(4)
        self.assertFalse((bench.where / 'late.txt').exists(), 'the child wrote after the run ended')

    def test_a_node_id_that_is_not_utf8_is_read_by_what_it_did(self):
        """pytest's cache plugins write every node id and every failed one at session end, and
        an id holding a surrogate escape, as a file name that is not UTF-8 gives, raised there
        before the summary line was printed: a pass and a failure both read as a crash, so a
        mutant such a test caught was never recorded caught. The cache fixture stays usable."""
        bench = Bench(self)
        (bench.where / 'conftest.py').write_text(YAML_CONFTEST.replace(
            'name=self.path.stem)', 'name=self.path.stem + "\\udce9")').replace(
            '        assert True\n', '        config = self.config\n'
            '        config.cache.set("bymax/probe", 1)\n'
            '        assert config.cache.get("bymax/probe", 0) == 1\n'
            '        assert "bad" not in self.path.stem\n'))
        (bench.where / 'cases').mkdir()
        (bench.where / 'cases' / 'good.yaml').write_text('a: 1\n')
        (bench.where / 'cases' / 'bad.yaml').write_text('a: 1\n')
        for stem, verdict in (('good', 'passed'), ('bad', 'failed')):
            with self.subTest(stem=stem):
                code, tail = matrix.run_case(str(bench.where), None, ['cases/%s.yaml::%s\udce9' % (stem, stem)])
                self.assertEqual(matrix.outcome(code, tail), verdict, tail)
                self.assertIn('1 ' + verdict, tail)


class CollectedTests(unittest.TestCase):
    """Which files the campaign asks pytest about, and what it takes as the answer."""

    def cases(self):
        """A directory of YAML cases a conftest collects and one it ignores, beside a broken
        Python neighbour that stops the directory's collect."""
        bench = Bench(self)
        (bench.where / 'conftest.py').write_text(YAML_CONFTEST)
        (bench.where / 'cases').mkdir()
        (bench.where / 'cases' / 'skip.yaml').write_text('a: 1\n')
        (bench.where / 'cases' / 'keep.yaml').write_text('a: 1\n')
        (bench.where / 'cases' / 'test_broken.py').write_text('import nothing_that_exists\n')
        commit(bench.where)
        cwd = os.getcwd()
        os.chdir(bench.where)
        self.addCleanup(os.chdir, cwd)
        return bench

    def test_a_case_the_conftest_ignores_is_not_a_test_beside_a_broken_neighbour(self):
        """Named alone, pytest collects a file its conftest's collect_ignore keeps out of the
        walk, so asking alone called it a test once the neighbour stopped the directory."""
        self.cases()
        asked = {}
        self.assertIs(review_evidence.collects_a_test('cases/skip.yaml', asked), False)
        self.assertIs(review_evidence.collects_a_test('cases/keep.yaml', asked), True)

    def test_a_case_whose_directory_failed_to_collect_is_not_ruled_out(self):
        """A collect hook that raises on a neighbour fails the directory under the directory's
        own id, so the case beside it is in neither answer; read as "not a test" it asked for no
        matrix."""
        bench = self.cases()
        (bench.where / 'conftest.py').write_text(YAML_CONFTEST.replace(
            '        return YamlFile', '        if file_path.name == "bad.yaml":\n'
            '            raise ValueError("unreadable")\n        return YamlFile'))
        (bench.where / 'cases' / 'bad.yaml').write_text('a: 1\n')
        commit(bench.where)
        self.assertIsNot(review_evidence.collects_a_test('cases/keep.yaml'), False)
        self.assertEqual(review_evidence.collected_elsewhere(['cases/keep.yaml']), {'cases/keep.yaml'})

    def test_a_document_a_conftest_collects_is_asked_about(self):
        """Only Python files were asked about, so a YAML case a conftest collects was no changed
        test. A document under no collection hook is still not asked about."""
        bench = Bench(self)
        (bench.where / 'checks').mkdir()
        (bench.where / 'checks' / 'conftest.py').write_text(
            YAML_CONFTEST.replace('collect_ignore = ["cases/skip.yaml"]\n', ''))
        (bench.where / 'checks' / 'check.yaml').write_text('a: 1\n')
        (bench.where / 'docs').mkdir()
        (bench.where / 'docs' / 'notes.yaml').write_text('a: 1\n')
        commit(bench.where)
        cwd = os.getcwd()
        os.chdir(bench.where)
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(review_evidence.collected_elsewhere(['checks/check.yaml', 'docs/notes.yaml']),
                         {'checks/check.yaml'})
        self.assertFalse(review_evidence.under_a_collect_hook(str(bench.where), 'docs/notes.yaml'))

    def test_a_document_a_named_plugin_collects_is_a_changed_test(self):
        """A conftest can register its collection hook from another module through
        `pytest_plugins`, and its own source then never names the hook, so a YAML case that
        plugin collects was left out of the tests a delta changed."""
        bench = Bench(self)
        base = subprocess.run(['git', '-C', str(bench.where), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
        (bench.where / 'conftest.py').write_text('pytest_plugins = ["yaml_plugin"]\n')
        (bench.where / 'yaml_plugin.py').write_text(
            YAML_CONFTEST.replace('collect_ignore = ["cases/skip.yaml"]\n', ''))
        (bench.where / 'checks').mkdir()
        (bench.where / 'checks' / 'check.yaml').write_text('a: 1\n')
        commit(bench.where)
        cwd = os.getcwd()
        os.chdir(bench.where)
        self.addCleanup(os.chdir, cwd)
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
        self.assertIn('checks/check.yaml', review_evidence.tests_changed(base, head)[0])

    def test_a_directory_out_of_time_is_collected_once_for_all_its_files(self):
        """matrix_first asked each changed file of a directory whose collect ran out of time,
        and each ask waited out the same deadline again."""
        clean = matrix.CLEAN
        matrix.CLEAN = 3
        self.addCleanup(setattr, matrix, 'CLEAN', clean)
        bench = Bench(self)
        (bench.where / 'pkg').mkdir()
        (bench.where / 'pkg' / 'conftest.py').write_text('while True:\n    pass\n')
        for name in ('test_a.py', 'test_b.py'):
            (bench.where / 'pkg' / name).write_text('def test_x():\n    assert True\n')
        commit(bench.where)
        cwd = os.getcwd()
        os.chdir(bench.where)
        self.addCleanup(os.chdir, cwd)
        asked, began = {}, time.monotonic()
        self.assertEqual([review_evidence.collects_a_test(name, asked)
                          for name in ('pkg/test_a.py', 'pkg/test_b.py')], [None, None])
        self.assertLess(time.monotonic() - began, 5)

    def test_a_node_id_that_is_not_utf8_comes_back_as_pytest_spelled_it(self):
        """pytest names a node by its file, and a file name that is not UTF-8 holds a surrogate
        escape there, which a strict writer refused: the collector stopped mid-report. The id
        reaches the reader as pytest spelled it, and so does a failed collector's. APFS cannot
        hold such a name, so a conftest spells the id the way pytest would."""
        bench = Bench(self)
        (bench.where / 'conftest.py').write_text(YAML_CONFTEST.replace(
            'name=self.path.stem)\n', 'name="caf\\udce9")\n'
            '        if self.path.stem == "bad":\n'
            '            yield Box.from_parent(self, name="box\\udce9")\n\n\n'
            'class Box(pytest.Collector):\n    def collect(self):\n        raise ValueError("unreadable")\n'))
        (bench.where / 'cases').mkdir()
        (bench.where / 'cases' / 'one.yaml').write_text('a: 1\n')
        (bench.where / 'cases' / 'bad.yaml').write_text('a: 1\n')
        self.assertEqual(matrix.ids(str(bench.where), ['cases/one.yaml']), ['cases/one.yaml::caf\udce9'])
        self.assertEqual(matrix.walked(str(bench.where), ['cases/bad.yaml']),
                         ({'cases/bad.yaml'}, {'cases/bad.yaml'}))

class NamedItsOwnWayTests(FlowBench):
    """A test the project names its own way — `python_files = check_*.py` — is a test to every
    rule that sorts a delta's files, not only to the one that asks for a matrix."""

    def save(self, message):
        """Commit the tree as it stands: the bench's commit() also rewrites code.txt."""
        self.git('add', '-A')
        self.git('commit', '-qm', message)

    def the_project_names_its_tests(self):
        (self.repo / 'pytest.ini').write_text('[pytest]\npython_files = check_*.py\n')
        (self.repo / 'checks').mkdir()
        (self.repo / 'checks/check_g.py').write_text('import sys\nsys.path.insert(0, ".")\n' + TEST_G)

    def test_a_correction_that_changes_such_a_test_does_not_widen_its_scope(self):
        """The scope rule excused tests by their names, so a correction that changed the test it
        proves itself with was refused as touching a file no finding named."""
        self.the_project_names_its_tests()
        self.commit('a project that names its tests its own way')
        self.start()
        self.report('claude', [dict(id='values.py:wrong', kind='defect', priority='P1', evidence='wrong')])
        self.report('codex', [])
        self.triage([dict(id='claude::values.py:wrong', status='open', evidence='Confirmed')])
        (self.repo / 'values.py').write_text('ONE = 1\nTWO = 2\nTHREE = 3\n')
        (self.repo / 'checks/check_g.py').write_text(
            'import sys\nsys.path.insert(0, ".")\n' + TEST_G + 'def test_three(): assert True\n')
        self.save('fix what the finding named, with its test')
        refused = self.start(ok=False, correction=True, reason='').stderr
        self.assertNotIn('No open finding names', refused)
        self.assertIn('no measured mutation matrix exists', refused)

    def test_a_correction_that_deletes_such_a_test_does_not_widen_its_scope(self):
        """A deleted file cannot be asked about in the corrected tree, so a test the project
        names its own way, once deleted, read as a file no finding named."""
        self.the_project_names_its_tests()
        (self.repo / 'checks/check_gone.py').write_text(TEST_G)
        self.commit('a project that names its tests its own way')
        self.start()
        self.report('claude', [dict(id='values.py:wrong', kind='defect', priority='P1', evidence='wrong')])
        self.report('codex', [])
        self.triage([dict(id='claude::values.py:wrong', status='open', evidence='Confirmed')])
        (self.repo / 'values.py').write_text('ONE = 1\nTWO = 2\nTHREE = 3\n')
        (self.repo / 'checks/check_gone.py').unlink()
        self.save('fix what the finding named, and delete a test')
        self.start(correction=True)

    def test_a_merged_in_test_named_its_own_way_is_listed(self):
        """The merged-in list was read by name, so a test merged from a side branch was not
        shown to reviewers as one."""
        self.the_project_names_its_tests()
        self.commit('a test the project names its own way')
        base = self.git('rev-parse', 'HEAD')
        self.git('switch', '-qc', 'side')
        (self.repo / 'checks/check_side.py').write_text(TEST_G)
        self.save('a test written on a side branch')
        self.git('switch', '-q', '-')
        (self.repo / 'values.py').write_text('ONE = 1\nTWO = 2\nTHREE = 3\n')
        self.save('work of our own')
        self.git('merge', '-q', '--no-ff', '-m', 'merge side', 'side')
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(review_evidence.merged_in_tests(base, self.git('rev-parse', 'HEAD')),
                         ['checks/check_side.py'])

    def test_a_deleted_test_that_failed_to_collect_is_listed(self):
        """The tolerant collect leaves out a file whose collection failed, so deleting an
        import-broken test hid the deletion from both reviewers."""
        self.the_project_names_its_tests()
        (self.repo / 'checks/check_broken.py').write_text('import nothing_that_exists\n')
        self.commit('a test the project names its own way that cannot import')
        base = self.git('rev-parse', 'HEAD')
        (self.repo / 'checks/check_broken.py').unlink()
        self.save('delete it')
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(review_evidence.tests_changed(base, self.git('rev-parse', 'HEAD'))[1],
                         ['checks/check_broken.py'])

    def test_a_deleted_test_named_its_own_way_is_listed(self):
        """The deleted-test list was read by name, and a file gone from the tree cannot be asked
        about there; the base's tree is asked instead."""
        self.the_project_names_its_tests()
        (self.repo / 'checks/check_gone.py').write_text(TEST_G)
        self.commit('two tests the project names its own way')
        base = self.git('rev-parse', 'HEAD')
        (self.repo / 'checks/check_gone.py').unlink()
        self.save('delete a test')
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(review_evidence.tests_changed(base, self.git('rev-parse', 'HEAD'))[1],
                         ['checks/check_gone.py'])

if __name__ == '__main__':
    unittest.main()
