# Shared Bymax review checklist

Generated from the Claude command; do not edit this copy. The Codex
code-review entrypoint overrides scope acquisition, mechanical-hit
classification, tool calls and reporting. Read these rules as reference.

## Step 2 — Mechanical gate (deterministic)

For a committed campaign, set `RANGE` to the literal `<review_base>..<head>` SHAs
returned by the helper. Never leave it empty. For a dirty preview use `HEAD` and read
untracked files separately. Detect the stack first: skip TypeScript/Tailwind checks on
Rust, and apply Rust-specific constraints only to Rust. Apply size/docs rules only to
the source/test surfaces actually governed by the target policy, never generic Markdown
length or inherited violations. All checklist severity headings below are candidate
classifications: verify applicability before admitting a finding.

Run these greps over the diff so findings are exact facts, not model impressions. The
`added()` helper isolates **added content lines** by re-marking them with `>` via
`--output-indicator-new` — this leaves the `+++ b/path` file header untouched (so a
filename containing a flagged token can't false-positive) and, unlike a `^\+` /
`grep -v '^+++'` filter, never drops a real content line that happens to start with
`++` (which would otherwise collide with the header prefix). Match the token anywhere on
the line — never fold an anchor and the token into one pattern like `^\+[^+].*TOKEN`,
because `[^+]` eats the first character of a token sitting at column 0 (`+console.log`,
`+#[allow(...)]`) and misses it. The `added()` output is content only — to get the
`file:line` of a hit, re-grep the working tree for it (`git grep -n '<pattern>'`), since
these are exact string matches. Every match is a candidate. Verify the actual syntax, changed lines, applicable project
policy, exemptions and impact before reporting it. Examples, fixtures and pre-existing
violations are not automatically introduced defects. CI-enforced failures belong to CI.

```bash
# Added content lines only: git marks them '>' instead of '+', leaving the
# '+++ b/path' header as-is — no header collision, no lost '++'-prefixed content.
added() { git diff --output-indicator-new='>' -U0 "$@" | grep '^>'; }

# CRITICAL — suppression comments (zero tolerance, see policy below)
added $RANGE | grep -E 'eslint-disable|@ts-ignore|@ts-expect-error|@ts-nocheck|prettier-ignore|as any|as unknown as|#\[allow\(|#!\[allow\(|# noqa|# type: ignore|@SuppressWarnings'

# CRITICAL — CLI bypasses committed in scripts or hooks
added $RANGE | grep -E -- '--no-verify|--skip-checks|--no-gpg-sign'

# HIGH — raw console in production code (frontend must use the project logger).
# Exclude test files by the `.test.`/`.spec.` convention — matched as a substring so
# `latest.ts`/`contest.ts` are NOT excluded (a bare `*test*` would wrongly drop them).
added $RANGE -- '*.ts' '*.tsx' ':!*.test.*' ':!*.spec.*' | grep -E 'console\.(log|warn|error|debug|info)'

# HIGH — TODO/FIXME without an issue link
added $RANGE | grep -E '(^|[^A-Za-z])(TODO|FIXME|XXX|HACK)([^A-Za-z]|$)' | grep -vE '#[0-9]+|issues/'

# HIGH — file over 800 lines (NUL-delimited so paths with spaces survive)
git diff --name-only -z $RANGE | while IFS= read -r -d '' f; do [ -f "$f" ] && wc -l "$f"; done | awk '$1 > 800'

# MEDIUM — Tailwind v4 non-canonical forms (skip on Tailwind v3 / NativeWind projects)
added $RANGE -- '*.tsx' '*.jsx' | grep -E '\[var\(--|aria-\[(invalid|disabled|pressed|expanded|hidden|selected|checked|busy|modal|required|readonly)=(true|false)\]|z-\[[0-9]+\]|-(bottom|top|left|right|m)-0([^.0-9]|$)'

# MEDIUM — Tailwind v3 utilities renamed in v4
added $RANGE -- '*.tsx' '*.jsx' | grep -E 'bg-gradient-to-|outline-none|decoration-(clone|slice)|overflow-ellipsis|flex-(shrink|grow)-|(bg|text|border|divide|placeholder|ring)-opacity-[0-9]'

# MEDIUM — hardcoded hex colors in className (use design tokens)
added $RANGE -- '*.tsx' '*.jsx' | grep -E 'className=.*#[0-9a-fA-F]{3,8}'

# MEDIUM — dynamic Tailwind class strings the JIT cannot see
added $RANGE -- '*.tsx' '*.jsx' | grep -E 'className=\{`[^`]*\$\{'
```

Severity mapping for Tailwind canonical forms (flag → suggest): `[var(--x)]` → `(--x)` ·
`aria-[invalid=true]:` → `aria-invalid:` · `z-[200]` → `z-200` · `-bottom-0` → `bottom-0` ·
`bg-gradient-to-r` → `bg-linear-to-r` · `outline-none` → `outline-hidden` ·
`bg-opacity-50` → `bg-blue-500/50` form · on-scale arbitrary rem (`p-[1rem]` → `p-4`,
`min-w-[8rem]` → `min-w-32`; token = rem × 4, off-scale values stay arbitrary) · filter px
(`backdrop-blur-[12px]` → `backdrop-blur-md`: 4=xs 8=sm 12=md 16=lg 24=xl 40=2xl 64=3xl) ·
v3 scale shifts (`shadow`→`shadow-sm`, `rounded`→`rounded-sm`, `blur`→`blur-sm`,
`ring`→`ring-3`). Full table: `/bymax-workflow:standards` §12.

Also scan added lines for secrets (AWS keys, GitHub PATs, JWTs, PEM blocks, provider tokens) —
the `secret-scanner` hook blocks writes, but the diff may predate the hook.

## Step 3 — Bug hunt

In `quick`, focus on introduced correctness/security defects and impacted callers.

**`full` (default):** hunt logic bugs yourself, single pass. For each changed file, read the whole
file plus its call sites — never review a hunk in isolation. Hunt specifically for: broken edge
cases (empty/null/zero/unicode), off-by-one and boundary errors, async races and unawaited
promises, error paths that leave state inconsistent, wrong operator or inverted condition,
regressions in callers the diff didn't touch. Report only candidates supported by a concrete trigger, affected path and impact.

**`deep`:** spend the same two reviewers' attention on security boundaries, state
transitions, recovery, concurrency and impacted callers. Do not add finder agents or
invoke a second review engine. Coverage still stays within the agreed change and its
behavioral effects; every candidate goes through Step 5.

## Step 4 — Convention checklist (judgment)

The mechanical patterns already ran in Step 2; this step covers what needs reading comprehension.
In `quick` mode, check only CRITICAL and HIGH.

### CRITICAL — verify security impact

- SQL injection (string-built queries), XSS (unsafe `dangerouslySetInnerHTML`, unescaped user
  input), path traversal (user input feeding `fs`/`path.join`).
- Missing input validation on a public boundary (HTTP handler, IPC, file parser).
- Logging or analytics that include PII, credentials, medical data, or other sensitive fields.
- Insecure dependencies (known CVEs, abandoned packages).

### Suppression policy — zero tolerance

A newly introduced operative suppression prohibited by the actual project policy is a
blocking candidate. Verify syntax and exemptions; quoted examples are not suppressions:
`eslint-disable` in any form, `@ts-ignore`/`@ts-expect-error`/`@ts-nocheck`, `as any`,
`as unknown as <T>` laundering a real type error, `prettier-ignore` (unless preserving a
deliberately-formatted table), cross-language suppressions (`# noqa`, `# type: ignore`,
`@SuppressWarnings`), and in Rust: `#[allow(...)]` silencing a clippy/rustc gate without a
user-accepted justification, `unsafe` without a `// SAFETY:` comment or inside a
`#![forbid(unsafe_code)]` crate, `#[ignore]` hiding a failing test.

**The rule:** fix the underlying cause. A failing lint or type error means the code is wrong, the
type is wrong, or the rule is wrong — choose one and fix it. Never silence the messenger.

**The only acceptable exception:** a suppression that (1) references a specific issue or PR
(`// eslint-disable-next-line no-unused-vars -- see #1234, follow-up tracked`) AND (2) has a
clear, time-bounded reason. Even then, flag it as HIGH so the reviewer accepts it explicitly.
If the user is fighting a wrong rule, change the rule config with justification — never scatter
`disable` comments through the code.

### HIGH — must fix before merge

- Functions > 50 lines; nesting depth > 4.
- **Docs (per `/bymax-workflow:standards`):** non-trivial source file missing the file-header
  JSDoc (Purpose + Layer); exported function/hook/component/service/store missing JSDoc with
  `@param`/`@returns`/`@throws`; test `it`/`test` block without a comment naming the scenario
  and the rule it protects. **Rust:** public item missing rustdoc (`///`, crate `//!`,
  `# Errors` on fallible items, `# Safety` on `unsafe fn`).
- **Architecture:** cross-feature import (`features/X/` importing `features/Y/` — orchestrate one
  level up); domain import inside `shared/ui/`; internal export leaked through a feature barrel.
- **Reinvented wheel (standards §0 simplicity ladder):** new code reimplements something that
  exists in this repo, in a `@bymax-one/*` lib, in the stdlib/platform (`Intl`,
  `crypto.randomUUID()`, `URL`, `structuredClone`, native `<input>` types, `std`/`core`), or in
  an installed dependency — point to the existing symbol. A new dependency for something already
  covered must be justified.
- **Error handling:** empty `catch`, `catch` that only logs without surfacing, ignored rejected
  promises, missing boundary validation (Zod or equivalent). **Rust:** `unwrap()`/`expect()`/
  `panic!`/`todo!()` on a library path (tests exempt); stringly-typed errors instead of a
  `thiserror` enum; `anyhow` in a library's public API; `let _ =` discarding a `Result`.
- **TS discipline:** `any` introduced (use `unknown` + guard, a generic, or the upstream type);
  non-null assertion `!` without a comment proving the invariant.
- An existing suppression retained without an issue-link justification (see policy above).

### MEDIUM — should fix

- Mutation where immutable would do; magic numbers without a named constant; emoji in code.
- Missing tests for new code.
- Copy-pasted logic across ≥ 2 places that belongs in `shared/` or a `@bymax-one/*` lib.
- Speculative generality (YAGNI) — options/params/abstractions with no current caller.
- Accessibility: missing labels, keyboard traps, color contrast.
- `enum` instead of a string-literal union; `interface` for a union/utility type or `type` for an
  entity shape (standards §1); boolean not prefixed `is/has/should/can`; `../../../` where a path
  alias exists.
- Comment not in English; plan phase/task references in committed comments (timeless-comments
  rule). **Rust:** avoidable `.clone()`/`format!` in a hot path; blocking work in an `async fn`
  without `spawn_blocking`; internal type leaked through the public API; missing `#[must_use]`;
  a dependency not cleared by `cargo deny`.

### LOW — nit

- Inconsistent naming with surrounding code; unnecessary re-exports; comments restating the code.

## Step 5 — Verify before reporting

Candidate ≠ finding. For **every** candidate (yours or a finder agent's):

1. Re-open the file at the cited line and confirm the claim against the actual code — the guard
   the finder "missed" is often three lines up.
2. For behavior claims, trace the call path; a claim that survives only as an inference from
   naming is dropped.
3. Consolidate duplicates ("5 functions missing JSDoc" is one finding with five locations).
4. Drop everything unconfirmed. Track the dropped count for the report.

Step 2 candidates require the same verification. Exact text matching does not prove a defect.

**Freeze the raw report before reading the other reviewer.** Subsequent triage preserves
its original evidence and severity, and records acceptance or rejection separately.

