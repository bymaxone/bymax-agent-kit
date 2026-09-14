# Phase {{N}} — {{PHASE_TITLE}}

> **Status**: 📋 ToDo &nbsp;·&nbsp; **Progress**: 0 / {{TOTAL_TASKS}} tasks &nbsp;·&nbsp; **Last updated**: {{YYYY-MM-DD}}
> **Source roadmap**: [`docs/plans/{{feature-slug}}-plan.md`](../plans/{{feature-slug}}-plan.md) § Phase {{N}}
> **Source spec**: [`docs/specs/{{feature-slug}}.md`](../specs/{{feature-slug}}.md)

---

## Context

> What state must the codebase be in when work on this phase starts? What's the deliverable when the phase finishes?

{{CONTEXT_PARAGRAPH}}

---

## Rules-of-phase

> Lifted from the roadmap. Numbered. Concrete. Each rule should be enforceable by code review.

1. {{RULE_1}}
2. {{RULE_2}}
3. {{RULE_3}}

---

## Reference docs

> The minimum set an agent needs to read to execute these tasks.

- `CLAUDE.md` § {{SECTION}}
- `docs/guidelines/{{GUIDELINE}}.md` § "{{ANCHOR}}"
- `docs/knowledge-base/{{CHAPTER}}.md` (if domain-specific)
- `/bymax-workflow:standards` skill (universal coding rules)

---

## Task index

| ID | Task | Status | Priority | Size | Depends on |
|---|---|---|---|---|---|
| {{N}}.1 | {{TASK_1_TITLE}} | 📋 ToDo | P0 | S | — |
| {{N}}.2 | {{TASK_2_TITLE}} | 📋 ToDo | P0 | M | {{N}}.1 |
| {{N}}.3 | {{TASK_3_TITLE}} | 📋 ToDo | P1 | S | {{N}}.1 |
| {{N}}.4 | {{TASK_4_TITLE}} | 📋 ToDo | P1 | M | {{N}}.2, {{N}}.3 |

---

## Tasks

### Task {{N}}.1 — {{TASK_1_TITLE}}

- **Status**: 📋 ToDo
- **Priority**: P0
- **Size**: S
- **Depends on**: —

#### Description

{{TASK_1_DESCRIPTION}}

#### Acceptance criteria

- [ ] {{AC_1}}
- [ ] {{AC_2}}
- [ ] {{AC_3}}
- [ ] All universal gates pass: `pnpm type-check`, `pnpm lint`, `pnpm format:check`, tests for touched files.

#### Files to create / modify

- ✚ `src/features/{{feature}}/{{file-1}}.ts`
- ✚ `src/features/{{feature}}/{{file-2}}.tsx`
- ✎ `src/features/{{feature}}/index.ts` — add new exports

#### Agent prompt (EN)

````
You are a senior {{ROLE}} engineer working on the {{PROJECT_NAME}} project.

PROJECT: {{PROJECT_NAME}} — {{ONE_LINE_DESC}}.
{{STACK_LINE}}

CURRENT PHASE: {{N}} ({{PHASE_TITLE}}) — Task {{N}}.1 of {{TOTAL_TASKS}} (FIRST of this phase)

PRECONDITIONS
- {{PRECONDITION_1}}
- {{PRECONDITION_2}}

REQUIRED READING (only these sections — do not load more):
- `CLAUDE.md` § {{SECTION}}
- `docs/guidelines/{{GUIDELINE}}.md` § "{{ANCHOR}}"
- `/bymax-workflow:standards` skill (TypeScript discipline, JSDoc policy, layered architecture, suppression bans)

TASK
{{ONE_TWO_SENTENCE_OBJECTIVE}}

DELIVERABLES

1. `src/features/{{feature}}/{{file-1}}.ts`:
   {{WHAT_AND_WHY}}

   ```ts
   /**
    * {{FILE_HEADER_PURPOSE}}.
    *
    * Layer: {{LAYER}}.
    */
   export {{...short illustrative skeleton...}}
   ```

2. `src/features/{{feature}}/{{file-2}}.tsx`:
   {{WHAT_AND_WHY}}

   ```tsx
   /**
    * {{COMPONENT_PURPOSE}}.
    */
   export function {{ComponentName}}({{props}}) { /* ... */ }
   ```

3. `src/features/{{feature}}/index.ts`:
   Add exports for the public API only (no internals leak).

