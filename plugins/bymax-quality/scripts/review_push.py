#!/usr/bin/env python3
"""Claude hook adapter: an early receipt check for the one literal push shape.

The enforcement boundary is the git pre-push hook that review_flow.py installs, which
receives the pushed SHAs from git itself and therefore holds however the push command
was spelled. This adapter does smaller jobs before git runs: it recognises the exact
`[cd <path> &&] [VAR=value ...] git [-C <dir>] push <remote> <refspec>...` form so a
missing receipt is reported with a useful message, it refuses the few options that would
disable or redirect that hook, and it refuses a push written inside a longer command or
ahead of a hook that accepts an unreceipted push. A command that runs no git push passes
untouched. A push deliberately spelled so that no check sees it is outside what a local
guard can prevent; review-protocol.md names CI as the boundary for that.
"""
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys

from review_flow import POLICY, require
from review_hook import HOOK_MARKER, HUSKY_STUB
from review_prepush import TAGS, explain, orphaned, published, satisfied

# Seconds a probe of the hook may take: under the time Claude Code gives this adapter, so a hook that
# does not answer is dropped here, not the whole adapter.
PROBE_SECONDS = 10

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
# `git rev-parse --git-dir` prints where the git directory is; it points git nowhere. The
# commands write handoff files at `$(git rev-parse --git-dir)/bymax-*`, so reading the token
# there as `git --git-dir=` refused blocks the kit itself prescribes. Only that literal handoff
# path is set aside, character for character: its content is fixed, so nothing a variable expands
# to can turn it into another command, and `$(git rev-parse --git-dir)/hooks` is still read. A
# pattern loose enough to accept `-C <dir>` or options was bypassed twice — by `rev-parse` as a
# mere word on the line, and by `git -C $X rev-parse --git-dir /y push` with X holding
# `. --namespace` — so every other spelling is read.
GIT_DIR_QUERY = '$(git rev-parse --git-dir)/bymax-'


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
    # A program written against shell punctuation, `(git push ...)` or `true&&git push ...`, is the
    # word `(git` or `true&&git` to shlex; its pieces are what the shell runs.
    return any(Path(piece).name in RUNNERS for word in words
               for piece in re.split('[' + re.escape(PUNCTUATION) + ']+', word) if piece)


# Shell punctuation that can sit against a word without being part of it: `a; git push` reads as the
# word `push` once these are trimmed, and `x&&git push` likewise.
PUNCTUATION = ';&|(){}`'
# The characters after which the shell starts a new word, so a `#` there begins a comment. `{` and
# `}` are ordinary word characters to the shell, which is why they are not here.
COMMENT_START = ';&|()<>'


def uncommented(command):
    """The command's words with shell comments dropped, or None when that cannot be done safely."""
    text = decommented(command)
    try:
        return None if text is None else shlex.split(text)
    except ValueError:
        return None


def decommented(command):
    """The command text with shell comments dropped, or None when that cannot be done safely.

    A comment line that says "is there a remote to push to?" is not a push, and the kit's own
    prescribed blocks carry such comments. Dropping them is only safe where this reading and the
    shell's agree on what a comment is: inside `${...}` a `#` after a space is literal to the shell,
    so none starts there, and a command holding `((` or a heredoc keeps its comment text and is
    read whole (None), the heredoc body being text to the shell, `#` included.
    """
    if '((' in command or '<<' in command:
        return None
    # The shell starts a comment only at the start of an unquoted word (`echo a#b` prints a#b), and
    # shlex.split cuts none, so the comments are cut here by the shell's rule.
    kept, quote, start, comment, escaped, depth = [], '', True, False, False, 0
    for char in command:
        if comment:
            if char != '\n':
                continue
            comment = False
        elif escaped:
            escaped, start = False, False
            kept.append(char)
            continue
        elif char == '\\' and quote != "'":
            escaped, start = True, False
            kept.append(char)
            continue
        elif char == '#' and start and not quote and not depth:
            comment = True
            continue
        if char == '{' and kept and kept[-1] == '$' and quote != "'":
            depth += 1
        elif char == '}' and depth and quote != "'":
            depth -= 1
        if quote:
            quote = '' if char == quote else quote
        elif char in '\'"':
            quote = char
        start = not quote and (char.isspace() or char in COMMENT_START)
        kept.append(char)
    return ''.join(kept)


