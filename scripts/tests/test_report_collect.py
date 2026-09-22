"""Gate layer for the standup collector: what it counts as evidence is decided here.

A report is only as honest as the records under it, and the collector's job is to
admit a person's request and refuse everything the harness wrote in the same file.
Each case names a line shape that exists in a real session file on the machine this
was built on. A collector that admitted any of them would write a PROGRESS item
nobody asked for.
"""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'plugins/bymax-report/scripts/collect.py'


def load():
    spec = importlib.util.spec_from_file_location('collect', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def noon(date: str) -> str:
    """A UTC timestamp at midday, so the local date is the same on any machine in the tests' zones."""
    return f'{date}T12:00:00.000Z'


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(r) for r in records) + '\n')


class PeriodTests(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.today = dt.date(2026, 9, 21)  # a Monday

    def test_last_week_is_the_previous_monday_through_sunday(self):
        self.assertEqual(self.m.parse_period('last-week', self.today),
                         (dt.date(2026, 9, 14), dt.date(2026, 9, 20)))

    def test_last_week_from_a_thursday_still_ends_on_sunday(self):
        self.assertEqual(self.m.parse_period(None, dt.date(2026, 9, 24)),
                         (dt.date(2026, 9, 14), dt.date(2026, 9, 20)))

    def test_days_end_today(self):
        self.assertEqual(self.m.parse_period('7d', self.today), (dt.date(2026, 9, 15), self.today))

    def test_explicit_range(self):
        self.assertEqual(self.m.parse_period('2026-09-01..2026-09-07', self.today),
                         (dt.date(2026, 9, 1), dt.date(2026, 9, 7)))

    def test_a_typo_is_refused_rather_than_becoming_last_week(self):
        for bad in ('lastweek', '2026-09-07..2026-09-01', '0d', 'week'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.m.parse_period(bad, self.today)


class ConventionalTests(unittest.TestCase):
    def test_type_scope_and_summary(self):
        m = load()
        self.assertEqual(m.conventional('feat(likes): stand the sweep down'),
                         {'type': 'feat', 'scope': 'likes', 'summary': 'stand the sweep down'})
        self.assertEqual(m.conventional('Guideline flags reach Pearl')['scope'], None)
        self.assertEqual(m.conventional('fix!: breaking')['type'], 'fix')

    def test_remote_prefix_is_not_a_branch_name(self):
        m = load()
        self.assertEqual(m.branch_name('refs/remotes/origin/fix/x'), 'fix/x')
        self.assertEqual(m.branch_name('refs/heads/feat/y'), 'feat/y')


class CollectTests(unittest.TestCase):
    """A fixture repository, a fake HOME with both session stores, and one collect over them."""

    def setUp(self):
        self.m = load()
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / 'home'
        self.repo = self.tmp / 'work' / 'app'
        self.repo.mkdir(parents=True)
        env = {**os.environ, 'GIT_AUTHOR_DATE': '2026-09-16T12:00:00Z', 'GIT_COMMITTER_DATE': '2026-09-16T12:00:00Z',
               'GIT_AUTHOR_NAME': 'Dev', 'GIT_AUTHOR_EMAIL': 'd@x', 'GIT_COMMITTER_NAME': 'Dev', 'GIT_COMMITTER_EMAIL': 'd@x'}
        git = lambda *a, **k: subprocess.run(['git', '-C', str(self.repo), *a], check=True, capture_output=True, env={**env, **k})
        git('init', '-q', '-b', 'main')
        (self.repo / 'a').write_text('1')
        git('add', 'a'); git('commit', '-q', '-m', 'feat(likes): stand the sweep down when Skool answers 429')
        (self.repo / 'b').write_text('2')
        git('add', 'b'); git('commit', '-q', '-m', 'chore: outside the period',
            GIT_AUTHOR_DATE='2026-09-01T12:00:00Z', GIT_COMMITTER_DATE='2026-09-01T12:00:00Z')
        git('checkout', '-q', '-b', 'fix/verdict')
        (self.repo / 'c').write_text('3')
        git('add', 'c'); git('commit', '-q', '-m', 'fix(approval): read a verdict written as text')
        git('checkout', '-q', 'main')
        self.repo = self.repo.resolve()
        self.slug = self.m.project_slug(str(self.repo))
        self.since, self.until = dt.date(2026, 9, 14), dt.date(2026, 9, 20)

    def claude_line(self, text, **extra):
        base = {'type': 'user', 'timestamp': noon('2026-09-16'), 'cwd': str(self.repo), 'sessionId': 'abcdef1234',
                'gitBranch': 'main', 'promptSource': 'typed', 'message': {'role': 'user', 'content': text}}
        base.update(extra)
        return {k: v for k, v in base.items() if v is not None}

    def test_only_what_a_person_typed_is_a_request(self):
        """Every shape below exists in a real session file; only the first two are asks."""
        lines = [
            self.claude_line('fix the approver, it says AI scoring degraded'),
            self.claude_line([{'type': 'image', 'source': {}}, {'type': 'text', 'text': '[Image #1] posts break guidelines and Pearl gets no Slack message'}]),
            self.claude_line('<task-notification> done', promptSource='system'),
            self.claude_line([{'type': 'text', 'text': '[Image: source: /x/1.png]'}], isMeta=True),
            self.claude_line('# Code Review\nRun a bounded review', isMeta=True),
            self.claude_line([{'type': 'tool_result', 'content': 'ok'}], toolUseResult={'x': 1}),
            self.claude_line('Another Claude session sent a message: hello'),
            self.claude_line('this is a summary', isCompactSummary=True),
            self.claude_line('a sidechain prompt', isSidechain=True),
            self.claude_line('typed in another repo', cwd='/elsewhere/other'),
            self.claude_line('typed before the period', timestamp=noon('2026-09-10')),
            self.claude_line('[Request interrupted by user]'),
            self.claude_line('[Request interrupted by user for tool use]'),
            # A session written before promptSource existed: the tag alone must refuse it.
            self.claude_line('<task-notification> done without promptSource', promptSource=None),
            # What Codex injects at the start of a turn, as a user-role message with no tag.
            self.claude_line('# AGENTS.md instructions for /repo\n\n<INSTRUCTIONS>\nrules'),
        ]
        write_jsonl(self.home / '.claude/projects' / self.slug / 's1.jsonl', lines)
        data = self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False)
        texts = [r['text'] for r in data['requests']]
        self.assertEqual(texts, ['fix the approver, it says AI scoring degraded',
                                 'posts break guidelines and Pearl gets no Slack message'])
        self.assertTrue(data['requests'][0]['opens_session'])
        self.assertFalse(data['requests'][1]['opens_session'])
        self.assertEqual(data['requests'][0]['branch'], 'main')

    def test_worktree_sessions_are_read_and_a_sibling_project_is_not(self):
        """Claude Code keeps a worktree's sessions in `<slug>--claude-worktrees-<name>`; a project whose
        slug merely starts with ours (`app-web`) is another repository."""
        wt = self.repo / '.claude/worktrees/pearl'
        write_jsonl(self.home / '.claude/projects' / f'{self.slug}--claude-worktrees-pearl' / 'w.jsonl',
                    [self.claude_line('tell Pearl in Slack when a reply mentions her', cwd=str(wt), gitBranch='pearl-mention-slack')])
        write_jsonl(self.home / '.claude/projects' / f'{self.slug}-web' / 'o.jsonl',
                    [self.claude_line('the other repo', cwd=str(self.repo) + '-web')])
        data = self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False)
        self.assertEqual([r['text'] for r in data['requests']], ['tell Pearl in Slack when a reply mentions her'])
        self.assertEqual(data['requests'][0]['branch'], 'pearl-mention-slack')
        self.assertEqual(len(data['coverage']['claude']['directories']), 1)

    def codex_session(self, name, source, cwd, messages):
        meta = {'timestamp': noon('2026-09-17'), 'type': 'session_meta',
                'payload': {'id': name, 'cwd': cwd, 'source': source, 'originator': 'x'}}
        items = [{'timestamp': noon('2026-09-17'), 'type': 'response_item',
                  'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': t}]}}
                 for t in messages]
        write_jsonl(self.home / '.codex/sessions/2026/09/17' / f'rollout-{name}.jsonl', [meta, *items])

    def test_codex_counts_a_person_and_not_the_review_plugin_or_a_subagent(self):
        self.codex_session('cli1', 'cli', str(self.repo),
                           ['<recommended_plugins>\nlist', '\n# Files mentioned by the user:\n\n## a.mov', 'make the DM route read the cache'])
        self.codex_session('vs1', 'vscode', str(self.repo), ['ship the panel'])
        self.codex_session('exec1', 'exec', str(self.repo), ['Review this diff for defects'])
        self.codex_session('sub1', {'subagent': {'other': 'guardian'}}, str(self.repo), ['assess this action'])
        self.codex_session('else', 'cli', '/elsewhere', ['other repo work'])
        data = self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False)
        self.assertEqual(sorted(r['text'] for r in data['requests']), ['make the DM route read the cache', 'ship the panel'])
        self.assertTrue(all(r['source'] == 'codex' for r in data['requests']))
        cov = data['coverage']['codex']
        self.assertEqual((cov['matched'], cov['skipped_exec'], cov['skipped_subagent']), (2, 1, 1))

    def test_commits_in_the_period_on_any_ref_with_scope_and_ref(self):
        data = self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False)
        by_subject = {c['subject']: c for c in data['commits']}
        self.assertIn('feat(likes): stand the sweep down when Skool answers 429', by_subject)
        self.assertIn('fix(approval): read a verdict written as text', by_subject)
        self.assertNotIn('chore: outside the period', by_subject)
        self.assertEqual(by_subject['fix(approval): read a verdict written as text']['ref'], 'fix/verdict')
        self.assertEqual(by_subject['feat(likes): stand the sweep down when Skool answers 429']['scope'], 'likes')
        self.assertEqual(data['coverage']['gh'], 'gh skipped by --no-gh')
        self.assertTrue(all(c['pr'] is None for c in data['commits']))

    def test_a_commit_is_linked_to_its_pr_by_title_or_head_and_then_drops_its_body(self):
        commits = [{'subject': 'feat(likes): x', 'ref': 'feat/likes', 'pr': None, 'body': 'long story'},
                   {'subject': 'test(likes): y', 'ref': 'feat/likes', 'pr': None, 'body': 'kept?'},
                   {'subject': 'docs: z', 'ref': 'main', 'pr': None, 'body': 'stays'},
                   {'subject': 'fix: w (#9)', 'ref': 'main', 'pr': 9, 'body': 'already'}]
        prs = [{'number': 138, 'title': 'feat(likes): x', 'head': 'feat/likes'}]
        self.m.link_commits_to_prs(commits, prs)
        self.assertEqual([c['pr'] for c in commits], [138, 138, None, 9])
        self.assertEqual([c['body'] for c in commits], ['', '', 'stays', 'already'])

    def test_a_stash_is_not_a_shipped_commit(self):
        """`git stash -u` writes two non-merge commits under refs/stash ('index on', 'untracked
        files on'); `--all` walks them and the report would list a stash as shipped work."""
        env = {**os.environ, 'GIT_AUTHOR_DATE': '2026-09-17T12:00:00Z', 'GIT_COMMITTER_DATE': '2026-09-17T12:00:00Z',
               'GIT_AUTHOR_NAME': 'Dev', 'GIT_AUTHOR_EMAIL': 'd@x', 'GIT_COMMITTER_NAME': 'Dev', 'GIT_COMMITTER_EMAIL': 'd@x'}
        (self.repo / 'a').write_text('changed')
        (self.repo / 'u').write_text('untracked')
        subprocess.run(['git', '-C', str(self.repo), 'stash', 'push', '-q', '-u', '-m', 'wip'], check=True, env=env)
        data = self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False)
        self.assertEqual({c['ref'] for c in data['commits']}, {'main', 'fix/verdict'})
        self.assertEqual(len(data['commits']), 2)

    def codex_rows(self, *entries):
        """A session_meta for this repo followed by rows: ('item'|'copy'|'event'|'assistant', timestamp, text).
        'item' is what a person typed, a response_item of role user; 'copy' is the event_msg
        item_completed/UserMessage Codex writes after it; 'event' is an event_msg/user_message."""
        rows = [{'timestamp': noon('2026-09-10'), 'type': 'session_meta',
                 'payload': {'id': 'rep', 'cwd': str(self.repo), 'source': 'cli', 'originator': 'x'}}]
        for kind, ts, text in entries:
            if kind in ('item', 'assistant'):
                rows.append({'timestamp': ts, 'type': 'response_item',
                             'payload': {'type': 'message', 'role': 'user' if kind == 'item' else 'assistant',
                                         'content': [{'type': 'input_text' if kind == 'item' else 'output_text', 'text': text}]}})
            elif kind == 'copy':
                rows.append({'timestamp': ts, 'type': 'event_msg',
                             'payload': {'type': 'item_completed', 'item': {'type': 'UserMessage', 'id': 'item-1',
                                                                            'content': [{'type': 'text', 'text': text}]}}})
            else:
                rows.append({'timestamp': ts, 'type': 'event_msg', 'payload': {'type': 'user_message', 'message': text}})
        write_jsonl(self.home / '.codex/sessions/2026/09/10/rollout-rep.jsonl', rows)
        return [r['text'] for r in self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False)['requests']]

    def test_codex_reads_the_typed_message_once_and_never_its_copy(self):
        """Measured on this machine (5 interactive sessions, cli_version 0.151.0 to 0.154.0-alpha):
        a typed input is one response_item of role user, and 0-6 ms later an event_msg
        item_completed/UserMessage carries the same text. The item is the ask; the copy is not read;
        an assistant message is not read; an event_msg/user_message, in no session here, neither."""
        self.assertEqual(self.codex_rows(('item', '2026-09-17T12:00:59.995Z', 'straddle'),
                                         ('copy', '2026-09-17T12:01:00.004Z', 'straddle'),
                                         ('assistant', '2026-09-17T12:01:05.000Z', 'straddle back'),
                                         ('event', '2026-09-17T12:02:00.000Z', 'only an event')), ['straddle'])

    def test_codex_keeps_every_repeat_a_person_typed(self):
        """Nothing deduplicates: the same words are another ask on another day, five minutes later,
        half a second later, and out of order; one typed before the period does not hide one inside it."""
        self.assertEqual(self.codex_rows(('item', noon('2026-09-10'), 'fix the approval flow'),
                                         ('item', noon('2026-09-17'), 'fix the approval flow')), ['fix the approval flow'])
        self.assertEqual(self.codex_rows(('item', '2026-09-17T15:00:00Z', 'continue'),
                                         ('item', '2026-09-17T15:05:00Z', 'continue'),
                                         ('item', '2026-09-17T15:05:00.500Z', 'continue'),
                                         ('item', '2026-09-17T15:04:00Z', 'continue')), ['continue'] * 4)

    def test_commits_reachable_only_from_a_remote_branch_or_a_tag_are_read(self):
        """A commit that only a remote-tracking ref or a tag still reaches is shipped work a
        deleted local branch must not hide."""
        env = {**os.environ, 'GIT_AUTHOR_DATE': '2026-09-17T12:00:00Z', 'GIT_COMMITTER_DATE': '2026-09-17T12:00:00Z',
               'GIT_AUTHOR_NAME': 'Dev', 'GIT_AUTHOR_EMAIL': 'd@x', 'GIT_COMMITTER_NAME': 'Dev', 'GIT_COMMITTER_EMAIL': 'd@x'}
        git = lambda *a: subprocess.run(['git', '-C', str(self.repo), *a], check=True, capture_output=True, env=env)
        for name, subject in (('remote-only', 'feat(dm): reachable from origin only'), ('tagged', 'feat(grants): reachable from a tag only')):
            git('checkout', '-q', '-b', name, 'main')
            (self.repo / name).write_text(name)
            git('add', name); git('commit', '-q', '-m', subject)
        git('update-ref', 'refs/remotes/origin/remote-only', 'remote-only')
        git('tag', 'v1', 'tagged')
        git('checkout', '-q', 'main'); git('branch', '-D', 'remote-only', 'tagged')
        subjects = {c['subject'] for c in self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False)['commits']}
        self.assertIn('feat(dm): reachable from origin only', subjects)
        self.assertIn('feat(grants): reachable from a tag only', subjects)

    def test_gh_reaching_its_cap_is_said_in_coverage(self):
        """gh pr list has no pagination: a read that returns exactly the cap may have dropped older
        PRs, and the evidence block must say so rather than read as complete."""
        cap = self.m.PR_LIMIT
        rows = [{'number': n, 'title': f'feat: item {n}', 'createdAt': noon('2026-09-17'), 'author': {'login': 'x'}} for n in range(cap)]
        def fake_gh(cmd, **kwargs):
            limit = int(cmd[cmd.index('--limit') + 1])
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(rows[:limit]), stderr='')
        with unittest.mock.patch.object(self.m.subprocess, 'run', side_effect=fake_gh):
            prs, note = self.m.collect_prs(self.repo, self.since, self.until)
        self.assertEqual(len(prs), cap)
        self.assertIn('cap', note)
        def fake_gh_under_cap(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(rows[:cap - 1]), stderr='')
        with unittest.mock.patch.object(self.m.subprocess, 'run', side_effect=fake_gh_under_cap):
            self.assertNotIn('cap', self.m.collect_prs(self.repo, self.since, self.until)[1])

    def skill_block(self):
        text = (ROOT / 'plugins/bymax-report/skills/standup/SKILL.md').read_text()
        import re
        return re.search(r'```bash\n(.*?)```', text, re.S).group(1)

    def run_block(self, home, args_lines):
        home.mkdir(parents=True, exist_ok=True)
        if args_lines is not None:
            (home / '.claude').mkdir(exist_ok=True)
            (home / '.claude/bymax-report-args').write_text('\n'.join(args_lines) + '\n')
        env = {**os.environ, 'HOME': str(home), 'TMPDIR': str(home / 'tmp'),
               'CLAUDE_PLUGIN_ROOT': str(ROOT / 'plugins/bymax-report')}
        (home / 'tmp').mkdir(exist_ok=True)
        return subprocess.run(['bash', '-c', self.skill_block()], cwd=str(self.repo), env=env,
                              capture_output=True, text=True)

    def test_the_skill_block_refuses_a_missing_args_file_and_runs_with_one(self):
        """The handoff file carries what the user typed; without it the block used to run the
        collect on defaults and exit 0, dropping an explicit period and author silently. The
        positive control proves the refusal is not just any refusal: with the file, the block
        runs the collect, deletes the file, and prints the temporary directory."""
        home = self.tmp / 'h1'
        missing = self.run_block(home, None)
        self.assertNotEqual(missing.returncode, 0, missing.stdout + missing.stderr)
        home2 = self.tmp / 'h2'
        with_file = self.run_block(home2, ['2026-09-14..2026-09-20', str(self.repo), ''])
        self.assertEqual(with_file.returncode, 0, with_file.stdout + with_file.stderr)
        self.assertFalse((home2 / '.claude/bymax-report-args').exists())
        work = with_file.stdout.strip().splitlines()[-1]
        self.assertTrue((Path(work) / 'collect.json').exists(), with_file.stdout)
        self.assertIn('(2026-09-14 .. 2026-09-20)', with_file.stdout)

    def git_in_repo(self, *args, **env):
        base = {**os.environ, 'GIT_AUTHOR_DATE': '2026-09-17T12:00:00Z', 'GIT_COMMITTER_DATE': '2026-09-17T12:00:00Z',
                'GIT_AUTHOR_NAME': 'Dev', 'GIT_AUTHOR_EMAIL': 'd@x', 'GIT_COMMITTER_NAME': 'Dev', 'GIT_COMMITTER_EMAIL': 'd@x'}
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True, text=True, env={**base, **env})

    def commit_on(self, branch, subject, start='main'):
        """One commit on its own branch, so each case can choose what reaches it afterwards."""
        self.git_in_repo('checkout', '-q', '-B', branch, start)
        (self.repo / subject.split(':')[0].replace('/', '-').replace('(', '-').replace(')', '-')).write_text(subject)
        self.git_in_repo('add', '-A'); self.git_in_repo('commit', '-q', '-m', subject)
        sha = self.git_in_repo('rev-parse', 'HEAD').stdout.strip()
        self.git_in_repo('checkout', '-q', 'main')
        return sha

    def shipped_by_subject(self, **kw):
        data = self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False, **kw)
        return {c['subject']: c['shipped'] for c in data['commits']}, data

    def test_only_what_reached_the_default_branch_counts_as_shipped(self):
        """Reachability from any ref is not delivery: an open branch, a tag on it and a
        remote-tracking copy of it are all reachable and none of them shipped. What decides is
        ancestry of the branch the repository delivers on, so a feature branch merged into it
        counts even after its own ref is deleted, and the same commit that did not count
        before the merge counts after it, with nothing else changed."""
        self.commit_on('feat/open', 'feat(dm): still in flight')
        self.commit_on('feat/tagged', 'feat(grants): only a tag reaches it')
        self.git_in_repo('tag', 'v2', 'feat/tagged')
        self.commit_on('feat/remote-only', 'feat(likes): only a remote ref reaches it')
        self.git_in_repo('update-ref', 'refs/remotes/origin/remote-only', 'feat/remote-only')
        self.git_in_repo('branch', '-D', 'feat/remote-only')
        self.commit_on('feat/merged', 'feat(replies): merged before the report ran')
        shipped, data = self.shipped_by_subject()
        self.assertIs(shipped['feat(replies): merged before the report ran'], False)
        self.git_in_repo('merge', '-q', '--no-ff', '-m', 'merge', 'feat/merged')
        self.git_in_repo('branch', '-D', 'feat/merged')
        shipped, data = self.shipped_by_subject()
        self.assertIs(shipped['feat(replies): merged before the report ran'], True)
        self.assertIs(shipped['feat(likes): stand the sweep down when Skool answers 429'], True)
        self.assertIs(shipped['feat(dm): still in flight'], False)
        self.assertIs(shipped['feat(grants): only a tag reaches it'], False)
        self.assertIs(shipped['feat(likes): only a remote ref reaches it'], False)
        self.assertEqual(data['coverage']['delivery_ref'], 'main')
        self.assertEqual(data['coverage']['commits_shipped'], 2)

    def test_what_the_delivery_branch_reached_only_afterwards_did_not_ship_in_the_period(self):
        """Ancestry asked now answers a different question from the one a period report asks.
        A commit authored inside the week and merged the week after had not shipped in it, and
        the pull request half of this collector already said so. The tip is followed by first
        parent because a date walk descends into a merge's second parent and hands back a
        commit that was never on the delivery branch — which would mark itself shipped."""
        early = 'feat(early): merged inside the week'
        self.commit_on('feat/early', early)
        self.git_in_repo('merge', '-q', '--no-ff', '-m', 'merged in the period', 'feat/early')
        # Dated after everything the delivery branch itself holds in the period, so a walk that
        # descends into the merge's second parent hands this commit back as the tip and it then
        # marks itself shipped. That is what --first-parent is for, and what this case pins.
        subject = 'feat(late): merged the week after'
        self.git_in_repo('checkout', '-q', '-B', 'feat/late', 'main')
        (self.repo / 'late').write_text(subject)
        self.git_in_repo('add', '-A')
        self.git_in_repo('commit', '-q', '-m', subject,
                         GIT_AUTHOR_DATE='2026-09-19T12:00:00Z', GIT_COMMITTER_DATE='2026-09-19T12:00:00Z')
        self.git_in_repo('checkout', '-q', 'main')
        self.git_in_repo('merge', '-q', '--no-ff', '-m', 'merged after the period', 'feat/late',
                         GIT_AUTHOR_DATE='2026-09-25T12:00:00Z', GIT_COMMITTER_DATE='2026-09-25T12:00:00Z')
        shipped, data = self.shipped_by_subject()
        self.assertIs(shipped[early], True)
        self.assertIs(shipped[subject], False)
        self.assertIs(shipped['feat(likes): stand the sweep down when Skool answers 429'], True)

    def fast_forwarded_repo(self, keep_reflog=True):
        """A delivery branch advanced by fast-forward after the period: no merge object is
        created and no date is stamped, so the branch commit still carries its own date."""
        repo = self.tmp / ('ff' if keep_reflog else 'ff-bare') / 'app'; repo.mkdir(parents=True)
        env = {**os.environ, 'GIT_AUTHOR_NAME': 'Dev', 'GIT_AUTHOR_EMAIL': 'd@x',
               'GIT_COMMITTER_NAME': 'Dev', 'GIT_COMMITTER_EMAIL': 'd@x'}
        def git(*args, when=None):
            extra = {'GIT_AUTHOR_DATE': when, 'GIT_COMMITTER_DATE': when} if when else {}
            subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, env={**env, **extra})
        git('init', '-q', '-b', 'main')
        git('commit', '-q', '--allow-empty', '-m', 'chore: base', when='2026-09-15T12:00:00Z')
        git('checkout', '-q', '-b', 'feat/ff')
        git('commit', '-q', '--allow-empty', '-m', 'feat(ff): fast-forwarded after the week', when='2026-09-17T12:00:00Z')
        git('checkout', '-q', 'main')
        git('merge', '-q', '--ff-only', 'feat/ff')
        if not keep_reflog:
            for log in (repo / '.git/logs').rglob('*'):
                if log.is_file():
                    log.unlink()
        return repo.resolve()

    def test_a_fast_forward_after_the_period_did_not_ship_in_it(self):
        """A fast-forward moves a branch without creating an object or stamping a date, so the
        branch's position cannot be reconstructed from commit dates: the commit still looks like
        the tip of the week it was written in. Git does record the move, in the reflog, and
        `<ref>@{<date>}` is that record — the one question that answers where a ref stood."""
        data = self.m.collect(self.fast_forwarded_repo(), self.since, self.until, self.home, use_gh=False)
        self.assertEqual([(c['subject'], c['shipped']) for c in data['commits']],
                         [('chore: base', True), ('feat(ff): fast-forwarded after the week', False)])
        self.assertIn('reflog', data['coverage']['shipped'])

    def repo_whose_reflog_starts_after_the_period(self):
        """A reflog that exists and begins too late: the entry is stamped when the commit was
        made, so a commit written during the week and committed after it leaves nothing on
        record for the week. Git answers the question anyway, with its oldest entry and a
        warning, which is the shape that reads as an answer and is not one."""
        repo = self.tmp / 'late-reflog' / 'app'; repo.mkdir(parents=True)
        env = {**os.environ, 'GIT_AUTHOR_NAME': 'Dev', 'GIT_AUTHOR_EMAIL': 'd@x',
               'GIT_COMMITTER_NAME': 'Dev', 'GIT_COMMITTER_EMAIL': 'd@x',
               'GIT_AUTHOR_DATE': '2026-09-17T12:00:00Z', 'GIT_COMMITTER_DATE': '2026-09-25T12:00:00Z'}
        for args in (('init', '-q', '-b', 'main'),
                     ('commit', '-q', '--allow-empty', '-m', 'feat(x): written in the week, committed after it')):
            subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, env=env)
        return repo.resolve()

    def test_when_the_reflog_cannot_answer_the_commit_dates_do_and_say_so(self):
        """Two ways the record is missing: no reflog at all, which is a fresh clone or an
        expired one, and a reflog that begins after the period, where git answers with its
        oldest entry and a warning. Both fall back to the commit dates, which cannot see a
        fast-forward, and the file says which question was answered rather than implying the
        stronger one."""
        for name, repo in (('no reflog', self.fast_forwarded_repo(keep_reflog=False)),
                           ('a reflog that begins too late', self.repo_whose_reflog_starts_after_the_period())):
            with self.subTest(case=name):
                data = self.m.collect(repo, self.since, self.until, self.home, use_gh=False)
                self.assertEqual(data['coverage']['delivery_ref'], 'main')
                self.assertIn('commit dates', data['coverage']['shipped'])
                self.assertNotIn('reflog', data['coverage']['shipped'])

    def test_a_file_named_like_a_commit_does_not_void_the_week(self):
        """The ancestry query hands git commit ids, and an untracked file named with one of their
        abbreviations makes it refuse — which left every commit undecided and, because the skill
        reads a null delivery ref as 'write no UPDATES', threw away the pull requests too."""
        # main's tip is the commit outside the period, which the query never names; the file
        # has to carry the abbreviation of a commit the query does hand git.
        collected = self.git_in_repo('rev-parse', '--short=12', 'main~1').stdout.strip()
        (self.repo / collected).write_text('a fixture named after a hash')
        shipped, data = self.shipped_by_subject()
        self.assertEqual(data['coverage']['delivery_ref'], 'main')
        self.assertIs(shipped['feat(likes): stand the sweep down when Skool answers 429'], True)

    def test_a_file_named_like_the_branch_does_not_break_the_fallback(self):
        """The reflog question is untouched by a path of the same name, so only the fallback
        needs the separator — and only a repository whose reflog cannot answer reaches it."""
        repo = self.repo_whose_reflog_starts_after_the_period()
        (repo / 'main').write_text('a compiled binary, not a branch')
        data = self.m.collect(repo, self.since, self.until, self.home, use_gh=False)
        self.assertEqual(data['coverage']['delivery_ref'], 'main')
        self.assertEqual({c['shipped'] for c in data['commits']}, {False})

    def test_a_delivery_branch_that_held_nothing_yet_shipped_nothing(self):
        """A delivery branch whose first commit lands after the period held nothing during it.
        That is an answer, not a missing one: the work had not shipped by then, and the file
        must say so rather than leave the week undecided."""
        repo = self.tmp / 'late' / 'app'; repo.mkdir(parents=True)
        env = {**os.environ, 'GIT_AUTHOR_NAME': 'Dev', 'GIT_AUTHOR_EMAIL': 'd@x',
               'GIT_COMMITTER_NAME': 'Dev', 'GIT_COMMITTER_EMAIL': 'd@x'}
        def git(*args, **extra):
            subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, env={**env, **extra})
        stamps = lambda when: {'GIT_AUTHOR_DATE': when, 'GIT_COMMITTER_DATE': when}
        git('init', '-q', '-b', 'main')
        git('commit', '-q', '--allow-empty', '-m', 'chore: main starts after the period', **stamps('2026-09-25T12:00:00Z'))
        git('checkout', '-q', '-b', 'feat/inside')
        git('commit', '-q', '--allow-empty', '-m', 'feat(x): written during the period', **stamps('2026-09-16T12:00:00Z'))
        git('checkout', '-q', 'main')
        data = self.m.collect(repo.resolve(), self.since, self.until, self.home, use_gh=False)
        self.assertEqual([(c['subject'], c['shipped']) for c in data['commits']],
                         [('feat(x): written during the period', False)])
        self.assertEqual(data['coverage']['delivery_ref'], 'main')
        self.assertIn('held nothing', data['coverage']['shipped'])

    def test_a_file_named_like_the_delivery_branch_does_not_break_the_question(self):
        """`git rev-list --before=<until> main` refuses when a path called main exists:
        'ambiguous argument'. A compiled binary in the root is the everyday case. The separator
        says the argument is a revision, and without it every commit came back undecided."""
        (self.repo / 'main').write_text('a compiled binary, not a branch')
        shipped, data = self.shipped_by_subject()
        self.assertIs(shipped['feat(likes): stand the sweep down when Skool answers 429'], True)
        self.assertEqual(data['coverage']['delivery_ref'], 'main')

    def collect_with_git_refusing(self, repo, refuse_when):
        """Run a collect where git refuses the calls this predicate picks, and nothing else."""
        real = self.m.git
        def refuse(where, *args, **kw):
            if refuse_when(args):
                raise RuntimeError('pretend git said no')
            return real(where, *args, **kw)
        with unittest.mock.patch.object(self.m, 'git', side_effect=refuse):
            return self.m.collect(repo, self.since, self.until, self.home, use_gh=False)

    def test_an_ancestry_question_git_refuses_decides_nothing_and_says_so(self):
        """Two calls can fail — where the branch stood, and what it reached — and each must end
        the same way: nothing decided, and no ref left in coverage claiming it did. The skill's
        one escape hatch reads `delivery_ref`, so a ref there with every commit undecided is how
        a report silently loses its updates, and it discards the pull requests with them. The
        first is reached only where the reflog cannot answer, which is why it gets a repository
        without one: a test that kills a call nothing runs measures nothing."""
        for name, repo, predicate in (
                ('where the branch stood', self.fast_forwarded_repo(keep_reflog=False),
                 lambda a: a[:2] == ('rev-list', '-1')),
                ('what it reached', self.repo,
                 lambda a: a and a[0] == 'rev-list' and a[1:2] != ('-1',))):
            with self.subTest(call=name):
                data = self.collect_with_git_refusing(repo, predicate)
                self.assertEqual({c['shipped'] for c in data['commits']}, {None})
                self.assertIsNone(data['coverage']['delivery_ref'])
                self.assertIn('failed', data['coverage']['shipped'])

    def test_a_repository_with_no_delivery_branch_says_it_could_not_tell(self):
        """A checkout whose default branch cannot be resolved must not call the work shipped,
        and must not call it unshipped either: the answer is that nothing decided it."""
        self.git_in_repo('checkout', '-q', '-b', 'feat/only-branch')
        self.git_in_repo('branch', '-D', 'main')
        shipped, data = self.shipped_by_subject()
        self.assertEqual(set(shipped.values()), {None})
        self.assertIsNone(data['coverage']['delivery_ref'])
        self.assertIn('no default branch', data['coverage']['shipped'])

    def test_a_pull_request_ships_when_it_merged_in_the_period(self):
        """collect_prs keeps a pull request opened in the period whether or not it merged, so
        each record says which it was; an open one is progress, never an update."""
        rows = [{'number': 1, 'title': 'feat(a): merged', 'state': 'MERGED', 'mergedAt': noon('2026-09-17'),
                 'createdAt': noon('2026-09-15'), 'author': {'login': 'dev'}},
                {'number': 2, 'title': 'feat(b): still open', 'state': 'OPEN', 'mergedAt': None,
                 'createdAt': noon('2026-09-16'), 'author': {'login': 'dev'}},
                {'number': 3, 'title': 'feat(c): closed unmerged', 'state': 'CLOSED', 'mergedAt': None,
                 'createdAt': noon('2026-09-16'), 'author': {'login': 'dev'}}]
        def fake_gh(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(rows), stderr='')
        with unittest.mock.patch.object(self.m.subprocess, 'run', side_effect=fake_gh):
            prs, _ = self.m.collect_prs(self.repo, self.since, self.until)
        self.assertEqual({p['number']: p['shipped'] for p in prs}, {1: True, 2: False, 3: False})

    def test_the_skill_block_carries_a_failed_collect_and_leaves_nothing_behind(self):
        """A collect that cannot run left the block at exit 0 printing a directory with no
        collect.json in it, so the reader took that path for a successful collection and the
        directory stayed on disk. The positive control is the other half: a collect that runs
        still gets its directory and its zero, so the refusal is this failure and not any failure."""
        home = self.tmp / 'h3'
        bad = self.run_block(home, ['7d', '/no/such/repo', ''])
        self.assertNotEqual(bad.returncode, 0, bad.stdout + bad.stderr)
        self.assertEqual(sorted((home / 'tmp').glob('bymax-report.*')), [])
        home2 = self.tmp / 'h4'
        good = self.run_block(home2, ['2026-09-14..2026-09-20', str(self.repo), ''])
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        made = sorted((home2 / 'tmp').glob('bymax-report.*'))
        self.assertEqual(len(made), 1, made)
        self.assertTrue((made[0] / 'collect.json').exists())

    def test_the_cli_writes_one_record_per_line_and_a_summary(self):
        write_jsonl(self.home / '.claude/projects' / self.slug / 's.jsonl', [self.claude_line('ask')])
        out = self.tmp / 'out' / 'collect.json'
        result = subprocess.run([sys.executable, str(SCRIPT), '--repo', str(self.repo), '--period', 'last-week',
                                 '--today', '2026-09-21', '--no-gh', '--home', str(self.home), '--out', str(out)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('2 commits, 0 PRs, 1 requests (2026-09-14 .. 2026-09-20)', result.stdout)
        text = out.read_text()
        data = json.loads(text)
        self.assertEqual(data['period'], {'since': '2026-09-14', 'until': '2026-09-20', 'author': None})
        record_lines = [l for l in text.splitlines() if l.startswith('    {')]
        self.assertEqual(len(record_lines), len(data['commits']) + len(data['prs']) + len(data['requests']))

    def test_author_keeps_one_person_by_name_or_email_and_never_filters_the_asks(self):
        """Two people commit; the standup is one person's. The sessions on this machine are
        already that person's, so an author filter that dropped them would empty PROGRESS."""
        env = {**os.environ, 'GIT_AUTHOR_DATE': '2026-09-17T12:00:00Z', 'GIT_COMMITTER_DATE': '2026-09-17T12:00:00Z',
               'GIT_AUTHOR_NAME': 'Other Person', 'GIT_AUTHOR_EMAIL': 'other@x', 'GIT_COMMITTER_NAME': 'Other Person', 'GIT_COMMITTER_EMAIL': 'other@x'}
        (self.repo / 'd').write_text('4')
        subprocess.run(['git', '-C', str(self.repo), 'add', 'd'], check=True, env=env)
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-q', '-m', 'feat(dm): by someone else'], check=True, env=env)
        write_jsonl(self.home / '.claude/projects' / self.slug / 's.jsonl', [self.claude_line('ask')])
        everyone = self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False)
        self.assertEqual(len(everyone['commits']), 3)
        for needle in ('dev', 'd@x', 'DEV'):
            with self.subTest(needle=needle):
                one = self.m.collect(self.repo, self.since, self.until, self.home, use_gh=False, author=needle)
                self.assertEqual({c['author'] for c in one['commits']}, {'Dev'})
                self.assertEqual(len(one['commits']), 2)
                self.assertEqual([r['text'] for r in one['requests']], ['ask'])
                self.assertEqual(one['period']['author'], needle)
        prs = [{'number': 1, 'author': 'maxsalvatti'}, {'number': 2, 'author': 'someone'}]
        self.assertEqual([p['number'] for p in self.m.by_author(prs, 'MAX', 'author')], [1])

    def test_a_bad_period_exits_two_with_the_reason(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--repo', str(self.repo), '--period', 'lastweek', '--no-gh'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('unknown period', result.stderr)


if __name__ == '__main__':
    unittest.main()
