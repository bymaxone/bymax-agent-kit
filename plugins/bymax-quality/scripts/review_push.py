#!/usr/bin/env python3
"""Claude hook adapter: an early receipt check for the one literal push shape.

The enforcement boundary is the git pre-push hook that review_flow.py installs, which
receives the pushed SHAs from git itself and therefore holds however the push command
was spelled. This adapter does two smaller jobs before git runs: it recognises the exact
`[cd <path> &&] [VAR=value ...] git [-C <dir>] push <remote> <refspec>...` form so a
missing receipt is reported with a useful message, and it refuses the few options that
would disable or redirect that hook. Every other command passes through untouched.
A push deliberately spelled so that neither check sees it is outside what a local guard
can prevent; review-protocol.md names CI as the boundary for that.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from review_flow import POLICY, require
from review_prepush import explain, orphaned, satisfied

# Anything that would skip the pre-push hook or point git at another repository, plus
# husky's own skip switch (its dispatcher exits before the tracked hook when HUSKY=0).
# These are matched as substrings of the raw command, wherever they appear: position does
# not matter, so no shell parsing is involved and none can be defeated by rearrangement.
DISARMS = ('no-verify', 'hooksPath', 'hooks-path', 'GIT_DIR', '--git-dir',
           'GIT_WORK_TREE', '--work-tree', 'GIT_COMMON_DIR', '.git/hooks', 'hooks/pre-push', 'HUSKY=')
# Expansions that turn one written refspec into several, and revision operators that
# would let a refspec name a commit other than the literal one.
EXPANSIONS = '*?[]{}~^+,!'
ASSIGNMENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*=')


# Programs that could start another program, so a command carrying one could reach a remote
# however the rest of it is spelled. Nothing here is an allowlist: this widens what the
# disarming scan below applies to, it never exempts anything from it.
RUNNERS = frozenset({'git', 'sh', 'bash', 'zsh', 'dash', 'ksh', 'fish', 'eval', 'exec', 'env',
                     'xargs', 'nohup', 'timeout', 'time', 'nice', 'sudo', 'doas', 'ssh'})


def could_push(command):
    """Whether this command could reach a remote, however it is spelled.

    The disarming scan matters where a push is at stake, and nowhere else: a hook that is not
    about to run cannot be redirected. Scanning every command instead refused reading — `git
    rev-parse --git-dir`, which /bymax-pr:push Step 0 prescribes, a `shasum` of a hook path, a
    `grep` whose PATTERN held a token, and the two piped greps this repository's own command
    files tell a model to run.

    The first attempt at that exemption listed programs that only read, and both reviewers
    broke it in one round: `rg --pre CMD`, `ack --pager=CMD` and `git ls-remote
    --upload-pack=CMD` each run a program the caller names while reading, and one of them
    deleted an installed hook end to end. The list of such flags across the list of such
    programs has no closed form, so the question is not asked. This one is: a command with no
    `push` in it cannot push, and a command that names no program able to start another cannot
    be hiding one. Both halves are conservative — unparseable answers yes.
    """
    words = words_of(command)
    if words is None:
        return True
    # The parsed words, never the raw text. The shell and git act on these, so a push verb
    # spelled pu""sh or pu\sh is invisible in the raw command and fully present here — measured:
    # a hooksPath redirection written that way was returned as no-opinion while the commit
    # reached the remote with the hook in place and never invoked.
    if not any('push' in word.lower() for word in words):
        return False
    return any(Path(word).name in RUNNERS for word in words)


def git(cwd, *args):
    """Read repository state for the command's explicit working directory."""
    return subprocess.check_output(['git', '-C', str(cwd), *args], text=True, stderr=subprocess.DEVNULL).strip()


def words_of(command):
    """The command as the shell would hand it on, or None when it cannot be parsed."""
    try:
        return shlex.split(command)
    except ValueError:
        return None


