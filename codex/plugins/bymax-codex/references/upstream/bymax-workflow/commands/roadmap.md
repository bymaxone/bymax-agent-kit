---
description: 'Layer 2 of the feature workflow — take an APPROVED spec and break it into a phased plan with a status dashboard, dependency graph, and definition-of-done per phase. Produces the "how we''ll build it" document. WAITS for user approval before any next step. Does NOT create task files yet. Triggers: "criar plano", "criar roadmap", "fasear", "roadmap", "plano mestre", "executar spec", "phase plan", "execution plan".'
argument-hint: "[feature or spec path]"
---

# Roadmap Command — Layer 2

Second step in the **spec → roadmap → phase-tasks** workflow. Takes an approved spec and decomposes it into a phased execution plan with status tracking. The roadmap is the project-management layer — it does NOT contain task-level prompts (those live in `/bymax-workflow:phase-tasks`).

## Prerequisite

A spec at `docs/specs/<feature>.md` (or wherever the project keeps them) must exist and be approved by the user. If no spec exists, refuse and tell the user to run `/bymax-workflow:spec` first.

## When to use

- Right after `/bymax-workflow:spec` was approved.
- Re-running on an existing roadmap to add/remove phases or update the dashboard (with explicit confirmation).

## Workflow

### Step 1 — Load context

1. Read the spec at the path the user passed (or detect under `docs/specs/`).
2. Read `CLAUDE.md` and `AGENTS.md`.
3. Look at existing `docs/plan.md` / `docs/plans/` files to match conventions (status emojis, dashboard format, dependency graph style).
4. Skim 1 existing roadmap in the repo to match voice and depth.

### Step 2 — Confirm path and naming

- Default location: `docs/plans/<feature>-plan.md`
- If the project uses a single `docs/plan.md` for everything (like bymax.bio), ask whether to **append** to that or create a per-feature file.
- If the project uses a different convention (`DEVELOPMENT_PLAN.md`, `ROADMAP.md`, etc.), match it.

### Step 3 — Decompose into phases

Aim for **4-12 phases**. Each phase should:
- Be **shippable / testable on its own** (no half-done things merged).
- Take roughly 2-8 hours of work end-to-end.
- Have a clear **definition of done** (one sentence, observable).
- Reference the spec section(s) it implements.

Don't over-decompose. A 2-line code change is not a phase.

For each phase, capture:
- ID (`P0`, `P1`, ... or `Phase 1`, `Phase 2`, ...)
- Title (kebab-case lowercase + human title)
- Status (default 📋 ToDo)
- Goal (one sentence)
- Scope (in / out)
- Definition of Done (3-5 bullets, observable)
- Context / preconditions
- Rules-of-phase (project conventions that apply specifically here)
- References to spec sections and existing docs
- Estimated size (S / M / L)

### Step 4 — Map dependencies

Identify which phases:
- Must be sequential (phase B needs phase A's deliverable).
- Can run in parallel (phase B and C are independent).
- Are optional / nice-to-have.

Render as an ASCII DAG. Example:

```
P0 ── P1 ──┬── P3 ── P5
           └── P4 ── P5
P2 ──────────────────┘
```

### Step 5 — Render the document

Use the `roadmap.template.md` structure — resolve it in this order, first hit wins: (1) `${CLAUDE_PLUGIN_ROOT}/templates/roadmap.template.md` — the copy versioned with this command; (2) only if that is absent, `~/.claude/templates/roadmap.template.md`; (3) only if both are absent, build the document from the required sections below — they are the same contract. Required sections:

1. **Header** — status legend, last updated, source spec link — computed
   relative to where the roadmap file actually lives (default
   `docs/plans/<feature>-plan.md` → `../specs/<feature-slug>.md`; a custom
   location changes the prefix, so derive it, never paste the default)
2. **Progress dashboard** — counter (`N / M phases done`, `XX%`)
3. **Phase table** — exactly this shape (Status always carries the legend emoji;
   Progress is `done/total` tasks):

   ```markdown
   | ID | Phase | Status | Progress | Size | Last updated |
   |---|---|---|---|---|---|
   | P0 | <kebab-title — short description> | 📋 ToDo | — | M | — |
   ```

   Progress becomes `done/total` tasks only when the phase's task file exists —
   `/bymax-workflow:phase-tasks` writes the `0/N` when it scaffolds the phase.
   At roadmap time the denominator is unknown: write `—`, never an invented
   count.
4. **Dependency graph** — ASCII DAG
5. **Parallelization notes** — what can run together, what blocks what
6. **Global conventions** — TypeScript / naming / paths / lint / test rules that apply across phases (lift from `CLAUDE.md` + `/bymax-workflow:standards`)
7. **Per-phase detail** — for each phase: Goal / Scope / DoD / Context / Rules / References / Size
8. **Update protocol** — exact steps to update the dashboard when a phase moves status (5-7 numbered steps)

Status emoji legend (use exactly these):
- 📋 ToDo
- 🔄 In Progress
- 👀 Review
- ✅ Done
- ⛔ Blocked
- 🟡 Partial

### Step 6 — Stop. Summarize. WAIT.

Print:

```
✅ Roadmap drafted at docs/plans/<feature>-plan.md

Phases:        <N>
Critical path: <list of phase IDs>
Parallelizable: <list of pairs / triples>
Total size estimate: <X S / Y M / Z L>

Dashboard:
  📋 ToDo:        N
  🔄 In Progress: 0
  ✅ Done:        0

Next step (after you review):
  /bymax-workflow:phase-tasks <feature> P1     ← scaffold the first phase's task file (recommended)
  /bymax-workflow:phase-tasks <feature> --all  ← scaffold every phase at once (not recommended for >5 phases)

Do you want to:
  - Approve and scaffold P1?
  - Modify phase decomposition?
  - Adjust dependencies?
```

**Do not** call `/bymax-workflow:phase-tasks` automatically. Wait for explicit user direction.

## Hard rules

- **Never proceed without an approved spec.** If the spec is marked `📝 Draft`, refuse and ask user to confirm it's ready.
- **Phases must be shippable independently.** If a phase makes no sense to merge alone, split or merge it.
- **No agent prompts here.** Those live in `/bymax-workflow:phase-tasks`. The roadmap is for managers/reviewers.
- **No code snippets in the roadmap.** Show file paths only when describing scope.
- **English-only** in the document body.

## Integration with the rest of the workflow

```
/bymax-workflow:spec          (already done)
   ⏸ user approval
/bymax-workflow:roadmap       ← you are here
   ⏸ user approval
/bymax-workflow:phase-tasks   (next — per-phase task files with agent prompts)
   ⏸ user approval per phase
```
