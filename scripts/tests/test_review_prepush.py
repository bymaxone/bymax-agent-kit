"""Invariant layer: no spelling of a push reaches a remote without a receipt, once git runs the hook.

The qualification is the whole of it, and this file carries its own counterexample sixty lines
down: `git push --no-verify` is git's own escape and no local design closes it. What these
cases hold is that a spelling which does reach the hook cannot get past it.

Every case here runs a REAL push against a bare remote through bash, exactly as the
Bash tool would, and then inspects the remote. The assertion is about what landed,
not about what any parser thought of the text, so a new spelling that defeats the
Bash adapter still has to get past the pre-push hook that git invokes with the SHA.
"""
import ast
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

    def test_a_probe_receipt_outlasts_the_hook_that_reads_it(self):
        """A slow hook must not be reported as a disagreeing one.

        The probe dates a temporary receipt just inside the waiver window and hands it to the
        kept hook, whose run is bounded by HOOK_SECONDS. With the margin equal to that bound, a
        hook that used its whole budget would watch the waiver expire while it read the receipt
        and refuse it — and the runtime would answer "shorter waiver window", which is a claim
        about the hook's policy for what was a timeout. Two constants that must not be equal is
        the kind of thing a reader checks once and a case checks always.
        """
        flow = self.modules()['review_flow']
        self.assertGreater(flow.PROBE_MARGIN, flow.HOOK_SECONDS,
                           'a probe receipt must stay valid for longer than the hook may take')
        fresh = flow.waived_shape()[1]
        stale = flow.waived_shape(stale=True)[1]
        now = int(time.time())
        # Fresh is inside the window by the margin; stale is outside it by the margin.
        self.assertGreater(now - fresh['at'], 0)
        self.assertLess(now - fresh['at'], flow.WAIVER_TTL)
        self.assertGreater(now - stale['at'], flow.WAIVER_TTL)
        self.assertAlmostEqual(flow.WAIVER_TTL - (now - fresh['at']), flow.PROBE_MARGIN, delta=5)
        self.assertAlmostEqual((now - stale['at']) - flow.WAIVER_TTL, flow.PROBE_MARGIN, delta=5)
        # The arithmetic above is not what makes the invariant hold: the dated receipt has to be
        # the one the probe hands the hook. Asserted at the call site, which is where an edit
        # would break it without touching either constant.
        source = (ROOT / 'plugins/bymax-quality/scripts/review_flow.py').read_text()
        # By AST, not by text: probe_receipt's own docstring names waived_shape(), so a textual
        # search is satisfied by the prose and passes with the call removed. Measured — the
        # first version of this assertion did exactly that.
        probe = next(n for n in ast.walk(ast.parse(source))
                     if isinstance(n, ast.FunctionDef) and n.name == 'probe_receipt')
        called = {c.func.id for c in ast.walk(probe)
                  if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        self.assertIn('waived_shape', called,
                      'the receipt no longer carries what waived_shape dates, so the margin '
                      'above is arithmetic nothing reads')

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
        """usable_hook asks the kept hook how it resolves Codex, to require that its answer
        matches the runtime's, and the hook it asks may be one somebody merged a check into — the
        shape install_hook asks for by name. Such a hook runs its check at import: executing it
        in this process
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

    def test_the_refusals_that_want_a_different_remedy_are_the_three_named(self):
        """The sentence about which refusals route through hook_remedy has been written wrongly
        five times — three unchecked counts, then a universal, then a universal with the wrong
        scope. Nothing checked it, which is the whole reason it kept drifting.

        What is stable is the rule: a refusal about a hook that exists and does not enforce asks
        the helper; three want a different answer, because this one would be wrong for them. A
        hook that is merely not executable wants chmod. A custom hooks directory holding no
        pre-push wants one added there — there is no file to fix. A hook this campaign did not
        install is never displaced, so it wants a hand merge. Those three are asserted by what
        they are about, so adding a fourth exception fails here and the prose gets corrected
        with the code instead of five rounds later.
        """
        source = (ROOT / 'plugins/bymax-quality/scripts/review_flow.py').read_text()
        tree = ast.parse(source)
        other = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef)
                    and node.name in ('usable_hook', 'upholds', 'run_hook', 'install_hook')):
                continue
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) \
                        and call.func.id in ('require', 'ValueError') \
                        and 'hook_remedy' not in (ast.get_source_segment(source, call) or ''):
                    other.append(ast.get_source_segment(source, call) or '')
        self.assertEqual(len(other), 3, 'the set of refusals wanting a different remedy moved; '
                                        'correct the rule in hook_remedy and the changelog with '
                                        'it: ' + str([o[:60] for o in other]))
        subjects = ' '.join(other)
        for marks in ('not executable', 'holds no pre-push', 'not managed by this campaign'):
            self.assertIn(marks, subjects, 'an exception changed what it is about')

    def test_every_hook_refusal_asks_the_shared_remedy(self):
        """Every refusal in upholds ends with hook_remedy, and none anywhere spells one by hand.

        The first version of this gate blacklisted four delete-flavoured phrases, line by line,
        while its name asserted the positive property. Both halves leaked. A refusal that
        copied hook_remedy's own clause — 'keeping any check you merged in' — sat inside a
        scanned function and passed, because the phrase was not on the list. And the per-line
        exemption skipped any line containing `hook_remedy`, which is the last line of every
        refusal that calls it, and therefore exactly where a reattached remedy would land.

        So the property is asserted as stated: over statements, by AST, positively for the
        function whose every refusal is about a hook that exists and failed, and negatively for
        the rest by the phrases the helper itself owns.
        """
        source = (ROOT / 'plugins/bymax-quality/scripts/review_flow.py').read_text()
        tree = ast.parse(source)

        def refusals(name):
            """Each require()/raise ValueError() statement in the named function, as source."""
            node = next(n for n in ast.walk(tree)
                        if isinstance(n, ast.FunctionDef) and n.name == name)
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) \
                        and call.func.id in ('require', 'ValueError'):
                    yield ast.get_source_segment(source, call) or ''

        # upholds exists to refuse a hook that is present and does not enforce; every one of its
        # refusals is therefore about a file the reader has, and every one must say how to fix it.
        silent = [r[:70] for r in refusals('upholds') if 'hook_remedy' not in r]
        self.assertFalse(silent, 'a refusal in upholds does not offer the shared remedy: ' + str(silent))
        self.assertGreaterEqual(sum(1 for _ in refusals('upholds')), 5, 'upholds stopped refusing')

        # And nowhere may a refusal SPELL a remedy, whether or not it also asks for one. No
        # exemption at all: the helper's contribution to a statement is a call, and a call
        # carries no string literals, so scanning only what the refusal spells for itself
        # separates the two exactly. The previous two versions exempted first by line and then
        # by statement, and the second was the wider hole — nearly every refusal site calls the
        # helper, so skipping them left the negative half examining almost nothing.
        owned = [value.value for value in ast.walk(
                     next(n for n in ast.walk(tree)
                          if isinstance(n, ast.FunctionDef) and n.name == 'hook_remedy'))
                 if isinstance(value, ast.Constant) and isinstance(value.value, str)
                 and len(value.value) > 12]
        self.assertGreaterEqual(len(owned), 2, 'hook_remedy stopped owning any wording')
        # A floor that does not depend on the helper's current phrasing, so rewording the
        # helper cannot silently shrink what counts as spelling a remedy.
        FLOOR = ('delete it', 'delete the hook', 'reinstall', 'reinstalls', 'remove it')
        offenders = []
        for name in ('usable_hook', 'upholds', 'run_hook', 'install_hook'):
            node = next(n for n in ast.walk(tree)
                        if isinstance(n, ast.FunctionDef) and n.name == name)
            for call in ast.walk(node):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                        and call.func.id in ('require', 'ValueError')):
                    continue
                spelled = ' '.join(c.value for c in ast.walk(call)
                                   if isinstance(c, ast.Constant) and isinstance(c.value, str))
                hits = [w for w in FLOOR if w in spelled.lower()]
                hits += [phrase for phrase in owned if phrase.strip()[:18] in spelled]
                if hits:
                    offenders.append(f'{name}: {sorted(set(hits))} in {spelled[:60]!r}')
        self.assertFalse(offenders, 'a refusal spells deletion wording, or a phrase hook_remedy '
                                    'owns, instead of asking it: ' + '; '.join(offenders)
                                    + '. This detects that vocabulary and the helper\'s own '
                                      'phrasings, not every conceivable remedy.')

    def test_a_custom_hooks_directory_is_never_told_to_delete_its_hook(self):
        """Five refusals told the reader to delete the hook and let start reinstall it. That is
        a remedy for the repository's own hooks directory and the opposite of one for a custom
        core.hooksPath: start never writes there, so deleting leaves the repository with no
        check at all and the next start can only report an empty directory.

        This case observes ONE of those refusals — the fixture's hook exits 0 on the first
        probe, so upholds raises before the others are built — and an earlier version of this
        docstring claimed it covered all five. It did not, and reattaching the wording by hand
        to any of the other four left it green. The claim now lives where it can be true:
        test_every_hook_refusal_asks_the_shared_remedy asserts it over the source.
        """
        custom = self.root / 'custom-hooks'
        custom.mkdir()
        hook = custom / 'pre-push'
        # Marked and executable, so it gets past the shape checks and reaches the probes, and
        # enforcing nothing, so a probe refuses it and a remedy is printed.
        hook.write_text('#!/bin/sh\n# ' + 'Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.' + '\nexit 0\n')
        hook.chmod(0o755)
        self.git('config', 'core.hooksPath', str(custom))
        refused = self.start_refused()
        self.assertIn('does not enforce', refused)
        self.assertIn('Do not delete it', refused)
        self.assertIn('start never writes into one', refused)
        self.assertNotIn('Delete it so start reinstalls', refused)

        # And the repository's own hooks directory still gets the remedy that is true there.
        self.git('config', '--unset', 'core.hooksPath')
        own = Path(self.git('rev-parse', '--git-common-dir'))
        own = (Path(self.repo) / own).resolve() / 'hooks' / 'pre-push'
        own.write_text('#!/bin/sh\n# ' + 'Git pre-push hook: refuse to publish any commit that lacks a completed review receipt.' + '\nexit 0\n')
        own.chmod(0o755)
        refused = self.start_refused()
        self.assertIn('Delete it so start reinstalls', refused)
        self.assertNotIn('Do not delete it', refused)

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

    def test_sweep_bound_outlasts_every_bounded_execution_of_one_probe(self):
        """An interrupted probe's refs are swept only once older than a probe can be, so the
        bound must exceed what one probe can consume — and what it consumes is every bounded
        execution inside its window, not one kind of them. Counting only the pushes is how a
        bound that no longer held went on passing: a second kind of bounded execution was
        added inside the window and the guard could not see it. Both kinds are counted here,
        so a third kind fails this rather than a sibling's sweep."""
        flow = self.modules()['review_flow']
        # Counted at the one place every bounded execution must pass through, rather than at
        # the two this test knows the names of. Naming the kinds is what let a second kind be
        # added inside the window while the guard went on passing; a third would do it again.
        bounded = []
        original = flow.subprocess.run

        def counted(*args, **kwargs):
            if kwargs.get('timeout'):
                bounded.append(kwargs['timeout'])
            return original(*args, **kwargs)

        flow.subprocess.run = counted
        self.addCleanup(setattr, flow.subprocess, 'run', original)
        # A hand-merged hook, so install_hook probes what it keeps rather than writing a bundle.
        hook = self.repo / '.git/hooks/pre-push'
        hook.write_bytes(FLOW.with_name('review_prepush.py').read_bytes() + b'\n# merged by hand\n')
        hook.chmod(0o755)
        self.install(flow)
        self.assertTrue(bounded)
        self.assertGreater(flow.PROBE_BOUND, sum(bounded),
                           f'{len(bounded)} bounded executions totalling {sum(bounded)}s')

    def test_a_kept_hook_whose_waiver_window_differs_is_refused(self):
        """A receipt carries a waiver dated at a moment, and the hook decides whether that
        moment is still inside the window. A kept hook with a window of its own therefore
        refuses real waived pushes while passing every probe, exactly as one that resolved
        the binary differently did — the probes bounded the window from above and never from
        below, because the receipt they showed was dated now, which any window accepts."""
        flow = self.modules()['review_flow']
        hook = self.repo / '.git/hooks/pre-push'
        # Edited where the constant is declared, not appended: a hook runs main() from its
        # own __main__ block, so anything after it never executes and a window bolted on the
        # end is a window the hook never has. The case must be the case before it is asserted.
        bundle = FLOW.with_name('review_prepush.py').read_bytes()
        shorter = bundle.replace(b'WAIVER_TTL = 24 * 3600', b'WAIVER_TTL = 3600')
        shorter += b'\n# merged by hand\n'
        self.assertNotIn(b'WAIVER_TTL = 24 * 3600', shorter)
        hook.write_bytes(shorter)
        hook.chmod(0o755)
        with self.assertRaises(ValueError) as refusal:
            self.install(flow)
        self.assertIn('waiver', str(refusal.exception).lower())
        self.assertEqual(hook.read_bytes(), shorter)

    def test_a_kept_hook_that_resolves_this_machine_differently_is_refused(self):
        """A kept hook that computes the Codex name differently refuses every real waived push,
        because the receipt the runtime writes names the other path. The waived probe catches
        that too, since the receipt it shows the hook carries the runtime's name — measured, and
        worth stating rather than claiming the probes are blind to it. What the agreement check
        adds is the divergence a probe cannot reach, one that exists only while the hook is
        imported, and a refusal that names the disagreement instead of reporting a refused
        push. Replacing byte-identical bundles by hash reaches neither."""
        flow = self.modules()['review_flow']
        hook = self.repo / '.git/hooks/pre-push'
        # Diverted inside resolve_codex, not appended past the module body: a hook runs main()
        # from its own __main__ block, so anything after it never executes and the divergence
        # would exist only for the importing view — the same injection-point defect this file
        # corrected once already, in the window fixture below.
        merged = FLOW.with_name('review_prepush.py').read_bytes().replace(
            b'    for location in CODEX_LOCATIONS:',
            b'    return "/another/name/for/codex"\n    for location in CODEX_LOCATIONS:')
        merged += b'\n# merged by hand\n'
        self.assertIn(b'return "/another/name/for/codex"', merged)
        hook.write_bytes(merged)
        hook.chmod(0o755)
        with self.assertRaises(ValueError) as refusal:
            self.install(flow)
        self.assertIn('resolves', str(refusal.exception))
        self.assertEqual(hook.read_bytes(), merged)  # reported, never overwritten

    def test_the_view_survives_whatever_a_hook_writes_at_import(self):
        """stdout is the channel the view comes back on, and a hook may write anything to it
        before the driver answers. Strict decoding turns a stray byte into an exception that
        is neither OSError nor SubprocessError, so it escapes the fallback this function
        promises; an unterminated write swallows the answer line instead.

        Each case proves it reached the branch it names before asserting the outcome. The
        first version of this test did not: its hook carried the stray byte in its source,
        which does not compile, so the child died before writing anything and the assertion
        held against unfixed code. An outcome a case reaches by another road is not evidence
        about the road it names.
        """
        flow = self.modules()['review_flow']
        hook = self.root / 'writes-at-import'

        # Valid source, invalid output: the byte must reach the decode, so the raw stdout
        # this case produces must itself be undecodable. Asserted, not assumed.
        hook.write_text('#!/usr/bin/env python3\nimport sys\n'
                        'sys.stdout.buffer.write(bytes([0xff, 0xfe]))\n'
                        'sys.stdout.buffer.flush()\n'
                        'def resolve_codex():\n    return "/the/hooks/own/view"\n')
        raw = subprocess.run([sys.executable, str(hook)], capture_output=True).stdout
        with self.assertRaises(UnicodeDecodeError):
            raw.decode('utf-8')
        self.assertEqual(flow.hook_view(hook), '/the/hooks/own/view')

        hook.write_text('#!/usr/bin/env python3\nimport sys\n'
                        'sys.stdout.write("no newline here")\n'
                        'def resolve_codex():\n    return "/the/real/view"\n')
        self.assertEqual(flow.hook_view(hook), '/the/real/view')

    def test_a_hook_that_outlasts_the_bound_is_not_waited_on(self):
        """The timeout is the only thing standing between a probe and a hook that never
        returns; the stdin case returns because the child is fed nothing, and proves the
        other branch."""
        flow = self.modules()['review_flow']
        flow.HOOK_SECONDS = 1
        hook = self.root / 'slow-hook'
        hook.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n')
        began = time.monotonic()
        self.assertEqual(flow.hook_view(hook), flow.resolve_codex())
        self.assertLess(time.monotonic() - began, 15)

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
