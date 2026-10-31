"""Regression layer: a reviewed candidate whose branch was rebased onto a moved base continues its
campaign. The same delta keeps its reviews and reruns its gates; a changed delta is reviewed again
in full; anything that is not a rebase of the frozen candidate is refused."""
import json
from pathlib import Path
import sys
import unittest

# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FlowBench


class RebaseTests(FlowBench):
    """What start --rebased-from does with a candidate rebased after its campaign froze."""

    def move_base(self):
        """Advance the branch the work merges into with an unrelated commit, rebase the candidate
        onto it, and return (frozen head, new base)."""
        frozen, branch = self.git('rev-parse', 'HEAD'), self.git('rev-parse', '--abbrev-ref', 'HEAD')
        self.git('checkout', '-q', '-b', 'upstream', self.base)
        (self.repo / 'other.txt').write_text('merged meanwhile\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'unrelated work merged meanwhile')
        moved = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-q', branch)
        self.git('rebase', '-q', 'upstream')
        return frozen, moved

    def rebase_start(self, frozen, base, ok=True):
        """start on the rebased head, keeping the frozen context."""
        return self.flow('start', '--autonomous', '--base', base, '--rebased-from', frozen, ok=ok)

    def cleared(self):
        """A delivery whose first candidate both reviewers read and the gates passed."""
        self.start(autonomous=True)
        self.complete()

    def test_a_rebase_keeping_the_delta_keeps_its_reviews_and_reruns_the_gates(self):
        """A conflict-free rebase is the same change on a newer base: the reports still describe
        it, the gates must run on the new tree, and the push of the rebased head is cleared."""
        self.cleared()
        used = self.flow('status')['delivery_used']
        frozen, moved = self.move_base()
        state = self.rebase_start(frozen, moved)
        self.assertTrue(state['rebased']['same_delta'])
        self.assertEqual((state['base'], state['round'], state['checks'], state['cleared']), (moved, 1, [], False))
        self.assertEqual(sorted(state['reviews']), ['claude', 'codex'])
        self.assertEqual(state['delivery_used'], used)
        self.flow('finish', ok=False)
        self.checks()
        self.assertTrue(self.flow('finish')['cleared'])
        self.push('git push origin HEAD:feature')

    def test_a_rebind_leaves_the_frozen_candidates_gate_logs_alone(self):
        """The rebound head keeps the round and starts its gates from none, and its first log
        took the frozen candidate's file name, overwriting the evidence its receipt points to."""
        self.cleared()
        frozen_log = Path(self.flow('status')['checks'][-1]['log'])
        before = frozen_log.read_text()
        frozen, moved = self.move_base()
        self.rebase_start(frozen, moved)
        self.checks()
        rebound_log = Path(self.flow('status')['checks'][-1]['log'])
        self.assertNotEqual(rebound_log, frozen_log)
        self.assertEqual(frozen_log.read_text(), before)

    def test_a_rebase_that_changed_the_delta_is_reviewed_again_in_full(self):
        """A rebase whose result differs from what was read is new code: both reviews again, from
        the new base, as the next round of the same delivery."""
        self.cleared()
        frozen, moved = self.move_base()
        (self.repo / 'code.txt').write_text('resolved differently\n')
        self.git('commit', '-qam', 'resolved differently')
        state = self.rebase_start(frozen, moved)
        self.assertFalse(state['rebased']['same_delta'])
        self.assertEqual((state['round'], state['review_base'], state['reviews']), (2, moved, {}))
        self.checks()
        self.flow('finish', ok=False)

    def test_what_is_not_a_rebase_of_the_frozen_candidate_is_refused(self):
        """A descendant is a correction, and a head the campaign never froze is not this campaign's."""
        self.cleared()
        frozen = self.git('rev-parse', 'HEAD')
        self.commit('a correction on top')
        self.assertIn('is a correction, not a rebase', self.rebase_start(frozen, self.base, ok=False).stderr)
        self.git('reset', '-q', '--hard', frozen)
        _, moved = self.move_base()
        refused = self.rebase_start(self.base, moved, ok=False).stderr
        self.assertIn('Name the head the campaign froze', refused)

    def test_the_prose_pass_after_a_rebase_reads_from_the_named_base(self):
        """The frozen head is no ancestor of a rebased one, so the delta since it is meaningless."""
        self.cleared()
        frozen, moved = self.move_base()
        refused = self.flow('prose', '--stage', 'prepare', ok=False).stderr
        self.assertIn('branch was rebased', refused)


if __name__ == '__main__':
    unittest.main()