# Where the shell ends one simple command and starts another.
SPLIT = ';&|()\n`{}'
# Programs that only print, read or search the words they are given and never start one of them, so
# `echo git push` is a mention. Any other program may start a later `git`, and is read as if it does:
# the list of launchers is open-ended (command, stdbuf, setsid, a script of the user's own), this one is not.
PASSIVE = frozenset({'echo', 'printf', 'cat', 'grep', 'egrep', 'fgrep', 'rg', 'ag', 'man', 'which', 'whereis',
                     'type', 'head', 'tail', 'wc', 'less', 'more', 'diff', 'ls', 'test', '[', 'true', 'false',
                     'sort', 'uniq', 'cut', 'tr', 'basename', 'dirname', 'realpath', 'jq', 'tee', 'read',
                     'cd', 'export', 'unset', 'set', 'alias', 'unalias', 'local', 'declare', 'return', 'exit'})
# Words that open a clause (`then git push`, `! git push`): the command is the word after.
KEYWORDS = frozenset({'then', 'else', 'elif', 'do', '!', 'time'})
# A compound command that a pipe feeds as a whole: every command inside it may read what was piped.
OPENERS = frozenset({'if', 'while', 'until', 'for', 'case', 'select'})
CLOSERS = frozenset({'fi', 'done', 'esac'})
# What can run the text it is given.
SHELL_SINKS = frozenset({'sh', 'bash', 'zsh', 'dash', 'ksh', 'ash', 'fish'})
CODE_SINKS = frozenset({'eval', 'source', '.'})
# Stands for input whose text is not known before the command runs.
UNKNOWN = '\x00'
GIT_WITH_VALUE = frozenset({'-C', '--git-dir', '--work-tree', '--namespace', '--super-prefix', '--config-env'})
GIT_FLAGS = frozenset({'-p', '-P', '--paginate', '--no-pager', '--bare', '--no-replace-objects',
                       '--literal-pathspecs', '--glob-pathspecs', '--noglob-pathspecs',
                       '--icase-pathspecs', '--no-optional-locks', '--no-lazy-fetch'})
HEREDOC = re.compile(r'<<(?!<)-?\s*(["\']?)([A-Za-z_][A-Za-z0-9_]*)\1')
SHELLS = re.compile(r'\b(?:sh|bash|zsh|dash|ksh|eval|source)\b')
WORD_EDGE = r'(?:^|$|[\s' + re.escape(PUNCTUATION) + r'\'"`\\])'
# What the shell reads as an operator, longest first so that `<<<` is not `<<` and `<`.
OPERATORS = ('<<<', '<<-', '<<', '<(', '>(', '>>', '>&', '<&', '&>', '>|', '<>', '|&', '||', '&&', ';;', ';&')
OPERATOR_CHARS = ';&|()<>'
# Operators that take the word after them (a file, a delimiter, a here-string's text) and start no command.
REDIRECTS = frozenset({'<<<', '<<-', '<<', '>>', '>&', '<&', '&>', '>|', '<>', '<', '>'})
# An operator character that is quoted or escaped is swapped for a private mark before the words are read, so it
# stays inside its word instead of being read as an operator.
MARKS = {char: chr(0xE000 + number) for number, char in enumerate(OPERATOR_CHARS)}
UNMARK = str.maketrans({mark: char for char, mark in MARKS.items()})


