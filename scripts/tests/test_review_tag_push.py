"""Invariant layer: a tag on a commit the remote's default branch already holds can be pushed.

A release tag points at the squash commit GitHub wrote on origin/main when it merged a reviewed
pull request. No receipt names that commit, since GitHub made it, so both the Bash guard and the
pre-push hook refused a push that publishes no new source. A push of tags only, each peeling to a
commit already on that remote's default branch — read from the remote itself and matching the
remote-tracking ref — needs no receipt. Every other shape is judged by receipts as before, and
the cases below by what the remote received.

The fixture is test_review_prepush's: a repository whose hook `start` installed, and a bare
remote whose contents are the only evidence of what a push did.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

# The bench is test_review_prepush's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_prepush import FLOW, PrePushBench

PUSH = FLOW.with_name('review_push.py')


class TagPushTests(PrePushBench):
    """Tags on published commits pass the guard and the hook."""

    def setUp(self):
        """Publish a squash commit on the remote's main, as a merge on GitHub would, and fetch it."""
        super().setUp()
        self.squash = self.git('commit-tree', 'HEAD^{tree}', '-p', self.base, '-m', 'feat: squash (#1)')
        self.remote_git('fetch', '-q', str(self.repo), self.squash_ref())
        self.remote_git('symbolic-ref', 'HEAD', 'refs/heads/main')
        self.git('branch', '-D', 'squash-on-main')
        self.git('fetch', '-q', 'origin')
        self.git('tag', 'v1.0.0', self.squash)
        self.git('tag', '-a', 'v1.0.1', '-m', 'release', self.squash)
        self.unpushed = self.dangling('never pushed')
        self.git('tag', 'v9.9.9', self.unpushed)

    def squash_ref(self):
        """A local branch on the squash commit, as the refspec the bare remote fetches it by."""
        self.git('branch', 'squash-on-main', self.squash)
        return 'refs/heads/squash-on-main:refs/heads/main'

    def remote_git(self, *args):
        """Run git inside the bare remote, as the hosting side would."""
        return subprocess.check_output(['git', '--git-dir', str(self.remote), *args], env=self.env,
                                       text=True).strip()

    def remote_tag(self, name):
        """The object the remote's tag points at, or '' when it has none."""
        listing = self.remote_git('for-each-ref', '--format=%(objectname)', 'refs/tags/' + name)
        return listing

    def guard(self, command):
        """The Bash guard's verdict on a command, as Claude Code runs it before the shell does."""
        payload = dict(cwd=str(self.repo), tool_input=dict(command=command))
        return subprocess.run([sys.executable, str(PUSH)], input=json.dumps(payload), text=True,
                              capture_output=True, env=self.env, timeout=60)

    def test_a_tag_on_the_squash_commit_passes_the_guard_and_the_hook(self):
        """The reported refusal: a lightweight and an annotated tag on the commit GitHub made."""
        for tag in ('v1.0.0', 'v1.0.1'):
            with self.subTest(tag=tag):
                command = 'git push origin refs/tags/' + tag
                verdict = self.guard(command)
                self.assertEqual(verdict.returncode, 0, verdict.stderr)
                landed = self.attempt(command)
                self.assertEqual(landed.returncode, 0, landed.stderr)
                self.assertEqual(self.remote_tag(tag), self.git('rev-parse', 'refs/tags/' + tag))

    def test_a_tag_on_a_commit_the_remote_does_not_hold_is_refused(self):
        """A tag on an unpushed commit would publish it; it needs a receipt like any commit."""
        command = 'git push origin refs/tags/v9.9.9'
        self.assertEqual(self.guard(command).returncode, 2)
        self.assertNotEqual(self.attempt(command).returncode, 0)
        self.assertFalse(self.remote_has(self.unpushed))

    def test_a_tag_on_a_reviewed_commit_still_passes_on_its_receipt(self):
        """The exemption only adds a way through: a tag on an unpushed commit whose review cleared
        is admitted by the receipt, as before, by the guard and by the hook."""
        self.receipt(self.unpushed)
        command = 'git push origin refs/tags/v9.9.9'
        verdict = self.guard(command)
        self.assertEqual(verdict.returncode, 0, verdict.stderr)
        landed = self.attempt(command)
        self.assertEqual(landed.returncode, 0, landed.stderr)
        self.assertTrue(self.remote_has(self.unpushed))

    def test_a_tag_beside_a_branch_is_judged_as_the_branch_is(self):
        """Mixed refspecs earn no exemption: every ref needs a receipt, the tag included."""
        self.commit('unreviewed')
        command = 'git push origin refs/tags/v1.0.0 HEAD:feature'
        self.assertEqual(self.guard(command).returncode, 2)
        self.assertNotEqual(self.attempt(command).returncode, 0)
        self.assertFalse(self.remote_has(self.git('rev-parse', 'HEAD')))
        self.assertEqual(self.remote_tag('v1.0.0'), '')

    def test_a_tag_pushed_to_a_branch_is_a_branch_push(self):
        """A tag source written to refs/heads/ creates a branch, so it is no tag push."""
        command = 'git push origin refs/tags/v9.9.9:refs/heads/evil'
        self.assertEqual(self.guard(command).returncode, 2)
        self.assertNotEqual(self.attempt(command).returncode, 0)
        self.assertFalse(self.remote_has(self.unpushed))
        published = 'git push origin refs/tags/v1.0.0:refs/heads/copy'
        self.assertEqual(self.guard(published).returncode, 2)

    def test_a_stale_or_forged_tracking_ref_is_not_evidence(self):
        """The remote is asked, not the local ref: a tracking ref moved to an unpushed commit, or
        one behind what the remote now holds, earns nothing until it is fetched."""
        self.git('update-ref', 'refs/remotes/origin/main', self.unpushed)
        command = 'git push origin refs/tags/v9.9.9'
        refused = self.guard(command)
        self.assertEqual(refused.returncode, 2)
        self.assertIn('fetch', refused.stderr)
        self.assertNotEqual(self.attempt(command).returncode, 0)
        self.assertFalse(self.remote_has(self.unpushed))
        self.git('update-ref', 'refs/remotes/origin/main', self.base)
        self.assertEqual(self.guard('git push origin refs/tags/v1.0.0').returncode, 2)

    def test_options_that_add_refs_and_deletions_are_still_refused(self):
        """--tags, --all, --mirror and --follow-tags push refs nobody named; a deletion is a
        separate operation. The guard refuses each; the hook judges what --tags sends."""
        for command in ('git push --tags origin', 'git push --all origin', 'git push --mirror origin',
                        'git push --follow-tags origin refs/tags/v1.0.0',
                        'git push origin :refs/tags/v1.0.0', 'git push --delete origin refs/tags/v1.0.0'):
            with self.subTest(command=command):
                self.assertEqual(self.guard(command).returncode, 2)
        self.assertNotEqual(self.attempt('git push --tags origin').returncode, 0)
        self.assertFalse(self.remote_has(self.unpushed))

    def test_a_url_or_another_push_destination_is_refused(self):
        """The default branch is read where the push goes. A bare URL has no tracking ref, and a
        push URL pointing elsewhere is asked about that destination, which lacks the commit."""
        url_command = 'git push ' + str(self.remote) + ' refs/tags/v1.0.0'
        self.assertEqual(self.guard(url_command).returncode, 2)
        self.assertNotEqual(self.attempt(url_command).returncode, 0)
        elsewhere = self.root / 'elsewhere.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(elsewhere)], env=self.env, check=True)
        self.git('config', 'remote.origin.pushurl', str(elsewhere))
        command = 'git push origin refs/tags/v1.0.0'
        self.assertEqual(self.guard(command).returncode, 2)
        self.assertNotEqual(self.attempt(command).returncode, 0)
        listing = subprocess.run(['git', '--git-dir', str(elsewhere), 'for-each-ref'],
                                 capture_output=True, text=True, env=self.env).stdout
        self.assertEqual(listing, '')

    def test_a_tag_on_a_tree_is_refused(self):
        """Only a tag that peels to a commit on the default branch qualifies."""
        self.git('tag', 'tree-tag', self.squash + '^{tree}')
        command = 'git push origin refs/tags/tree-tag'
        self.assertEqual(self.guard(command).returncode, 2)
        self.assertNotEqual(self.attempt(command).returncode, 0)

    def test_the_hook_alone_admits_a_published_tag_whatever_the_guard_saw(self):
        """The hook is the boundary: a spelling the guard never parses still reaches it, and it
        admits the published tag on its own reading of the remote."""
        landed = self.attempt('env git push origin v1.0.0')
        self.assertEqual(landed.returncode, 0, landed.stderr)
        self.assertEqual(self.remote_tag('v1.0.0'), self.squash)


if __name__ == '__main__':
    unittest.main()
