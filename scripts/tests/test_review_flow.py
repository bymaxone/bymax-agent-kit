"""Regression layer: exercise review state and push guards in isolated Git repositories."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / 'plugins/bymax-quality/scripts/review_flow.py'
sys.path.insert(0, str(FLOW.parent))
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

    def text(self, *args):
        """Invoke a lifecycle command that answers in plain text rather than state."""
        result = subprocess.run([sys.executable, str(FLOW), *args], cwd=self.repo,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def start(self, ok=True, correction=False, design=False, probe=None, reason='fixture: no test needed',
              nit='fixture: no blocking finding in play', widen='', answers=(), extend='', autonomous=False):
        """Start or reuse a candidate; a correction round carries its probe and test evidence.

        A round needs a blocking finding or a recorded reason for spending it on nits; a
        fixture exercising another rule passes the reason so that rule stays in view.
        """
        args = ['start', '--base', self.base, '--context', str(self.context)]
        if correction:
            path = self.root / 'probe.json'
            path.write_text(json.dumps(probe if probe is not None else [
                dict(command='python3 -c "print(1)"', expected='1', observed='1')]))
            args += ['--probe', str(path), '--no-regression-reason', reason]
            if nit:
                args += ['--nit-round', nit]
        if widen:
            args += ['--widen-scope', widen]
        if answers:
            args += ['--answers', *answers]
        if extend:
            args += ['--extend-delivery', extend]
        if autonomous:
            args.append('--autonomous')
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

    def test_prompt_keeps_sandboxed_reviewers_off_the_declared_checks(self):
        """Declared checks are the caller's to run; a reviewer that gave up on a sandbox denial is
        told the environment fix, so the retry is not spent on the same failure."""
        self.start()
        prompt = self.flow('prompt')
        self.assertIn('executed and recorded by the caller through review_flow.py check', prompt.stdout)
        self.assertIn('never a reason to report incomplete', prompt.stdout)
        state = self.flow('status')
        path = self.root / 'incomplete.json'
        path.write_text(json.dumps(dict(status='incomplete', head=state['head'], base=state['review_base'],
                                        summary="Could not run the suite: EPERM: operation not permitted, open '/tmp/jest_dx'",
                                        findings=[], resolutions=[])))
        refused = self.flow('record', '--reviewer', 'codex', '--report', str(path), ok=False).stderr
        self.assertIn('a retry in the same sandbox fails identically', refused)
        self.assertIn('no project configuration makes that sandbox writable', refused)
        # Ordinary words in a summary are not a denial: a ceiling timeout keeps its one retry.
        path.write_text(json.dumps(dict(status='incomplete', head=state['head'], base=state['review_base'],
                                        summary='Read-only review with permission to read everything ran out of the ten-minute ceiling',
                                        findings=[], resolutions=[])))
        refused = self.flow('record', '--reviewer', 'codex', '--report', str(path), ok=False).stderr
        self.assertIn('did not complete its scope', refused)
        self.assertNotIn('fails identically', refused)

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
        """One copied reviewer key collapses to the bare id; a path under codex/ is never touched.

        Keys are reviewer::<id>, and their two parts stay recoverable by one split from the
        left, so exactly one copied prefix is removed and an id that still begins with one is
        refused. A root file and its mirror under a real codex/ directory stay distinct
        through record, triage, resolutions and the reopened comparison.
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
        # This fixture exercises key collision, and its correction edits the fixture file
        # rather than the README the findings name; that is a widened round, so it says so.
        self.start(correction=True, widen='fixture: this case is about keys, not about scope')
        # A resolution for the root file does not cover its mirror, and vice versa.
        self.report('claude', resolutions=[dict(id=k, evidence='still') for k in keys[1:]], ok=False)
        resolutions = [dict(id=k, evidence='still') for k in keys]
        # A doubled prefix is ambiguous: removing both would let an id's content move the
        # boundary of the key, so it is refused rather than collapsed.
        doubled = self.report('claude', [dict(mirror, id='codex::claude::codex/README.md:x')],
                              resolutions=resolutions, ok=False)
        self.assertIn('still begins with a reviewer prefix', doubled.stderr)
        # One copied prefix names the bare invariant; the mirror path survives as itself.
        self.report('claude', [dict(mirror, id='claude::codex/README.md:x'), dict(root, id='claude::README.md:x')],
                    resolutions=resolutions)
        self.assertEqual([f['id'] for f in self.flow('status')['reviews']['claude']['findings']],
                         ['codex/README.md:x', 'README.md:x'])
        self.report('codex', [root], resolutions=resolutions)
        self.triage([dict(id=k, status='open', evidence='e') for k in keys])
        self.commit('fix again')
        result = self.start(ok=False, correction=True)
        self.assertIn('Reopened after a claimed fix: README.md:x, codex/README.md:x', result.stderr)
        self.assertEqual(self.start(correction=True, design=True,
                                    widen='fixture: this case is about keys, not about scope'
                                    )['reopened'], ['README.md:x', 'codex/README.md:x'])

    def prepare_scope_fixture(self):
        """A campaign whose one open finding names a file git would C-quote.

        The name is non-ASCII on purpose: the two sides of the rule read git separately,
        and each quotes such a path unless told otherwise. A comparison where one side
        quotes and the other does not refuses the very file it was given.
        """
        (self.repo / 'café.txt').write_text('the finding names this\n')
        (self.repo / 'sub').mkdir()
        (self.repo / 'sub/keep.txt').write_text('somewhere to stand\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'add the named file and a subdirectory')
        self.start()
        self.report('claude', [dict(id='café.txt:wrong', kind='defect', priority='P1',
                                    evidence='wrong')])
        self.report('codex', [])
        self.triage([dict(id='claude::café.txt:wrong', status='open', evidence='Confirmed')])
        (self.repo / 'café.txt').write_text('fixed\n')
        probe = self.root / 'probe.json'
        probe.write_text(json.dumps([dict(command='c', expected='e', observed='e')]))
        return [str(FLOW), 'start', '--base', self.base, '--context', str(self.context),
                '--probe', str(probe), '--no-regression-reason', 'fixture']

    def start_from(self, arguments, where):
        """Run `start` from a given directory, since the rule must not depend on one."""
        return subprocess.run([sys.executable, *arguments], cwd=where,
                              capture_output=True, text=True, timeout=10)

    def test_touching_only_the_named_file_is_not_widening(self):
        """However git spells that name.

        Run from the subdirectory, and only once: `start` is idempotent for an unchanged
        candidate, so a second call returns the state the first one wrote without reaching
        the rule at all. Two calls would read as two cases and be one.
        """
        arguments = self.prepare_scope_fixture()
        self.git('add', '-A')
        self.git('commit', '-qm', 'fix only what the finding named')
        result = self.start_from(arguments, self.repo / 'sub')
        self.assertEqual(result.returncode, 0, 'a correction touching only the named file was '
                                               f'refused: {result.stderr}')

    def test_a_name_that_begins_with_whitespace_is_still_its_own_file(self):
        """Trimming a NUL-delimited listing edits filenames, and an edited name collapses.

        A path beginning with a tab, trimmed, becomes the path a finding did name, so the
        file nobody asked for disappears from the comparison that exists to catch it.
        """
        arguments = self.prepare_scope_fixture()
        (self.repo / '\tcafé.txt').write_text('a different file entirely\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'fix, and a file whose name starts with a tab')
        result = self.start_from(arguments, self.repo)
        self.assertEqual(result.returncode, 2, 'the tab-prefixed file collapsed onto the named one')
        self.assertIn('café.txt', result.stderr.split('No open finding names:')[1])

    def test_a_file_no_finding_named_is_caught_from_any_directory(self):
        """`git diff` is root-relative; a listing that is not would make the rule silent."""
        arguments = self.prepare_scope_fixture()
        (self.repo / 'unasked.txt').write_text('a file nobody asked for\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'fix, and one more thing')
        for where in (self.repo, self.repo / 'sub'):
            result = self.start_from(arguments, where)
            self.assertEqual(result.returncode, 2, f'from {where.name} the rule stayed silent')
            blamed = result.stderr.split('No open finding names:')[1]
            self.assertIn('unasked.txt', blamed)
            # Assert on the stem: a mismatched comparison would print the quoted spelling,
            # which shares no full substring with the unquoted one.
            self.assertNotIn('caf', blamed)


    def test_a_correction_may_delete_the_file_its_finding_named(self):
        """Deleting the file is a fix, and the rule must not read that as erased evidence.

        The findings describe the candidate that was reviewed, so their paths are looked up
        there. Looking them up in the corrected tree let a correction remove its own scope
        evidence by doing exactly what it was told to do.
        """
        (self.repo / 'doomed.txt').write_text('remove me\n')
        self.git('add', 'doomed.txt')
        self.git('commit', '-qm', 'add the file a finding will name')
        self.start()
        self.report('claude', [dict(id='doomed.txt:should-not-exist', kind='defect',
                                    priority='P1', evidence='this file should not be here')])
        self.report('codex', [])
        self.triage([dict(id='claude::doomed.txt:should-not-exist', status='open',
                          evidence='Confirmed')])
        (self.repo / 'doomed.txt').unlink()
        self.git('add', '-A')
        self.git('commit', '-qm', 'remove it')
        self.start(correction=True)

    def test_widening_exempts_what_this_module_calls_a_test(self):
        """One classifier, not two: the loose pattern calls `v1.spec.yaml` a test and it is not."""
        (self.repo / 'named.txt').write_text('the finding names this\n')
        self.git('add', 'named.txt')
        self.git('commit', '-qm', 'add the named file')
        self.start()
        self.report('claude', [dict(id='named.txt:wrong', kind='defect', priority='P1',
                                    evidence='wrong')])
        self.report('codex', [])
        self.triage([dict(id='claude::named.txt:wrong', status='open', evidence='Confirmed')])
        (self.repo / 'named.txt').write_text('fixed\n')
        (self.repo / 'openapi').mkdir()
        (self.repo / 'openapi/v1.spec.yaml').write_text('openapi: 3.1.0\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'fix, and change a spec that is not a test')
        refused = self.start(ok=False, correction=True).stderr
        self.assertIn('openapi/v1.spec.yaml', refused)

    def test_a_correction_may_not_touch_what_no_finding_named(self):
        """This is where every bad round of this branch went bad: a fix arrived with a mechanism.

        The finding names one file; the correction brings a new one along; the next review
        reads it and finds the next defect. A correction answers what was found. Tests and
        the generated bundle are how a fix is proved and shipped, so they do not count.
        """
        self.start()
        self.report('claude', [dict(id='code.txt:wrong-answer', kind='defect', priority='P1',
                                    evidence='returns the wrong value')])
        self.report('codex', [])
        self.triage([dict(id='claude::code.txt:wrong-answer', status='open', evidence='Confirmed')])
        self.commit('fixed')
        (Path(self.repo) / 'extra.txt').write_text('a mechanism nobody asked for\n')
        self.git('add', 'extra.txt')
        self.git('commit', '-qm', 'and one more thing')
        refused = self.start(ok=False, correction=True).stderr
        self.assertIn('answers the open findings and nothing else', refused)
        self.assertIn('extra.txt', refused)

        widened = self.start(correction=True, widen='Max asked for it in the session')
        self.assertEqual(widened['widen_scope'], 'Max asked for it in the session')
        self.assertIn('touches files no open finding named', self.text('prompt'))

    def test_a_round_is_spent_on_a_defect_not_on_nits(self):
        """A correction round needs an open finding above P3, or a recorded reason.

        Correcting text no test can check is where a review loop starts: each correction is
        new surface for the next review, so nits are deferred and batched instead.
        """
        self.start()
        nit = dict(id='docs:wording', kind='nit', priority='P3', evidence='Sentence reads oddly')
        bug = dict(id='guard:spelling', kind='defect', priority='P1', evidence='Bypass reproduced')
        self.report('claude', [nit])
        self.report('codex', [])
        self.triage([dict(id='claude::docs:wording', status='open', evidence='Confirmed')])
        self.commit('correct the wording')
        refused = self.start(ok=False, correction=True, nit='').stderr
        self.assertIn('Every open finding is P3', refused)
        self.assertIn('--nit-round', refused)
        # Recorded, the round proceeds and both reviewers are told why.
        state = self.start(correction=True, nit='the wording misleads a reader of the protocol')
        self.assertEqual(state['round'], 2)
        self.assertIn('spent on P3 findings', self.flow('prompt').stdout)
        # A blocking finding needs no such reason; the nit is deferred, not carried open.
        keep = [dict(id='claude::docs:wording', evidence='reworded in this delta')]
        self.report('claude', [bug], resolutions=keep)
        self.report('codex', [], resolutions=keep)
        self.triage([dict(id='claude::guard:spelling', status='open', evidence='Reproduced')])
        self.commit('fix the guard')
        self.assertEqual(self.start(correction=True, nit='')['round'], 3)

    def test_a_nit_filed_at_a_high_priority_still_does_not_buy_a_round(self):
        """`start` and `finish` must agree on what blocks: kind and priority, not priority alone."""
        self.start()
        loud = dict(id='docs:wording', kind='nit', priority='P1', evidence='reads oddly')
        self.report('claude', [loud])
        self.report('codex', [])
        self.triage([dict(id='claude::docs:wording', status='open', evidence='Confirmed')])
        self.commit('reword')
        refused = self.start(ok=False, correction=True, nit='').stderr
        self.assertIn('Every open finding is P3', refused)

    def test_a_campaign_kept_aside_is_found_however_it_was_renamed(self):
        """The runtime's own recovery messages name a rename; each spelling must be seen."""
        for suffix, prefix in (('.archived', ''), ('', 'archived-'), ('-kept-aside', 'old-')):
            self.start()
            directory = Path(self.flow('status')['directory'])
            aside = directory.parent / (prefix + directory.name + suffix)
            directory.rename(aside)
            refused = self.start(ok=False).stderr
            self.assertIn('kept aside without clearing', refused)
            self.assertIn(aside.name, refused)
            shutil.rmtree(aside)

    def test_range_answers_only_while_the_campaign_is_the_scope_in_hand(self):
        """The gate's fenced shell cannot reach this state, so this is what it asks.

        A copy of the endpoints, written once and read later, outlived what it described,
        and the shell grew one predicate per round trying to tell. Nothing is kept now:
        the campaign is read when the question is asked, and an empty answer means the
        caller's scope is its own working tree, which is what a preview reviews.
        """
        self.assertEqual(self.text('range'), '', 'a branch with no campaign has no range')
        state = self.start()
        self.assertEqual(self.text('range'), f"{state['review_base']}..{state['head']}")

        # A dirty tree is not the scope a campaign froze; clean_head() is that definition,
        # and it counts untracked work, which a `git diff` in the document would not.
        (Path(self.repo) / 'untracked.txt').write_text('new\n')
        self.assertEqual(self.text('range'), '', 'a dirty tree still answered with a range')
        (Path(self.repo) / 'untracked.txt').unlink()
        self.assertNotEqual(self.text('range'), '', 'the range did not come back with the tree')

        self.complete()
        self.assertEqual(self.text('range'), '', 'a cleared campaign still owns a scope')

    def test_a_campaign_kept_aside_in_place_is_found_too(self):
        """read_state used to recommend this spelling, so it is the one a caller reaches for."""
        self.start()
        directory = Path(self.flow('status')['directory'])
        (directory / 'state.json').rename(directory / 'state.json.kept-aside')
        refused = self.start(ok=False).stderr
        self.assertIn('kept aside without clearing', refused)
        self.assertIn('state.json renamed', refused)

    def test_the_recovery_messages_name_the_rename_the_refusal_reads(self):
        """A message that names another spelling would send the caller past the guardrail."""
        source = FLOW.read_text()
        # Detection needs the whole directory name as a substring, so guidance that asks
        # only for "the branch hash" walks a caller into an abbreviation that evades it.
        for message in ('renaming its directory, keeping its ',
                        'state directory keeping its whole current name and adding to it'):
            self.assertIn(message, source)
        self.assertNotIn('branch hash still in', source)

    def test_starting_over_after_an_unfinished_campaign_needs_authorization(self):
        """Exhausting the budget hands the work to a human; archiving is not a way around it."""
        self.start()
        directory = Path(self.flow('status')['directory'])
        aside = directory.parent / ('archived-fixture-' + directory.name)
        aside.mkdir(parents=True)
        (aside / 'state.json').write_text(json.dumps(dict(head='0' * 40, round=3, cleared=False)))
        (directory / 'state.json').unlink()
        refused = self.start(ok=False).stderr
        self.assertIn('kept aside without clearing', refused)
        self.assertIn('--after-archived', refused)
        result = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base,
                                 '--context', str(self.context), '--after-archived',
                                 'Max authorised a fresh campaign for the hook probe only'],
                                cwd=self.repo, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('authorised to start over', self.flow('prompt').stdout)

    def test_the_command_the_notice_names_writes_both_files_it_checks(self):
        """A notice whose exit condition no command can reach would fire forever."""
        document = (ROOT / 'plugins/bymax-quality/commands/review-md.md').read_text()
        steps = document.split('## Steps', 1)[1].split('## Template', 1)[0]
        self.assertIn('Write `REVIEW.md`', steps)
        self.assertIn('Write the `## Code Review Rules` section of `AGENTS.md`', steps)
        self.assertIn('## Code Review Rules', document.split('## Template — the `AGENTS.md`', 1)[1])

    def test_a_repository_without_review_rules_is_told_once(self):
        """The PR bots read files a repository must carry; a campaign says so and continues."""
        result = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base,
                                 '--context', str(self.context)],
                                cwd=self.repo, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('REVIEW.md', result.stderr)
        self.assertIn('Code Review Rules', result.stderr)
        self.assertIn('review-md', result.stderr)
        # With both files present a first campaign is silent about them.
        shutil.rmtree(Path(self.flow('status')['directory']))
        (self.repo / 'REVIEW.md').write_text('# Review instructions\n')
        (self.repo / 'AGENTS.md').write_text('## Code Review Rules\n\nOne narrow rule.\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'add the review rules')
        result = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base,
                                 '--context', str(self.context)],
                                cwd=self.repo, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('review-md', result.stderr)

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
        # Deleting that test is not a regression: a correction that leaves the candidate
        # without one needs a recorded reason, which reaches both reviewers.
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