def segments(text):
    """The text cut into simple commands at every unquoted separator."""
    parts, buffer, quote, escaped = [], [], '', False
    for char in text:
        if escaped:
            escaped = False
        elif char == '\\' and quote != "'":
            escaped = True
        elif quote:
            quote = '' if char == quote else quote
        elif char in '\'"':
            quote = char
        elif char in SPLIT:
            parts.append(''.join(buffer))
            buffer = []
            continue
        buffer.append(char)
    parts.append(''.join(buffer))
    return parts


def heredocs(text):
    """(the text without heredoc bodies, the bodies that run), or None when a body is unterminated.

    A body is text to the shell, so `git push` written in one is not a push. It runs where the
    command reading it is a shell, or what follows the operator hands it to a program not known to only print, or, for an
    unquoted delimiter, where it holds `$( )` or backticks (only those substitutions run).
    """
    lines, main, runs, index = text.split('\n'), [], [], 0
    while index < len(lines):
        line = lines[index]
        main.append(line)
        index += 1
        for found in HEREDOC.finditer(line):
            body = []
            while index < len(lines) and lines[index].strip() != found.group(2):
                body.append(lines[index])
                index += 1
            if index >= len(lines):
                return None
            index += 1
            blob = '\n'.join(body)
            later = '\n'.join(lines[index:])
            if SHELLS.search(line[:found.start()]) or fed_to_program(line[found.end():] + '\n' + later):
                runs.append(blob)
            elif not found.group(1):
                runs += re.findall(r'\$\(([^)]*)\)', blob) + re.findall(r'`([^`]*)`', blob)
    return '\n'.join(main), runs


def names_push(text):
    """Whether the text has `push` as a word of its own."""
    return re.search(WORD_EDGE + 'push' + WORD_EDGE, text.lower()) is not None


def masked(text):
    """The text with each quoted or escaped operator character marked, and each newline that ends a command a `;`.

    A newline after a pipe or `&&` continues the command, so it is only a space.
    """
    out, quote, escaped = [], '', False
    for char in text:
        if escaped:
            escaped = False
            out.append(MARKS.get(char, char))
        elif char == '\\' and quote != "'":
            escaped = True
            out.append(char)
        elif quote:
            quote = '' if char == quote else quote
            out.append(MARKS.get(char, char))
        elif char in '\'"':
            quote = char
            out.append(char)
        elif char == '\n':
            out.append(' ' if ''.join(out[-64:]).rstrip().endswith(('|', '&&')) else ' ; ')
        else:
            out.append(char)
    return ''.join(out)


