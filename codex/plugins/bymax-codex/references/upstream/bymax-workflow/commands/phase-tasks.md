---
description: 'Layer 3 of the feature workflow — take an APPROVED roadmap and scaffold detailed task files for a single phase (or all phases on demand). Each task file contains task table (JIRA-style with id/status/priority/size/depends-on), acceptance criteria, files to create/modify, and a verbose English agent prompt that another AI can execute end-to-end (Role / PROJECT / PRECONDITIONS / REQUIRED READING / TASK / DELIVERABLES / Constraints / Verification / Completion Protocol). Default = ONE phase at a time (`--all` scaffolds every phase, for small features only). WAITS for user approval before scaffolding the next. Triggers: "criar tasks", "scaffold tasks", "detalhar fase", "phase tasks", "criar arquivos de fase", "preciso das tasks da fase", "executar fase".'
argument-hint: "<feature> [phase-id|next|--all]"
---

# Phase Tasks Command — Layer 3

Final step in the **spec → roadmap → phase-tasks** workflow. Takes a single phase from the approved roadmap and produces a detailed task file with self-contained agent prompts. Each prompt is meant to be droppable into a fresh Claude Code conversation that will then execute the task without needing the rest of the conversation as context.

## Prerequisite

An approved roadmap must exist (`docs/plans/<feature>-plan.md` or `docs/plan.md`). If no roadmap exists, refuse and tell the user to run `/bymax-workflow:roadmap` first.

## Invocation

```
/bymax-workflow:phase-tasks <feature> <phase-id>     # scaffold one phase (recommended)
/bymax-workflow:phase-tasks <feature> --all          # scaffold every phase (use only for small features)
/bymax-workflow:phase-tasks <feature> next           # scaffold the next non-scaffolded phase
```

Default behavior when the user just says `/bymax-workflow:phase-tasks <feature>` is `next`.

## Workflow

### Step 1 — Load context

1. Read the roadmap to find the phase block.
2. Read the spec linked from the roadmap header.
3. Read `CLAUDE.md`, `AGENTS.md`, and any `docs/guidelines/` files relevant to this phase.
4. Look at 1-2 existing `docs/tasks/phase-NN-*.md` files to match conventions (header layout, prompt structure, completion log format).
5. Detect which related sections of the codebase already exist (so prompts can reference them by real path, not by guess).

### Step 2 — Confirm path and existence

- Default file: `docs/tasks/phase-<NN>-<phase-slug>.md`
- If the file already exists, **do not overwrite**. Ask whether to:
  - Append new tasks to it
  - Open it for review
  - Cancel

### Step 3 — Decompose the phase into tasks

Aim for **3-8 tasks** per phase. Each task should:
- Be doable in **15 min – 2 hours** by a focused engineer/agent.
- Have a single, clear deliverable (one component, one service, one migration, one set of tests).
- Be ordered so an engineer/agent can execute top-to-bottom without backtracking.

For each task, capture:

- **ID** — `<phase>.<seq>` (e.g., `1.3`, `P0-2`) — match project convention
- **Title** — short imperative ("Create useUserProfile hook")
- **Status** — default 📋 ToDo
- **Priority** — P0 / P1 / P2
- **Size** — XS / S / M / L
- **Depends on** — list of task IDs in this or earlier phases
- **Description** — 1-2 sentences
- **Acceptance criteria** — checkbox list, observable outcomes
- **Files to create / modify** — exact paths
- **Agent prompt** — verbose, English, self-contained (see template below)

### Step 4 — Render the file

Use the `phase-tasks.template.md` structure — resolve it in this order, first hit wins: (1) `${CLAUDE_PLUGIN_ROOT}/templates/phase-tasks.template.md` — the copy versioned with this command; (2) only if that is absent, `~/.claude/templates/phase-tasks.template.md`; (3) only if both are absent, build the file from the required sections below. Required sections:

1. **Header** — phase id, title, status, progress (`0/N tasks`), last-updated, source roadmap link
   — and in the same scaffold, replace the phase's `—` Progress in the master
   roadmap with `0/N`: the task count is born here, so this command is what
   writes the denominator upstream
