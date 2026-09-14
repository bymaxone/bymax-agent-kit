# Task Lifecycle and Quality Gates

## States

```
BACKLOG → READY → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → REVIEW → VERIFICATION → VERIFIED → DONE
                                                 ↕            (LOW risk skips REVIEW:
                                              BLOCKED          IN_PROGRESS → VERIFICATION)
                                                              any state → CANCELLED
```

| State | Meaning — and the fact that must be true to be in it |
| --- | --- |
| BACKLOG | captured, not yet actionable (missing decomposition, decision, or dependency) |
| READY | contract complete, dependencies satisfied, an owner could start today |
| ASSIGNED | `TASK_ASSIGN` sent to exactly one owner; awaiting acknowledgement |
| ACKNOWLEDGED | owner restated the goal correctly and proposed an approach (see `task-contract.md`); a HIGH/CRITICAL task stays here until `PLAN_APPROVED` — approval gates the move to IN_PROGRESS, not this state |
| IN_PROGRESS | owner reported starting, or a checkpoint/status shows work happening |
| BLOCKED | a `BLOCKER` message is on file with cause, evidence, and what would unblock it |
| REVIEW | worker sent `TASK_COMPLETE` with evidence; an independent reviewer is examining it |
| VERIFICATION | review passed (or was waived for LOW risk); PM is checking evidence itself |
| VERIFIED | PM confirmed the evidence against the repositories — Gates 1–6 below |
| DONE | verified AND integrated (merged/released as the contract required) |
| CANCELLED | withdrawn; reason logged in `activity.md`, owner informed |

## Transition rules

- **Only the PM moves tasks between states.** Workers report events; the PM decides
  what they mean. A worker cannot self-serve into DONE.
- READY requires all `Depends on` tasks at least VERIFIED — VERIFIED or DONE,
  never merely claimed complete.
- ASSIGNED → ACKNOWLEDGED requires a real ack, not receipt (`task-contract.md`).
- `TASK_COMPLETE` from the worker moves IN_PROGRESS → REVIEW when review is required
  by risk, else directly → VERIFICATION. **It never moves anything to DONE.**
- REVIEW → IN_PROGRESS when the reviewer requests changes (same owner, same task —
  do not mint a new task for review fixes).
- BLOCKED is orthogonal: any active state can enter it and returns to the state it
  left. Record both on the board (`BLOCKED (was IN_PROGRESS)`).
- CANCELLED requires notifying the owner with `CANCEL_TASK` — a cancelled task the
  owner keeps working is the most expensive kind of miscommunication.
- Regressions found after DONE are a **new task** referencing the old one, never a
  reopened state — history stays append-only and auditable.
- A vanished owner adds no state: the task returns to READY or is reassigned
  (ASSIGNED to the new owner), and the staleness is recorded on the roster row —
  the missing-peer procedure is in `peer-protocol.md`.

## WORKER_COMPLETE ≠ PM_VERIFIED

The single most important distinction in this skill. `TASK_COMPLETE` is a claim.
The PM verifies claims **against the repositories, not against the message** — so
the evidence must name a location the PM can actually read: a pushed branch (the
default the contract should require), or, for legitimately local-only work, the
worker's checkout path — in which case the reads below run against that path
(`git -C <worker-checkout> …`) instead of `origin/<branch>`:

```bash
git -C <repo> fetch origin && git -C <repo> log --oneline origin/<branch> | head -5
git -C <repo> diff origin/<default>...origin/<branch> --stat        # matches claimed scope?
gh pr view <n> --json state,statusCheckRollup,reviews               # CI + review state
gh pr checks <n>                                                    # every check green?
```

If the claimed commit does not exist, the diff does not match the claimed scope, or
CI is red — the claim fails verification and goes back as `VERIFICATION_FAILED`
(PM → worker, `peer-protocol.md`): which gate failed, what was measured, what to
fix — never a vague "please check again". (`TASK_REJECTED` is the worker's message
for refusing a contract; it is not the PM's verdict on evidence.)

## Quality gates

Every task passes the gates its risk level requires. A gate is a fact you checked,
not a box you ticked.

| Gate | Question | Checked how | Required for |
| --- | --- | --- | --- |
| 1 — Criteria | does the work satisfy every acceptance criterion in the contract? | PM reads each criterion against the diff/behaviour | all |
| 2 — Evidence | does the claimed evidence exist, as the contract's Required evidence specified? | per the task type (table below): commit reachable and diff matching scope for code, a PR only where the contract requires one, written findings for investigations | all |
| 3 — Checks | did the required verification run green, proven by a read the PM performed? | CI status via `gh` when the contract has CI; without CI, rerun the contract's named verification commands in a disposable checkout — `git worktree add <tmp> <claimed SHA>`, removed afterwards — or hand the rerun to an independent agent. Never run them in the worker's own checkout (build artifacts and caches would dirty it), and the worker's pasted output tail alone never satisfies this gate | all |
| 4 — Review | did someone other than the owner approve it? | reviewer's `REVIEW_RESULT`, or PR review state | MEDIUM+ |
| 5 — Integration | does it hold across repository boundaries? | consumer builds against the change; contract tests; migration order validated | HIGH+ whose effects cross a repository boundary (`multi-repo.md`); single-repository HIGH+ work has no Gate 5 — its extra weight is Gate 4's specialised review |
| 6 — PM verification | PM independently confirmed every gate this task's risk required (1–3 always; 4 for MEDIUM+; 5 for HIGH+ with cross-repository effects) from the sources of truth | the commands above, run by the PM | all |

Gate 4 means **independent** review: the implementing agent is never the only
authority on its own work. Use a dedicated reviewer session when one exists; a PR
review (human or a review bot the project trusts) also satisfies it. For CRITICAL,
add the specialised reviewer the risk demands (security, architecture) — and human
sign-off before merge.

Do not inflate gates for trivial work: a LOW-risk typo fix needs Gates 1, 2, 3, 6 —
demanding more is bureaucracy that teaches agents to route around the PM.

## Evidence by task type

| Task type | Minimum evidence for Gate 2/3 |
| --- | --- |
| Code change | branch, commit SHA, `--stat` summary, test run tail; the PR URL when — and only when — the contract requires a PR |
| Bug fix | the above + a failing-then-passing test that pins the bug |
| Refactor | the above + proof of no behaviour change (same tests green before/after) |
| Migration | forward + rollback tested on a real dataset copy, ordering documented |
| Library release | version, changelog entry, consumer smoke test against the new version |
| Investigation | written findings with file:line references — reproducible, not impressions |
| Docs | the rendered diff, links resolve, examples actually run |

## Release readiness

"Can we release?" is answered from the board plus live checks — never from memory:

1. Every task tagged to the release is DONE — verified AND integrated (merged/
   released as its contract required). VERIFIED alone is not releasable: the work
   may still live only on a feature branch. If the human asks about pre-merge
   readiness, answer that separately and say explicitly which tasks still await
   integration.
2. CI green on every involved repository's release branch — checked now, via `gh`.
3. Migrations validated in order; rollback path stated.
4. Backwards compatibility evaluated for every public contract that moved
   (`multi-repo.md`); consumer repositories tested against the new versions.
5. Security review done where risk demanded it (Gate 4/5 records).
6. Docs and changelogs updated; dependency versions aligned across repos.
7. Open risks reviewed — each accepted risk has a decision entry naming who accepted it.

Answer with the evidence attached: "Yes — 12/12 tasks DONE (all merged), CI green
(links), migrations validated on staging" or "No — TASK-031 verified but not merged
and consumer X untested; earliest path is …".