def tokens_of(text):
    """The text as (kind, token) pairs, `word` or `op`, with quotes honoured; None when the shell could not read it."""
    lexer = shlex.shlex(masked(text), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ''
    try:
        raw = list(lexer)
    except ValueError:
        return None
    tokens = []
    for token in raw:
        if all(char in OPERATOR_CHARS for char in token):
            while token:
                size = next((len(operator) for operator in OPERATORS if token.startswith(operator)), 1)
                tokens.append(('op', token[:size]))
                token = token[size:]
        else:
            tokens.append(('word', token.translate(UNMARK)))
    return tokens


class Frame:
    """What one group of commands (the whole text, a subshell, a brace group, a substitution) has shown so far."""

    def __init__(self, closer, inherited):
        self.closer = closer
        self.inherited = inherited  # what the group's standard input holds; '' when nothing is fed to it
        self.found = False          # text naming a push reached a program that is not known to only print
        self.shown = []             # every word of the group
        self.quiet = True           # every command so far only prints
        self.piped = None           # what the pipe into the current command holds; None when no pipe leads to it
        self.pipeline = ''          # what the passive commands of this pipeline printed; None once one is not passive
        self.name = None            # the current command's program
        self.words = []             # the current command's words
        self.printing = True        # the current command only prints
        self.depth = 0              # compound commands (while, if, ...) open around the current command
        self.held = ''              # what the outermost open compound command was fed
        self.dynamic = False        # a word of the current command is not known before it runs
        self.dynamic_in = False     # the current command's input is a substitution or a here-string not known before it runs
        self.subs = ''              # the text of the substitutions among the current command's words

    def stdin(self):
        if self.piped is not None:
            return self.piped
        return self.held if self.depth else self.inherited

    def runs_unknown(self):
        """Whether the current command is a sink that may run a push."""
        names = {Path(word).name for word in self.words}
        unknown_in = UNKNOWN in self.stdin() or self.dynamic_in
        if names & CODE_SINKS:
            return unknown_in or self.dynamic or names_push(self.subs)
        flagged = any(word.startswith('-') and 'c' in word for word in self.words)
        return bool(names & SHELL_SINKS) and (unknown_in or (flagged and (self.dynamic or names_push(self.subs))))

    def close_command(self):
        self.found = self.found or (bool(self.words) and self.runs_unknown())
        self.dynamic = self.dynamic_in = False
        self.subs = ''
        self.shown += self.words
        self.quiet = self.quiet and self.printing
        self.name, self.words, self.printing = None, [], True

    def absorb(self, child):
        """Take in a group that stands where a command would."""
        self.found = self.found or child.found
        self.words.append(' '.join(child.shown))
        self.subs += ' ' + ' '.join(child.shown)
        self.printing = self.printing and child.quiet


class Reach:
    """Finds where text that names a push is handed to a program that is not known to only print.

    A command is fed when a pipe leads to it, or when it stands inside a group that a pipe leads to,
    whatever separates it from the group's first command: `echo git push | (read l; eval $l)`.
    """

    def __init__(self, tokens):
        self.tokens, self.pos = tokens, 0

    def next_word(self):
        """The word after a redirection, consumed; None when an operator follows it instead."""
        if self.pos < len(self.tokens) and self.tokens[self.pos][0] == 'word':
            self.pos += 1
            return self.tokens[self.pos - 1][1]
        return None

    def group(self, closer, inherited):
        """Walk to the end of one group and return its Frame."""
        frame = Frame(closer, inherited)
        while self.pos < len(self.tokens):
            kind, token = self.tokens[self.pos]
            self.pos += 1
            if (self.word if kind == 'word' else self.operator)(frame, token):
                break
        frame.close_command()
        return frame

    def word(self, frame, token):
        """Apply one word; True when it closes a brace group."""
        if frame.name is None:
            if token in OPENERS:
                frame.held = frame.stdin() if not frame.depth else frame.held
                frame.depth += 1
                return False
            if token in CLOSERS and frame.depth:
                frame.depth -= 1
                return False
            if ASSIGNMENT.match(token) or token in KEYWORDS:
                return False
            if token == '}' and frame.closer == '}':
                return True
            frame.name = token
            if token == '{':
                frame.absorb(self.group('}', frame.stdin()))
                return False
            frame.printing = Path(token).name in PASSIVE
            frame.found = frame.found or (not frame.printing and names_push(frame.stdin()))
        elif '$' in token or '`' in token:
            frame.dynamic = True
        frame.words.append(token)
        return False

    def operator(self, frame, token):
        """Apply one operator; True when it closes a group."""
        if token in ('|', '|&'):
            quiet = frame.printing and frame.pipeline is not None
            frame.pipeline = frame.pipeline + ' ' + ' '.join(frame.words) if quiet else None
            frame.piped = UNKNOWN if frame.pipeline is None else frame.pipeline
            frame.close_command()
        elif token in ('(', '<(', '>('):
            self.substitution(frame, token)
        elif token in REDIRECTS:
            word = self.next_word()
            if token == '<<<' and word is not None:
                frame.words.append(word)
                frame.dynamic_in = frame.dynamic_in or '$' in word or '`' in word
        elif token == ')' and frame.closer == ')':
            return True
        else:
            frame.close_command()
            frame.piped, frame.pipeline = None, ''
        return False

    def substitution(self, frame, token):
        """A subshell, or a process substitution that reads from or feeds the command it is given to."""
        if token == '(':
            child = self.group(')', frame.stdin() if frame.name is None else '')
            frame.absorb(child)
            return
        printed = ' '.join([frame.stdin(), *frame.words]) if token == '>(' and frame.printing and frame.name else ''
        child = self.group(')', printed)
        text = ' '.join(child.shown)
        frame.found = frame.found or child.found or (token == '<(' and not frame.printing and names_push(text))
        frame.dynamic_in = frame.dynamic_in or (token == '<(' and not child.quiet)
        frame.subs += ' ' + text
        frame.words.append(text)


def reaches_program(text, carried=''):
    """Whether text naming a push is handed to a program that may run it; None when the text cannot be read."""
    tokens = tokens_of(text)
    return None if tokens is None else Reach(tokens).group(None, carried).found


def fed_to_program(rest):
    """Whether what follows a heredoc operator hands the body to a program that may run it."""
    return reaches_program('cat push ' + rest) is not False


def git_pushes(tokens):
    """Whether git, given these words after its own name, runs the push subcommand (or cannot be ruled out)."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == '-c':
            if index + 1 >= len(tokens) or 'push' in tokens[index + 1].lower():
                return True  # an alias to push is a push
            index += 2
        elif token in GIT_WITH_VALUE:
            index += 2
        elif token in GIT_FLAGS or (token.startswith('--') and '=' in token):
            index += 1
        elif token.startswith('-'):
            return True  # an option this reader does not know could take the next word
        else:
            return token == 'push'
    return False


def segment_pushes(tokens, depth):
    """Whether one simple command's words run git push."""
    while tokens and (ASSIGNMENT.match(tokens[0]) or tokens[0] in KEYWORDS):
        tokens = tokens[1:]
    if not tokens:
        return False
    program = Path(tokens[0]).name
    if any(mark in tokens[0] for mark in '$`') and any(word.strip().lower() == 'push' for word in tokens):
        return True  # the program is not known until the shell expands it
    if program == 'git':
        return git_pushes(tokens[1:])
    if program in PASSIVE:
        return False
    # A wrapper starts another program: a quoted word with a whole command in it, `sh -c "..."`, or
    # a git named later on the line (`env X=1 git push`, `timeout 5 git push`).
    if any(len(word.split()) > 1 and runs_push(word, depth + 1) for word in tokens[1:]):
        return True
    named = next((i for i, word in enumerate(tokens[1:], 1) if Path(word).name == 'git'), None)
    return named is not None and git_pushes(tokens[named + 1:])


def runs_push(command, depth=0):
    """Whether any simple command in this text runs git push.

    could_push answers a wider question (any word holding the letters, beside any program that can
    start another), and `git log --grep push` answers yes to it.
    This one reads each simple command and asks whether git is the program and push its
    subcommand, so a word that is only text, or another program's verb, is not a push. Comments are
    dropped where `decommented` can; whatever cannot be read word by word is read as its raw text.
    """
    text = decommented(command)
    cut = heredocs(command if text is None else text)
    if depth > 4 or cut is None:
        return re.search(WORD_EDGE + 'push' + WORD_EDGE, command.lower()) is not None
    main, runs = cut
    if any(runs_push(body, depth + 1) for body in runs):
        return True
    if reaches_program(main):
        return True
    for part in segments(main):
        try:
            tokens = shlex.split(part)
        except ValueError:
            if 'push' in part.lower():
                return True
            continue
        if segment_pushes(tokens, depth) or any(('$(' in word or '`' in word) and runs_push(word, depth + 1)
                                                for word in tokens):
            return True
    return False


def git(cwd, *args):
    """Read repository state for the command's explicit working directory."""
    return subprocess.check_output(['git', '-C', str(cwd), *args], text=True, stderr=subprocess.DEVNULL).strip()


def words_of(command):
    """The command's words after quote removal, or None when it cannot be parsed.

    Less than the shell does, and the difference matters: shlex performs no parameter
    expansion, no command substitution and no ANSI-C quoting, so a token the shell would
    assemble from `${...}` appears in neither this form nor the raw text. Reading both forms
    strictly beats reading one, and calling it "what the shell hands on" made the gap between
    them look closed when it is the residue this adapter has always had.
    """
    # No comment handling here, on purpose: deciding what is a comment needs the shell's own grammar
    # (a `#` inside a word or inside a multi-line string is not one), and the readings that
    # tried it here were each bypassed by a push the shell ran. `decommented` is the one reader
    # that cuts comments, and only where it agrees with the shell. A command that does not parse
    # is read as able to push and scanned whole, which is safe.
    try:
        return shlex.split(command)
    except ValueError:
        return None


def unchecked(command, words, pushes):
    """None for a command that is not the literal push shape, unless it is a push in disguise.

    `git commit ...; git push ...` and `x && git push ...` carry a push the receipt lookup never
    sees, because only a command that starts with git push is read for one. Letting them run left
    the pre-push hook as the only check, and a hook that has been regenerated checks nothing, so a
    command that could reach a remote and names the verb is refused instead of passed on.
    """
    require(not (pushes and runs_push(command)), 'Use a literal git push in its own command.')
    return None


def parse(command, cwd):
    """Return (directory, push arguments) for the literal shape; None for anything else.

    None means this adapter has no opinion: the command is run and the pre-push hook
    decides. Only the literal shape earns a receipt lookup here. A command that could push
    and names the verb without being that shape is refused, not passed on (see `unchecked`).
    """
    # Case-insensitive: git reads config keys and most of these options that way too.
    lowered = command.lower()
    pushes = could_push(command)
    cut = decommented(command)
    if cut is not None and cut.strip():
        command = cut.strip()  # a comment line before a literal push does not make it another shape
    words = words_of(command)
    # Both forms, for one reachable reason: a token split across quotes — core.hooks""Path — is
    # absent from the raw text and present once the shell has parsed it. The converse cannot
    # happen, because quote removal only deletes characters and so never breaks a token the raw
    # text already spells contiguously; the raw scan is kept because it costs nothing and reads
    # the command as the user wrote it. Reading only the raw form was the unrepaired
    # half of the previous round's fix, which moved the precondition to the words and left the
    # scan a line below it on the raw command.
    seen = lowered + '\n' + ' '.join(words).lower() if words is not None else lowered
    seen = seen.replace(GIT_DIR_QUERY, '')
    require(not pushes or not any(token.lower() in seen for token in DISARMS),
            'That would disable or redirect the pre-push receipt check; run a plain git push. '
            'A command that only names one of these — reading a hook, grepping for the token — '
            'is not this refusal: it applies where the command could reach a remote. That '
            'includes one command holding both a word spelling "push" (a path such as '
            'hooks/pre-push counts) and a program able to start another, git among them, so '
            'a read that shares a line with a git command is refused: run the read as its own command.')
    if words is None:
        return unchecked(command, words, pushes)
    tail = command
    if words[:1] == ['cd'] and len(words) > 3 and words[2] == '&&':
        cwd = (Path(cwd) / words[1]).resolve()
        words, tail = words[3:], command.split('&&', 1)[1]
    while words and ASSIGNMENT.match(words[0]):
        words = words[1:]
    if not words or Path(words[0]).name != 'git':
        return unchecked(command, words, pushes)
    words = words[1:]
    if words[:1] == ['-C'] and len(words) > 1:
        cwd, words = (Path(cwd) / words[1]).resolve(), words[2:]
    if words[:1] != ['push']:
        return unchecked(command, words, pushes)
    # The shape matched, so from here the command is a push and must be exactly one.
    require(not any(c in tail.strip() for c in '$`;|&<>\n'), 'Use a literal git push in its own command.')
    return cwd, words[1:]


def hook_gap(cwd):
    """Why the pre-push hook git will run for this repository does not check receipts; None when it does.

    The hook is the enforcement boundary, and `pnpm install` can replace it: husky regenerates its
    `_/pre-push` on every install, dropping the check, after which a push is judged by nothing. The
    hook git runs is the one in core.hooksPath (relative to the worktree root) or else the common
    directory's hooks, so that file is read, not the one this runtime last wrote. A husky stub
    delegates to the tracked `<hooks dir>/../pre-push`, which counts when it carries the check.
    """
    top = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if top.returncode != 0:
        return None  # not a repository: the push itself fails, and there is no hook to read
    custom = subprocess.run(['git', '-C', str(cwd), 'config', '--get', 'core.hooksPath'],
                            capture_output=True, text=True)
    if custom.returncode == 0:
        directory = Path(top.stdout.strip()) / Path(custom.stdout.strip()).expanduser()
    else:
        common = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                capture_output=True, text=True)
        if common.returncode != 0:
            return None
        directory = Path(common.stdout.strip()) / 'hooks'
    hook = directory / 'pre-push'
    remedy = hook_remedy(hook, top.stdout.strip(), custom.returncode == 0)
    if not hook.is_file() or not os.access(hook, os.X_OK):
        return ('The pre-push hook git will run, ' + str(hook) + ', is missing or not executable, so this push '
                'would be checked by nothing. ' + remedy)
    problem = probe_problem(hook, cwd, top.stdout.strip())
    return None if problem is None else 'The pre-push hook git will run, ' + str(hook) + ', ' + problem + ' ' + remedy


