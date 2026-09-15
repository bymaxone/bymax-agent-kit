---
description: 'Drive a strict red-green-refactor TDD cycle for NEW code — scaffold interfaces, write failing tests FIRST, run them and confirm they fail, then write the minimal implementation to make them pass, then refactor. Enforces 80% coverage minimum (100% on critical paths). Every it() must carry a block comment per /bymax-workflow:standards. Use for new features and bug fixes (write the regression test first). For tests on EXISTING code without changing behavior, use the `tester` skill instead. Triggers: "implementar com tdd", "tdd", "test first", "red green refactor", "vou implementar", "criar função", "criar serviço", "fix this bug".'
argument-hint: "[what to build]"
---

# TDD Command

This command enforces test-driven development methodology — scaffold, RED, GREEN, REFACTOR, coverage — with the same rich-comment policy as the `tester` skill.

## What This Command Does

1. **Scaffold Interfaces** - Define types/interfaces first
2. **Generate Tests First** - Write failing tests (RED)
3. **Implement Minimal Code** - Write just enough to pass (GREEN)
4. **Refactor** - Improve code while keeping tests green (REFACTOR)
5. **Verify Coverage** - Ensure 80%+ test coverage

## When to Use

Use `/bymax-quality:tdd` when:
- Implementing new features
- Adding new functions/components
- Fixing bugs (write test that reproduces bug first)
- Refactoring existing code
- Building critical business logic

## How It Works

The command drives this cycle:

