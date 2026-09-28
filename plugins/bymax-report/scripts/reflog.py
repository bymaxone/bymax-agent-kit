"""Where a branch stood at a moment, read from its reflog, and whether that record can be trusted.

A reflog says where a ref stood only where no
move since was this repository catching up with another one, since a catch-up means our view of
that moment was corrected afterwards. Which moves are catch-ups is read from the messages git
writes, which do not follow the reader's language.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
import re
import subprocess

REFLOG_STAMP = re.compile(r'@\{(\d+)\}')
# Reflog actions that always mean this repository caught the ref up with another one, and
# those that mean it only depending on where the ref was sent: `merge origin/main`,
# `reset: moving to origin/main` and `branch: Reset to origin/main` are catch-ups, the same
# words sent to `feat/x` or `HEAD~1` are local, and the action word is the same on both sides.
# A rebase rewrites the delivery branch onto a commit it names only by id, which no longer says
# whose it was, so it counts as a catch-up: that answer costs a week an unknown, and the other
# one reports work as shipped on the strength of a record the rebase replaced.
SYNCED = ('fetch', 'pull', 'clone', 'rebase')
TOWARD = ('merge', 'reset', 'branch')
# Where an action in TOWARD writes the ref it moved to, after the colon when not before it.
DESTINATION = (' moving to ', ' Reset to ', ' Created from ')
# An operand spelled as an object id says what the ref moved to and not whose it was.
OBJECT_ID = re.compile(r'[0-9a-f]{7,64}')
# A name git quotes in a merge subject. Git writes those subjects in English whatever the
# reader's language, so the words around the names can be read.
QUOTED = re.compile(r"'([^']*)'")


def git_out(repo: Path, *args: str) -> tuple[int, str, str]:
    """Run git and hand back what it said, including the warnings it writes to stderr."""
    done = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def reflog_reaches(repo: Path, ref: str, cutoff: float) -> bool:
    """Whether the ref's reflog goes back far enough to answer for that moment.

    Asked of the entries' own timestamps, not of git's warning: that warning is a sentence
    git translates where catalogues are installed, so reading it would make the answer
    depend on the language the machine speaks. Out of range git still answers, and with exit
    zero: the tip from before its oldest entry, which may be later than the period's.
    """
    code, out, _ = git_out(repo, 'reflog', 'show', '--date=unix', '--format=%gd', ref, '--')
    lines = [line for line in out.splitlines() if line.strip()]
    if code != 0 or not lines:
        return False
    oldest = REFLOG_STAMP.search(lines[-1])
    return bool(oldest) and int(oldest.group(1)) <= cutoff


def moved_by_syncing(repo: Path, message: str, tracking: bool) -> bool:
    """Whether one reflog entry records this repository catching up with another one.

    Read from the message, because that is where git puts what it did. An entry's action is
    the first word before the first colon: ``clone:`` would otherwise keep its colon, and
    ``pull --tags origin main:`` its arguments, while ``update by push`` has no colon at all
    — what the pushing repository writes on its tracking ref, where the receiver writes
    ``push``. Git writes those words into the file, so they do not follow the reader's
    language.

    An action in ``SYNCED`` is always a catch-up, whatever the ref is called.

    An action in ``TOWARD`` is a catch-up or local work depending on where the ref was sent,
    and the action word cannot tell: the operands can. A merge names them before the
    colon, every one of them, and an octopus merge is a catch-up when any operand is; a reset
    names one after ``moving to``, and ``branch`` after ``Reset to`` or ``Created from``. What
    each operand is, is ``names_another_repository``'s question. An action from ``TOWARD`` with
    no operand at all is read as a catch-up, since nothing says it was local.

    Anything left over is read as local, because the actions that are not on either list —
    ``commit``, ``update by push``, ``am``, ``cherry-pick`` — move a ref because the work landed.
    A ``commit (merge)`` concludes a merge, and ``committed_merge_syncs`` reads what it merged.

    An entry carrying no action at all is one ``GIT_REFLOG_ACTION=`` produces, and what
    it hides depends on which ref moved. A push writes ``update by push`` on the tracking ref
    whatever that variable says, so on a ref under ``refs/remotes/`` a blank entry is a fetch,
    and a catch-up. On a local branch it is our own merge or reset — or a pull, which is a
    catch-up this cannot see; that residual under-reports.
    """
    head, _, tail = message.partition(':')
    words = head.split()
    action = words[0] if words else ''
    if not action:
        return tracking
    if action in SYNCED:
        return True
    if words == ['commit', '(merge)']:
        return committed_merge_syncs(repo, tail.strip())
    if action not in TOWARD:
        return False
    operands = words[1:]
    if not operands:
        for marker in DESTINATION:
            if marker in ' ' + tail:
                operands = (' ' + tail).rpartition(marker)[2].split()[:1]
                break
    if not operands:
        return True
    return any(names_another_repository(repo, operand) for operand in operands)


def committed_merge_syncs(repo: Path, subject: str) -> bool:
    """Whether a merge concluded by ``git commit`` caught this repository up with another one.

    A merge that stops on a conflict writes nothing to the reflog, and the commit that
    concludes it writes ``commit (merge):`` and the merge's subject. What was merged, which a
    ``merge`` entry names before its colon, is then only in the words git's merge message
    uses: ``Merge remote-tracking branch 'origin/main'`` for a tracking ref, ``Merge branch
    'main' of <url>`` for what a pull fetched, ``Merge branch 'feat/x'`` or ``Merge tag 'v1'``
    for a ref of ours. A ref name holds no space, so neither ``remote-tracking branch`` nor
    ``' of '`` can come from one of the names. A name spelled as an object id is
    ``names_another_repository``'s question, and a branch of ours called like one resolves to
    its own name there. A subject that is not a merge message names nothing, and is a catch-up
    as a ``merge`` entry without an operand is, since nothing says it was local. A subject
    rewritten by hand that happens to hold `` of `` reads as a catch-up too: that leaves the
    period's landing unknown, which is the direction that never over-reports.
    """
    if not subject.startswith('Merge '):
        return True
    if 'remote-tracking branch' in subject or ' of ' in subject:
        return True
    return any(OBJECT_ID.fullmatch(name) and names_another_repository(repo, name)
               for name in QUOTED.findall(subject))


def names_another_repository(repo: Path, operand: str) -> bool:
    """Whether a reflog operand is what another repository sent here.

    Only git is asked: it exits 128 and echoes back a name it cannot resolve, and answers a
    plain revision such as ``HEAD~1`` with nothing at all, so a ref under ``refs/remotes/`` with
    a zero status is another repository's and a name it can no longer resolve stays local,
    which under-reports a pruned tracking ref: reading the remote its name begins with instead
    turned a local merge into a catch-up once a deleted branch's name began with a remote's.
    ``FETCH_HEAD`` is what the last fetch brought, so it is another repository's by definition.
    An object id resolves to no name either, and it may be anyone's: counted as another
    repository's, it leaves the week unknown rather than reporting it from a record it may not
    be.
    """
    if operand == 'FETCH_HEAD':
        return True
    code, named, _ = git_out(repo, 'rev-parse', '--symbolic-full-name', operand)
    if code == 0 and named.strip():
        return named.strip().startswith('refs/remotes/')
    return bool(OBJECT_ID.fullmatch(operand))


def synced_since(repo: Path, ref: str, cutoff: float) -> bool:
    """Whether this repository caught the ref up with another one after that moment.

    A reflog says when the ref moved *here*, so it is a record of delivery only where the
    move and the delivery are the same event. That is not a property of the ref's name: a
    remote-tracking ref moved by ``update by push`` moved because the work landed, and a
    local branch moved by ``pull`` moved because we caught up. It is not a property of the
    whole history either. A sync before the period is history: someone's work arrived, and
    where the ref stood last week is still what we put there. A sync after it says something
    later corrected our view of that week. Testing every entry confused the two and sent a
    delivering ref back to the dates, which reported work pushed the week after as delivered
    inside it. What each entry is, is ``moved_by_syncing``'s question.
    """
    code, out, _ = git_out(repo, 'reflog', 'show', '--date=unix', '--format=%gd%x1f%gs', ref, '--')
    if code != 0:
        return True
    named = git_out(repo, 'rev-parse', '--symbolic-full-name', ref)
    tracking = named[0] == 0 and named[1].strip().startswith('refs/remotes/')
    for line in out.splitlines():
        stamp, _, message = line.partition('\x1f')
        at = REFLOG_STAMP.search(stamp)
        if not at or int(at.group(1)) <= cutoff:
            continue
        if moved_by_syncing(repo, message, tracking):
            return True
    return False


def reflog_tip(repo: Path, ref: str, when: str) -> str | None:
    """Where the ref stood at that moment by its reflog, or None when the reflog cannot say.

    Where no move since that moment was this repository syncing, the reflog is the record of
    where the ref stood and the only one that sees a fast-forward, which creates no object and
    stamps no date. Where a move since was a catch-up, our view of that moment was corrected
    afterwards, and a reflog that begins after it has nothing on record for it.
    """
    cutoff = dt.datetime.fromisoformat(when).timestamp()
    if synced_since(repo, ref, cutoff) or not reflog_reaches(repo, ref, cutoff):
        return None
    code, out, _ = git_out(repo, 'rev-parse', '--verify', f'{ref}@{{{when}}}')
    return out.strip() if code == 0 and out.strip() else None