def hook_remedy(hook, top, custom):
    """How to put the receipt check back, in the words that are true for this hook."""
    runtime = Path(__file__).with_name('review_flow.py')
    text = hook.read_text(errors='replace') if hook.is_file() else ''
    if HUSKY_STUB.search(text) and len(text.splitlines()) <= 2 or hook.parent.name == '_':
        return ('Reinstall it with: cd ' + shlex.quote(top) + ' && python3 ' + shlex.quote(str(runtime))
                + " status  (it chains the check back into husky's generated hook).")
    checker = runtime.with_name('review_prepush.py')
    if custom:
        return ('core.hooksPath names ' + str(hook.parent) + ', which `start` never writes into: point ' + str(hook)
                + ' at ' + str(checker) + ', keeping any check you merged in.')
    return ('Run `start` from ' + shlex.quote(top) + ' (python3 ' + shlex.quote(str(runtime))
            + ' start ...) to install the bundled hook, or point ' + str(hook) + ' at ' + str(checker) + '.')


def probe_problem(hook, cwd, top, seconds=PROBE_SECONDS):
    """What a probe push says is wrong with the hook, or None.

    A marker in the text is a claim: a hook can carry the words and exit 0. The hook is run on a
    push of a commit no receipt can name, the way git would, and must refuse it. A hook that does
    not answer in time is no verdict: a husky hook may run a test suite first, and the installed
    hook still decides at the push.
    """
    parent = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--verify', '-q', 'HEAD'],
                            capture_output=True, text=True)
    tree = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--verify', '-q', 'HEAD^{tree}'],
                          capture_output=True, text=True)
    if parent.returncode != 0 or tree.returncode != 0:
        return None  # no commit yet: nothing here can be pushed
    # Written as an object, not with commit-tree: that needs the user's identity and may sign.
    body = ('tree ' + tree.stdout.strip() + '\nparent ' + parent.stdout.strip() + '\n'
            'author probe <probe@example.invalid> 0 +0000\ncommitter probe <probe@example.invalid> 0 +0000\n\n'
            'receipt probe\n')
    made = subprocess.run(['git', '-C', str(cwd), 'hash-object', '-t', 'commit', '-w', '--stdin'], input=body,
                          capture_output=True, text=True)
    require(made.returncode == 0, 'Could not build the commit used to probe the pre-push hook: ' + made.stderr.strip())
    record = 'refs/heads/receipt-probe ' + made.stdout.strip() + ' refs/heads/receipt-probe ' + '0' * 40 + '\n'
    try:
        status = run_probe(hook, record, top, seconds)
    except OSError as error:
        return 'could not be run (' + str(error.strerror) + '), so git would not run it either.'
    if status == 0:
        return 'accepted a push of a commit with no receipt, so it does not enforce receipts.'
    return None


