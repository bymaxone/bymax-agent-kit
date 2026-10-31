"""Regression layer: every triaged round and every clearance is measured, and read back.

No mechanism of the campaign could be kept or retired on evidence while the only record of what
the reviewers caught was the campaign state each new round overwrote.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FlowBench

FINDING = dict(id='code.txt:content', kind='defect', priority='P1', evidence='code.txt is wrong')


class OutcomeTests(FlowBench):
    """What `outcomes` reports after campaigns triage and clear."""

    def test_a_triaged_round_and_its_clearance_are_read_back_per_reviewer(self):
        """One reviewer's rejected finding and the round the candidate cleared in."""
        self.start()
        self.report('claude', [FINDING])
        self.report('codex')
        self.triage([dict(id='claude::code.txt:content', status='rejected', evidence='Disproved by the fixture')])
        self.checks()
        self.flow('finish')
        summary = self.flow('outcomes')
        self.assertEqual((summary['triaged_rounds'], summary['cleared_candidates']), (1, 1))
        self.assertEqual(summary['rounds_to_clear'], {'1': 1})
        self.assertEqual(summary['reviewers'], {'claude': {'rejected': 1}, 'codex': {}})

    def test_a_branch_with_no_campaign_reports_nothing_measured(self):
        """No log is an empty measurement, never a refusal."""
        summary = self.flow('outcomes')
        self.assertEqual((summary['triaged_rounds'], summary['cleared_candidates']), (0, 0))


if __name__ == '__main__':
    unittest.main()
