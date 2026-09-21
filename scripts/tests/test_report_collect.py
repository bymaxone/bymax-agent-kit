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
        """Measured on this machine (codex-cli 0.154.0, 5 interactive sessions): a person's input is one
        response_item of role user, and 0-6 ms later an event_msg item_completed/UserMessage carries
        the same text. The item is the ask; the copy is not read; an assistant message is not read;
        an event_msg/user_message, seen only in exec sessions of an earlier version, is not read either."""
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
