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
import time
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
                        'echo a#b; git push origin HEAD:f',
                        # A `#` after any other character, a closing quote or a backslash is still
                        # inside its word.
                        'echo {#x; git push origin HEAD:f',
                        'echo }#x; git push origin HEAD:f',
                        'echo a=#b; git push origin HEAD:f',
                        'echo "a"#b; git push origin HEAD:f',
                        'echo a\\#b; git push origin HEAD:f',
                        # A heredoc body is text to the shell, `#` included, and an unquoted one still runs `$( )`.
                        'cat <<EOF\n #x $(git push origin HEAD:f)\nEOF',
                        'cat <<EOF\n #x `git push origin HEAD:f`\nEOF',
                        # A program that starts git, or a shell reading a heredoc, still runs the push.
                        'env X=1 git push origin HEAD:f',
                        'timeout 5 git push origin HEAD:f',
                        'bash <<EOF\ngit push origin HEAD:f\nEOF',
                        '{ git push origin HEAD:f; }',
                        'git -c alias.p=push p origin',
                        'if true; then git push origin HEAD:f; fi',
                        '! git push origin HEAD:f',
                        # Any program not known to only print its words, a here-string into a shell, and a heredoc piped into a shell.
                        'git commit -m x; command git push origin HEAD:f',
                        'builtin git push origin HEAD:f',
                        'stdbuf -oL git push origin HEAD:f',
                        'setsid git push origin HEAD:f',
                        'my-wrapper --flag git push origin HEAD:f',
                        'sh <<< "git push origin HEAD:f"',
                        'cat <<EOF | sh\ngit push origin HEAD:f\nEOF',
                        "cat <<'EOF' | bash\ngit push origin HEAD:f\nEOF",
                        'cat <<EOF | command sh\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF | env bash\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF | nice sh\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF | xargs sh -c\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF | tee >(sh)\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF | eval\ngit push origin HEAD:f\nEOF',
                        'sh <(echo git push origin HEAD:f)',
                        'cat <<EOF | (sh)\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF |& sh\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF | { sh; }\ngit push origin HEAD:f\nEOF',
                        'cat <(echo git push origin HEAD:f) | sh',
                        'echo git push origin HEAD:f | sh',
                        "printf 'git push origin HEAD:f' |& bash",
                        # Command positions the first word of a pipe segment does not show.
                        'FOO=x echo git push origin HEAD:f | sh',
                        'A=1 B=2 printf "git push origin HEAD:f" | env -i sh',
                        'echo git push origin HEAD:x | (read l; eval $l)',
                        'echo git push origin HEAD:x | { read l; eval $l; }',
                        'cat <<EOF |\ngit push origin HEAD:f\nEOF\nsh',
                        'cat <<< "git push origin HEAD:f" | sh',
                        # Input that is not known before it runs, handed to anything that runs it, may be a push.
                        # grep keeps the lines that name a push and sh runs them, so `git log | grep push | sh`
                        # cannot be shown not to push.
                        'git log | grep push | sh',
                        "git config alias.s 'git push origin HEAD:f'; git config --get alias.s | sh",
                        "git config alias.s 'git push origin HEAD:f'; git config --get alias.s | xargs sh -c",
                        "git config alias.s 'git push origin HEAD:f'; git config --get alias.s | { read l; eval $l; }",
                        "git config alias.s 'git push origin HEAD:f'; git config --get alias.s | (read l; eval $l)",
                        'echo git push origin HEAD:x | while read l; do eval "$l"; done',
                        'echo git push origin HEAD:x | if true; then sh; fi',
                        'echo git push origin HEAD:x | until false; do sh; done',
                        "git config alias.s 'git push origin HEAD:f'; git config --get alias.s | while read l; do sh; done",
                        "git config alias.s 'git push origin HEAD:f'; git config --get alias.s | if true; then bash; fi",
                        'echo git push origin HEAD:x | for x in 1; do sh; done',
                        'echo git push origin HEAD:x | case x in x) sh;; esac',
                        'git log --format=%s | while read l; do case $l in *push*) eval "$l";; esac; done',
                        'git config alias.s "git push origin HEAD:f"; eval "$(git config --get alias.s)"',
                        'git config alias.s "git push origin HEAD:f"; sh -c "$(git config --get alias.s)"',
                        'git config alias.s "git push origin HEAD:f"; bash <(git config --get alias.s)',
                        'git config alias.s "git push origin HEAD:f"; source <(git config --get alias.s)',
                        'git config alias.s "git push origin HEAD:f"; sh <<< "$(git config --get alias.s)"',
                        'git config alias.s "git push origin HEAD:f"; eval `git config --get alias.s`',
                        'git config alias.s "git push origin HEAD:f"; eval $(git config --get alias.s)',
                        'git config alias.s "git push origin HEAD:f"; sh -c $(git config --get alias.s)',
                        "git config alias.s 'git push origin HEAD:f'; git config --get alias.s | . /dev/stdin",
                        'git log --grep push | env sh',
                        'git log --grep push | sudo bash',
                        'git log --grep push | command . /dev/stdin',
                        'git log --grep push | timeout 5 sh',
                        'git log --grep push | nice -n 5 bash',
                        "git config alias.s 'git push origin HEAD:f'; . <(git config --get alias.s)",
                        "git config alias.s 'git push origin HEAD:f'; git config --get alias.s | while read l; do $l; done",
                        "git config alias.s 'git push origin HEAD:f'; git config --get alias.s | $SHELL",
                        "git config alias.s 'git push origin HEAD:f'; $(git config --get alias.s)",
                        "git config alias.s 'git push origin HEAD:f'; X=$(git config --get alias.s); $X",
                        'sh <<EOF\n$(echo git push origin HEAD:f)\nEOF',
                        'sh <<EOF\n`echo git push origin HEAD:f`\nEOF',
                        "git config alias.s 'git push origin HEAD:f'; sh <<EOF\n$CMD\nEOF",
                        'A="git push origin HEAD:f"; sh -c "$A"',
                        'A="git push origin HEAD:f"; eval "$A"',
                        "printf 'git push\\n' | sh",
                        'printf "git push\\n" | bash',
                        # `subtree push` pushes, and a subcommand the shell has not expanded yet may be `push`.
                        'git subtree push --prefix=x origin main',
                        'git -C d subtree push --prefix=x origin main',
                        'git subtree split --prefix=x -b y; git subtree push --prefix=x origin y',
                        'git subtree $(echo push) --prefix=x origin main',
                        'git subtree -P x push origin main',
                        'git subtree -P -b push origin x',
                        'git subtree -P x push origin split',
                        'git subtree --no-prefix push',
                        'git subtree -- push',
                        'git log --grep push; git subtree $x',
                        'git subtree split --prefix x $(git push)',
                        'git subtree split --prefix x && git push origin HEAD:f',
                        'git $(echo push) origin HEAD:f',
                        'git `echo push` origin HEAD:f',
                        'git $x origin HEAD:f; git log --grep push',
                        'git ${x:-push} origin HEAD:f',
                        'git log --grep push; git "$x" origin HEAD:f',
                        'git -C d $(echo push) origin HEAD:f',
                        '$(echo git) push origin HEAD:f',
                        'sh -c "$(echo git push)"',
                        'eval "git $(echo push)"',
                        's=push; eval "git $s"',
                        # Text the shell could not read is refused rather than guessed at.
                        "echo 'git push origin HEAD:f | sh"):
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
                        'git status # git push origin HEAD:f',
                        'git status;# git push origin HEAD:f',
                        'grep -rn "git push" docs/',
                        "# the PR's branch\ngit status",
                        # `push` is an argument here, or another program's verb: git is not pushing.
                        'git grep push',
                        "git grep -n 'push'",
                        'git log --grep push',
                        'git log -S push --oneline',
                        'git log --oneline | grep push',
                        'git branch -vv | grep push',
                        'git status && git log -1 --format=%s | grep -i push',
                        'grep -rn push src/ && git status',
                        'docker push img:tag && git status',
                        'git help push',
                        'cat <<EOF\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF > sh.txt\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF | grep x\ngit push origin HEAD:f\nEOF',
                        'cat <<EOF | tee out.txt\ngit push origin HEAD:f\nEOF',
                        'diff <(echo git push a) <(echo git push b)',
                        'echo git push origin HEAD:f | grep push',
                        'echo git push origin HEAD:f | tee log | wc -l',
                        'git log --grep push | xargs git show',
                        'git log --oneline | grep push | wc -l',
                        'git log --grep push; ls .',
                        # A subcommand that is written out, or a substitution that is only an argument, is not a push.
                        'git subtree split --prefix=x -b y; git log --grep push',
                        'git subtree add --prefix=x origin main; git log --grep push',
                        # The verb is the first word, so a push word after it is an argument.
                        'git subtree split --prefix push',
                        'git subtree split --prefix x -b push',
                        'git subtree split --prefix x --branch push',
                        'git subtree -P x add --prefix x o r; git log --grep push',
                        'git subtree split --prefix x $(echo -b push)',
                        'git commit -m "$(cat msg)"; git log --grep push',
                        'git -C "$dir" log --oneline --grep push',
                        'git log --grep "$(echo push)"',
                        'git diff "$(git merge-base a b)" HEAD; git log --grep push',
                        # An argument that is named like a sink is text; only the program run is a sink.
                        'git log --grep push | ls .',
                        'git log --grep push | cp a .',
                        'git log --grep push | grep source x',
                        'git log --grep push | grep -r eval .',
                        'git log --grep push | echo sh',
                        'git log --grep push | cat sh',
                        'git log --grep push | ls eval',
                        'git log --format=%s | xargs git show',
                        'bash scripts/build.sh $TARGET && git log --grep push',
                        # A pipe or a `;` inside quotes or escaped is text, not an operator.
                        "echo 'git push origin HEAD:f | sh'",
                        'echo "git push origin HEAD:f; sh"',
                        'echo git push origin HEAD:f \\| sh',
                        # Real pipes, and every command in them only prints, or the producer is not text.
                        'printf "push\\n" | sort | uniq',
                        'echo git push origin HEAD:f'):
            with self.subTest(command=command):
                self.assertEqual(self.guard(command)[0], 0)