1. **Define interfaces** for inputs/outputs
2. **Write tests that will FAIL** (because code doesn't exist yet)
3. **Run tests** and verify they fail for the right reason
4. **Write minimal implementation** to make tests pass
5. **Run tests** and verify they pass
6. **Refactor** code while keeping tests green
7. **Check coverage** and add more tests if below 80%

## TDD Cycle

```
RED → GREEN → REFACTOR → REPEAT

RED:      Write a failing test
GREEN:    Write minimal code to pass
REFACTOR: Improve code, keep tests passing
REPEAT:   Next feature/scenario
```

## Worked example — minimal skeleton

The cycle in code (one feature: `calculateLiquidityScore`). Every step has a `git commit` you'd actually make.

### Step 1 — SCAFFOLD (interface, no logic)

```ts
// lib/liquidity.ts
export interface MarketData {
  totalVolume: number;
  bidAskSpread: number;
  activeTraders: number;
  lastTradeTime: Date;
}

export function calculateLiquidityScore(market: MarketData): number {
  throw new Error('Not implemented');
}
```

### Step 2 — RED (failing tests with rich comments — see Comment Policy below)

```ts
// lib/liquidity.test.ts
describe('calculateLiquidityScore', () => {
  // Confirms the zero-volume short-circuit: no trading must produce exactly 0
  // — protects the documented rule "no trades = no liquidity" and the
  // division-by-zero regression from issue #214.
  it('returns 0 for zero-volume market', () => {
    expect(calculateLiquidityScore({ totalVolume: 0, /* ... */ })).toBe(0);
  });

  // ...one `it` per scenario / branch / regression — each with its own block comment.
});
```

Run tests → confirm they fail for the right reason. **Do not skip this check.**

### Step 3 — GREEN (minimal code to pass)

Write just enough. No premature constants, no extracted helpers. The smallest patch that turns the suite green.

Before writing the body, run the simplicity ladder (`/bymax-workflow:standards` §0): an existing util/component, a `@bymax-one/*` lib, the stdlib/platform, or an installed dependency may already BE the green — reuse beats reimplementing, and never add a new dependency just to pass a test.

### Step 4 — REFACTOR (improve while green)

Now extract constants, helpers, and clean up — re-running tests after every meaningful change. Tests stay green throughout.

### Step 5 — Coverage

```bash
npm test -- --coverage lib/liquidity.test.ts
# Target: 100% on critical paths, 80%+ otherwise.
```

If coverage is below target, add the missing test → loop back to Step 2 (RED first).

---

### Rust variant (same cycle, `#[test]` + `cargo test`)

On a Rust project (`Cargo.toml`) the cycle is identical; the mechanics map like this:

```rust
// src/liquidity.rs — Step 1 SCAFFOLD (signature, no logic)
/// Computes a 0–100 liquidity score for a market snapshot.
pub fn liquidity_score(market: &MarketData) -> u8 {
    todo!("not implemented")
}

#[cfg(test)]
mod tests {
    use super::*;

    // Step 2 RED — confirms the zero-volume short-circuit: no trading must
    // produce exactly 0, protecting the rule "no trades = no liquidity" and the
    // divide-by-zero regression from #214.
    #[test]
    fn returns_zero_for_zero_volume_market() {
        assert_eq!(liquidity_score(&MarketData { total_volume: 0, /* … */ }), 0);
    }
}
```

> The `todo!()` above is **RED-phase scaffolding only** — it lets the signature compile while the test fails. GREEN replaces it with the real body; `todo!()` / `unimplemented!()` must never reach `/bymax-workflow:verify` or a commit (the Rust standards flag them on library paths as HIGH).

- **RED:** `cargo test` → confirm it fails for the right reason. Do not skip this check.
- **GREEN:** the smallest patch that turns the suite green.
- **REFACTOR:** extract helpers/consts while green; re-run `cargo test`.
- **Coverage:** `cargo llvm-cov -p <crate>` (crate-scoped; `--workspace` only when asked) — 100% on critical paths; `proptest` for round-trips/parsers.

`unwrap()`/`expect()` are fine in test code (a failing assertion stays legible) but never in library code. Never `#[ignore]` to silence a failing test or `#[allow(...)]`/`unwrap`-in-lib to dodge a gate.

## Comment Policy — MANDATORY

Every test you write under `/bymax-quality:tdd` must follow the same rich-comment policy as the `tester` skill. There are no exceptions, even during the RED phase.

On a **Rust** project the identical policy applies to every `#[test]`: a `//` block comment on the lines immediately above the `#[test]` attribute, in English, naming the scenario and the rule it protects.

### Required structure

1. **File-level docblock** at the top of every test file:

   ```ts
   /**
    * <Layer> Tests — <SymbolName>
    *
    * Rendering strategy: <how the SUT is exercised, or "N/A" for pure logic>
    * Mocks: <list any mocks and why they exist>
    * Special setup: <fake timers, providers, fixtures, etc.>
    */
   ```

2. **Section separators** before each `describe` block:

   ```ts
   // ---------------------------------------------------------------------------
   // SymbolName — short description
   // ---------------------------------------------------------------------------
   ```

3. **Block comment above every single `it()` / `test()`.** No exceptions.
   The comment must:

   - Be at least one full sentence.
   - Describe the **scenario** being exercised AND the **rule it protects**
     (the contract / invariant / regression / business rule).
   - Be written in English.
   - Sit on the lines immediately above the `it`/`test`, never inside it.

### Examples

```ts
// Verifies that the default variant resolves to the primary brand color,
// confirming the CVA defaultVariants config is wired correctly.
it('uses default variant and size when no options given', () => { /* ... */ })

// Ensures the asChild prop delegates rendering to the child element,
// so Button can wrap <a> or other elements without adding an extra DOM node.
it('renders child element when asChild is true', () => { /* ... */ })

// Confirms that calculateLiquidityScore returns exactly 0 for a market with
// zero volume — protecting the documented business rule "no trades = no
// liquidity" and preventing the division-by-zero regression from issue #214.
it('returns 0 for zero-volume market', () => { /* ... */ })
```

### What a BAD test comment looks like

```ts
// ❌ tells you nothing more than the test name itself
// tests the function
it('returns high score for liquid market', () => { /* ... */ })

// ❌ describes mechanics, not the contract being protected
// calls calculateLiquidityScore with volume 100000 and asserts > 80
it('returns high score for liquid market', () => { /* ... */ })
```

### What a GOOD test comment looks like

```ts
// ✅ explains the SCENARIO and the RULE / CONTRACT it protects
// Verifies that a market with high volume, tight spread, many traders, and
// recent activity produces a score in the top quintile — protecting the
// contract that healthy markets are surfaced to users as "liquid".
it('returns high score for liquid market', () => { /* ... */ })
```

### Inline comments

Add an inline comment whenever a decision is non-obvious:

- Why a mock exists.
- Why a wrapper / provider is needed to render the SUT.
- What a magic number or design token represents.
- Why a specific assertion was chosen (e.g. range vs exact equality).

This rule is **identical** to the one enforced by the `tester` skill. Tests written via TDD must be indistinguishable in comment quality from tests written via `tester`.

---

## TDD Best Practices

**DO:**
- ✅ Write the test FIRST, before any implementation
- ✅ Run tests and verify they FAIL before implementing
- ✅ Write minimal code to make tests pass
- ✅ Refactor only after tests are green
- ✅ Add edge cases and error scenarios
- ✅ Aim for 80%+ coverage (100% for critical code)
- ✅ Write a rich block comment above EVERY `it()` / `test()` (see "Comment Policy" above)
- ✅ Add a file-level docblock and section separators on every test file

**DON'T:**
- ❌ Write implementation before tests
- ❌ Skip running tests after each change
- ❌ Write too much code at once
- ❌ Ignore failing tests
- ❌ Test implementation details (test behavior)
- ❌ Mock everything (prefer integration tests)
- ❌ Ship a test without a block comment explaining the scenario and the rule it protects
- ❌ Write a comment that just restates the test name — it must add the "why"
- ❌ Use `// eslint-disable*`, `// @ts-ignore`, `// @ts-expect-error`, `as any`, or `as unknown as <T>` to silence a failing lint / type error — fix the root cause instead. The only acceptable exception is a suppression that references a specific issue and has a time-bounded reason, and even then the user must explicitly accept it.
- ❌ Bypass quality gates with `--no-verify`, `--force`, or by skipping/deleting a failing test "for now"

## Test Types to Include

**Unit Tests** (Function-level):
- Happy path scenarios
- Edge cases (empty, null, max values)
- Error conditions
- Boundary values

**Integration Tests** (Component-level):
- API endpoints
- Database operations
- External service calls
- React components with hooks

**E2E Tests** (for web flows, use `/bymax-web-verify:verify`):
- Critical user flows
- Multi-step processes
- Full stack integration

## Coverage Requirements

- **80% minimum** for all code
- **100% required** for:
  - Financial calculations
  - Authentication logic
  - Security-critical code
  - Core business logic

## Important Notes

**MANDATORY**: Tests must be written BEFORE implementation. The TDD cycle is:

1. **RED** - Write failing test
2. **GREEN** - Implement to pass
3. **REFACTOR** - Improve code

Never skip the RED phase. Never write code before tests.

## Integration with Other Commands

- Use `/bymax-workflow:plan` first to understand what to build
- Use `/bymax-quality:tdd` to implement with tests
- Use `/bymax-quality:code-review` to review implementation
- Use `/bymax-workflow:verify` to run the full gate (types, lint, tests, coverage)
