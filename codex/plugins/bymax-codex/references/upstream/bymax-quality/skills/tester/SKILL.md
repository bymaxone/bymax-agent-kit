---
name: tester
description: Write tests for a file or component. Detects the project's test stack (Jest/Vitest, React Native/React DOM/pure logic, or Rust cargo test), enforces 100% file coverage, every it() carries a comment, no fake classNames, real branches. Auto-runs tests and verifies coverage on completion.
user-invocable: true
argument-hint: "[file-path]"
---

# Tester Skill

You are writing tests for a file in a TypeScript/JavaScript **or Rust** project. Follow every rule below without exception. Some rules are **universal** (apply to every stack); others are **stack-specific** and depend on what you detect at the start.

---

## 0. Detect the test stack — FIRST STEP, ALWAYS

Before writing anything, determine the project's setup. Read these in order until you have an answer:

0. `Cargo.toml` present → Rust project → use **Profile F** and skip the JS/TS signals below.
1. `package.json` → `scripts.test`, `devDependencies` (look for `jest`, `vitest`, `@testing-library/react-native`, `@testing-library/react`, `react-native`, `expo`).
2. `jest.config.*`, `vitest.config.*`, `jest-setup.*`, `tests/` folder.
3. Any `CLAUDE.md`, `AGENTS.md`, or `docs/guidelines/testing-*.md` in the repo — project-specific rules win over this skill.
4. Existing test files near the source — match their style and conventions exactly.

Then classify into one of these **profiles**:

| Profile | Trigger signals | Render approach | Test runner |
|---|---|---|---|
| **A — RN + Jest** | `react-native`, `expo`, `@testing-library/react-native` | `render` from `@testing-library/react-native` | `jest` |
| **B — Web + Jest** | `react`, `@testing-library/react`, no `react-native` | `render` from `@testing-library/react` | `jest` |
| **C — Web + Vitest** | `vitest`, `@testing-library/react` or `renderToStaticMarkup` | RTL render OR `renderToStaticMarkup` from `react-dom/server` | `vitest` |
| **D — Pure logic** | No React imports in the file under test | None — call functions directly | `jest` or `vitest` (use whatever the project has) |
| **E — Node backend** | `express`, `fastify`, `hono`, etc., no React | None — supertest / direct calls | `jest` or `vitest` |
| **F — Rust** | `Cargo.toml` present | None — `#[cfg(test)] mod tests` + `#[test]`, call functions directly | `cargo test` (+ `cargo llvm-cov`) |

If signals are mixed or unclear, **ask the user** which profile to use. Do not guess.

---

## 1. Universal rules — apply to ALL profiles

### 1.1 Before writing any test

1. Read the source file(s) under test completely.
2. Identify every exported symbol: components, functions, constants, types.
3. Map every **branch** in the code (ternary, `if`, `&&`, `||`, `switch`, default parameters, optional chaining with side effects, `??`).
4. Only then start writing. No test before full source understanding.

### 1.2 Test file location & naming

- Co-locate the test file next to the source: `Button.tsx` → `Button.test.tsx`, `utils.ts` → `utils.test.ts`.
- Exception: if the project already places tests under `tests/` or `__tests__/`, match that convention. Check 2–3 existing tests before deciding.
- Extension: `.test.ts` for pure logic, `.test.tsx` for JSX.

### 1.3 Test structure

```ts
/**
 * <Layer> Tests — <SymbolName>
 *
 * Rendering strategy: <which approach this profile uses>
 * Mocks: <list any mocks and why>
 * Special setup: <context wrappers, providers, fake timers, etc.>
 */

// ---------------------------------------------------------------------------
// SymbolName — one section per exported symbol
// ---------------------------------------------------------------------------

describe('SymbolName', () => {
  // <one-sentence comment explaining what THIS test verifies and why>
  it('does X when Y', () => { /* ... */ })
})
```

Rules:

- One `describe` block per exported symbol.
- Test names are full sentences that read naturally.
- Group related tests in nested `describe` blocks (e.g. `describe('variant', ...)`)
- Order: happy path → edge cases → error cases.

### 1.4 Comment policy — MANDATORY

**Every single `it()` or `test()` block must have a block comment above it.** No exceptions. The comment:

- Is at least one sentence.
- Describes the **scenario** being exercised AND the **rule it protects** (the contract / invariant / regression).
- Is written in English.
- Sits on the lines immediately above the `it`/`test`, not inside it.

```ts
// Verifies that the default variant resolves to the primary brand color,
// confirming the CVA defaultVariants config is wired correctly.
it('uses default variant and size when no options given', () => { /* ... */ })

// Ensures the asChild prop delegates rendering to the child element,
// so Button can wrap <a> or other elements without adding an extra DOM node.
it('renders child element when asChild is true', () => { /* ... */ })
```

Also required:

- **File-level docblock** at the top (see §1.3).
- **Section separators** before each `describe`:
  ```ts
  // ---------------------------------------------------------------------------
  // ComponentName — short description
  // ---------------------------------------------------------------------------
  ```
- **Inline comments** for non-obvious decisions: why a mock exists, why a wrapper is needed, what a token value represents, why an assertion was chosen this way.

### 1.5 className / styling assertions

- **Never use fake classes** like `my-class`, `extra-class`, `custom-class`.
- Always use **real Tailwind / NativeWind classes** that exist in the project's design system and won't conflict with base classes.
- Preferred safe utilities: `opacity-75`, `mt-4`, `px-2`, `sr-only`, `bg-transparent`.

```ts
// ✅ correct
expect(html).toContain('opacity-75')

// ❌ wrong — triggers lint errors and is meaningless
expect(html).toContain('my-custom-class')
```

### 1.6 Imports order

Follow the project's `import/order` ESLint rule. Generic order:

```ts
import type { ReactNode } from 'react'        // 1. type imports
import * as React from 'react'                 // 2. react / framework
import { render } from '<test-lib-for-profile>' // 3. test framework + renderer
import { describe, it, expect, jest } from '@jest/globals' // (Vitest: from 'vitest')

// jest.mock / vi.mock calls go here (they are hoisted)
jest.mock('...', /* ... */)

import { MyComponent } from './my-component'   // 4. relative imports
```

### 1.7 Coverage requirement

**100% coverage per file under test.** Every branch must be exercised:

| Branch type | How to cover |
|---|---|
| `condition ? a : b` | One test for each path |
| `prop ?? default` | Test with and without the prop |
| `if/else if/else` | One test per arm |
| `switch` | One test per case + default |
| Optional render (`x && <View />`) | Render with `x` truthy and falsy |
| `variant` / `size` (CVA, NativeWind variants) | One test per variant value |
| Default export + named exports | Test each exported symbol |

**Do not run coverage for the entire project** — only for the file(s) being tested. Project-wide coverage runs only when explicitly requested by the user.

### 1.8 What NOT to do

- Do not add tests for code you did not write in this session, unless explicitly asked.
- Do not run project-wide coverage — only file-scoped.
- Do not install new packages without asking.
- Do not use `@ts-ignore`, `as any`, or `// eslint-disable` to work around errors. Fix the root cause.
- Do not snapshot test — use explicit assertions.
- Do not use `try/catch` for error assertions — use `rejects.toThrow()` / `expect(() => ...).toThrow()`.
- Do not test implementation details (private helpers); test observable behavior.
- Do not skip the "verify it actually fails first" check when adding a test for a bug fix.

---

## 2. Profile-specific rules

Apply only the section that matches your detected profile.

### Profile A — React Native + Jest

**Render:**

```tsx
import { render, fireEvent, screen } from '@testing-library/react-native'
import { describe, it, expect, jest } from '@jest/globals'

const { getByText, queryByTestId } = render(<MyComponent prop="value" />)
expect(getByText('Hello')).toBeTruthy()
```

**Context-dependent components** (theme provider, navigation, react-query, i18next):

- Wrap in the project's existing `renderWithProviders` helper if one exists. Check `tests/` or `src/test-utils/` first.
- If none exists, build a minimal wrapper inline; do not introduce a new shared helper without asking.

**Common RN-specific mocks:**

```ts
// Reanimated needs its mock loaded
jest.mock('react-native-reanimated', () =>
  require('react-native-reanimated/mock')
)

// Gesture Handler
jest.mock('react-native-gesture-handler', () => ({
  /* ... project's existing mock ... */
}))
```

Always check the project's `jest-setup.ts` / `tests/__mocks__/` before adding a new mock — most are already configured globally.

**Run:**

```bash
# Single file
pnpm jest <path-to-file>.test.tsx

# Coverage for one file
pnpm jest --coverage --collectCoverageFrom='<path-to-file-under-test>' <path-to-file>.test.tsx
```

### Profile B — Web React + Jest

**Render:**

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, jest } from '@jest/globals'

render(<MyComponent prop="value" />)
expect(screen.getByRole('button', { name: 'Submit' })).toBeInTheDocument()
```

Use `screen.getByRole` over `getByTestId` whenever possible (accessibility-first queries).

**Run:**

```bash
pnpm jest <path>.test.tsx
pnpm jest --coverage --collectCoverageFrom='<path>' <path>.test.tsx
```

### Profile C — Web React + Vitest

**Two render strategies — pick by need:**

**C.1 — RTL** (when interaction or DOM queries are needed):

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
```

**C.2 — `renderToStaticMarkup`** (when only structural / className assertions are needed, no events):

```tsx
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect, vi } from 'vitest'

const html = renderToStaticMarkup(<MyComponent prop="value" />)
expect(html).toContain('expected-output')
```