class ReaderTests(unittest.TestCase):
    """runs_push read directly: where the adapter's wide gate would not have asked."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(FLOW.parent))
        import review_push
        cls.review_push = review_push

    def test_an_operator_inside_quotes_or_escaped_is_text_and_not_a_command_boundary(self):
        """`echo 'git push x | sh'` printed a message; the pipe inside the quotes started nothing."""
        for command in ("echo 'git push origin HEAD:f | sh'", 'echo "git push origin HEAD:f; sh"',
                        'echo git push origin HEAD:f \\| sh', "printf '%s' 'git push origin HEAD:f | bash'",
                        "echo git push origin HEAD:f '|' sh"):
            with self.subTest(command=command):
                self.assertFalse(self.review_push.runs_push(command))

    def test_text_that_cannot_be_tokenised_is_reported_as_unreadable_and_a_heredoc_behind_it_runs(self):
        self.assertIsNone(self.review_push.reaches_program("echo 'git push origin HEAD:f | sh"))
        self.assertTrue(self.review_push.fed_to_program("| 'unterminated"))

    def test_text_that_cannot_be_tokenised_and_names_a_push_is_read_as_a_push(self):
        for command in ("echo 'git push origin HEAD:f | sh", 'echo git push origin HEAD:f | (sh'):
            with self.subTest(command=command):
                self.assertTrue(self.review_push.runs_push(command))


class CodexCopyTests(unittest.TestCase):
    """The Codex package ships its own copy of the guard; a stale copy lets through what the plugin refuses."""

    UPSTREAM = Path(__file__).resolve().parents[2] / 'codex' / 'plugins' / 'bymax-codex' / 'references'

    def test_the_codex_copy_of_the_guard_is_the_plugin_file_byte_for_byte(self):
        copy = self.UPSTREAM / 'upstream' / 'bymax-quality' / 'scripts' / 'review_push.py'
        self.assertEqual(copy.read_bytes(), (FLOW.parent / 'review_push.py').read_bytes(),
                         'run python3 codex/scripts/bundle.py')

    def test_the_hash_that_pins_the_codex_copy_is_the_hash_of_the_file(self):
        import hashlib
        pins = json.loads((self.UPSTREAM / 'upstream-sha256.json').read_text())
        digest = hashlib.sha256((FLOW.parent / 'review_push.py').read_bytes()).hexdigest()
        self.assertIn(digest, json.dumps(pins), 'run python3 codex/scripts/bundle.py')


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
        self.assertIn('accepted a push of a commit with no receipt', error)
        self.assertIn('chains the check back into husky', error)
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

    def test_a_hook_is_probed_even_when_the_user_cannot_make_commits(self):
        """A user with no commit identity made the probe commit fail, and a failed probe passed."""
        command = self.pushable()
        for key in [key for key in self.env if key.startswith(('GIT_AUTHOR_', 'GIT_COMMITTER_'))]:
            del self.env[key]
        self.git('config', 'user.useConfigOnly', 'true')
        for key in ('user.name', 'user.email'):
            subprocess.run(['git', 'config', '--unset', key], cwd=self.repo, env=self.env)
        hook = self.repo / '.git/hooks/pre-push'
        hook.write_text('#!/bin/sh\n# review_prepush\nexit 0\n')
        hook.chmod(0o755)
        status, error = self.guard(command)
        self.assertEqual(status, 2, error)
        self.assertIn('accepted a push of a commit with no receipt', error)

    def test_a_hook_too_slow_to_answer_the_probe_is_not_called_unchecked(self):
        """A husky hook that runs a test suite before the check is slow, not absent: no verdict, no refusal."""
        sys.path.insert(0, str(FLOW.parent))
        try:
            import review_push
        finally:
            sys.path.remove(str(FLOW.parent))
        slow = self.repo / 'slow-hook'
        slow.write_text('#!/bin/sh\nsleep 5\nexit 1\n')
        slow.chmod(0o755)
        self.assertIsNone(review_push.probe_problem(slow, self.repo, str(self.repo), seconds=1))

    def test_a_comment_before_or_after_a_literal_push_does_not_make_it_another_shape(self):
        """The receipt lookup is for the literal push; a comment around it used to hide the shape."""
        command = self.pushable()
        for text in ('# a comment\n' + command, "# the PR's branch\n" + command, command + ' # why'):
            with self.subTest(text=text):
                self.assertEqual(self.guard(text), (0, ''))
        missing = f'git push origin {self.dangling("unreceipted")}:refs/heads/x'
        self.assertIn('No completed review', self.guard('# a comment\n' + missing)[1])

    def test_an_enforcing_hook_in_a_custom_hooks_path_is_judged_by_what_it_does(self):
        """A hook that hands the push to its own checker carries no marker and still enforces."""
        command = self.pushable()
        directory = self.repo / '.githooks'
        directory.mkdir()
        (directory / 'receipt-check').write_text('#!/bin/sh\nexit 1\n')
        (directory / 'receipt-check').chmod(0o755)
        (directory / 'pre-push').write_text('#!/bin/sh\nexec "$(dirname "$0")/receipt-check" "$@"\n')
        (directory / 'pre-push').chmod(0o755)
        self.git('config', 'core.hooksPath', '.githooks')
        self.assertEqual(self.guard(command), (0, ''))

    def test_a_hook_with_no_interpreter_line_is_run_the_way_git_runs_it(self):
        """git runs a hook without a shebang through sh; the probe did not, and raised."""
        command = self.pushable()
        hook = self.repo / '.git/hooks/pre-push'
        for body, expected in (('exit 1\n', 0), ('exit 0\n', 2)):
            with self.subTest(body=body):
                hook.write_text(body)
                hook.chmod(0o755)
                self.assertEqual(self.guard(command)[0], expected)

    def test_a_hook_that_outruns_the_probe_is_stopped_with_what_it_started(self):
        """A kill of the hook alone left its children running; the probe also has to end inside the 15 s Claude Code allows."""
        sys.path.insert(0, str(FLOW.parent))
        try:
            import review_push
        finally:
            sys.path.remove(str(FLOW.parent))
        self.assertLess(review_push.PROBE_SECONDS, 15)
        marker = self.repo / 'child.pid'
        slow = self.repo / 'slow-hook'
        slow.write_text(f'#!/bin/sh\nsleep 60 &\necho $! > {marker}\nwait\n')
        slow.chmod(0o755)
        self.assertIsNone(review_push.probe_problem(slow, self.repo, str(self.repo), seconds=1))
        child = int(marker.read_text())
        for _ in range(50):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        os.kill(child, 9)
        self.fail('the hook\'s child outlived the probe')

    def test_the_remedy_is_the_one_that_is_true_for_the_hook(self):
        """`status` fixes a husky stub; for a missing hook it is the wrong command."""
        command = self.pushable()
        (self.repo / '.git/hooks/pre-push').unlink()
        error = self.guard(command)[1]
        self.assertIn('Run `start`', error)
        self.assertNotIn(str(FLOW) + ' status', error)
        (self.repo / '.githooks').mkdir()
        self.git('config', 'core.hooksPath', '.githooks')
        error = self.guard(command)[1]
        self.assertIn('which `start` never writes into', error)
        self.assertNotIn(str(FLOW) + ' status', error)

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
