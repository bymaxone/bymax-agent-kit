---
name: standards
description: Universal coding standards reference (TypeScript and Rust tracks) — simplicity ladder (reuse-first / YAGNI, run before writing code), type/lint discipline, naming conventions, doc policy (JSDoc / rustdoc), layered architecture, typed error handling, English-only comments, conventional commits. Load this BEFORE writing any non-trivial code, reviewing a PR, or scaffolding a new project. Other skills (/bymax-workflow:plan, /bymax-quality:tdd, /bymax-quality:code-review, /bymax-bootstrap:bootstrap) reference this.
user-invocable: true
---

# Universal Coding Standards

The single source of truth for the rules that apply to **every** project, regardless of stack. Stack-specific rules (NativeWind, Drizzle, Next.js routing, etc.) live in the project's own `CLAUDE.md` / `AGENTS.md`. This document is the universal layer underneath.

When in doubt, this doc wins over personal preference. Project-specific docs win over this doc.

### Which track applies

Detect the stack and follow the matching track:

- **TypeScript / JavaScript** (`package.json` / `tsconfig.json` present) → **§1–§14** below.
- **Rust** (`Cargo.toml` present) → **§15 Rust track**. The universal principles — document every public item, English + timeless comments, zero suppression, layered modules, typed errors, the security baseline — still hold; §15 expresses them in Rust idioms and replaces the TS-specific mechanics (tsconfig, JSDoc, ESLint, Tailwind).

§0 (Simplicity ladder), §9 (Conventional Commits), §10 (Performance — measure first), §11 (Accessibility, for any UI), and §14 (conflict resolution) are stack-neutral and apply everywhere.

---

## 0. Simplicity ladder — run BEFORE writing code

Understanding comes first: read the code the change touches and trace the real flow. Then, before writing anything, stop at the **first rung that holds**:

1. **Does this need to exist?** No → skip it (YAGNI). Don't build for hypothetical futures.
2. **Already in THIS codebase?** → reuse it. Search before writing: if the project has a knowledge graph (`graphify-out/` present), prefer scoped graph queries — `graphify query "<need>"`, `graphify explain "<symbol>"`, `graphify path A B` — over grepping: they answer "does something already do this?" at a fraction of the tokens and resolve cross-file/cross-package links. `grep`/Glob is the fallback when no graph exists, **and remains the authority for code changed since the last graph build** (the graph refreshes on commit, not on every edit). Either way: find the existing component, hook, util, service, or query that already does it (or nearly does — extend it instead).
3. **Already in one of your org's shared libs (e.g. `@bymax-one/*`) or a sibling project checkout?** → reuse the lib. If the code lives in a sibling repo and isn't published, **promote it to a shared lib** (or mirror the proven pattern) — never copy-paste-drift. If a knowledge-vault MCP is connected (e.g. Obsidian), check the stack's Patterns note for the established convention before inventing a new one. Declare your org's lib scope and sibling-repo locations in the project's `CLAUDE.md` so this rung is checkable.
4. **Stdlib / native platform does it?** → use it. `Intl` over date/number-formatting libs, `crypto.randomUUID()` over `uuid`, `URL`/`URLSearchParams` over manual parsing, `structuredClone` over a deep-clone dep, `<input type="date">` over a picker component, `fetch` + `AbortController` over an HTTP lib. (Rust: `std`/`core` before a new crate.)
5. **An installed dependency does it?** → use it. **Never add a new dependency to avoid writing ten lines** — a new dep needs justification (maintenance, popularity, license, security posture) and must pass the project's supply-chain policy.
6. **Will a second feature (or project) need this?** → build it **once, as a reusable unit**: `shared/ui` / `shared/utils` for cross-feature, promote to `@bymax-one/*` when a second project needs it. Minimal public API, zero domain imports, documented per §3.
7. **Only then:** write the minimum that works. If it fits in one clear line, one line is correct.

**Lazy, not negligent — never on the chopping block:** trust-boundary validation (§7), error handling (§7), the security baseline (§13), accessibility (§11), and the mandatory docs/tests (§3–§4). Code is small because it's *necessary*, not because it's golfed.

**Output economy is a side effect:** less generated code = fewer tokens, less to review, less to maintain. But minimal ≠ cryptic — naming (§2) and documentation (§3) always apply.

**Official docs beat trained memory:** when a rung lands on a library or platform API (rungs 3–5), verify the current official documentation before writing the call — via the Context7 MCP when connected, web search otherwise. Stacks evolve faster than any model's training data.

At review time, a rung violation is flagged by `/bymax-quality:code-review` (reimplementing something that already exists = HIGH).

---

## 1. TypeScript discipline

### Strict, always