Constraints:
- TS strict + `noUncheckedIndexedAccess` — zero `any`.
- File-header JSDoc on every new non-trivial file. JSDoc on every export.
- English comments only.
- No suppression comments (`eslint-disable`, `@ts-ignore`, `as any`). Fix root cause if a rule fires.
- Match the project's naming conventions (see `/bymax-workflow:standards` §2).
- {{PROJECT_SPECIFIC_CONSTRAINT}}

Verification:
- `pnpm type-check` — expected: 0 errors
- `pnpm lint` — expected: 0 errors, 0 new warnings on touched files
- `pnpm test src/features/{{feature}}` — expected: tests pass (write tests if missing — see /bymax-quality:tester or /bymax-quality:tdd)
- {{MANUAL_VERIFICATION_STEP}}

Completion Protocol (after the agent reports done):
1. Update task status emoji to ✅ Done in this file
2. Tick acceptance-criteria checkboxes above
3. Update task row in the task index table (status column)
4. Increment phase progress counter at top of this file (`N/{{TOTAL_TASKS}} tasks`)
5. Update phase row in the master roadmap dashboard at `docs/plans/{{feature-slug}}-plan.md`
6. Recompute overall progress percentage in the roadmap
7. Append a completion log entry at the bottom of this file:
   `- {{N}}.1 ✅ YYYY-MM-DD — {{one-line summary}}`
````

---

### Task {{N}}.2 — {{TASK_2_TITLE}}

- **Status**: 📋 ToDo
- **Priority**: P0
- **Size**: M
- **Depends on**: {{N}}.1

#### Description

{{TASK_2_DESCRIPTION}}

#### Acceptance criteria

- [ ] {{AC_1}}
- [ ] {{AC_2}}

#### Files to create / modify

- ✚ `src/features/{{feature}}/{{file}}.ts`
- ✎ `src/features/{{feature}}/{{existing}}.ts` — modify to use new helper

#### Agent prompt (EN)

````
You are a senior {{ROLE}} engineer working on the {{PROJECT_NAME}} project.

PROJECT: {{PROJECT_NAME}} — {{ONE_LINE_DESC}}.
{{STACK_LINE}}

CURRENT PHASE: {{N}} ({{PHASE_TITLE}}) — Task {{N}}.2 of {{TOTAL_TASKS}} (MIDDLE of this phase)

PRECONDITIONS
- Task {{N}}.1 must be ✅ Done — {{file-1}}.ts and {{file-2}}.tsx exist as scaffolded.
- {{OTHER_PRECONDITION}}

REQUIRED READING (only these sections):
- `docs/guidelines/{{GUIDELINE}}.md` § "{{ANCHOR}}"
- The output of task {{N}}.1 (read `src/features/{{feature}}/{{file-1}}.ts`)

TASK
{{OBJECTIVE}}

DELIVERABLES

1. `src/features/{{feature}}/{{file}}.ts`:
   {{WHAT_AND_WHY}}

   ```ts
   {{SKELETON}}
   ```

2. Modify `src/features/{{feature}}/{{existing}}.ts`:
   {{WHAT_TO_CHANGE}}

Constraints:
- All universal rules from `/bymax-workflow:standards`.
- {{PHASE_SPECIFIC_CONSTRAINT}}

Verification:
- `pnpm type-check`
- `pnpm test src/features/{{feature}}/{{file}}.test.ts`
- {{MANUAL_STEP}}

Completion Protocol (after the agent reports done):
1. Update task status emoji to ✅ Done in this file
2. Tick acceptance-criteria checkboxes above
3. Update task row in the task index table (status column)
4. Increment phase progress counter at top of this file (`N/{{TOTAL_TASKS}} tasks`)
5. Update phase row in the master roadmap dashboard at `docs/plans/{{feature-slug}}-plan.md`
6. Recompute overall progress percentage in the roadmap
7. Append a completion log entry at the bottom of this file:
   `- {{N}}.2 ✅ YYYY-MM-DD — {{one-line summary}}`
````

---

> Repeat the per-task block for every task. Keep them in execution order. Each task's prompt must be self-contained.

---

## Completion log

> Append-only. One line per task completion. Format: `- {{task-id}} ✅ YYYY-MM-DD — {{one-line summary}}`.

<!-- entries will be added as tasks complete -->
