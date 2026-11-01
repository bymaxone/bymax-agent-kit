"""Regression layer: a running gate does not hold the campaign lock.

`check` held the lock for the whole gate, up to CHECK_TIMEOUT, so `status`, `record` and a
reviewer's reservation waited behind a twenty-minute validator.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FLOW, FlowBench

SLOW = [sys.executable, '-c', 'import time; time.sleep(4)']


class CheckLockTests(FlowBench):
    """What the rest of the campaign can do while a declared gate runs."""

    def background_check(self, command):
        """Start `check -- command` in its own process and return it."""
        env = dict(os.environ, CODEX_HOME=str(self.home))
        return subprocess.Popen([sys.executable, str(FLOW), 'check', '--', *command], cwd=self.repo,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)

    def test_status_answers_while_a_gate_runs(self):
        """status returns well inside the gate's run time, and the gate's result is still recorded."""
        self.start()
        running = self.background_check(SLOW)
        self.addCleanup(running.kill)
        time.sleep(1)
        began = time.monotonic()
        self.flow('status')
        self.assertLess(time.monotonic() - began, 2.5)
        self.assertEqual(running.wait(timeout=30), 0, running.stderr.read())
        checks = self.flow('status')['checks']
        self.assertEqual([c['exit_code'] for c in checks], [0])

    def test_a_result_for_a_candidate_that_moved_on_is_not_recorded(self):
        """A gate that ran on one head must not mark the next head's run as passed."""
        self.start()
        running = self.background_check(SLOW)
        self.addCleanup(running.kill)
        time.sleep(1)
        path = Path(self.flow('status')['directory']) / 'state.json'
        state = json.loads(path.read_text())
        state['head'] = '0' * 40
        path.write_text(json.dumps(state))
        running.wait(timeout=30)
        self.assertIn('moved to another candidate', running.stderr.read())


if __name__ == '__main__':
    unittest.main()
