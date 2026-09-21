#!/usr/bin/env python3
"""A prose pass that corrects instead of reporting, inside an envelope a function checks.

A false sentence costs a whole round today: freeze the candidate, two reviewers, triage, a
correction commit. Measured on one campaign: 3 of the 6 findings in its final round were
about prose, and the corrections that answered prose findings wrote 203 lines of prose
against 19 of code — the answer to a prose finding was more prose, which is the next
round's findings.

So the prose is corrected before the candidate freezes, by a reader who has never seen the
author's reasoning. That last part is the whole mechanism: re-reading one's own sentence
re-runs the reasoning that wrote it, and the flawed premise is still in place, so the
conclusion is reached again. A reader without that premise checks the sentence against the
code instead.

What keeps this from becoming the loop it is meant to end:

    prose only      a Python file's behaviour — its syntax tree with every docstring
                    removed — must be identical before and after. Markdown is prose
                    throughout. Anything else this pass cannot read, so it cannot show a
                    change there is prose, and refuses it.
    never longer    the pass may correct and delete; it may not expand, per file. An
                    "improved" comment is new unverified surface, which is how the loop
                    restarts.
    before freezing never on a frozen candidate: editing what reviewers were handed
                    invalidates the review rather than improving it.

Comparing syntax trees rather than changed lines is what lets the pass correct the comment
at the end of a line of code — the commonest edit there is — while still refusing the edit
that changes the code beside it. A line-based envelope had to call such a line one thing or
the other, and either answer was wrong for half the edits.

The rule the pass applies is not taste. Published taxonomy names the smells, and every
prose defect measured on this loop was one of them — Misleading, Non-local, or Too much
information. None was a comment explaining WHY. A reason does not rot when the
implementation changes; a description of the implementation rots by definition. So: keep
the why, correct or cut the what.
"""
import ast
import hashlib
import io
from stat import S_IFMT, S_ISDIR, S_ISLNK, S_ISREG
import os
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

import review_claims

RULES = """Correct prose that is FALSE about the code, and cut prose that cannot stay true.
Keep every sentence that says WHY — a decision, a constraint, a rejected alternative. Those
do not rot when the implementation changes, and they are the reason comments exist here.

Cut or correct these, which are named smells and were every measured defect on this codebase:
  - Misleading: the sentence describes behaviour the code does not have.
  - Non-local: the sentence describes code in ANOTHER file, which nobody editing that file
    can keep true. This was the single largest class here.
  - Too much information: a count of the project's own history, a list that duplicates what
    the code states, an explanation longer than what it explains.

A fact about the code does not belong in prose at all. If a sentence asserts a count, a list,
or a set ("these three refusals", "six attempts", "the helper has one call site"), the fix is
to delete the assertion and point at the test or the code that holds it — not to correct the
number. A number corrected is a number that drifts again.

You may edit comments, docstrings and markdown only, and only in the files listed below. Do
not add prose anywhere; do not touch code; do not create or delete files. A verifier runs
after you and refuses the whole pass if any of that happened."""

SCOPED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def git(*args, cwd=None):
    """Answered about the worktree, not about the directory the process was started in."""
    done = subprocess.run(['git', *args], capture_output=True, text=True,
                          cwd=review_claims.root(cwd))
    return done.stdout if done.returncode == 0 else ''


