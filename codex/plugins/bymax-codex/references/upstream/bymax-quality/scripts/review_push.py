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
from review_hook import HOOK_MARKER, HUSKY_STUB
from review_prepush import TAGS, explain, orphaned, published, satisfied

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
PUNCTUATION = ';&|(){}'
# The characters after which the shell starts a new word, so a `#` there begins a comment. `{` and
# `}` are ordinary word characters to the shell, which is why they are not here.
COMMENT_START = ';&|()<>'


def uncommented(command):
    """The command's words with shell comments dropped, or None when that cannot be done safely.

    A comment line that says "is there a remote to push to?" is not a push, and the kit's own
    prescribed blocks carry such comments. Dropping them is only safe where this reading and the
    shell's agree on what a comment is: inside `${...}` a `#` after a space is literal to the shell
    but starts a comment here, which would hide a push the shell runs, so any command holding `${`
    or `((` keeps its comment text and is read whole. A quote left open — including by an
    apostrophe in a comment the shell would skip — is None as well, and comments are kept.
    """
    if '${' in command or '((' in command:
        return None
    # The shell starts a comment only at the start of an unquoted word (`echo a#b` prints a#b), and
    # shlex.split cuts none, so the comments are cut here by the shell's rule.
    kept, quote, start, comment, escaped = [], '', True, False, False
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
        elif char == '#' and start and not quote:
            comment = True
            continue
        if quote:
            quote = '' if char == quote else quote
        elif char in '\'"':
            quote = char
        start = not quote and (char.isspace() or char in COMMENT_START)
        kept.append(char)
    try:
        return shlex.split(''.join(kept))
    except ValueError:
        return None


def names_push(command, words):
    """Whether a push is written into this command as a word of its own.

    could_push answers a wider question (any word holding the letters, beside any program that can
    start another), and a commit message that says "push" answers yes to it. This one asks for the
    verb itself: a word that is `push` once shell punctuation is trimmed, or one quoted word that
    holds a whole command, `sh -c "git push ..."`, with a program and the verb both in it. Comments
    are not read where `uncommented` can drop them. A command that cannot be read word by word is
    read as its raw text.
    """
    edge = r'(?:^|[\s' + re.escape(PUNCTUATION) + r'\'"`])'
    read = uncommented(command)
    words = words if read is None else read
    if words is None:
        return re.search(edge + 'push' + edge.replace('^', '$'), command.lower()) is not None
    # `echo git push > notes` prints text and runs nothing. That holds only for a command with no
    # separator, substitution or newline in it: `echo x; git push` is a push after an echo.
    if words[:1] in (['echo'], ['printf']) and not any(c in command for c in ';&|(){}$`\n<'):
        return False
    previous = ''
    for word in words:
        spelled = word.strip(PUNCTUATION).lower()
        if spelled == 'push' and previous != 'stash':  # `git stash push` saves changes, it publishes none
            return True
        pieces = [piece.lower() for piece in re.split(r'[\s' + re.escape(PUNCTUATION) + r']+', word) if piece]
        # A whole command in one word runs only as the argument of a shell's -c or of eval/exec;
        # anywhere else it is a pattern or a message that merely quotes one.
        if (len(pieces) > 1 and 'push' in pieces and any(Path(piece).name in RUNNERS for piece in pieces)
                and (re.fullmatch(r'-[a-z]*c', previous) or previous in ('eval', 'exec'))):
            return True
        previous = spelled
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
    # No comment handling, on purpose: deciding what is a comment needs the shell's own grammar
    # (a `#` inside a word or inside a multi-line string is not one), and two readings that
    # tried were each bypassed by a push the shell ran. A command that does not parse is read
    # as able to push and scanned whole, which is safe, and the handoff query is set aside.
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
    require(not (pushes and names_push(command, words)), 'Use a literal git push in its own command.')
    return None


def parse(command, cwd):
    """Return (directory, push arguments) for the literal shape; None for anything else.

    None means this adapter has no opinion: the command is run and the pre-push hook
    decides. Only the literal shape earns a receipt lookup here. A command that could push
    and names the verb without being that shape is refused, not passed on (see `unchecked`).
    """
    # Case-insensitive: git reads config keys and most of these options that way too.
    lowered = command.lower()
    words = words_of(command)
    pushes = could_push(command)
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
    runtime = Path(__file__).with_name('review_flow.py')
    remedy = ('Reinstall it with: cd ' + shlex.quote(top.stdout.strip()) + ' && python3 ' + shlex.quote(str(runtime))
              + " status  (it chains the check back into husky's generated hook; `start` installs it elsewhere).")
    if not hook.is_file() or not os.access(hook, os.X_OK):
        return ('The pre-push hook git will run, ' + str(hook) + ', is missing or not executable, so this push '
                'would be checked by nothing. ' + remedy)
    text = hook.read_text(errors='replace')
    if HUSKY_STUB.search(text) and len(text.splitlines()) <= 2:
        tracked = directory.parent / 'pre-push'
        text = tracked.read_text(errors='replace') if tracked.is_file() else ''
    if HOOK_MARKER not in text and 'review_prepush' not in text:
        return ('The pre-push hook git will run, ' + str(hook) + ', does not call the receipt check (husky '
                'regenerates it on install). ' + remedy)
    problem = probe_problem(hook, cwd, top.stdout.strip())
    return None if problem is None else 'The pre-push hook git will run, ' + str(hook) + ', ' + problem + ' ' + remedy


def probe_problem(hook, cwd, top, seconds=30):
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
        ran = subprocess.run([str(hook), 'origin', 'origin'], input=record, cwd=top,
                             capture_output=True, text=True, timeout=seconds)
    except subprocess.TimeoutExpired:
        return None
    if ran.returncode == 0:
        return 'accepted a push of a commit with no receipt, so it does not enforce receipts.'
    return None


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
