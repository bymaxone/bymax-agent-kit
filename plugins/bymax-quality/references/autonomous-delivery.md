# Autonomous delivery contract

A user request to push authorizes the orchestrator to complete the ordinary shipping
workflow: scoped corrections, candidate commits, both reviews, required checks and the
requested push. Do not ask again whether to review or continue a verified correction.
It does not authorize unrelated features, destructive history changes, bypassing checks,
merging, or treating missing evidence as approval.

## Budget and continuity

Use `review_flow.py start --autonomous` for shipping. The default is **six frozen
candidates total**: the initial candidate plus up to five correction candidates. This is
an engineering budget, not a vendor recommendation or a promise of convergence.
The ledger is stored under the shared Git directory at
`bymax-review/deliveries/<branch-hash>.json`, outside the campaign directory. Repeating
start for the same SHA does not spend another slot. Successful intermediate pushes,
watcher wakeups, new bot comments and campaign archives do not renew the budget.
Omitting `--autonomous` on later starts does not disable an enrolled delivery.
A spent budget is an alarm that the corrections keep producing the next finding, not a
wall: a human who decides to continue records it with `--extend-delivery "<who, why>"`,
which grants another budget and is shown to both reviewers. Never delete the ledger.
Keep the same original base and context throughout the feature branch/PR, even after
pushing. A new feature belongs on a new branch; never create one to evade this budget.
Standalone reviews retain their ordinary three-candidate default until enrolled.

The first candidate receives a full review. Subsequent candidates receive a delta review,
verification of prior open findings, and checks of affected callers. Even after a cleared
intermediate candidate, the next start retains the prior head as review base and requires
`--probe` and regression evidence, and it names what it answers with
`--answers <path:slug>...`: after a clearance there are no open findings, so those
declared answers are what the correction-scope rule measures the change against. A new
external finding is included in that probe's command/expected/observed evidence and in
the orchestrator's handoff, not used to reopen unrelated parts of the original
implementation.

## Automatic loop

1. Capture the requested destination/refspec, exact scope, acceptance criteria and real
   project gates. Preserve staged-only boundaries and unrelated work. Reuse a current
   cleared receipt rather than reviewing it again.
2. Run one fresh Claude reviewer and one fresh Codex reviewer, with identical frozen
   context. Only the orchestrator edits or directs corrections; reviewers return evidence.
3. Verify and deduplicate candidates by invariant. Defer nits and pre-existing unrelated
   issues. Reject unsupported claims with concrete counterevidence. After the first pass,
   admit a new blocker only if it proves a defect in the correction or its affected callers,
   or new evidence invalidates a previous rejection. Never optimize for zero comments.
4. Triage before editing. Make one minimal batch, retain cumulative regression tests, and
   check the actual behavior before committing. Keep dependencies and public behavior
   outside the accepted fix unchanged. Record necessary related-file changes with
   `--widen-scope`; this technical justification needs no extra permission when the change
   remains within the user's scope. Use `--no-regression-reason` only when a behavioral
   regression test is infeasible, with concrete alternative verification.
5. A repeated invariant triggers an automatic root-cause analysis with a fresh context.
   Choose the smallest justified repair and use `--design-round` within the same budget;
   it is not by itself a reason to ask the user or expand the feature. Preserve failing
   evidence when a correction regresses an earlier test and replace that correction
   minimally; never reset unrelated work or weaken a test to make the gate green.
6. Run all declared gates against the final candidate, finish, push to the saved target,
   then verify the remote SHA. Do not stop at a clean review when the request was to push.
   PR/babysit/autopilot handlers reuse this ledger and triage, not a new local budget.

Each reviewer has at most two CLI attempts per candidate. Diagnose infrastructure or
schema failures and retry once when the cause is addressed. Never retry a valid review
for a different opinion. Existing platform permissions still apply. Stop with evidence
only for a real obstacle: exhausted budget with blockers, unavailable reviewer after
recovery, an unresolved failing check, ambiguous scope/destination, or a required action
outside authorization. Never publish known unresolved blockers merely to finish.

## Hook handoff

Claude's PreToolUse Bash hook blocks an unreviewed push and returns **AUTOMATIC
CONTINUATION** instructions to the running agent: invoke code-review, certify, and retry
that push. This is an internal handoff, not a request for user confirmation. It does not
start a nested model inside Git's hook. Git pre-push validates every actual pushed SHA;
it never edits commits while Git is transmitting them. A terminal with no agent running
can only report a missing receipt; it cannot execute a skill by printing its name.

## Reviewer ownership and Codex-led shipping

An implementer subagent returns the committed candidate, worktree path, context and gate
results. The main orchestrator owns both independent reviews, corrections, push and PR
creation; the implementer neither reviews its own work nor spawns nested reviewers.
When Claude orchestrates, use its fresh read-only reviewer subagent plus `codex` helper.
When Codex orchestrates an explicitly requested dual-review push, use the same installed
helper and lifecycle. Record the independent Codex report from a fresh context and run
`review_flow.py claude` for the other side (or run both helper reviewers from the parent).
The Claude adapter exposes only Read/Grep/Glob, supplies the exact committed diff,
disables skills/hooks/MCP in that child, and accepts only matching structured output.
A standalone Codex code-review remains single-reviewer and never manufactures a receipt.

## Official guidance checked

- [Claude best practices](https://code.claude.com/docs/en/best-practices): give the agent
  executable success criteria and use fresh-context verification. Applied through actual
  gates, cumulative regression evidence and independent reviewers.
- [Claude hooks](https://code.claude.com/docs/en/hooks): blocking hook feedback returns
  to the agent. Applied as a short handoff instead of model execution inside pre-push.
- [Codex best practices](https://learn.chatgpt.com/guides/best-practices): explicit scope,
  constraints, verification and reusable repository guidance. Applied to the frozen
  context and delta-only corrections.
- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode):
  structured outputs and explicit execution permissions support automation. Applied to
  the read-only reviewer and schema-validated reports, not to permission bypasses.

These sources do not guarantee error-free code or prescribe six candidates. The budget
and convergence policy above are local design decisions to be evaluated on real tasks.