Why `renderToStaticMarkup` is acceptable here: no jsdom required, fast, covers forwardRef and className paths. Use it when the component has no interactive behavior to test.

**Radix / portal-style components** that need DOM APIs:

```ts
vi.mock('@radix-ui/react-dialog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@radix-ui/react-dialog')>()
  return { ...actual, Portal: ({ children }: { children: ReactNode }) => children }
})
```

**Run:**

```bash
npx vitest run <path>.test.tsx
npx vitest run --coverage --coverage.include='<path-to-file-under-test>'
```

### Profile D — Pure logic

**No render. Call functions directly:**

```ts
import { describe, it, expect } from '@jest/globals' // or 'vitest'
import { calculateScore } from './score'

describe('calculateScore', () => {
  // Confirms the scoring weights produce the documented baseline for a typical input.
  it('returns expected score for a balanced input', () => {
    expect(calculateScore({ a: 1, b: 2 })).toBe(42)
  })
})
```

Cover boundary values (0, max, negative, NaN, empty), error throws, and every branch.

### Profile E — Node backend

**HTTP routes — use supertest if present, otherwise call the handler directly:**

```ts
import request from 'supertest'
import { app } from '../app'

// Confirms the /health route returns 200 with the documented body shape,
// protecting the contract used by the load balancer's health check.
it('GET /health returns 200', async () => {
  const res = await request(app).get('/health')
  expect(res.status).toBe(200)
  expect(res.body).toEqual({ status: 'ok' })
})
```

For DB-backed code, follow the project's existing pattern (test container, in-memory DB, transactional rollback). Do not invent a new approach.

### Profile F — Rust

**No render. Unit tests live in a `#[cfg(test)] mod tests` block in the same file; integration tests go in `tests/`.**

```rust
#[cfg(test)]
mod tests {
    use super::*;

    // Confirms the scoring weights produce the documented baseline for a typical
    // input — protecting the contract that a balanced market scores mid-range.
    #[test]
    fn returns_expected_score_for_balanced_input() {
        assert_eq!(liquidity_score(&balanced_market()), 50);
    }

    // Wrong-input path: a malformed snapshot must surface a typed error, never panic.
    #[test]
    fn rejects_malformed_snapshot() {
        assert!(matches!(parse_snapshot(""), Err(SnapshotError::Empty)));
    }
}
```

Rust specifics:
- **Comment policy is identical** — a `//` block comment (English, scenario + rule) on the lines immediately above every `#[test]`. The file-level docblock maps to the module `//!` or a `//` header on the `mod tests`.
- **Error assertions** use `assert!(matches!(result, Err(...)))` or `result.unwrap_err()` — never a `panic!`-catching wrapper. `#[should_panic]` only for code whose contract is to panic.
- **Async tests** use the runtime macro (`#[tokio::test]`).
- **`unwrap()` / `expect()` are allowed in test code** (they keep a failing assertion legible) — that exemption is test-only; library code still may not.
- **Real values, not fakes** — assert against real domain types and real error variants, never invented strings (the Rust analogue of §1.5's "no fake classNames").
- **Coverage:** `cargo llvm-cov` for the crate under test; `proptest` for parser/round-trip properties. Do not run workspace-wide coverage unless asked.

---

## 3. Execution workflow — universal

After writing all tests, execute this sequence:

### Step 1 — Run tests

Use the project's standard command. Examples:

| Profile | Command |
|---|---|
| Jest (any) | `pnpm jest <path>` or `npm test -- <path>` |
| Vitest | `npx vitest run <path>` |
| Rust (F) | `cargo test` (whole crate) or `cargo test <name>` (filter) |

If tests fail → diagnose, fix the test or source, run again **once**.
If they still fail after one fix attempt → stop, report the failure clearly, and wait for instructions.

### Step 2 — Verify file coverage

| Profile | Command |
|---|---|
| Jest | `pnpm jest --coverage --collectCoverageFrom='<path-to-source>' <path-to-test>` |
| Vitest | `npx vitest run --coverage --coverage.include='<path-to-source>'` |
| Rust (F) | `cargo llvm-cov -p <crate-under-test>` (crate-scoped; add `--workspace` only when explicitly asked) |

The file under test must show **100%** on Stmts, Branch, Funcs, Lines.

If coverage is below 100% → identify the uncovered branch, add a test, run Step 1 again **once**.
If still below after one attempt → stop, show the coverage report, and wait for instructions.

### Step 3 — Report

When both steps pass, report:

- ✅ `X/X tests passing`
- ✅ `100% coverage on <filename>`
- Profile used (A/B/C/D/E/F)
- One line per `describe` block summarizing what was tested

---

## 4. Defer to project conventions

If the repo has a `CLAUDE.md`, `AGENTS.md`, or `docs/guidelines/testing-*.md`, **those override this skill** when they conflict. This skill is the default; the project is the authority.
