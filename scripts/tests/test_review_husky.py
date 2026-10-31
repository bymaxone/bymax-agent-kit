"""Invariant layer: the receipt check survives husky regenerating its hooks directory.

husky points core.hooksPath at `.husky/_`, a directory it generates, ignores in git and rewrites
on every install — and `prepare`, which many package scripts trigger, is an install. A receipt
check placed there by hand was dropped silently by the next `pnpm <script>`, and a check placed
in the tracked `.husky/pre-push` has to name a script on one person's machine. The runtime now
chains the check ahead of husky's dispatcher itself, writes it again whenever husky has replaced
it, and says so loudly; nothing is committed to the repository.

The fixture is test_review_prepush's: a repository and a bare remote whose contents are the only
evidence of what a push did.
"""
from pathlib import Path
import subprocess
import sys
import unittest

# The bench is test_review_prepush's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_prepush import CAMPAIGN_TIMEOUT, FLOW, PrePushBench

# husky 9's dispatcher, reduced to what decides a push: the tracked hook named like the one git
# ran is executed with the same arguments and stdin, and its status is the hook's.
DISPATCHER = ('#!/usr/bin/env sh\nn=$(basename "$0")\ns=$(dirname "$(dirname "$0")")/$n\n'
              '[ ! -f "$s" ] && exit 0\nsh -e "$s" "$@"\nc=$?\nexit $c\n')
STUBS = ('#!/usr/bin/env sh\n. "$(dirname "$0")/h"', '#!/usr/bin/env sh\n. "${0%/*}/h"')


class HuskyChainTests(PrePushBench):
    """`start`, `status` and `finish` keep the check in husky's generated pre-push."""

    def setUp(self):
        """Lay husky's generated directory out the way `husky` does, and point git at it."""
        super().setUp()
        self.generated = self.repo / '.husky' / '_'
        self.generated.mkdir(parents=True)
        (self.generated / '.gitignore').write_text('*')
        (self.generated / 'h').write_text(DISPATCHER)
        self.regenerate(STUBS[0])
        self.git('config', 'core.hooksPath', '.husky/_')
        self.context = str(self.root / 'context.json')

    def regenerate(self, stub):
        """What husky's install does to the pre-push it generated."""
        hook = self.generated / 'pre-push'
        hook.write_text(stub)
        hook.chmod(0o755)

    def track(self, body):
        """A tracked `.husky/pre-push`, excluded rather than committed so HEAD stays the
        candidate the fixture froze."""
        (self.repo / '.husky' / 'pre-push').write_text(body)
        (self.repo / '.git/info/exclude').write_text('.husky/pre-push\n')

    def run_flow(self, *args):
        """A lifecycle command, returning the finished process whatever its status."""
        return subprocess.run([sys.executable, str(FLOW), *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, timeout=CAMPAIGN_TIMEOUT)

    def started(self):
        """`start` on the fixture candidate, required to succeed."""
        result = self.run_flow('start', '--base', self.base, '--context', self.context)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def refuses_an_unreviewed_push(self):
        """Commit something nobody reviewed and show the remote never receives it."""
        self.commit('unreviewed ' + str(len(self.git('log', '--oneline').splitlines())))
        refused = self.attempt('git push origin HEAD:feature')
        self.assertIn('cannot be pushed: no completed review', refused.stderr)
        self.assertFalse(self.remote_has(self.git('rev-parse', 'HEAD')))

    def test_start_chains_the_check_into_the_generated_hook(self):
        """husky's stub runs nothing when no tracked hook exists, so a repository using husky
        had no check at all; `start` writes the chain there instead of refusing."""
        for stub in STUBS:
            with self.subTest(stub=stub):
                self.regenerate(stub)
                self.assertIn('husky', self.started().stderr)
                self.assertIn('Git pre-push hook: refuse to publish', (self.generated / 'pre-push').read_text())
                self.refuses_an_unreviewed_push()
                self.git('reset', '-q', '--hard', self.head)

    def test_the_tracked_husky_hook_still_runs_and_still_decides(self):
        """The chain runs husky's own hook after the check, with the same records: it reaches the
        remote only when both pass, so nothing husky enforced is lost."""
        self.track('echo tracked-hook-ran >&2\nexit 0\n')
        self.started()
        self.receipt(self.head)
        landed = self.attempt('git push origin HEAD:feature')
        self.assertEqual(landed.returncode, 0, landed.stderr)
        self.assertIn('tracked-hook-ran', landed.stderr)
        self.assertTrue(self.remote_has(self.head))
        self.track('echo tracked-hook-refused >&2\nexit 1\n')
        refused = self.attempt('git push origin HEAD:other')
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('tracked-hook-refused', refused.stderr)

    def test_status_and_finish_heal_a_regenerated_hook_and_say_so(self):
        """`pnpm <script>` regenerates the stub between steps; the next status or finish writes
        the chain again and warns, and the push after it is refused."""
        self.started()
        for action in ('status', 'finish'):
            with self.subTest(action=action):
                self.regenerate(STUBS[0])
                result = self.run_flow(action)
                self.assertIn('husky', result.stderr)
                self.assertIn('receipt check', result.stderr)
                self.assertIn('Git pre-push hook: refuse to publish', (self.generated / 'pre-push').read_text())
        self.refuses_an_unreviewed_push()

    def test_an_intact_chain_is_left_alone_and_nothing_is_committed(self):
        """A chain already in place is not announced again, and the repository's own tree is
        untouched: husky's generated directory is ignored by git."""
        self.started()
        quiet = self.run_flow('status')
        self.assertNotIn('husky', quiet.stderr)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_a_hook_somebody_wrote_there_is_never_overwritten(self):
        """Only husky's own stub is replaced: a pre-push written by hand is judged by the probe
        pushes as before, and kept byte for byte when it is refused."""
        written = '#!/bin/sh\necho mine\nexit 0\n'
        self.regenerate(written)
        refused = self.run_flow('start', '--base', self.base, '--context', self.context)
        self.assertEqual(refused.returncode, 2, refused.stdout)
        self.assertIn('does not enforce receipts', refused.stderr)
        self.assertEqual((self.generated / 'pre-push').read_text(), written)

    def test_a_hooks_path_that_is_not_huskys_is_never_written(self):
        """The chain is for husky's generated directory alone: any other core.hooksPath stays the
        user's, as it always was."""
        custom = self.root / 'hooks'
        custom.mkdir()
        self.git('config', 'core.hooksPath', str(custom))
        self.assertIn('holds no pre-push', self.start_refused())
        self.assertFalse((custom / 'pre-push').exists())


if __name__ == '__main__':
    unittest.main()