def run_probe(hook, record, top, seconds):
    """The hook's exit status on one push record, or None when it did not answer within `seconds`.

    The hook runs in its own process group, so that a timeout stops what it started as well: a
    husky hook that runs a test suite leaves grandchildren a plain kill does not reach.
    """
    shebang = hook.read_bytes().startswith(b'#!')  # git runs a hook without one through sh
    child = subprocess.Popen([*([] if shebang else ['sh']), str(hook), 'origin', 'origin'], stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=top, text=True,
                             start_new_session=True)
    try:
        child.communicate(record, timeout=seconds)
    except subprocess.TimeoutExpired:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(child.pid, sig)
                child.wait(timeout=2)
                break
            except (subprocess.TimeoutExpired, ProcessLookupError):
                continue
        return None
    return child.returncode


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


class MissingReceipt(ValueError):
    """The one refusal the review campaign can answer: a pushed commit without a usable receipt.

    Every other refusal is about the command's spelling or the repository's configuration,
    and finishing a review cannot change either, so it must not tell the caller to run one.
    """


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
        if not satisfied(state):
            raise MissingReceipt('The receipt for ' + sha[:12] + ' cannot clear this push: ' + explain(state))
        return
    raise MissingReceipt('No completed review for pushed commit ' + sha[:12])


