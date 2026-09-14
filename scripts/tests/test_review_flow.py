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

    def start(self, ok=True):
        """Start or reuse the current bounded review candidate."""
        return self.flow('start', '--base', self.base, '--context', str(self.context), ok=ok)

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

    def test_directory_changes_only_precede_push(self):
        """A trailing cd cannot substitute a reviewed worktree for the pushed one."""
        self.start()
        self.complete()
        sibling = self.root / 'reviewed'
        self.git('worktree', 'add', '-qb', 'reviewed', str(sibling))
        self.commit('unreviewed')
        self.push(f'git push origin HEAD && cd "{sibling}"', ok=False)
        self.push(f'cd "{sibling}" && git push origin HEAD')
        self.push(f'cd "{sibling}" extra && git push origin HEAD', ok=False)
        self.push('cd - && git push origin HEAD', ok=False)

    def test_exec_prefixes_cannot_skip_the_receipt(self):
        """An exec prefix still reaches git, so it must not turn the guard off."""
        self.start()
        self.complete()
        self.commit('unreviewed')
        for prefix in ('command', 'env', 'sudo', 'nohup', 'xargs', 'timeout 60'):
            self.push(prefix + ' git push origin HEAD', ok=False)
        self.push('FOO=1 git push origin HEAD', ok=False)
        self.git('reset', '-q', '--hard', 'HEAD~1')
        self.push('FOO=1 git push origin HEAD')
        self.push('env FOO=1 grep push notes.txt')

    def test_shell_control_forms_cannot_skip_the_receipt(self):
        """A keyword or negation before git still runs it, so the form must fail closed."""
        self.start()
        self.complete()
        self.commit('unreviewed')
        for form in ('if true; then git push origin HEAD; fi',
                     '! git push origin HEAD',
                     'while true; do git push origin HEAD; done',
                     '{ git push origin HEAD; }',
                     # The -C option separates git from push; detection must not need adjacency.
                     'if true; then git -C . push origin HEAD; fi',
                     '! git -C . push origin HEAD',
                     'while true; do git -C . push origin HEAD; done',
                     'command git -C . push origin HEAD',
                     'env git -C . push origin HEAD'):
            self.push(form, ok=False)

    def test_arguments_of_an_ordinary_command_are_not_command_position(self):
        """Only a keyword or exec prefix opens a command; a plain command's args do not."""
        self.start()
        self.complete()
        self.push('printf "%s %s" git push')
        self.push('git stash push')
        self.push('if true; then git status; fi')
        self.push('echo git push > notes.txt')

    def test_git_environment_overrides_are_refused(self):
        """GIT_DIR would publish another repository while this one's receipt is read."""
        self.start()
        self.complete()
        for override in ('GIT_DIR=/other/.git', 'GIT_WORK_TREE=/other', 'GIT_OBJECT_DIRECTORY=/other'):
            self.push(override + ' git push origin HEAD', ok=False)
        self.push('git push origin HEAD')

    def test_quoted_shift_text_is_not_a_heredoc(self):
        """'<<' inside an argument is data; only the operator introduces a document."""
        self.start()
        self.complete()
        self.push('git log --grep="git push << example"')
        self.push('python3 -c "print(1 << 3)"')
        self.push('grep -rn "a << b" docs/')
        self.push('printf "%s %s" "<<" example')

    def test_heredoc_cannot_hide_following_push(self):
        """Only a standalone literal document may bypass command parsing."""
        document = "cat <<'EOF' > notes.txt\ngit push origin HEAD\nEOF\n"
        self.push(document)
        self.push(document + 'git push origin HEAD', ok=False)
        self.push(document + 'git pu""sh origin HEAD', ok=False)
        self.push('cat <<EOF\n$(git push origin HEAD)\nEOF', ok=False)
        self.push('git status\ngit push origin HEAD', ok=False)

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
            result = self.start(ok=round_number < 3)
            if round_number < 3:
                self.assertEqual(result['round'], round_number + 1)

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
        state = self.start()
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

    def test_ambiguous_push_rejected_and_reads_allowed(self):
        """Unsupported shell/refspec forms fail rather than picking an unrelated tip."""
        self.start()
        self.complete()
        for cmd in ('git push', 'git push --all origin', 'git push origin :branch',
                    'git push origin "refs/heads/*:refs/heads/*"', 'git push origin $BRANCH',
                    "bash -c 'git push origin HEAD'"):
            self.push(cmd, ok=False)
        self.push('git status')
        self.push('rg push README.md')

    def test_quoted_push_spellings_are_still_checked(self):
        """Shell quoting that still runs git push cannot skip the receipt lookup."""
        self.start()
        self.complete()
        reviewed = self.git('rev-parse', 'HEAD')
        self.commit('unreviewed')
        for spelling in ('git pu""sh', "git 'pu'sh", 'git p\\ush', 'git "push"'):
            self.push(spelling + ' origin HEAD', ok=False)
            self.push(spelling + ' origin ' + reviewed)

    def test_expansion_cannot_smuggle_an_extra_ref(self):
        """A brace expansion in the remote slot would publish a ref the guard never read."""
        self.start()
        self.complete()
        self.push('git push origin{,evil} HEAD', ok=False)
        self.push('git push origin HEAD{,~1}', ok=False)
        self.push('git push origin HEAD')

    def test_commands_that_only_mention_a_push_are_allowed(self):
        """Reading or writing text about a push publishes nothing and must not be blocked."""
        self.start()
        self.complete()
        for command in ('git log --grep=push', 'git stash push', 'grep -rn "git push" docs/',
                        'echo "run git push later" > notes.txt', 'git show HEAD --stat'):
            self.push(command)
        self.push("bash -c 'git push origin HEAD'", ok=False)

    def test_push_cannot_follow_an_unchecked_command(self):
        """A chained command could rewrite HEAD after the guard read it."""
        self.start()
        self.complete()
        self.push('git commit --allow-empty -m x; git push origin HEAD', ok=False)
        self.push('git push origin HEAD && echo done', ok=False)
        self.push('cd . && git push origin HEAD')

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
