"""Regression layer: the Codex pass through the command line — its attempt budget and
reservation, the lock a running pass holds, the waiver its own probe records for a Codex this
machine cannot run, and the rounds that escalate to a better reviewer."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FLOW, FlowBench


class CodexPassTests(FlowBench):
    """Drive `review_flow.py codex` against a stand-in Codex this test installs."""

    def test_abandoned_codex_reservation_keeps_retry_budget(self):
        """A dead owner permits one retry without resetting the attempt count."""
        state = self.start()
        self.checks()
        reserve = ('import sys; sys.path.insert(0, ' + repr(str(FLOW.parent)) + '); '
                   'import review_flow as flow, review_codex; review_codex.reserve_codex(flow.location(), flow)')
        subprocess.run([sys.executable, '-c', reserve], cwd=self.repo, check=True)
        binary = self.fake_codex('#!/bin/sh\nexit 1\n')
        result = self.codex_run('codex', locations=[binary])
        self.assertEqual(result.returncode, 2, result.stderr)
        # A run that fails without saying why is a review that did not happen, not a
        # reviewer this machine cannot run: it is never waived.
        self.assertIn('Codex failed', result.stderr)
        self.assertNotIn('codex_waiver', self.flow('status'))
        latest = self.flow('status')
        self.assertEqual(latest['codex_attempts'], 2)
        self.assertFalse(latest['codex_running'])
        self.assertEqual(latest['head'], state['head'])
        # The spent budget is asked against the Codex this test installed, not the one the
        # developer happens to have: with the attempts gone the runtime probes availability,
        # and a machine with no Codex answers `absent` and waives instead of refusing. That
        # difference is why this passed here and failed on a runner.
        self.locations = [binary]
        self.assertIn('budget exhausted', self.flow('codex', ok=False).stderr)

    def test_a_gate_refusal_does_not_spend_a_reviewer_attempt(self):
        """Both adapters reserved the attempt before building the task, and the gate raises from
        inside prompt(), which is only evaluated as the subprocess input. So a campaign whose
        gates had not run spent an attempt on a refusal no reviewer ever saw, and two of them
        exhausted the per-candidate budget with nothing read — after which execute_codex diverts
        to an availability probe and reports a spent budget for a reason Codex was never part of.
        The path is the old ordering, which every already-installed command file prescribes.
        """
        binary = self.fake_codex('#!/bin/sh\nexit 0\n')
        self.start()
        for _ in range(2):
            refused = self.codex_run('codex', locations=[binary])
            self.assertEqual(refused.returncode, 2, refused.stdout)
            self.assertIn('have not run on this candidate', refused.stderr)
        self.assertEqual(self.flow('status').get('codex_attempts', 0), 0)
        # And once the gates pass, the attempt is spent on an actual run.
        self.checks()
        self.codex_run('codex', locations=[binary])
        self.assertEqual(self.flow('status').get('codex_attempts', 0), 1)

    def test_codex_child_keeps_lock_after_launcher_is_killed(self):
        """An orphaned child excludes retries until it exits, then recovery is bounded."""
        self.start()
        self.checks()
        ready, release, done = [self.root / name for name in ('ready', 'release', 'done')]
        binary = self.fake_codex(f"#!{sys.executable}\nimport time,pathlib\n"
            f"pathlib.Path({str(ready)!r}).touch()\n"
            f"while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)\n"
            f"pathlib.Path({str(done)!r}).touch()\n")
        argv = [*self.sealed('review_flow', 'cli', [binary]), 'codex']
        env = self.codex_env()
        process = subprocess.Popen(argv, cwd=self.repo,
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            process.kill()
            process.wait(timeout=5)
            self.assertIn('already running', self.flow('codex', ok=False).stderr)
            self.assertEqual(self.flow('status')['codex_attempts'], 1)
            release.touch()
            deadline = time.monotonic() + 5
            while not done.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(done.exists())
            while time.monotonic() < deadline:
                result = subprocess.run(argv, cwd=self.repo,
                                        env=env, capture_output=True, text=True)
                if 'already running' not in result.stderr:
                    break
                time.sleep(0.01)
            self.assertEqual(self.flow('status')['codex_attempts'], 2)
            self.locations = [binary]      # ask the spent budget against this test's Codex
            self.assertIn('budget exhausted', self.flow('codex', ok=False).stderr)
        finally:
            release.touch()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)

    def test_codex_wait_does_not_lock_out_claude_report(self):
        """Concurrent model completion preserves both reports without blocking the writer."""
        state = self.start()
        self.checks()
        ready, release = self.root / 'ready', self.root / 'release'
        report = dict(status='completed', head=state['head'], base=state['review_base'],
                      summary='Fixture review', findings=[], resolutions=[])
        binary = self.fake_codex(f"#!{sys.executable}\nimport sys,time,pathlib\n"
            f"pathlib.Path({str(ready)!r}).touch()\n"
            f"while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)\n"
            f"pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text({json.dumps(report)!r})\n")
        process = subprocess.Popen([*self.sealed('review_flow', 'cli', [binary]), 'codex'], cwd=self.repo,
                                   env=self.codex_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            self.assertIn('already running', self.flow('codex', ok=False).stderr)
            self.assertEqual(self.flow('status')['codex_attempts'], 1)
            self.report('claude')
            release.touch()
            output, error = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(set(json.loads(output)['reviews']), {'claude', 'codex'})
        finally:
            release.touch()
            if process.poll() is None:
                process.kill()
            process.communicate()


    # A Codex this machine cannot run is waived by the runtime's own probe, and only by it.
    # Every case below asks the same two questions: did the probe decide, and does the
    # receipt still rest on two independent readings of the diff?

    QUOTA = "#!/bin/sh\necho \"ERROR: You've hit your usage limit. Visit https://example.invalid to purchase more credits.\" >&2\nexit 1\n"
    AUTH = '#!/bin/sh\necho "ERROR: Not logged in. Run codex login to authenticate." >&2\nexit 1\n'

    def waive(self, script=None):
        """Run the probe against the Codex this test installed, and keep that machine for the
        rest of the campaign.

        The declared gates run first because the adapters check them before reserving an
        attempt, which is the order a real campaign follows; a fixture that skipped them would
        be modelling a sequence the runtime refuses.
        """
        if not self.flow('status')['checks']:
            self.checks()
        self.locations = [self.fake_codex(script)] if script else []
        result = self.flow('codex')
        return result['codex_waiver'], self.locations

    def test_absent_codex_is_waived_and_a_second_claude_stands_in(self):
        """No Codex at any install location and none on $PATH: the campaign continues on the
        substitute pair, and one reviewer is still not two."""
        self.start()
        waiver, locations = self.waive()
        self.assertEqual(waiver['reason'], 'absent')
        self.report('claude')
        self.assertIn('claude-b', self.triage(ok=False).stderr)
        self.flow('finish', ok=False)
        self.push('git push -u origin HEAD:feature', ok=False, locations=locations)
        self.report('claude-b')
        self.triage()
        self.checks()
        self.assertTrue(self.flow('finish')['cleared'])
        self.push('git push -u origin HEAD:feature', locations=locations)

    def test_an_account_with_nothing_left_to_spend_is_waived(self):
        """A Codex that runs and reports an exhausted account is a reviewer this machine
        cannot run, and the waiver names the binary it was measured against."""
        self.start()
        self.checks()
        waiver, locations = self.waive(script=self.QUOTA)
        self.assertEqual(waiver['reason'], 'quota')
        # Not .resolve(): the waiver records the stable name, so an upgrade that repoints
        # it does not void a receipt that already cleared.
        self.assertEqual(waiver['binary'], os.path.abspath(locations[0]))
        self.assertIn('usage limit', waiver['detail'])
        self.report('claude')
        self.report('claude-b')
        self.triage()
        self.checks()
        self.assertTrue(self.flow('finish')['cleared'])
        self.push('git push -u origin HEAD:feature')

    def test_being_signed_out_is_never_waived(self):
        """Setup, not an absent reviewer: one command fixes it, and waiving it would make
        deleting a credentials file enough to clear any candidate."""
        self.locations = [self.fake_codex(self.AUTH)]
        self.start()
        self.checks()
        result = self.flow('codex', ok=False)
        self.assertIn('codex-setup', result.stderr)
        self.assertNotIn('codex_waiver', self.flow('status'))
        self.report('claude')
        self.assertIn('no valid waiver', self.report('claude-b', ok=False).stderr)

    def test_the_review_prompt_in_the_log_cannot_waive_the_reviewer(self):
        """Codex echoes the whole prompt into the same log. A candidate whose own context
        discusses a usage limit would otherwise classify itself as one and waive the reviewer
        it was meant to run, and so would an old error further up a long log."""
        echoed = ('#!/bin/sh\necho "The acceptance contract mentions a usage limit and credits."\n'
                  'echo "ERROR: transport closed"\nexit 1\n')
        self.locations = [self.fake_codex(echoed)]
        self.start()
        self.checks()
        result = self.flow('codex', ok=False)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('Codex failed', result.stderr)
        self.assertNotIn('codex_waiver', self.flow('status'))

        buried = ('#!/bin/sh\necho "ERROR: You have hit your usage limit."\n'
                  'i=0; while [ $i -lt 40 ]; do echo "thinking about the diff"; i=$((i+1)); done\nexit 1\n')
        self.locations = [self.fake_codex(buried)]
        result = self.flow('codex', ok=False)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn('codex_waiver', self.flow('status'))

    UNRECOGNISED = '#!/bin/sh\necho "ERROR: transport closed" >&2\nexit 1\n'
    ALIVE = '#!/bin/sh\necho OK\nexit 0\n'

    def exhaust(self):
        """Spend both review attempts the way a round that hit the wall already did.

        The gates run first, because an attempt is only reserved once they have passed: a
        fixture that burned attempts without them would be spending a budget the runtime
        never lets a real campaign spend.
        """
        self.locations = [self.fake_codex(self.UNRECOGNISED)]
        self.start()
        self.checks()
        for _ in range(2):
            self.flow('codex', ok=False)
        state = self.flow('status')
        self.assertEqual(state['codex_attempts'], 2)
        self.assertNotIn('codex_waiver', state)
        return state

    def test_a_spent_budget_still_learns_whether_codex_can_run(self):
        """Burning attempts is the only way to discover an exhausted account, so the state
        that most needs a waiver is the one the budget locks out. The attempts are gone and
        stay gone; what the probe answers is whether this machine has a reviewer at all."""
        self.exhaust()
        self.fake_codex(self.QUOTA)
        waiver = self.flow('codex')['codex_waiver']
        self.assertEqual(waiver['reason'], 'quota')
        self.assertIn('usage limit', waiver['detail'])
        state = self.flow('status')
        self.assertEqual(state['codex_attempts'], 2)  # the probe is not a review attempt
        self.assertEqual(state['codex_probes'], 1)
        self.report('claude')
        self.report('claude-b')
        self.triage()
        self.checks()
        self.assertTrue(self.flow('finish')['cleared'])
        self.push('git push -u origin HEAD:feature')

    def test_a_spent_budget_never_waives_a_codex_that_answers(self):
        """Credits that came back make the spent attempts a failure to report, not a missing
        reviewer: the probe asks the machine now rather than rereading an old log."""
        self.exhaust()
        self.fake_codex(self.ALIVE)
        refused = self.flow('codex', ok=False).stderr
        self.assertIn('account is not the problem', refused)
        self.assertNotIn('codex_waiver', self.flow('status'))

        self.fake_codex(self.AUTH)
        self.assertIn('codex-setup', self.flow('codex', ok=False).stderr)
        self.assertNotIn('codex_waiver', self.flow('status'))
        # The probe has a small budget of its own, so a machine that keeps answering
        # unrecognisably cannot be asked forever.
        self.assertEqual(self.flow('status')['codex_probes'], 2)
        self.fake_codex(self.UNRECOGNISED)
        self.assertIn('without a recognisable answer', self.flow('codex', ok=False).stderr)

    def test_a_recorded_codex_review_is_never_reprobed(self):
        """A candidate that already has its Codex report is finished with Codex, whatever
        its attempt count says: the guard is the report, not the ordering."""
        self.locations = [self.fake_codex(self.UNRECOGNISED)]
        self.start()
        self.checks()
        self.flow('codex', ok=False)
        self.report('codex')
        self.assertIn('Reuse the completed Codex review', self.flow('codex', ok=False).stderr)

    def bind_escalated(self):
        """Bind an escalated profile the way the user's own setup would."""
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / 'escalated.config.toml').write_text('model = "a-model-the-user-chose"\n')

    def recording_codex(self):
        """A stand-in Codex that writes down the argv it was given."""
        argv = self.root / 'argv.txt'
        return self.fake_codex(f"#!{sys.executable}\nimport sys,pathlib\n"
                               f"pathlib.Path({str(argv)!r}).write_text(repr(sys.argv))\n"
                               "sys.exit(1)\n"), argv

    def test_the_runtime_decides_which_rounds_escalate(self):
        """The decision is a function of the campaign's own state, so it cannot depend on a
        model remembering to ask for a better reviewer, and an unbound profile is a choice
        rather than a misconfiguration: it means today's behaviour, silently."""
        import importlib.util
        spec = importlib.util.spec_from_file_location('flow_escalation', FLOW.with_name('review_codex.py'))
        flow = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(flow)
        os.environ['CODEX_HOME'] = str(self.home)
        self.addCleanup(os.environ.pop, 'CODEX_HOME', None)

        ordinary = dict(round=1, max_rounds=3)
        decisive = [dict(round=2, max_rounds=3, design_round=True),
                    dict(round=2, max_rounds=3, reopened=['src/job.py:restart']),
                    dict(round=3, max_rounds=3),
                    dict(round=1, max_rounds=6, delivery_used=6)]
        # Unbound: nothing escalates, including the rounds that would.
        self.assertEqual(flow.escalation(ordinary), [])
        for state in decisive:
            self.assertEqual(flow.escalation(state), [], state)
        self.bind_escalated()
        self.assertEqual(flow.escalation(ordinary), [])
        for state in decisive:
            self.assertEqual(flow.escalation(state), ['-p', 'escalated'], state)

    def test_an_ordinary_round_runs_the_standing_model(self):
        """The argv Codex actually receives carries no profile until a round is decisive, so
        the expensive slot is not the standing cost of every campaign."""
        binary, argv = self.recording_codex()
        self.locations = [binary]
        self.bind_escalated()
        self.start()
        self.checks()
        self.flow('codex', ok=False)
        self.assertNotIn('-p', eval(argv.read_text()))

        directory = Path(self.flow('status')['directory'])
        state = json.loads((directory / 'state.json').read_text())
        (directory / 'state.json').write_text(json.dumps(dict(state, max_rounds=1, codex_attempts=0)))
        self.flow('codex', ok=False)
        spelled = eval(argv.read_text())
        self.assertEqual(spelled[spelled.index('-p') + 1], 'escalated')
        self.assertLess(spelled.index('-p'), spelled.index('--sandbox'))

    def loaded(self, name):
        """Import one runtime module on its own, for a check that needs no repository."""
        spec = importlib.util.spec_from_file_location(name, FLOW.with_name(name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_a_waiver_names_the_codex_path_and_not_the_file_it_points_at(self):
        """Every install channel here puts a stable name in front of a versioned file, so
        dereferencing pins a waiver to a release: a routine upgrade inside the window then
        voids a receipt that already cleared and blocks a certified push. Dereferencing buys
        nothing — both sides of the comparison call this same function."""
        prepush = self.loaded('review_prepush')
        real = self.root / 'versions' / '1.0.0' / 'codex'
        real.parent.mkdir(parents=True)
        real.write_text('#!/bin/sh\nexit 0\n')
        real.chmod(0o755)
        link = self.root / 'stable' / 'codex'
        link.parent.mkdir()
        link.symlink_to(real)
        prepush.CODEX_LOCATIONS = (str(link),)
        self.assertEqual(prepush.resolve_codex(), str(link))

        # And the comparison still holds against what a waiver recorded, which is the point.
        waiver = dict(reason='quota', at=int(time.time()), binary=prepush.resolve_codex())
        self.assertTrue(prepush.waiver_ok(waiver))

    def test_the_substitute_is_refused_without_a_waiver_the_runtime_granted(self):
        """claude-b is the stand-in for a Codex the probe could not run. With Codex available
        it is a second reading dressed as the missing one, and the record refuses it."""
        self.start()
        self.report('claude')
        refused = self.report('claude-b', ok=False).stderr
        self.assertIn('no valid waiver', refused)
        self.report('codex')
        self.triage()
        self.checks()
        self.assertTrue(self.flow('finish')['cleared'])

    def test_a_real_codex_report_replaces_the_waiver(self):
        """Credits return, or a report is obtained elsewhere: the reviewer that exists
        replaces the reason it was missing, and the receipt names it."""
        self.start()
        self.waive()
        self.report('claude')
        self.report('claude-b')
        self.report('codex')
        self.assertNotIn('codex_waiver', self.flow('status'))
        self.triage()
        self.checks()
        self.assertTrue(self.flow('finish')['cleared'])
        # Codex is on the record, so the receipt no longer rests on a waiver and the guard's
        # probe has nothing to re-check.
        self.push('git push -u origin HEAD:feature')

    def test_a_waiver_that_no_longer_describes_this_machine_stops_the_push(self):
        """A waiver is evidence about a machine at a moment. The guard re-runs the probe
        rather than reading the claim: past its window, or measured against a Codex this
        machine does not resolve, a cleared receipt stops being one."""
        self.start()
        _, locations = self.waive()
        self.report('claude')
        self.report('claude-b')
        self.triage()
        self.checks()
        self.assertTrue(self.flow('finish')['cleared'])
        self.push('git push -u origin HEAD:feature', locations=locations)

        directory = Path(self.flow('status')['directory'])
        state = json.loads((directory / 'state.json').read_text())
        for waiver, expected in ((dict(state['codex_waiver'], at=time.time() - 25 * 3600), 'window'),
                                 (dict(state['codex_waiver'], at=time.time() + 7200), 'window'),
                                 (dict(state['codex_waiver'], reason='quota', binary='/nowhere/codex'), 'resolves')):
            (directory / 'state.json').write_text(json.dumps(dict(state, codex_waiver=waiver)))
            refused = self.push('git push -u origin HEAD:feature', ok=False, locations=locations)
            self.assertIn(expected, refused.stderr)
        # And the same receipt re-checked where Codex is installed: an absent waiver is void.
        (directory / 'state.json').write_text(json.dumps(state))
        refused = self.push('git push -u origin HEAD:feature', ok=False,
                            locations=[self.fake_codex('#!/bin/sh\nexit 0\n')])
        self.assertIn('but it is, at', refused.stderr)


if __name__ == '__main__':
    unittest.main()
