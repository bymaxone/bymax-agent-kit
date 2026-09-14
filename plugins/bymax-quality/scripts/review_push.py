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
ASSIGNMENT = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)=')
# Commands whose arguments are inert text. This allowlist is safe in the way the
# earlier denylist of command openers was not: an unknown command still fails closed,
# so a name added here can only narrow a false positive, never open a bypass.
PRINTS_ARGUMENTS = {'echo', 'printf', 'cat', 'grep', 'egrep', 'fgrep', 'rg', 'ag', 'ack',
                    'sed', 'awk', 'head', 'tail', 'less', 'more', 'comm', 'diff'}
# These decide which repository git operates on, so the guard would inspect one
# repository's receipts while the command published another's commits.
REDIRECTING = 'GIT_'
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


def unquoted(command, needle):
    """Report whether needle occurs as syntax, outside single and double quotes.

    shlex discards quoting, so a quoted "<<" argument is indistinguishable from the
    heredoc operator once tokenized. Decide that question on the raw text instead.
    """
    quote, index = None, 0
    while index < len(command):
        character = command[index]
        if quote:
            if character == quote:
                quote = None
            elif quote == '"' and character == '\\':
                index += 1
        elif character in '\'"':
            quote = character
        elif character == '\\':
            index += 1
        elif command.startswith(needle, index):
            return True
        index += 1
    return False


def command_words(words):
    """Split leading VAR=value assignments from the command they prefix."""
    index = 0
    while index < len(words) and ASSIGNMENT.match(words[index]):
        index += 1
    return words[:index], words[index:]


def nested_push(argument):
    """Report a git push inside an interpreter's command STRING, however it is spelled."""
    if not re.search(r'\bgit\b', argument) and 'git' not in argument:
        return False
    try:
        nested = shlex.split(argument)
    except ValueError:
        return True
    return any(Path(word).name == 'git' and git_push(nested[index:]) is not None
               for index, word in enumerate(nested)) or names_a_push(nested)


def names_a_push(words):
    """Report a git push standing anywhere but this segment's own command word.

    Three rounds of listing the words after which a command can begin each missed
    another member of the same class -- exec prefixes, then shell keywords, then
    `eval`, `coproc`, `builtin`, `caffeinate`, `unbuffer`, `script`. Resolving which
    token the shell really runs would need every wrapper's option grammar, because
    `timeout 60 git push` and `sudo -u me git push` put an operand where a command
    word would otherwise be, and guessing wrong reopens a bypass rather than
    producing a false positive. So no list is kept and the default is closed: a push
    shape anywhere other than argv[0] is refused, whatever precedes it.

    The cost is borne by commands that pass a literal `git push` as trailing
    arguments, such as `printf "%s %s" git push`, which are refused too. A quoted
    "git push" is one token and is unaffected, so searching for the phrase still works.
    """
    if not words or Path(words[0]).name in PRINTS_ARGUMENTS:
        return False
    # Skip index 0 by POSITION, not by name: `git submodule foreach git push` has git
    # as its own command word and still publishes through the git at index 3.
    return any(Path(word).name == 'git' and git_push(words[index:]) is not None
               for index, word in enumerate(words) if index)


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
    # Bash removes a backslash-newline before parsing, so `git pu\<newline>sh` is one word.
    command = command.replace('\\\n', '')
    # A heredoc is the '<<' operator; the same characters inside a quoted argument are data.
    if unquoted(command, '<<'):
        literal_heredoc(command)
        return None
    # Refuse substitution BEFORE detection, not after: when it supplies the command word
    # itself, as in `$(which git) push`, there is no git token left to detect.
    require(not (re.search(r'\bpush\b', command) and
                 (unquoted(command, '$') or unquoted(command, '`'))),
            'Use a literal git push without shell substitution.')
    try:
        parts = segments(command)
    except ValueError:
        require(not re.search(r'\bgit\b.*\bpush\b', command),
                'Unparsable command naming a git push; issue an explicit git push.')
        return None
    found, unrecognized = None, False
    for _, raw in parts:
        assignments, words = command_words(raw)
        if not words:
            continue
        if Path(words[0]).name in INTERPRETERS:
            # Re-tokenize the nested command: a quoted spelling defeats a regex on the
            # raw text exactly as it defeated the original raw-text detection.
            require(not any(nested_push(word) for word in words[1:]),
                    'Do not wrap git push in another shell.')
        unrecognized = unrecognized or names_a_push(words)
        result = git_push(words)
        if result is None:
            continue
        require(not any(ASSIGNMENT.match(a).group(1).startswith(REDIRECTING) for a in assignments),
                'Run git push without GIT_* overrides; they change which repository git uses.')
        require(found is None, 'Issue one explicit git push per command.')
        found = (raw, result)
    if found is None:
        require(not unrecognized,
                'This names a git push in a form the guard cannot verify; issue an explicit git push.')
        return None
    raw, (directory, arguments) = found
    require(not unrecognized, 'Issue one explicit git push per command.')
    require(parts[-1][1] is raw and all(w is raw or command_words(w)[1][:1] == ['cd'] for _, w in parts),
            'Issue git push as its own command, optionally preceded by cd <path> &&.')
    require(all(o in (None, '&&') for o, _ in parts),
            'Chain a push only with && so it cannot follow an unchecked command.')
    require(not any(x in command for x in ('$', '`')), 'Use a literal git push without shell substitution.')
    for _, other in parts:
        if other is not raw:
            change = command_words(other)[1]
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
