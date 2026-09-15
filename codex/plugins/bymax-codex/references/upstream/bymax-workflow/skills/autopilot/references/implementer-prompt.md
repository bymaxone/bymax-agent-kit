# Implementer Prompt Template

The orchestrator renders this template — replacing every `{{PLACEHOLDER}}`
with values from `docs/AUTOPILOT.md` and the current phase — and passes it
verbatim to the implementer sub-agent (Agent tool, `isolation: "worktree"`,
`model` per the config's policy row). Nothing may be left unrendered.

| Placeholder | Source |
|---|---|
| `{{PHASE_NUMBER}}` / `{{PHASE_NN}}` | Current phase (plain / zero-padded) |
| `{{PHASE_FILE}}` | `docs/tasks/phase-{{PHASE_NN}}-*.md` resolved to the real filename |
| `{{BRANCH_SLUG}}` | The phase file's slug (e.g. `core-object-operations`) |
| `{{PROJECT_ROOT}}` / `{{GITHUB_REPO}}` | Config → Identity |
| `{{PRODUCT_SUMMARY}}` | Config → Identity (2–4 lines) |
| `{{ROADMAP_FILE}}` / `{{TASKS_INDEX}}` | Config → Identity |
| `{{PHASE_GATES}}` | Config → Gates: the gate commands active for this phase |
| `{{INVARIANT_GREPS}}` | Config → Invariant greps (may be empty) |
| `{{SECURITY_FOCUS}}` | Config → Security invariants + this phase's review focus |
| `{{CONVENTIONS_EXTRA}}` | Config → Custom conventions (may be empty) |
| `{{REVIEW_BOT_LINE}}` | Config → Review bot: the exact `gh pr edit --add-reviewer …` command, or "No review bot configured — skip this step." |

---

```
You implement ONE phase of {{GITHUB_REPO}} end-to-end up to OPENING A PR and
REQUESTING the code review, then you STOP and return the PR number. You do
NOT wait for the review bot, you do NOT merge, you do NOT spawn any agent.
The orchestrator owns all of that.

Project root: {{PROJECT_ROOT}}
GitHub repo:  {{GITHUB_REPO}}
Product:
{{PRODUCT_SUMMARY}}

You are running in an ISOLATED git worktree: your branch, commits, and files
do not touch the main tree or any other agent. Create your branch with
`git switch -c feat/phase-{{PHASE_NN}}-{{BRANCH_SLUG}}` (NEVER
`git checkout -b`).

ARCHITECTURE OVERRIDE (supersedes any phase-close wording in the task file):
if the phase-close task says to wait for review, address findings, and
merge — under this run you execute the phase-close ONLY up to:
acceptance-criteria audit, dashboard updates, final commit, `gh pr create`,
requesting the code review, returning the PR number. Waiting, fixing review
findings, resolving threads, the grace window, the merge, the branch
deletion, and the final "mark phase Done" commit are OWNED BY THE
ORCHESTRATOR.

YOUR PHASE: Phase {{PHASE_NUMBER}}.
Read {{PHASE_FILE}} (Context, Rules-of-phase, the Task index, and the task
blocks) and each task's REQUIRED READING. TOKEN ECONOMY: read ONLY your
current task's block plus its REQUIRED READING list; use offset/limit reads
on large files; never load the whole spec or plan.

────────────────────────────────────────────────────────────────────────────
STEP 0: Claim the phase
────────────────────────────────────────────────────────────────────────────
ONE status legend (📋 ToDo · 🔄 In Progress · 👀 Review · ✅ Done ·
⛔ Blocked · 🟡 Partial). Update, keeping all three in sync:
  • {{ROADMAP_FILE}} Progress Dashboard: phase row → 🔄, active-phase counter.
  • {{TASKS_INDEX}} phase-files table: phase row → 🔄.
  • {{PHASE_FILE}} header: Status → 🔄.

────────────────────────────────────────────────────────────────────────────
STEP 1: Execute the phase, task by task
────────────────────────────────────────────────────────────────────────────
Tasks run in the Depends-on order of the Task index. For every task:
  • Follow its Agent prompt literally — it is self-contained and names the
    exact deliverables, constraints, and verification commands.
  • Load /bymax-workflow:standards first (§0 simplicity ladder before any
    new code). Verify current official docs for any library/SDK you touch —
    never code an API from memory; the shipped type declarations and README
    of a consumed package are the truth. Reconcile any spec drift against
    the real API and note it in the PR body.
  • TDD as the working mode (/bymax-quality:tdd for new code; the tester
    skill to backfill tests): tests land with the code, every it() carries a
    scenario comment.
  • After each task, run the relevant gates and FIX any failure before the
    next task. MEMORY-SAFE: bounded workers (maxWorkers '50%'), ONE suite at
    a time, never unit and e2e concurrently, never fan out parallel test
    agents.
  • Apply the task's Completion Protocol exactly as written (checkboxes,
    Task index row, header progress, dashboard rows + counters, completion
    log line, Conventional Commit `<type>(<scope>): <subject>
    ({{PHASE_NUMBER}}.<n>)` — no attribution trailers).
Technical priority order: security, then correctness, then performance,
then ergonomics.

────────────────────────────────────────────────────────────────────────────
STEP 2: Phase-wide gates (must all pass)
────────────────────────────────────────────────────────────────────────────
{{PHASE_GATES}}

Invariant greps (each must find nothing):
{{INVARIANT_GREPS}}

────────────────────────────────────────────────────────────────────────────
STEP 3: Bounded Claude + Codex review
────────────────────────────────────────────────────────────────────────────
Verify security candidates against code and tests before fixing them. Complete the
phase-close edits and authorized candidate commit before certification; do not push yet.
Invoke `/bymax-quality:code-review full` with the phase context and actual integration
base. Use one Claude pass and one Codex pass. Triage every finding; fix confirmed
introduced blockers, defer nits/unrelated work with reasons. Re-run STEP 2 gates after
fixes. Both reviewers verify correction deltas and earlier open findings. Maximum three
candidate rounds total; on exhaustion return BLOCKED with evidence to the orchestrator.
Never iterate until zero findings, reset the campaign, or add a third mandatory reviewer.
Any further commit in STEP 4 needs its own covered delta before push.
Special attention for this project:
{{SECURITY_FOCUS}}
Re-run the STEP 2 gates after the review fixes.

────────────────────────────────────────────────────────────────────────────
STEP 4: Open the PR, request the review, return the number, STOP
────────────────────────────────────────────────────────────────────────────
Execute the phase-close task up to the override boundary: acceptance-criteria
audit, dashboard updates ({{ROADMAP_FILE}} row + counters, {{TASKS_INDEX}}
mirror, {{PHASE_FILE}} header + completion log), final Conventional Commit,
push, then:
  gh pr create --title "<type>(<scope>): phase {{PHASE_NUMBER}}, <phase title>" \
    --body "<professional summary: deliverables, acceptance criteria met, gate evidence>"
  {{REVIEW_BOT_LINE}}
Return EXACTLY the PR number and head branch as your final message, e.g.
"PR #7 on branch feat/phase-{{PHASE_NN}}-{{BRANCH_SLUG}}". Do NOT wait for
CI or the review bot. Do NOT merge. Do NOT spawn anything. STOP.

────────────────────────────────────────────────────────────────────────────
MANDATORY CONVENTIONS
────────────────────────────────────────────────────────────────────────────
/bymax-workflow:standards applies in full. Highlights: strict typing, zero
suppression comments (@ts-ignore / eslint-disable / #[allow] / istanbul
ignore); functions ≤ 50 lines, files ≤ 800; a documentation header per file
and doc comments on every export; English-only TIMELESS comments (no
Phase/Task references in committed source or CI config — planning docs may
name phases, shipped code may not); Conventional Commits with NO attribution
trailers anywhere (commits, PR titles, PR bodies, comments); `git switch -c`
(never `git checkout -b`); no `.gitkeep` / empty-dir placeholders;
memory-safe tests (bounded workers, one suite at a time, never fan out).
{{CONVENTIONS_EXTRA}}
```
