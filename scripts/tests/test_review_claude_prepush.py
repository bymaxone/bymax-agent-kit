"""Git receipt boundary: Claude quota never lowers the requirement to one reviewer."""
import time
import unittest
from test_review_prepush import PrePushBench


class ClaudeQuotaPushTests(PrePushBench):
    """Only isolated local bare remotes receive these fixture commits."""

    def test_actual_hook_accepts_pair_and_rejects_missing_stale_wrong_head_evidence(self):
        """The installed hook checks current evidence, both reports and the exact transmitted SHA."""
        prepush = self.modules()['review_prepush']
        binary = prepush.resolve_claude()
        self.assertIsNotNone(binary, 'Fixture requires the installed Claude CLI path, never execution.')
        passed = self.dangling('two Codex reviews')
        waiver = dict(reason='quota', at=int(time.time()), binary=binary, head=passed, round=1)
        self.receipt(passed, reviews={'codex': {}, 'codex-b': {}}, claude_waiver=waiver, round=1)
        self.assertEqual(self.attempt(f'git push origin {passed}:refs/heads/quota-fixture').returncode, 0)
        self.assertTrue(self.remote_has(passed))
        cases = [('one', {'codex': {}}, {}),
                 ('unwaived', {'codex': {}, 'codex-b': {}}, None),
                 ('stale', {'codex': {}, 'codex-b': {}}, {'at': time.time()-prepush.WAIVER_TTL-1}),
                 ('wrong-head', {'codex': {}, 'codex-b': {}}, {'head': passed}),
                 ('wrong-round', {'codex': {}, 'codex-b': {}}, {'round': 2})]
        for label, reviews, change in cases:
            with self.subTest(label=label):
                sha = self.dangling(label)
                evidence = dict(waiver, head=sha, **(change or {})) if not (change and 'head' in change) else dict(waiver, **change)
                extra = {} if change is None else {'claude_waiver': evidence}
                self.receipt(sha, reviews=reviews, round=1, **extra)
                self.assertNotEqual(self.attempt(f'git push origin {sha}:refs/heads/{label}').returncode, 0)
                self.assertFalse(self.remote_has(sha))


if __name__ == '__main__':
    unittest.main()