def tags_unpublished(cwd, remote, words):
    """None when the push is not of tags only; '' when every push URL's default branch already
    holds each tag's commit; otherwise why not.

    The hook decides the same from the records git hands it. Only the full spelling
    refs/tags/<name> counts, on both sides: a short name may be a branch, and a tag written to
    refs/heads/ is a branch push. A tag that is not published still passes on a receipt.
    """
    specs = [word for word in words if not word.startswith('-')][1:]
    if not specs or not all(spec.split(':')[0].startswith(TAGS) and spec.split(':')[-1].startswith(TAGS)
                            for spec in specs):
        return None
    urls = subprocess.run(['git', '-C', str(cwd), 'remote', 'get-url', '--push', '--all', '--', remote],
                          capture_output=True, text=True)
    if urls.returncode != 0 or not urls.stdout.split():
        return remote + ' is not a configured remote'
    targets = [spec.split(':')[0] for spec in specs]
    return next((r for r in (published(remote, url, targets, cwd=cwd) for url in urls.stdout.split()) if r), '')


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
        unpublished = tags_unpublished(cwd, remote, words)
        if unpublished == '':
            return
        try:
            for source in refs:
                approved(cwd, source)
        except MissingReceipt as missing:
            if unpublished is None:
                raise
            raise MissingReceipt(str(missing) + '. A push of tags only needs no receipt when each '
                                 "tag's commit is already on " + remote + "'s default branch, and "
                                 'here ' + unpublished + '.') from None
        # Last, so a push that lacks a receipt still hears about the receipt: a receipt the hook
        # will not look for is the second thing wrong with it, not the first.
        gap = hook_gap(cwd)
        require(gap is None, str(gap))


def cli():
    """The process entry point, separate from main() so a test can drive it in a process
    whose Codex resolution table it controls; the command line never controls it."""
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        message = 'BLOCKED: ' + str(error)
        if isinstance(error, MissingReceipt):
            message += ('\nAUTOMATIC CONTINUATION: the authorized push is pending. '
                        'Run /bymax-quality:code-review using start --autonomous, reuse evidence, complete both '
                        'reviewers, triage proven blockers, run gates and finish. Retry the original push destination/refspec. '
                        'Do not ask whether to review or continue ordinary verified corrections. Keep the original scope '
                        'and six-candidate delivery budget; never bypass a real blocker or disable this hook.')
        print(message, file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    cli()
