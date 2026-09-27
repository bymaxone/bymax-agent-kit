"""The reviewer adapters' attempt budget: what spends an attempt, and what may not. Driven through
the command line in a fixture repository, with the runtime patched in the process that runs it."""
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FLOW, FlowBench


class AttemptTests(FlowBench):
    """A refusal while the task is being built is not a review that failed."""

    def refused_while_building(self, reviewer, locations=(), body=None):
        """Run one adapter in a process whose prompt() refuses, as a collect that fails the second
        time it is asked does: the gates themselves have passed."""
        body = body or '    raise ValueError("the collect failed the second time it was asked")\n'
        script = ('import sys; sys.path.insert(0, %r)\n'
                  'import review_prepush; review_prepush.CODEX_LOCATIONS = %r\n'
                  'import review_flow\n'
                  'def refuse(*args, **kwargs):\n%s'
                  'review_flow.prompt = refuse\n'
                  'sys.argv = ["review_flow.py", %r]\n'
                  'review_flow.cli()\n' % (str(FLOW.parent), tuple(str(p) for p in locations), body, reviewer))
        # Outside a Claude session, as the adapter refuses to nest one.
        env = {key: value for key, value in self.codex_env().items() if key != 'CLAUDECODE'}
        return subprocess.run([sys.executable, '-c', script], cwd=self.repo, env=env,
                              capture_output=True, text=True, timeout=60)

    def test_a_task_that_cannot_be_built_spends_no_attempt(self):
        """Both adapters reserved the attempt and then built the task, whose prompt() runs the
        gates again: a collect that failed that second time spent an attempt on a review nobody
        ran, and enough of them spent the candidate's budget."""
        binary = self.fake_codex('#!/bin/sh\nexit 0\n')
        self.start()
        self.checks()
        for reviewer, locations in (('claude', ()), ('codex', (binary,))):
            with self.subTest(reviewer=reviewer):
                refused = self.refused_while_building(reviewer, locations)
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertIn('the collect failed the second time', refused.stderr)
                self.assertEqual(self.flow('status').get(reviewer + '_attempts', 0), 0)


    def test_a_gate_that_ran_while_the_task_was_built_spends_no_attempt(self):
        """A check that fails after the task is built and before the attempt is reserved left a
        review running on a task that says every gate passed, and spent the attempt."""
        binary = self.fake_codex('#!/bin/sh\nexit 0\n')
        self.start()
        self.checks()
        body = ('    directory = review_flow.location()\n'
                '    with review_flow.locked(directory):\n'
                '        state = review_flow.read_state(directory)\n'
                '        state["checks"].append(dict(command=["false"], exit_code=1, log="late"))\n'
                '        review_flow.save(directory, state)\n'
                '    return "the task"\n')
        for reviewer, locations in (('claude', ()), ('codex', (binary,))):
            with self.subTest(reviewer=reviewer):
                refused = self.refused_while_building(reviewer, locations, body)
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertIn('a gate ran while this review was being prepared', refused.stderr)
                self.assertEqual(self.flow('status').get(reviewer + '_attempts', 0), 0)
            # The late failure is this subtest's; the next reviewer starts from passing gates.
            subprocess.run([sys.executable, '-c', 'import sys; sys.path.insert(0, %r)\nimport review_flow\n'
                            'd = review_flow.location()\ns = review_flow.read_state(d)\n'
                            's["checks"] = [c for c in s["checks"] if c["log"] != "late"]\n'
                            'review_flow.save(d, s)\n' % str(FLOW.parent)], cwd=self.repo, check=True)

class CodexStdinTests(unittest.TestCase):
    """What the Codex pass is handed on stdin."""

    def test_a_name_that_is_not_utf8_reaches_codex_as_valid_utf8(self):
        """Codex refuses stdin that is not valid UTF-8 before any model reads it, so a task
        carrying a surrogate-escaped name goes with the byte spelled out."""
        sys.path.insert(0, str(FLOW.parent))
        import review_flow
        seen = {}

        def run(command, **kwargs):
            seen.update(kwargs)
            return subprocess.CompletedProcess(command, 1)
        with tempfile.TemporaryDirectory() as box, \
                mock.patch.object(review_flow.subprocess, 'run', run), \
                mock.patch.object(review_flow, 'codex_outcome', lambda *args: None), \
                mock.patch.object(review_flow, 'escalation', lambda state: []):
            review_flow.run_codex(Path(box), {'round': 1, 'codex_attempts': 0},
                                  'tests/test_caf\udce9.py', 'codex', None)
        self.assertEqual(seen['input'].encode(seen.get('encoding') or 'ascii'), b'tests/test_caf\\xe9.py')


if __name__ == '__main__':
    unittest.main()
