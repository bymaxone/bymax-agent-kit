#!/usr/bin/env python3
"""Collect what one repository shipped in a period, and what was asked of it.

The report a model writes from this JSON is only as honest as the JSON: every update
must trace to a commit or pull request listed here, and every progress item to a
request a person typed into a Claude Code or Codex session on this repository.
Nothing here summarises. The model summarises; this script enumerates.

Sources, in the order they are read:

- ``git log`` of the repository, non-merge commits in the period, with the ref
  each commit was reached from and its Conventional Commits type and scope. ``--author``
  keeps the commits whose git name or email contains the text, and the PRs whose
  GitHub login does; the sessions are already one person\'s, so they are not filtered.
- ``gh pr list`` for pull requests merged or opened in the period. A missing or
  signed-out ``gh`` is recorded in ``coverage`` and never fails the collect.
- Claude Code sessions under ``~/.claude/projects/<slug>``. Only lines a person typed
  count: tool results, task notifications, meta lines the harness injects, compact
  summaries and sidechains are skipped. Worktree sessions live in sibling directories
  named ``<slug>--claude-worktrees-*``; those are read too, and every line is kept only
  if its ``cwd`` is this repository or one of its worktrees.
- Codex sessions under ``~/.codex/sessions``. A session counts when its ``session_meta``
  names this repository as ``cwd`` and its ``source`` is in ``CODEX_HUMAN_SOURCES``.
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
PR_SUFFIX = re.compile(r'\s*\(#(?P<number>\d+)\)\s*$')
IMAGE_TOKEN = re.compile(r'\[Image(?: #\d+)?[^\]]*\]')
DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
TEXT_LIMIT = 800
# Codex writes one input twice, as a response_item and an event_msg milliseconds apart.
# The same text again inside this window is that second copy; outside it, a person typed
# the words again. A calendar minute was tried first and split a pair at :59.995/:00.004.
PAIR_WINDOW = dt.timedelta(seconds=2)
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
            'pr': int(pr.group('number')) if pr else None, **parsed,
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
            'merged_in_period': merged, 'opened_in_period': opened,
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
    if text.lstrip().startswith('# Files mentioned by the user'):
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
        last_admitted: dict[str, dt.datetime] = {}
        first = True
        for line in lines:
            kind = line.get('type')
            body = line.get('payload') or {}
            if kind == 'response_item' and body.get('type') == 'message' and body.get('role') == 'user':
                text = clean_request(message_text(body.get('content')))
            elif kind == 'event_msg' and body.get('type') == 'user_message':
                text = clean_request(body.get('message') or '')
            else:
                continue
            if text is None:
                continue
            timestamp = line.get('timestamp') or ''
            when = parse_timestamp(timestamp)
            previous = last_admitted.get(text)
            if previous is not None and when is not None and abs(when - previous) <= PAIR_WINDOW:
                continue
            if when is not None:
                last_admitted[text] = when
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
            'prs': len(prs), 'requests': len(requests),
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
