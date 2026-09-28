"""Invariant layer: no spelling of a push reaches a remote without a receipt, once git runs the hook.

The qualification is the whole of it, and this file carries its own counterexample sixty lines
down: `git push --no-verify` is git's own escape and no local design closes it. What these
cases hold is that a spelling which does reach the hook cannot get past it.

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
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / 'plugins/bymax-quality/scripts/review_flow.py'
sys.path.insert(0, str(FLOW.parent))

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


class PrePushBench(unittest.TestCase):
    """A repository with the hook installed and a bare remote, and the helpers that push into
    it. It holds no test, so the suites that share it collect nothing from it."""

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
        context.write_text(json.dumps(dict(intent='i', acceptance=['a'], measured=['ran the fixture gate against the candidate tree: 1 file read, nonempty'], constraints=['c'], scope='s',
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
        # test_review_flow's CAMPAIGN_TIMEOUT: a `start` under load outran a tighter bound.
        result = subprocess.run([sys.executable, str(FLOW), *args], cwd=self.repo,
                                env=self.env, capture_output=True, text=True, timeout=180)
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

    def modules(self):
        """Load the runtime, its hook installer and the self-contained checker beside them, as
        modules."""
        import importlib.util
        loaded = {}
        for name in ('review_flow', 'review_hook', 'review_prepush'):
            spec = importlib.util.spec_from_file_location(name, FLOW.with_name(name + '.py'))
            loaded[name] = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded[name])
        return loaded

    def receipt(self, sha, reviews=None, **extra):
        """Write a completed receipt for a commit, in the shape a cleared campaign leaves."""
        directory = self.repo / '.git/bymax-review/manual'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f'completed-{sha}.json').write_text(json.dumps(dict(
            head=sha, cleared=True, policy=2,
            reviews=reviews if reviews is not None else dict(claude={}, codex={}), **extra)))

    def dangling(self, message):
        """A child of HEAD that exists only to be pushed."""
        return self.git('commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', message)

    def install(self, flow):
        """Run install_hook against the fixture repository."""
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            flow.install_hook()
        finally:
            os.chdir(cwd)

    def start_refused(self):
        """Run start expecting a refusal; return its message."""
        result = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base,
                                 '--context', str(self.root / 'context.json')],
                                cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout)
        return result.stderr


class PrePushInvariantTests(PrePushBench):
    """A commit without a receipt must not land, whatever command produced the push."""

    def test_hook_policy_matches_the_campaign_runtime(self):
        """The self-contained hook must recognise receipts written by the current runtime."""
        modules = self.modules()
        self.assertEqual(modules['review_prepush'].POLICY, modules['review_flow'].POLICY)

    def test_a_waived_receipt_reaches_the_remote_and_a_broken_one_does_not(self):
        """A candidate whose Codex the runtime could not run clears on the substitute pair,
        and the real hook lets it land. The same receipt past its window does not, and
        neither does one that names the substitute with no waiver at all: the hook re-runs
        the probe rather than reading the claim."""
        prepush = self.modules()['review_prepush']
        binary = prepush.resolve_codex()
        waiver = dict(reason='quota' if binary else 'absent', at=int(time.time()), binary=binary or '')
        substitute = {'claude': {}, 'claude-b': {}}

        landed = self.dangling('waived candidate')
        self.receipt(landed, reviews=substitute, codex_waiver=waiver)
        self.assertEqual(self.attempt(f'git push origin {landed}:refs/heads/waived').returncode, 0)
        self.assertTrue(self.remote_has(landed))

        for name, broken in (('stale', dict(waiver, at=int(time.time()) - prepush.WAIVER_TTL - 60)),
                             ('future', dict(waiver, at=int(time.time()) + 7200)),
                             ('alone', None)):
            refused = self.dangling(name + ' waiver')
            self.receipt(refused, reviews=substitute, **({'codex_waiver': broken} if broken else {}))
            result = self.attempt(f'git push origin {refused}:refs/heads/{name}')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.remote_has(refused))

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
                self.assertIn('cannot be pushed: no completed review', result.stderr, spelling)

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

    def test_orphaned_probe_receipt_is_void_as_soon_as_its_process_is_gone(self):
        """A probe receipt is valid only while its holder file is locked by the probe; the
        hook and the adapter ignore one nobody holds, before any sweep runs and whatever
        pid the system reuses."""
        orphan = self.git('commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', 'interrupted probe')
        left = self.repo / '.git/bymax-review/probe-left'
        left.mkdir(parents=True)
        (left / 'holder').write_text('')
        (left / 'completed-probe.json').write_text(json.dumps(dict(
            head=orphan, cleared=True, policy=2, reviews=dict(claude={}, codex={}),
            probe_lock='holder', probe_pid=os.getpid())))  # a live pid: the lock decides, not the pid
        refused = self.attempt(f'git push origin {orphan}:refs/heads/orphan')
        self.assertIn('cannot be pushed: no completed review', refused.stderr)
        self.assertFalse(self.remote_has(orphan))
        guard = subprocess.run([sys.executable, str(FLOW.with_name('review_push.py'))], cwd=self.repo, env=self.env,
                               input=json.dumps(dict(tool_input=dict(command=f'git push origin {orphan}:refs/heads/orphan'))),
                               capture_output=True, text=True)
        self.assertEqual(guard.returncode, 2, guard.stderr)
        self.assertIn('No completed review for pushed commit', guard.stderr)
        # A probe receipt with a pid and nothing to hold is void too, however alive that pid is.
        (left / 'completed-probe.json').write_text(json.dumps(dict(
            head=orphan, cleared=True, policy=2, reviews=dict(claude={}, codex={}), probe_pid=os.getpid())))
        self.assertIn('cannot be pushed: no completed review',
                      self.attempt(f'git push origin {orphan}:refs/heads/orphan').stderr)
        (left / 'completed-probe.json').write_text(json.dumps(dict(
            head=orphan, cleared=True, policy=2, reviews=dict(claude={}, codex={}),
            probe_lock='holder', probe_pid=os.getpid())))
        # While a process holds the lock the same receipt is honoured.
        keeper = subprocess.Popen([sys.executable, '-c', 'import fcntl, sys, time; h = open(sys.argv[1]); '
                                   'fcntl.flock(h, fcntl.LOCK_EX); print("held", flush=True); time.sleep(30)',
                                   str(left / 'holder')], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(keeper.stdout.readline().strip(), 'held')
            self.assertEqual(self.attempt(f'git push origin {orphan}:refs/heads/orphan').returncode, 0)
        finally:
            keeper.kill()


if __name__ == '__main__':
    unittest.main()
