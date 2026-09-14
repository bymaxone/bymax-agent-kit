#!/usr/bin/env python3
"""Claude hook adapter: validate explicit push sources against review receipts."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from review_flow import POLICY, require


def git(cwd, *args):
    """Read repository state for the command's explicit working directory."""
    return subprocess.check_output(['git', '-C', str(cwd), *args], text=True, stderr=subprocess.DEVNULL).strip()


PUNCTUATION = '();<>|&\n'
# Interpreters take the command as a STRING argument, so both words land in one token.
INTERPRETERS = {'sh', 'bash', 'zsh', 'dash', 'ksh', 'eval', 'ssh', 'script'}
# Exec prefixes take the command as the REST of argv, so `command git push` reaches git
# with argv[0] no longer git. Their own options cannot be modelled here, so a prefixed
# push is refused outright rather than parsed.
PREFIXES = {'command', 'env', 'exec', 'nohup', 'time', 'timeout', 'sudo', 'doas',
            'setsid', 'nice', 'ionice', 'stdbuf', 'xargs', 'watch'}
ASSIGNMENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*=')
# Shell expansions that turn one written argument into several actual refs, plus the
# revision operators that would let a refspec name a commit other than the literal one.
EXPANSIONS = '*?[]{}~^+,!'


def operator(token):
    """Recognize a shell control token, which shlex emits separately from arguments."""
    return bool(token) and all(character in PUNCTUATION for character in token)


def literal_heredoc(command):
    """Allow a standalone literal cat document; reject other heredocs explicitly."""
    header, separator, body = command.partition('\n')
    match = re.fullmatch(r"cat\s+(?:(?:>|>>)\s*[\w./-]+\s+)?<<\s*(['\"])([\w-]+)\1(?:\s+(?:>|>>)\s*[\w./-]+)?\s*", header)
    require(match is not None and separator,
            'Issue heredocs separately: use a standalone cat with a quoted delimiter and literal output path.')
    lines = body.splitlines()
    delimiter = match.group(2)
    require(delimiter in lines, 'Unterminated heredoc.')
    end = lines.index(delimiter)
    require(not any(line.strip() for line in lines[end + 1:]),
            'Issue commands after a heredoc separately so each push can be checked.')
    return True


def segments(command):
    """Split into (preceding-operator, argv) pairs; newlines are command boundaries."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace_split = True
    lexer.whitespace = ' \t\r'
    parts, preceding, words = [], None, []
    for token in lexer:
        if operator(token):
            if words:
                parts.append((preceding, words))
            preceding, words = token, []
        else:
            words.append(token)
    if words:
        parts.append((preceding, words))
    return parts


def command_words(words):
    """Drop leading VAR=value assignments so the real command word is argv[0]."""
    index = 0
    while index < len(words) and ASSIGNMENT.match(words[index]):
        index += 1
    return words[index:]


def git_push(words):
    """Return (-C directory, push arguments) for a literal git push, else None."""
    if not words or Path(words[0]).name != 'git':
        return None
    directory, rest = None, words[1:]
    if rest[:1] == ['-C']:
        require(len(rest) > 1, 'Missing -C directory.')
        directory, rest = rest[1], rest[2:]
    if rest[:1] == ['push']:
        return directory, rest[1:]
    # Another subcommand (git log, git stash push) publishes nothing and is left alone,
    # but a global option before push hides the real argv from this parser.
    require(not (rest and rest[0].startswith('-') and 'push' in rest),
            'Push with global git options is unsupported; use git -C <path> push.')
    return None


def parse(command, cwd):
    """Accept one literal push, optionally preceded by cd; reject ambiguous pushes.

    Decisions come from the shell-tokenized argv rather than the raw text, so quoted
    spellings such as `pu""sh` normalize to `push` and are still checked, while a
    command that merely mentions a push in an argument is not treated as one.
    """
    try:
        parts = segments(command)
    except ValueError:
        # An apostrophe inside a heredoc body is unbalanced to shlex but is still data.
        if '<<' in command:
            literal_heredoc(command)
            return None
        require(not re.search(r'\bgit\b.*\bpush\b', command),
                'Unparsable command naming a git push; issue an explicit git push.')
        return None
    # A heredoc is the '<<' OPERATOR token, never the characters inside a quoted argument.
    if any(o is not None and o.startswith('<<') for o, _ in parts):
        literal_heredoc(command)
        return None
    found = None
    for _, raw in parts:
        words = command_words(raw)
        require(bool(words), 'Name a command, not only environment assignments.')
        name = Path(words[0]).name
        if name in INTERPRETERS:
            require(not any(re.search(r'\bgit\b.*\bpush\b', word) for word in words[1:]),
                    'Do not wrap git push in another shell.')
        if name in PREFIXES:
            require(not ('push' in words[1:] and any(Path(w).name == 'git' for w in words[1:])),
                    'Run git push directly, without an exec prefix such as ' + name + '.')
        result = git_push(words)
        if result is None:
            continue
        require(found is None, 'Issue one explicit git push per command.')
        found = (raw, result)
    if found is None:
        return None
    raw, (directory, arguments) = found
    require(parts[-1][1] is raw and all(w is raw or command_words(w)[:1] == ['cd'] for _, w in parts),
            'Issue git push as its own command, optionally preceded by cd <path> &&.')
    require(all(o in (None, '&&') for o, _ in parts),
            'Chain a push only with && so it cannot follow an unchecked command.')
    require(not any(x in command for x in ('$', '`')), 'Use a literal git push without shell substitution.')
    for _, other in parts:
        if other is not raw:
            change = command_words(other)
            require(len(change) == 2 and not change[1].startswith('-')
                    and not any(c in change[1] for c in EXPANSIONS), 'Name the directory explicitly: cd <path> && git push ...')
            cwd = (Path(cwd) / change[1]).resolve()
    return ((Path(cwd) / directory).resolve() if directory else cwd), arguments


def sources(words):
    """Require explicit remote/refspecs and reject implicit or wildcard pushes."""
    allowed = {'-u', '--set-upstream', '--force-with-lease', '--atomic', '--porcelain', '--verbose', '-v'}
    # Checked across every argument, not only refspecs: an expansion in the remote slot
    # (`origin{,evil}`) becomes an extra unreviewed refspec that this parser never sees.
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
