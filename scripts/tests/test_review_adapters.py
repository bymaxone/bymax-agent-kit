"""The reviewer adapters' attempt budget: what spends an attempt, and what may not. Driven through
the command line in a fixture repository, with the runtime patched in the process that runs it."""
import sys
import subprocess
import unittest
from pathlib import Path

# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FLOW, FlowBench


class AttemptTests(FlowBench):
    """A refusal while the task is being built is not a review that failed."""

    def refused_while_building(self, reviewer, locations=()):
        """Run one adapter in a process whose prompt() refuses, as a collect that fails the second
        time it is asked does: the gates themselves have passed."""
        script = ('import sys; sys.path.insert(0, %r)\n'
                  'import review_prepush; review_prepush.CODEX_LOCATIONS = %r\n'
                  'import review_flow\n'
                  'def refuse(*args, **kwargs):\n'
                  '    raise ValueError("the collect failed the second time it was asked")\n'
                  'review_flow.prompt = refuse\n'
                  'sys.argv = ["review_flow.py", %r]\n'
                  'review_flow.cli()\n' % (str(FLOW.parent), tuple(str(p) for p in locations), reviewer))
        # Outside a Claude session, as the adapter refuses to nest one.
        env = {key: value for key, value in self.codex_env().items() if key != 'CLAUDECODE'}
        return subprocess.run([sys.executable, '-c', script], cwd=self.repo, env=env,
                              capture_output=True, text=True, timeout=60)

    def test_a_task_that_cannot_be_built_spends_no_attempt(self):
        """Both adapters reserved the attempt and then built the task, whose prompt() runs the
        gates again: a collect that failed that second time spent an attempt on a review nobody
        ran, and two of them spent the candidate's budget."""
        binary = self.fake_codex('#!/bin/sh\nexit 0\n')
        self.start()
        self.checks()
        for reviewer, locations in (('claude', ()), ('codex', (binary,))):
            with self.subTest(reviewer=reviewer):
                refused = self.refused_while_building(reviewer, locations)
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertIn('the collect failed the second time', refused.stderr)
                self.assertEqual(self.flow('status').get(reviewer + '_attempts', 0), 0)


if __name__ == '__main__':
    unittest.main()
