"""Regression layer: a gate command the runtime records must be one it can execute.

`check -- "pnpm test:cov"` hands the runtime ONE argument holding a space, and so does zsh for an
unquoted `$var`, which it does not split into words. The runtime recorded that argument as a
gate, the gate could never run, and its unfinished attempt kept every later step of the campaign
refused. These cases pin the refusal at record time, before anything is persisted.
"""
import json
import subprocess
from pathlib import Path
import sys
import unittest

# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import CAMPAIGN_TIMEOUT, FLOW, FlowBench

GATE = 'from pathlib import Path; assert Path("code.txt").read_text()'


class CheckCommandTests(FlowBench):
    """What `check` and a context's `checks` accept as a command."""

    def write_context(self, checks):
        """Replace the fixture context's gates, keeping every other field."""
        data = json.loads(self.context.read_text())
        data['checks'] = checks
        self.context.write_text(json.dumps(data))

    def test_a_command_passed_as_one_word_is_refused_and_nothing_is_recorded(self):
        """`check -- "pnpm test:cov"` reaches argv as one word. It was recorded as a gate that
        could never execute, and the campaign stayed refused from then on."""
        self.start()
        refused = self.flow('check', '--', sys.executable + ' -c pass', ok=False).stderr
        self.assertIn('one argument', refused)
        # The corrected spelling is in the message, word by word.
        self.assertIn('check -- ' + sys.executable + ' -c pass', refused)
        self.assertIn('${=', refused)
        self.assertEqual(self.flow('status')['checks'], [])

    def test_a_refused_command_does_not_poison_the_campaign(self):
        """After the refusal the declared gate still runs, and the reviewers can be handed the
        candidate: nothing about the refused attempt is left to fail later."""
        self.start()
        self.flow('check', '--', 'pnpm test:cov', ok=False)
        self.checks()
        self.assertIn('Review only', self.text('prompt'))

    def test_a_program_that_does_not_resolve_is_refused_before_it_is_recorded(self):
        """A gate whose script path was wrong froze a campaign the same way: its attempt never
        reported an exit status. A missing file and one that is not executable are both refused."""
        self.start()
        missing = self.flow('check', '--', './scripts/missing-gate.sh', ok=False).stderr
        self.assertIn('does not resolve', missing)
        self.assertIn('./scripts/missing-gate.sh', missing)
        plain = self.repo / 'not-executable.sh'
        plain.write_text('exit 0\n')
        self.flow('check', '--', str(plain), ok=False)
        self.assertEqual(self.flow('status')['checks'], [])

    def test_a_context_declaring_an_unsplit_gate_is_refused_at_start(self):
        """`checks` is also where the runtime records commands; a context declaring
        ["pnpm test:cov"] froze a candidate whose gate could never run."""
        self.write_context([['pnpm test:cov']])
        refused = self.start(ok=False).stderr
        self.assertIn('one argument', refused)
        self.assertIn('["pnpm", "test:cov"]', refused)
        self.assertIn('No review campaign', self.flow('status', ok=False).stderr)

    def test_a_context_declaring_a_gate_that_does_not_resolve_is_refused_at_start(self):
        """A declared gate over a script the tree does not hold can never pass."""
        self.write_context([[str(self.repo / 'scripts' / 'gone.sh')]])
        self.assertIn('does not resolve', self.start(ok=False).stderr)

    def test_a_program_name_with_a_space_that_resolves_is_still_accepted(self):
        """The refusal is about a program that cannot run, not about a space: an executable whose
        own path holds one is a single word and runs."""
        spaced = self.root / 'with space'
        spaced.mkdir()
        gate = spaced / 'gate'
        gate.write_text('#!/bin/sh\nexit 0\n')
        gate.chmod(0o755)
        self.write_context([[str(gate)]])
        self.start()
        self.flow('check', '--', str(gate))
        self.assertEqual(self.flow('status')['checks'][0]['exit_code'], 0)

    def test_a_context_gate_with_a_relative_path_is_read_from_the_worktree_root(self):
        """A context's gates are meant to run from the root, and `start` may be run from anywhere: a
        relative script path the root holds is accepted from a subdirectory."""
        script = self.repo / 'gate.sh'
        script.write_text('#!/bin/sh\nexit 0\n')
        script.chmod(0o755)
        self.git('add', 'gate.sh')
        self.git('commit', '-qm', 'gate')
        (self.repo / 'sub').mkdir()
        self.write_context([['./gate.sh']])
        result = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base, '--context',
                                 str(self.context)], cwd=self.repo / 'sub', capture_output=True, text=True,
                                timeout=CAMPAIGN_TIMEOUT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_fixture_gate_still_runs(self):
        """The ordinary argument list is unaffected."""
        self.start()
        self.flow('check', '--', sys.executable, '-c', GATE)
        self.assertEqual(self.flow('status')['checks'][0]['exit_code'], 0)


if __name__ == '__main__':
    unittest.main()
