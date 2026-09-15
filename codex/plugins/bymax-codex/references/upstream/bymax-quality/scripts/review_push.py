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
from review_prepush import orphaned

# Anything that would skip the pre-push hook or point git at another repository. These
# are matched as substrings of the raw command, wherever they appear: position does not
# matter, so no shell parsing is involved and none can be defeated by rearrangement.
DISARMS = ('no-verify', 'hooksPath', 'hooks-path', 'GIT_DIR', '--git-dir',
           'GIT_WORK_TREE', '--work-tree', 'GIT_COMMON_DIR', '.git/hooks', 'hooks/pre-push')
# Expansions that turn one written refspec into several, and revision operators that
# would let a refspec name a commit other than the literal one.
EXPANSIONS = '*?[]{}~^+,!'
ASSIGNMENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*=')


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
    require(not any(token.lower() in lowered for token in DISARMS),
            'That would disable or redirect the pre-push receipt check; run a plain git push.')
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
        if orphaned(state):
            continue
        require(set(state.get('reviews', {})) == {'claude', 'codex'}, 'Receipt lacks both reviews.')
        return
    raise ValueError('No completed Claude + Codex review for pushed commit ' + sha[:12])


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


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('BLOCKED: ' + str(error) + '\nRun /bymax-quality:code-review with the bounded review protocol. '
              'Reuse completed evidence; never restart a full review merely to push.', file=sys.stderr)
        sys.exit(2)