`tsconfig.json` must have:

```jsonc
{
  "strict": true,
  "noUncheckedIndexedAccess": true,
  "noImplicitOverride": true,
  "noFallthroughCasesInSwitch": true,
  "noUnusedLocals": true,
  "noUnusedParameters": true,
  "forceConsistentCasingInFileNames": true,
  "isolatedModules": true
}
```

Weakening any of these is **not** a patch-level change. It needs a separate, justified PR.

### Stricter opt-ins (recommended for new projects, libraries, and security-critical code)

```jsonc
{
  "exactOptionalPropertyTypes": true,  // distinguishes `prop?: T` from `prop?: T | undefined`
  "verbatimModuleSyntax": true         // forces explicit `import type` — pairs with consistent-type-imports
}
```

These are stricter and may surface real issues on existing codebases. Turn them on at project start. For an existing project, plan the migration as a separate task — don't bundle into an unrelated PR.

### Zero `any`

If `any` shows up, something is wrong. Replacements:

- `unknown` when the type is genuinely unknown — refine with a guard before use.
- A type parameter when the function is generic.
- Import the upstream type from the library — never reinvent.

Banned forever: `// @ts-ignore`, `// @ts-expect-error`, `// @ts-nocheck`, `as any`, `as unknown as <T>` (when used to launder a real type error). See `/bymax-quality:code-review` and `/bymax-workflow:verify` for enforcement.

### `interface` vs `type`

- **`interface`** for entity-like shapes: component props, DB rows, service I/O.
- **`type`** for unions, intersections, mapped types, utility aliases, tuples.

```ts
interface UserProfile { id: string; email: string }
type Status = 'active' | 'archived' | 'pending';
type Handler = (value: string) => void;
```

### No `enum`

Prefer string literal unions:

```ts
type Theme = 'dark' | 'light' | 'system';
```

Exception: a legacy `enum` coming from a third-party library you can't change.

### Readonly where it matters

Arrays/objects that must not mutate → `readonly` / `ReadonlyArray<T>`. Literal constants with `as const`.

### Non-null assertions (`!`) are rare

Allowed only when the invariant is obvious and validated in the same closure (e.g., after `if (value)`). When used, add a one-line comment explaining the invariant.

---

## 2. Naming conventions

| Element | Convention | Example |
|---|---|---|
| Component file | PascalCase | `UserCard.tsx` |
| Hook | camelCase, `use*` | `useUserProfile.ts` |
| Service / pure fn | camelCase, descriptive | `calculateScore.ts` |
| DB query | camelCase, `get* / insert* / update* / delete*` | `insertUser` |
| Top-level constant | UPPER_SNAKE | `MAX_RETRIES` |
| Type / interface | PascalCase | `User`, `UserFormValues` |
| Union literal value | snake_case | `'pending' \| 'in_progress'` |
| Folder | kebab-case | `user-profile/` |
| Analytics event | snake_case | `user_signed_up` |
| DB column | snake_case | `created_at`, `email_address` |
| DB table | plural snake_case | `users`, `user_sessions` |

### Booleans

Start with `is`, `has`, `should`, or `can`:

```ts
const isLoading = false;
const hasPermission = true;
const shouldRefresh = false;
const canDelete = true;
```

### Async functions

`handle*` prefix for UI event handlers. Descriptive verb name in services.

```ts
const handleSubmit = async () => { /* ... */ };
async function fetchUserProfile(id: string): Promise<User> { /* ... */ }
```

---

## 3. Code documentation — MANDATORY

Future-you and every AI agent depends on this. No exceptions.

### File header

Every non-trivial source file starts with a JSDoc block:

```ts
/**
 * <One-sentence purpose>.
 *
 * Layer: <screen | component | hook | service | query | store | utility | config>.
 *
 * <Optional: important constraints, invariants, or non-obvious behavior the
 * reader must know that isn't visible from the code.>
 */
```

For trivial barrel files (`index.ts` re-exporting), one comment line is enough:

```ts
// Public API of the `user-profile` feature.
```

### Exported function / class / component / hook — JSDoc required

```ts
/**
 * <Imperative one-line summary — "Logs an event.", not "This function logs…">.
 *
 * <Optional why-paragraph for non-obvious behavior, edge cases, invariants.>
 *
 * @param paramName - What it represents and constraints.
 * @returns What is returned (omit for void).
 * @throws <ErrorType> when <condition> (omit if no thrown errors callers care about).
 */
```

### Inline comments — explain WHY

Add an inline comment when the code:
- Applies a non-obvious constraint (platform limit, third-party quirk).
- Works around a known bug — link the issue.
- Implements a business rule that isn't self-evident.
- Would surprise a reader (asymmetric branch, magic number).

