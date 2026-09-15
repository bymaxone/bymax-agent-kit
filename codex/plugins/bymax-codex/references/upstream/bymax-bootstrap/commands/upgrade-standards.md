---
description: 'Audit an EXISTING project and apply universal best practices incrementally and non-destructively. Adds what''s missing (.vscode, Prettier, Husky, EditorConfig, CLAUDE.md), proposes strengthening tsconfig and ESLint with explicit user confirmation per change. Never overwrites existing configs silently. Triggers: "upgrade standards", "apply standards", "improve setup", "trazer boas práticas", "atualizar config", "padronizar projeto".'
---

# Upgrade Standards Command

For projects that already exist and may already have *some* of the standards. The goal is to bring the project closer to `/bymax-workflow:standards` **without breaking anything that currently works**.

## When to use

- Existing repo missing `.vscode`, Prettier, Husky, or `CLAUDE.md`.
- TypeScript not strict, or `noUncheckedIndexedAccess` not enabled.
- ESLint flat-config missing the security / import-order plugins.
- No Conventional Commits enforcement.

## When NOT to use

- Brand-new project — use **`/bymax-bootstrap:bootstrap`** instead.
- Project that follows a different (intentional) convention you want to preserve. This skill respects "no" answers.

## Workflow

### Step 1 — Audit

Read the project and produce a diff against `/bymax-workflow:standards`. Check each item:

| Area | Check |
|---|---|
| TS strict | `tsconfig.json` → `strict: true`, `noUncheckedIndexedAccess: true`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `noUnusedLocals`, `noUnusedParameters` |
| Path aliases | `paths` in `tsconfig.json` (`@/*` etc.) |
| ESLint | `eslint.config.*` exists, has `eslint-plugin-import`, `eslint-plugin-security`, `eslint-plugin-prettier`, `eslint-config-prettier` |
| ESLint stack-specific | `eslint-config-next` / `eslint-config-expo` / `typescript-eslint` strict |
| Suppression bans | `@typescript-eslint/ban-ts-comment` enforced; `no-restricted-syntax` blocks `enum` |
| Cross-feature imports | `no-restricted-imports` rule on `src/features/**` |
| Prettier | `.prettierrc*` exists with sane settings |
| EditorConfig | `.editorconfig` exists |
| Gitignore | `.gitignore` covers node_modules, dist, build, .env*, coverage |
| VS Code | `.vscode/settings.json` (format on save) and `.vscode/extensions.json` |
| Husky | `.husky/` with `pre-commit` and `commit-msg` |
| lint-staged | `lint-staged.config.*` or `package.json#lint-staged` |
| commitlint | `commitlint.config.*` |
| Scripts | `lint`, `format`, `format:check`, `type-check`, `test`, `prepare` |
| CLAUDE.md | `CLAUDE.md` exists |

Output the audit as a table with three columns: **Item · Status (✅ / ⚠️ / ❌) · Recommendation**.

### Step 2 — Group changes by risk

Sort missing/incorrect items into three buckets:

**🟢 Safe** (will not break anything):
- Add `.vscode/settings.json` and `extensions.json`
- Add `.editorconfig`
- Add missing `.gitignore` entries (merge, never overwrite existing rules)
- Add `CLAUDE.md` if missing (use the universal template)
- Add `prettier` if missing (only formats; never breaks)
- Add `eslint-plugin-import` and `eslint-plugin-security` to ESLint config (start at `warn`, not `error`)

**🟡 Needs install** (adds deps but non-breaking):
- Add Husky + lint-staged + commitlint
- Add Conventional Commits enforcement on new commits only

**🔴 Potentially breaking** (requires explicit confirmation per item):
- Strengthen `tsconfig.json` — `strict: true`, `noUncheckedIndexedAccess`, etc. **Will surface real type errors.** Show how many.
- Promote ESLint security/import rules from `warn` to `error`. **May fail CI.**
- Add `no-restricted-syntax: TSEnumDeclaration` ban. **Fails if any enum exists.**
- Add cross-feature import ban. **Fails if any cross-feature import exists.**

### Step 3 — Confirm per bucket

For each bucket, ask:

```
🟢 Safe changes (n items):
  - [list]
Apply all? (yes / pick / no)

🟡 Needs install (n items):
  - [list of deps]
Install + apply? (yes / no)

🔴 Potentially breaking (n items):
  Each one needs your call. Going one at a time.
```

For 🔴 items, dry-run first: enable the rule with `--no-fix`, show count of new errors, ask "fix now? defer? skip?" before committing.

### Step 4 — Apply

For each approved change:

- **Read** the corresponding template at `~/.claude/templates/`.
- **Diff** with the existing file (if any).
- **Merge** rather than replace whenever possible:
  - `.gitignore` — append missing entries with a comment header `# Added by /bymax-bootstrap:upgrade-standards`.
  - `package.json` — add scripts/devDeps without removing existing ones.
  - `tsconfig.json` — preserve existing `paths`, `include`, `exclude`; only modify `compilerOptions`.
  - `eslint.config.*` — if a flat config exists, append the universal layer at the end; if it's a legacy `.eslintrc`, ask whether to migrate.

### Step 5 — Verify

Run all four gates:

```bash
<pm> type-check
<pm> lint
<pm> format:check
<pm> test --passWithNoTests
```

Report any new failures introduced. If a 🔴 change introduced failures, give the user the choice to fix them now (suggest `/bymax-quality:code-review` or `/bymax-quality:tdd`) or revert that single change.

### Step 6 — Report

```
## Upgrade report

Applied (n):
  ✅ ...
  ✅ ...

Skipped (n):
  ⏸ ... (reason)

Pending — opted to defer:
  ⏳ tsconfig.strict — surfaced 23 type errors. Suggest: /bymax-quality:code-review then /bymax-quality:tdd to address.

New gate status:
  type-check: PASS
  lint:       PASS  (was: FAIL)
  format:     PASS
  test:       PASS

Next: commit with `chore: upgrade to universal standards`.
```

## Hard rules

- **Never overwrite an existing config silently.** Always diff and confirm.
- **Never weaken** existing settings the project already has. If their rule is stricter than the template, keep theirs.
- **Never bypass a gate.** No `--no-verify`. If a fix surfaces real issues, route through `/bymax-quality:code-review` or `/bymax-quality:tdd`, don't paper over.
- **Preserve intentional deviations.** If the project has documented reasons for a non-standard choice (in `CLAUDE.md` or an ADR), do not "fix" it.
