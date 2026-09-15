# Persistence, Startup, Recovery

The project truth must survive the PM's context window, a compaction, a crash, and
a machine restart. **Conversation is cache; the workspace and the repositories are
the record.** Any fact worth acting on tomorrow is written down today.

## Workspace layout

Created at `.claude/pm/` inside the PM session's working directory — a dedicated
coordination directory (see the README), never inside a worker's repository.

```
.claude/pm/
  board.md          index — one line per active task; the at-a-glance state
  tasks/TASK-NNN.md one file per task: contract, ack, checkpoints, evidence, gates
  roster.md         agents: responsibility, repos, current assignment, last contact
  decisions.md      append-only decision log (format in escalation.md)
  activity.md       append-only event log — one dated line per state change
```

Rules that keep it trustworthy:

- **Single writer.** Only the PM writes here. Workers report via messages; the PM
  records. Two writers on coordination files is how boards silently fork.
- **The PM never modifies a worker repository's working tree, branches, or
  history.** Inspect freely (`git -C`, `gh`) — `git fetch` (remote-tracking refs
  only) and a disposable verification worktree (`git worktree add` at a claimed
  SHA, removed afterwards; Gate 3 in `lifecycle.md`) are part of reading, since
  neither touches the worker's own checkout, branches, or history — and delegate
  all real modifications. The board is the PM's blast radius.
- `board.md` is a living index, rewritten as state changes. `tasks/`, `decisions.md`
  and `activity.md` are append-oriented — history is never edited, corrections are
  new entries.
- Index, don't mirror: the board stores task state and pointers (branch, PR number,
  commit SHA), never copies of diffs, CI logs or message threads. GitHub already
  stores those; duplicating them guarantees staleness.
- Timestamps are absolute — a date, plus the time whenever a duration depends on
  it (the silent-peer deadline) — never "today" or "2h ago".
- No secrets, tokens, or credentials — ever. The workspace is git-friendly and may
  be committed or shared.

## board.md format

```
# PM Board — <project/program name>
Health: ON_TRACK          Updated: 2026-08-31

| ID | State | Owner | Repo | Pri | Risk | Note |
| --- | --- | --- | --- | --- | --- | --- |
| TASK-021 | IN_PROGRESS | nest-logger | nest-logger | P1 | HIGH | checkpoint 1 ok |
| TASK-025 | BLOCKED (was READY) | nest-observability | nest-observability | P1 | MEDIUM | needs TASK-021 contract |

## Risks
- <open risk — mitigation or the task that carries it>

## Dependencies
TASK-025 BLOCKED_BY TASK-021 · TASK-027 BLOCKED_BY TASK-025
```

## tasks/TASK-NNN.md format

The full contract as assigned (`task-contract.md`), then appended sections as the
task advances: `## Ack` (owner's summary), `## Checkpoints` (dated status notes),
`## Evidence` (what TASK_COMPLETE delivered), `## Gates` (which passed, checked
how), `## Outcome` (VERIFIED/DONE/CANCELLED + date). One glance at the file answers
"what is this task and where does it stand" without any conversation context.

## roster.md format

```
| Agent | Responsibility | Repos | Assignment | Last contact | Notes |
| --- | --- | --- | --- | --- | --- |
| nest-logger | logging library | nest-logger | TASK-021 | 2026-08-31 | prefers small PRs |
| reviewer | independent review | all | on demand | 2026-08-31 | Gate-4 authority |
```

`Last contact` is the date of the last message either direction. An agent absent
from ListAgents keeps its row — sessions come and go; responsibility persists.

## Startup routine (every PM session start / resume)

1. Read `board.md`, `roster.md`, tail of `activity.md`, and open decisions.
2. **Reconcile against reality before acting** — the board is a snapshot, the
   repositories moved while the PM was away:
   - `ListAgents` → who is actually reachable now; update roster contact states.
     If a task file records a pending cancellation and its former owner is back
     in the listing, send `CANCEL_TASK` before any other message. Review
     `STALE`-marked roster rows: a returned owner may resume only under a fresh
     assignment.
   - For every ASSIGNED/ACKNOWLEDGED/IN_PROGRESS task: check the branch/PR
     (`git -C <repo> fetch && git -C <repo> log`, `gh pr view`) — did work land that the
     board does not know? Did nothing land where the board says IN_PROGRESS?
   - For every REVIEW/VERIFICATION task: is the evidence still valid (new pushes
     invalidate old review)?
3. Rebuild the operating picture from the delta — **re-plan from current state,
   never restart the plan**. Mark discrepancies in `activity.md`.
4. Contact only the agents whose state is ambiguous, one message each. Do NOT blast
   "status?" to every agent on startup — reconciliation from git/gh answers most
   questions without spending anyone's attention.

## Shutdown / handoff

Before ending a session (or when context feels heavy): bring `board.md` current,
append a `## Handoff` note to `activity.md` — active assignments, in-flight
messages awaiting replies, idle-notice subscriptions that will die with the session
(they are session-scoped — a resumed PM must re-subscribe), and the next three
actions. A new PM session running the startup routine on these files must be able
to continue without asking the human "where were we?".

## Failover truth hierarchy

When records disagree, trust in this order — and record the correction:

1. **Repositories / CI / PRs** — implementation and delivery truth.
2. **Live agent state** — what a worker says it is doing right now.
3. **PM workspace** — coordination truth, but a snapshot.
4. Conversation memory — last, always.

A board that says IN_PROGRESS while the PR merged yesterday is corrected from git,
not defended. Stale PM state confidently acted on is worse than no state.
