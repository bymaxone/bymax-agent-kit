"""Regression layer: a declared gate that turns out wrong can be corrected, on the record.

The scope guards compare a context's `checks` with the campaign's and the delivery ledger's, so
a gate declared over a file the scope itself deletes could never be corrected: archiving the
campaign and starting again with --after-archived reached the ledger, which kept the original
gates and answered "new work needs a new branch". --correct-checks "<why>" lets the gates, and
nothing else, differ; it spends no less of the budget and leaves an entry the reviewers read.
"""
import json
from pathlib import Path
import sys
import unittest

# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FlowBench

STALE = [[sys.executable, 'scripts/removed_gate.py']]
REASON = 'fixture: the declared gate ran a script this scope deletes; the suite replaces it'


class ChecksCorrectionTests(FlowBench):
    """What --correct-checks accepts, what it refuses, and what it leaves behind."""

    def setUp(self):
        """Freeze a candidate whose declared gate runs a script the tree no longer holds."""
        super().setUp()
        self.good = json.loads(self.context.read_text())['checks']
        self.declare(STALE)

    def declare(self, checks, **fields):
        """Rewrite the fixture context with these gates and any other changed fields."""
        data = json.loads(self.context.read_text())
        data.update(checks=checks, **fields)
        self.context.write_text(json.dumps(data))

    def ledger(self):
        """The delivery ledger of this branch's campaign."""
        directory = Path(self.flow('status')['directory'])
        return json.loads((directory.parent / 'deliveries' / (directory.name + '.json')).read_text())

    def keep_aside(self):
        """Rename the campaign directory the way the recovery messages ask, and return it."""
        directory = Path(self.flow('status')['directory'])
        directory.rename(directory.with_name(directory.name + '.archived'))
        return directory

    def failed_delivery(self):
        """An enrolled delivery whose only declared gate fails on the frozen candidate."""
        self.start(autonomous=True)
        self.flow('check', '--', *STALE[0], ok=False)
        used = self.ledger()['used']
        self.keep_aside()
        self.declare(self.good)
        return used

    def start_correcting(self, reason=REASON, ok=True, extra=()):
        """`start` on the corrected context with the recorded correction."""
        return self.flow('start', '--base', self.base, '--context', str(self.context), *extra,
                         '--correct-checks', reason, ok=ok)

    def test_the_ledger_refused_a_corrected_gate_after_the_campaign_was_kept_aside(self):
        """The reported shape: kept aside and restarted with --after-archived, the ledger still
        held the deleted gate and refused the corrected one as a scope change."""
        self.failed_delivery()
        refused = self.flow('start', '--base', self.base, '--context', str(self.context),
                            '--after-archived', 'fixture: Max authorised a restart', ok=False).stderr
        self.assertIn('Delivery scope changed', refused)
        self.assertIn('--correct-checks', refused)

    def test_a_recorded_correction_restarts_without_resetting_the_budget(self):
        """The correction is accepted, the ledger keeps its count and gains an audit entry, and
        the ledger's gates become the corrected ones so the next start needs no flag."""
        used = self.failed_delivery()
        state = self.start_correcting(extra=('--after-archived', 'fixture: Max authorised a restart'))
        ledger = self.ledger()
        self.assertGreaterEqual(ledger['used'], used)
        self.assertEqual(state['delivery_used'], ledger['used'])
        entry = ledger['check_corrections'][-1]
        self.assertEqual(entry['reason'], REASON)
        self.assertEqual(entry['before'], STALE)
        self.assertEqual(entry['after'], self.good)
        self.assertEqual(entry['head'], state['head'])
        self.assertEqual(state['required_checks'], self.good)
        self.assertEqual(state['checks_corrected']['reason'], REASON)
        self.assertEqual(json.loads(ledger['context'])['checks'], self.good)
        # Told to both reviewers, with what changed.
        self.checks()
        task = self.text('prompt')
        self.assertIn('declared gates were corrected', task)
        self.assertIn(REASON, task)

    def test_a_correction_changes_the_gates_and_nothing_else(self):
        """The flag narrows one comparison: an intent, scope or base change is still refused."""
        self.failed_delivery()
        self.declare(self.good, intent='Something else entirely')
        refused = self.start_correcting(ok=False, extra=('--after-archived', 'x')).stderr
        self.assertIn('Delivery scope changed', refused)

    def test_a_correction_needs_a_reason_and_a_change(self):
        """An empty reason is no record, and gates identical to the recorded ones correct
        nothing; neither is written."""
        self.failed_delivery()
        self.assertIn('needs a reason', self.start_correcting(reason=' ', ok=False,
                                                              extra=('--after-archived', 'x')).stderr)
        self.declare(STALE)
        self.assertIn('nothing to correct', self.start_correcting(ok=False,
                                                                  extra=('--after-archived', 'x')).stderr)

    def test_a_live_campaign_corrects_its_gates_on_the_next_head(self):
        """Without archiving: the candidate the stale gate failed is replaced in its round by a
        new head, and the corrected gates are the ones it must pass."""
        first = self.start()
        self.flow('check', '--', *STALE[0], ok=False)
        self.git('commit', '-q', '--allow-empty', '-m', 'same tree, corrected gate')
        self.declare(self.good)
        self.assertIn('Scope changed', self.start(ok=False).stderr)
        state = self.start_correcting()
        self.assertEqual(state['round'], first['round'])
        self.assertEqual(state['replaced'], [first['head']])
        self.assertEqual(state['required_checks'], self.good)
        self.assertEqual(state['checks_corrected']['before'], STALE)

    def test_a_replacement_of_the_corrected_head_keeps_the_correction(self):
        """The corrected gate failed in turn and the next head replaced that candidate in its
        round: the replacement dropped the record, so the reviewers of the head they read were
        never told the gates had changed, and neither head could be flagged again."""
        self.start()
        self.flow('check', '--', *STALE[0], ok=False)
        self.git('commit', '-q', '--allow-empty', '-m', 'corrected gate')
        failing = [[sys.executable, '-c', 'raise SystemExit(1)']]
        self.declare(failing)
        self.start_correcting()
        self.flow('check', '--', *failing[0], ok=False)
        self.git('commit', '-q', '--allow-empty', '-m', 'fix what the corrected gate found')
        state = self.start()
        self.assertEqual(len(state['replaced']), 2)
        self.assertEqual(state['checks_corrected']['reason'], REASON)
        self.assertEqual(state['checks_corrected']['after'], failing)

    def test_the_frozen_candidate_cannot_change_its_gates_in_place(self):
        """On the head already frozen the failed run stays on the record, so the correction is
        refused there and says what to do instead."""
        self.start()
        self.declare(self.good)
        refused = self.start_correcting(ok=False).stderr
        self.assertIn('already frozen', refused)

    def test_a_first_campaign_has_no_gates_to_correct(self):
        """With no campaign and no delivery there is no recorded gate to differ from."""
        self.declare(self.good)
        self.assertIn('no declared gates to correct', self.start_correcting(ok=False).stderr)


if __name__ == '__main__':
    unittest.main()