2. **Context** — preconditions + state of codebase expected at start (1-2 paragraphs)
3. **Rules-of-phase** — numbered list of project rules that apply specifically (lift from roadmap)
4. **Reference docs** — relevant `docs/guidelines/` and `docs/knowledge-base/` files with section anchors
5. **Task index table** — exactly this shape (Status always carries the legend
   emoji: 📋 🔄 👀 ✅ ⛔ 🟡):

   ```markdown
   | ID | Task | Status | Priority | Size | Depends on |
   |---|---|---|---|---|---|
   | <N>.1 | <imperative title> | 📋 ToDo | P0 | S | — |
   ```
6. **Per-task block** — for each task: header / status / priority / size / depends / description / acceptance criteria / files / agent prompt
7. **Completion log** — append-only at the end, one line per completed task: `- <task-id> ✅ YYYY-MM-DD — <one-line summary>`

### Step 5 — Agent-prompt template (inside each task)

Every task contains an English code-block prompt with this structure (use 4 backticks to wrap so internal triple-backticks survive):

````
You are a senior <role> engineer working on the <project> project.

PROJECT: <project name> — <one-line description>.
<one-line stack: framework, key versions, language>

CURRENT PHASE: <N> (<phase title>) — Task <N.M> of <total> (<position: FIRST / MIDDLE / LAST>)

PRECONDITIONS
- <bullet — what must already exist in the codebase>
- <bullet>

REQUIRED READING (only these sections — do not load more):
- <doc path> § "<section anchor>"
- <doc path> § "<section anchor>"

TASK
<1-2 sentence objective in plain English>

DELIVERABLES

1. `<exact file path>`:
   <description of what goes in the file, why, and any non-obvious decisions>

   ```ts
   <code skeleton if helpful — keep short, illustrative>
   ```

2. `<exact file path>`:
   ...

Constraints:
- <project-specific must-have>
- Follow /bymax-workflow:standards: TS strict, JSDoc on every export, English comments only, no suppression comments.
- <other constraints from rules-of-phase>

Verification:
- `<command>` — expected: <observable result>
- `<command>` — expected: <observable result>

Completion Protocol (after the agent reports done):
1. Update task status emoji to ✅
2. Tick acceptance-criteria checkboxes
3. Update task row in the task index table
4. Increment phase progress counter (`N/M tasks`)
5. Update phase row in the master roadmap dashboard
6. Recompute overall progress percentage
7. Append a completion log entry: `- <task-id> ✅ <YYYY-MM-DD> — <one-line summary>`
````

The prompt **must read self-contained** — an agent dropped into a fresh conversation should be able to execute it without needing the rest of the project history.

### Step 6 — Stop. Summarize. WAIT.

Print:

```
✅ Phase <N> tasks scaffolded at docs/tasks/phase-<NN>-<slug>.md

Tasks: <count>
Estimated size: <total>
Critical task: <id> (<short reason>)

Next options:
  /bymax-workflow:phase-tasks <feature> next    ← scaffold the next phase
  Start working: /bymax-workflow:plan or /bymax-quality:tdd on task <first-task-id>
  Modify: tell me what to change in this file

Do not auto-scaffold the next phase — wait for explicit confirmation.
```

## Hard rules

- **One phase per invocation by default.** `--all` exists but should be reserved for small features (≤ 5 phases) or late-night scaffolding sessions where the user is OK reviewing in bulk.
- **Never re-scaffold an existing file silently.** Ask first.
- **Prompts must be self-contained.** No "see above" or "as discussed". Each prompt = one agent's full context.
- **Every prompt ends with the Completion Protocol.** Non-negotiable — keeps the dashboards honest.
- **English in prompts.** Mixed-language prompts make agents flaky.
- **Reference real paths.** Don't invent file paths the project doesn't have. Verify before writing the prompt.

## Integration with the rest of the workflow

```
/bymax-workflow:spec          (done)
/bymax-workflow:roadmap       (done)
/bymax-workflow:phase-tasks   ← you are here (run once per phase, with approval)
   ⏸ user approval
/bymax-workflow:plan / /bymax-quality:tdd   ← then execute the prompts inside each task
/bymax-workflow:verify        ← prove each task is done
/bymax-quality:code-review   ← before marking ✅
```