def changed(cwd=None):
    """Every path whose worktree differs from HEAD, as git itself decides it.

    Asked of git through a scratch index built from HEAD, not of the repository's own:
    the index carries assume-unchanged and skip-worktree bits that hide a file from every
    status and diff, and status honours submodule.<name>.ignore and showUntrackedFiles on
    top. A scratch index has no bits, so `git diff HEAD` compares every tracked file, with
    git's own line-ending conversion — hashing the bytes outside the index normalised CRLF
    that the index would have kept, and refused a clean tree forever. Untracked files are
    read against the same scratch index, so a staged addition is listed too. A file a sparse
    checkout leaves absent is not a change, because its skip-worktree bit excuses an absence
    and nothing else.
    """
    root = review_claims.root(cwd)
    # Under the git directory, which no listing walks: a scratch file under a $TMPDIR inside
    # the worktree listed itself as untracked while it existed.
    handle, scratch = tempfile.mkstemp(prefix='bymax-index-', dir=git('rev-parse', '--absolute-git-dir', cwd=cwd).strip())
    os.close(handle)
    os.unlink(scratch)
    env = dict(os.environ, GIT_INDEX_FILE=scratch)
    try:
        subprocess.run(['git', 'read-tree', 'HEAD'], cwd=root, env=env, check=True, capture_output=True)
        # The scratch index is stat-dirty everywhere by construction, and the porcelain diff
        # drops a stat-dirty file with identical content only under diff.autoRefreshIndex;
        # asked for explicitly, so a user who turned it off does not get a clean tree refused.
        listed = subprocess.run(['git', '-c', 'diff.autoRefreshIndex=true', 'diff', '--name-only', '-z',
                                 '--ignore-submodules=none', 'HEAD'],
                                cwd=root, env=env, check=True, capture_output=True, text=True).stdout
        others = subprocess.run(['git', 'ls-files', '-z', '--others', '--exclude-standard'],
                                cwd=root, env=env, check=True, capture_output=True, text=True).stdout
    finally:
        if os.path.exists(scratch):
            os.unlink(scratch)
    return present(root, {name for name in (listed + others).split('\0') if name}, cwd=cwd)


def present(root, names, cwd=None):
    """The listed names minus the absences a sparse checkout made on purpose.

    The one bit read from the repository's own index, and only to excuse an ABSENCE, and
    only in a sparse checkout: a sparse checkout leaves files out on purpose and marks
    them skip-worktree, and read-tree does not reapply its patterns to a scratch index.
    Outside a sparse checkout the bit was set by hand, and an absence is a deletion — a
    reader deleting such a file went unseen. Asked as a boolean, because git spells true
    as yes, on and 1 too, and a string compare refused a clean sparse checkout forever. A present path is compared whatever its bits
    say, and a symlink is present when its own entry is, whatever its target does.
    """
    if git('config', '--type=bool', '--get', 'core.sparseCheckout', cwd=cwd).strip() != 'true':
        return sorted(names)
    skipped = {row[2:] for row in git('ls-files', '-z', '-v', cwd=cwd).split('\0') if row[:1] in ('S', 's')}
    return sorted(name for name in names if name not in skipped or os.path.lexists(Path(root) / name))


def ignored(cwd=None):
    """Untracked files the repository ignores, each with a digest of its bytes: not a change,
    and never part of a candidate — but one the reader creates, edits or deletes is a file it
    left, so offences compares this snapshot before and after. Names alone saw a creation and
    missed an edit and a deletion; size and mtime saw those and missed a same-length edit
    with the mtime put back. The bytes are what the invariant is about, and reading them
    once per stage is cheap: twenty thousand small files or one of a gibibyte, under a
    second. A nested repository is one entry to git and its inside is not this
    repository's; a directory entry is recorded by name alone."""
    root = review_claims.root(cwd)
    out = subprocess.run(['git', 'ls-files', '-z', '--others', '--ignored', '--exclude-standard'],
                         cwd=root, check=True, capture_output=True, text=True).stdout
    found = {}
    for name in (n for n in out.split('\0') if n):
        found[name] = identity(Path(root) / name)
    return found


def identity(path):
    """What an ignored entry is, as far as bytes go: a digest for a regular file, and a kind
    for everything else. Only a regular file is opened — git lists a pipe or a socket among
    the ignored too, and opening a pipe with no writer waits forever, ahead of any timeout.
    A file that cannot be read is recorded as such: a reader with Edit alone cannot alter what
    it cannot read either, and a refusal there protected nothing. The digest streams, so a
    file larger than memory costs time and not a MemoryError."""
    stat = os.lstat(path)
    if S_ISLNK(stat.st_mode):
        return 'link:' + os.readlink(path)
    if S_ISDIR(stat.st_mode):
        return 'dir'
    if not S_ISREG(stat.st_mode):
        return 'special:%o' % S_IFMT(stat.st_mode)
    try:
        with open(path, 'rb') as handle:
            return hashlib.file_digest(handle, 'sha256').hexdigest()
    except OSError as error:
        return 'unreadable:%d' % (error.errno or 0)


