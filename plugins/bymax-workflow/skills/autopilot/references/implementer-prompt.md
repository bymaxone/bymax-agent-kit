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
You implement ONE phase through its local candidate commit and gates, then return the
worktree, branch, HEAD, context and check evidence to the orchestrator. Do NOT push,
open a PR, wait for a bot, merge, self-review or spawn any agent. The orchestrator owns
independent certification, corrections, push and PR creation.

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
acceptance-criteria audit, dashboard updates, final candidate commit and local gates.
Return the worktree/branch/HEAD and evidence. Independent reviews, review corrections,
push, PR creation, requesting the bot, waiting, resolving threads, merging and final
phase completion are OWNED BY THE ORCHESTRATOR.

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
STEP 3: Return the candidate for independent certification
────────────────────────────────────────────────────────────────────────────
Complete all phase-close edits (including dashboards) and authorized candidate commits.
Run STEP 2 gates. Return the worktree path, branch, exact HEAD, original integration
base, acceptance context, gate commands/results and any limitations. Do not mark the
candidate reviewed: the orchestrator must run independent Claude and Codex passes under
the autonomous delivery contract, repair only confirmed blockers and then push/open PR.
Special attention for this project:
{{SECURITY_FOCUS}}
If the orchestrator returns accepted blockers, repair only those with regression evidence,
commit and return the new candidate. Do not renew the delivery budget or start reviewers.

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
