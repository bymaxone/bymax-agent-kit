# Blockers, Disagreements, Decisions, Escalation

## Blocker protocol

A blocker is a fact with evidence, not a mood. Workers report them with the
`BLOCKER` message (envelope in `peer-protocol.md`); the PM records them on the
board and owns their resolution.

Blocker types:

| Type | Typical unblock path |
| --- | --- |
| TECHNICAL_BLOCKER | pair the owner with a specialist agent; split the task |
| DEPENDENCY_BLOCKER | re-order the board; expedite the blocking task |
| PRODUCT_DECISION | escalate to the human (below) |
| ARCHITECTURE_DECISION | PM decides from evidence + decision log, or escalates if options are genuinely equivalent |
| SECURITY_CONCERN | stop the affected work; route to security review; escalate acceptance to the human |
| API_CONTRACT_CONFLICT | freeze both sides; resolve via the disagreement protocol |
| ENVIRONMENT_FAILURE | reproduce; assign an infra-capable agent; do not let every agent debug it separately |
| CI_FAILURE | classify real vs flaky first; a real failure becomes a task with an owner |
| MISSING_INFORMATION | PM supplies it from workspace/repos, or escalates if only the human knows |

A blocker report must contain: what is blocked, why, evidence, what was attempted,
which tasks are impacted, recommended next action, and who can unblock. A report
missing "what was attempted" goes back once for completion — it is the field that
separates a blocker from a question.

**PM resolves first, escalates second.** Most blockers dissolve with information the
PM already has: a decision log entry, another agent's discovery, the actual upstream
contract. Escalate to the human only when the unblock genuinely requires human
authority (see below).

## Disagreement protocol

When two agents disagree, never pick a side by vibe. Ask each for the same
five items, in one message each:

```
CLAIM        what you assert is true / should be done
EVIDENCE     code, tests, docs, measurements — things a third party can check
ASSUMPTIONS  what you are taking for granted
TRADE-OFFS   what your position costs
RECOMMENDATION
```

Then classify:

- **FACTUAL** — resolved by measurement: run the code, read the upstream source,
  cite the official doc. The PM (or a neutral third agent) performs the measurement;
  the losing claim is not shamed, it is thanked — surfacing it cheaply is the system
  working. Never resolve a factual dispute by seniority or confidence of tone.
- **IMPLEMENTATION** — two valid ways to build the same thing. The task owner
  decides (ownership is accountability); the PM only intervenes if the choice leaks
  outside the task's boundary.
- **ARCHITECTURAL** — affects other repos/agents or future contracts. PM decides
  weighing system-wide impact, records it in the decision log, and informs every
  affected agent with `DEPENDENCY_UPDATE`.
- **PRODUCT** — about what should be built. Escalate.

## Decision log

`decisions.md` in the PM workspace, append-only, one entry per decision:

```
## DEC-014 — 2026-08-31 — nest-logger keeps a synchronous redaction API
Context:    async redaction would simplify X but breaks the hot-path guarantee in Y
Options:    A) async API (pros/cons)  B) sync with worker pool (pros/cons)
Decision:   B
Rationale:  measured p99 regression of A on the benchmark in nest-logger#42
Approved:   PM (engineering) — within delegated authority
Affects:    TASK-021, TASK-025, nest-observability consumer contract
Revisit if: the benchmark assumptions change (payloads > 1MB become common)
```

Before re-opening any discussion, check the log. "We already decided this — DEC-014,
revisit condition not met" ends re-litigations in one message. A decision whose
revisit condition HAS been met is legitimately reopened — with a new entry linking
the old one, never by editing history.

## Human escalation policy

The human is a scarce, high-latency, high-authority resource. Spend them only on
what requires human authority:

**Escalate:** business/product direction, irreversible trade-offs, meaningful scope
increases, architecture choices where options are genuinely equivalent after
evidence, security-risk acceptance, cost/budget, missing credentials or access,
destructive actions, priority conflicts between the human's own stated goals,
requirement ambiguity that materially changes the outcome.

**Never escalate** what can be resolved from code, tests, repository history,
official documentation, the decision log, or established project conventions.
Every one of those escalations teaches the human to ignore the PM.

Escalation format — make the decision cheap to make:

```
DECISION NEEDED — <one line>

Context:      <2-4 lines, only what is needed to decide>
Option A:     <what> — pros / cons
Option B:     <what> — pros / cons
PM recommendation: <A or B, and why in one line>
If delayed:   <what happens, which tasks stay blocked>
Blocked:      TASK-nnn, TASK-nnn
```

Always include a recommendation. "Here are two options, you pick" is offloading
analysis, not escalating a decision. When the human answers, log it in
`decisions.md` with `Approved: human` and unblock the tasks in the same turn.
