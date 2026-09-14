# Multi-Repository Coordination

A program spanning repositories (a library, its sibling, and their consumers) fails
in the seams, not in the files. The PM owns the seams.

## Dependency model

Tasks form a DAG. Record edges on the board (`Dependencies` section) using:

- `BLOCKED_BY` — cannot meaningfully start until the other task is at least
  VERIFIED (VERIFIED or DONE).
  The inverse (`BLOCKS`) is derived; record one direction only.
- `RELATED_TO` — shared context worth knowing, no ordering constraint.

Rules:
- A task is READY only when every `BLOCKED_BY` edge points at a task that is at
  least VERIFIED (VERIFIED or DONE) — claimed-complete does not unblock anyone
  (`lifecycle.md`).
- **Partial unblocking beats waiting:** if TASK-B needs only TASK-A's interface,
  not its implementation, split A into "define + publish the contract" (small,
  expedited) and "implement" — B starts against the contract. This is the single
  most effective latency reducer in cross-repo work.
- Identify the critical path when priorities compete: the chain of BLOCKED_BY edges
  with the most downstream weight gets the strongest agents and the fastest reviews.

## Repository dependency awareness

Track (a section in `board.md` or the project hub note) which repo consumes which:
`backend-template → nest-logger, nest-observability`. From it derive:

- **Change propagation** — a public-surface change in a library spawns explicit
  consumer tasks; consumers do not discover breakage by accident.
- **Release sequencing** — dependencies release before dependents; migration order
  is stated in the task contracts, not assumed.
- **Version alignment** — at release readiness, every consumer pins versions that
  actually contain the changes it needs.

## API contract changes — the standing rule

Any task that changes an exported surface (function signatures, wire formats, event
schemas, DB schemas, config shapes) must say so in its contract, and its completion
triggers `DEPENDENCY_UPDATE` messages to every consumer's owner — sent by the PM,
recorded in `activity.md`. HIGH risk by default. Prefer contract tests in the
consumer repos over documentation promises: a test fails loudly, a document rots.

## Collision detection — before parallelizing

Two tasks may run in parallel only if they do not contend. Check, in order of
expense:

1. Same repository? If no — parallel is safe from git's perspective.
2. Same branch? Two agents on one branch is a merge race — forbid; give each a
   branch or worktree.
3. Overlapping files/modules? Compare the contracts' `Likely files` (that field
   exists for this). Overlap → serialize, or re-split along the module boundary.
4. Same exported interface, schema, migration chain, shared config, or dependency
   manifest (package.json/Cargo.toml)? These collide invisibly even across files —
   the two most common: both tasks add a migration (ordering conflict), both bump
   dependencies (lockfile conflict). Serialize or pre-assign the order.

When ownership boundaries are clean (different repos, or well-separated modules),
parallelize aggressively — idle specialist agents are waste. When boundaries are
murky, one reconciliation merge costs more than the parallelism saved.

## Worktrees and branches

Never assume two sessions share a working tree. Before delegating a modification,
know where the owner works: which repo checkout, which branch, worktree or not
(`Branch:` in the contract). If two agents must touch one repo concurrently, put
them in separate worktrees/branches with the merge order decided at assignment
time, not at merge time.

## Cross-repo integration verification (Gate 5)

For HIGH+ tasks whose effects cross a repo boundary, verification includes the
other side: build the consumer against the changed library (locally-linked or a
prerelease), run the consumer's suite, run contract tests where they exist. A
library green in isolation proves nothing about the seam — the seam is what Gate 5
exists to check.
