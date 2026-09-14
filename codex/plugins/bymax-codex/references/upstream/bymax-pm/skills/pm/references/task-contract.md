# Task Contract

Every delegated task is a contract, not a chat request. The contract is what makes
completion checkable: without acceptance criteria and required evidence written down
*before* work starts, "done" is an opinion.

## Sizing rule

A task should be the smallest unit that is **independently verifiable**: one owner, one
repository, one reviewable change, evidence that can be checked without reading the
worker's mind. If the contract needs three unrelated acceptance criteria, it is three
tasks. Oversized tasks hide progress, block reviewers, and turn every status question
into an essay — decompose first, delegate second.

## Contract template

Send this as the body of a `TASK_ASSIGN` message (envelope format in
`peer-protocol.md`). Omit rows that genuinely do not apply; never omit Acceptance
criteria, Required evidence, or Out of scope.

```
TASK_ASSIGN TASK-042 — <one-line imperative title, self-contained>

Owner:        <agent name from ListAgents — exactly one>
Repository:   <repo path or slug>
Branch:       <branch/worktree to work on, or "create feat/<slug>">
Priority:     P0|P1|P2|P3|P4      Risk: LOW|MEDIUM|HIGH|CRITICAL

Objective:    <what must be true when this is done — outcome, not activity>
Why:          <one or two lines: the reason this matters now>
Context:      <only what the owner needs: relevant decisions (DEC-nnn), contracts,
               links, prior findings. Not the project history.>

In scope:     <bullet list>
Out of scope: <bullet list — explicit. Silence here invites scope creep.>

Depends on:   <TASK-nnn …, or "none">
Constraints:  <API stability, compat requirements, forbidden approaches, deadlines>
Likely files: <best guess of modules/files involved — helps collision detection>

Acceptance criteria:
- <objective, checkable statements — each one testable by someone other than the owner>

Required verification:  <what must run green: typecheck, lint, unit, integration,
                         build, project gates — name the actual commands when known>
Required evidence:      <what to send back with TASK_COMPLETE: branch + commit SHA,
                         diff summary, test output tail, PR URL, CI link>

Checkpoints:  <when to send TASK_STATUS unprompted — e.g. "after the audit, before
               changing any export" or "if not complete within this session">
Blockers:     <conditions that require a BLOCKER message instead of improvisation —
               e.g. "any change to a public export", "a failing test you did not cause">

Reply with TASK_ACK TASK-042: your understanding of the goal, planned approach,
files you expect to touch, dependencies or unknowns you see, and whether you are
ready to start. [HIGH/CRITICAL only:] Do not implement until you receive
PLAN_APPROVED.

Then, throughout the task — always replying to this message's `from` address,
first line starting with the message type and task id exactly as shown:
- TASK_STATUS TASK-042 — at each checkpoint above: progress, evidence so far,
  on-track or drifting, next step
- BLOCKER TASK-042 — the moment a blocker condition above occurs: what and why,
  evidence, what you attempted, who can unblock
- TASK_COMPLETE TASK-042 — when finished: the Required evidence, item by item
```

The closing instructions are not politeness — peers have not loaded this skill, so
**every message must carry its own reply instructions**, for the whole lifecycle,
not just the acknowledgement. A contract without them gets free-form or misrouted
answers the board cannot track.

## Acknowledgement (TASK_ACK)

The acknowledgement is the cheapest defect detector in the whole system: a wrong
understanding costs one message to fix now and a rewritten implementation later.
Require, in the worker's own words:

- **Goal restated** — if the restatement is wrong, stop and correct it.
- **Approach** — enough to spot a doomed direction before code exists.
- **Files/areas expected** — feeds collision detection (`multi-repo.md`).
- **Dependencies and unknowns** — anything the worker needs that the contract missed.
- **Ready / not ready** — "not ready" plus a reason is a good acknowledgement.

State moves ASSIGNED → ACKNOWLEDGED only when the ack shows understanding, not merely
receipt. A bare "ok, starting" is receipt — ask for the missing pieces once, then
treat repeated bare acks as a stuck signal.

## Plan approval — HIGH and CRITICAL risk

For HIGH and CRITICAL tasks the ack doubles as a plan proposal, and the worker must
wait for `PLAN_APPROVED` before implementing. The PM reviews the proposed approach
against: system-wide impact, the decision log, API/contract stability, and migration
order. Approve, correct, or escalate — but answer quickly; an unanswered plan
approval is a PM-caused blocker.

## Risk classification

Risk decides how much verification a task must buy. Classify at assignment time;
re-classify if scope reveals more.

| Level | Typical territory | Extra requirements |
| --- | --- | --- |
| LOW | docs, tests, internal refactor with no exported-surface change | evidence + PM verification |
| MEDIUM | new features behind existing contracts, bug fixes touching shared code | + independent review (Gate 4) |
| HIGH | public API changes, shared libraries, DB schema/migrations, auth-adjacent code, CI/CD pipelines, cross-repo contracts | + plan approval before implementation, + review is mandatory, + Gate 5 integration validation when the effects cross a repository boundary (`lifecycle.md`) |
| CRITICAL | authentication/authorization, payments, security boundaries, destructive/irreversible operations, backwards-compatibility breaks | everything HIGH requires, + a second specialised reviewer (security/architecture), + explicit human sign-off before merge |

Anything touching secrets, credentials, or data deletion is CRITICAL by default and
can only be downgraded by a logged decision.

## Priority model

| Priority | Meaning |
| --- | --- |
| P0 | production down, security incident, data loss — preempts everything |
| P1 | release blocker or major defect on the critical path |
| P2 | important planned work — the default for roadmap tasks |
| P3 | improvement; scheduled when it does not displace P2 |
| P4 | backlog; assigned only to otherwise-idle agents |

Priority orders the queue; risk sizes the gates. A P4 task can be CRITICAL risk
(a small change to auth code) and a P0 can be LOW risk (revert a bad config). Never
conflate the two.
