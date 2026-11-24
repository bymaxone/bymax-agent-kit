"""Claude adapter gaps measured on a real repository: a push the adapter never looked at, and a hook
that no longer checks receipts.

Both reached GitHub with no receipt. The adapter read a receipt only for a command that STARTS with
`git push`, so `git commit ...; git push ...` and `x && git push ...` were passed on to a hook; and a
`pnpm install` in a fresh worktree let husky regenerate `.husky/_/pre-push` without the check, so that
hook decided nothing. The first class is held here at the adapter, the second at the adapter's reading
of the hook git will run.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from test_review_prepush import FLOW, PrePushBench

ADAPTER = FLOW.with_name('review_push.py')
LITERAL = 'Use a literal git push in its own command.'
STUB = '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n'


class AdapterBench(PrePushBench):
    """PrePushBench plus the adapter run as Claude Code's hook would run it."""

    def guard(self, command):
        """The adapter's exit status and stderr for one Bash command, run in the fixture repository."""
        run = subprocess.run([sys.executable, str(ADAPTER)], cwd=self.repo, env=self.env, capture_output=True,
                             text=True, timeout=60,
                             input=json.dumps(dict(tool_input=dict(command=command), cwd=str(self.repo))))
        return run.returncode, run.stderr

    def husky(self, hook=STUB, tracked=None):
        """Point core.hooksPath at a husky 9 generated directory whose pre-push is `hook`."""
        generated = self.repo / '.husky/_'
        generated.mkdir(parents=True)
        # husky's dispatcher runs the tracked hook of the same name, which is what a stub delegates to.
        (generated / 'h').write_text('#!/usr/bin/env sh\nn=$(basename "$0")\n'
                                     '[ -f "$(dirname "$0")/../$n" ] && exec sh "$(dirname "$0")/../$n" "$@"\n'
                                     'exit 0\n')
        (generated / '.gitignore').write_text('*\n')
        (generated / 'pre-push').write_text(hook)
        (generated / 'pre-push').chmod(0o755)
        if tracked is not None:
            (self.repo / '.husky/pre-push').write_text(tracked)
        self.git('config', 'core.hooksPath', '.husky/_')


class CompoundPushTests(AdapterBench):
    """A push written inside a longer command is refused, not passed on."""

    def test_a_push_that_is_not_the_whole_command_is_refused_by_the_adapter(self):
        """`git commit; git push` and `x && git push` returned no opinion and ran unchecked."""
        for command in ('git commit -qm x; git push origin HEAD:f',
                        'true && git push origin HEAD:f',
                        'git status\ngit push origin HEAD:f',
                        'echo hi | git push origin HEAD:f',
                        '(git push origin HEAD:f)',
                        'sh -c "git push origin HEAD:f"',
                        "echo it's; git push origin HEAD:f",
                        # `#` after a space inside ${...} is literal to the shell, so this push runs.
                        'echo ${x:-a #b}; git push origin HEAD:f',
                        # `#` inside a word is literal to the shell; only a word that starts with it is a comment.
                        'echo a#b; git push origin HEAD:f'):
            with self.subTest(command=command):
                status, error = self.guard(command)
                self.assertEqual(status, 2, error)
                self.assertIn(LITERAL, error)

    def test_a_command_that_only_mentions_push_still_passes(self):
        """The refusal is for the verb written as a command, not for a message or a comment."""
        for command in ('git commit -qm "fix the push guard"',
                        'git remote -v   # is there a remote to push to?',
                        'git log --oneline -3',
                        'git stash push -m wip',
                        'echo git push > notes.txt',
                        'grep -rn "git push" docs/',
                        "# the PR's branch\ngit status"):
            with self.subTest(command=command):
                self.assertEqual(self.guard(command)[0], 0)


class HookGapTests(AdapterBench):
    """A literal push is allowed only while the hook git will run calls the receipt check."""

    def pushable(self):
        """A commit that has a receipt, so the only thing that can stop its push is the hook."""
        sha = self.dangling('receipted')
        self.receipt(sha)
        return f'git push origin {sha}:refs/heads/receipted'

    def test_a_husky_stub_that_dropped_the_check_refuses_the_push_with_the_reinstall_command(self):
        """husky regenerated `_/pre-push` on install and the adapter let the push through on the receipt."""
        command = self.pushable()
        self.assertEqual(self.guard(command)[0], 0, 'the default hook carries the check')
        self.husky()
        status, error = self.guard(command)
        self.assertEqual(status, 2, error)
        self.assertIn('does not call the receipt check', error)
        self.assertIn(str(FLOW) + ' status', error)

    def test_the_reinstall_command_restores_the_push(self):
        """The remedy the refusal names puts the check back, and the same push then passes."""
        command = self.pushable()
        self.husky()
        self.assertEqual(self.guard(command)[0], 2)
        run = subprocess.run([sys.executable, str(FLOW), 'status'], cwd=self.repo, env=self.env,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.guard(command), (0, ''))

    def test_a_tracked_husky_hook_that_carries_the_check_counts(self):
        """The stub delegates to `.husky/pre-push`; a check there is the check git runs."""
        self.husky(tracked='#!/bin/sh\npython3 "' + str(FLOW.with_name('review_prepush.py')) + '" "$@"\n')
        self.assertEqual(self.guard(self.pushable())[0], 0)

    def test_a_hook_that_only_carries_the_marker_and_accepts_everything_refuses_the_push(self):
        """The marker and the checker's name are text; the hook is judged by what it does with a push."""
        command = self.pushable()
        modules = self.modules()
        marker = modules['review_hook'].HOOK_MARKER
        hook = self.repo / '.git/hooks/pre-push'
        for body in (f'#!/bin/sh\n# {marker}\nexit 0\n', '#!/bin/sh\n# review_prepush\nexit 0\n'):
            with self.subTest(body=body):
                hook.write_text(body)
                hook.chmod(0o755)
                status, error = self.guard(command)
                self.assertEqual(status, 2, error)
                self.assertIn('accepted a push of a commit with no receipt', error)

    def test_a_missing_or_unexecutable_hook_refuses_the_push(self):
        """git skips a hook that is not executable, which is no hook at all."""
        command = self.pushable()
        hook = self.repo / '.git/hooks/pre-push'
        os.chmod(hook, 0o644)
        self.assertEqual(self.guard(command)[0], 2)
        hook.unlink()
        status, error = self.guard(command)
        self.assertEqual(status, 2, error)
        self.assertIn('missing or not executable', error)


if __name__ == '__main__':
    unittest.main()
