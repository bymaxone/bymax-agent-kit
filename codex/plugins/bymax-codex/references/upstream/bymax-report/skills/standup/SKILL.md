---
name: standup
description: 'Write the weekly silent-standup report for one repository: a PROGRESS list of what was asked in the period, and UPDATES grouped by area saying what shipped and what it replaced. Every line traces to a pull request, a commit or a request a person typed into a Claude Code or Codex session; nothing is written from memory. Output is plain text to paste, in English unless another language is asked for, printed in the reply with its evidence below it; no file is left on disk. Arguments: a period (default last week: Monday to Sunday), an optional repository path, an optional --author to keep one git author, an optional --lang. Triggers: "standup", "weekly report", "silent standup", "what did we ship", "relatório da semana", "report da semana", "/bymax-report:standup".'
user-invocable: true
argument-hint: "[last-week|this-week|<n>d|YYYY-MM-DD..YYYY-MM-DD] [--repo <path>] [--author <name-or-email>] [--lang <code>]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Grep
  - Glob
---

# /bymax-report:standup — the week, as the team reads it

Produce the two sections a silent standup carries for one repository and one period:

```
PROGRESS (from last week)
- <what was asked, as one outcome sentence>
- <what was asked and is still open> (in progress)

UPDATES:
<Area>
- <what changed>; <what it used to do, or why it mattered>
```

The reader is the team, not the engineer: coaches, a community manager, a founder.
They do not read commit hashes or PR numbers, and the report never shows them. The
author does, so the evidence is printed under the report in the reply, never in it.

Nothing is left on disk. The collect writes one temporary file, read once and deleted
in the same run; the report and its evidence exist only in the reply.

The report is plain text, not Markdown: the author pastes it into a document that
does its own checkboxes, strikethrough and bold. So no `- [x]`, no `~~`, no `**`,
no `#` headings. A line starts with `- ` when it is an item and with nothing when
it is a section title or an area name.

## Arguments

`$ARGUMENTS` is zero or more tokens, in any order:

- a period: `last-week` (default; the previous Monday through Sunday), `this-week`,
  `<n>d` (the last n days ending today), or `YYYY-MM-DD..YYYY-MM-DD`.
- `--repo <path>`: the repository to report on. Default: the current one. The report
  is always for one repository; run the skill once per repository for several.
- `--author <text>`: keep only the commits whose git name or email contains the text
  and the PRs whose GitHub login does. The asks are not filtered: the sessions read
  are this machine's, so they are already one person's. Use it when several people
  commit to the repository and the standup is one person's.
- `--lang <code>`: the language of the report. Default `en`. Another language
  translates the whole report, headings included.

## Step 1 — Collect (deterministic, read-only)

First write the arguments to a file with the file tool, three lines, so a value the
user typed never becomes shell source: line 1 the period token (`last-week` when none
was given), line 2 the repository path (an absolute path, or `.` when none was given),
line 3 the author text (an empty line when none was given).

Write it into `.claude/bymax-report-args.d/` in the home directory, under **a name no
other run would pick** — the date and time to the second is enough. **Remember that
name.** Two standups at once cannot be prevented from both writing there, so the block
does not try: it refuses unless exactly one file is waiting, and it prints the name it
claimed. Check that against the name you wrote before you read anything. Then run:

