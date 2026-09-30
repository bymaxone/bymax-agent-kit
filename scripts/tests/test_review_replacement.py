"""Regression layer: a candidate whose declared gate failed before any reviewer read it is replaced
within its round, and every other candidate still needs both reviews before a new head."""
from pathlib import Path
import sys
import unittest

# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FlowBench

# The fixture context's one declared gate: code.txt must not be empty.
GATE = [sys.executable, '-c', 'from pathlib import Path; assert Path("code.txt").read_text()']


class ReplacementTests(FlowBench):
    """What start does with a new head while the frozen candidate has not been reviewed."""

    def red(self, message='a candidate its declared gate refuses'):
        """Commit a candidate the declared gate fails on and return its head."""
        (self.repo / 'code.txt').write_text('')
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def gate_fails(self):
        """Run the declared gate on the frozen candidate and watch it fail."""
        self.flow('check', '--', *GATE, ok=False)

    def correction_on_red(self):
        """A first round with an open blocking finding on code.txt, then a correction the gate
        refuses, frozen as round two; returns (round-one head, red head)."""
        first = self.start()['head']
        bug = dict(id='code.txt:content', kind='defect', priority='P1', evidence='code.txt is wrong')
        self.report('claude', [bug])
        self.report('codex')
        self.triage([dict(id='claude::code.txt:content', status='open', evidence='Reproduced')])
        red = self.red()
        state = self.start(correction=True)
        self.assertEqual((state['round'], state['review_base']), (2, first))
        self.gate_fails()
        return first, red

    def test_a_first_round_candidate_its_gate_failed_is_replaced_and_counted(self):
        """A first-round candidate whose gate failed is replaced by the fixed commit in round one,
        and a delivery counts it. prompt refuses to build a reviewer task for the failed
        candidate, so a start that demanded both reviews of it would leave archiving the
        campaign as the only exit."""
        red = self.red()
        self.assertEqual(self.start(autonomous=True)['delivery_used'], 1)
        self.gate_fails()
        self.commit('the gate passes now')
        state = self.start(autonomous=True)
        self.assertEqual((state['round'], state['review_base'], state['delivery_used']), (1, self.base, 2))
        self.assertEqual((state['replaced'], state['checks'], state['reviews']), ([red], [], {}))
        self.checks()
        self.assertIn('already ran on this candidate and passed', self.text('prompt'))

    def test_an_amended_candidate_replaces_the_one_its_gate_failed(self):
        """An amend rewrites the failed candidate rather than descending from it. No reviewer read
        what it rewrites, so it replaces that candidate rather than being refused as rewritten
        history."""
        red = self.red()
        self.start()
        self.gate_fails()
        (self.repo / 'code.txt').write_text('amended')
        self.git('commit', '-qa', '--amend', '--no-edit')
        state = self.start()
        self.assertEqual((state['round'], state['replaced']), (1, [red]))

    def test_a_correction_its_gate_failed_is_replaced_within_its_round(self):
        """A correction round whose gate failed is replaced within that round too, and the
        replacement still owes the correction contract measured from the same review base: its
        scope, its probe and its regression evidence."""
        first, red = self.correction_on_red()
        (self.repo / 'other.txt').write_text('a file no open finding names\n')
        self.commit('the correction, fixed, and a file beside it')
        widened = self.start(correction=True, ok=False).stderr
        self.assertIn('No open finding names: other.txt', widened)
        self.git('rm', '-q', 'other.txt')
        self.git('commit', '-qm', 'the correction, fixed')
        refused = self.flow('start', '--base', self.base, '--context', str(self.context), ok=False).stderr
        self.assertIn('--probe', refused)
        state = self.start(correction=True)
        self.assertEqual((state['round'], state['review_base'], state['replaced']), (2, first, [red]))
        self.assertEqual(state['previous_triage'][0]['id'], 'claude::code.txt:content')
        self.assertTrue(state['probe'])
        self.checks()
        self.assertIn('Round 2/', self.text('prompt'))

    def test_a_replacement_keeps_the_gate_log_of_the_candidate_it_replaced(self):
        """The failed head stays listed under `replaced`, so its gate log stays on disk as it
        was: the new candidate's first gate run writes a file of its own. A log named by round
        and check index alone would be the same file for both, and the new run would erase the
        failure the replacement cites."""
        self.red()
        self.start()
        self.gate_fails()
        failed = Path(self.flow('status')['checks'][0]['log'])
        failure = failed.read_text()
        self.assertIn('AssertionError', failure)
        self.commit('the gate passes now')
        self.start()
        self.checks()
        passed = Path(self.flow('status')['checks'][0]['log'])
        self.assertNotEqual(passed, failed)
        self.assertEqual(failed.read_text(), failure)

    def test_a_replacement_must_descend_from_the_review_base(self):
        """Unrelated history is not a fixed candidate: the delta reviewers read starts at the
        review base, so a head that does not descend from it has no delta to read."""
        first, _ = self.correction_on_red()
        self.git('reset', '-q', '--hard', self.base)
        self.commit('unrelated history')
        refused = self.start(correction=True, ok=False).stderr
        self.assertIn('does not descend from ' + first[:12], refused)

    def test_a_candidate_a_reviewer_has_read_is_not_replaced(self):
        """A reviewer's reading is spent on the candidate it read, so a red gate after it does
        not let a new head take its place: the round still needs both reviews."""
        self.red()
        self.start()
        self.report('claude')
        self.gate_fails()
        self.commit('the gate passes now')
        refused = self.start(correction=True, ok=False).stderr
        self.assertIn('Complete both reviews', refused)

    def test_a_candidate_whose_gate_passed_is_not_replaced(self):
        """Only a failed gate replaces a candidate; a green one is ready for its reviewers."""
        self.start()
        self.checks()
        self.commit('another head')
        refused = self.start(correction=True, ok=False).stderr
        self.assertIn('Complete both reviews', refused)

    def test_a_candidate_whose_gate_never_ran_is_not_replaced(self):
        """A gate nobody ran has not failed, so it cannot stand for a replacement's reason."""
        self.start()
        self.commit('another head')
        refused = self.start(correction=True, ok=False).stderr
        self.assertIn('Complete both reviews', refused)


if __name__ == '__main__':
    unittest.main()
