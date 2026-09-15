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
                        'rm .git/hooks/pre-push', 'chmod -x .git/hooks/pre-push',
                        # git reads config keys case-insensitively; so must the guard.
                        'git -c core.hookspath=/dev/null push origin HEAD',
                        'git -c CORE.HOOKSPATH=/x push origin HEAD', 'git push --NO-VERIFY origin HEAD',
                        # husky's dispatcher exits before the tracked hook when HUSKY=0.
                        'env HUSKY=0 git push origin HEAD', 'HUSKY=0 git push origin HEAD'):
            self.push(command, ok=False)

    def test_triage_after_the_correction_commit_names_the_way_back(self):
        """Dispositions belong to the reviewed candidate; once HEAD moved on, the refusal says
        to return to it, and the disposition file must key every finding exactly once."""
        self.start()
        self.complete()
        self.commit('correction before triage')
        refused = self.triage([], ok=False).stderr
        candidate = self.git('rev-parse', 'HEAD~1')
        self.assertIn(f'git reset --hard {candidate[:12]}, triage, then git reset --hard back', refused)
        self.git('reset', '-q', '--hard', 'HEAD~1')
        refused = self.triage([dict(id='claude/x:y', status='open', evidence='e')], ok=False).stderr
        self.assertIn('keyed reviewer::<id>', refused)
        self.assertIn('Unexpected or duplicated: claude/x:y', refused)
        refused = self.triage([dict(status='open', evidence='no id at all')], ok=False).stderr
        self.assertIn('Unexpected or duplicated: None', refused)

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
        self.triage([dict(id='claude::guard:spelling', status='open', evidence='Reproduced')])
        self.commit('patch one instance')
        self.start(correction=True)
        resolutions = [dict(id='claude::guard:spelling', evidence='Adjacent form fixed; -C form still open')]
        self.report('claude', [bug], resolutions=resolutions)
        self.report('codex', resolutions=resolutions)
        self.triage([dict(id='claude::guard:spelling', status='open', evidence='Still bypassed via -C')])
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
        # A probe the reviewer's sandbox cannot run is a limitation to state, not `incomplete`.
        self.assertIn('is a limitation to state in your summary, not a reason to report incomplete', prompt.stdout)

    def test_reopened_is_an_invariant_not_an_id_and_needs_no_design_round_otherwise(self):
        """The other reviewer re-reporting the defect still counts; --design-round alone does not."""
        self.start()
        bug = dict(id='guard:spelling', kind='defect', priority='P1', evidence='Bypass')
        self.report('claude', [bug])
        self.report('codex')
        self.triage([dict(id='claude::guard:spelling', status='open', evidence='Reproduced')])
        self.commit('patch')
        self.start(ok=False, correction=True, design=True)  # nothing reopened yet
        self.start(correction=True)
        resolutions = [dict(id='claude::guard:spelling', evidence='Not fixed')]
        self.report('claude', resolutions=resolutions)
        # The other reviewer repeats it under the PREFIXED id it saw in the dispositions;
        # record strips the prefix, so it is still the same invariant.
        prefixed = dict(bug, id='claude::guard:spelling')
        self.report('codex', [prefixed], resolutions=resolutions)
        self.triage([dict(id='codex::guard:spelling', status='open', evidence='Still bypassed')])
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
                     'tests/golden/expected.txt', 'tests/api.rst', 'tests/doctest_cases.txt',
                     'tests/fixtures/config.spec.yaml', 'Tests/x.py', 'src/__TESTS__/a.ts', 'a/b.Test.tsx'):
            self.assertTrue(flow.is_test_path(path), path)
        for path in ('docs/spec.md', 'openapi/spec.yaml', 'test.txt', 'tests.md', 'src/latest.ts',
                     'contest.py', 'attestation.json', 'docs/spec/overview.md', 'spec/README.md',
                     'docs/tests/plan.md', 'notes_test.txt', 'latest.spec.md', 'tests/README.md',
                     'tests/plan.markdown', 'tests/notes.adoc', 'openapi/v1.spec.yaml', 'api.spec.json',
                     'config.test.toml'):
            self.assertFalse(flow.is_test_path(path), path)

    def test_each_reviewers_open_disposition_needs_its_own_resolution(self):
        """claude::x and codex::x are two verifications; one resolution covers one of them."""
        self.start()
        bug = dict(id='guard:x', kind='defect', priority='P1', evidence='e')
        self.report('claude', [bug])
        self.report('codex', [bug])
        self.triage([dict(id='claude::guard:x', status='open', evidence='e'),
                     dict(id='codex::guard:x', status='open', evidence='e')])
        self.commit('fix')
        self.start(correction=True)
        self.report('claude', resolutions=[dict(id='claude::guard:x', evidence='fixed')], ok=False)
        self.report('claude', resolutions=[dict(id='claude::guard:x', evidence='fixed'),
                                           dict(id='codex::guard:x', evidence='fixed')])

    def test_reviewer_keys_cannot_collide_with_paths(self):
        """A copied reviewer key collapses to the bare id; a path under codex/ is never touched.

        Keys are reviewer::<id>, and no path begins with `claude::` or `codex::`, so a
        root file and its mirror under a real codex/ directory stay distinct through
        record, triage, resolutions and the reopened comparison.
        """
        (self.repo / 'codex').mkdir()
        (self.repo / 'codex/README.md').write_text('codex readme\n')
        (self.repo / 'README.md').write_text('root readme\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'add codex mirror')
        self.start()
        root = dict(id='README.md:x', kind='defect', priority='P1', evidence='root')
        mirror = dict(id='codex/README.md:x', kind='defect', priority='P1', evidence='mirror')
        self.report('claude', [mirror, dict(root, id=' README.md:x ')])
        self.report('codex', [root, dict(id='codex::README.md:x', kind='nit', priority='P3', evidence='dup')], ok=False)
        self.report('codex', [root])
        self.assertEqual([f['id'] for f in self.flow('status')['reviews']['claude']['findings']],
                         ['codex/README.md:x', 'README.md:x'])
        keys = ['claude::codex/README.md:x', 'claude::README.md:x', 'codex::README.md:x']
        self.triage([dict(id=k, status='open', evidence='e') for k in keys])
        self.commit('fix')
        self.start(correction=True)
        # A resolution for the root file does not cover its mirror, and vice versa.
        self.report('claude', resolutions=[dict(id=k, evidence='still') for k in keys[1:]], ok=False)
        resolutions = [dict(id=k, evidence='still') for k in keys]
        # Copied keys, even doubled, name the bare invariants; the mirror path survives as itself.
        self.report('claude', [dict(mirror, id='codex::claude::codex/README.md:x'), dict(root, id='claude::README.md:x')],
                    resolutions=resolutions)
        self.assertEqual([f['id'] for f in self.flow('status')['reviews']['claude']['findings']],
                         ['codex/README.md:x', 'README.md:x'])
        self.report('codex', [root], resolutions=resolutions)
        self.triage([dict(id=k, status='open', evidence='e') for k in keys])
        self.commit('fix again')
        result = self.start(ok=False, correction=True)
        self.assertIn('Reopened after a claimed fix: README.md:x, codex/README.md:x', result.stderr)
        self.assertEqual(self.start(correction=True, design=True)['reopened'], ['README.md:x', 'codex/README.md:x'])

    def test_policy_mismatch_is_refused_with_instructions(self):
        """A campaign frozen under another policy is neither misread nor deleted."""
        self.start()
        state_path = Path(self.flow('status')['directory']) / 'state.json'
        state = json.loads(state_path.read_text())
        state['policy'] = 1
        state_path.write_text(json.dumps(state))
        result = self.flow('status', ok=False)
        self.assertIn('frozen under policy 1', result.stderr)
        self.assertIn('runtime is policy 2', result.stderr)
        self.assertEqual(json.loads(state_path.read_text())['policy'], 1)

    def test_renamed_test_counts_under_its_new_path(self):
        """A renamed and extended test is regression evidence, listed where it now lives."""
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_old.py').write_text('def test_a(): pass\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'existing test')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/test_old.py').rename(self.repo / 'tests/test_new.py')
        (self.repo / 'tests/test_new.py').write_text('def test_a(): pass\ndef test_b(): pass\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'rename and extend')
        state = self.start(correction=True, reason='')
        self.assertEqual(state['regression_tests'], ['tests/test_new.py'])
        self.assertIn('tests/test_new.py', self.flow('prompt').stdout)

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
        # Adding the regression on top of the same candidate lifts the requirement.
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_fix.py').write_text('def test_fix(): pass\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'add regression')
        state = self.start(correction=True, reason='')
        self.assertEqual(state['round'], 2)
        self.assertEqual(state['regression_tests'], ['tests/test_fix.py'])
        self.assertIn('Tests changed in this delta: tests/test_fix.py', self.flow('prompt').stdout)
        self.report('claude')
        self.report('codex')
        self.triage()
        # Deleting that test is not a regression: the next round needs a reason again,
        # and the reason reaches both reviewers. This is round 3, inside the limit.
        (self.repo / 'tests/test_fix.py').unlink()
        self.git('add', '-A')
        self.git('commit', '-qm', 'remove the test')
        result = self.start(ok=False, correction=True, reason='')
        self.assertIn('touches no test', result.stderr)
        state = self.start(correction=True, reason='removed a flaky test on purpose')
        self.assertEqual(state['round'], 3)
        self.assertEqual(state['removed_tests'], ['tests/test_fix.py'])
        prompt = self.flow('prompt').stdout
        self.assertIn('removed a flaky test on purpose', prompt)
        self.assertIn('Tests removed in this delta: tests/test_fix.py', prompt)

    def test_confirmed_blocker_cannot_be_deferred(self):
        """A P2 correctness finding needs repair or concrete rejection, not deferral."""
        self.start()
        finding = dict(id='code:invariant', kind='defect', priority='P2', evidence='Concrete failure path')
        self.report('claude', [finding])
        self.report('codex')
        self.triage(ok=False)
        self.triage([dict(id='claude::code:invariant', status='deferred', evidence='Later')])
        self.checks()
        self.flow('finish', ok=False)

    def test_correction_requires_explicit_recheck(self):
        """An earlier defect cannot vanish from the next report without evidence."""
        self.start()
        self.report('claude', [dict(id='bug', kind='defect', priority='P1', evidence='Proof')])
        self.report('codex')
        self.triage([dict(id='claude::bug', status='open', evidence='Reproduced')])
        self.commit('repair')
        state = self.start(correction=True)
        self.assertNotEqual(state['base'], state['review_base'])
        self.report('claude', ok=False)
        resolutions = [dict(id='claude::bug', evidence='Regression test now passes; caller checked')]
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
