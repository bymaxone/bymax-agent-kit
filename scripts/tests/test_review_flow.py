"""Regression layer: exercise review state and push guards in isolated Git repositories."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

INHERIT = object()  # push(): use whatever Codex this test's campaign ran against

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
        # None: the developer machine's own Codex, whatever it is. A test that simulates a
        # machine sets this once, and every command of that campaign then sees that machine —
        # the probe runs in the runtime, in the Bash guard and in the hook, and a campaign
        # whose steps disagreed about what is installed would be testing nothing.
        self.locations = None
        self.root = Path(self.temp.name)
        # Its own CODEX_HOME, so no test reads the developer's real Codex profiles and a
        # machine that has one bound cannot change what a fixture observes.
        self.home = self.root / 'codex-home'
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.commit('base')
        self.base = self.git('rev-parse', 'HEAD')
        self.context = self.root / 'context.md'
        self.context.write_text(json.dumps(dict(intent='Fix requested feature', acceptance=['Preserve callers'],
            measured=['ran the fixture gate against the candidate tree: 1 file read, nonempty'], constraints=['No unrelated changes'], scope='Candidate against base',
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
        argv = ([sys.executable, str(FLOW)] if self.locations is None
                else self.sealed('review_flow', 'cli', self.locations))
        env = dict(os.environ, CODEX_HOME=str(self.home)) if self.locations is None else self.codex_env()
        result = subprocess.run([*argv, *args], cwd=self.repo, capture_output=True, text=True,
                                timeout=60, env=env)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr)
        return json.loads(result.stdout) if result.returncode == 0 and result.stdout.startswith('{') else result

    def sealed(self, module, entry, locations=()):
        """argv running <module>.<entry> in a process whose Codex resolution table is this
        test's own.

        Production resolves Codex from a fixed list of install locations and, only as a last
        resort, $PATH — so a test cannot hand it a binary through the environment, which is
        exactly the property being protected. The table is replaced in-process instead.
        """
        return [sys.executable, '-c',
                'import sys; sys.path.insert(0, %r)\n'
                'import review_prepush; review_prepush.CODEX_LOCATIONS = %r\n'
                'import %s as entry; entry.%s()'
                % (str(FLOW.parent), tuple(str(p) for p in locations), module, entry)]

    def codex_env(self):
        """The environment with every $PATH entry that holds a codex removed."""
        entries = [e for e in os.environ.get('PATH', '').split(os.pathsep)
                   if e and not os.access(os.path.join(e, 'codex'), os.X_OK)]
        return dict(os.environ, PATH=os.pathsep.join(entries), CODEX_HOME=str(self.home))

    def codex_run(self, *args, locations=(), timeout=60):
        """Run a lifecycle command against a Codex that is only what this test installed."""
        return subprocess.run([*self.sealed('review_flow', 'cli', locations), *args], cwd=self.repo,
                              env=self.codex_env(), capture_output=True, text=True, timeout=timeout)

    def fake_codex(self, script):
        """Install a stand-in Codex binary and return its path."""
        binary_dir = self.root / 'bin'
        binary_dir.mkdir(exist_ok=True)
        binary = binary_dir / 'codex'
        binary.write_text(script)
        binary.chmod(0o755)
        return binary

    def text(self, *args):
        """Invoke a lifecycle command that answers in plain text rather than state."""
        result = subprocess.run([sys.executable, str(FLOW), *args], cwd=self.repo,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def matrix(self, path, cases):   # cases: (anchor, becomes, case)
        """Run a real mutation matrix in the fixture repo, because nothing here fakes one.

        A correction that changes a test must carry a measured matrix, and a fixture that
        wrote the record by hand would make the gate satisfiable by typing — which is the
        defect the gate exists to remove. `cases` is (anchor, case) per function the file
        defines, so the enumeration command and the mutant count agree by construction.
        """
        spec = self.root / 'matrix.json'
        spec.write_text(json.dumps([{
            'rule': 'fixture: one mutant per case the file defines',
            'enumeration': 'grep -c "def test_" %s' % path,
            'mutants': [{'file': path, 'anchor': anchor, 'becomes': becomes, 'case': case}
                        for anchor, becomes, case in cases]}]))
        return self.flow('matrix', '--spec', str(spec), path)


    def start(self, ok=True, correction=False, design=False, probe=None, reason='fixture: no test needed',
              nit='fixture: no blocking finding in play', widen='', answers=(), extend='', autonomous=False):
        """Start or reuse a candidate; a correction round carries its probe and test evidence.

        A round needs a blocking finding or a recorded reason for spending it on nits; a
        fixture exercising another rule passes the reason so that rule stays in view.
        """
        args = ['start', '--base', self.base, '--context', str(self.context)]
        if correction:
            path = self.root / 'probe.json'
            # The default entry carries without_fix because a correction that touches a test
            # must show it failing; a fixture exercising another rule should not have to know
            # that. The case that owns the rule passes its own probe, with and without it.
            path.write_text(json.dumps(probe if probe is not None else [
                dict(command='python3 -c "print(1)"', expected='1', observed='1',
                     without_fix='fixture: reverted the change and the case failed')]))
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

    TRIGGER = 'python3 -m pytest tests/test_regression.py::test_the_invariant'

    def report(self, name, findings=None, resolutions=None, ok=True):
        """Provide a completed reviewer fixture for the current endpoints.

        A blocking finding names the command that makes the defect appear, so a fixture that
        means "a blocker" gets one by default and a fixture exercising some other rule need
        not know the field exists. Copies, never the caller's dicts: several cases report the
        same finding twice and then compare it. The cases that own the trigger rule set the
        field themselves, present or absent, and are unaffected by this.
        """
        items = [dict(item) for item in (findings or [])]
        for item in items:
            if (item.get('kind') in ('defect', 'policy') and item.get('priority') != 'P3'
                    and 'trigger' not in item):
                item['trigger'] = self.TRIGGER
        # trigger=None means the reviewer never wrote the field, which is how a real report
        # that omits it arrives; an empty string would be a reviewer claiming an empty command.
        items = [{k: v for k, v in item.items() if not (k == 'trigger' and v is None)}
                 for item in items]
        state = self.flow('status')
        path = self.root / (name + '.json')
        path.write_text(json.dumps(dict(status='completed', head=state['head'], base=state['review_base'], summary='Inspected fixture',
                                       findings=items, resolutions=resolutions or [])))
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

    def push(self, command, cwd=None, ok=True, locations=INHERIT):
        """Invoke only the guard, never a real push.

        locations, when given, drives the guard through the same sealed entry point the
        campaign used, so a receipt waived against an absent Codex is re-checked against
        the absence the test created rather than the developer machine's own install.
        """
        payload = dict(cwd=str(cwd or self.repo), tool_input=dict(command=command))
        locations = self.locations if locations is INHERIT else locations
        argv = ([sys.executable, str(PUSH)] if locations is None
                else self.sealed('review_push', 'cli', locations))
        result = subprocess.run(argv, input=json.dumps(payload), text=True, capture_output=True,
                                env=self.codex_env() if locations is not None else None)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr)
        return result

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

    def test_the_guard_lets_a_command_that_only_reads_name_the_hook(self):
        """A guard that blocks reading protects nothing: no rev-parse reaches a remote, and
        the refusal taught whoever met it to phrase commands to slip past a matcher, which is
        the habit the guard exists to prevent. Measured on this machine, each of these was
        refused while it held: the first is prescribed by /bymax-pr:push Step 0, so the shipped
        command file could not be followed as written, and the third and fourth were hit twice
        in one session by a grep whose PATTERN carried a token."""
        self.start()
        self.complete()
        for command in ('git rev-parse --git-dir', 'git -C . rev-parse --git-dir',
                        'shasum .git/hooks/pre-push', 'cat .git/hooks/pre-push',
                        'grep -rn "core.hooksPath" scripts/', 'echo --no-verify',
                        'git config --get core.hooksPath', 'git log --oneline -3'):
            self.push(command)

    def test_a_command_that_could_not_reach_a_remote_is_never_scanned(self):
        """What the first attempt at this got wrong, plus the two shapes both reviewers used to
        break it and the two this repository's own command files prescribe.

        These pass and are meant to. This adapter refuses a push spelled to skip the receipt
        check; it does not defend the hook file, and two rounds spent trying taught why: every
        local check of the hook is undone by the same shell the check is defending against, and
        each layer was found bypassable in the round after it. `start` reinstalls and
        re-verifies the hook, which is when it matters, and CI is the boundary for deliberate
        evasion — which is what the protocol always said. None can push: the
        first three name no program able to start another, and the last two contain no `push`
        at all. Each was refused while the scan ran on every command."""
        self.start()
        self.complete()
        for command in ('git rev-parse --git-dir', 'shasum .git/hooks/pre-push', 'cat .git/hooks/pre-push',
                        'grep -rn "core.hooksPath" scripts/', 'echo --no-verify',
                        'git config --get core.hooksPath', 'sort -o out.txt in.txt',
                        # One of the escapes that broke the allowlist, allowed to run: what it
                        # does to the hook is caught by the case above, not by a matcher.
                        # (The ls-remote escape is not here because it names git and a path
                        # spelling "push", so the scan applies to it — incidentally, not
                        # because the mechanism recognised what it does.)
                        'rg --pre rm pattern .git/hooks/pre-push',
                        # Prescribed by plugins/bymax-workflow/commands/verify.md and by
                        # plugins/bymax-quality/commands/code-review.md; both were refused.
                        "git diff HEAD | grep -nE '(--no-verify|--skip-checks)'",
                        "git log --oneline | grep -E -- '--no-verify'"):
            self.push(command)

    def test_a_disarming_option_is_still_refused_wherever_it_appears(self):
        """The scan did not get weaker: it got a precondition. Every shape that could reach a
        remote is still read for a hook-skipping option, in any arrangement."""
        self.start()
        self.complete()
        for command in ('git -c core.hooksPath=/dev/null push origin HEAD',
                        'GIT_DIR=/other/.git git push origin HEAD',
                        'cd . && git --git-dir=/x push origin HEAD',
                        'sh -c "git push --no-verify origin HEAD"',
                        'xargs git push --no-verify origin HEAD',
                        'env HUSKY=0 git push origin HEAD',
                        'eval git push --no-verify origin HEAD',
                        # The precondition reads the parsed words, not the raw text: these two
                        # spell the verb so that the raw command holds no "push" substring at
                        # all, while the shell and git still see a push. Measured on the
                        # previous candidate: returned as no-opinion, and the commit reached
                        # the remote with the hook present and never invoked.
                        'git -c core.hooksPath=/dev/null pu""sh origin HEAD',
                        'git -c core.hooksPath=/dev/null pu\\sh origin HEAD',
                        # And the mirror image: the verb is plain and the TOKEN is split across
                        # quotes, so the raw command holds no `hooksPath` while the words the
                        # shell hands git do. Reading one form and not the other was the half of
                        # the previous round's repair I left undone, one line below the half I made.
                        'git -c core.hooks""Path=/dev/null push origin HEAD',
                        'git -c core.hooks\\Path=/dev/null push origin HEAD'):
            self.push(command, ok=False)

    def test_adapter_refuses_what_would_disarm_the_hook(self):
        """Options that skip hooks or redirect git are refused wherever they appear, in any
        command that could reach a remote.

        `rm` and `chmod -x` on the hook used to be on this list and are not any more: the
        mechanism stopped classifying commands, because the list of readers that can run a
        program of the caller's choosing has no closed form and both reviewers emptied it in one
        round. What those refusals were standing in front of — remove the hook, then push in a
        shape parse() does not judge — is not held by anything here, deliberately: two attempts
        to hold it locally were each bypassed in the round after they shipped, and the protocol
        names the residue instead of covering it.
        """
        self.start()
        self.complete()
        for command in ('git push --no-verify origin HEAD', 'eval git push --no-verify origin HEAD',
                        'git -c core.hooksPath=/dev/null push origin HEAD',
                        'GIT_DIR=/other/.git git push origin HEAD', 'git --git-dir=/x push origin HEAD',
                        'echo x > .git/hooks/pre-push && git push origin HEAD',
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
        self.checks()
        reserve = ('import sys; sys.path.insert(0, ' + repr(str(FLOW.parent)) + '); '
                   'import review_flow as flow; flow.reserve_codex(flow.location())')
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
        self.checks()
        prompt = self.flow('prompt')
        self.assertIn('DESIGN ROUND', prompt.stdout)

    def test_the_first_round_brief_carries_the_code_view(self):
        """The round that reads the WHOLE delta used to receive none of the three views: they
        were built inside correction_brief, which returns early on round one, while the
        changelog said every reviewer receives them. Round one is where 'these checks read
        NOTHING in N changed files of other kinds' matters most — on a repository of languages
        they cannot read, that sentence is what stops silence from reading as clean."""
        self.start()
        self.checks()
        brief = self.flow('prompt').stdout
        self.assertIn('prose elided', brief)
        self.assertIn('Prose in this delta', brief)

    def test_the_first_round_brief_names_the_tests_the_delta_changed(self):
        """The note read a key only a correction round sets, and the round it was first shown
        on round one it said "No test changed in this delta. Recorded reason: ." about a
        delta that changed four test files. It reads the diff now, on every round."""
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_x.py').write_text('def test_x(): assert 1 == 1\n')
        self.commit('a candidate that adds a test')
        self.start()
        self.checks()
        brief = self.flow('prompt').stdout
        self.assertIn('Tests changed in this delta: tests/test_x.py', brief)
        self.assertNotIn('Recorded reason: .', brief)

    PROSE = ('LIMIT = 10\n'
             '# Six attempts at this rule, and it guards the limit.\n'
             'def over(value):\n'
             '    """Whether value exceeds the limit."""\n'
             '    return value > LIMIT\n')
    CORRECTED = '# Guards the limit because callers pass unbounded input.'

    def fake_claude(self, edit):
        """A stand-in `claude` on $PATH that ignores its task and applies one edit to thing.py."""
        binary_dir = self.root / 'claude-bin'
        binary_dir.mkdir(exist_ok=True)
        binary = binary_dir / 'claude'
        binary.write_text('#!/bin/sh\ncat > /dev/null\n%s - <<\'EOF\'\nfrom pathlib import Path\n'
                          'p = Path("thing.py"); p.write_text(p.read_text().replace(%r, %r))\nEOF\n'
                          'echo \'{"is_error": false}\'\n' % (sys.executable, *edit))
        binary.chmod(0o755)
        return binary_dir

    def prose(self, *args, claude=None, nested=False, ok=True, cwd=None):
        """Run the prose subcommand in a process whose $PATH and Claude nesting this test decides."""
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDECODE'}
        if nested:
            env['CLAUDECODE'] = '1'
        if claude is not None:
            env['PATH'] = str(claude) + os.pathsep + env.get('PATH', '')
        env['CODEX_HOME'] = str(self.home)
        result = subprocess.run([sys.executable, str(FLOW), 'prose', *args], cwd=cwd or self.repo,
                                capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr + result.stdout)
        return json.loads(result.stdout) if ok and result.stdout.startswith('{') else result

    def add_prose(self, text=None):
        (self.repo / 'thing.py').write_text(text or self.PROSE)
        self.git('add', '-A')
        self.git('commit', '-qm', 'a candidate that adds prose')

    def read_prose(self):
        """The pass in two stages with no edits between: the record binds the candidate's prose
        even when the reader changed nothing, which is what a fixture that adds markdown needs
        before start will accept it."""
        self.prose('--base', self.base, '--stage', 'prepare', nested=True)
        return self.prose('--base', self.base, '--stage', 'verify', nested=True)

    def test_the_prose_pass_refuses_a_dirty_worktree(self):
        """The envelope compares the worktree to HEAD, so with the author's own edits in the
        tree the pass's edits would be indistinguishable from them."""
        (self.repo / 'thing.py').write_text(self.PROSE)
        self.assertIn('worktree is dirty', self.prose('--base', self.base, ok=False).stderr)

    def test_a_delta_that_adds_no_prose_records_a_skipped_pass_and_needs_none(self):
        self.commit('code only')
        record = self.prose('--base', self.base)
        self.assertEqual(record['outcome'], 'skipped')
        self.start()
        self.checks()
        self.assertIn('added no prose, so no prose pass ran', self.flow('prompt').stdout)

    def test_the_prose_pass_records_what_a_correcting_reader_left(self):
        """The whole mechanism end to end: a fresh Claude corrects a comment, the envelope
        holds, the record binds to the text it left, and the candidate carrying that text
        starts with a brief telling the logic reviewers wording is not theirs."""
        self.add_prose()
        record = self.prose('--base', self.base, claude=self.fake_claude(
            ('# Six attempts at this rule, and it guards the limit.', self.CORRECTED)))
        self.assertEqual((record['outcome'], record['changed'], record['files']),
                         ('corrected', ['thing.py'], ['thing.py']))
        self.assertIn(self.CORRECTED, (self.repo / 'thing.py').read_text())
        self.git('commit', '-qam', 'prose corrected before the freeze')
        self.assertEqual(self.start()['prose']['outcome'], 'corrected')
        self.checks()
        brief = self.flow('prompt').stdout
        # What the record proves, not more: the runtime never observes the reader, so the
        # note that said 'a fresh reader corrected' claimed a reading it could not show.
        self.assertIn('The prose pass ran before the freeze', brief)
        self.assertIn('the record proves the text and not the reading', brief)
        self.assertIn('Wording is still not yours to review', brief)

    def test_a_pass_that_edits_code_is_refused_and_reverted(self):
        """The one outcome worse than the defect: reviewers are told the pass touched no
        behaviour. The tree was clean when the pass started, so everything it left is its
        own and is put back; no record is written."""
        self.add_prose()
        refused = self.prose('--base', self.base, ok=False,
                             claude=self.fake_claude(('value > LIMIT', 'value >= LIMIT')))
        self.assertIn('left the envelope', refused.stderr)
        self.assertIn('behaviour changed', refused.stderr)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(list((self.repo / '.git').glob('bymax-review/*/prose-*.json')), [])

    def test_start_refuses_a_candidate_whose_prose_no_pass_read(self):
        self.add_prose()
        self.assertIn('no prose pass read it', self.start(ok=False).stderr)

    def test_start_refuses_a_record_bound_to_other_text(self):
        """The author edits the prose again after the pass: the record's digest no longer
        matches the candidate, so what the reviewers would be handed was never read."""
        self.add_prose()
        self.prose('--base', self.base, claude=self.fake_claude(
            ('# Six attempts at this rule, and it guards the limit.', self.CORRECTED)))
        self.git('commit', '-qam', 'prose corrected')
        (self.repo / 'thing.py').write_text(self.PROSE.replace('Six attempts', 'Seven attempts'))
        self.git('commit', '-qam', 'and then edited again by hand')
        self.assertIn('bound to other text', self.start(ok=False).stderr)

    def test_inside_claude_the_pass_prepares_and_verifies_in_two_stages(self):
        """A Claude cannot start a Claude, so inside one the runtime hands the task out and
        checks what came back, and the record is the same either way."""
        self.add_prose()
        self.assertIn('Inside Claude', self.prose('--base', self.base, nested=True, ok=False).stderr)
        task = self.prose('--base', self.base, '--stage', 'prepare', nested=True).stdout
        self.assertIn('Keep every sentence that says WHY', task)
        self.assertIn('--- thing.py', task)
        (self.repo / 'thing.py').write_text(self.PROSE.replace(
            '# Six attempts at this rule, and it guards the limit.', self.CORRECTED))
        record = self.prose('--base', self.base, '--stage', 'verify', nested=True)
        self.assertEqual(record['outcome'], 'corrected')
        self.git('commit', '-qam', 'prose corrected by a subagent')
        self.assertEqual(self.start()['round'], 1)

    def test_verify_without_a_prepare_at_this_head_is_refused(self):
        """Without the marker, verify on a dirty tree would bless the author's own edits as
        a pass that changed only prose."""
        self.add_prose()
        (self.repo / 'thing.py').write_text(self.PROSE.replace('Six attempts', 'Seven attempts'))
        self.assertIn('Nothing was prepared', self.prose('--stage', 'verify', nested=True, ok=False).stderr)

    def test_start_refuses_a_record_that_covers_other_files(self):
        """The record digested the files the pass saw,
        so prose committed afterwards in a file outside that set reached the reviewers under
        a note saying a reader had seen it. The candidate's own touched set must be the
        record's."""
        self.add_prose()
        self.read_prose()
        (self.repo / 'NOTES.md').write_text('# Notes\n\nover() never returns for negative input.\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'prose in a file no reader saw')
        self.assertIn('in these files', self.start(ok=False).stderr)

    def test_after_a_cleared_campaign_the_pass_reads_from_the_given_base(self):
        """start treats a cleared, non-autonomous campaign as no campaign and opens a first
        round from the merge-base; the pass read from the cleared head instead, so the
        record's base never matched and start's own remedy looped."""
        self.start()
        self.complete()
        self.flow('finish')
        self.add_prose()
        record = self.read_prose()
        self.assertEqual(record['base'], self.base)
        self.assertEqual(self.start()['round'], 1)

    def test_a_staged_code_edit_is_reverted(self):
        """`git checkout --` restores the index, so a staged edit survived while the refusal
        said it had been reverted."""
        self.add_prose()
        self.prose('--base', self.base, '--stage', 'prepare', nested=True)
        (self.repo / 'thing.py').write_text(self.PROSE.replace('value > LIMIT', 'value >= LIMIT'))
        self.git('add', 'thing.py')
        self.assertIn('left the envelope', self.prose('--stage', 'verify', nested=True, ok=False).stderr)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_the_revert_works_from_a_subdirectory(self):
        """changed() names paths from the worktree root; the checkout resolved them against
        the process cwd, failed, and left the code edit in place."""
        (self.repo / 'sub').mkdir()
        (self.repo / 'sub/k.txt').write_text('k\n')
        self.add_prose()
        self.prose('--base', self.base, '--stage', 'prepare', nested=True)
        (self.repo / 'thing.py').write_text(self.PROSE.replace('value > LIMIT', 'value >= LIMIT'))
        refused = self.prose('--stage', 'verify', nested=True, ok=False, cwd=self.repo / 'sub')
        self.assertIn('left the envelope', refused.stderr)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_a_directory_the_pass_created_is_removed(self):
        """An untracked directory is one porcelain row, and unlink() refused it with an errno
        that reached the author instead of the envelope refusal."""
        self.add_prose()
        self.prose('--base', self.base, '--stage', 'prepare', nested=True)
        (self.repo / 'newdir').mkdir()
        (self.repo / 'newdir/x.md').write_text('# x\n')
        refused = self.prose('--stage', 'verify', nested=True, ok=False)
        self.assertIn('left the envelope', refused.stderr)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_a_reader_that_fails_leaves_no_edits(self):
        """A reader that edited code and then exited non-zero left the edit in the tree, and
        the next pass refused a dirty worktree it had made itself."""
        self.add_prose()
        binary_dir = self.fake_claude(('value > LIMIT', 'value >= LIMIT'))
        script = (binary_dir / 'claude').read_text().replace('echo \'{"is_error": false}\'', 'exit 1')
        (binary_dir / 'claude').write_text(script)
        refused = self.prose('--base', self.base, ok=False, claude=binary_dir)
        self.assertIn('its edits were reverted', refused.stderr)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_a_correction_round_reads_prose_since_the_frozen_head(self):
        """No --base once a campaign is frozen: the delta is what changed since that head.
        And on the frozen head itself the pass refuses, because editing what reviewers were
        handed invalidates their reading rather than improving it."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        frozen = self.git('rev-parse', 'HEAD')
        self.assertIn('frozen under review', self.prose(ok=False).stderr)
        self.add_prose()
        record = self.prose('--stage', 'prepare', nested=True)
        self.assertIn('--- thing.py', record.stdout)
        self.assertEqual(self.prose('--stage', 'verify', nested=True)['base'], frozen)

    def test_the_matrix_runs_before_the_first_start(self):
        """Round one has no campaign to read, and the documents say commit, matrix, start:
        the measurement the author takes on the first candidate must not be refused with
        "No review campaign", which is true and not what was wrong."""
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_first.py').write_text('def test_first(): assert 1 == 1\n')
        self.commit('a first candidate with a test')
        run = self.matrix('tests/test_first.py', [('1 == 1', '1 == 2', 'test_first')])
        self.assertIn('1 mutant(s), all caught', run.stdout)
        head = self.git('rev-parse', 'HEAD')
        self.assertTrue(list((self.repo / '.git').glob('bymax-review/*/matrix-%s.json' % head)))
        self.assertEqual(self.start()['round'], 1)

    def test_a_refused_matrix_blocks_like_every_other_refusal(self):
        """bail() refused by raising SystemExit with a message, which exits 1, while every
        other refusal in the runtime exits 2 — so a caller keying on 2 for BLOCKED read a
        surviving mutant as a different class of failure. It also made these refusals
        untestable here: this helper asserts 2, so no case could reach them through the CLI."""
        self.start()
        spec = self.root / 'empty-matrix.json'
        spec.write_text('[]')
        refused = self.flow('matrix', '--spec', str(spec), 'scripts/tests', ok=False)
        self.assertIn('non-empty list of rules', refused.stderr)

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
        self.checks()
        prompt = self.flow('prompt')
        self.assertIn('eval git push', prompt.stdout)
        self.assertIn('Shallow probing is a finding', prompt.stdout)
        # A probe the reviewer's sandbox cannot run is a limitation to state, not `incomplete`.
        self.assertIn('is a limitation to state in your summary, not a reason to report incomplete', prompt.stdout)

    def test_a_finding_with_nothing_to_run_cannot_hold_the_receipt(self):
        """The runtime trusted the label the reviewer typed, so a sentence about a docstring
        arrived as a P2 defect, finish refused to clear it and refused to let it be deferred,
        and the budget went on prose. Measured over two campaigns in two repositories: every
        finding worth a round could name a command and every finding that wasted one could not.
        It is still recorded, still triaged, still shown to the next reviewer — it just cannot
        refuse a receipt while two readers argue about a label."""
        prose = dict(id='code.txt:docstring-contradicts-the-code', kind='defect', priority='P2',
                     evidence='the sentence names a return arity the function no longer has',
                     trigger=None)
        self.start()
        self.checks()
        # The author is told, on stderr, rather than the report being rejected: a reviewer that
        # omitted the field still produced a review, and a real defect is still theirs to fix.
        path = self.root / 'claude.json'
        state = self.flow('status')
        path.write_text(json.dumps(dict(status='completed', head=state['head'], base=state['review_base'],
                                        summary='Inspected fixture',
                                        findings=[{k: v for k, v in prose.items() if v is not None}],
                                        resolutions=[])))
        result = subprocess.run([sys.executable, str(FLOW), 'record', '--reviewer', 'claude',
                                 '--report', str(path)], cwd=self.repo, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('named no trigger', result.stderr)
        self.assertIn('code.txt:docstring-contradicts-the-code', result.stderr)
        self.report('codex', [])
        self.triage([dict(id='claude::code.txt:docstring-contradicts-the-code', status='deferred',
                          evidence='real, and batched into a follow-up campaign')])
        self.assertTrue(self.flow('finish')['cleared'])

    def test_a_policy_finding_that_names_a_gate_command_still_blocks(self):
        """The rule narrows what blocks; it does not soften it. A trigger need not be a test —
        a gate command that fails is one — and a P2 carrying one cannot be deferred away, which
        is the behaviour that must survive the change that ended the argument about prose."""
        violation = dict(id='code.txt:suppression-added', kind='policy', priority='P2',
                         evidence='an eslint-disable was introduced on the changed line',
                         trigger='npm run lint')
        self.start()
        self.checks()
        self.report('claude', [violation])
        self.report('codex', [])
        # triage records the disposition the author chose; finish is what refuses it.
        self.triage([dict(id='claude::code.txt:suppression-added', status='deferred',
                          evidence='would rather not')])
        refused = self.flow('finish', ok=False).stderr
        self.assertIn('Confirmed blocker cannot be deferred', refused)

    def test_the_prompt_names_the_one_base_a_report_may_carry(self):
        """record rejects a report whose base is the campaign's original rather than the round's,
        and on a correction round the two differ — so a prompt that printed both with equal
        billing made the natural choice the wrong one, on every correction round. Two authors in
        two repositories hit "Report scope mismatch" that way."""
        self.start()
        self.checks()
        self.report('claude')
        self.report('codex')
        self.triage()
        self.commit('a correction')
        state = self.start(correction=True)
        self.checks()
        self.assertNotEqual(state['base'], state['review_base'])
        prompt = self.text('prompt')
        self.assertIn('"base" field must be exactly ' + state['review_base'], prompt)
        self.assertIn('original base (' + state['base'] + ')', prompt)
        # And the value the prompt names is the one record accepts, which is the whole claim.
        self.report('claude')

    def test_a_standalone_campaign_stores_a_corrected_measurement_too(self):
        """The non-autonomous branch is the live default, not a corner: a campaign is autonomous
        only once enrolled, and main() does not write state after start. Without the `changed`
        write the correction lives in memory, is returned, and the next prompt re-reads the file
        and interpolates the previous reading — the defect this round was opened for, in the
        path every standalone review takes. Every other re-measurement case here enrols first."""
        body = json.loads(self.context.read_text())
        self.start()
        self.checks()
        self.context.write_text(json.dumps(dict(body, measured=['a standalone correction'])))
        self.start()
        self.assertIn('a standalone correction', self.text('prompt'))

    def test_a_regenerated_context_is_not_a_correction(self):
        """Formatting is not content, and both questions about a context must ask the same way.

        The freeze compared the file byte for byte while the guard two lines above it compares
        semantically, so a context re-serialised with different indentation or key order read
        as a correction and blocked the documented idempotent restart — on every campaign that
        writes its context file again. It fails as somebody unable to work, not as a red case,
        which is why it is asserted here.
        """
        body = json.loads(self.context.read_text())
        self.start()
        self.checks()
        self.report('claude')
        # Same document, written the way a different orchestrator would write it.
        self.context.write_text(json.dumps(body, indent=2, sort_keys=True))
        self.start()
        self.assertEqual(self.flow('status')['round'], 1)

    def test_a_reading_cannot_change_once_a_reviewer_has_read_it(self):
        """The window closes at the first report. Afterwards the task is what that reviewer
        read: changing it would hand the second a different context from the first, and a
        cleared candidate would have the evidence behind its receipt edited after the fact —
        the reviews, the triage and the cleared flag all stay, and only the text they were
        judged against would move."""
        body = json.loads(self.context.read_text())
        self.start()
        self.checks()
        self.report('claude')
        self.context.write_text(json.dumps(dict(body, measured=['too late for this candidate'])))
        refused = self.start(ok=False).stderr
        self.assertIn('already read this candidate', refused)
        # Unchanged is still idempotent: start is called repeatedly through a campaign.
        self.context.write_text(json.dumps(body))
        self.assertEqual(self.flow('status')['round'], 1)
        self.start()

    def test_a_re_measurement_on_the_same_candidate_reaches_the_reviewers(self):
        """A reading corrected on the candidate in hand is what the reviewers must read.

        The guard that used to refuse this was loosened so the field could move; the branch
        behind it kept returning the stored state, so start accepted the correction and handed
        both reviewers the previous reading. prompt() interpolates state['context'] verbatim,
        so the divergence is invisible at exactly the moment it decides what is reviewed.
        """
        body = json.loads(self.context.read_text())
        self.start(autonomous=True)
        self.checks()
        self.context.write_text(json.dumps(dict(body, measured=['the corrected reading'])))
        self.start(autonomous=True)                      # same head, corrected measurement
        self.assertIn('the corrected reading', self.text('prompt'))

    def test_a_re_measurement_is_not_a_scope_change(self):
        """`measured` records what the author ran against real data for the candidate in hand,
        so it changes when the candidate does — that is the field's purpose. Three guards
        compared it as scope, which made it write-once: round 2 was refused for carrying a new
        reading of the same contract.

        Reported from another repository as something worse, and it was the same defect: a
        delivery whose ledger predated the field could not acquire it at all, because
        context_contract demanded the edit while these guards forbade it. Three guards closing
        a ring on a campaign that had done nothing wrong.
        """
        body = json.loads(self.context.read_text())
        self.start(autonomous=True)
        self.complete()
        self.commit('a correction')
        self.context.write_text(json.dumps(dict(body, measured=['re-measured for this candidate'])))
        state = self.start(correction=True, answers=['code.txt:external'], autonomous=True)
        self.assertEqual(state['round'], 2)

    def test_a_delivery_predating_the_field_can_acquire_it(self):
        """The reported shape, end to end: a ledger written before `measured` existed, and a
        context that must gain the field to satisfy the contract. Adding it continues the
        delivery on its own branch and budget instead of being refused as new work."""
        body = json.loads(self.context.read_text())
        without = {k: v for k, v in body.items() if k != 'measured'}
        self.start(autonomous=True)
        directory = Path(self.flow('status')['directory'])
        # Age every ledger under the campaign root the way one written before the field looks;
        # which file holds it is the runtime's business, and naming a path here would be a
        # second guess at it. An earlier version computed one, found nothing, and ignored both.
        aged = 0
        for path in directory.parent.rglob('*.json'):
            data = json.loads(path.read_text())
            if isinstance(data, dict) and 'context' in data and 'heads' in data:
                data['context'] = json.dumps(without)
                path.write_text(json.dumps(data, indent=2))
                aged += 1
        # Or the case proves nothing: with no ledger aged, the start below simply succeeds the
        # way it always would, and the ring it is named for was never set up.
        self.assertEqual(aged, 1, 'no ledger was aged, so this case tests nothing')
        self.complete()
        self.commit('a correction')
        state = self.start(correction=True, answers=['code.txt:external'], autonomous=True)
        self.assertEqual(state['round'], 2)
        self.assertEqual(state['delivery_used'], 2)

    def test_a_real_scope_change_is_still_refused(self):
        """The guards keep their meaning: the contract is what the campaign is measured
        against, and changing it mid-delivery is what they exist to stop. Only the reading
        taken under it may move."""
        body = json.loads(self.context.read_text())
        self.start(autonomous=True)
        self.complete()
        self.commit('a correction')
        self.context.write_text(json.dumps(dict(body, intent='something else entirely')))
        refused = self.start(ok=False, correction=True, answers=['code.txt:external'], autonomous=True)
        self.assertIn('Scope changed', refused.stderr)

    def test_the_ledger_keeps_the_measurement_of_the_candidate_it_froze(self):
        """Scope is unchanged by the guard above, so what differs is the reading — and the
        ledger carries the current one, written with the head it belongs to, so it still
        changes once and only when a candidate freezes."""
        body = json.loads(self.context.read_text())
        self.start(autonomous=True)
        self.complete()
        self.commit('a correction')
        self.context.write_text(json.dumps(dict(body, measured=['the second reading'])))
        self.start(correction=True, answers=['code.txt:external'], autonomous=True)
        directory = Path(self.flow('status')['directory'])
        stored = [json.loads(path.read_text()) for path in directory.parent.rglob('*.json')]
        ledgers = [d for d in stored if isinstance(d, dict) and 'heads' in d and 'context' in d]
        self.assertTrue(ledgers)
        self.assertIn('the second reading', ledgers[0]['context'])

    def test_the_context_measures_each_acceptance_item_against_real_data(self):
        """A tree can be self-consistently wrong and no reviewer can see it from the diff.

        Measured elsewhere: a correct gate, green tests, thirteen of thirteen mutants caught,
        and a feature that did almost nothing because 540 of 540 cached records carry an empty
        timestamp the date floor rejects. Two commands answered it and nobody ran them because
        nothing asked. Per acceptance item, or it is theatre — that author had production
        access and used it twice in the same hour, measuring what they were curious about
        rather than the one thing the feature turned on, which a single free-text note would
        have been satisfied by.
        """
        body = dict(intent='i', acceptance=['first criterion', 'second criterion'],
                    constraints=['c'], scope='s', checks=[[sys.executable, '-c', 'pass']])
        self.context.write_text(json.dumps(body))
        refused = self.flow('start', '--base', self.base, '--context', str(self.context), ok=False).stderr
        self.assertIn('one entry per acceptance item', refused)
        self.assertIn('There are 2 acceptance items', refused)
        # One note for two criteria is the shape that reads as measured and is not.
        self.context.write_text(json.dumps(dict(body, measured=['540 of 540 records carry the field'])))
        self.assertIn('one entry per acceptance item',
                      self.flow('start', '--base', self.base, '--context', str(self.context), ok=False).stderr)
        # "Not measurable offline" is an honest answer, and recording it is the point.
        self.context.write_text(json.dumps(dict(body, measured=[
            '540 of 540 cached records carry the field the gate reads',
            'not measurable offline: the counter exists only in production telemetry'])))
        self.assertEqual(self.flow('start', '--base', self.base, '--context', str(self.context))['round'], 1)

    def test_every_field_the_blocking_rule_reads_is_representable_in_a_report(self):
        """Both reviewer routes constrain the report to review-report.schema.json — review_flow
        passes it to `codex exec --output-schema` and review_claude to `claude -p --json-schema`
        — and that schema sets additionalProperties false. So a field blocks_a_receipt reads and
        the schema does not declare is a field no automated reviewer can ever send: every
        finding then fails the blocking test, finish lets real blockers be deferred, and the
        receipt authorises the push. That is what shipping the trigger rule without touching the
        schema did, and no case saw it because every fixture writes its reports by hand.

        Derived from the runtime rather than restated: the keys come out of the function itself,
        so adding a third one to the rule and forgetting the schema fails here.
        """
        source = ast.parse(FLOW.read_text())
        rule = next(n for n in ast.walk(source)
                    if isinstance(n, ast.FunctionDef) and n.name == 'blocks_a_receipt')
        keys = {node.args[0].value for node in ast.walk(rule)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'get' and node.args
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)}
        self.assertIn('trigger', keys, 'the blocking rule no longer reads a trigger')
        items = json.loads((FLOW.with_name('review-report.schema.json')).read_text())[
            'properties']['findings']['items']
        # The strictness is what makes the omission fatal rather than merely untidy.
        self.assertIs(items.get('additionalProperties'), False)
        missing = keys - set(items['properties'])
        self.assertFalse(missing, f'blocks_a_receipt reads {sorted(missing)}, which no structured '
                                  'report can carry')
        # And in the shape a strict structured-output mode accepts: it requires every property
        # to appear in `required`, an optional field being a nullable union instead. This file
        # had no optional property before trigger, so the first one is the one to get wrong, and
        # the failure would be a Codex run that dies on an unrecognised error after merge.
        self.assertEqual(set(items['required']), set(items['properties']))
        self.assertIn('null', items['properties']['trigger']['type'])

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

    def test_the_declared_gates_run_before_a_reviewer_reads_the_tree(self):
        """A reviewer round is the scarcest thing a campaign spends, so the machine answers
        first. Until this, the declared gates ran on the way to finish — after both readings —
        which is how two rounds here went to a test that read the developer machine's Codex and
        a bundler that swept a local cache into the manifest. A gate names either in seconds."""
        self.start()
        refused = self.flow('prompt', ok=False).stderr
        self.assertIn('have not run on this candidate', refused)
        # The route that launches a reviewer, not only the one that prints the task: both build
        # the text through prompt(), which is where the refusal lives, so there is one rule.
        launched = self.codex_run('codex', locations=[self.fake_codex('#!/bin/sh\nexit 0\n')])
        self.assertEqual(launched.returncode, 2, launched.stdout)
        self.assertIn('have not run on this candidate', launched.stderr)
        self.checks()
        self.assertIn('already ran on this candidate and passed', self.text('prompt'))

    def test_a_gate_that_failed_keeps_the_candidate_from_the_reviewers(self):
        """Having run is not having passed. A red suite handed to two readers spends both
        rounds on what the suite already prints, and the exit code is named in the refusal so
        the author fixes the candidate rather than re-running the gate to see why."""
        failing = [sys.executable, '-c', 'raise SystemExit(3)']
        self.context.write_text(json.dumps(dict(
            intent='Fix requested feature', acceptance=['Preserve callers'],
            measured=['ran the fixture gate against the candidate tree: 1 file read, nonempty'], constraints=['No unrelated changes'], scope='Candidate against base', checks=[failing])))
        self.start()
        self.flow('check', '--', *failing, ok=False)
        refused = self.flow('prompt', ok=False).stderr
        self.assertIn('exit 3', refused)
        self.assertIn('gates already accept', refused)

    def test_prompt_keeps_sandboxed_reviewers_off_the_declared_checks(self):
        """Declared checks are the caller's to run; a reviewer that gave up on a sandbox denial is
        told the environment fix, so the retry is not spent on the same failure."""
        self.start()
        self.checks()
        prompt = self.flow('prompt')
        self.assertIn('already ran on this candidate and passed', prompt.stdout)
        # The task and the schema handed to the same CLI must agree about the one field whose
        # representability this campaign spent a round on: it is required and nullable, so the
        # instruction says null rather than omit.
        self.assertIn('"trigger":"the command or test that makes it appear, or null when there '
                      'is none"', prompt.stdout)
        self.assertNotIn('omit when there is none', prompt.stdout)
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
        self.read_prose()
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

    def caused_round(self, slug, file='code.txt', previous=None):
        """A round whose only blocking finding sits in the file the correction changed.

        Each round gets its own invariant name: the same id open twice is the reopened
        rule, and these tests are about the other one. A correction round resolves the
        previous round's open finding, as any report must.
        """
        resolutions = [dict(id=f'claude::code.txt:{previous}', evidence='verified fixed')] if previous else []
        self.report('claude', [dict(id=f'{file}:{slug}', kind='defect', priority='P1', evidence='wrong')],
                    resolutions=resolutions)
        self.report('codex', [], resolutions=resolutions)
        self.triage([dict(id=f'claude::{file}:{slug}', status='open', evidence='Confirmed')])

    def test_a_finding_in_the_corrected_file_is_recorded_as_self_inflicted(self):
        """The diff decides; round 1 has no correction to blame."""
        self.start()
        self.caused_round('first')
        self.assertEqual(self.flow('status')['retrospectives'][-1]['introduced'], [])
        self.commit('fix')
        self.start(correction=True, nit='')
        self.caused_round('second', previous='first')
        entry = self.flow('status')['retrospectives'][-1]
        self.assertEqual(entry['introduced'], ['claude::code.txt:second'])
        self.assertEqual(entry['still_open'], ['claude::code.txt:second'])
        self.assertIn('claude::code.txt:second', self.text('lessons'))

    def test_retriaging_a_round_keeps_one_retrospective_entry(self):
        """Two entries for one round would read as two rounds, misreporting the history the
        author reads in `lessons` and the count the budget is measured against."""
        self.start()
        self.caused_round('first')
        self.commit('fix')
        self.start(correction=True, nit='')
        self.caused_round('second', previous='first')
        self.triage([dict(id='claude::code.txt:second', status='open', evidence='Confirmed again')])
        rounds = [r['round'] for r in self.flow('status')['retrospectives']]
        self.assertEqual(rounds, [1, 2])
        self.commit('fix again')
        named = [dict(command='c', expected='e', observed='e', covers='code.txt:second')]
        self.assertEqual(self.start(correction=True, nit='', probe=named, design=True)['round'], 3)

    def test_lessons_keep_their_evidence_after_the_next_round_starts(self):
        """The reports a lesson came from are reset by start; the lesson is not."""
        self.start()
        self.caused_round('first')
        self.commit('fix')
        self.start(correction=True, nit='')
        self.caused_round('second', previous='first')
        self.commit('fix again')
        named = [dict(command='c', expected='e', observed='e', covers='code.txt:second')]
        self.start(correction=True, nit='', probe=named, design=True)
        self.assertIn('claude::code.txt:second: wrong', self.text('lessons'))

    def test_a_deferred_self_inflicted_blocker_still_needs_its_probe(self):
        """Deferring a blocker is not answering it; only a rejection with counterevidence is."""
        self.start()
        self.caused_round('first')
        self.commit('fix')
        self.start(correction=True, nit='')
        self.report('claude', [dict(id='code.txt:second', kind='defect', priority='P1', evidence='wrong')],
                    resolutions=[dict(id='claude::code.txt:first', evidence='verified fixed')])
        self.report('codex', resolutions=[dict(id='claude::code.txt:first', evidence='verified fixed')])
        self.triage([dict(id='claude::code.txt:second', status='deferred', evidence='later')])
        self.commit('fix again')
        blind = self.start(ok=False, correction=True, design=True).stderr
        self.assertIn('no probe names them', blind)

    def test_a_rejected_finding_is_not_blamed_on_the_correction(self):
        """A rejection carries counterevidence: the correction did not produce that finding."""
        self.start()
        self.caused_round('first')
        self.commit('fix')
        self.start(correction=True, nit='')
        resolutions = [dict(id='claude::code.txt:first', evidence='verified fixed')]
        self.report('claude', [dict(id='code.txt:second', kind='defect', priority='P1', evidence='wrong')],
                    resolutions=resolutions)
        self.report('codex', resolutions=resolutions)
        self.triage([dict(id='claude::code.txt:second', status='rejected', evidence='disproved: the guard is three lines up')])
        entry = self.flow('status')['retrospectives'][-1]
        self.assertEqual((entry['introduced'], entry['still_open']), ([], []))
        self.assertIn('has produced a finding yet', self.text('lessons'))
        self.commit('next')
        self.assertEqual(self.start(correction=True)['round'], 3)
        self.checks()
        self.assertNotIn('the correction produced the finding', self.text('prompt'))

    def test_a_finding_elsewhere_is_not_blamed_on_the_correction(self):
        """Only a file the correction changed can carry a finding it introduced."""
        (self.repo / 'other.txt').write_text('untouched\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'add other.txt')
        self.start()
        self.caused_round('first')
        self.commit('fix')
        self.start(correction=True, nit='')
        self.caused_round('second', file='other.txt', previous='first')
        self.assertEqual(self.flow('status')['retrospectives'][-1]['introduced'], [])
        self.assertIn('No correction in this campaign has produced a finding yet', self.text('lessons'))

    def test_a_self_inflicted_finding_needs_a_probe_that_names_it(self):
        """The case the finding exposed is the case the author shows being tried."""
        self.start()
        self.caused_round('first')
        self.commit('fix')
        self.start(correction=True, nit='')
        self.caused_round('second', previous='first')
        self.commit('fix again')
        # The round is a design round from here: the correction produced the finding it was
        # reviewed for, and that is declared before anything else about the round is judged.
        blind = self.start(ok=False, correction=True, nit='', design=True).stderr
        self.assertIn('no probe names them', blind)
        self.assertIn('claude::code.txt:second', blind)
        named = [dict(command='c', expected='e', observed='e', covers='code.txt:second')]
        self.start(correction=True, nit='', probe=named, design=True)

    def test_one_self_inflicted_round_already_forces_a_design_round(self):
        """The second patch of a mechanism that produced a finding is what the rule stops.

        This waited for two such rounds in a row, and waiting is what the second round was
        spent proving. Measured in an unrelated repository on the same loop: when the author
        finally ran a mutation matrix over the whole family instead of patching the latest
        instance, it found two cells nothing in a 3100-test suite covered, in one round — the
        round that should have been the second. Firing on the first is safe only because a
        finding must name a trigger to be counted here, so an argument about a sentence in the
        file just corrected no longer forces a redesign.
        """
        self.start(autonomous=True)
        self.caused_round('first')
        # Round 1 has no correction to blame, so the first attributable round is round 2: this
        # correction produces the finding round 2 is then reviewed for.
        self.commit('a first patch')
        self.start(correction=True, nit='',
                   probe=[dict(command='c', expected='e', observed='e', covers='code.txt:first')])
        self.caused_round('second', previous='first')
        self.commit('a second patch')
        named = [dict(command='c', expected='e', observed='e', covers='code.txt:second')]
        refused = self.start(ok=False, correction=True, nit='', probe=named).stderr
        self.assertIn('The last correction introduced the finding it was then reviewed for', refused)
        self.assertIn('lessons', refused)
        state = self.start(correction=True, nit='', probe=named, design=True)
        self.assertTrue(state['design_round'])
        self.checks()
        prompt = self.text('prompt')
        self.assertIn('the correction produced the finding', prompt)
        self.assertIn('DESIGN ROUND: the last correction introduced', prompt)
        self.assertNotIn('reopened after a claimed fix: .', prompt)

    def test_the_lessons_checklist_names_the_stale_bytecode_hazard(self):
        """The checklist the author reads before the next correction asks for a mutation matrix,
        so it must also name the way a matrix lies. CPython invalidates bytecode on (mtime
        seconds, size), so two mutants of the same size written inside one second serve the
        previous mutant's result — and the direction that fails is "broke nothing", which
        manufactures a false claim that a rule is uncovered. One row of a real matrix did
        exactly this. Restoring the tree does not clear it: a source comparison says restored."""
        self.start(autonomous=True)
        self.caused_round('first')
        self.commit('a first patch')
        self.start(correction=True, nit='',
                   probe=[dict(command='c', expected='e', observed='e', covers='code.txt:first')])
        self.caused_round('second', previous='first')
        advice = self.text('lessons')
        self.assertIn('PYTHONDONTWRITEBYTECODE=1', advice)
        self.assertIn('__pycache__', advice)
        self.assertIn('mutation matrix after committing and before `start`', advice)

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
        self.checks()
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
        self.assertIn('No open finding is one a round is for', refused)
        self.assertIn('--nit-round', refused)
        # Recorded, the round proceeds and both reviewers are told why.
        state = self.start(correction=True, nit='the wording misleads a reader of the protocol')
        self.assertEqual(state['round'], 2)
        self.checks()
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
        self.assertIn('No open finding is one a round is for', refused)

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
        self.checks()
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
        self.assertEqual(self.read_prose()['outcome'], 'unchanged')
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
        (self.repo / 'tests/test_old.py').write_text('def test_a(): assert 1 == 1\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'existing test')
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests/test_old.py').rename(self.repo / 'tests/test_new.py')
        (self.repo / 'tests/test_new.py').write_text(
            'def test_a(): assert 1 == 1\ndef test_b(): assert 2 == 2\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'rename and extend')
        # Each mutant changes a case's BODY. Replacing a signature makes the module stop
        # importing, which the runner refuses as a crash rather than a measurement — and two
        # of these fixtures did exactly that, recording "caught" for cases that never ran.
        self.matrix('tests/test_new.py', [('1 == 1', '1 == 2', 'test_a'),
                                          ('2 == 2', '2 == 3', 'test_b')])
        state = self.start(correction=True, reason='')
        self.assertEqual(state['regression_tests'], ['tests/test_new.py'])
        self.checks()
        self.assertIn('tests/test_new.py', self.flow('prompt').stdout)

    def test_a_correction_that_changes_a_test_needs_a_measured_matrix(self):
        """Every refusal of matrix_first, because a gate nobody tries is decoration.

        Reported by a reviewer: replacing this function's body with `return` left the suite
        green, so four refusals guarded nothing anyone had checked.
        """
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_g.py').write_text('def test_g(): assert 1 == 1\n')
        self.commit('a correction that changes a test')

        missing = self.start(ok=False, correction=True, reason='').stderr
        self.assertIn('no measured mutation matrix exists', missing)

        directory = Path(self.flow('status')['directory'])
        head = self.git('rev-parse', 'HEAD')
        record = directory / ('matrix-' + head + '.json')

        record.write_text(json.dumps({'head': 'another', 'mutants': 1, 'tree': 'x',
                                       'survivors': []}))
        self.assertIn('names head another', self.start(ok=False, correction=True, reason='').stderr)

        record.write_text(json.dumps({'head': head, 'mutants': 0, 'tree': 'x', 'survivors': []}))
        self.assertIn('measured no mutants', self.start(ok=False, correction=True, reason='').stderr)

        record.write_text(json.dumps({'head': head, 'mutants': 1, 'tree': '', 'survivors': []}))
        self.assertIn('no fingerprint', self.start(ok=False, correction=True, reason='').stderr)

        record.write_text(json.dumps({'head': head, 'mutants': 1, 'tree': 'x',
                                       'survivors': ['test_g']}))
        self.assertIn('has survivors', self.start(ok=False, correction=True, reason='').stderr)

        # The fingerprint is recomputed, not tested for presence: a record saying `tree: x`
        # passed here while two sentences said it was bound to the tree it measured.
        record.write_text(json.dumps({'head': head, 'mutants': 1, 'tree': 'not-a-digest',
                                       'survivors': [], 'files': ['tests/test_g.py']}))
        self.assertIn('does not match', self.start(ok=False, correction=True, reason='').stderr)

        # And named, not merely listed: the digest of no files is the digest of nothing.
        import hashlib
        record.write_text(json.dumps({'head': head, 'mutants': 1, 'files': [], 'survivors': [],
                                       'tree': hashlib.sha256().hexdigest()}))
        self.assertIn('does not name the files', self.start(ok=False, correction=True, reason='').stderr)

        record.unlink()
        self.matrix('tests/test_g.py', [('1 == 1', '1 == 2', 'test_g')])
        self.assertEqual(self.start(correction=True, reason='')['round'], 2)

    def test_a_correction_that_changes_no_test_needs_no_matrix(self):
        """The scope, asserted: a correction with no gate to mutate is exempt, and saying so
        here keeps the exemption from widening unnoticed."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        self.commit('a correction that changes no test')
        self.assertEqual(self.start(correction=True)['round'], 2)

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
        (self.repo / 'tests/test_fix.py').write_text('def test_fix(): assert 1 == 1\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'add regression')
        self.matrix('tests/test_fix.py', [('1 == 1', '1 == 2', 'test_fix')])
        state = self.start(correction=True, reason='')
        self.assertEqual(state['round'], 2)
        self.assertEqual(state['regression_tests'], ['tests/test_fix.py'])
        self.checks()
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
        self.checks()
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
        spec = importlib.util.spec_from_file_location('flow_escalation', FLOW)
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

    def test_the_runtime_keeps_its_functions_under_the_size_limit(self):
        """AGENTS.md names a function over 50 lines as a finding for what a change
        introduces, including a change that pushes an existing one past it. A rule only a
        reviewer remembers is a rule that comes back; this is the gate for these modules."""
        modules = sorted(FLOW.parent.glob('*.py'))
        # Discovered, not listed: a module added later is inside the rule it exists to
        # enforce, and a list is the thing that silently stops covering what it names.
        self.assertGreaterEqual(len(modules), 5)
        over = {}
        for module in modules:
            name = module.stem
            tree = ast.parse(module.read_text())
            over.update({f'{name}.{node.name}': node.end_lineno - node.lineno + 1
                         for node in ast.walk(tree)
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                         and node.end_lineno - node.lineno + 1 > 50})
        self.assertFalse(over, f'functions over 50 lines: {over}')

    def test_a_correction_that_changes_a_test_must_show_it_failing(self):
        """A case the author believes exercises the fix is not evidence that it does.

        Measured across two campaigns on two repositories: every such belief that was
        checked turned out wrong, and a reviewer checked it every time, by reverting the
        change and watching the case stay green. Reverting costs seconds, so the round asks
        for that output instead of the belief.
        """
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        # Deliberately not finished: a cleared candidate makes the next start a first round
        # with no correction contract at all, so the rule under test is never reached. An
        # earlier version of this case did exactly that and the runtime answered 0, not 2.
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests' / 'test_thing.py').write_text('def test_thing():\n    assert True\n')
        self.commit('correction that changes a test')
        self.matrix('tests/test_thing.py', [('assert True', 'assert False', 'test_thing')])

        believed = [dict(command='python3 -m pytest tests/test_thing.py', expected='passes',
                         observed='passes')]
        refused = self.start(ok=False, correction=True, probe=believed).stderr
        self.assertIn('without_fix', refused)
        self.assertIn('never watched fail', refused)

        shown = [dict(believed[0], without_fix='reverted the guard; the case failed with '
                                               'AssertionError on the invariant it names')]
        self.assertEqual(self.start(correction=True, probe=shown)['round'], 2)

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


class BriefShowsTheDeltaTests(unittest.TestCase):
    """What the brief RENDERS, which no case reached until now.

    Both reviewers found the same hole from two directions: the matrix mutates review_claims
    and review_matrix, so the two halves of the brief that live here were uncovered. Replacing
    the removal check's call with `[]` and collapsing the three-state marker to a constant both
    left the suite green, and each restores a defect a reviewer had already filed once.
    """

    def setUp(self):
        """Enter a two-commit repository: both functions read the process cwd, not an argument."""
        self.where = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.where, ignore_errors=True))
        for command in (['init', '-q'], ['config', 'user.email', 'c@example.invalid'],
                        ['config', 'user.name', 'C']):
            subprocess.run(['git', '-C', str(self.where)] + command, check=True)
        was = os.getcwd()
        os.chdir(self.where)
        self.addCleanup(os.chdir, was)
        spec = importlib.util.spec_from_file_location('flow_brief', FLOW)
        self.flow = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.flow)

    def commit(self, files, drop=()):
        for name in drop:
            (self.where / name).unlink()
        for name, text in files.items():
            (self.where / name).write_text(text)
        subprocess.run(['git', '-C', str(self.where), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(self.where), 'commit', '-q', '-m', 'x',
                        '--allow-empty'], check=True)
        return subprocess.run(['git', '-C', str(self.where), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip()

    def test_the_brief_shows_a_removal_claim_the_check_only_reports(self):
        """An independent reviewer found that nothing on the flow path executed the removal check, so its rows
        reached nobody while the brief said they did. The fix was to RUN it; this is what
        fails when it stops being run — replacing the call with `[]` passes every other case.
        """
        base = self.commit({'a.py': 'X = 1  # most likely never joined\n'})
        head = self.commit({'a.py': 'X = 1  # most likely never joined\n',
                            'NOTES.md': 'We removed `most likely never joined` from it.\n'})
        said = self.flow.claims_coverage({'review_base': base, 'head': head})
        self.assertIn('REPORTED, not refusing', said)
        self.assertIn('most likely never joined', said)

    def test_the_code_view_marks_an_addition_a_removal_and_a_change_with_no_line(self):
        """A removal reached reviewers through the format an addition uses, and a file that
        changed without any line changing was then announced as one too. Three states, three
        marks: collapsing the expression to any single constant fails here.
        """
        base = self.commit({'a.py': 'A = 1\nB = 2\n', 'bin.dat': 'x'})
        head = self.commit({'a.py': 'A = 1\nC = 3\n', 'bin.dat': 'x'})
        subprocess.run(['chmod', '+x', str(self.where / 'bin.dat')], check=True)
        head = self.commit({})
        shown = self.flow.code_view({'review_base': base, 'head': head})
        marks = {line.strip()[0] for line in shown.split('\n') if line.startswith('  ')}
        self.assertEqual(marks, {'+', '-', '?'}, shown)


if __name__ == '__main__':
    unittest.main()