def parse(command, cwd):
    """Return (directory, push arguments) for the literal shape; None for anything else.

    None means this adapter has no opinion: the command is run and the pre-push hook
    decides. Only the literal shape earns a receipt lookup here.
    """
    # Case-insensitive: git reads config keys and most of these options that way too.
    lowered = command.lower()
    words = words_of(command)
    pushes = could_push(command)
    # Both forms. A token split across quotes — core.hooks""Path — is absent from the raw text
    # and present once the shell has parsed it; a token the shell would not have produced is
    # absent from the words and present in the text. Reading one of them was the unrepaired
    # half of the previous round's fix, which moved the precondition to the words and left the
    # scan a line below it on the raw command.
    seen = lowered + '\n' + ' '.join(words).lower() if words is not None else lowered
    require(not pushes or not any(token.lower() in seen for token in DISARMS),
            'That would disable or redirect the pre-push receipt check; run a plain git push. '
            'A command that only names one of these — reading a hook, grepping for the token — '
            'is not this refusal: it applies where the command could reach a remote.')
    if words is None:
        return None
    tail = command
    if words[:1] == ['cd'] and len(words) > 3 and words[2] == '&&':
        cwd = (Path(cwd) / words[1]).resolve()
        words, tail = words[3:], command.split('&&', 1)[1]
    while words and ASSIGNMENT.match(words[0]):
        words = words[1:]
    if not words or Path(words[0]).name != 'git':
        return None
    words = words[1:]
    if words[:1] == ['-C'] and len(words) > 1:
        cwd, words = (Path(cwd) / words[1]).resolve(), words[2:]
    if words[:1] != ['push']:
        return None
    # The shape matched, so from here the command is a push and must be exactly one.
    require(not any(c in tail for c in '$`;|&<>\n'), 'Use a literal git push in its own command.')
    return cwd, words[1:]


def sources(words):
    """Require explicit remote/refspecs and reject implicit or wildcard pushes."""
    allowed = {'-u', '--set-upstream', '--force-with-lease', '--atomic', '--porcelain', '--verbose', '-v'}
    require(not any(c in word for word in words for c in EXPANSIONS),
            'Use literal remote and refspec arguments without shell expansion.')
    positional = []
    for word in words:
        if word.startswith('-'):
            require(word in allowed or word.startswith('--force-with-lease='), 'Unsupported push option: ' + word)
        else:
            positional.append(word)
    require(len(positional) >= 2, 'Name remote and source explicitly: git push -u origin HEAD:<branch>.')
    specs = positional[1:]
    require(all(s and s.count(':') <= 1 for s in specs), 'Use literal branch refspecs.')
    require(all(s.split(':')[0] for s in specs), 'Deletion pushes require a separate user-controlled operation.')
    return positional[0], [s.split(':')[0] for s in specs]


def approved(cwd, source):
    """Look up only the exact pushed commit, never another linked worktree tip."""
    sha = git(cwd, 'rev-parse', '--verify', source + '^{commit}')
    common = Path(git(cwd, 'rev-parse', '--git-common-dir'))
    common = (Path(cwd) / common).resolve()
    paths = list((common / 'bymax-review').glob('*/state.json'))
    paths += list((common / 'bymax-review').glob('*/completed-*.json'))
    for path in paths:
        state = json.loads(path.read_text())
        if state.get('head') != sha or not state.get('cleared') or state.get('policy') != POLICY:
            continue
        if orphaned(path, state):
            continue
        # Same predicate the hook applies, including the fresh probe behind a Codex waiver:
        # this adapter exists to report the refusal usefully, never to reach a softer verdict.
        require(satisfied(state), 'The receipt for ' + sha[:12] + ' cannot clear this push: ' + explain(state))
        return
    raise ValueError('No completed review for pushed commit ' + sha[:12])


def main():
    """Read Claude's Bash payload and block without starting any review."""
    payload = json.load(sys.stdin)
    parsed = parse(payload.get('tool_input', {}).get('command', ''), payload.get('cwd') or os.getcwd())
    if parsed:
        cwd, words = parsed
        remote, refs = sources(words)
        for key in ('push.followTags', 'remote.' + remote + '.mirror'):
            result = subprocess.run(['git', '-C', str(cwd), 'config', '--bool', '--get', key],
                                    capture_output=True, text=True)
            require(result.returncode in (0, 1) and result.stdout.strip() != 'true',
                    'Implicit additional refs enabled by ' + key + '; use an explicit non-mirror remote without followTags.')
        for source in refs:
            approved(cwd, source)


def cli():
    """The process entry point, separate from main() so a test can drive it in a process
    whose Codex resolution table it controls; the command line never controls it."""
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('BLOCKED: ' + str(error) + '\nAUTOMATIC CONTINUATION: the authorized push is pending. '
              'Run /bymax-quality:code-review using start --autonomous, reuse evidence, complete both '
              'reviewers, triage proven blockers, run gates and finish. Retry the original push destination/refspec. '
              'Do not ask whether to review or continue ordinary verified corrections. Keep the original scope '
              'and six-candidate delivery budget; never bypass a real blocker or disable this hook.', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    cli()
