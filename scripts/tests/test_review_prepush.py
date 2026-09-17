"""Invariant layer: no spelling of a push reaches a remote without a receipt.

Every case here runs a REAL push against a bare remote through bash, exactly as the
Bash tool would, and then inspects the remote. The assertion is about what landed,
not about what any parser thought of the text, so a new spelling that defeats the
Bash adapter still has to get past the pre-push hook that git invokes with the SHA.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
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

    def modules(self):
        """Load the runtime and the self-contained checker beside it, as modules."""
        import importlib.util
        loaded = {}
        for name in ('review_flow', 'review_prepush'):
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

    def test_a_hook_that_resolves_this_machine_differently_is_replaced(self):
        """A receipt names the Codex its waiver was measured against, and the hook re-resolves
        that name before honouring it. A hook left by a release that computed the name
        differently therefore refuses every waived push, for a disagreement no message
        explains and no probe of receipt shape can see — both sides understand waivers
        perfectly. Shipping a change to how the name is computed means replacing the copy git
        runs, and what start leaves behind must agree with the runtime about this machine."""
        flow = self.modules()['review_flow']
        hook = self.repo / '.git/hooks/pre-push'
        bundle = FLOW.with_name('review_prepush.py').read_bytes()
        earlier = bundle + b'\n\ndef resolve_codex():\n    return "/an/earlier/release/codex"\n'
        hook.write_bytes(earlier)
        hook.chmod(0o755)
        self.assertNotEqual(flow.hook_view(hook), flow.resolve_codex())

        flow.SUPERSEDED = frozenset({hashlib.sha256(earlier).hexdigest()})
        self.install(flow)
        self.assertEqual(flow.hook_view(hook), flow.resolve_codex())
        self.assertEqual(hook.read_bytes(), bundle)

    def test_a_hook_that_runs_at_import_cannot_escape_or_hang_the_view(self):
        """A probe receipt is built from the checker's own view of the machine, and the hook
        it borrows that from may be one somebody merged a check into — the shape install_hook
        asks for by name. Such a hook runs its check at import: executing it in this process
        lets SystemExit past every guard the runtime has, since it is not an Exception, and a
        hook that reads stdin at import never returns at all. Neither may reach start."""
        flow = self.modules()['review_flow']
        hook = self.root / 'handmade-pre-push'

        hook.write_text('#!/usr/bin/env python3\nimport sys\nsys.exit(3)\n')
        self.assertEqual(flow.hook_view(hook), flow.resolve_codex())

        hook.write_text('#!/usr/bin/env python3\nimport sys\nsys.stdin.read()\nsys.exit(0)\n')
        began = time.monotonic()
        self.assertEqual(flow.hook_view(hook), flow.resolve_codex())
        self.assertLess(time.monotonic() - began, flow.HOOK_SECONDS)

        # A hook is asked for its view; it does not get to announce one. Measured before the
        # marker carried a nonce: a hook printing the fixed marker at import did win.
        hook.write_text('#!/usr/bin/env python3\nprint("' + flow.VIEW_MARKER + '/spoofed/codex")\n')
        self.assertEqual(flow.hook_view(hook), flow.resolve_codex())

        # A checker that does know about waivers is still the one that is asked.
        self.assertEqual(flow.hook_view(FLOW.with_name('review_prepush.py')), flow.resolve_codex())

    def test_an_untouched_bundle_from_an_earlier_release_is_replaced(self):
        """The hook carries the receipt rule, so shipping a change to that rule means
        replacing the copy git actually runs. Only bytes a release shipped: a hook somebody
        merged a check into is reported for reconciliation, never overwritten."""
        flow = self.modules()['review_flow']
        hook = self.repo / '.git/hooks/pre-push'
        bundle = FLOW.with_name('review_prepush.py').read_bytes()
        earlier = bundle + b'\n# shipped by an earlier release\n'
        hook.write_bytes(earlier)
        flow.SUPERSEDED = frozenset({hashlib.sha256(earlier).hexdigest()})
        self.install(flow)
        self.assertEqual(hook.read_bytes(), bundle)

        merged = bundle + b'\n# a check merged in by hand\n'
        hook.write_bytes(merged)
        hook.chmod(0o755)
        self.install(flow)
        self.assertEqual(hook.read_bytes(), merged)

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
        self.assertIn('holds no pre-push', self.start_refused())
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
        self.assertIn('cannot be pushed: no completed review', refused.stderr)
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
        self.assertEqual(list((self.repo / '.git/bymax-review').glob('probe-*')), [])

    def test_probe_push_looks_real_to_a_fussy_hook(self):
        """A merged hook that also checks the pushed ref, parent and remote, as a real push
        offers them, is accepted; the receipt check behind it still refuses a real push."""
        checker = sys.executable + ' ' + str(FLOW.with_name('review_prepush.py'))
        fussy = ('#!/bin/sh\n# Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.\n'
                 '[ "$2" = "$(git remote get-url origin)" ] || exit 3\n'
                 'lines=$(cat)\n'
                 'printf "%s\\n" "$lines" | while read l s r x; do\n'
                 '  [ "$(git rev-parse --verify -q "$l")" = "$s" ] || exit 4\n'
                 '  git rev-parse --verify -q "$s^" >/dev/null || exit 5\n'
                 '  [ "$(git log -1 --format=%ae "$s")" = "$(git config user.email)" ] || exit 8\n'
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
        self.assertIn('cannot be pushed: no completed review', refused.stderr)
        self.assertFalse(self.remote_has(self.git('rev-parse', 'HEAD')))

    def test_concurrent_starts_in_linked_worktrees_probe_independently(self):
        """Two campaigns starting at once on sibling worktrees share the common directory;
        neither probe may replace or remove the other's temporary receipt."""
        other = self.root / 'other'
        self.git('worktree', 'add', '-q', '-b', 'other', str(other))
        # An honest hook that takes a moment widens the window in which the probes overlap.
        hook = self.repo / '.git/hooks/pre-push'
        hook.write_text('#!/bin/sh\n# Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.\n'
                        'sleep 1\nexec ' + sys.executable + ' ' + str(FLOW.with_name('review_prepush.py')) + ' "$@"\n')
        hook.chmod(0o755)
        command = [sys.executable, str(FLOW), 'start', '--base', self.base, '--context', str(self.root / 'context.json')]
        results = {}

        def start(name, cwd, delay):
            time.sleep(delay)
            results[name] = subprocess.run(command, cwd=cwd, env=self.env, capture_output=True, text=True)

        for delay in (0.0, 0.5):
            threads = [threading.Thread(target=start, args=('repo', self.repo, 0.0)),
                       threading.Thread(target=start, args=('other', other, delay))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            for name, result in results.items():
                self.assertEqual(result.returncode, 0, f'{name} with {delay}s offset: {result.stderr}')
        self.assertEqual(list((self.repo / '.git/bymax-review').glob('probe-*')), [])

    def test_start_from_a_subdirectory_probes_the_hook_at_the_toplevel(self):
        """git runs pre-push from the worktree root, so a merged hook naming its checker by a
        root-relative path is valid; the probe must run it from there wherever start runs."""
        tools = self.repo / '.git/tools'
        tools.mkdir()
        (tools / 'check.py').write_bytes(FLOW.with_name('review_prepush.py').read_bytes())
        hook = self.repo / '.git/hooks/pre-push'
        hook.write_text('#!/bin/sh\n# Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.\n'
                        'exec ' + sys.executable + ' .git/tools/check.py "$@"\n')
        hook.chmod(0o755)
        (self.repo / 'sub').mkdir()
        result = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base,
                                 '--context', str(self.root / 'context.json')],
                                cwd=self.repo / 'sub', env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        # The same hook keeps enforcing when git runs it from the root on a real push.
        self.commit('unreviewed')
        refused = self.attempt('git push origin HEAD:feature')
        self.assertIn('cannot be pushed: no completed review', refused.stderr)
        self.assertFalse(self.remote_has(self.git('rev-parse', 'HEAD')))

    def test_husky_stub_delegating_to_a_tracked_hook_qualifies(self):
        """husky points core.hooksPath at a generated directory and rewrites its stubs on every
        install; the tracked hook the stub delegates to is where the check lives, and start
        judges the pair by behaviour, so the arrangement survives regeneration."""
        husky = self.repo / '.husky'
        (husky / '_').mkdir(parents=True)
        (husky / '_' / '.gitignore').write_text('*\n')
        (husky / '_' / 'h').write_text('#!/usr/bin/env sh\nn=$(basename "$0")\ns=$(dirname "$(dirname "$0")")/$n\n'
                                       '[ ! -f "$s" ] && exit 0\nsh -e "$s" "$@"\n')
        stub = '#!/usr/bin/env sh\n. "${0%/*}/h"\n'
        (husky / '_' / 'pre-push').write_text(stub)
        (husky / '_' / 'pre-push').chmod(0o755)
        (husky / 'pre-push').write_text('echo tracked-hook >&2\n' + sys.executable + ' '
                                        + str(FLOW.with_name('review_prepush.py')) + ' "$@"\n')
        # Excluded rather than committed so HEAD stays the candidate the fixture froze.
        (self.repo / '.git/info/exclude').write_text('.husky/\n')
        self.git('config', 'core.hooksPath', '.husky/_')
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        (husky / '_' / 'pre-push').write_text(stub)  # regenerated by husky's prepare script
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        self.assertEqual((husky / '_' / 'pre-push').read_text(), stub)
        self.commit('unreviewed')
        refused = self.attempt('git push origin HEAD:feature')
        self.assertIn('cannot be pushed: no completed review', refused.stderr)
        self.assertFalse(self.remote_has(self.git('rev-parse', 'HEAD')))
        # The tracked hook without the check is what is judged, not the stub's shape.
        self.git('reset', '-q', '--hard', 'HEAD~1')
        (husky / 'pre-push').write_text('echo tracked-hook >&2\n')
        self.assertIn('does not enforce receipts', self.start_refused())

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

    def test_kept_hook_must_refuse_an_orphaned_receipt(self):
        """A kept hook that honours a receipt nobody holds — whether it ignores holders or only
        honours receipts without one — fails the third or the fourth push; a checker copy edited
        by hand that passes every push is kept byte for byte."""
        hook = self.repo / '.git/hooks/pre-push'
        careless = ('#!/bin/sh\n# Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.\n'
                    'while read l s r x; do grep -lq "\\"head\\": \\"$s\\"" .git/bymax-review/*/completed-*.json '
                    '2>/dev/null || exit 1; done\nexit 0\n')
        hook.write_text(careless)
        hook.chmod(0o755)
        self.assertIn('orphaned probe receipt', self.start_refused())
        self.assertEqual(hook.read_text(), careless)
        # A checker that checks holders but honours a receipt with none to check fails the
        # fourth push.
        (self.repo / '.git/tools').mkdir()
        (self.repo / '.git/tools/halfway.py').write_text(
            'import fcntl, glob, json, sys\nfrom pathlib import Path\n'
            'for line in sys.stdin:\n'
            '    l, s, r, x = line.split()\n'
            '    for p in glob.glob(".git/bymax-review/*/completed-*.json"):\n'
            '        state = json.load(open(p))\n'
            '        if state.get("head") != s:\n'
            '            continue\n'
            '        if "probe_lock" not in state:\n'
            '            break  # honoured with nothing to hold: void, yet accepted here\n'
            '        try:\n'
            '            with open(Path(p).parent / state["probe_lock"]) as holder:\n'
            '                fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)\n'
            '        except BlockingIOError:\n'
            '            break\n'
            '    else:\n'
            '        sys.exit(1)\n')
        hook.write_text('#!/bin/sh\n# Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.\n'
                        'exec ' + sys.executable + ' .git/tools/halfway.py "$@"\n')
        self.assertIn('orphaned probe receipt', self.start_refused())
        merged = FLOW.with_name('review_prepush.py').read_bytes() + b'\n# a check merged in by hand\n'
        hook.write_bytes(merged)
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        self.assertEqual(hook.read_bytes(), merged)
        self.assertEqual(list((self.repo / '.git/bymax-review').glob('probe-*')), [])
        self.assertEqual(self.git('for-each-ref', 'refs/bymax-review/'), '')

    def test_sweep_bound_outlasts_every_hook_run_of_one_probe(self):
        """An interrupted probe's refs are swept only once older than a probe can be, so the
        bound must exceed what the probe's own hook runs can consume: a push added to the
        probe without raising it would let a sibling start sweep refs still in flight."""
        import importlib.util
        spec = importlib.util.spec_from_file_location('flow_bound', FLOW)
        flow = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(flow)
        runs = []
        original = flow.run_hook
        flow.run_hook = lambda path, remote, line, _o=original: (runs.append(line), _o(path, remote, line))[1]
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            flow.install_hook()
        finally:
            os.chdir(cwd)
        self.assertTrue(runs)
        self.assertGreater(flow.PROBE_BOUND, len(runs) * flow.HOOK_SECONDS)

    def test_kept_hook_must_check_every_record_of_a_multi_ref_push(self):
        """git hands the hook one record per pushed ref. A hook that reads a single one of them
        and delegates only that lets the other commits land, so the probe's two multi-ref pushes
        place an unreceipted commit where each fixed position reads a receipted one."""
        hook = self.repo / '.git/hooks/pre-push'
        marker = '#!/bin/sh\n# Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.\n'
        delegate = ' | exec ' + sys.executable + ' ' + str(FLOW.with_name('review_prepush.py')) + ' "$@"\n'
        middle = ('lines=$(cat)\nif [ "$(printf "%s\\n" "$lines" | wc -l)" -ge 3 ]; then '
                  'printf "%s\\n" "$lines" | sed -n 2p; else printf "%s\\n" "$lines"; fi')
        leading_pair = 'printf "%s\\n" "$(cat)" | sed -n 1,2p'
        for sampler in ('read l s r x\nprintf "%s %s %s %s\\n" "$l" "$s" "$r" "$x"',
                        'while read l s r x; do last="$l $s $r $x"; done\nprintf "%s\\n" "$last"',
                        middle, leading_pair):
            hook.write_text(marker + sampler + delegate)
            hook.chmod(0o755)
            self.assertIn('one of whose commits holds no receipt', self.start_refused())
        # Each record carries its own remote ref, as git gives a push of three refs, so a
        # hook that reads every record but keys on the remote ref still sees all three.
        hook.write_text(marker + 'printf "%s\\n" "$(cat)" | awk \'!seen[$3]++\'' + delegate)
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        # The real checker reads every record: a push of two refs, one receipted and one not,
        # lands neither.
        hook.unlink()
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        cleared = self.git('commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', 'cleared')
        unreviewed = self.git('commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', 'unreviewed')
        receipt = self.repo / '.git/bymax-review/campaign'
        receipt.mkdir(parents=True)
        (receipt / f'completed-{cleared}.json').write_text(json.dumps(dict(
            head=cleared, cleared=True, policy=2, reviews=dict(claude={}, codex={}))))
        for spelling in (f'git push origin {cleared}:refs/heads/a {unreviewed}:refs/heads/b',
                         f'git push origin {unreviewed}:refs/heads/b {cleared}:refs/heads/a'):
            self.assertIn('cannot be pushed: no completed review', self.attempt(spelling).stderr)
            self.assertFalse(self.remote_has(unreviewed) or self.remote_has(cleared))

    def test_interrupted_probe_ref_is_swept_once_older_than_a_probe(self):
        """A temporary probe ref left by a kill is deleted by the next probe when its commit is
        older than a probe can be; a younger one may belong to a sibling and is kept."""
        stale_env = dict(self.env, GIT_COMMITTER_DATE='2020-01-01T00:00:00Z', GIT_AUTHOR_DATE='2020-01-01T00:00:00Z')
        old = subprocess.check_output(['git', 'commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', 'old probe'],
                                      cwd=self.repo, env=stale_env, text=True).strip()
        young = self.git('commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', 'young probe')
        self.git('update-ref', 'refs/bymax-review/probe-old', old)
        self.git('update-ref', 'refs/bymax-review/probe-young', young)
        # An exported old GIT_COMMITTER_DATE must not date the probe's own commit, or the
        # sweep would take the live probe ref for a stale one mid-probe and a hook that
        # checks the ref resolves to the pushed SHA would be refused.
        hook = self.repo / '.git/hooks/pre-push'
        hook.write_text('#!/bin/sh\n# Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.\n'
                        'lines=$(cat)\nprintf "%s\\n" "$lines" | while read l s r x; do\n'
                        '  [ "$(git rev-parse --verify -q "$l")" = "$s" ] || exit 4\ndone || exit $?\n'
                        'printf "%s\\n" "$lines" | exec ' + sys.executable + ' '
                        + str(FLOW.with_name('review_prepush.py')) + ' "$@"\n')
        hook.chmod(0o755)
        result = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base,
                                 '--context', str(self.root / 'context.json')],
                                cwd=self.repo, env=stale_env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('for-each-ref', '--format=%(refname)', 'refs/bymax-review/'),
                         'refs/bymax-review/probe-young')

    def test_interrupted_probe_receipt_is_swept_before_it_can_clear_a_push(self):
        """A probe killed mid-run leaves a receipt for a commit carrying the candidate's tree;
        the next probe removes it once it is older than a probe can be."""
        stale = self.repo / '.git/bymax-review/probe-left'
        stale.mkdir(parents=True)
        orphan = self.git('commit-tree', 'HEAD^{tree}', '-p', 'HEAD', '-m', 'interrupted probe')
        (stale / 'completed-probe.json').write_text(json.dumps(dict(
            head=orphan, cleared=True, policy=2, reviews=dict(claude={}, codex={}))))
        os.utime(stale, (time.time() - 3600, time.time() - 3600))
        self.assertEqual(self.attempt(f'git push origin {orphan}:refs/heads/orphan').returncode, 0)
        self.git('push', '-q', 'origin', ':refs/heads/orphan')  # a deletion needs no receipt
        self.flow('start', '--base', self.base, '--context', str(self.root / 'context.json'))
        self.assertFalse(stale.exists())
        self.assertNotEqual(self.attempt(f'git push origin {orphan}:refs/heads/orphan').returncode, 0)
        self.assertFalse(self.remote_has(orphan))

    def test_dangling_hook_symlink_is_refused_not_written_through(self):
        """A symlink at hooks/pre-push whose target does not exist yet is somebody's hook
        arrangement: start refuses it as unmanaged instead of creating the target file."""
        hook = self.repo / '.git/hooks/pre-push'
        hook.unlink()
        hook.symlink_to(self.repo / 'scripts/hooks/pre-push')
        self.assertIn('not managed by this campaign', self.start_refused())
        self.assertFalse((self.repo / 'scripts/hooks/pre-push').exists())
        self.assertTrue(hook.is_symlink())
        hook.unlink()
        hook.symlink_to(self.repo / '.git')  # a symlink to a directory is not a hook either
        self.assertIn('is a directory, so git cannot run it', self.start_refused())
        self.assertTrue(hook.is_symlink())

    def test_stale_bundled_hook_is_refused_not_kept(self):
        """A bundled copy declaring another policy would refuse every push if kept; it is refused."""
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
