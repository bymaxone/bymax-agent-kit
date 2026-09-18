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


# Shapes that only read. The disarming scan below is a substring match over the raw command,
# which is right where a push is at stake and wrong everywhere else: it refused `git rev-parse
# --git-dir`, which /bymax-pr:push Step 0 prescribes, a `shasum` of a hook path, a `grep` whose
# PATTERN held one of the tokens, and an `echo` of the same text. A guard that blocks reading
# protects nothing — no `rev-parse` reaches a remote — and it teaches whoever meets it to phrase
# commands to slip past a matcher, which is the habit the guard exists to prevent.
#
# An allowlist, so the default stays refusal: anything not recognised as read-only is scanned
# exactly as before. `rm` and `chmod -x` on the hook file are not on this list and are still
# refused, which is why the question asked here is "does this only read" and not "is this a
# push" — a command that deletes the hook never mentions pushing.
# Every program here must be one that cannot write a file the caller names and cannot run
# another program. Both reviewers found the first version admitting writers: `sort -o FILE`,
# `uniq INPUT OUTPUT` (POSIX makes the second operand the output), and `awk 'BEGIN{system(...)}'`,
# none of which needs a shell metacharacter. `sort -o .git/hooks/pre-push /dev/null` truncates
# the installed hook, and this predicate short-circuits the only scan that would have refused
# it. awk decides the shape of the rule: a program whose language can execute commands is not a
# read-only shape however it is invoked, so the test is the program and never its arguments.
READS = frozenset({'grep', 'rg', 'ack', 'cat', 'head', 'tail', 'wc', 'ls', 'stat', 'shasum',
                   'sha256sum', 'md5sum', 'file', 'echo', 'printf', 'basename',
                   'dirname', 'realpath', 'readlink', 'true', 'test', 'cut', 'column'})
GIT_READS = frozenset({'rev-parse', 'status', 'log', 'show', 'diff', 'ls-files', 'describe',
                       'merge-base', 'symbolic-ref', 'for-each-ref', 'rev-list', 'cat-file',
                       'check-ignore', 'blame', 'shortlog', 'ls-remote', 'ls-tree'})
CONFIG_READS = ('--get', '--get-all', '--get-regexp', '--list', '-l')


def reads_only(command):
    """Whether this command is a recognised read-only shape, so a token in it disarms nothing.

    Unrecognised means refused: a shell metacharacter, an environment assignment (which is how
    the directory variable is redirected), a `git -c` (which is how the hook path is injected),
    an unparseable line, or a program not on the lists all answer no and are scanned exactly as
    before. The lists are the whole of the claim, and they are deliberately small — the first
    version of this said "fail-closed in every direction" while admitting four writers, which
    is the sentence being a defect rather than describing one.
    """
    if any(c in command for c in '$`;|&<>\n'):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    if not words or ASSIGNMENT.match(words[0]):
        return False
    if Path(words[0]).name != 'git':
        return Path(words[0]).name in READS
    # --output=FILE is a diff option, so `git diff`, `git show` and `git log` all accept it and
    # all write wherever it points. It is refused wherever it appears rather than only in the
    # leading options, because a diff option is accepted after the subcommand too.
    if any(word.startswith('--output') for word in words):
        return False
    rest = words[1:]
    while rest and rest[0].startswith('-'):
        if rest[0].startswith(('-c', '--git-dir', '--work-tree')):
            return False
        rest = rest[2:] if rest[0] == '-C' and len(rest) > 1 else rest[1:]
    if rest[:1] == ['config']:
        # Only the reading forms: writing the hook-path key is the redirection this guard
        # exists to catch, and it differs from a read by one argument.
        return any(flag in rest for flag in CONFIG_READS)
    return bool(rest) and rest[0] in GIT_READS


def git(cwd, *args):
    """Read repository state for the command's explicit working directory."""
    return subprocess.check_output(['git', '-C', str(cwd), *args], text=True, stderr=subprocess.DEVNULL).strip()


def parse(command, cwd):
    """Return (directory, push arguments) for the literal shape; None for anything else.

    None means this adapter has no opinion: the command is run and the pre-push hook
    decides. Only the literal shape earns a receipt lookup here.
    """
    # Case-insensitive: git reads config keys and most of these options that way too.
    lowered = command.lower()
    require(reads_only(command) or not any(token.lower() in lowered for token in DISARMS),
            'That would disable or redirect the pre-push receipt check; run a plain git push. '
            'Reading one of these names is fine; this refusal is for a command that could act on '
            'them, and yours was not recognised as one that only reads.')
    try:
        words = shlex.split(command)
    except ValueError:
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
