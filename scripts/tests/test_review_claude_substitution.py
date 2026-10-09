"""Regression layer: quota-bound reciprocal substitution still requires two complete reviews."""
import json
import sys
import time
import unittest
from unittest import mock

from test_review_flow import FLOW, FlowBench
sys.path.insert(0, str(FLOW.parent))
import review_flow
import review_prepush


class ClaudeSubstitutionTests(FlowBench):
    """Isolated campaigns admit Codex's second pass only on this candidate's quota evidence."""

    def quota(self, **changes):
        """Build current runtime-shaped evidence against the installed Claude binary."""
        value = dict(reason='quota', at=int(time.time()), binary=review_prepush.resolve_claude(),
                     head=self.git('rev-parse', 'HEAD'), round=1)
        value.update(changes)
        return value

    def test_required_pair_and_rejected_evidence(self):
        """Expired, wrong-binary/head/round and nonquota evidence cannot replace Claude."""
        state = dict(head=self.git('rev-parse', 'HEAD'), round=1, reviews={'codex': {}, 'codex-b': {}})
        with mock.patch.object(review_prepush, 'resolve_claude', return_value='/fixture/claude'):
            good = self.quota(binary='/fixture/claude')
            self.assertTrue(review_prepush.satisfied(dict(state, claude_waiver=good)))
            for changes in ({'at': time.time()-review_prepush.WAIVER_TTL-1}, {'at': time.time()+7200},
                            {'binary': '/another/claude'}, {'head': 'another'}, {'round': 2},
                            {'reason': 'auth'}, {'reason': 'absent'}, {'at': True}):
                broken = dict(state, claude_waiver=dict(good, **changes))
                self.assertFalse(review_prepush.satisfied(broken))
            self.assertFalse(review_prepush.satisfied(state))
            one = dict(state, claude_waiver=good, reviews={'codex': {}})
            self.assertFalse(review_prepush.satisfied(one))

    def test_both_unavailable_never_accepts_a_substitute_pair(self):
        """No pair can complete by waiving both providers at the same time."""
        with mock.patch.object(review_prepush, 'resolve_claude', return_value='/fixture/claude'), \
                mock.patch.object(review_prepush, 'resolve_codex', return_value='/fixture/codex'):
            state = dict(head=self.git('rev-parse', 'HEAD'), round=1,
                         claude_waiver=self.quota(binary='/fixture/claude'),
                         codex_waiver=dict(reason='quota', at=time.time(), binary='/fixture/codex'),
                         reviews={'codex': {}, 'codex-b': {}, 'claude-b': {}})
            self.assertFalse(review_prepush.satisfied(state))
            with self.assertRaises(ValueError):
                review_flow.substitute_allowed(state, 'codex-b')
            with self.assertRaises(ValueError):
                review_flow.substitute_allowed(state, 'claude-b')

    def test_campaign_records_distinct_reports_and_clears_exact_head(self):
        """Two matching complete Codex reports clear, while a missing second pass refuses finish."""
        self.start()
        self.checks()
        path = next((self.repo / '.git/bymax-review').glob('*/state.json'))
        state = json.loads(path.read_text())
        state['claude_waiver'] = self.quota()
        path.write_text(json.dumps(state))
        head = self.git('rev-parse', 'HEAD')
        report = self.root / 'report.json'
        report.write_text(json.dumps(dict(status='completed', head=head, base=self.base,
                                         summary='independent fixture review', findings=[])))
        self.flow('record', '--reviewer', 'codex', '--report', str(report))
        self.flow('finish', ok=False)
        self.flow('record', '--reviewer', 'codex-b', '--report', str(report))
        triage = self.root / 'triage.json'
        triage.write_text('[]')
        self.flow('triage', '--report', str(triage))
        final = self.flow('finish')
        self.assertTrue(final['cleared'])
        self.assertEqual(set(final['reviews']), {'codex', 'codex-b'})


    def test_substitute_cli_is_fresh_readonly_and_has_separate_attempts(self):
        """A quota-bound second pass uses a fresh process and its own artifact, not the primary report."""
        self.start()
        self.checks()
        path = next((self.repo / '.git/bymax-review').glob('*/state.json'))
        state = json.loads(path.read_text())
        state['claude_waiver'] = self.quota()
        path.write_text(json.dumps(state))
        head = self.git('rev-parse', 'HEAD')
        script = ("#!" + sys.executable + "\nimport sys,json\nfrom pathlib import Path\n"
                  "args=sys.argv[1:]\nassert '--ephemeral' in args and 'read-only' in args\n"
                  "assert 'codex-b-' in args[args.index('--output-last-message')+1]\n"
                  "Path(args[args.index('--output-last-message')+1]).write_text(json.dumps(" + repr(dict(
                      status='completed', head=head, base=self.base, summary='fresh second fixture pass', findings=[])) + "))\n")
        binary = self.fake_codex(script)
        self.locations = (binary,)
        result = self.flow('codex', '--as', 'codex-b')
        self.assertEqual(result['codex_b_attempts'], 1)
        self.assertNotIn('codex_attempts', result)
        self.assertEqual(set(result['reviews']), {'codex-b'})
        self.assertFalse(result['cleared'])


if __name__ == '__main__':
    unittest.main()
