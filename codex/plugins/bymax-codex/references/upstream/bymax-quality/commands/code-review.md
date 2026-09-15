---
description: 'Bounded Claude and Codex code review with shared context, pinned scope, verified findings, regression checks and at most three candidate rounds. Full review first, correction deltas thereafter; never fix speculative findings or loop until zero nits. Triggers: "code review", "review changes", "revisar código".'
argument-hint: "[quick|full|deep] [target] [--fix] [--preview]"
---

# Code Review

Run a bounded review campaign using **both Claude and Codex**. Default `full` means
one Claude review and one independent Codex review. The Claude review is this command's
read-only pass; do not additionally invoke the built-in `/code-review`. Never invoke
this command recursively or start a Stop-hook review loop. `deep` widens risk analysis,
not the number of automatic review/correction rounds. `quick` focuses the same pair on
correctness and security; it does not skip a reviewer.

Read `${CLAUDE_PLUGIN_ROOT}/references/review-protocol.md` before running. It defines
context capture, executable lifecycle commands, report/triage schemas, correction scope,
and the exact conditions for a completed review. Its verification and scope rules take
precedence over the generic checklist below. Read the target project's actual policies;
explicit local constraints take precedence over generic Bymax conventions.

## First run in a repository (mandatory, once)

Two reviewer pairs see this repository: the bounded campaign below, and the PR bots —
Anthropic's Code Review and Codex — which read files this repository must carry. Check
them before the first campaign here and tell the user in one line if either is missing:

| File | Read by | Missing means |
|---|---|---|
| `REVIEW.md` (repo root) | Anthropic Code Review, `/code-review ultra` | every wording preference arrives as a blocking finding, and nits never converge |
| `## Code Review Rules` in `AGENTS.md` | Codex review | the same, from the other bot |

`/bymax-quality:review-md` generates both from this repository's own invariants; run it
once per repository and keep it refreshed when the invariants change. `review_flow.py
start` prints the same notice, so a campaign never silently runs without them.

## Scope and authorization

For a push-ready campaign, the intended changes must already be committed and the
worktree clean, including untracked files. Never stage unrelated files, stash, switch
branches or create a commit merely to satisfy a review. When the user has authorized
shipping the changes, the implementing workflow can create the candidate commit before
review; a local commit is not approval to push. Otherwise report that certification
requires a committed candidate and offer the read-only preview described below.

Resolve the target branch/PR's actual base. For a PR, read its base/head with
`gh pr view <target> --json baseRefName,baseRefOid,headRefOid`; fetch missing objects
without checkout, and verify the requested head equals the current HEAD. For a branch,
use its intended integration branch; do not substitute a pushed upstream already equal
to HEAD. Resolve `git merge-base <verified-target-base> HEAD` to a nonempty SHA.
Never guess another base on resolution failure. Read the existing campaign with
`review_flow.py status` before starting: reuse its original base, contract and reports
through correction rounds. A changed PR base or rewritten history requires reassessment.

A path, another checkout's branch, dirty work, or a range ending elsewhere can receive
`--preview`: read the exact requested diff and surrounding code, and provide the same
scope/context to a read-only Codex `exec` prompt. Include untracked files by reading them,
not by `git add -N`. Label it **PREVIEW — not push clearance**. Do not create campaign
receipts for partial or mutable scopes. Preview is one pass per reviewer; do not loop.

`--fix` authorizes minimal fixes only after both raw reports and triage are recorded.
It does not authorize speculative refactors, unrelated repairs, commits or pushes.
Legacy `--no-codex`, `--no-builtin` and `--adversarial` flags do not alter certification:
explain that the bounded campaign uses exactly the Claude/Codex pair. If the user wants
a separate design audit, report it separately from this campaign.

## Review execution

1. Capture intent, acceptance criteria, affected invariants, exclusions, actual stack
   versions and required gate commands in the campaign context. Give both reviewers
   the identical generated prompt. Share prior dispositions on correction rounds,
   but never the other reviewer's current findings before freezing your own report.
2. Start `review_flow.py codex` in a background shell. It runs a fresh read-only Codex
   context with the explicit diff and task contract, and persists its completed report.
   While it runs, perform the Claude pass using `review_flow.py prompt` and the relevant
   checklist below. Read enough callers and tests to prove each proposed finding.
   On a correction round, or whenever this session authored the candidate, delegate the
   Claude pass to a fresh-context subagent (`general-purpose`, read-only) given exactly
   the generated prompt and nothing from this conversation; record its JSON report as
   the Claude report. The author's own reading is not the Claude review.
