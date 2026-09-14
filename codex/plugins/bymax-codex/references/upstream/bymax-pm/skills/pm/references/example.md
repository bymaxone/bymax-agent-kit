# Worked Example

Sessions running (each started by the human in its own terminal):
`pm` · `nest-logger` · `nest-observability` · `backend-template` · `reviewer`.

The human tells the PM:

> "We need to prepare nest-logger for the new nest-observability package and ensure
> backend-template can consume both safely."

## 1 — Inspect before decomposing

The PM reads, delegates nothing yet: `ListAgents` (all four workers reachable),
the three repositories (`git -C … log`, exported surfaces, versions,
`backend-template`'s dependency manifest), and the decision log. Finding: nest-logger
exposes a transport interface nest-observability will need to hook; its shape is the
coupling point.

## 2 — Decompose along the seam

The contract-first split (see `multi-repo.md`, partial unblocking):

| ID | Owner | Task | Depends on | Risk |
| --- | --- | --- | --- | --- |
| TASK-021 | nest-logger | audit + publish the transport contract (types only, no impl) | — | HIGH (public API) |
| TASK-022 | nest-logger | implement the contract changes behind the published types | 021 | MEDIUM |
| TASK-025 | nest-observability | build the package against TASK-021's contract | 021 | MEDIUM |
| TASK-027 | backend-template | consume both; integration + contract tests | 022, 025 | HIGH (cross-repo contract) |

TASK-021 is deliberately tiny: it unblocks 025 without waiting for 022.

## 3 — Assign with contracts

`TASK_ASSIGN TASK-021 — publish the nest-logger transport contract` goes to
`nest-logger` with the full template: objective, out of scope ("no implementation,
no version bump yet"), acceptance criteria ("types compile, exported from the
package root, documented"), required evidence (branch, SHA, type-check run), and —
HIGH risk — "reply with TASK_ACK; do not implement until PLAN_APPROVED."

The ack proposes extending an existing interface instead of adding a new one. The
PM checks the consumer impact (breaking for one method) → answers with a
correction, worker adjusts, `PLAN_APPROVED`. Board: ACKNOWLEDGED → IN_PROGRESS.
The PM subscribes for an idle notice (`notify_when_idle: true`, no body) instead
of asking for status later.

## 4 — Contract lands, dependents unblock

Idle notice arrives; nest-logger sends `TASK_COMPLETE TASK-021` with branch, SHA,
type-check output. PM verifies (Gate 2/3: commit exists, diff is types-only,
check green), sends `REVIEW_REQUEST` to `reviewer` (Gate 4 — HIGH risk). Reviewer
approves with one naming finding; worker fixes; reviewer re-approves. Gate 5
(021 is HIGH): no consumer exists yet, so the PM performs the smallest real
integration read a types-only contract permits — compile-checking a throwaway
consumer stub against the published types in a scratch directory. PM runs
Gate 6, marks 021 VERIFIED, and in the same turn:

- `TASK_ASSIGN TASK-025` → nest-observability (now READY),
- `TASK_ASSIGN TASK-022` → nest-logger,
- `DEPENDENCY_UPDATE` → backend-template: "transport contract published at
  <SHA>; TASK-027 lands after 022+025; nothing for you yet, heads-up only."

022 and 025 run in parallel — different repos, no collision (checked: no shared
files, no shared migration chain).

## 5 — A discovery, routed not self-fixed

Mid-task, nest-observability reports `DISCOVERY — nest-logger's shutdown hook
swallows errors; affects my flush guarantee. Severity: medium. Evidence:
file:line. Suggested owner: nest-logger.` The PM does not let the discoverer
patch nest-logger: it becomes TASK-026 (owner nest-logger, MEDIUM), RELATED_TO 025
on the board, and the discoverer continues its own contract.

## 6 — Integrate, verify, report

022 and 025 complete → reviewed → verified. TASK-027 becomes READY;
backend-template consumes both packages, adds contract tests, reports evidence
(branch, test run, CI link). Gate 5: the PM checks the seam itself — consumer CI
green against the real published versions, contract tests failing on a deliberate
type break (proof they bite). VERIFIED → DONE as each PR merges.

To the human:

```
PROJECT HEALTH — ON_TRACK
Done & verified  TASK-021/022 nest-logger contract + impl · TASK-025 observability pkg
                 TASK-026 shutdown-hook fix (found by observability, fixed by logger)
In progress      TASK-027 backend-template integration — contract tests green, PR in CI
Decisions needed none  (DEC-017 logged: extend transport interface, not add a second one)
Next             merge TASK-027 → release readiness check on all three repos
```

Total human involvement after the kickoff: zero decisions, one report.