```bash
ARGS_DIR="${HOME}/.claude/bymax-report-args.d"
set -- "$ARGS_DIR"/*
if [ ! -f "$1" ]; then
  echo "No arguments file in $ARGS_DIR: write one (period, repo, author) and run again." >&2
  exit 1
fi
if [ "$#" -ne 1 ]; then
  echo "$# arguments files are waiting in $ARGS_DIR, so another standup is in flight or left" >&2
  echo "one behind. Wait for it, or remove one older than fifteen minutes, and run again." >&2
  exit 1
fi
MINE="${ARGS_DIR}.claimed.$$"
mv "$1" "$MINE" 2>/dev/null || MINE=''
if [ -z "$MINE" ]; then
  echo "Another run claimed the arguments first; write yours again and run this block again." >&2
  exit 1
fi
echo "claimed $(basename "$1")"
PERIOD=$(sed -n 1p "$MINE")
REPO=$(sed -n 2p "$MINE")
AUTHOR=$(sed -n 3p "$MINE")
rm -f "$MINE"
if [ -z "$PERIOD" ] || [ -z "$REPO" ]; then
  echo "The arguments file had no period or no repository; write all three lines and run again." >&2
  exit 1
fi
WORK=$(mktemp -d "${TMPDIR:-/tmp}/bymax-report.XXXXXX") || WORK=''
if [ -z "$WORK" ] || [ ! -d "$WORK" ]; then
  echo "No temporary directory under ${TMPDIR:-/tmp}, so the collect did not run." >&2
  exit 1
fi
if ! python3 "${CLAUDE_PLUGIN_ROOT}/scripts/collect.py" --period "$PERIOD" --repo "$REPO" --author "$AUTHOR" --out "${WORK}/collect.json"; then
  rm -rf "$WORK"
  echo "The collect failed, so there is nothing to report on; the reason is above." >&2
  exit 1
fi
echo "$WORK"
```

The block prints the temporary directory only when the collect succeeded; on a failure
it removes that directory and exits nonzero, so a printed path always holds a `collect.json`.
It also stops when there is no temporary directory to make, because an unchecked `mktemp`
leaves the variable empty and the collector is then told to write `/collect.json`, outside
the run's own directory and outside its cleanup.
The collect's own line says how many commits, pull requests and requests it found and
the dates it resolved and the repository it read. **Read that line before anything
else, and check it against what you were asked for**, together with the `claimed` line
above it. The claimed name is what your run chose; the period and the repository are a
second reading, and a weaker one, since a repository written as `.` is resolved wherever
the block runs. A disagreement means you are holding another run's arguments: write
yours again and run the block again rather than reporting on the wrong repository.
Then read
`collect.json`; it is one record per line, so read it whole with the file tool.

What the file holds:

- `prs`: pull requests merged or opened in the period, with title, body, state, head
  branch and the Conventional Commits type and scope parsed from the title. `shipped`
  is true only for one that merged in the period.
- `commits`: non-merge commits in the period on any branch, remote branch or tag, with
  `pr` set when a pull request explains them and `shipped` true only when the delivery
  branch had reached them by the end of the period. `coverage.shipped` names the record
  that decided it: the branch's reflog, which sees a branch moved without a merge, or
  its commit dates, which cannot. A commit with `pr: null` is one no
  pull request explains, which is not the same as one that shipped; its body is kept.
  `shipped: null` means nothing decided what shipped, and `coverage.shipped` says why.
- `requests`: what a person typed into Claude Code or Codex on this repository in
  the period, dated to the minute, with the git branch a Claude session was on.
  Pasted text from a third party — a client's message, a bug report — is a request
  too; it was put in the session so the work would be done.
- `coverage`: what was read and what was not. `gh` says whether pull requests were
  read at all. `codex.matched` counts the interactive Codex sessions of this repo.

If `coverage.gh` says gh failed, is missing or reached its cap, the evidence says so
and UPDATES is built from what was read. If `coverage.delivery_ref` is null, nothing
decided what shipped: write no UPDATES section, say what `coverage.shipped` says, and
keep the period's work in PROGRESS. If `requests` is empty, PROGRESS cannot be
written: remove the temporary directory the collect printed, say so, and stop rather
than inventing the week's asks from the commits.

## Step 2 — PROGRESS: the asks, as outcomes

A progress item is **what was asked, rewritten as the outcome it asked for**, in one
sentence, imperative, in the reader's words. The images this format was taken from
read: "Let the coach say why they edited, in one tap, and act on it immediately",
"Fix the prompt cache so the DM route reads instead of only writing".

Build the list from `requests`:

1. **Cluster** the requests into asks. One ask often spans several sessions and
   many messages: the opening message states it, follow-ups steer it ("faça as 3",
   "corrija como recomendou", "fiz o deploy, verifique"). Group by branch first, then
   by subject. Steering messages, status questions ("qual status?") and
   acknowledgements are not asks; they attach to the ask they steer.
2. **Drop** what is not the team's business: questions about tooling, the review
   plugin, credits, or this skill itself, unless the repository *is* the tooling.