```ts
// iOS limits scheduled local notifications to 64; cap at 40 to leave
// headroom for ad-hoc reminders. See <link>.
const MAX_SCHEDULED = 40;
```

**Never** restate the code:

```ts
// ❌ noise
// Increment the counter
counter++;
```

### Comment language

**English only.** No exceptions. User-facing strings live in i18n bundles.

### Stale comments

A wrong comment is worse than no comment. When you change behavior, update the comment in the same commit.

---

## 4. Test documentation — MANDATORY

(Mirrors `tester` and `/bymax-quality:tdd` skills — kept here as the universal reference.)

### Every test file has a header

```ts
/**
 * <Layer> tests for <SymbolName>.
 *
 * Layer: <unit | integration | component | hook>.
 * Goal: <what the suite verifies>.
 * Mocks: <list and why>.
 */
```

### Every `it` / `test` has a block comment

The comment must describe:
1. **What scenario** is being exercised.
2. **What is expected and why** — tie back to the rule it protects.
3. **Edge case tag** if relevant ("Empty input", "Boundary", "Race condition", "Regression for #123").

```ts
/**
 * Empty history edge case.
 *
 * When the user has no history, the algorithm must default to a
 * deterministic starting state — protecting the "new user" UX from
 * showing undefined.
 */
it('returns first preference when history is empty', () => { /* ... */ });
```

### Arrange / Act / Assert

Label the three phases when the body is non-trivial:

```ts
it('…', () => {
  // Arrange
  const input = build({ size: 8 });

  // Act
  const result = process(input);

  // Assert
  expect(result).toEqual(expected);
});
```

---

## 5. Layered architecture

```
app/             routes / entry points (thin, composition only)
src/features/*   feature code: components, hooks, services, queries
src/shared/*     portable: ui, utils, db, i18n, theme, observability
```

Direction of imports: **UI → components → hooks → services → queries → storage**. Top never imports bottom.

**No cross-feature imports.** `features/billing/` does not import from `features/auth/`. If they must talk, orchestrate one level up (in a hook or service in `app/` or `shared/`). Enforced via ESLint `no-restricted-imports`.

**Barrel files** export the public API only — never internals:

```ts
// src/features/user-profile/index.ts
export { UserCard } from './components/UserCard';
export { useUserProfile } from './hooks/useUserProfile';
export type { User } from './types';
// queries and internal services are NOT exported
```

`shared/ui/` has zero domain imports. It must be portable enough to extract as its own package later.

---

## 6. Imports

### Order (enforced by `eslint-plugin-import`)

1. Built-in (Node stdlib)
2. External (`react`, libs)
3. Internal aliases (`@/`, `@app/`, `@tests/`)
4. Parent (`../`)
5. Sibling (`./`)
6. Index (`./index`)

Blank line between groups. Alphabetical within each group.

### Path aliases

Always use aliases for internal imports — never `../../../`. Configure in both `tsconfig.json` (`paths`) and the bundler (Vite/Metro/Next).

```ts
// ✅
import { Button } from '@/shared/ui/Button';

// ❌
import { Button } from '../../../shared/ui/Button';
```

---

## 7. Error handling

- **Trust internal code.** Don't re-validate `undefined` where the type already guarantees it.
- **Validate at boundaries.** Network responses, user input, file reads, IPC — wrap in Zod (or equivalent) and `try/catch`.
- **Never swallow errors silently.** Always either:
  - Capture to observability (`captureError(err, { context })`), AND
  - Re-throw OR show a user-facing error (toast / banner / status response).
- **Toast for the UI, full stack for observability.** Users see a friendly message; engineers see the stack in Sentry/Datadog.

---

## 8. Suppression comments — ZERO tolerance

Banned: `// eslint-disable*`, `// @ts-ignore`, `// @ts-expect-error`, `// @ts-nocheck`, `as any`, `as unknown as <T>` to launder errors, CLI bypasses (`--no-verify`, `--force` on protected branches).

Only acceptable exception: a suppression that references a specific issue and has a time-bounded reason. Even then, the user must explicitly accept.

Fix the root cause. If the rule itself is wrong, change the rule config — don't scatter `disable` through the code.

---

## 9. Conventional Commits

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.

Subject: imperative mood, no trailing period, ≤ 100 chars total header.

Examples:
- `feat(auth): add passkey support`
- `fix(notifications): debounce permission prompt`
- `refactor(weight): extract trend calculator`
- `chore: bump expo to 55.0.18`

Enforced by `commitlint` + Husky `commit-msg` hook.

---

## 10. Performance

**Avoid premature optimization.** Measure first. Tools: profiler, Flamechart, Lighthouse, React DevTools Profiler.

