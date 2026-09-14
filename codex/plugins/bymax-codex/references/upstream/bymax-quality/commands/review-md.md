---
description: 'Generate or refresh a repo-root REVIEW.md that makes Anthropic''s built-in Code Review (cloud @claude review on PRs, /code-review ultra) enforce the Bymax rules. Distills the /bymax-quality:code-review checklist plus the project''s CLAUDE.md into review-only instructions: severity recalibration (suppressions and secrets = Important), nit cap, skip rules for generated files and lockfiles, and repo-specific always-check rules. Self-contained output — REVIEW.md is injected verbatim into every review agent, so no @imports or file references. Triggers: "gerar review.md", "create review.md", "configure cloud review", "review-md".'
---

# Generate REVIEW.md

Produce a `REVIEW.md` at the repository root so Claude Code's built-in review engine — the cloud
Code Review triggered by `@claude review` on PRs, and `/code-review ultra` — enforces the same
rules as `/bymax-quality:code-review`. The file is injected verbatim into the system prompt of
every agent in Anthropic's review pipeline as the highest-priority instruction block.

## Hard constraints on the output

- **Self-contained.** `REVIEW.md` is pasted verbatim: `@` imports are NOT expanded and referenced
  files are NOT read. Every rule must be written out in the file itself — never "see
  `docs/guidelines/...`".
- **Short.** Length dilutes priority. Target ≤ 100 lines; keep only rules that change review
  behavior. General project context stays in `CLAUDE.md`.
- **English**, plain markdown, no frontmatter.

## Steps

1. **Read the sources:** the repo's `CLAUDE.md` (and `AGENTS.md` if present) for project-specific
   invariants worth enforcing on every PR (logger rules, constants imports, banned patterns), and
   the `/bymax-quality:code-review` checklist for the universal Bymax rules.
2. **Select what earns a slot.** Only rules the built-in reviewer would not already enforce by
   default (it already hunts correctness bugs — do not restate that) and that are objective enough
   to check in a diff. Prefer the project's top 5–8 invariants over an exhaustive list.
3. **Write `REVIEW.md`** at the repo root from the template below, filling the "Always check"
   section with the project-specific invariants found in step 1.
4. **Show the result** to the user and point out which project rules were included and which were
   left out (and why). Do not commit — the user commits.
5. If a `REVIEW.md` already exists, read it first and refresh it in place, preserving any
   hand-written rules that don't conflict with the template sections.

## Template

```markdown
# Review instructions

## What Important means here

Reserve 🔴 Important for findings that would break behavior, leak data, or block a
rollback: incorrect logic, injection or XSS, unscoped queries, PII or credentials in
logs, and non-backward-compatible migrations. Style, naming, and refactoring
suggestions are Nit at most — with the exceptions listed under "Escalations".

## Escalations

Treat these as 🔴 Important even though they look stylistic:

- Any new suppression comment: `eslint-disable` (any form), `@ts-ignore`,
  `@ts-expect-error`, `@ts-nocheck`, `as any`, `as unknown as <T>` used to silence a
  real type error, Rust `#[allow(...)]` without a justification, `unsafe` without a
  `// SAFETY:` comment.
- Hardcoded credentials, API keys, or tokens anywhere, including test fixtures.
- `--no-verify` / `--skip-checks` added to any script or hook.

## Cap the nits

Report at most 5 Nits per review; if you found more, say "plus N similar items" in the
summary. After the first review round on a PR, suppress new nits and post Important
findings only. Lead the summary with the finding counts per severity.

## Do not report

- Anything CI already enforces: lint, formatting, type errors.
- Generated files, lockfiles (`*.lock`, `pnpm-lock.yaml`), vendored code, and
  build output.
- Test-only code that intentionally violates production rules.
- Missing test coverage (tracked by a separate gate).

## Always check

<!-- Project-specific invariants distilled from CLAUDE.md — replace per repo. -->
- Comments, JSDoc, and identifiers are in English.
- No plan/phase/task references in committed comments.
- Behavior claims in findings must cite a file:line in the source, not an inference
  from naming.
```

## Keeping it in sync

`/bymax-quality:code-review` remains the local gate (it blocks; the built-in never does).
`REVIEW.md` is the distilled projection of the same rules for the cloud engine. When the
checklist gains a rule worth cloud enforcement, re-run this command to refresh the file.
