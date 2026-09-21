# bymax-report

The weekly silent-standup report for one repository, written from evidence.

```
/bymax-report:standup                          # last week (Mon–Sun), current repo, English
/bymax-report:standup 2026-09-14..2026-09-20   # an explicit period
/bymax-report:standup 14d --repo ../other-repo # the last 14 days of another repo
/bymax-report:standup --lang pt                # prose in Portuguese
/bymax-report:standup --author maximiliano     # one git author's commits and PRs only
```

## What it writes

```
PROGRESS (from last week)
- Tell Pearl in Slack when a reply mentions her
- Stop the like sweep when Skool rate-limits, instead of telling the coach their browser is gone
- Score prompt changes through the production generators (in progress)

UPDATES:
Approval flow
- The approver reads a verdict the provider returns as plain text; the two most recent posts had shown "AI scoring degraded, verify manually"

Likes
- The sweep stands down when Skool answers 429, instead of telling a rate-limited coach their browser is gone
```

Plain text, not Markdown: the document it is pasted into does its own checkboxes,
strikethrough and bold.

**PROGRESS** is what was asked in the period, each ask rewritten as the outcome it
asked for, marked `(in progress)` when no pull request delivered it yet. **UPDATES** is what
shipped, one bullet per change, grouped by the product area the reader knows, each
saying what it does now and what it did before when the sources say.

The report shows no hash, PR number, branch, file or function: the reader is the
team. An evidence block printed under it maps every line to its PR, commit and
request, for the author who has to stand behind it. Nothing is written to disk: the
collect's one temporary file is deleted in the same run.

## Where the evidence comes from

`scripts/collect.py` is deterministic and read-only. It reads, for one repository
and one range of local dates:

| Source | What counts | What is skipped |
| --- | --- | --- |
| `git log --all` | non-merge commits in the period, with the branch they were reached from and their Conventional Commits type and scope; linked to a PR when the tree still says which | merge commits |
| `gh pr list` | PRs merged or opened in the period, with body and head | anything gh cannot read — recorded in `coverage.gh`, never fatal |
| `~/.claude/projects/<slug>` | lines a person typed, in sessions whose `cwd` is the repo or one of its worktrees (the `--claude-worktrees-*` sibling directories are read) | tool results, task notifications, harness-injected meta lines, compact summaries, sidechains, cross-session messages |
| `~/.codex/sessions` | user messages of interactive sessions whose `cwd` is the repo | `exec` sessions (the review plugin prompting Codex) and subagent sessions |

Text a person pasted into a session — a client's request, a bug report — is a
request too. Member names and emails in such text stay in the evidence file and
never reach the report.

The collect is usable on its own:

```bash
python3 plugins/bymax-report/scripts/collect.py --period last-week --out /tmp/week.json
python3 plugins/bymax-report/scripts/collect.py --period 2026-09-01..2026-09-07 --repo ~/src/app --no-gh
```

The output is JSON with one record per line, so it pages by line and greps by field.

## What it never does

- Write a line the collected records do not support. An empty request list means
  no PROGRESS section, said plainly, not one guessed from the commits.
- Read another repository's sessions, or a Codex session the review plugin started.
- Commit, push, or touch the standup document. The output is text to paste.

## Requirements

`git` and `python3`. `gh` (authenticated) for pull requests; without it the report
is built from commits and says so.
