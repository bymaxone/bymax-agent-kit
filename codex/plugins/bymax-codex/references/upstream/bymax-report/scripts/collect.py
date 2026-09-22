#!/usr/bin/env python3
"""Collect what one repository shipped in a period, and what was asked of it.

The report a model writes from this JSON is only as honest as the JSON: every update
must trace to a commit or pull request listed here, and every progress item to a
request a person typed into a Claude Code or Codex session on this repository.
Nothing here summarises. The model summarises; this script enumerates.

Sources, in the order they are read:

- ``git log`` of the repository, non-merge commits in the period, with the ref each commit
  was reached from, whether the delivery branch had reached it by the period's end, and its Conventional Commits
  type and scope. Reachability from any ref is not delivery, so ``shipped`` answers that
  separately. ``--author`` keeps the commits whose git name or email contains the text,
  and the PRs whose GitHub login does; the sessions are already one person\'s, so they
  are not filtered.
- ``gh pr list`` for pull requests merged or opened in the period. A missing or
  signed-out ``gh`` is recorded in ``coverage`` and never fails the collect.
- Claude Code sessions under ``~/.claude/projects/<slug>``. Only lines a person typed
  count: tool results, task notifications, meta lines the harness injects, compact
  summaries and sidechains are skipped. Worktree sessions live in sibling directories
  named ``<slug>--claude-worktrees-*``; those are read too, and every line is kept only
  if its ``cwd`` is this repository or one of its worktrees.
- Codex sessions under ``~/.codex/sessions``. A session counts when its ``session_meta``
  names this repository as ``cwd`` and its ``source`` is in ``CODEX_HUMAN_SOURCES``; a
  request is a ``response_item`` of role ``user``, the one form every input has here.
  ``exec`` and subagent sessions are skipped: on the machine this was built, every
  ``exec`` session was the review plugin prompting Codex, not a person typing.

Timestamps are stored in UTC; the period is a range of local calendar days, so each
timestamp is converted to the machine's local zone before its date is compared.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CONVENTIONAL = re.compile(r'^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?!?:\s*(?P<summary>.+)$')
REFLOG_STAMP = re.compile(r'@\{(\d+)\}')
# The reflog actions that mean a ref moved because this repository caught up with another
# one; a ref moved by anything else moved because the work arrived here.
SYNCED = ('fetch', 'pull', 'clone')
PR_SUFFIX = re.compile(r'\s*\(#(?P<number>\d+)\)\s*$')
IMAGE_TOKEN = re.compile(r'\[Image(?: #\d+)?[^\]]*\]')
DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
TEXT_LIMIT = 800
# gh pr list has no pagination: a read that comes back exactly this long may have dropped
# older PRs, and the coverage note says so instead of reading as complete.
PR_LIMIT = 1000
# A commit body is dropped once a pull request is linked by title or head; the PR body
# carries the story then, and 150 bodies of a week were 110 KB the reader never needed.
BODY_LIMIT = 400
# A Codex session's ``source`` is a string for a person at a keyboard and a dict for a
# subagent. ``exec`` is a string too; on the machine this was built it was never a person.
CODEX_HUMAN_SOURCES = {'cli', 'vscode', 'tui'}
# A Claude line whose promptSource is one of these was written by the harness.
CLAUDE_MACHINE_PROMPTS = {'system'}


def parse_period(spec: str | None, today: dt.date) -> tuple[dt.date, dt.date]:
    """Resolve a period spelling to an inclusive pair of local dates.

    ``last-week`` is the previous Monday through Sunday, the standup's own week.
    ``this-week`` is this Monday through today. ``<n>d`` is the last n days ending today.
    ``A..B`` is explicit. Anything else is refused, so a typo never silently becomes
    the default week.
    """
    spec = (spec or 'last-week').strip().lower()
    monday = today - dt.timedelta(days=today.weekday())
    if spec == 'last-week':
        return monday - dt.timedelta(days=7), monday - dt.timedelta(days=1)
    if spec == 'this-week':
        return monday, today
    days = re.fullmatch(r'(\d+)d', spec)
    if days:
        n = int(days.group(1))
        if n < 1:
            raise ValueError('a period needs at least one day')
        return today - dt.timedelta(days=n - 1), today
    explicit = re.fullmatch(r'(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})', spec)
    if explicit:
        since, until = (dt.date.fromisoformat(part) for part in explicit.groups())
        if until < since:
            raise ValueError(f'period ends before it starts: {spec}')
        return since, until
    raise ValueError(f"unknown period {spec!r}: use last-week, this-week, <n>d or YYYY-MM-DD..YYYY-MM-DD")


def parse_timestamp(timestamp: str) -> dt.datetime | None:
    """An ISO-8601 timestamp as an aware datetime, UTC when it names no zone, or None when unreadable."""
    if not timestamp:
        return None
    try:
        parsed = dt.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def local_date(timestamp: str) -> dt.date | None:
    """The local calendar date of a timestamp, or None when it cannot be read."""
    parsed = parse_timestamp(timestamp)
    return None if parsed is None else parsed.astimezone().date()


def in_period(timestamp: str, since: dt.date, until: dt.date) -> bool:
    date = local_date(timestamp)
    return date is not None and since <= date <= until


def project_slug(path: str) -> str:
    """The directory name Claude Code gives a project: every non-alphanumeric byte becomes a dash."""
    return re.sub(r'[^A-Za-z0-9]', '-', path)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def repo_paths(repo: Path) -> list[str]:
    """The repository root and every registered worktree, as absolute path strings."""
    paths = [str(repo)]
    try:
        listing = git(repo, 'worktree', 'list', '--porcelain')
    except RuntimeError:
        return paths
    for line in listing.splitlines():
        if line.startswith('worktree '):
            path = line[len('worktree '):].strip()
            if path and path not in paths:
                paths.append(path)
    return paths


def belongs(cwd: str | None, paths: list[str]) -> bool:
    """Whether a session's working directory is this repository or lives inside it."""
    if not cwd:
        return False
    cwd = cwd.rstrip('/')
    return any(cwd == root or cwd.startswith(root.rstrip('/') + '/') for root in paths)