def sides(name, cwd=None):
    """(committed text, working-tree text) for one file, named from the worktree root."""
    where = Path(review_claims.root(cwd)) / name
    working = where.read_text() if where.is_file() else None
    return git('show', 'HEAD:%s' % name, cwd=cwd), working


def behaviour(text):
    """A Python file's syntax tree with every docstring removed, dumped.

    This is what a prose edit must leave identical. Comments are not in the tree at all;
    docstrings are the first statement of a module, class or function, and are cut here so
    that correcting one reads as no change. Everything else — an operator, an order, a
    name, a deleted line — changes the dump, and the envelope refuses it.
    """
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, SCOPED) and ast.get_docstring(node, clean=False) is not None:
            node.body = node.body[1:]
    return ast.dump(tree, include_attributes=False)


def header(text):
    """What the interpreter reads before the tree: the shebang, and the encoding.

    The encoding comes from tokenize.detect_encoding, the interpreter's own reader, rather
    than from a pattern: a pattern matched a cookie on line two after code, which Python
    ignores, and refused a reworded comment it could not show was behaviour. A cookie
    changed from utf-8 to latin-1 is still refused, because the file then prints differently.
    """
    first = text.split('\n', 1)[0]
    try:
        encoding = tokenize.detect_encoding(io.BytesIO(text.encode('utf-8')).readline)[0]
    except SyntaxError:
        encoding = None
    return [first if first.startswith('#!') else '', encoding]


def prose_size(name, text):
    """How much prose a file carries, so growth can be refused per file.

    Markdown: its non-empty lines. Python: comment tokens plus docstring lines. A file that
    does not parse has no measurable prose and answers None; the envelope has already
    refused it by then, since nothing can show its change was prose.
    """
    if name.endswith('.md'):
        return sum(1 for line in text.split('\n') if line.strip())
    count = 0
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            count += tok.type == tokenize.COMMENT
        tree = ast.parse(text)
    except (SyntaxError, tokenize.TokenError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, SCOPED):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                count += doc.count('\n') + 1
    return count


def first_change(name, cwd=None):
    """The first changed row that is not a comment line, so a refusal names what moved.

    The written side first: a diff lists what was removed before what replaced it, and the
    line the author needs to see is the one now in the file.
    """
    at = None
    removed = ''
    for row in git('diff', '-U0', 'HEAD', '--', name, cwd=cwd).split('\n'):
        if row.startswith('@@'):
            at = int(row.split('+')[1].split(',')[0].split()[0])
        elif row[:1] in '+-' and row[:3] not in ('+++', '---') and at is not None:
            text = row[1:].strip()
            if text and not text.startswith('#'):
                if row.startswith('+'):
                    return ' at line %d: %s' % (at, text[:70])
                removed = removed or ' near line %d, removed: %s' % (at, text[:70])
            at += row.startswith('+')
    return removed


def ignored_since(before, cwd=None):
    """What the reader did to ignored files, each named by its own verb."""
    if not isinstance(before, dict) or any(not isinstance(v, str) for v in before.values()):
        # A marker from a runtime that recorded names alone, or sizes and mtimes: nothing here
        # can say what the reader did to them. The remedy is a fresh prepare, not a guess.
        return ['the prepared marker records ignored files without their contents, which an earlier '
                'runtime wrote; run `prose --stage prepare` again on a clean tree']
    now = ignored(cwd=cwd)
    found = []
    for name in sorted(now.keys() - before.keys()):
        found.append('%s is ignored and new: a pass corrects prose that exists, it does not add a file' % name)
    for name in sorted(n for n in before if n in now and now[n] != before[n]):
        found.append('%s is ignored and was edited: an ignored file is not prose of this delta' % name)
    for name in sorted(before.keys() - now.keys()):
        found.append('%s is ignored and was deleted: a pass corrects prose, it does not remove a file' % name)
    return found


