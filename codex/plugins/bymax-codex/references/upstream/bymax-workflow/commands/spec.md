---
description: 'Layer 1 of the feature workflow — write a complete technical specification document for a new feature. Asks clarifying questions if the request is vague, then drafts a spec covering goal, scope, user stories, success criteria, technical approach, constraints, risks, and open questions. WAITS for user approval before any next step. Does NOT create plans or tasks. Triggers: "novo recurso", "nova feature", "spec", "specification", "especificacao", "preciso especificar", "vou implementar X", "documentar feature", "começar feature".'
argument-hint: "[feature description]"
---

# Spec Command — Layer 1

First step in the **spec → roadmap → phase-tasks** workflow. Produces the "what we're building and why" document. The spec is the foundation everything else builds on; never skip it for non-trivial features.

## When to use

- A real new feature that will need multiple phases (auth flow, billing, dashboard, export pipeline, etc.).
- An epic-sized refactor (state migration, framework upgrade, multi-screen redesign).
- Any work that needs a senior reviewer to sign off on direction before code is touched.

## When NOT to use

- A bug fix → use `/bymax-workflow:plan` directly.
- A 1-task tweak → use `/bymax-workflow:plan` or just write the code.
- A vague brainstorm — use `/bymax-workflow:brainstorm` first to refine the idea, then come back here.

## Workflow

### Step 1 — Read the project context

1. Read `CLAUDE.md` and `AGENTS.md` if present.
2. Look at `docs/specs/`, `docs/plans/`, `docs/tasks/` to understand existing conventions and naming.
3. Skim 1-2 existing specs in this repo to match the project's voice and depth.

### Step 2 — Clarify

If the user's request is missing any of the following, **ask before drafting** (group questions into batches of 3-5):

- **Goal** — what user problem this solves, measurable outcome.
- **Scope** — what's in v1, what's out, what's "v2 maybe".
- **Users / personas** — who this is for and what they do today instead.
- **Constraints** — deadline, performance budget, privacy, regulatory, platform.
- **Dependencies** — other features / services this needs.
- **Success metric** — how we'll know it worked (analytics event, manual test, business KPI).
- **Non-goals** — things this is explicitly NOT trying to do.

If the request is rich enough to skip clarification, say so and proceed.

### Step 3 — Choose a path and slug

- Default location: `docs/specs/<feature-slug>.md`
- If the project already uses a different convention (e.g., `docs/features/`, `docs/rfc/`), match it.
- Slug: kebab-case, ≤ 4 words. Examples: `passkey-auth`, `nutrition-history`, `csv-export`.
- Confirm the path with the user before writing.

### Step 4 — Draft the spec

Read `spec.template.md` and fill it in — resolve it in this order, first hit wins: (1) `${CLAUDE_PLUGIN_ROOT}/templates/spec.template.md` — the copy versioned with this command; (2) only if that is absent, `~/.claude/templates/spec.template.md`; (3) only if both are absent, write the sections below directly. Sections (mandatory in this order):

1. **Header / metadata** — status (📝 Draft), owner, last-updated, related links
2. **Goal** — one paragraph, user-facing
3. **Background / why now** — what changed; what user pain triggered this
4. **Scope** — in / out / future (3 bullet lists)
5. **User stories or scenarios** — 3-7 numbered, in the user's voice
6. **Success criteria** — measurable, with how we'll verify
7. **Technical approach** — high-level, no file paths yet
8. **Architecture / data model** — if applicable, one diagram or schema sketch
9. **Constraints** — privacy, performance, regulatory, dependencies, tech stack alignment
10. **Risks** — what could bite, scored (LOW / MEDIUM / HIGH) with mitigation
11. **Open questions** — explicit unknowns that block decisions
12. **References** — prior art, related issues, design docs, ADRs

Keep it under ~3 pages. Long specs hide important details.

### Step 5 — Stop. Summarize. WAIT.

Print:

```
✅ Spec drafted at docs/specs/<feature-slug>.md

Summary:
  Goal:           <one line>
  Scope (v1):     <one line>
  Constraints:    <one line>
  Open questions: <count>
  Risks (HIGH):   <count>

Next step (after you review):
  /bymax-workflow:roadmap docs/specs/<feature-slug>.md
  → breaks the spec into phases with a dashboard, dependency graph, and DoD per phase

Do you want to:
  - Approve as-is and run /bymax-workflow:roadmap?
  - Modify a section?
  - Answer the open questions before /bymax-workflow:roadmap?
```

**Do not** call `/bymax-workflow:roadmap` or any other command. Wait for explicit user direction.

## Hard rules

- **Never invent missing information.** If the user can't answer a clarifying question, write `TBD` and add it to "Open questions" — don't guess.
- **No code, no file paths in the spec.** This document is for the *what*, not the *how*. Save file paths for `/bymax-workflow:phase-tasks`.
- **No phases yet.** Phases live in `/bymax-workflow:roadmap`. The spec describes ONE feature, not the work breakdown.
- **English-only** in the spec body (per `/bymax-workflow:standards`).

## Integration with the rest of the workflow

```
/bymax-workflow:spec          ← you are here
   ⏸ user approval
/bymax-workflow:roadmap       (next — phased plan with dashboard)
   ⏸ user approval
/bymax-workflow:phase-tasks   (per-phase scaffolding with agent prompts)
   ⏸ user approval per phase
/bymax-workflow:plan, /bymax-quality:tdd, /bymax-workflow:verify, /bymax-quality:code-review (execution)
```
