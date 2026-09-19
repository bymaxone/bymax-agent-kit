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
import io
import subprocess
import sys
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
after you and reverts everything if any of that happened."""

SCOPED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def git(*args, cwd=None):
    """Answered about the worktree, not about the directory the process was started in."""
    done = subprocess.run(['git', *args], capture_output=True, text=True,
                          cwd=review_claims.root(cwd))
    return done.stdout if done.returncode == 0 else ''


def changed(cwd=None):
    """Every path the working tree has moved away from HEAD, whatever its type.

    Tracked changes and untracked files both, because a pass that adds a new source file
    leaves `git diff` silent and the envelope would report only what it could already see.
    """
    listed = git('status', '--porcelain', '-z', '--untracked-files=all', cwd=cwd)
    return sorted({row[3:] for row in listed.split('\0') if len(row) > 3})


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


def offences(cwd=None):
    """Every way the working tree has left the envelope, named one by one.

    Per file and never netted: an added comment in one file is not paid for by a deletion
    in another, because the reviewers are told each file's prose did not grow.
    """
    found = []
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