Patterns that always apply:
- Use the platform's virtualized list (`FlatList`, `react-window`, `Virtuoso`) for long lists.
- `React.memo` only when proven by a profiler — not preemptively.
- `useMemo` / `useCallback` only when passing to a memoed child or to a stable-deps requirement.
- Don't ship oversized images.

---

## 11. Accessibility

- Every interactive element has a name (`accessibilityLabel` / `aria-label`) and a role.
- Touch / click target ≥ 44×44 px on mobile, ≥ 24px on desktop.
- State exposed (`accessibilityState` / `aria-*`) when the element has selected / disabled / checked / busy.
- Respect reduce motion / high contrast.
- Color contrast meets WCAG AA (≥ 4.5:1 body, ≥ 3:1 large).

---

## 12. Tailwind CSS conventions

Tailwind has two major versions in active use. Pick the right syntax for the project's version — **mixing them breaks the build**.

### Tailwind v4 (modern, recommended for new projects)

Uses **canonical class shortcuts** for two common patterns. Tailwind's language server emits a `suggestCanonicalClasses` warning when you write the long form — **always use the short form**.

#### CSS variable shorthand

```diff
- bg-[var(--surface)]                    ❌ verbose (works but warned)
+ bg-(--surface)                         ✅ canonical

- border-[var(--glass-border)]           ❌
+ border-(--glass-border)                ✅

- text-[var(--ink-base)]                 ❌
+ text-(--ink-base)                      ✅

- ring-[var(--lime-300)]                 ❌
+ ring-(--lime-300)                      ✅
```

Rule: **whenever the arbitrary value is exactly `var(--name)`, drop `[var(...)]` and use `(--name)`**. Applies to every utility (`bg-`, `text-`, `border-`, `ring-`, `outline-`, `decoration-`, `divide-`, `accent-`, `caret-`, `fill-`, `stroke-`, `from-`, `via-`, `to-`, etc.).

#### ARIA boolean canonical variants

When the variant is `aria-<name>=true`, use the canonical short variant (no brackets, no `=true`):

```diff
- aria-[invalid=true]:border-destructive            ❌
+ aria-invalid:border-destructive                   ✅

- aria-[disabled=true]:opacity-50                   ❌
+ aria-disabled:opacity-50                          ✅

- aria-[pressed=true]:bg-lime-300                   ❌
+ aria-pressed:bg-lime-300                          ✅
```

Canonical ARIA variants (memorize this set):