def branch_name(ref: str) -> str:
    """A ref as a branch name: no refs/heads/, no refs/remotes/, no origin/ prefix."""
    ref = ref.replace('refs/heads/', '').replace('refs/remotes/', '')
    return ref.split('/', 1)[1] if ref.startswith('origin/') else ref


def conventional(subject: str) -> dict:
    """Split a Conventional Commits subject into type, scope and summary; plain subjects keep only the summary."""
    match = CONVENTIONAL.match(subject)
    if not match:
        return {'type': None, 'scope': None, 'summary': subject}
    return {'type': match.group('type'), 'scope': match.group('scope') or None, 'summary': match.group('summary')}


def delivery_ref(repo: Path) -> str | None:
    """The ref this repository delivers on: what a commit must reach to count as shipped.

    ``origin/HEAD`` is what the remote itself calls its default branch, so it is asked first;
    the conventional names follow, and only ones that resolve here. None means the question
    cannot be answered in this checkout, which is said rather than guessed.
    """
    try:
        head = git(repo, 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD').strip()
    except RuntimeError:
        head = ''
    candidates = ([head[len('refs/remotes/'):]] if head.startswith('refs/remotes/') else [])
    candidates += ['origin/main', 'origin/master', 'main', 'master', 'origin/trunk', 'trunk']
    for name in candidates:
        try:
            git(repo, 'rev-parse', '--verify', '--quiet', name + '^{commit}')
        except RuntimeError:
            continue
        return name
    return None


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


def moved_by_syncing(repo: Path, ref: str) -> bool:
    """Whether any move of that ref was this repository catching up with another one.

    A reflog says when the ref moved *here*, so it is a record of delivery only where the
    move and the delivery are the same event. That is not a property of the ref's name: a
    remote-tracking ref moved by ``update by push`` moved because the work landed, and a
    local branch moved by ``pull`` moved because we caught up. Deciding by the name threw
    the first away, and a clone whose last fetch before the period predated the week
    reported the week's work as still in flight — both measured.

    So the entries answer. An entry's action is the first word of its message once anything
    from the first colon is cut off: ``clone:`` would otherwise keep its colon, and
    ``pull --tags origin main:`` its arguments, while ``update by push`` has no colon at all.
    These words are written into the file by the command that moved the ref, not rendered at
    read time, so they do not follow the reader's language.
    """
    code, out, _ = git_out(repo, 'reflog', 'show', '--format=%gs', ref, '--')
    if code != 0:
        return True
    actions = [line.split(':', 1)[0].split()[0] for line in out.splitlines() if line.strip()]
    return any(action in SYNCED for action in actions)


def delivery_tip(repo: Path, ref: str, until: dt.date) -> tuple[str | None, str]:
    """Where the delivery ref stood at the end of the period, and which record answered.

    Asking what the ref reaches *now* answers a different question from the one a period
    report asks: a branch merged the week after is reachable today and shipped in no week
    under review.

    Where every move of the ref was delivery rather than syncing, the reflog is that record
    and the only thing that sees a fast-forward, which creates no object and stamps no date.
    Where any move was this repository catching up, the reflog says when that happened, so
    the commit dates answer instead — and they carry the upstream merge time,
    which is what the question is about. Neither sees a fast-forward performed elsewhere;
    coverage names the record so the reader knows which question was answered.

    The date walk goes by first parent: it otherwise descends into a merge's second parent
    and returns a commit that was never on the delivery branch, which then marks itself
    shipped. ``--`` ends its revisions, and the ancestry query's: an untracked path spelled
    like the ref, or like a commit's twelve hex digits, otherwise makes git refuse.
    """
    when = f'{until.isoformat()}T23:59:59'
    if not moved_by_syncing(repo, ref) and reflog_reaches(repo, ref, dt.datetime.fromisoformat(when).timestamp()):
        code, out, _ = git_out(repo, 'rev-parse', '--verify', f'{ref}@{{{when}}}')
        if code == 0 and out.strip():
            return out.strip(), f'the reflog of {ref} on {until.isoformat()}'
    out = git(repo, 'rev-list', '-1', '--first-parent', f'--before={when}', ref, '--')
    return out.strip() or None, f'the commit dates on {ref} up to {until.isoformat()}'


def mark_shipped(repo: Path, commits: list[dict], ref: str | None, until: dt.date) -> tuple[str | None, str]:
    """Say, per commit, whether the delivery ref had reached it by the end of the period.

    That is the only sense in which a commit shipped *in* a period. Reachability from any ref
    is not delivery either: an open branch, a tag on it and a remote-tracking copy are all
    reachable, and a report built from them presents work in flight as done.

    Returns the ref that decided, and the sentence coverage carries — which names the record
    that answered, because the reflog and the commit dates answer different questions and the
    reader is entitled to know which one they got. A question git refuses decides nothing, and
    says so with a null ref, because the skill's one escape hatch reads that field: leaving the
    ref there while every commit came back undecided is how a report silently loses its
    updates and claims the branch had ruled on them.

    One ``rev-list`` decides every commit: it prints what the tip does not reach, so a
    collected sha is unshipped exactly when it appears. Asking ``merge-base --is-ancestor``
    instead would be one process per commit.
    """
    if ref is None:
        for commit in commits:
            commit['shipped'] = None
        return None, 'no default branch resolves here, so nothing decided what shipped'
    try:
        tip, answered_by = delivery_tip(repo, ref, until)
    except RuntimeError as error:
        for commit in commits:
            commit['shipped'] = None
        return None, f'asking where {ref} stood on {until.isoformat()} failed, so nothing decided what shipped: {error}'
    decided = (f'a commit shipped when {ref} had reached it by {until.isoformat()}, read from '
               f'{answered_by}; a pull request when it merged in the period')
    if tip is None:
        for commit in commits:
            commit['shipped'] = False
        return ref, f'{ref} held nothing by {until.isoformat()}, read from {answered_by}, so nothing had shipped by then'
    if not commits:
        return ref, decided
    try:
        out = git(repo, 'rev-list', *[c['sha'] for c in commits], '--not', tip, '--')
    except RuntimeError as error:
        for commit in commits:
            commit['shipped'] = None
        return None, f'asking what {ref} reached failed, so nothing decided what shipped: {error}'
    unshipped = {line.strip()[:12] for line in out.splitlines() if line.strip()}
    for commit in commits:
        commit['shipped'] = commit['sha'] not in unshipped
    return ref, decided


def collect_commits(repo: Path, since: dt.date, until: dt.date) -> list[dict]:
    """Non-merge commits reachable from any branch, remote branch or tag in the period, oldest first."""
    # No --since here: git treats it as a traversal cutoff, not a filter, and stops
    # walking a line at the first commit older than the date. A backdated commit
    # (a rebase, a cherry-pick, a clock) then hides every ancestor behind it — the
    # fixture that found this had a commit dated 09-01 whose parent was dated 09-16.
    # So every commit is read and the period is applied here, by author date.
    fmt = '%H%x1f%an%x1f%ae%x1f%aI%x1f%S%x1f%s%x1f%b%x1e'
    # Not --all: it walks refs/stash too, and a stash's commits are work nobody shipped.
    out = git(repo, 'log', '--branches', '--remotes', '--tags', '--source', '--no-merges', '--reverse',
              f'--format={fmt}')
    commits = []
    seen: set[str] = set()
    for record in out.split('\x1e'):
        record = record.strip('\n')
        if not record:
            continue
        parts = record.split('\x1f')
        if len(parts) != 7:
            continue
        sha, author, email, when, ref, subject, body = parts
        if sha in seen or not in_period(when, since, until):
            continue
        seen.add(sha)
        pr = PR_SUFFIX.search(subject)
        parsed = conventional(PR_SUFFIX.sub('', subject))
        commits.append({
            'sha': sha[:12], 'author': author, 'email': email, 'date': local_date(when).isoformat(),
            'ref': branch_name(ref), 'subject': subject, 'body': body.strip()[:BODY_LIMIT],
            'pr': int(pr.group('number')) if pr else None, 'shipped': None, **parsed,
        })
    return commits


def by_author(items: list[dict], author: str | None, *fields: str) -> list[dict]:
    """Keep the records one of whose named fields contains the author text, case-insensitively.

    The same spelling git's --author would accept as a fixed string: a name, an email, or
    a fragment of either. Empty means everyone.
    """
    if not author:
        return items
    needle = author.lower()
    return [item for item in items if any(needle in str(item.get(field) or '').lower() for field in fields)]


def collect_prs(repo: Path, since: dt.date, until: dt.date) -> tuple[list[dict], str]:
    """Pull requests merged or opened in the period, and a coverage note for the reader."""
    fields = 'number,title,body,state,createdAt,mergedAt,closedAt,headRefName,url,author'
    cmd = ['gh', 'pr', 'list', '--state', 'all', '--limit', str(PR_LIMIT),
           '--search', f'updated:>={since.isoformat()}', '--json', fields]
    try:
        result = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return [], 'gh is not installed: pull requests were not read'
    except subprocess.TimeoutExpired:
        return [], 'gh timed out: pull requests were not read'
    if result.returncode != 0:
        return [], f'gh failed: {result.stderr.strip()[:200] or "no error text"}'
    try:
        raw = json.loads(result.stdout or '[]')
    except json.JSONDecodeError:
        return [], 'gh returned something that is not JSON'
    prs = []
    for item in raw:
        merged = in_period(item.get('mergedAt') or '', since, until)
        opened = in_period(item.get('createdAt') or '', since, until)
        if not merged and not opened:
            continue
        parsed = conventional(item.get('title') or '')
        prs.append({
            'number': item.get('number'), 'title': item.get('title'), 'state': item.get('state'),
            # A pull request shipped when it merged in the period; one merged after it, one
            # still open, and one closed without merging are progress and never an update.
            'shipped': merged, 'merged_in_period': merged, 'opened_in_period': opened,
            'merged_at': item.get('mergedAt'), 'created_at': item.get('createdAt'),
            'head': item.get('headRefName'), 'url': item.get('url'),
            'author': (item.get('author') or {}).get('login'),
            'body': (item.get('body') or '').strip()[:TEXT_LIMIT * 2], **parsed,
        })
    prs.sort(key=lambda pr: pr['merged_at'] or pr['created_at'] or '')
    note = f'gh read {len(raw)} pull requests updated since {since.isoformat()}'
    if len(raw) >= PR_LIMIT:
        note += f', which is the cap of {PR_LIMIT}: older ones may be missing'
    return prs, note


def link_commits_to_prs(commits: list[dict], prs: list[dict]) -> None:
    """Give each commit the pull request it shipped in, when the tree still says so.

    A squash merge keeps the PR title as the commit subject; a branch still on the
    remote keeps the PR head as the commit's ref. A commit nothing matches stays
    unlinked, and the reader treats it as work that shipped without a PR.
    """
    by_title = {pr['title']: pr['number'] for pr in prs if pr.get('title')}
    by_head = {pr['head']: pr['number'] for pr in prs if pr.get('head')}
    for commit in commits:
        if commit['pr'] is not None:
            continue
        commit['pr'] = by_title.get(commit['subject']) or by_head.get(commit['ref'])
        if commit['pr'] is not None:
            commit['body'] = ''


def message_text(content) -> str:
    """The text of a message whose content is a string or a list of typed parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get('type') in ('text', 'input_text'):
                parts.append(part.get('text') or '')
        return '\n'.join(parts)
    return ''


def clean_request(text: str) -> str | None:
    """Strip image tokens and refuse text the harness wrote."""
    text = IMAGE_TOKEN.sub('', text or '').strip()
    if not text or text.startswith(('<', 'Another Claude session', '[Request interrupted')):
        return None
    if text.lstrip().startswith(('# Files mentioned by the user', '# AGENTS.md instructions')):
        return None
    return text[:TEXT_LIMIT]


def request(source: str, session: str, timestamp: str, branch: str | None, opens: bool, text: str) -> dict:
    """One thing a person typed, dated in local time to the minute."""
    parsed = parse_timestamp(timestamp)
    return {
        'source': source, 'session': session[:8], 'at': parsed.astimezone().strftime('%Y-%m-%d %H:%M'),
        'branch': branch, 'opens_session': opens, 'text': text,
    }


def read_jsonl(path: Path):
    try:
        with path.open(encoding='utf-8', errors='replace') as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def claude_session_dirs(home: Path, paths: list[str]) -> list[Path]:
    projects = home / '.claude' / 'projects'
    if not projects.is_dir():
        return []
    slugs = {project_slug(path) for path in paths}
    found = []
    for entry in sorted(projects.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in slugs or any(entry.name.startswith(slug + '--claude-worktrees-') for slug in slugs):
            found.append(entry)
    return found


def collect_claude(home: Path, paths: list[str], since: dt.date, until: dt.date) -> tuple[list[dict], dict]:
    """What a person typed into Claude Code on this repository in the period."""
    requests = []
    dirs = claude_session_dirs(home, paths)
    files = 0
    for directory in dirs:
        for path in sorted(directory.glob('*.jsonl')):
            files += 1
            first = True
            for line in read_jsonl(path):
                if line.get('type') != 'user' or 'toolUseResult' in line:
                    continue
                if line.get('isMeta') or line.get('isCompactSummary') or line.get('isSidechain'):
                    continue
                if line.get('promptSource') in CLAUDE_MACHINE_PROMPTS:
                    continue
                if not belongs(line.get('cwd'), paths):
                    continue
                text = clean_request(message_text((line.get('message') or {}).get('content')))
                if text is None:
                    continue
                opens = first
                first = False
                timestamp = line.get('timestamp') or ''
                if not in_period(timestamp, since, until):
                    continue
                requests.append(request('claude', line.get('sessionId') or path.stem, timestamp,
                                        line.get('gitBranch'), opens, text))
    coverage = {'directories': [str(d) for d in dirs], 'files': files}
    return requests, coverage


def collect_codex(home: Path, paths: list[str], since: dt.date, until: dt.date) -> tuple[list[dict], dict]:
    """What a person typed into an interactive Codex session on this repository in the period."""
    sessions = home / '.codex' / 'sessions'
    requests = []
    scanned = matched = skipped_exec = skipped_subagent = 0
    if not sessions.is_dir():
        return requests, {'directory': str(sessions), 'files': 0, 'matched': 0, 'note': 'no Codex sessions directory'}
    for path in sorted(sessions.rglob('*.jsonl')):
        scanned += 1
        lines = read_jsonl(path)
        meta = next(lines, None)
        if not meta or meta.get('type') != 'session_meta':
            continue
        payload = meta.get('payload') or {}
        if not belongs(payload.get('cwd'), paths):
            continue
        source = payload.get('source')
        if isinstance(source, dict):
            skipped_subagent += 1
            continue
        if source not in CODEX_HUMAN_SOURCES:
            skipped_exec += 1
            continue
        matched += 1
        session = payload.get('id') or path.stem
        first = True
        for line in lines:
            body = line.get('payload') or {}
            # What a person typed is a response_item of role user, and only that. Measured on
            # the machine this was built (5 interactive sessions, cli_version 0.151.0, 0.153.4
            # and 0.154.0-alpha.6.2): a typed input also appears 0-6 ms later as an event_msg
            # item_completed/UserMessage, which is not read, so nothing here deduplicates and a
            # repeat at any distance is another ask. Two windows were tried and each lost one.
            if line.get('type') != 'response_item' or body.get('type') != 'message' or body.get('role') != 'user':
                continue
            text = clean_request(message_text(body.get('content')))
            if text is None:
                continue
            timestamp = line.get('timestamp') or ''
            opens = first
            first = False
            if not in_period(timestamp, since, until):
                continue
            requests.append(request('codex', session, timestamp, None, opens, text))
    return requests, {
        'directory': str(sessions), 'files': scanned, 'matched': matched,
        'skipped_exec': skipped_exec, 'skipped_subagent': skipped_subagent,
        'note': 'exec and subagent sessions were not read',
    }


def collect(repo: Path, since: dt.date, until: dt.date, home: Path, use_gh: bool = True,
            author: str | None = None) -> dict:
    paths = repo_paths(repo)
    commits = by_author(collect_commits(repo, since, until), author, 'author', 'email')
    ref, shipped_note = mark_shipped(repo, commits, delivery_ref(repo), until)
    prs, gh_note = collect_prs(repo, since, until) if use_gh else ([], 'gh skipped by --no-gh')
    prs = by_author(prs, author, 'author')
    if author:
        gh_note += f'; kept the PRs whose GitHub login contains {author!r}, and the commits whose git name or email does'
    link_commits_to_prs(commits, prs)
    claude_requests, claude_cov = collect_claude(home, paths, since, until)
    codex_requests, codex_cov = collect_codex(home, paths, since, until)
    requests = sorted(claude_requests + codex_requests, key=lambda r: r['at'])
    return {
        'repo': {'name': repo.name, 'path': str(repo), 'worktrees': paths[1:]},
        'period': {'since': since.isoformat(), 'until': until.isoformat(), 'author': author},
        'commits': commits,
        'prs': prs,
        'requests': requests,
        'coverage': {
            'commits': len(commits), 'commits_without_pr': sum(1 for c in commits if c['pr'] is None),
            'commits_shipped': sum(1 for c in commits if c['shipped']),
            'delivery_ref': ref, 'shipped': shipped_note,
            'prs': len(prs), 'prs_shipped': sum(1 for p in prs if p['shipped']),
            'requests': len(requests),
            'gh': gh_note, 'claude': claude_cov, 'codex': codex_cov,
        },
    }


def dump(data: dict) -> str:
    """JSON with one record per line, so a reader can page it by line and grep it by field.

    ``json.dumps(indent=2)`` turned a week of one repository into 6,000 lines; this keeps
    it at one line per commit, PR and request, and stays valid JSON.
    """
    lines = ['{']
    keys = list(data)
    for index, key in enumerate(keys):
        value = data[key]
        comma = ',' if index < len(keys) - 1 else ''
        if isinstance(value, list):
            if not value:
                lines.append(f'  {json.dumps(key)}: []{comma}')
                continue
            lines.append(f'  {json.dumps(key)}: [')
            for position, item in enumerate(value):
                tail = ',' if position < len(value) - 1 else ''
                lines.append('    ' + json.dumps(item, ensure_ascii=False) + tail)
            lines.append(f'  ]{comma}')
        else:
            lines.append(f'  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}{comma}')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--repo', default='.', help='repository path (default: current directory)')
    parser.add_argument('--period', default='last-week',
                        help='last-week (default), this-week, <n>d, or YYYY-MM-DD..YYYY-MM-DD')
    parser.add_argument('--out', help='write the JSON here instead of stdout')
    parser.add_argument('--no-gh', action='store_true', help='do not read pull requests')
    parser.add_argument('--author', default=None,
                        help='keep only commits whose git name or email contains this, and PRs whose GitHub login does')
    parser.add_argument('--home', default=os.environ.get('HOME', str(Path.home())),
                        help=argparse.SUPPRESS)
    parser.add_argument('--today', default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    try:
        since, until = parse_period(args.period, today)
    except ValueError as error:
        print(f'collect: {error}', file=sys.stderr)
        return 2
    try:
        repo = Path(git(Path(args.repo).resolve(), 'rev-parse', '--show-toplevel').strip()).resolve()
    except RuntimeError as error:
        print(f'collect: {error}', file=sys.stderr)
        return 2

    data = collect(repo, since, until, Path(args.home), use_gh=not args.no_gh, author=args.author or None)
    text = dump(data)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding='utf-8')
        cov = data['coverage']
        print(f"wrote {out}: {cov['commits']} commits, {cov['prs']} PRs, {cov['requests']} requests "
              f"({since} .. {until})")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