3. Save the Claude JSON report and record it. Await the Codex shell's completion;
   inspect its exit status and `status`. Missing, malformed, failed or timed-out review
   means **INCOMPLETE**, never an approval and never a reason to edit the product.
4. Read both reports, verify every candidate, deduplicate by violated invariant and
   record every disposition. Preserve reviewer provenance and original severity.
   Agreement is not proof; rejection needs concrete counterevidence. Report at most
   five nits; group the rest. Confirmed introduced P0/P1/P2 defects and explicit policy
   violations block; nits and unrelated pre-existing work can be deferred with reasons.
5. Fix accepted blockers in one small batch, in this order, and do not reorder it:
   1. **Regression first.** Turn each accepted finding's reproduction into a permanent
      test case that fails on the current candidate, in the suite the campaign's
      `checks` already runs. The suite is the cumulative invariant matrix: every case
      from every round stays, so a later fix that breaks an earlier case is caught by
      the gate, not by a reviewer. Assert the invariant (what must and must not
      happen), never the fix's mechanism, and never the shell's or a parser's verdict
      when the real effect can be observed instead.
   2. **Extend, do not replace.** Make the minimum change preserving neighboring
      behavior. A correction that deletes an existing check must first run every case
      that check covered against the replacement; a cruder check's blind spots are not
      the new check's blind spots, and removing it removes coverage.
   3. **Never flip a test.** An existing test's expectation may not change in a
      correction round without a triage entry saying why; a flipped expectation is
      evidence the test mirrored a design choice, and `start` shows every changed
      test to both reviewers so an unjustified flip is a finding.
   4. **Probe your own fix before committing.** Spend bounded effort trying to defeat
      the correction the way a reviewer would, record each attempt as
      `{command, expected, observed}`, and pass that file to `start --probe`. It is
      required for every correction round and both reviewers see it. What you find
      here costs nothing; the same hole found after commit costs a round.
   5. Check affected callers, error paths and lifecycle transitions. Run the regression
      suite and project gates. If authorized, commit and advance the same campaign.
      A correction that touches no test needs `--no-regression-reason`, which is
      recorded and shown to both reviewers.
   6. **The author does not review the correction.** The Claude pass on a correction
      delta runs in a fresh-context subagent given only the generated prompt, never in
      the session that wrote the fix. Authorship is not independence, and the reviewer
      that has no stake in the design is the one that finds what the author cannot.
6. **A reopened finding ends patching.** If a finding is open in two consecutive
   triages, the previous correction addressed the instance and not the cause; `start`
   refuses the next round unless it is declared `--design-round`, and that round is
   spent on the approach — a design proposal for the human, or a change that removes
   the class — not on another patch. Both reviewers are told it is a design round.
7. At three candidate rounds (initial + two correction rounds), stop if still blocked.
   Present unresolved invariants, attempted fixes and a proposed scope split. Do not
   reset the campaign, change branches, disable Codex or clear a receipt to evade the
   limit, and do not archive the campaign and open another on the same finding without
   the human's explicit authorization for that campaign. A limit is a handoff, never
   automatic approval. These limits are operational defaults, not a claim that three
   passes prove correctness. Findings about instruction prose are deferred and batched:
   correcting prose in a round of its own is how a loop starts, since every correction
   to text no test can check is a new surface for the next review.

No code mutation is allowed while either reviewer is running. If another session changes
HEAD or the worktree, discard that candidate's unrecorded output and reassess. A report
must state actual coverage and limitations; an empty result does not prove absence of bugs.

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
# The literal endpoints the helper reported for this candidate; never leave it empty.
RANGE='<review_base>..<head>'
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

## Step 5.5 — Complete the bounded campaign

Follow `references/review-protocol.md`: record triage, execute required gates through the
helper and run `finish`. Verify `status` reports the intended HEAD, both completed
reviewers, passing check evidence and `cleared: true` before reporting **REVIEW COMPLETE**.
If blockers remain, report **BLOCKED**; if a reviewer/gate did not complete, **INCOMPLETE**.
A skill invocation itself records no clearance. A repeated push reuses the completed
receipt for that exact commit and never starts a new review solely to create a marker.