| Long form (don't use)       | Canonical (use this)  |
| --------------------------- | --------------------- |
| `aria-[invalid=true]:`      | `aria-invalid:`       |
| `aria-[disabled=true]:`     | `aria-disabled:`      |
| `aria-[pressed=true]:`      | `aria-pressed:`       |
| `aria-[expanded=true]:`     | `aria-expanded:`      |
| `aria-[hidden=true]:`       | `aria-hidden:`        |
| `aria-[selected=true]:`     | `aria-selected:`      |
| `aria-[checked=true]:`      | `aria-checked:`       |
| `aria-[busy=true]:`         | `aria-busy:`          |
| `aria-[modal=true]:`        | `aria-modal:`         |
| `aria-[required=true]:`     | `aria-required:`      |
| `aria-[readonly=true]:`     | `aria-readonly:`      |

**Composition** with other variants stays the same:

```diff
- aria-[invalid=true]:focus-visible:ring-destructive/30   ❌
+ aria-invalid:focus-visible:ring-destructive/30           ✅
```

The canonical variant **only** applies when matching `=true`. If you genuinely need `aria-checked=mixed` or `data-[state=open]`, **keep the long form** — those aren't booleans.

```ts
// Valid long forms (no canonical exists):
data-[state=open]:rotate-90
data-[orientation=vertical]:flex-col
aria-[checked=mixed]:bg-amber-200
```

#### Canonical numeric tokens (spacing / sizing)

When the arbitrary value matches an entry in Tailwind's default scale, **always use the token**. The language server emits the same `suggestCanonicalClasses` warning.

```diff
- min-w-[8rem]                 ❌ verbose
+ min-w-32                     ✅ canonical (32 × 0.25rem = 8rem)

- w-[16rem]                    ❌
+ w-64                         ✅

- h-[12rem]                    ❌
+ h-48                         ✅

- p-[1rem]                     ❌
+ p-4                          ✅

- gap-[2rem]                   ❌
+ gap-8                         ✅

- m-[0.5rem]                   ❌
+ m-2                          ✅

- top-[4rem]                   ❌
+ top-16                       ✅

- text-[1rem]                  ❌  (matches default `text-base`)
+ text-base                    ✅

- text-[1.5rem]                ❌
+ text-2xl                     ✅
```

**Default spacing scale** — each unit equals `0.25rem` (4px at 16px root):

| Token | rem | px |
|-------|------|-----|
| `0`   | 0     | 0    |
| `0.5` | 0.125 | 2    |
| `1`   | 0.25  | 4    |
| `2`   | 0.5   | 8    |
| `4`   | 1     | 16   |
| `8`   | 2     | 32   |
| `16`  | 4     | 64   |
| `24`  | 6     | 96   |
| `32`  | 8     | 128  |
| `48`  | 12    | 192  |
| `64`  | 16    | 256  |
| `96`  | 24    | 384  |

**Quick math**: `<token> = <rem-value> × 4`. So `8rem` → `8 × 4 = 32` → `min-w-32`.

This applies to **every utility** that uses the spacing scale: `p-`, `m-`, `gap-`, `space-`, `w-`, `h-`, `size-`, `min-w-`, `min-h-`, `max-w-`, `max-h-`, `top-`, `right-`, `bottom-`, `left-`, `inset-`, `translate-`, `scroll-`, `indent-`, `basis-`.

**Type scale tokens** (for `text-`):

| Arbitrary  | Canonical     |
| ---------- | ------------- |
| `[0.75rem]` | `text-xs`     |
| `[0.875rem]` | `text-sm`    |
| `[1rem]`   | `text-base`   |
| `[1.125rem]` | `text-lg`    |
| `[1.25rem]` | `text-xl`    |
| `[1.5rem]` | `text-2xl`    |
| `[1.875rem]` | `text-3xl`   |
| `[2.25rem]` | `text-4xl`    |
| `[3rem]`   | `text-5xl`    |

**Backdrop-blur / blur px scale** — use named tokens instead of `[Npx]` when the value is on the default filter scale:

| Arbitrary   | `backdrop-blur-*` token | `blur-*` token |
| ----------- | ----------------------- | -------------- |
| `[4px]`     | `backdrop-blur-xs`      | `blur-xs`      |
| `[8px]`     | `backdrop-blur-sm`      | `blur-sm`      |
| `[12px]`    | `backdrop-blur-md`      | `blur-md`      |
| `[16px]`    | `backdrop-blur-lg`      | `blur-lg`      |
| `[24px]`    | `backdrop-blur-xl`      | `blur-xl`      |
| `[40px]`    | `backdrop-blur-2xl`     | `blur-2xl`     |
| `[64px]`    | `backdrop-blur-3xl`     | `blur-3xl`     |

**Z-index integers** — in v4, `z-[N]` (any non-negative integer) can drop the brackets: `z-[200]` → `z-200`, `z-[9999]` → `z-9999`.

**Negative zero** — `-{utility}-0` always equals `{utility}-0`. Always use the positive form: `-bottom-0` → `bottom-0`, `-top-0` → `top-0`, `-left-0` → `left-0`, `-right-0` → `right-0`, `-m-0` → `m-0`.

**When to keep `[Nrem]` arbitrary** (no canonical exists):

- Off-scale values: `w-[7.3rem]`, `mt-[1.7rem]`, `text-[0.94rem]`. The token closest may not match the design — keep arbitrary, but ideally extend `tailwind.config.js` with a project-named token.
- Calc / clamp / vars: `w-[calc(100%-2rem)]`, `text-[clamp(1rem,2vw,1.5rem)]`. Canonical doesn't apply.
- Logical project tokens: `bg-(--surface)` (CSS variable shorthand) — different rule, keep using.

**Don't fight the IDE**: if VS Code's Tailwind extension shows `(suggestCanonicalClasses)`, take the quickfix. The exception is when you've **intentionally** chosen an off-scale value and documented why.

#### Renamed utilities (v3 → v4)

Tailwind v4 renamed several utilities for consistency. **Use the new names from the start**. The language server emits the same `suggestCanonicalClasses` warning when it sees a v3 name in a v4 project.

##### Whole-scale shifts (the big ones)

The shadow, rounded, blur, drop-shadow, and backdrop-blur scales were **renumbered down one step** so every utility has a named value:

| v3 (don't use)           | v4 (use this)             |
| ------------------------ | ------------------------- |
| `shadow`                 | `shadow-sm`               |
| `shadow-sm`              | `shadow-xs`               |
| `drop-shadow`            | `drop-shadow-sm`          |
| `drop-shadow-sm`         | `drop-shadow-xs`          |
| `blur`                   | `blur-sm`                 |
| `blur-sm`                | `blur-xs`                 |
| `backdrop-blur`          | `backdrop-blur-sm`        |
| `backdrop-blur-sm`       | `backdrop-blur-xs`        |
| `rounded`                | `rounded-sm`              |
| `rounded-sm`             | `rounded-xs`              |

The `md/lg/xl/2xl/3xl` end of each scale stays the same — only the small end shifted.

##### Ring default changed (3px → 1px)

| v3                        | v4                           |
| ------------------------- | ---------------------------- |
| `ring` (was 3px)          | `ring-3` (explicit 3px)      |
| `ring-1`                  | `ring` (now the default 1px) |

If your design uses a 3px ring as default, replace bare `ring` with `ring-3`.

##### Renamed individual utilities

| v3 (don't use)            | v4 (use this)             | Why                                                                  |
| ------------------------- | ------------------------- | -------------------------------------------------------------------- |
| `bg-gradient-to-r`        | `bg-linear-to-r`          | v4 added `bg-radial-*` and `bg-conic-*`; "linear" disambiguates.    |
| `bg-gradient-to-l`        | `bg-linear-to-l`          | (same — applies to all 8 directions)                                |
| `bg-gradient-to-t`        | `bg-linear-to-t`          |                                                                      |
| `bg-gradient-to-b`        | `bg-linear-to-b`          |                                                                      |
| `bg-gradient-to-tr`       | `bg-linear-to-tr`         |                                                                      |
| `bg-gradient-to-tl`       | `bg-linear-to-tl`         |                                                                      |
| `bg-gradient-to-br`       | `bg-linear-to-br`         |                                                                      |
| `bg-gradient-to-bl`       | `bg-linear-to-bl`         |                                                                      |
| `outline-none`            | `outline-hidden`          | "none" was a misnomer — it actually keeps a transparent outline.    |
| `decoration-clone`        | `box-decoration-clone`    | Aligns with the CSS property name.                                  |
| `decoration-slice`        | `box-decoration-slice`    | Same.                                                                |
| `overflow-ellipsis`       | `text-ellipsis`           | The CSS property is `text-overflow`, not `overflow`.                |
| `flex-shrink-0`           | `shrink-0`                | Drop the `flex-` prefix.                                             |
| `flex-shrink`             | `shrink`                  |                                                                      |
| `flex-grow-0`             | `grow-0`                  |                                                                      |
| `flex-grow`               | `grow`                    |                                                                      |
| `bg-opacity-50`           | `bg-{color}/50`           | Opacity modifiers replace standalone opacity utilities.              |
| `text-opacity-50`         | `text-{color}/50`         | Same.                                                                |
| `border-opacity-50`       | `border-{color}/50`       | Same.                                                                |
| `divide-opacity-50`       | `divide-{color}/50`       | Same.                                                                |
| `placeholder-opacity-50`  | `placeholder-{color}/50`  | Same.                                                                |
| `ring-opacity-50`         | `ring-{color}/50`         | Same.                                                                |

##### How to find renames not listed here

Tailwind's canonical mappings are **dynamic** — they come from the project's design system, not a static list. To audit a real project:

1. **Run the official upgrade codemod** (the authoritative source):
   ```bash
   npx @tailwindcss/upgrade
   # Diffs every file it would change. Inspect the diff before accepting.
   ```
2. **Read the [Tailwind v4 Upgrade Guide](https://tailwindcss.com/docs/upgrade-guide)** for the latest list.
3. **Trust the IDE**: VS Code with the Tailwind extension shows `suggestCanonicalClasses` warnings inline — that's the same source of truth as `npx @tailwindcss/upgrade`.

#### Other Tailwind v4 niceties

- **`not-` modifier** for `:not()`: `not-disabled:hover:bg-accent` instead of `[&:not(:disabled):hover]:bg-accent`.
- **`has-` modifier** for `:has()`: `has-[input:checked]:border-primary` (this stays arbitrary because the inner selector varies).
- **Container queries**: `@container` and `@md:` style — built-in, no plugin needed.
- **3D transforms**: `translate-z-`, `rotate-x-`, `perspective-`.

### Tailwind v3 + NativeWind 4 (legacy / mobile)

NativeWind 4 ships against Tailwind 3.x. There **are no canonical shortcuts** — use the long form:

```ts
// Tailwind v3 — these are the correct forms:
bg-[var(--surface)]
border-[var(--glass-border)]
aria-[invalid=true]:border-destructive
```

Trying to use `bg-(--surface)` on Tailwind 3 will **fail to compile** — the parser doesn't recognize it. Don't migrate a v3 project's strings to v4 syntax until the project itself moves to Tailwind 4.

### Universal Tailwind rules (any version)

- **Never hardcode hex** in components — use a token (`bg-primary`, `text-ink-base`). Add new tokens to `tailwind.config.js`.
- **Never build dynamic class strings** the JIT can't see: `\`text-${size}\`` is invisible to the scanner. Use full literals + `cn()` / `clsx()` / `cx()`.
- **Group classes by intent** when wrapping: layout → spacing → sizing → typography → color → state → motion. (`prettier-plugin-tailwindcss` automates this.)
- **Avoid `!important`** (`!`) unless overriding a third-party style you can't otherwise reach. Document the reason inline.
- **Allowed utility plugins** (project decides):
  - `prettier-plugin-tailwindcss` (sort classes — universally recommended)
  - `eslint-plugin-tailwindcss` (lint — recommended for v4 projects)

### How to check the project's version

```bash
grep -E '"tailwindcss":' package.json
# "tailwindcss": "^4.x.x"  → use canonical shortcuts
# "tailwindcss": "^3.x.x"  → use long form
```

If the project also ships `nativewind`, it's almost certainly on Tailwind 3 (NativeWind doesn't have a v4-compatible release at the time of writing).

---

## 13. Security baseline

- Never commit secrets — `.env*` in `.gitignore`, secret scanner in CI.
- Validate every external input (network, file, IPC) — Zod or equivalent at the boundary.
- `eslint-plugin-security` enabled (regex DoS, eval, prototype pollution, child_process injection, non-literal `fs` paths).
- **Constant-time comparisons** for tokens/HMACs/passwords — `security/detect-possible-timing-attacks` is enabled by `security.configs.recommended`. Use `crypto.timingSafeEqual` instead of `===` for any secret comparison.
- **Banned imports** (enforced via `no-restricted-imports` in the universal ESLint base):
  - `crypto` → use `node:crypto` (prefixed form)
  - `bcrypt`, `bcryptjs` → use `argon2` via the project's hashing service
  - `crypto-js` → use `node:crypto` / WebCrypto
  - `md5` → use SHA-256 via `node:crypto`
  - `uuid`, `nanoid` → use `crypto.randomUUID()` (Node 18+ / WebCrypto)
- No PII / health data / credentials in logs or analytics — block via lint rule (`no-pii-in-observability` style).
- Dependency audit in CI (`pnpm audit` / `npm audit --omit=dev`).
- Pre-publish chain on libraries: `typecheck && lint && test && build` — fails if any gate fails.

---

## 14. When this guide conflicts with…

- **The project's `CLAUDE.md`**: project wins.
- **A tool's default config**: this guide wins (override the tool).
- **Personal preference**: this guide wins.
- **A rule that's actually wrong for the codebase**: open an ADR, raise it in the PR. Don't silently work around it.

---

## 15. Rust track (when the project is Rust)

Applies when `Cargo.toml` is present. Replaces the TypeScript-specific mechanics of §1–§8 and §12–§13 with their Rust equivalents — the *principles* are identical.

### 15.1 Rust discipline

- **Edition + MSRV pinned.** `edition` and `rust-version` (MSRV) in `[workspace.package]`; a committed `rust-toolchain.toml` pins the toolchain (channel + components + targets). An MSRV bump is a deliberate, visible PR.
- **`cargo clippy --workspace --all-targets --all-features -- -D warnings` is clean** (clippy-as-error ≈ `eslint -D`), and **`cargo fmt --all --check`** is clean (≈ Prettier) — both CI-gating.
- **No `unwrap()` / `expect()` / `panic!` / `todo!()` / `unimplemented!()` on library paths** — the Rust analogue of an unhandled throw. Return a typed `Result<T, E>` and propagate with `?`. Test/bench/build code may use them; `src/` library code may not.
- **Typed errors only.** One error enum per crate via `thiserror` (`AuthError` / `ConfigError` / `RepositoryError`); no stringly-typed errors. `anyhow` is fine in bins/tests, never in a library's public API (it erases the type).
- **`#![forbid(unsafe_code)]` on every crate.** The sole sanctioned exception is an FFI / `wasm-bindgen` binding, which uses `#![deny(unsafe_op_in_unsafe_fn)]` and confines `unsafe` to the boundary with a `// SAFETY:` comment on every block.
- **Strong types over primitives** — newtypes/enums over boolean traps and magic strings; builders for complex construction.

### 15.2 Naming

| Element | Convention | Example |
|---|---|---|
| Module / file | snake_case | `token_service.rs` |
| Function / method / variable | snake_case | `verify_password` |
| Type / trait / enum | PascalCase | `AuthEngine`, `SessionStore` |
| Enum variant | PascalCase | `AuthError::InvalidCredentials` |
| Constant / static | SCREAMING_SNAKE | `MAX_SESSIONS` |
| Crate dir / path | kebab-case / snake_case | `bymax-auth-core` → `bymax_auth_core` |
| Cargo feature | kebab-case | `oauth-reqwest` |

Booleans read as predicates (`is_*`, `has_*`, `should_*`, `can_*`). Conversions follow the standard convention: `as_*` (cheap borrow), `to_*` (clone/expensive), `into_*` (consuming).

### 15.3 Documentation — MANDATORY (the rustdoc equivalent of §3)

- **`#![deny(missing_docs)]`** on every public crate; each crate opens with a `//!` crate-level doc.
- Every **public item** (`pub fn` / `struct` / `enum` / `trait` / `mod`) carries a `///` doc: imperative one-line summary, then `# Errors` (when it returns `Err`), `# Panics` (if it can), `# Safety` (for `unsafe fn`), and a runnable `# Examples` block (compiled as a doctest) on important items.
- **Inline `//` comments explain WHY** (invariants, security ordering, third-party quirks) — never restate the code.
- **English + timeless.** No comment references a plan phase / task / sprint. `docs/` prose may be the project's language; code comments are English.

### 15.4 Tests — MANDATORY (mirrors `tester` / `/bymax-quality:tdd`)

- Unit tests in `#[cfg(test)] mod tests` in the same file; integration tests in `tests/`. Run `cargo test --workspace`.
- **Every `#[test]` carries a block comment** (English) naming the scenario and the rule/invariant it protects — identical policy to the `tester` skill, expressed for `#[test]`.
- **Coverage via `cargo-llvm-cov`** (100% on logic crates); `proptest` for parser/round-trip properties; `cargo-mutants` as a pre-release gate; doctests run in CI. Never `#[ignore]` a test to silence a failure.

### 15.5 Modules, crates & imports (the §5 layering)

- A framework-agnostic core depends on **no** adapter/infra crate; adapters (HTTP, store backends) depend on the core, never the reverse. No crate reaches across its single responsibility.
- `pub use` re-exports define a crate's public API; internal modules stay private (`mod`, not `pub mod`). The facade re-export is the Rust analogue of a barrel file.
- Imports grouped std → external → crate-internal.

### 15.6 Error handling (the §7 principles in Rust)

- Validate at boundaries (`serde` + a validator like `garde` in the adapter, never the core); trust the type system internally.
- **Never swallow an error.** Propagate with `?`, map to a typed variant, or log via `tracing` and surface. An empty match arm or `let _ = result;` on a fallible call is the Rust "swallowed error".

### 15.7 Suppression — ZERO tolerance (the Rust list for §8)

Banned in committed code: `#[allow(...)]` / `#![allow(...)]` added to dodge a clippy/rustc gate without a user-accepted justification; an `unsafe` block in a `forbid(unsafe_code)` crate; `#[ignore]` to hide a failing test; CLI bypasses (`--no-verify`, dodging `cargo audit`/`deny`). Fix the root cause, or fix the lint config — don't scatter `allow`.

### 15.8 Security baseline (the §13 baseline in Rust)

- **RustCrypto only** on the crypto path — no `ring`, OpenSSL, or C bindings (keeps the wasm path clean, the supply-chain surface minimal). Constant-time secret comparison via `subtle`; never `==` on secret bytes.
- Secrets in `secrecy::SecretString` (redacting `Debug`/`Display`, zeroize-on-drop); CSPRNG via `rand`/`getrandom` (`OsRng`).
- **Supply chain gated:** `cargo-deny` (advisories + license allow-list + ban-list + crates.io-only sources), `cargo-audit` (RustSec), `cargo-vet`; `Cargo.lock` committed. Ban `openssl`/`openssl-sys`/`ring`; deny duplicate semver-major versions. Never log secrets/PII/tokens; never place a token in a URL.

### 15.9 Tooling map (TS → Rust)

| TS / JS | Rust |
|---|---|
| Prettier (`prettier --check`) | `cargo fmt --all --check` |
| ESLint (`eslint -D`) | `cargo clippy --workspace --all-targets --all-features -- -D warnings` |
| `tsc --noEmit` | `cargo build --workspace --all-features --locked` |
| Jest / Vitest + coverage | `cargo test --workspace` + `cargo llvm-cov` |
| Stryker (mutation) | `cargo-mutants` |
| `pnpm audit` | `cargo audit` + `cargo deny check` + `cargo vet` |
| `.nvmrc` / engines | `rust-toolchain.toml` + `rust-version` (MSRV) |
| JSDoc + TypeDoc | rustdoc (`///` / `//!`) + docs.rs |
| `.vscode` Prettier+ESLint | rust-analyzer (`formatOnSave` + `check.command: clippy`) |

§9 Conventional Commits, §10 Performance (measure first — `criterion` benches, non-gating), and §11 carry over unchanged.
