# CLAUDE.md — {{PROJECT_NAME}}

Quick rules for Claude Code and any AI coding agent. Read before every task.

Universal standards live in the global `/bymax-workflow:standards` skill. This file documents what is **specific to this project** and overrides the universal layer when needed.

---

## Stack

> Replace with the project's actual stack on day one.

- **Runtime**: {{RUNTIME}} (Node version, browser target, mobile platform)
- **Framework**: {{FRAMEWORK}}
- **Language**: TypeScript {{TS_VERSION}} strict
- **Styling**: {{STYLING}} (Tailwind / NativeWind / CSS Modules / etc.)
- **State / forms**: {{STATE_LIB}} + React Hook Form + Zod
- **Testing**: {{TEST_RUNNER}} ({{TEST_LIB}})
- **Tooling**: ESLint 9 flat config, Prettier 3, Husky 9, commitlint, {{PKG_MGR}}

---

## Non-negotiables (project-specific)

- **TypeScript strict + `noUncheckedIndexedAccess`**. No `any`, no `// @ts-ignore`, no `// eslint-disable`. Fix the root cause.
- **English comments only** — code, JSDoc, inline notes. User-facing strings live in i18n bundles.
- **File-header JSDoc on every non-trivial file**; JSDoc on every exported function/hook/component/service.
- **Every test `it` carries a block comment** describing the scenario and the rule it protects.
- **Feature-based, layered**: `app/` → `src/features/*` → `src/shared/*`. No cross-feature imports — go through `shared/`.
- **Conventional Commits** — enforced by commitlint + Husky.
- **{{PROJECT_SPECIFIC_RULE_1}}**
- **{{PROJECT_SPECIFIC_RULE_2}}**

---

## Folder layout

```
app/              {{ROUTES_OR_ENTRY}} — thin, composition only
src/features/*    feature code: components, hooks, services, queries
src/shared/*      portable: ui, utils, db, i18n, theme, observability
tests/            shared fixtures and integration suites
```

---

## Verification before finishing

```bash
{{PKG_MGR}} type-check     # TS must compile — 0 errors
{{PKG_MGR}} lint           # ESLint must pass — 0 errors or suppressions
{{PKG_MGR}} format:check   # Prettier must be clean
{{PKG_MGR}} test           # tests pass
```

Manual sweep on changed files:

- [ ] No `console.log` (use the project logger).
- [ ] No `any`, no `// @ts-ignore`, no `// eslint-disable`.
- [ ] Comments in English only.
- [ ] File-header JSDoc on every new non-trivial file.
- [ ] JSDoc on every new exported function, hook, component, service.
- [ ] Every new test `it` has a block comment describing the scenario and the rule it protects.
- [ ] User-facing strings via `t()`.
- [ ] No cross-feature imports.
- [ ] No PII / secrets in analytics or logs.
- [ ] New external deps justified.

---

## Git

{{GIT_RULES}}

Conventional Commits grammar (`feat(scope): …`, `fix(scope): …`).

---

## Before ANY task — in this order

1. Skim this file.
2. If there is an `AGENTS.md` or `docs/guidelines/` folder, scan the index — load only what's needed for the task at hand.
3. Load **only the guidelines** the task needs (see "On-demand guidelines map" below if present).
4. Read the relevant `docs/knowledge-base/` chapter if the task touches domain logic.
5. Before coding, list:
   - Files to be created/modified
   - Guidelines consulted
   - Risks and edge cases

Never open every guideline up-front — load on demand. Keep the conversation lean.

---

## On-demand guidelines map

> Replace the rows below with this project's actual guideline files. Empty by default.

| Task | Guideline |
|---|---|
| Routing, navigation | `docs/guidelines/{{ROUTING}}.md` |
| Components, hooks | `docs/guidelines/{{COMPONENTS}}.md` |
| Types, generics | `docs/guidelines/{{TYPESCRIPT}}.md` |
| Styling | `docs/guidelines/{{STYLING}}.md` |
| Forms, validation | `docs/guidelines/{{FORMS}}.md` |
| Database / persistence | `docs/guidelines/{{DB}}.md` |
| State management | `docs/guidelines/{{STATE}}.md` |
| Tests, mocks | `docs/guidelines/{{TESTING}}.md` |
| i18n / localization | `docs/guidelines/{{I18N}}.md` |
| Observability | `docs/guidelines/{{OBSERVABILITY}}.md` |
| Security / privacy | `docs/guidelines/{{SECURITY}}.md` |
| Lint, format, hooks | `docs/guidelines/{{LINT_FORMAT}}.md` |
| Git workflow, PRs | `docs/guidelines/{{GIT}}.md` |

---

## When to load global skills

- New feature or non-trivial change → start with `/bymax-workflow:brainstorm` (if vague) or `/bymax-workflow:plan` (if clear).
- Implementation → `/bymax-quality:tdd` for new code, `tester` for adding tests to existing code.
- Before declaring done → `/bymax-workflow:verify`.
- Before commit / PR → `/bymax-quality:code-review` and `/security-review`.
- Cloud review calibration → root `REVIEW.md` (generate or refresh with `/bymax-quality:review-md`).
- Reference for any universal rule → `/bymax-workflow:standards`.

---

## When in doubt

Security and privacy win. Universal `/bymax-workflow:standards` win over personal preference. This project file wins over `/bymax-workflow:standards`. A rule you think is wrong → open an ADR, don't silently work around it.
