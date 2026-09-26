"""The correction gate the review runtime keeps: a correction that changes a test must carry a
mutation matrix the runtime measured on its head, whose results name the tests it changed and
added and show each of them catching a mutant. Driven through the CLI in a fixture repository."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import OLD_TEST, TEST_G, FlowBench
import review_evidence
import review_matrix


class MatrixGateTests(FlowBench):
    """What a correction round that changes a test is refused for, and what it is let through on."""

    def test_a_refused_matrix_blocks_like_every_other_refusal(self):
        """bail() refused by raising SystemExit with a message, which exits 1, while every
        other refusal in the runtime exits 2 — so a caller keying on 2 for BLOCKED read a
        surviving mutant as a different class of failure. It also made these refusals
        untestable: the bench's flow() asserts 2, so no case could reach them through the CLI."""
        self.start()
        spec = self.root / 'empty-matrix.json'
        spec.write_text('[]')
        refused = self.flow('matrix', '--spec', str(spec), 'scripts/tests', ok=False)
        self.assertIn('non-empty list of rules', refused.stderr)

    def test_a_correction_that_changes_a_test_needs_a_measured_matrix(self):
        """Refusals of matrix_first, because a gate nobody tries is decoration.

        Reported by a reviewer: replacing this function's body with `return` left the suite
        green, so its refusals guarded nothing anyone had checked.
        """
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_g.py').write_text(TEST_G)
        self.commit('a correction that changes a test')

        missing = self.start(ok=False, correction=True, reason='').stderr
        self.assertIn('no measured mutation matrix exists', missing)

        directory = Path(self.flow('status')['directory'])
        head = self.git('rev-parse', 'HEAD')
        record = directory / ('matrix-' + head + '.json')

        record.write_text(json.dumps({'head': 'another', 'mutants': 1, 'tree': 'x',
                                       'survivors': []}))
        self.assertIn('names head another', self.start(ok=False, correction=True, reason='').stderr)

        record.write_text(json.dumps({'head': head, 'mutants': 0, 'tree': 'x', 'survivors': []}))
        self.assertIn('measured no mutants', self.start(ok=False, correction=True, reason='').stderr)

        record.write_text(json.dumps({'head': head, 'mutants': 1, 'tree': '', 'survivors': []}))
        self.assertIn('no fingerprint', self.start(ok=False, correction=True, reason='').stderr)

        record.write_text(json.dumps({'head': head, 'mutants': 1, 'tree': 'x',
                                       'survivors': ['test_g']}))
        self.assertIn('has survivors', self.start(ok=False, correction=True, reason='').stderr)

        # The fingerprint is recomputed, not tested for presence: a record saying `tree: x`
        # passed here while two sentences said it was bound to the tree it measured.
        record.write_text(json.dumps({'head': head, 'mutants': 1, 'tree': 'not-a-digest',
                                       'survivors': [], 'files': ['tests/test_g.py']}))
        self.assertIn('does not match', self.start(ok=False, correction=True, reason='').stderr)

        record.unlink()
        self.matrix('tests/test_g.py', [('ONE = 1', 'ONE = 2', 'test_g')], where='values.py', enumeration='echo 1')
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_record_naming_files_its_results_never_mutated_is_refused(self):
        """The file list is the record's own and the digest is recomputed over it, so a list
        swapped for files the matrix never touched carried a matching fingerprint and bound
        the record to nothing the results measured."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_g.py').write_text(TEST_G)
        self.commit('a correction that changes a test')
        self.matrix('tests/test_g.py', [('ONE = 1', 'ONE = 2', 'test_g')], where='values.py', enumeration='echo 1')
        directory = Path(self.flow('status')['directory'])
        record = directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')
        kept = json.loads(record.read_text())
        kept['results'][0]['file'] = 'tests/other.py'
        record.write_text(json.dumps(kept))
        self.assertIn('results mutated tests/other.py',
                      self.start(ok=False, correction=True, reason='').stderr)

    def test_a_candidate_frozen_without_the_gates_meets_them_before_a_reviewer_reads(self):
        """A campaign an earlier runtime froze under this policy never met the matrix or the
        claims check, while the prompt says the latter ran. Each is asked again before
        a reviewer reads: here the record goes after the freeze, and then a head whose prose
        names a name it removed is written into the frozen state by hand."""
        record, _ = self.measured_record()
        self.start(correction=True, reason='')
        self.checks()
        record.unlink()
        self.assertIn('no measured mutation matrix exists', self.flow('prompt', ok=False).stderr)
        (self.repo / 'values.py').write_text('ONE = 1\n')
        (self.repo / 'README.md').write_text('Set `TWO` first.\n')
        self.commit('a head no start froze')
        directory = Path(self.flow('status')['directory'])
        state = json.loads((directory / 'state.json').read_text())
        state['head'] = self.git('rev-parse', 'HEAD')
        (directory / 'state.json').write_text(json.dumps(state))
        self.assertIn('Prose asserts a name this delta removed', self.flow('prompt', ok=False).stderr)

    def test_a_reviewed_candidate_frozen_without_the_gates_meets_them_before_its_receipt(self):
        """A state reviewed and triaged before this runtime was installed calls no
        reviewer again, so finish() is where the matrix is asked before the receipt."""
        record, _ = self.measured_record()
        self.start(correction=True, reason='')
        self.checks()
        self.report('claude')
        self.report('codex')
        self.triage()
        record.unlink()
        self.assertIn('no measured mutation matrix exists', self.flow('finish', ok=False).stderr)

    def test_a_test_the_project_names_its_own_way_needs_a_matrix(self):
        """pytest reads a project's python_files and TEST_PATH does not: a correction whose only
        test is checks/check_g.py under `python_files = check_*.py` changed a test all the same."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'pytest.ini').write_text('[pytest]\npython_files = check_*.py\n')
        (self.repo / 'checks').mkdir()
        (self.repo / 'checks/check_g.py').write_text('import sys\nsys.path.insert(0, ".")\n' + TEST_G)
        self.commit('a correction whose test the project names its own way')
        missing = self.start(ok=False, correction=True, reason='').stderr
        self.assertIn('no measured mutation matrix exists', missing)
        self.assertIn('checks/check_g.py', missing)

    def test_a_directory_pytest_cannot_answer_for_is_refused_by_name(self):
        """A collect that fails leaves pytest unable to say whether checks/check_g.py holds a
        test: a conftest that exits before the collector reports, one that fails to import, and
        the file itself failing to import. Read as "no test here", each ran with no matrix."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'pytest.ini').write_text('[pytest]\npython_files = check_*.py\n')
        (self.repo / 'checks').mkdir()
        (self.repo / 'checks/check_g.py').write_text(TEST_G)
        for conftest, test in (('import os\nos._exit(0)\n', TEST_G), ('import missing_module\n', TEST_G),
                               ('', 'import missing_module\n' + TEST_G)):
            with self.subTest(conftest=conftest, test=test):
                (self.repo / 'checks/conftest.py').write_text(conftest)
                (self.repo / 'checks/check_g.py').write_text(test)
                self.commit('a correction whose test directory cannot be collected: ' + conftest + test)
                refused = self.start(ok=False, correction=True, reason='').stderr
                self.assertIn('pytest could not say whether checks/check_g.py', refused)

    def test_a_module_beside_a_broken_test_is_asked_alone(self):
        """A failed directory collect says nothing about the module beside it: asked alone,
        pkg/app.py is code, and round one's prompt is built."""
        (self.repo / 'pkg').mkdir()
        (self.repo / 'pkg/test_app.py').write_text('import missing_module\n')
        (self.repo / 'pkg/app.py').write_text('X = 1\n')
        self.commit('a module beside a broken test')
        self.start()
        self.checks()
        prompt = self.flow('prompt').stdout
        self.assertIn('Tests changed in this delta: pkg/test_app.py.', prompt)

    def test_with_no_pytest_nothing_is_a_collected_test(self):
        """A runtime whose Python has no pytest cannot ask it, and nothing is a test it collects;
        refusing there blocked every round of a delta that touched a Python file."""
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        with mock.patch('importlib.util.find_spec', return_value=None), \
                mock.patch.object(review_matrix, 'nodes', side_effect=AssertionError('asked pytest')):
            self.assertEqual(review_evidence.collected_elsewhere(['values.py']), set())

    def test_a_refused_rerun_leaves_no_earlier_record_behind(self):
        """A matrix run again on the same head and refused before it writes, here by an anchor
        that occurs nowhere, leaves no record: the earlier run's would be accepted by start as
        the measurement of a spec it never ran."""
        record, _ = self.measured_record()
        spec = self.root / 'revised-matrix.json'
        spec.write_text(json.dumps([{'rule': 'fixture: a revised spec', 'enumeration': 'echo 1',
                                     'mutants': [{'file': 'values.py', 'anchor': 'ABSENT = 0',
                                                  'becomes': 'ABSENT = 1', 'case': 'test_g'}]}]))
        refused = self.flow('matrix', '--spec', str(spec), 'tests/test_g.py', ok=False)
        self.assertIn('occurs 0 times', refused.stderr)
        self.assertFalse(record.exists())
        self.assertIn('no measured mutation matrix exists', self.start(ok=False, correction=True, reason='').stderr)

    def measured_record(self):
        """A correction that changes a test, its matrix run for real, and the record it wrote:
        what the forgeries below start from. Returns (record path, its contents)."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_g.py').write_text(TEST_G)
        self.commit('a correction that changes a test')
        self.matrix('tests/test_g.py', [('ONE = 1', 'ONE = 2', 'test_g')], where='values.py', enumeration='echo 1')
        directory = Path(self.flow('status')['directory'])
        record = directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')
        return record, json.loads(record.read_text())

    def refused_with(self, record, measured, said, **edits):
        """Write the measured record with these top-level fields replaced and assert the
        refusal names what the forgery did."""
        forged = json.loads(json.dumps(measured))
        forged.update(edits)
        record.write_text(json.dumps(forged))
        self.assertIn(said, self.start(ok=False, correction=True, reason='').stderr)

    def test_a_record_is_judged_by_its_results_not_its_summary(self):
        """Found by a reviewer: the survivor list is a summary the record carries beside the
        results, and clearing it by hand passed matrix_first while a result still said
        caught: false; a mutant count the results do not add up to is the same forgery."""
        record, measured = self.measured_record()
        result = measured['results'][0]
        self.refused_with(record, measured, 'results it did not catch: test_g', results=[dict(result, caught=False)])
        self.refused_with(record, measured, 'carries 1 results', mutants=2)
        self.refused_with(record, measured, 'repeats a result', mutants=2, results=[result, dict(result)])
        # The runtime records a mutation shared by two rules twice; that is two measurements.
        forged = json.loads(json.dumps(measured))
        forged['mutants'] = 2
        forged['results'].append(dict(result, rule='another rule'))
        record.write_text(json.dumps(forged))
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_record_is_read_in_the_shape_the_runtime_writes(self):
        """JSON an author can edit: the string "false" is truthy, a result may carry no case
        or a list where the rule's name should be, a survivor may be null, and a container may
        be the wrong kind; each is refused by name before any field is compared, so nothing
        raises."""
        record, measured = self.measured_record()
        result = measured['results'][0]
        self.refused_with(record, measured, 'shape the runtime never writes (caught)', results=[dict(result, caught='false')])
        self.refused_with(record, measured, 'shape the runtime never writes (case)',
                          results=[{k: v for k, v in dict(result, caught=False).items() if k != 'case'}])
        self.refused_with(record, measured, 'shape the runtime never writes (rule)', results=[dict(result, rule=['r'])])
        self.refused_with(record, measured, 'has survivors: None', survivors=[None])
        for field, value, said in (('results', 1, 'never writes (results)'), ('mutants', '1', 'never writes (mutants)'),
                                   ('mutants', True, 'never writes (mutants)'),
                                   ('files', ['tests/test_g.py', 1], 'not a list of paths'),
                                   ('tests', ['tests/test_g.py'], 'does not name the tests it ran')):
            self.refused_with(record, measured, said, **{field: value})

    def test_a_record_must_have_run_the_tests_the_correction_changed(self):
        """Found by a reviewer: a matrix run over some other test file carried a valid head,
        files and results, and start accepted the correction as matrix-backed although the
        changed test never ran. The record names the tests it ran; the changed ones must be
        among them."""
        record, measured = self.measured_record()
        self.refused_with(record, measured, 'did not run tests/test_g.py', tests={'tests/test_other.py': ['test_g']})
        # Named is not run: the file on the command line with none of its own cases selected.
        self.refused_with(record, measured, 'caught nothing in tests/test_g.py', tests={'tests/test_g.py': []})
        # A summary no result backs: the file said to hold a case nothing measured.
        self.refused_with(record, measured, 'says tests/test_g.py held nothing_measured, test_g, which its results do not',
                          tests={'tests/test_g.py': ['nothing_measured']})
        # A measured case credited to a second file's entry too: the results say where it ran.
        self.refused_with(record, measured, 'says tests/changed.py held test_g, which its results do not: they measured nothing there',
                          tests={'tests/changed.py': ['test_g'], 'tests/test_g.py': ['test_g']})
        # And the other direction: a result collected in a file the mapping never names.
        forged = json.loads(json.dumps(measured))
        forged['results'][0]['tests'] = ['tests/omitted.py', 'tests/test_g.py']
        record.write_text(json.dumps(forged))
        self.assertIn('caught in tests/omitted.py, which its tests mapping never names',
                      self.start(ok=False, correction=True, reason='').stderr)
        record.write_text(json.dumps(measured))
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_the_record_names_a_test_as_the_runtime_does_whatever_the_command_line_said(self):
        """Found by a reviewer: the matrix took an absolute path and wrote it verbatim, so its
        own record was refused against the root-relative name of the changed test; and a
        second file on the command line whose cases were all deselected was recorded as run."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_g.py').write_text(TEST_G)
        (self.repo / 'tests/test_h.py').write_text('def test_h(): assert 2 == 2\n')
        self.commit('a correction that changes two tests')
        self.matrix(str(self.repo / 'tests/test_g.py'), [('ONE = 1', 'ONE = 2', 'test_g')], also=('tests/test_h.py',),
                    where='values.py', enumeration='echo 1')
        directory = Path(self.flow('status')['directory'])
        record = json.loads((directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')).read_text())
        self.assertEqual(record['tests'], {'tests/test_g.py': ['test_g'], 'tests/test_h.py': []})
        self.assertIn('caught nothing in tests/test_h.py', self.start(ok=False, correction=True, reason='').stderr)
        self.matrix('tests/test_g.py', [('ONE = 1', 'ONE = 2', 'test_g')], also=('tests/test_h.py',),
                    where='values.py', enumeration='echo 1')
        self.assertIn('caught nothing in tests/test_h.py', self.start(ok=False, correction=True, reason='').stderr)
        # A directory on the command line runs whatever pytest collects under it, by pytest's
        # own rules: the record names both files, and the one no case of the spec lives in
        # is refused.
        self.matrix('tests', [('ONE = 1', 'ONE = 2', 'test_g')], where='values.py', enumeration='echo 1')
        record = json.loads((directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')).read_text())
        self.assertEqual(record['tests'], {'tests/test_g.py': ['test_g'], 'tests/test_h.py': []})
        self.assertIn('caught nothing in tests/test_h.py', self.start(ok=False, correction=True, reason='').stderr)

    def test_a_case_is_what_pytest_collected_not_what_the_text_says(self):
        """Found by a reviewer: a case named only in a comment of the changed file was credited
        to it, and a file pytest collects as *_test.py under a directory was not named at all.
        The record asks pytest, so the comment counts for nothing and the file is named — and
        a test of it the selector never chose does not run under the mutant, though it would
        fail there."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_g.py').write_text(TEST_G)
        (self.repo / 'tests/quiet_test.py').write_text('# def test_g(): a comment, not a case\n'
                                                       'from test_g import test_g as g\ndef test_q(): g()\n')
        self.commit('a correction that changes two tests')
        self.matrix('tests', [('ONE = 1', 'ONE = 2', 'test_g')], where='values.py', enumeration='echo 1')
        directory = Path(self.flow('status')['directory'])
        record = json.loads((directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')).read_text())
        self.assertEqual(record['tests'], {'tests/quiet_test.py': [], 'tests/test_g.py': ['test_g']})
        self.assertIn('caught nothing in tests/quiet_test.py', self.start(ok=False, correction=True, reason='').stderr)

    def test_a_node_id_selects_for_the_collect_what_it_selects_for_the_run(self):
        """Found by a reviewer: the collect stripped a node id to its file while the run kept
        the node, so a second file defining a case of the same name was credited with it though
        the run never selected it there. Both take the same arguments now; the second file's
        case fails with the first's, so selecting it is what the record shows."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_g.py').write_text(TEST_G)
        (self.repo / 'tests/test_b.py').write_text('from test_g import test_g as g\ndef test_g(): g()\n'
                                                   'def test_other(): assert 3 == 3\n')
        self.commit('a correction that changes two tests')
        self.matrix('tests/test_g.py::test_g', [('ONE = 1', 'ONE = 2', 'test_g')], also=('tests/test_b.py::test_g',),
                    where='values.py', enumeration='echo 1')
        directory = Path(self.flow('status')['directory'])
        record = json.loads((directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')).read_text())
        self.assertEqual(record['results'][0]['tests'], ['tests/test_b.py', 'tests/test_g.py'])
        self.assertEqual(record['tests'], {'tests/test_b.py': ['test_g'], 'tests/test_g.py': ['test_g']})
        self.matrix('tests/test_g.py::test_g', [('ONE = 1', 'ONE = 2', 'test_g')], also=('tests/test_b.py::test_other',),
                    where='values.py', enumeration='echo 1')
        record = json.loads((directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')).read_text())
        self.assertEqual(record['tests'], {'tests/test_b.py': [], 'tests/test_g.py': ['test_g']})
        self.assertIn('caught nothing in tests/test_b.py', self.start(ok=False, correction=True, reason='').stderr)

    def test_a_changed_test_is_credited_only_with_the_mutant_it_fails(self):
        """Found by a reviewer: the run put every selected test in one pytest and read one
        summary line, so a vacuous changed test sharing its name with an older test in another
        file was credited with the older one's catch, and matrix_first accepted a correction
        whose test exercised nothing. Each collected node runs alone under the mutant, and a
        file is credited with a case only when a test of it failed."""
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_g.py').write_text(TEST_G)
        self.commit('an older test that discriminates')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/test_changed.py').write_text('def test_g(): assert True\n')
        self.commit('a correction that adds a vacuous test of the same name')
        self.matrix('tests', [('ONE = 1', 'ONE = 2', 'test_g')], where='values.py', enumeration='echo 1')
        directory = Path(self.flow('status')['directory'])
        record = json.loads((directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')).read_text())
        self.assertEqual(record['results'][0]['tests'], ['tests/test_g.py'])
        self.assertEqual(record['tests'], {'tests/test_changed.py': [], 'tests/test_g.py': ['test_g']})
        self.assertIn('caught nothing in tests/test_changed.py', self.start(ok=False, correction=True, reason='').stderr)
        # The same test made to fail with the older one is credited, and the correction opens.
        (self.repo / 'tests/test_changed.py').write_text('from test_g import test_g as g\ndef test_g(): g()\n')
        self.commit('a correction whose test fails with the fix reverted')
        self.matrix('tests', [('ONE = 1', 'ONE = 2', 'test_g')], where='values.py', enumeration='echo 1')
        record = json.loads((directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')).read_text())
        self.assertEqual(record['tests'], {'tests/test_changed.py': ['test_g'], 'tests/test_g.py': ['test_g']})
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def a_guard_and_its_older_test(self):
        """A guard outside the test directory, and the test that already discriminates it:
        what a correction adding a test of its own starts from."""
        (self.repo / 'guard.py').write_text('LIMIT = 7\n')
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST)
        self.commit('a guard and the test that discriminates it')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()

    def guard_matrix(self):
        """The matrix over the guard, whose own file defines no test to count."""
        return self.matrix('tests', [('LIMIT = 7', 'LIMIT = 8', 'test_calc')],
                           where='guard.py', enumeration='echo 1')

    def test_the_test_the_delta_changed_is_the_test_that_must_catch(self):
        """Found by a reviewer: a file is credited when any node of it failed, so a vacuous
        test added beside a test that already discriminated made the record say the file
        caught the mutant, and the correction opened on the neighbour's evidence. A result
        names the nodes that failed, and the test the delta changed must be one of them."""
        self.a_guard_and_its_older_test()
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST + 'def test_calc_new(): assert True\n')
        self.commit('a correction that adds a vacuous test beside the older one')
        self.guard_matrix()
        self.assertIn('caught nothing with tests/test_calc.py::test_calc_new',
                      self.start(ok=False, correction=True, reason='').stderr)
        # The same test made to fail with the guard mutated is credited, and it opens.
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST + 'def test_calc_new(): assert LIMIT == 7\n')
        self.commit('a correction whose own test fails with the guard mutated')
        self.guard_matrix()
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_changed_test_is_found_under_its_class_and_its_parameters(self):
        """A node id is file::Class::name[param]; the changed test is the name the source
        defines, so the class has to prefix it and the parameters must not hide it."""
        self.a_guard_and_its_older_test()
        (self.repo / 'tests/test_calc.py').write_text(
            OLD_TEST + 'import pytest\n\n\nclass TestCalc:\n'
            '    @pytest.mark.parametrize("v", [7])\n'
            '    def test_calc_new(self, v): assert LIMIT == v\n')
        self.commit('a correction whose own test is a parametrized method')
        directory = Path(self.flow('status')['directory'])
        self.guard_matrix()
        record = json.loads((directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')).read_text())
        self.assertIn('tests/test_calc.py::TestCalc::test_calc_new[7]', record['results'][0]['nodes'])
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_suite_the_matrix_cannot_run_is_not_asked_for_a_matrix(self):
        """Found by a reviewer: a test path is any repository's, while the matrix runs pytest,
        so on a project whose suite is Jest or Cargo the record demanded could never be
        produced and the correction was blocked for good. What pytest collects no test from
        is not a gate this can mutate."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'src/__tests__').mkdir(parents=True, exist_ok=True)
        (self.repo / 'src/__tests__/widget.test.ts').write_text('it("holds", () => expect(1).toBe(1));\n')
        self.commit('a correction that changes a test this runtime cannot run')
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_file_pytest_collects_no_test_from_is_not_asked_for_a_case(self):
        """A conftest, a fixture and a helper module are test paths the scope rule counts as
        part of the correction, and no matrix can ever name a case that ran in one: asking was
        a refusal nobody could satisfy. Asked of pytest, not guessed from the name — a helper
        may define a test-shaped function pytest never collects."""
        self.a_guard_and_its_older_test()
        (self.repo / 'tests/conftest.py').write_text('import pytest\n\n\n@pytest.fixture\ndef spare(): return 1\n')
        (self.repo / 'tests/helpers.py').write_text('def build(v): return v\n\n\ndef test_added(): assert 1\n')
        (self.repo / 'tests/fixtures.json').parent.mkdir(exist_ok=True)
        (self.repo / 'tests/fixtures.json').write_text('{"v": 1}\n')
        self.commit('a correction that repairs a fixture the tests share')
        self.guard_matrix()
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_test_a_merge_carried_in_is_named_to_both_reviewers(self):
        """Refusing on a test the runtime cannot attribute was wrong in both directions: it
        fired on an ordinary merge of the base branch, and it stayed quiet when the correction
        had changed a test of its own, which is the shape it was written for. A carried test is
        exactly as unattributable either way, so it is named rather than enforced, because the
        diff shown beside it holds those files."""
        self.a_guard_and_its_older_test()
        run = lambda *args: subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                                           capture_output=True)
        run('checkout', '-q', '-b', 'topic')
        (self.repo / 'tests/test_topic.py').write_text('def test_topic(): assert 1\n')
        self.commit('a test on a side branch')
        run('checkout', '-q', '-')
        run('merge', '-q', '--no-ff', '--no-edit', 'topic')
        # And the correction changes a test of its own, which is the half that stayed silent.
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST + 'def test_calc_new(): assert LIMIT == 7\n')
        self.commit('a correction that also changes a test of its own')
        self.guard_matrix()
        state = self.start(correction=True, reason='')
        self.assertEqual(state['regression_tests'], ['tests/test_calc.py'])
        self.checks()
        said = self.flow('prompt').stdout
        self.assertIn('Tests changed in this delta: tests/test_calc.py', said)
        self.assertIn('tests/test_topic.py', said)
        self.assertIn('nothing here can say whose work it is', said)

    def test_a_conftest_that_fails_before_collection_answers_nothing(self):
        """Found by a reviewer: a conftest that will not import makes pytest write the captured
        output of the module that failed and stop before collecting anything. A run that never
        reached collection answers nothing, and a directory like that has nothing the matrix
        could measure."""
        (self.repo / 'guard.py').write_text('LIMIT = 7\n')
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST)
        (self.repo / 'tests/conftest.py').write_text(
            'print("tests/helpers.py::test_shape")\nimport totally_absent_dependency\n')
        self.commit('a guard, its test, and a conftest that will not import')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/helpers.py').write_text('def build(v): return v\n')
        self.commit('a correction that changes a helper the conftest names')
        said = self.start(correction=True, reason='', ok=False)
        self.assertIn('pytest could not say whether', said.stdout + said.stderr)

    def test_a_neighbour_that_prints_a_node_id_while_failing_names_nothing(self):
        """Filed by both reviewers, then reopened by one of them: every line holding `::` was
        read as a node id, and pytest replays what a module printed while it failed to import —
        after its report banner from a module beside the tests, and ahead of every real id from
        a conftest BELOW them. The ids come from pytest's own collection now, so a print cannot
        be one."""
        (self.repo / 'guard.py').write_text('LIMIT = 7\n')
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST)
        (self.repo / 'tests/sub').mkdir(exist_ok=True)
        (self.repo / 'tests/sub/test_sub.py').write_text('def test_sub(): assert 1\n')
        (self.repo / 'tests/sub/conftest.py').write_text(
            'print("tests/helpers.py::test_shape")\nimport totally_absent_dependency\n')
        self.commit('a guard, its test, and a conftest below them that prints while it fails')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/helpers.py').write_text('def build(v): return v\n\n\ndef test_shape(v): assert v\n')
        self.commit('a correction that changes a helper the neighbour names')
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_changed_test_git_quotes_is_still_a_changed_test(self):
        """Git quotes a path it prints one to a line, so tests/test_café.py came back as
        "tests/test_caf\\303\\251.py", matched no file, and the correction read as testless: the
        matrix was never demanded. Read NUL-separated, the path is itself and the gate holds."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_café.py').write_text(TEST_G)
        self.commit('a correction whose test git quotes')
        said = self.start(correction=True, reason='', ok=False)
        self.assertIn('no measured mutation matrix exists', said.stdout + said.stderr)

    def test_a_neighbour_that_cannot_be_collected_does_not_refuse_the_round(self):
        """Both reviewers found this case missing: rewriting the block between two markers had
        deleted it. It puts a broken neighbour beside a CHANGED TEST, which is where asking the
        directory a second time changes an answer. The directory is what pytest is asked about,
        so a neighbour with a broken import stopped it answering and the round was refused for
        a test that is not implicated."""
        (self.repo / 'guard.py').write_text('LIMIT = 7\n')
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST)
        (self.repo / 'tests/test_absent.py').write_text('import totally_absent_dependency\n')
        self.commit('a guard, its test, and a neighbour whose import is not installed')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST + 'def test_calc_new(): assert LIMIT == 7\n')
        self.commit('a correction beside it')
        # Still demanded, which is what says the gate is live rather than merely unrefused.
        said = self.start(correction=True, reason='', ok=False)
        self.assertIn('no measured mutation matrix exists', said.stdout + said.stderr)
        self.matrix('tests/test_calc.py', [('LIMIT = 7', 'LIMIT = 8', 'test_calc')],
                    where='guard.py', enumeration='echo 1')
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_helper_beside_a_broken_neighbour_is_still_not_asked_for_a_case(self):
        """The other side of asking the directory again: a helper is not a test because the
        directory says so, and a neighbour that cannot be imported must not turn that into
        "this file is what failed". Answered the second way, every helper in a directory with
        one broken file would refuse the round."""
        (self.repo / 'guard.py').write_text('LIMIT = 7\n')
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST)
        (self.repo / 'tests/test_absent.py').write_text('import totally_absent_dependency\n')
        self.commit('a guard, its test, and a neighbour whose import is not installed')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/helpers.py').write_text('def build(v): return v\n\n\ndef test_shape(v): assert v\n')
        self.commit('a correction that changes a helper the tests share')
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_collect_that_cannot_answer_refuses_instead_of_skipping_the_gate(self):
        """Found by a reviewer: a collect that errors was read as "no test here", which emptied
        the list the gate is scoped by and returned before the gate demanded anything. A
        conftest that will not import anywhere near a changed test then skipped the one check
        this delivery exists for, in silence. It is refused by name instead."""
        self.a_guard_and_its_older_test()
        (self.repo / 'tests/conftest.py').write_text('import nothing_that_exists\n')
        self.commit('a correction whose test directory no longer collects')
        said = self.start(correction=True, reason='', ok=False)
        self.assertIn('pytest could not say whether', said.stdout + said.stderr)

    def test_a_test_the_correction_added_is_what_must_have_caught(self):
        """What a correction adds is a gate it asserts, and which tests it added is asked of
        pytest on both sides — what it names here and does not name at the base. A test
        pytest skips is not asked for: it can never be among those that failed. What the
        base already held is not asked for either, however little it discriminates — the
        vacuous neighbour here is the correction's to answer for only if the correction wrote it."""
        (self.repo / 'guard.py').write_text('LIMIT = 7\n')
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_calc.py').write_text(OLD_TEST + 'def test_calc_quiet(): assert True\n')
        self.commit('a guard, the test that discriminates it and a vacuous neighbour')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/test_calc.py').write_text(
            OLD_TEST + 'def test_calc_quiet(): assert True\n'
            'import pytest\n\n\n@pytest.mark.skip\ndef test_calc_skipped(): assert LIMIT == 7\n')
        self.commit('a correction that adds a test pytest skips')
        self.guard_matrix()
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/test_calc.py').write_text(
            OLD_TEST + 'def test_calc_quiet(): assert True\ndef test_calc_new(): assert True\n')
        self.commit('a correction that adds a vacuous test beside the older one')
        self.guard_matrix()
        self.assertIn('caught nothing with tests/test_calc.py::test_calc_new',
                      self.start(ok=False, correction=True, reason='').stderr)
        # And the matrix's own selector is not the exemption: a case that names only the
        # older test leaves the added one unrun by the matrix, and it is still asked for.
        self.matrix('tests', [('LIMIT = 7', 'LIMIT = 8', 'test_calc_old')],
                    where='guard.py', enumeration='echo 1')
        self.assertIn('caught nothing with tests/test_calc.py::test_calc_new',
                      self.start(ok=False, correction=True, reason='').stderr)

    def test_every_parameter_the_correction_added_must_catch(self):
        """Found by the PR review: a parameter a correction added to an older parametrized test
        was credited by the parameter beside it, because the node ids lost their parameters
        before they were compared. Each added node is asked for by its whole id."""
        (self.repo / 'guard.py').write_text('LIMIT = 7\n')
        (self.repo / 'tests').mkdir(exist_ok=True)
        kinds = (OLD_TEST + 'import pytest\n\n\n@pytest.mark.parametrize("kind", ["strict"%s])\n'
                 'def test_calc_kinds(kind): assert LIMIT == 7 or kind == "loose"\n')
        (self.repo / 'tests/test_calc.py').write_text(kinds % '')
        self.commit('a guard and a parametrized test that discriminates it')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/test_calc.py').write_text(kinds % ', "loose"')
        self.commit('a correction that adds a vacuous parameter to the older test')
        self.guard_matrix()
        self.assertIn('caught nothing with tests/test_calc.py::test_calc_kinds[loose]',
                      self.start(ok=False, correction=True, reason='').stderr)

    def test_every_test_the_delta_changed_must_catch_not_one_of_them(self):
        """Found by a reviewer: the demand was an intersection, so one test that caught
        carried every other — a correction adding a test that discriminates, in the commit
        that adds a vacuous one beside it, was credited by the first."""
        self.a_guard_and_its_older_test()
        (self.repo / 'tests/test_calc.py').write_text(
            OLD_TEST + 'def test_calc_two(): assert LIMIT == 7\n\n\ndef test_calc_new(): assert True\n')
        self.commit('a correction that adds a discriminating test and a vacuous one')
        self.guard_matrix()
        self.assertIn('caught nothing with tests/test_calc.py::test_calc_new',
                      self.start(ok=False, correction=True, reason='').stderr)

    def test_the_runtime_runs_pytest_without_the_project_addopts(self):
        """Found by a reviewer: a project's addopts reached every pytest the runtime starts, so
        the project decided what the matrix ran and what it read back. An addopts that collects
        instead of running leaves every mutant uncaught while the tree looks green.
        PYTEST_ADDOPTS in the environment is the same option by another door."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'pytest.ini').write_text('[pytest]\naddopts = --collect-only\n')
        os.environ['PYTEST_ADDOPTS'] = '-qq'
        self.addCleanup(os.environ.pop, 'PYTEST_ADDOPTS', None)
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_g.py').write_text(TEST_G)
        self.commit('a correction that changes a test, under a project that sets addopts')
        self.matrix('tests/test_g.py', [('ONE = 1', 'ONE = 2', 'test_g')], where='values.py', enumeration='echo 1')
        directory = Path(self.flow('status')['directory'])
        record = json.loads((directory / ('matrix-' + self.git('rev-parse', 'HEAD') + '.json')).read_text())
        self.assertEqual(record['tests'], {'tests/test_g.py': ['test_g']})
        self.assertTrue(all(r['caught'] for r in record['results']))
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_correction_that_changes_no_test_needs_no_matrix(self):
        """The scope, asserted: a correction with no gate to mutate is exempt, and saying so
        here keeps the exemption from widening unnoticed."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        self.commit('a correction that changes no test')
        self.assertEqual(self.start(correction=True)['round'], 2)


if __name__ == '__main__':
    unittest.main()
