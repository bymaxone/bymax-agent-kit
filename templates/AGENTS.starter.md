# AGENTS.md — {{PROJECT_NAME}}

Complete spec for AI coding agents working on {{PROJECT_NAME}}. Read before starting any non-trivial task. For a faster skim, start with [CLAUDE.md](CLAUDE.md).

---

## 📖 How to read this document

1. **`CLAUDE.md`** — quickest rule summary. Open every session.
2. **This doc** — Critical Rules + Common Pitfalls. Open for any task that isn't a one-line fix.
3. **`docs/guidelines/`** — one guideline per stack area. Open **only** the ones your task touches.
4. **`docs/knowledge-base/`** — product specs, architecture, business rules, observability, privacy. Open when domain questions come up.

Never open every guideline. Always load on demand using the [Reference documentation](#-reference-documentation) table.

---

## 🗂️ Table of Contents

- [🚨 Critical Rules](#-critical-rules)
- [🎯 Project Overview](#-project-overview)
- [🧱 Stack](#-stack)
- [🏗️ Architecture](#-architecture)
- [📁 Project Structure](#-project-structure)
- [📐 Code Standards](#-code-standards)
- [🔄 Feature Workflow](#-feature-workflow)
- [🧪 Testing](#-testing)
- [🌍 Internationalization (i18n)](#-internationalization-i18n)
- [📊 Observability](#-observability)
- [🛡️ Security & Privacy](#-security--privacy)
- [⚠️ Common Pitfalls & Anti-patterns](#-common-pitfalls--anti-patterns)
- [✅ Pre-commit Checklist](#-pre-commit-checklist)
- [📚 Reference Documentation](#-reference-documentation)
- [🌐 External Documentation](#-external-documentation)

---

## 🚨 Critical Rules

Non-negotiable. Violation blocks merge.

### 1. {{Project-specific top rule}}

> Examples:
> - **Local-first health data** — Dose values, medication names, applied times… **never** leave the device except via user-initiated share.
> - **Multi-tenant isolation** — Every operation scoped by `tenantId`, extracted from validated JWT.
> - **PCI / payments** — Never log full card numbers, CVVs, or PANs.

See [docs/guidelines/{{relevant}}.md](docs/guidelines/{{relevant}}.md).

### 2. TypeScript strict

- `strict: true`, `noUncheckedIndexedAccess: true`.
- **Never** `any`, `// @ts-ignore`, `// @ts-expect-error`, `as any`.
- **Never** `// eslint-disable` (inline or file-level). Fix the source.

See [docs/guidelines/typescript-guidelines.md](docs/guidelines/typescript-guidelines.md) and [docs/guidelines/lint-format-guidelines.md](docs/guidelines/lint-format-guidelines.md).

### 3. Comments in English + documentation mandatory

- Every code comment, JSDoc, and inline note in English.
- User-facing strings through `t()` — never hardcoded. See [docs/guidelines/i18n-guidelines.md](docs/guidelines/i18n-guidelines.md).
- **File-header JSDoc** on every non-trivial file: purpose, layer, constraints.
- **JSDoc block on every exported** function, hook, component, service, query, store — with `@param`, `@returns`, `@throws` where relevant.
- **Inline comments** explain the *why* where the code is non-obvious (business rule, platform quirk, workaround link).
- **Every test `it`** carries a JSDoc block explaining the scenario and the rule it protects.
- **Stale comments are bugs**. Update comments in the same commit as the code.

### 4. No cross-feature imports

`features/{{X}}/` does not import from `features/{{Y}}/`. Share via `shared/` or orchestrate in a hook/service one level up.

### 5. `shared/ui/` is portable

Zero domain imports, zero dependency on `features/`. Designed to extract as a separate package. Feature code overrides via `className`, never by forking a primitive.

### 6. {{Project-specific design rule}}

> Examples:
> - "Lime primary, never cyan — cyan belongs to umbrella brand"
> - "Brand blue (#0066FF) only via Tailwind token, never hardcoded"
> - "Material 3 design tokens — no custom one-offs"

### 7. {{Project-specific safety rule}}

> Examples:
> - "Dose field is blank on new application — never autofill medical-safety-critical numeric inputs"
> - "Money fields default to 0, never undefined or null"

### 8. No banned dependencies

See [Banned dependencies](#banned-dependencies) below for the full list.

### 9. Git

> Replace with your project's policy. Example:
> - "Never execute git commands. Prepare them as suggestions. The user runs them."

Conventional Commits grammar (`feat(scope): …`, `fix(scope): …`). See [docs/guidelines/git-workflow.md](docs/guidelines/git-workflow.md).

---

## 🎯 Project Overview

**{{PROJECT_NAME}}** is **{{ONE-PARAGRAPH WHAT IT IS}}**.

- **Target user**: {{persona}}
- **Primary flows**: {{flow 1}}, {{flow 2}}, {{flow 3}}
- **Business model**: {{free / paid / freemium / subscription / etc.}}

Full spec: [docs/overview.md](docs/overview.md). Feature spec: [docs/knowledge-base/02-feature-spec.md](docs/knowledge-base/02-feature-spec.md). User journeys: [docs/knowledge-base/01-user-journeys.md](docs/knowledge-base/01-user-journeys.md).

---

## 🧱 Stack

Versions pinned in `package.json`. Full rationale: [docs/knowledge-base/08-stack.md](docs/knowledge-base/08-stack.md).

| Area            | Tech                                |
| --------------- | ----------------------------------- |
| Meta framework  | {{e.g., Next.js 16 / Expo SDK 55}}  |
| Routing         | {{e.g., App Router / expo-router}}  |
| Runtime         | {{e.g., Node 24+ / RN 0.85}}        |
| UI runtime      | React {{VERSION}}                   |
| Language        | TypeScript {{VERSION}} strict       |
| Styling         | {{Tailwind / NativeWind / Chakra}}  |
| State           | {{Zustand / Redux / Jotai}}         |
| Forms           | React Hook Form 7 + Zod 4           |
| Persistence     | {{Postgres + Prisma / SQLite + Drizzle / DynamoDB}} |
| KV / cache      | {{Redis / MMKV / IndexedDB}}        |
| i18n            | i18next + {{react-i18next}}         |
| Observability   | {{Sentry / Datadog / PostHog}}      |
| Tests           | {{Jest + RNTL / Vitest + RTL}}      |
| Lint            | ESLint 9 flat config + Prettier 3   |
| Hooks           | Husky 9 + lint-staged + commitlint  |
| Package manager | pnpm 9+ (Node 24+)                  |

### Banned dependencies

- `crypto` → use `node:crypto`
- `bcrypt` / `bcryptjs` → use `argon2`
- `crypto-js`, `md5` → use `node:crypto` / WebCrypto
- `uuid`, `nanoid` → use `crypto.randomUUID()`
- `moment` → use `date-fns`
- `lodash` (default entry) → native ES methods
- {{Other project-specific bans}}

---

## 🏗️ Architecture

```
{{ASCII or Mermaid showing layers / data flow / module boundaries}}

   Cross-cutting (src/shared/*):
   ui/ · i18n/ · theme/ · observability/ · utils/ · config/
```

Layers are strictly top-down. UI never imports services directly — always through a hook. Services never call React, navigation, or toast — that's the hook's job. See [docs/knowledge-base/07-layers.md](docs/knowledge-base/07-layers.md).

---

## 📁 Project Structure

```
{{project-name}}/
├── app/                         {{Routes / entry points}}
│   ├── _layout.tsx              root layout, providers
│   ├── (group)/                 {{describe groups}}
│   └── +not-found.tsx
├── src/
│   ├── features/                domain code (one folder per feature)
│   │   ├── {{feature1}}/
│   │   ├── {{feature2}}/
│   │   └── ...
│   ├── shared/                  cross-cutting
│   │   ├── ui/                  portable primitives
│   │   ├── db/                  client + schema + migrations
│   │   ├── i18n/                bundles + helpers
│   │   ├── theme/               tokens + provider
│   │   ├── observability/       Sentry/PostHog wrappers
│   │   ├── storage/             KV + local userId
│   │   ├── utils/               date, format, uuid, validation
│   │   └── config/              env, constants
│   └── assets/                  fonts, images
├── docs/
│   ├── overview.md              executive summary (source of truth)
│   ├── plan.md                  roadmap and phases
│   ├── knowledge-base/          product + technical specs
│   ├── decisions/               ADRs
│   ├── guidelines/              ← stack + workflow guidelines (load on demand)
│   ├── operations/              runbooks
│   └── tasks/                   sprint planning
├── tests/
├── scripts/
├── .github/
├── eslint.config.js             ESLint flat config
├── commitlint.config.js
└── tsconfig.json
```

**Rules**:

- `app/` is thin — route files under ~40 lines.
- `src/features/<name>/` self-contained: `components/`, `hooks/`, `services/`, `queries.ts`, `schemas.ts`, `types.ts`, `index.ts` (barrel).
- `src/shared/ui/` has zero domain imports.
- Path aliases only: `@/*` → `src/*`, `@app/*` → `app/*`, `@tests/*` → `tests/*`.
- No `../../` beyond one level.

---

## 📐 Code Standards

### Naming

| Kind                | Convention                     | Example                                |
| ------------------- | ------------------------------ | -------------------------------------- |
| Component file      | PascalCase                     | `UserCard.tsx`                         |
| Hook                | camelCase `use*`               | `useUserProfile.ts`                    |
| Service             | camelCase descriptive          | `calculateScore.ts`                    |
| Query               | camelCase `insert/get/update`  | `insertUser`                           |
| Top-level constant  | UPPER_SNAKE                    | `MAX_RETRIES`                          |
| Type / Interface    | PascalCase                     | `User`, `UserFormValues`               |
| Union literal value | snake_case                     | `'pending' \| 'in_progress'`           |
| Folder              | kebab-case                     | `user-profile/`                        |
| Analytics event     | snake_case                     | `user_signed_up`                       |
| DB column           | snake_case                     | `created_at`                           |
| DB table            | plural snake_case              | `users`, `user_sessions`               |
| Boolean             | `is/has/should/can` prefix     | `isLoading`, `canDelete`               |

### Formatting

- Single quotes, semicolons, 2-space indent, 100-col wrap, trailing comma `'all'`.
- Managed by Prettier 3 — do not hand-format.

### Imports

1. Built-in / external
2. Internal absolute (`@/...`, `@app/...`, `@tests/...`)
3. Types
4. Parent (one level max)
5. Sibling

Groups separated by blank lines, alphabetical inside groups. `eslint-plugin-import` enforces.

### Types over enums

Union literals + `as const` objects. No `enum` unless re-exporting from a third-party lib.

### Zod at boundaries

Every external input (user form, deep link param, network response, DB read that crosses a trust boundary) validates through Zod. Infer the TS type from the schema.

### Error handling

- Internal code trusted — don't re-validate what the type guarantees.
- External boundaries validate and `try/catch`.
- Never swallow errors — always `captureError` or re-throw.
- Toast for UI, exception for observability.

### Comments & documentation — required

This codebase is maintained by humans **and** AI agents. Thorough documentation is how we keep the loop healthy.

- **File header** on every non-trivial file — purpose, layer, constraints.
- **JSDoc** on every exported function, hook, component, service, query, store — with `@param`, `@returns`, `@throws` and a short "why" paragraph when the behavior isn't obvious.
- **Inline comments** where the code is non-obvious: a constraint, a platform quirk, a business rule, a workaround (link the issue).
- **Tests**: every `it` gets a JSDoc block describing the scenario and the rule it protects.
- **English only**. User-facing strings live in i18n bundles.
- **Keep fresh**. Stale comments are bugs — update in the same commit.

---

## 🔄 Feature Workflow

When adding or modifying a feature, follow the **Bymax Agent Kit workflow**:

1. **Vague idea?** → `/brainstorm` to refine.
2. **Big multi-phase feature?** → `/spec` → `/roadmap` → `/phase-tasks` → `/task`.
3. **Single PR?** → `/plan` → execute → `/verify` → `/code-review`.
4. **Just adding tests to existing code?** → use the `tester` skill.

For all paths:

1. **Check the design system** — [docs/guidelines/design-system-guidelines.md](docs/guidelines/design-system-guidelines.md).
2. **Confirm schema** if DB-touching — [docs/knowledge-base/06-data-model.md](docs/knowledge-base/06-data-model.md).
3. **Start with the service** — write the pure logic first, test it.
4. **Add the query** — in `src/features/<name>/queries.ts` (if applicable).
5. **Write the hook** — orchestrates service + toast + analytics + navigation.
6. **Build the component** — uses `src/shared/ui/` primitives.
7. **Wire the route** — `app/<path>.tsx`, under 40 lines.
8. **Add i18n keys** — primary locale first, then translations.
9. **Update docs** — if a new external dep, update [docs/knowledge-base/08-stack.md](docs/knowledge-base/08-stack.md). If a new pattern, consider a new guideline.
10. **`/verify` → `/security-review` → `/code-review`** before commit.

For complex refactors, produce a plan doc in `docs/tasks/` before touching code.

---

## 🧪 Testing

Pyramid:

```
  E2E ({{X}}% — {{tool: Playwright / Maestro / Detox}})
  Component ~20%
  Integration ~60% — queries, services with deps
  Unit — 100% for pure services
```

Priority: **100% coverage** on critical pure services. Integration coverage on the queries any dashboard reads. One component test per critical flow.

Commands:

```bash
{{PKG_MGR}} test                # full suite
{{PKG_MGR}} test --watch        # watch
{{PKG_MGR}} test path/to/file   # single
{{PKG_MGR}} test:ci             # CI mode, coverage
```

Patterns, mocks, fixtures, and the **mandatory `it` comment policy**: [docs/guidelines/testing-guidelines.md](docs/guidelines/testing-guidelines.md).

---

## 🌍 Internationalization (i18n)

> Replace if your project isn't multilingual.

- Locales: {{`pt-BR` (primary), `en`, `es`}}.
- Every visible string goes through `t()`. No exceptions.
- Keys in English, kebab-hierarchical: `app.log.dose.label`.
- Pluralization via `_one` / `_other` suffixes.
- Bundle parity enforced by `{{PKG_MGR}} check:i18n`.
- Types generated via `{{PKG_MGR}} i18n:types`.

Full reference: [docs/guidelines/i18n-guidelines.md](docs/guidelines/i18n-guidelines.md).

---

## 📊 Observability

- **Analytics**: `track(EVENT.name, props)` — wrapper strips unknown props. Allowlist in `src/shared/observability/events.ts`.
- **Errors**: `captureError(err, context)` — Sentry/Datadog with sanitization. Use in every non-terminal catch.
- **Identity**: SHA256 hash of local UUID. Never raw UUID, never email, never name.
- **Opt-outs**: separate toggles in Settings for analytics and error reporting.

See [docs/guidelines/observability-guidelines.md](docs/guidelines/observability-guidelines.md).

---

## 🛡️ Security & Privacy

One dedicated guideline. Read before any code that touches user data, external SDKs, or files: [docs/guidelines/security-privacy-guidelines.md](docs/guidelines/security-privacy-guidelines.md).

Highlights:

- {{Project-specific privacy posture, e.g., "No PII off device", "Tenant isolation enforced at architecture level"}}.
- Telemetry opt-outable, allowlisted, anonymous.
- Secrets only in `.env` (gitignored), validated via Zod at boot.
- "Delete all data" is a one-tap complete wipe (LGPD / GDPR Art. 17).
- Constant-time comparisons (`crypto.timingSafeEqual`) for any secret comparison.
- Banned imports enforced via ESLint `no-restricted-imports` (see [Banned dependencies](#banned-dependencies)).

---

## ⚠️ Common Pitfalls & Anti-patterns

> Replace with your project's real anti-patterns. This list saves agents (and humans) from repeating mistakes.

### 🔐 Security / privacy

1. **Logging sensitive values** — never. Coarse only ({{e.g., `dose_unit` not `dose_value`, `tier` not `email`}}).
2. **Raw UUID in analytics** — always hash via `getDistinctId()`.
3. **Hardcoded secrets** — `.env` only, accessed via typed `Env`.
4. **Missing opt-out check** — use `track()` / `captureError()` wrappers; they enforce opt-out.
5. **New external SDK without privacy review** — document in knowledge-base, disable auto telemetry.

### 🏗️ Architecture

6. **Cross-feature imports** — use `shared/` or orchestrate in a hook.
7. **Service importing React/hook/navigation** — services are pure. Move the side effect to the hook.
8. **`shared/ui/` importing from `features/`** — breaks portability. Never.
9. **Route file with business logic** — keep it thin; extract to feature.
10. **New top-level dep without updating `docs/knowledge-base/08-stack.md`** — catalog drift kills review value.

### 🖥️ Frontend

> Adapt to your stack. Examples for React Native:

11. **`TouchableOpacity`** — use `Pressable`.
12. **Text outside `<Text>`** — iOS crashes, Android silent. Always wrap.
13. **`ScrollView` + `.map()` for long lists** — use `FlatList`.
14. **Hardcoded hex** — add to `tailwind.config.js` first.
15. **Dynamic `className` strings** — JIT can't see them. Use full literals + `cx()`.

### 🗄️ Data

16. **Raw SQL** — always use the ORM.
17. **Auto-increment IDs** — UUID v4 via `crypto.randomUUID()`.
18. **Missing index on FK** — slow dashboards.
19. **Mutating query results expecting downstream immutability** — clone first.
20. **`delete` without `where`** — wipes a table. Always scope.
21. **Hard delete without prior archive** — two-step by policy.

### 📝 Forms

22. **Defaulting safety-critical fields** — leave blank. No autofill.
23. **Schema re-created every render** — memoize with `useMemo(..., [t])`.
24. **`mode: 'onChange'`** on create flows — use `'onTouched'`.
25. **Swallowing errors in the hook** — `handleSubmit` hides rejections. Always `try/catch`.

### 🌍 i18n

26. **Hardcoded strings in JSX, alerts, notifications** — always `t()`.
27. **Dynamic keys** (`t(\`status.\${v}\`)`) — use a map.
28. **Missing `_one` / `_other`** — counts render weirdly.
29. **Merging without `{{PKG_MGR}} check:i18n`** — key drift ships to prod.

### 🧪 Testing

30. **Snapshots for arbitrary objects** — use focused assertions.
31. **Mocking the ORM** — use in-memory DB.
32. **Ignored `act()` warnings** — always a real bug.
33. **Date-dependent tests without fake timers** — pin time.
34. **`it` without a block comment** — every `it` gets a JSDoc explaining the scenario and rule it protects. Test names alone are not enough.

### 📝 Documentation

35. **Missing file-header JSDoc** — every non-trivial file starts with a purpose/layer block.
36. **Missing JSDoc on exports** — every exported symbol has a block.
37. **Stale comments** — updating behavior without updating the comment. Both change in the same commit.
38. **Comments in non-English** — English only. Always.

### 🎨 Design system

39. **Off-palette color** — only theme tokens.
40. **Missing accessibility label on icon-only button** — a11y failure.
41. **Touch target < 44×44** — mobile a11y violation.
42. **Missing empty state** — never render a blank list.
43. **Missing skeleton** — spinners only for inline button states.

---

## ✅ Pre-commit Checklist

Run:

```bash
{{PKG_MGR}} type-check
{{PKG_MGR}} lint
{{PKG_MGR}} format:check
{{PKG_MGR}} test --passWithNoTests
{{PKG_MGR}} check:i18n        # if multilingual
```

Manual sweep on diff:

- [ ] No `console.log` / `console.warn` / `console.error` (use `captureError` for errors).
- [ ] No `any`, no `@ts-ignore`, no `@ts-expect-error`, no `eslint-disable`.
- [ ] All comments in English.
- [ ] File-header JSDoc on every new non-trivial file (purpose, layer, constraints).
- [ ] JSDoc on every new exported function / hook / component / service (`@param`, `@returns`, `@throws`).
- [ ] Every new test `it` has a block JSDoc describing the scenario and the rule it protects.
- [ ] No stale comments — updated in the same commit as the behavior change.
- [ ] All user-facing strings via `t()`.
- [ ] No hex literals outside `tailwind.config.js`.
- [ ] No `../../` beyond one level.
- [ ] No cross-feature imports.
- [ ] {{Project-specific check (PII, dose, tenant scoping, etc.)}}.
- [ ] New external deps reflected in `docs/knowledge-base/08-stack.md`.
- [ ] If new user-facing feature: i18n keys in all bundles.
- [ ] If new DB schema: migration generated and reviewed.
- [ ] Accessibility: roles, labels, touch targets ≥ 44×44, color contrast ≥ AA.

---

## 📚 Reference Documentation

**Open guidelines on demand.** The agent should open only the files needed for the current task.

### Stack guidelines (`docs/guidelines/`)

> Replace rows with this project's actual guideline files.

| Domain                          | When to read                                                 |
| ------------------------------- | ------------------------------------------------------------ |
| {{routing-guidelines.md}}       | Before modifying `app/`, routing, deep linking               |
| react-guidelines.md             | Before any component, hook, list                             |
| typescript-guidelines.md        | Before typing anything non-trivial                           |
| {{styling}}-guidelines.md       | Before any `className`, new token, dark-mode variant         |
| design-system-guidelines.md     | Before any new screen or component                           |
| {{orm}}-guidelines.md           | Before any schema change, query, migration                   |
| storage-guidelines.md           | Before reading/writing settings or flags                     |
| state-guidelines.md             | Before creating or modifying a store                         |
| forms-guidelines.md             | Before any form (RHF + Zod)                                  |
| i18n-guidelines.md              | Before any user-facing string                                |
| observability-guidelines.md     | Before any analytics or error capture                        |
| security-privacy-guidelines.md  | Before any code near user data or external SDK               |
| testing-guidelines.md           | Before writing any test                                      |
| lint-format-guidelines.md       | Before modifying ESLint / Prettier / hooks                   |
| coding-style.md                 | Overall codebase style + mandatory code documentation policy |
| git-workflow.md                 | Before opening or closing any piece of work                  |
| pr-review.md                    | Before giving PR approval                                    |
| agent-handoff.md                | Before or when dispatching work to another agent             |

### Knowledge base (`docs/knowledge-base/`)

| File                       | Contents                                                 |
| -------------------------- | -------------------------------------------------------- |
| 01-user-journeys.md        | Personas, flows, onboarding sequence                     |
| 02-feature-spec.md         | Feature by feature requirements, premium polish patterns |
| 03-copywriting.md          | Voice, tone, canonical copy                              |
| 04-business-rules.md       | Domain logic, edge cases                                 |
| 05-folder-architecture.md  | Complete directory layout + conventions                  |
| 06-data-model.md           | DB schema, FK map, seeding                               |
| 07-layers.md               | Layer rules and testability matrix                       |
| 08-stack.md                | Dependency catalog + rationale + banned list             |
| 09-i18n.md                 | Locale strategy, bundle layout                           |
| 10-notifications.md        | Scheduling strategy, capacity limits                     |
| 11-observability.md        | Analytics events, error workflows                        |
| 12-export.md               | PDF/CSV pipeline, schema of exports                      |
| 14-accessibility.md        | WCAG AA requirements                                     |
| 15-security-privacy.md     | Privacy posture + LGPD / GDPR compliance                 |
| 16-success-metrics.md      | KPIs, definition of done per feature                     |

### Decisions (`docs/decisions/`)

ADRs documenting non-obvious choices. Read before challenging a convention.

### Other

- [docs/overview.md](docs/overview.md) — executive summary, source of truth for strategy
- [docs/plan.md](docs/plan.md) — roadmap and phases
- [docs/operations/](docs/operations/) — release runbooks

---

## 🌐 External Documentation

Canonical upstream docs. Consult when the project guidelines don't answer a specific API question.

> Replace with the actual upstream docs for your stack.

- [{{Framework}} docs]({{url}})
- [TypeScript {{VERSION}}](https://www.typescriptlang.org/docs/)
- [React {{VERSION}}](https://react.dev)
- [{{ORM}}]({{url}})
- [Zustand](https://zustand.docs.pmnd.rs/) / Redux Toolkit / Jotai
- [React Hook Form](https://react-hook-form.com/docs)
- [Zod](https://zod.dev)
- [i18next](https://www.i18next.com)
- [Sentry]({{url}}) / Datadog / PostHog
- [Jest](https://jestjs.io/docs/getting-started) / Vitest
- [ESLint flat config](https://eslint.org/docs/latest/use/configure/configuration-files-new)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

**Consistency, privacy, and polish are non-negotiable. When conventions conflict, privacy wins.**
