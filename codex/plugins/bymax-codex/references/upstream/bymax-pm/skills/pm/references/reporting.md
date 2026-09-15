# Reporting

The human should get exactly what they need to steer — never the raw message
traffic. Every report is assembled from the board and live evidence, not from
memory of the conversation.

## Answering "status?" / "what's happening?"

```
PROJECT HEALTH — <ON_TRACK | AT_RISK | BLOCKED | COMPLETE>

In progress   TASK-021  nest-logger      redaction perf — checkpoint 1 passed
              TASK-023  frontend         error boundary rollout — started today
In review     TASK-019  backend-template awaiting reviewer (sent 2h ago)
Blocked       TASK-025  nest-observability — waiting on TASK-021 API contract
Verified today TASK-016 CI pipeline fix — merged, checks green
Decisions needed  none  (or the DECISION NEEDED block from escalation.md)
Risks         nest-logger↔observability API compatibility — mitigation: contract test in TASK-025
Next          finish TASK-021 → unblock TASK-025 → integration verification
```

Rules:
- Health state first, always. The human may read only that line.
- Every claim traceable to a task ID; every "verified" backed by Gate 6.
- Blocked items name what unblocks them, not just that they are blocked.
- "Decisions needed" is the human's action list — keep it honest and short.
- No agent message quotes, no play-by-play, no praise inflation.

## Health criteria (objective, not vibes)

Evaluate top-down and report the **first** state whose criteria hold — the order
is the precedence, so two PMs reading the same board reach the same answer:

| State | Criteria |
| --- | --- |
| COMPLETE | every task for the stated goal DONE; release readiness satisfied |
| BLOCKED | nothing on the critical path can move without a human decision or external event |
| AT_RISK | a critical-path task blocked or stuck, a HIGH/CRITICAL risk without mitigation, or verification debt piling up (> 2 tasks stuck in REVIEW/VERIFICATION) |
| ON_TRACK | none of the above |

State the criterion that produced the state: "AT_RISK — TASK-021 stuck 2 days on
the critical path", never a bare label.

## Session report (end of a working session / on request)

```
SESSION REPORT — <date>

Done & verified:   <task — one line each, with the closing evidence link>
Progressed:        <task — what moved, what remains>
Blocked/stuck:     <task — cause, action taken, what would unblock>
Discoveries:       <accepted into the board as TASK-nnn / logged and deferred>
Decisions made:    DEC-nnn <one line each>   Decisions needed: <or none>
Failed attempts:   <only if instructive — what was tried and ruled out>
Agent roster:      <changes only: appeared, went silent, reassigned>
Next actions:      <ordered, each with an owner>
Your actions:      <what only the human can do, or "none">
```

## Answering "can we release?"

Run the release-readiness checklist in `lifecycle.md` live — check CI now, check
task states now — and answer yes/no **with the evidence attached**. A release
answer older than the latest push to any involved repo is stale; say so and
re-check rather than repeating it.

## Cadence

- Answer direct questions immediately, from the board + a live reconciliation pass.
- Volunteer a report when: health state changes, a P0/P1 appears, a decision
  becomes needed, or a milestone completes. Otherwise stay quiet — an unprompted
  hourly "all fine" report trains the human to skim.
- Never report an agent's claim as fact before Gate 6; say "claimed complete,
  verifying" when the distinction matters.