def offences(cwd=None, ignored_before=None):
    """Every way the working tree has left the envelope, named one by one.

    Per file and never netted: an added comment in one file is not paid for by a deletion
    in another, because the reviewers are told each file's prose did not grow.
    """
    found = [] if ignored_before is None else ignored_since(ignored_before, cwd=cwd)
    for name in changed(cwd=cwd):
        if not name.endswith(review_claims.READABLE):
            found.append('%s is not a file this pass can read, so nothing here can show its '
                         'change is prose' % name)
            continue
        before, after = sides(name, cwd=cwd)
        if not before:
            found.append('%s is new: a pass corrects prose that exists, it does not add a file' % name)
            continue
        if after is None:
            found.append('%s was deleted: a pass corrects prose, it does not remove a file' % name)
            continue
        if before == after:
            # git lists it and the text is the same: the mode changed, or the line endings
            # did, and neither is prose. Text mode folds CRLF into LF, so this is the only
            # place a line-ending edit is seen.
            found.append('%s: changed in mode or line endings, not prose' % name)
            continue
        if name.endswith('.py'):
            try:
                same = behaviour(before) == behaviour(after)
            except SyntaxError as error:
                found.append('%s does not parse, so nothing can show its change is prose: %s'
                             % (name, error))
                continue
            if not same:
                found.append('%s: behaviour changed, not prose%s' % (name, first_change(name, cwd=cwd)))
            if header(before) != header(after):
                found.append('%s: the shebang or coding declaration changed, which Python reads '
                             'as behaviour' % name)
        was, now = prose_size(name, before), prose_size(name, after)
        if was is not None and now is not None and now > was:
            found.append('%s: prose grew by %d; this pass corrects and cuts, it does not expand, '
                         'because an expanded comment is new surface nothing checks'
                         % (name, now - was))
    return found


def envelope(cwd=None):
    """Refuse the pass's own edits when they leave the envelope. Exit status, not advice."""
    broken = offences(cwd=cwd)
    for line in broken:
        print('OUTSIDE  ' + line)
    if broken:
        print('\nRevert these and run the pass again. A prose pass that edits behaviour is worse '
              'than the sentence it came to fix: the reviewers were told it touched no code.')
        return 1
    print('%d file(s) changed, prose only, no growth.' % len(changed(cwd=cwd)))
    return 0


def prepare(base, head, cwd=None):
    """The task a fresh reader is given: this delta's added prose, file by file."""
    added = review_claims.added(base, head, cwd=cwd)
    if not added:
        return ''
    parts = [RULES, '', 'Prose this delta added, by file. Read each sentence against the code '
                       'in that file at %s and correct what is false.' % head[:12], '']
    for name, text in sorted(added.items()):
        parts.append('--- %s' % name)
        parts.append(text)
        parts.append('')
    return '\n'.join(parts)


def cut(cwd=None):
    """Lines of prose the pass removed, summed over the files it changed."""
    total = 0
    for name in changed(cwd=cwd):
        before, after = sides(name, cwd=cwd)
        was, now = prose_size(name, before or ''), prose_size(name, after or '')
        if was is not None and now is not None:
            total += max(0, was - now)
    return total


def main(argv):
    if len(argv) == 4 and argv[1] == 'prepare':
        text = prepare(argv[2], argv[3], cwd=str(Path.cwd()))
        print(text or 'This delta added no prose; there is nothing for a prose pass to read.')
        return 0
    if len(argv) == 2 and argv[1] == 'verify':
        return envelope(cwd=str(Path.cwd()))
    print('usage: review_prose.py prepare <base> <head> | review_prose.py verify', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
