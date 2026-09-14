"""Regression layer: exercise review state and push guards in isolated Git repositories."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / 'plugins/bymax-quality/scripts/review_flow.py'
PUSH = FLOW.with_name('review_push.py')


class ReviewFlowTests(unittest.TestCase):
    """Model candidate changes and independent reviewer evidence through the CLI."""

    def setUp(self):
        """Create a private Git fixture and context outside the candidate tree."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.commit('base')
        self.base = self.git('rev-parse', 'HEAD')
        self.context = self.root / 'context.md'
        self.context.write_text(json.dumps(dict(intent='Fix requested feature', acceptance=['Preserve callers'],
            constraints=['No unrelated changes'], scope='Candidate against base',
            checks=[[sys.executable, '-c', 'from pathlib import Path; assert Path("code.txt").read_text()']])))
        self.commit('candidate')

    def git(self, *args):
        """Run Git without hooks or global configuration in the fixture."""
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        return subprocess.check_output(['git', *args], cwd=self.repo, env=env, text=True).strip()

    def commit(self, text):
        """Create a candidate with an observable tree change."""
        (self.repo / 'code.txt').write_text(text)
        self.git('add', '.')
        self.git('commit', '-qm', text)

    def flow(self, *args, ok=True):
        """Invoke the lifecycle command and assert success or fail-closed behavior."""
        result = subprocess.run([sys.executable, str(FLOW), *args], cwd=self.repo, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr)
        return json.loads(result.stdout) if result.returncode == 0 and result.stdout.startswith('{') else result

    def start(self, ok=True, correction=False, design=False, probe=None, reason='fixture: no test needed'):
        """Start or reuse a candidate; a correction round carries its probe and test evidence."""
        args = ['start', '--base', self.base, '--context', str(self.context)]
        if correction:
            path = self.root / 'probe.json'
            path.write_text(json.dumps(probe if probe is not None else [
                dict(command='python3 -c "print(1)"', expected='1', observed='1')]))
            args += ['--probe', str(path), '--no-regression-reason', reason]
        if design:
            args.append('--design-round')
        return self.flow(*args, ok=ok)

    def report(self, name, findings=None, resolutions=None, ok=True):
        """Provide a completed reviewer fixture for the current endpoints."""
        state = self.flow('status')
        path = self.root / (name + '.json')
        path.write_text(json.dumps(dict(status='completed', head=state['head'], base=state['review_base'], summary='Inspected fixture',
                                       findings=findings or [], resolutions=resolutions or [])))
        return self.flow('record', '--reviewer', name, '--report', str(path), ok=ok)

    def triage(self, items=None, ok=True):
        """Persist dispositions as an explicit review artifact."""
        path = self.root / 'triage.json'
        path.write_text(json.dumps(items or []))
        return self.flow('triage', '--report', str(path), ok=ok)

    def checks(self):
        """Run a real successful check of the fixture candidate."""
        return self.flow('check', '--', sys.executable, '-c', 'from pathlib import Path; assert Path("code.txt").read_text()')

    def complete(self):
        """Complete both empty review fixtures and the required check."""
        self.report('claude')
        self.report('codex')
        self.triage()
        self.checks()
        return self.flow('finish')

    def push(self, command, cwd=None, ok=True):
        """Invoke only the guard, never a real push."""
        payload = dict(cwd=str(cwd or self.repo), tool_input=dict(command=command))
        result = subprocess.run([sys.executable, str(PUSH)], input=json.dumps(payload), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr)

    def test_requires_both_reviewers_and_checks(self):
        """One reviewer or missing gates cannot clear a candidate."""
        self.start()
        self.report('claude')
        self.flow('finish', ok=False)
        self.report('codex')
        self.triage()
        self.flow('finish', ok=False)
        self.checks()
        self.assertTrue(self.flow('finish')['cleared'])
        self.assertTrue(self.start()['cleared'])
        self.push('git push -u origin HEAD:feature')

    def test_stale_and_dirty_candidates(self):
        """New commits and untracked files invalidate current operations."""
        self.start()
        self.complete()
        self.commit('changed')
        self.push('git push origin HEAD', ok=False)
        self.flow('finish', ok=False)
        (self.repo / 'untracked').write_text('new')
        self.start(ok=False)

    def test_other_worktree_cannot_clear_current_source(self):
        """A reviewed sibling SHA cannot release an unreviewed candidate."""
        self.start()
        self.complete()
        sibling = self.root / 'sibling with spaces'
        self.git('worktree', 'add', '-qb', 'sibling', str(sibling))
        self.commit('unreviewed')
        self.push('git push origin HEAD', ok=False)
        self.push('git push origin sibling')
        self.push('git push origin sibling HEAD', ok=False)
        self.push(f'git -C "{sibling}" push origin HEAD')

    def test_adapter_checks_only_the_literal_shape(self):
        """The adapter reports a missing receipt early for the exact form; the hook is the net."""
        self.start()
        self.complete()
        self.commit('unreviewed')
        for literal in ('git push origin HEAD', 'FOO=1 git push origin HEAD', 'git -C . push origin HEAD',
                        'cd . && git push origin HEAD', 'git pu""sh origin HEAD'):
            self.push(literal, ok=False)
        # Any other arrangement is not this adapter's call: it passes, and pre-push decides.
        for other in ('eval git push origin HEAD', 'if true; then git push origin HEAD; fi',
                      'git log --grep=push --format=$FORMAT', 'echo git push > notes.txt',
                      'grep -rn "git push" docs/', 'python3 -c "print(1 << 3)"',
                      "cat <<'EOF' > f\ngit push origin HEAD\nEOF\n", 'git stash push', 'FOO=bar'):
            self.push(other)

    def test_adapter_refuses_what_would_disarm_the_hook(self):
        """Options that skip hooks or redirect git are refused wherever they appear."""
        self.start()
        self.complete()
        for command in ('git push --no-verify origin HEAD', 'eval git push --no-verify origin HEAD',
                        'git -c core.hooksPath=/dev/null push origin HEAD',
                        'GIT_DIR=/other/.git git push origin HEAD', 'git --git-dir=/x push origin HEAD',
                        'echo --no-verify', 'echo x > .git/hooks/pre-push && git push origin HEAD',
                        'rm .git/hooks/pre-push', 'chmod -x .git/hooks/pre-push'):
            self.push(command, ok=False)

    def test_adapter_refuses_ambiguous_literal_pushes(self):
        """A literal push that names no source, or a wildcard one, is refused rather than guessed."""
        self.start()
        self.complete()
        for command in ('git push', 'git push --all origin', 'git push origin :branch',
                        'git push origin "refs/heads/*:refs/heads/*"', 'git push origin{,evil} HEAD',
                        'git push origin $BRANCH', 'git push origin HEAD && echo done',
                        'git push origin HEAD; rm -rf x'):
            self.push(command, ok=False)

    def test_abandoned_codex_reservation_keeps_retry_budget(self):
        """A dead owner permits one retry without resetting the attempt count."""
        state = self.start()
        reserve = ('import sys; sys.path.insert(0, ' + repr(str(FLOW.parent)) + '); '
                   'import review_flow as flow; flow.reserve_codex(flow.location())')
        subprocess.run([sys.executable, '-c', reserve], cwd=self.repo, check=True)
        binary_dir = self.root / 'bin'
        binary_dir.mkdir()
        binary = binary_dir / 'codex'
        binary.write_text('#!/bin/sh\nexit 1\n')
        binary.chmod(0o755)
        env = dict(os.environ, PATH=str(binary_dir) + os.pathsep + os.environ['PATH'])
        result = subprocess.run([sys.executable, str(FLOW), 'codex'], cwd=self.repo,
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Codex failed', result.stderr)
        latest = self.flow('status')
        self.assertEqual(latest['codex_attempts'], 2)
        self.assertFalse(latest['codex_running'])
        self.assertEqual(latest['head'], state['head'])
        self.assertIn('budget exhausted', self.flow('codex', ok=False).stderr)

    def test_round_limit_survives_processes(self):
        """Three rounds permit completion but prohibit a fourth automatic candidate."""
        self.start()
        for round_number in (1, 2, 3):
            self.report('claude')
            self.report('codex')
            self.triage()
            self.commit('fix' + str(round_number))
            result = self.start(ok=round_number < 3, correction=True)
            if round_number < 3:
                self.assertEqual(result['round'], round_number + 1)

    def test_reopened_finding_requires_a_design_round(self):
        """A finding open in two consecutive triages is a failed approach, not a missed patch."""
        self.start()
        bug = dict(id='guard:spelling', kind='defect', priority='P1', evidence='Bypass')
        self.report('claude', [bug])
        self.report('codex')
        self.triage([dict(id='claude/guard:spelling', status='open', evidence='Reproduced')])
        self.commit('patch one instance')
        self.start(correction=True)
        resolutions = [dict(id='claude/guard:spelling', evidence='Adjacent form fixed; -C form still open')]
        self.report('claude', [bug], resolutions=resolutions)
        self.report('codex', resolutions=resolutions)
        self.triage([dict(id='claude/guard:spelling', status='open', evidence='Still bypassed via -C')])
        self.commit('patch another instance')
        result = self.start(ok=False, correction=True)
        # Reopened invariants are reported without the reviewer prefix.
        self.assertIn('Reopened after a claimed fix: guard:spelling', result.stderr)
        self.assertIn('--design-round', result.stderr)
        state = self.start(correction=True, design=True)
        self.assertTrue(state['design_round'])
        self.assertEqual(state['reopened'], ['guard:spelling'])
        prompt = self.flow('prompt')
        self.assertIn('DESIGN ROUND', prompt.stdout)

    def test_correction_round_carries_the_authors_probe(self):
        """The author's own probe is required, validated, and shown to both reviewers."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        self.commit('fix')
        result = self.start(ok=False)
        self.assertIn('--probe', result.stderr)
        for hollow in ([], {}, 'text', [dict(command='x', expected='y')],
                       [dict(command='x', expected='y', observed=1)],
                       [dict(command=' ', expected=' ', observed=' ')]):
            self.start(ok=False, correction=True, probe=hollow)
            self.assertEqual(self.flow('status')['round'], 1, f'advanced on hollow probe {hollow!r}')
        self.start(correction=True, probe=[dict(command='eval git push', expected='blocked', observed='blocked')])
        prompt = self.flow('prompt')
        self.assertIn('eval git push', prompt.stdout)
        self.assertIn('Shallow probing is a finding', prompt.stdout)

    def test_reopened_is_an_invariant_not_an_id_and_needs_no_design_round_otherwise(self):
        """The other reviewer re-reporting the defect still counts; --design-round alone does not."""
        self.start()
        bug = dict(id='guard:spelling', kind='defect', priority='P1', evidence='Bypass')
        self.report('claude', [bug])
        self.report('codex')
        self.triage([dict(id='claude/guard:spelling', status='open', evidence='Reproduced')])
        self.commit('patch')
        self.start(ok=False, correction=True, design=True)  # nothing reopened yet
        self.start(correction=True)
        resolutions = [dict(id='claude/guard:spelling', evidence='Not fixed')]
        self.report('claude', resolutions=resolutions)
        # The other reviewer repeats it under the PREFIXED id it saw in the dispositions;
        # record strips the prefix, so it is still the same invariant.
        prefixed = dict(bug, id='claude/guard:spelling')
        self.report('codex', [prefixed], resolutions=resolutions)
        self.triage([dict(id='codex/guard:spelling', status='open', evidence='Still bypassed')])
        self.commit('patch again')
        result = self.start(ok=False, correction=True)
        self.assertIn('Reopened after a claimed fix: guard:spelling', result.stderr)
        self.assertEqual(self.start(correction=True, design=True)['reopened'], ['guard:spelling'])

    def test_test_path_classification(self):
        """Jest's __tests__ and Python's test_ files count; a spec document does not."""
        import importlib.util
        spec = importlib.util.spec_from_file_location('flow', FLOW)
        flow = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(flow)
        for path in ('src/__tests__/foo.ts', 'app/(tabs)/__tests__/index.tsx', 'tests/test_x.py',
                     'scripts/tests/test_review_flow.py', 'pkg/foo_test.go', 'a/b.test.tsx',
                     'a/b.spec.js', 'spec/models/user_spec.rb', 'test_alone.py', 'tests/fixtures/data.json',
                     'tests/golden/expected.txt', 'tests/api.rst', 'tests/doctest_cases.txt'):
            self.assertTrue(flow.is_test_path(path), path)
        for path in ('docs/spec.md', 'openapi/spec.yaml', 'test.txt', 'tests.md', 'src/latest.ts',
                     'contest.py', 'attestation.json', 'docs/spec/overview.md', 'spec/README.md',
                     'docs/tests/plan.md', 'notes_test.txt', 'latest.spec.md', 'tests/README.md',
                     'tests/plan.markdown', 'tests/notes.adoc'):
            self.assertFalse(flow.is_test_path(path), path)

    def test_prefix_stripped_only_for_a_copied_id_never_for_a_real_path(self):
        """A copied disposition id collapses to the known invariant; a codex/ path is kept.

        The stripping rule was changed from unconditional to path-aware, so the earlier
        expectation that any prefixed id is stored bare no longer holds; see the
        path-segment-mistaken-for-reviewer-prefix disposition.
        """
        (self.repo / 'codex/scripts').mkdir(parents=True)
        (self.repo / 'codex/scripts/bundle.py').write_text('# real file under codex/\n')
        (self.repo / 'codex/README.md').write_text('codex readme\n')
        (self.repo / 'README.md').write_text('root readme\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'add codex tree')
        self.start()
        real = [dict(id='codex/scripts/bundle.py:drift', kind='nit', priority='P3', evidence='x'),
                dict(id='README.md:x', kind='nit', priority='P3', evidence='y'),
                dict(id='codex/README.md:x', kind='nit', priority='P3', evidence='z'),
                dict(id='guard:spelling', kind='defect', priority='P1', evidence='w'),
                dict(id=' guard:spelling ', kind='nit', priority='P3', evidence='dup by whitespace')]
        self.report('claude', real, ok=False)  # the whitespace variant is a duplicate
        self.report('claude', real[:4])
        stored = [f['id'] for f in self.flow('status')['reviews']['claude']['findings']]
        self.assertEqual(stored, ['codex/scripts/bundle.py:drift', 'README.md:x',
                                  'codex/README.md:x', 'guard:spelling'])
        self.report('codex')
        self.triage([dict(id='claude/' + f['id'], status='open' if f['id'] == 'guard:spelling' else 'deferred',
                          evidence='e') for f in real[:4]])
        self.commit('fix')
        self.start(correction=True)
        # Round 2: a copied prefixed id names the known invariant; a prefixed REAL path stays.
        again = [dict(id='claude/guard:spelling', kind='defect', priority='P1', evidence='still'),
                 dict(id='codex/claude/codex/scripts/bundle.py:drift', kind='nit', priority='P3', evidence='n')]
        resolutions = [dict(id='claude/guard:spelling', evidence='still open')]
        self.report('claude', again, resolutions=resolutions)
        stored = [f['id'] for f in self.flow('status')['reviews']['claude']['findings']]
        self.assertEqual(stored, ['guard:spelling', 'codex/scripts/bundle.py:drift'])
        # Within one report, a prefixed repeat of an id already listed is a duplicate.
        self.report('codex', [dict(id='guard:c', kind='nit', priority='P3', evidence='x'),
                              dict(id='codex/guard:c', kind='nit', priority='P3', evidence='y')],
                    resolutions=resolutions, ok=False)

    def test_legacy_round_state_yields_no_fabricated_evidence(self):
        """A round frozen before evidence recording must not be presented as probed."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        self.commit('fix')
        self.start(correction=True)
        state_path = Path(self.flow('status')['directory']) / 'state.json'
        state = json.loads(state_path.read_text())
        for key in ('probe', 'regression_tests', 'no_regression_reason', 'design_round', 'reopened'):
            state.pop(key, None)
        state_path.write_text(json.dumps(state))
        prompt = self.flow('prompt').stdout
        self.assertIn('predates probe and regression-test recording', prompt)
        self.assertNotIn('Shallow probing', prompt)
        self.assertNotIn('No test changed', prompt)

    def test_correction_without_tests_needs_a_recorded_reason(self):
        """A correction that touches no test must say why, and the reason reaches reviewers."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        self.commit('fix without test')
        result = self.start(ok=False, correction=True, reason='')
        self.assertIn('touches no test', result.stderr)
        self.start(ok=False, correction=True, reason='   ')
        self.start(correction=True, reason='docs-only change')
        self.assertIn('docs-only change', self.flow('prompt').stdout)
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_fix.py').write_text('def test_fix(): pass\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'add regression')
        state = self.start(correction=True, reason='')
        self.assertEqual(state['regression_tests'], ['tests/test_fix.py'])
        self.assertIn('Tests changed in this delta: tests/test_fix.py', self.flow('prompt').stdout)

    def test_confirmed_blocker_cannot_be_deferred(self):
        """A P2 correctness finding needs repair or concrete rejection, not deferral."""
        self.start()
        finding = dict(id='code:invariant', kind='defect', priority='P2', evidence='Concrete failure path')
        self.report('claude', [finding])
        self.report('codex')
        self.triage(ok=False)
        self.triage([dict(id='claude/code:invariant', status='deferred', evidence='Later')])
        self.checks()
        self.flow('finish', ok=False)

    def test_correction_requires_explicit_recheck(self):
        """An earlier defect cannot vanish from the next report without evidence."""
        self.start()
        self.report('claude', [dict(id='bug', kind='defect', priority='P1', evidence='Proof')])
        self.report('codex')
        self.triage([dict(id='claude/bug', status='open', evidence='Reproduced')])
        self.commit('repair')
        state = self.start(correction=True)
        self.assertNotEqual(state['base'], state['review_base'])
        self.report('claude', ok=False)
        resolutions = [dict(id='claude/bug', evidence='Regression test now passes; caller checked')]
        self.report('claude', resolutions=resolutions)
        self.report('codex', resolutions=resolutions)

    def test_failed_check_not_hidden_by_other_command(self):
        """A trivial pass cannot erase a recorded failure."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        self.flow('check', '--', sys.executable, '-c', 'raise SystemExit(1)', ok=False)
        self.checks()
        self.flow('finish', ok=False)

    def test_interrupted_check_cannot_leave_a_cleared_receipt(self):
        """A gate that never reports an exit status invalidates the previous clearance."""
        self.start()
        self.complete()
        self.push('git push origin HEAD')
        self.flow('check', '--', str(self.root / 'absent-executable'), ok=False)
        self.flow('finish', ok=False)
        self.push('git push origin HEAD', ok=False)

    def test_incomplete_or_wrong_scope_reports_rejected(self):
        """Plausible prose cannot substitute for a completed matching report."""
        state = self.start()
        path = self.root / 'bad.json'
        for status, head in [('incomplete', state['head']), ('completed', self.base)]:
            path.write_text(json.dumps(dict(status=status, head=head, base=state['review_base'],
                                            summary='Coverage', findings=[])))
            self.flow('record', '--reviewer', 'claude', '--report', str(path), ok=False)

    def test_all_declared_checks_required(self):
        """A successful unrelated check does not satisfy the declared project gates."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        self.flow('check', '--', sys.executable, '-c', 'print("ok")')
        self.flow('finish', ok=False)

    def test_completed_campaign_allows_new_work(self):
        """Bounded repair limits do not permanently lock a successfully reviewed branch."""
        self.start()
        previous = self.complete()['head']
        self.commit('new request')
        state = self.start()
        self.assertEqual(state['round'], 1)
        self.assertEqual(state['review_base'], self.base)
        self.assertFalse(state['cleared'])
        self.push('git push origin ' + previous)
        self.push('git push origin HEAD', ok=False)

    def test_implicit_additional_refs_are_rejected(self):
        """Git configuration cannot turn an explicit source check into a mirror push."""
        self.start()
        self.complete()
        self.git('config', 'push.followTags', 'true')
        self.push('git push origin HEAD', ok=False)
        self.git('config', '--unset', 'push.followTags')
        self.git('config', 'remote.origin.mirror', 'true')
        self.push('git push origin HEAD', ok=False)

    def test_codex_child_keeps_lock_after_launcher_is_killed(self):
        """An orphaned child excludes retries until it exits, then recovery is bounded."""
        self.start()
        binary_dir = self.root / 'bin'
        binary_dir.mkdir()
        ready, release, done = [self.root / name for name in ('ready', 'release', 'done')]
        binary = binary_dir / 'codex'
        binary.write_text(f"#!{sys.executable}\nimport time,pathlib\n"
            f"pathlib.Path({str(ready)!r}).touch()\n"
            f"while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)\n"
            f"pathlib.Path({str(done)!r}).touch()\n")
        binary.chmod(0o755)
        env = dict(os.environ, PATH=str(binary_dir) + os.pathsep + os.environ['PATH'])
        process = subprocess.Popen([sys.executable, str(FLOW), 'codex'], cwd=self.repo,
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
                result = subprocess.run([sys.executable, str(FLOW), 'codex'], cwd=self.repo,
                                        env=env, capture_output=True, text=True)
                if 'already running' not in result.stderr:
                    break
                time.sleep(0.01)
            self.assertEqual(self.flow('status')['codex_attempts'], 2)
            self.assertIn('budget exhausted', self.flow('codex', ok=False).stderr)
        finally:
            release.touch()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)

    def test_codex_wait_does_not_lock_out_claude_report(self):
        """Concurrent model completion preserves both reports without blocking the writer."""
        state = self.start()
        binary_dir = self.root / 'bin'
        binary_dir.mkdir()
        ready, release = self.root / 'ready', self.root / 'release'
        report = dict(status='completed', head=state['head'], base=state['review_base'],
                      summary='Fixture review', findings=[], resolutions=[])
        binary = binary_dir / 'codex'
        binary.write_text(f"#!{sys.executable}\nimport sys,time,pathlib\n"
            f"pathlib.Path({str(ready)!r}).touch()\n"
            f"while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)\n"
            f"pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text({json.dumps(report)!r})\n")
        binary.chmod(0o755)
        env = dict(os.environ, PATH=str(binary_dir) + os.pathsep + os.environ['PATH'])
        process = subprocess.Popen([sys.executable, str(FLOW), 'codex'], cwd=self.repo,
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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


if __name__ == '__main__':
    unittest.main()
