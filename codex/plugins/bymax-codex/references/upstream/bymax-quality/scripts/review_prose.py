#!/usr/bin/env python3
"""A prose pass that corrects instead of reporting, inside an envelope a function checks.

A false sentence costs a whole round today: freeze the candidate, two reviewers, triage, a
correction commit. Measured on one campaign: 7 of 27 findings were about prose, and the
corrections that answered them wrote 203 lines of prose against 19 of code — so the answer
to a prose finding was more prose, which is the next round's findings.

So the prose is corrected before the candidate freezes, by a reader who has never seen the
author's reasoning. That last part is the whole mechanism: re-reading one's own sentence
re-runs the reasoning that wrote it, and the flawed premise is still in place, so the
conclusion is reached again. A reader without that premise checks the sentence against the
code instead.

What keeps this from becoming the loop it is meant to end:

    prose only      every changed line must be a comment, a docstring or markdown, in both
                    the old file and the new. A behaviour edit wearing a prose pass is the
                    one outcome that would be worse than the defect.
    never longer    the pass may correct and delete; it may not expand. An "improved"
                    comment is new unverified surface, which is how the loop restarts.
    before freezing never on a frozen candidate: editing what reviewers were handed
                    invalidates the review rather than improving it.

The rule the pass applies is not taste. Published taxonomy names the smells, and every prose
defect measured on this loop was one of them — Misleading, Non-local, or Too much information.
None was a comment explaining WHY. A reason does not rot when the implementation changes; a
description of the implementation rots by definition. So: keep the why, correct or cut the
what.
"""
import subprocess
import sys
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
number. A number corrected is a number that drifts again."""


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
    listed = git('status', '--porcelain', '-z', cwd=cwd)
    names = []
    for row in listed.split('\0'):
        if len(row) > 3:
            names.append(row[3:])
    return sorted(set(names))


def prepare(base, head, cwd=None):
    """The task a fresh reader is given: this delta's prose, and the code it describes."""
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


def sides(name, cwd=None):
    """(committed text, working-tree text) for one file, named from the worktree root."""
    where = Path(review_claims.root(cwd))
    working = (where / name).read_text() if (where / name).is_file() else ''
    return git('show', 'HEAD:%s' % name, cwd=cwd), working


def offences(cwd=None):
    """Every way the working tree has left the envelope, named one by one.

    Additions and removals both, per file. An earlier version read only added lines and
    claimed in a comment that removals were covered by the growth total, which counted prose
    alone — so deleting a line of live code passed as "prose only, no growth". And the total
    was summed across files, which let an added comment in one be paid for by a deletion in
    another.
    """
    found = []
    for name in changed(cwd=cwd):
        if not name.endswith(review_claims.READABLE):
            found.append('%s is not a file this pass can read, so nothing here can show its '
                         'change is prose' % name)
            continue
        before, after = sides(name, cwd=cwd)
        was, now = review_claims.marks(name, before), review_claims.marks(name, after)
        if len(now) > len(was):
            found.append('%s: prose grew by %d line(s); this pass corrects and cuts, it does '
                         'not expand, because an expanded comment is new surface nothing '
                         'checks' % (name, len(now) - len(was)))
        found += stray(name, was, now, cwd=cwd)
    return found


def stray(name, was, now, cwd=None):
    """Changed lines in one file that are not prose on the side they belong to."""
    out = []
    at = old = None
    for row in git('diff', '-U0', 'HEAD', '--', name, cwd=cwd).split('\n'):
        if row.startswith('@@'):
            old = int(row.split('-')[1].split(',')[0].split()[0])
            at = int(row.split('+')[1].split(',')[0].split()[0])
        elif row.startswith('+') and not row.startswith('+++') and at is not None:
            if at not in now:
                out.append('%s:%d adds code, not prose: %s' % (name, at, row[1:].strip()[:70]))
            at += 1
        elif row.startswith('-') and not row.startswith('---') and old is not None:
            if old not in was:
                out.append('%s:%d removes code, not prose: %s' % (name, old, row[1:].strip()[:70]))
            old += 1
    return out


def envelope(cwd=None):
    """Refuse the pass's own edits when they leave the envelope. Exit status, not advice."""
    broken = offences(cwd=cwd)
    for line in broken:
        print('OUTSIDE  ' + line)
    if broken:
        print('\nRevert these and run the pass again. A prose pass that edits behaviour is worse '
              'than the sentence it came to fix: the reviewers were told it touched no code.')
        return 1
    files = changed(cwd=cwd)
    print('%d file(s) changed, prose only, no growth.' % len(files))
    return 0


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
