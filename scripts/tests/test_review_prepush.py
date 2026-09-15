"""Invariant layer: no spelling of a push reaches a remote without a receipt.

Every case here runs a REAL push against a bare remote through bash, exactly as the
Bash tool would, and then inspects the remote. The assertion is about what landed,
not about what any parser thought of the text, so a new spelling that defeats the
Bash adapter still has to get past the pre-push hook that git invokes with the SHA.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / 'plugins/bymax-quality/scripts/review_flow.py'

# Every form found across the review campaigns that ever reached git with argv `push`
# while a text-level guard reported no push. Each must fail at the hook instead.
SPELLINGS = [
    'git push origin HEAD:feature',
    'git pu""sh origin HEAD:feature',
    "git 'pu'sh origin HEAD:feature",
    'git p\\ush origin HEAD:feature',
    "git $'push' origin HEAD:feature",
    "git $'pu\\x73h' origin HEAD:feature",
    'git pu\\\nsh origin HEAD:feature',
    'command git push origin HEAD:feature',
    'env git push origin HEAD:feature',
    'FOO=1 git push origin HEAD:feature',
    'nohup git push origin HEAD:feature',
    'timeout 60 git push origin HEAD:feature',
    'eval git push origin HEAD:feature',
    'builtin command git push origin HEAD:feature',
    'if true; then git push origin HEAD:feature; fi',
    '! git push origin HEAD:feature',
    'while true; do git push origin HEAD:feature; break; done',
    '{ git push origin HEAD:feature; }',
    '( git push origin HEAD:feature )',
    'true && git push origin HEAD:feature',
    'true; git push origin HEAD:feature',
    'echo x | git push origin HEAD:feature',
    'git -C . push origin HEAD:feature',
    'if true; then git -C . push origin HEAD:feature; fi',
    'bash -c "git push origin HEAD:feature"',
    'bash -c "true;git push origin HEAD:feature"',
    "bash -c 'git pu\"\"sh origin HEAD:feature'",
    '$(which git) push origin HEAD:feature',
    '"$(which git)" push origin HEAD:feature',
    '`which git` push origin HEAD:feature',
    'echo hi && $(which git) push origin HEAD:feature',
    'git push origin{,evil} HEAD:feature',
    'git -c push.default=current push origin HEAD:feature',
    'git push --force origin HEAD:feature',
    'printf "%s\\n" x | xargs -I{} git push origin HEAD:feature',
]
# `git push --no-verify` is deliberately absent: git itself provides that escape and no
# hook can see a push that skips hooks. Refusing it is the Bash adapter's job, covered
# in test_review_flow, and a spelling that hides it from the adapter is the one class
# this local design cannot close; review-protocol.md names CI as the boundary for that.


class PrePushInvariantTests(unittest.TestCase):
    """A commit without a receipt must not land, whatever command produced the push."""

    def setUp(self):
        """Build a repository with the hook installed and a bare remote to push into."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo, self.remote = self.root / 'repo', self.root / 'remote.git'
        self.repo.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        subprocess.run(['git', 'init', '-q', '--bare', str(self.remote)], env=self.env, check=True)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('remote', 'add', 'origin', str(self.remote))
        self.commit('base')
        self.base = self.git('rev-parse', 'HEAD')
        context = self.root / 'context.json'
        context.write_text(json.dumps(dict(intent='i', acceptance=['a'], constraints=['c'], scope='s',
                                           checks=[[sys.executable, '-c', 'pass']])))
        self.commit('candidate')
        self.head = self.git('rev-parse', 'HEAD')
        # start installs the pre-push hook as a side effect of freezing the candidate.
        self.flow('start', '--base', self.base, '--context', str(context))

    def git(self, *args):
        """Run git in the working repository without global configuration."""
        return subprocess.check_output(['git', *args], cwd=self.repo, env=self.env, text=True).strip()

    def commit(self, text):
        """Create a commit with an observable change."""
        (self.repo / 'code.txt').write_text(text)
        self.git('add', '.')
        self.git('commit', '-qm', text)

    def flow(self, *args):
        """Drive the campaign helper and require success."""
        result = subprocess.run([sys.executable, str(FLOW), *args], cwd=self.repo,
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def remote_has(self, sha):
        """Report whether the bare remote received the commit on any ref."""
        listing = subprocess.run(['git', '--git-dir', str(self.remote), 'for-each-ref',
                                  '--format=%(objectname)'], capture_output=True, text=True)
        return sha in listing.stdout.split()

    def attempt(self, spelling):
        """Run one push spelling through bash exactly as the Bash tool would."""
        return subprocess.run(['bash', '-c', spelling], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, timeout=30)

    def test_hook_policy_matches_the_campaign_runtime(self):
        """The self-contained hook must recognise receipts written by the current runtime."""
        import importlib.util
        modules = {}
        for name in ('review_flow', 'review_prepush'):
            spec = importlib.util.spec_from_file_location(name, FLOW.with_name(name + '.py'))
            modules[name] = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modules[name])
        self.assertEqual(modules['review_prepush'].POLICY, modules['review_flow'].POLICY)

    def test_hook_installed_by_start(self):
        """The receipt check is the repository's own pre-push hook."""
        hook = self.repo / '.git/hooks/pre-push'
        self.assertTrue(hook.exists() and os.access(hook, os.X_OK))

    def test_no_spelling_lands_without_a_receipt(self):
        """Every historical bypass form is stopped by the hook, not by text inspection."""
        # The remote is the only invariant here. Neither the shell's exit status (`!`
        # negates it, a loop's `break` succeeds) nor the reason a push failed matters:
        # a spelling git rejects before any hook runs still must not land.
        for spelling in SPELLINGS:
            with self.subTest(spelling=spelling):
                result = self.attempt(spelling)
                self.assertFalse(self.remote_has(self.head),
                                 f'{spelling!r} landed on the remote\n{result.stderr}')

    def test_the_hook_is_what_stops_them(self):
        """For spellings that do reach git, the refusal comes from the hook, not elsewhere."""
        for spelling in ('git push origin HEAD:feature', 'eval git push origin HEAD:feature',
                         '$(which git) push origin HEAD:feature', 'bash -c "git push origin HEAD:feature"',
                         '! git push origin HEAD:feature', '( git push origin HEAD:feature )',
                         'echo x | git push origin HEAD:feature', "git $'pu\\x73h' origin HEAD:feature",
                         'if true; then git -C . push origin HEAD:feature; fi'):
            with self.subTest(spelling=spelling):
                result = self.attempt(spelling)
                self.assertIn('no completed Claude + Codex review', result.stderr, spelling)

    def test_receipt_admits_the_exact_commit_only(self):
        """A completed campaign clears its head, and nothing newer rides along."""
        reports = self.root / 'r.json'
        for reviewer in ('claude', 'codex'):
            reports.write_text(json.dumps(dict(status='completed', head=self.head, base=self.base,
                                               summary='fixture', findings=[], resolutions=[])))
            self.flow('record', '--reviewer', reviewer, '--report', str(reports))
        (self.root / 't.json').write_text('[]')
        self.flow('triage', '--report', str(self.root / 't.json'))
        self.flow('check', '--', sys.executable, '-c', 'pass')
        self.flow('finish')
        self.assertEqual(self.attempt('git push origin HEAD:feature').returncode, 0)
        self.assertTrue(self.remote_has(self.head))
        # An annotated tag pushes the tag object's SHA; the receipt is for the commit it peels to.
        self.git('tag', '-a', 'v9', '-m', 'release')
        self.assertEqual(self.attempt('git push origin v9').returncode, 0)
        self.assertIn(self.git('rev-parse', 'v9'), subprocess.run(
            ['git', '--git-dir', str(self.remote), 'for-each-ref', '--format=%(objectname)'],
            capture_output=True, text=True).stdout)
        self.commit('unreviewed')
        newer = self.git('rev-parse', 'HEAD')
        self.assertNotEqual(self.attempt('eval git push origin HEAD:later').returncode, 0)
        self.assertFalse(self.remote_has(newer))

    def test_hand_merged_hook_is_kept_and_custom_hooks_path_can_reconcile(self):
        """A hook carrying the marker but edited by hand is kept; a custom hooks directory
        qualifies once its pre-push carries the marker, and is never written into."""
        hook = self.repo / '.git/hooks/pre-push'
        # A hand merge keeps the marker AND invokes the real checker; the marker alone is a claim.
        merged = ('#!/bin/sh\n# ' + 'Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.'
                  + '\necho merged-by-hand\nexec ' + sys.executable + ' ' + str(FLOW.with_name('review_prepush.py')) + ' "$@"\n')
        hook.write_text(merged)
        hook.chmod(0o755)
        # start on the same candidate is idempotent for state and re-runs install_hook.
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        self.assertEqual(hook.read_text(), merged)
        custom = self.root / 'hooks'
        custom.mkdir()
        self.git('config', 'core.hooksPath', str(custom))
        self.assertIn('merge the receipt check', self.start_refused())
        self.assertFalse((custom / 'pre-push').exists())
        (custom / 'pre-push').write_text(merged)  # present and marked, but git would skip it
        self.assertIn('not executable', self.start_refused())
        (custom / 'pre-push').chmod(0o755)
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        self.assertEqual((custom / 'pre-push').read_text(), merged)
        # The accepted merged hook really enforces: it, not some other failure, keeps an
        # unreceipted commit off the remote.
        self.commit('unreviewed')
        refused = self.attempt('git push origin HEAD:feature')
        self.assertIn('pre-push: no completed Claude + Codex review', refused.stderr)
        self.assertFalse(self.remote_has(self.git('rev-parse', 'HEAD')))

    def start_refused(self):
        """Run start expecting a refusal; return its message."""
        result = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base,
                                 '--context', str(self.root / 'context.json')],
                                cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout)
        return result.stderr

    def test_marker_alone_is_not_enforcement(self):
        """A hook that carries the marker but lets an unreceipted push through is refused."""
        stub = '#!/bin/sh\n# ' + 'Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.' \
               + '\nexit 0\n'
        hook = self.repo / '.git/hooks/pre-push'
        hook.write_text(stub)
        hook.chmod(0o755)
        self.assertIn('does not enforce receipts', self.start_refused())
        self.assertEqual(hook.read_text(), stub)
        custom = self.root / 'hooks'
        custom.mkdir()
        (custom / 'pre-push').write_text(stub)
        (custom / 'pre-push').chmod(0o755)
        self.git('config', 'core.hooksPath', str(custom))
        self.assertIn('does not enforce receipts', self.start_refused())
        self.git('config', '--unset', 'core.hooksPath')
        # Validating that the SHA exists is not enforcing receipts: the probe commit exists.
        marker = 'Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.'
        hook.write_text('#!/bin/sh\n# ' + marker + '\nwhile read l s r x; do git cat-file -e "$s" '
                        '|| exit 1; done\nexit 0\n')
        self.assertIn('does not enforce receipts', self.start_refused())
        # Refusing every push is not enforcing receipts either: a receipted commit must pass.
        hook.write_text('#!/bin/sh\n# ' + marker + '\nexit 1\n')
        self.assertIn('not consulting receipts', self.start_refused())
        # A shebang-less wrapper is run through sh, as git runs it, and is accepted.
        hook.write_text('# ' + marker + '\nexec ' + sys.executable + ' '
                        + str(FLOW.with_name('review_prepush.py')) + ' "$@"\n')
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        self.assertFalse((self.repo / '.git/bymax-review/probe').exists())

    def test_probe_push_looks_real_to_a_fussy_hook(self):
        """A merged hook that also checks the pushed ref, parent and remote, as a real push
        offers them, is accepted; the receipt check behind it still refuses a real push."""
        checker = sys.executable + ' ' + str(FLOW.with_name('review_prepush.py'))
        fussy = ('#!/bin/sh\n# Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.\n'
                 '[ "$2" = "$(git remote get-url origin)" ] || exit 3\n'
                 'lines=$(cat)\n'
                 'printf "%s\\n" "$lines" | while read l s r x; do\n'
                 '  git rev-parse --verify -q "$l" >/dev/null || exit 4\n'
                 '  git rev-parse --verify -q "$s^" >/dev/null || exit 5\n'
                 '  case $x in 0000000000000000000000000000000000000000) ;;\n'
                 '    *) git merge-base --is-ancestor "$x" "$s" || exit 6 ;; esac\n'
                 'done || exit $?\n'
                 'printf "%s\\n" "$lines" | exec ' + checker + ' "$@"\n')
        hook = self.repo / '.git/hooks/pre-push'
        hook.write_text(fussy)
        hook.chmod(0o755)
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        self.commit('unreviewed')
        refused = self.attempt('git push origin HEAD:feature')
        self.assertIn('pre-push: no completed Claude + Codex review', refused.stderr)
        self.assertFalse(self.remote_has(self.git('rev-parse', 'HEAD')))

    def test_stale_bundled_hook_is_refused_not_kept(self):
        """A hook from an earlier runtime declares its policy; kept, it would refuse every push."""
        hook = self.repo / '.git/hooks/pre-push'
        stale = hook.read_text().replace('POLICY = 2', 'POLICY = 1')
        self.assertNotEqual(stale, hook.read_text())
        hook.write_text(stale)
        message = self.start_refused()
        self.assertIn('policy 1', message)
        self.assertIn('runtime is policy 2', message)
        self.assertEqual(hook.read_text(), stale)  # never overwritten silently
        hook.chmod(0o644)
        hook.write_text(hook.read_text().replace('POLICY = 1', 'POLICY = 2'))
        self.assertIn('not executable', self.start_refused())

    def test_foreign_hook_is_not_displaced(self):
        """A pre-push hook that is not ours stops the campaign instead of being overwritten."""
        hook = self.repo / '.git/hooks/pre-push'
        hook.write_text('#!/bin/sh\nexit 0\n')
        result = subprocess.run([sys.executable, str(FLOW), 'status'], cwd=self.repo,
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.commit('next')
        result = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base,
                                 '--context', str(self.root / 'context.json')],
                                cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('not managed by this campaign', result.stderr)
        self.assertEqual(hook.read_text(), '#!/bin/sh\nexit 0\n')


if __name__ == '__main__':
    unittest.main()