3. **Write** each ask as one outcome sentence. Name the thing the reader knows
   (the approver, the DM route, Pearl, the like sweep), not the code (`approval.ts`,
   `classifier`). Translate a Portuguese request into English; keep a client's
   English wording where it is already an outcome.
4. **Mark** each ask done when a shipped pull request on the same branch or scope
   delivers it, or a shipped commit does. An ask whose only evidence is an open pull
   request or an unreached commit is still open, however much work it has behind it.
   A done item is the plain sentence;
   the author ticks it in the document. An open item ends with ` (in progress)`
   and goes last. An ask delivered partly is one open item describing what
   remains, not a done item with a caveat.
5. **Order** by the first message of each ask.

Ten to fifteen items is a normal week; forty is a list of messages, not of asks.

## Step 3 — UPDATES: what shipped, grouped by area

An update is one bullet per shipped change, grouped under an area name on its own
line, with a blank line before each area.
The area is a product name the reader uses ("Reply quality", "Reviewer workflow",
"Likes"), derived from the Conventional Commits scope but never spelled as one
(`approval` becomes "Approval flow", `dm` becomes "Direct messages"). A change that
fits no group stands alone as a bullet above the first heading, as the source format
allows ("Changed the model from Opus 5 to Fable 5.1 for reply posts").

**Only what shipped belongs here.** Build the bullets from the pull requests whose
`shipped` is true, then from the commits whose `shipped` is true that no listed pull
request already covers — a commit whose `pr` names one of those pull requests is that
same change, and a commit whose `pr` names a pull request the file does not list (the
number came from its own subject) is a bullet of its own. A pull request still open,
one closed without merging, and a commit whose `shipped` is false are work
in flight: they are evidence for a PROGRESS item that is still open, never an update.
A branch merged during the period is shipped whatever its state is now, because the
delivery branch had reached its commits by the period's end; where the merge squashed
them it had reached the squashed commit instead, and that one carries the change.

Then, over the shipped records:

1. **One PR, one bullet**, normally. Two PRs that are one change to the reader
   (a feature and its fix the same day) become one bullet; one PR that shipped two
   things the reader would list separately becomes two.
2. **Say what it does now, then what it did before or why**, when the PR body or
   the request says. "The approver reads a verdict the provider returns as plain
   text; the two most recent posts had shown 'AI scoring degraded, verify manually'."
   Skip the second half when nothing in the sources states it; do not infer one.
3. **Numbers only when the source has them** and the reader would act on them
   ("Bryan 42 positions, Jennifer 25"). No counts of commits, tests or files.
4. **Never** a hash, a PR number, a branch name, a file path, a function name, a
   test name, or the words "refactor", "regression", "flaky". A test-only or
   docs-only PR is not an update unless it changed what the reader sees.
5. **People's data stays out.** A request may carry a member's name and email; the
   report carries neither unless the standup already names that person as a case.

## Step 4 — Print the report, then the evidence, then delete the temporary file

Print the report, and only the report, inside one fenced block so it copies as
written. Under it, a second fenced block titled `Evidence` with one row per report
line, in report order, and a last row for coverage naming the delivery ref and the
shipped counts: a repository that delivers on a branch the collector did not pick is
invisible in the report itself and obvious in that row.

```
| Line | Evidence |
| PROGRESS 1 | requests 2026-09-16 18:06, 18:12 (feat/guideline-flags-reach-pearl); PR #128, #129 |
| UPDATES Likes 2 | PR #138 (a9d438e); request 2026-09-19 10:41 |
| coverage | delivery ref origin/main, 14 of 21 commits shipped, 6 of 9 PRs; gh ok; 3 Claude session dirs, 30 files; 0 Codex sessions matched, 8 exec skipped |
```

Then remove the temporary directory the collect printed, with the file tool's Bash:
`rm -rf` of that exact path and nothing wider. Nothing else in the reply: no summary
of the method, no offer, no file left behind.

## What this skill never does

- Writes a line no record in `collect.json` supports. When the sources leave a
  gap — a PR with an empty body, a request with no PR — the line says what the
  sources say and stops.
- Reads a session for another repository, or a Codex session the review plugin
  started. The collector decides that; the skill does not widen it.
- Edits the repository, commits, or touches the standup document. The output is
  text to paste; where it goes is the author's.
