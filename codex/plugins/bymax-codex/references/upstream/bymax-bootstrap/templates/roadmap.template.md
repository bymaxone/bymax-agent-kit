# Roadmap — {{FEATURE_TITLE}}

> **Source spec**: [`docs/specs/{{feature-slug}}.md`]({{relative-path-from-this-file-to-the-spec}}) <!-- default layout docs/plans/ → ../specs/{{feature-slug}}.md; compute from where this roadmap actually lives -->
> **Last updated**: {{YYYY-MM-DD}}

---

## Status legend

| Emoji | Meaning |
|---|---|
| 📋 | ToDo |
| 🔄 | In Progress |
| 👀 | Review |
| ✅ | Done |
| ⛔ | Blocked |
| 🟡 | Partial |

---

## Progress

> Update this every time a phase moves status. Recompute % from the table below.

**Overall progress**: 📋 0 / {{TOTAL_PHASES}} phases done (0%)
**Active phase**: —
**Blocked**: —

---

## Phase dashboard

| ID | Phase | Status | Progress | Size | Last updated |
|---|---|---|---|---|---|
| P0 | {{P0_TITLE}} | 📋 ToDo | — | S | — |
| P1 | {{P1_TITLE}} | 📋 ToDo | — | M | — |
| P2 | {{P2_TITLE}} | 📋 ToDo | — | M | — |
| P3 | {{P3_TITLE}} | 📋 ToDo | — | L | — |
| P4 | {{P4_TITLE}} | 📋 ToDo | — | S | — |

---

## Dependency graph

```
P0 ── P1 ──┬── P3
           └── P2
P4 (independent — can run any time after P0)
```

### Parallelization notes

- **P1** and **P2** can run in parallel after P0 completes.
- **P3** depends on both P1 and P2.
- **P4** has no dependency beyond the project bootstrap.

---

## Global conventions

> Project-wide rules that every phase respects. Lifted from `CLAUDE.md` + `/bymax-workflow:standards` + this project's `docs/guidelines/`.

| Area | Rule |
|---|---|
| Package manager | {{PKG_MGR}} (e.g., `pnpm@10`) |
| Node version | {{NODE_VERSION}} |
| TypeScript | strict + `noUncheckedIndexedAccess`. No `any`, no `// @ts-ignore`. |
| Naming | Components PascalCase · hooks `use*` · constants UPPER_SNAKE · folders kebab-case |
| Comments | English only. File-header JSDoc on every non-trivial file. JSDoc on every export. |
| Tests | Every `it()` has a block comment (scenario + rule it protects). |
| Lint | ESLint flat config + `eslint-plugin-security` + `eslint-plugin-import` order |
| Format | Prettier — 100 col, single quotes, trailing comma all, LF |
| Commits | Conventional Commits via commitlint + Husky |
| Architecture | Layered: `app/` → `features/*` → `shared/*`. No cross-feature imports. |
| Suppression | Banned: `eslint-disable*`, `@ts-ignore`, `as any`. Fix root cause. |

---

## Phase details

### P0 — {{P0_TITLE}}

- **Goal**: {{P0_GOAL}}
- **Scope**:
  - In: {{P0_IN}}
  - Out: {{P0_OUT}}
- **Definition of Done**:
  - [ ] {{P0_DOD_1}}
  - [ ] {{P0_DOD_2}}
  - [ ] {{P0_DOD_3}}
- **Context / preconditions**: {{P0_CONTEXT}}
- **Rules-of-phase**:
  1. {{P0_RULE_1}}
  2. {{P0_RULE_2}}
- **References**:
  - Spec § {{SPEC_SECTION}}
  - `docs/guidelines/{{GUIDELINE}}.md`
- **Estimated size**: S / M / L
- **Tasks**: scaffolded via `/bymax-workflow:phase-tasks {{feature-slug}} P0` → `docs/tasks/phase-00-{{slug}}.md`

---

### P1 — {{P1_TITLE}}

- **Goal**: …
- **Scope**: …
- **Definition of Done**: …
- **Context / preconditions**: …
- **Rules-of-phase**: …
- **References**: …
- **Estimated size**: …
- **Tasks**: `docs/tasks/phase-01-{{slug}}.md` (run `/bymax-workflow:phase-tasks {{feature-slug}} P1` after P0 is approved)

---

> Repeat the per-phase block for every phase in the dashboard. Keep them in dependency order.

---

## Update protocol

When a phase moves status:

1. Edit the row in the **Phase dashboard** table — status emoji + progress + last-updated.
2. Update **Overall progress** counter and percentage.
3. Update **Active phase** and **Blocked** lines at the top.
4. If the phase is ✅ Done, append a one-line entry to the **Completion log** in this file (or in `CHANGELOG.md` if the project keeps one).
5. If a downstream phase becomes unblocked, update its status from 📋 ToDo to 🔄 In Progress (or just notify).
6. Leave the commit to the user — suggested message when they ask:
   `chore(roadmap): {{feature-slug}} phase {{N}} → {{status}}`. Commands that run
   this protocol never commit on their own.

---

## Completion log

> Append-only. One line per phase completion.

- {{YYYY-MM-DD}} — P0 ✅ {{P0_TITLE}}: {{one-line summary}}

---

## Sign-off

When this roadmap is approved, run:

```
/bymax-workflow:phase-tasks {{feature-slug}} P0     ← scaffold first phase's tasks
```

For each subsequent phase, repeat with `P1`, `P2`, etc. **One phase at a time.**
