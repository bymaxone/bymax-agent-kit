---
description: 'Scaffold a NEW project (or empty repo) with universal best practices wired up — strict TypeScript, ESLint flat-config tailored to the stack, Prettier, .vscode (format on save), .editorconfig, .gitignore, Husky + commitlint + lint-staged, CLAUDE.md, path aliases, and Conventional Commits. Detects the stack (Next/Expo-RN/Vite-React/Node) and uses the right ESLint preset. Triggers: "novo projeto", "new project", "scaffold", "init project", "create project", "set up", "bootstrap", "starter", "boilerplate".'
---

# Bootstrap Command

One-shot setup for new projects. Wires everything from the universal `/bymax-workflow:standards` into a fresh repo without touching product code.

## When to use

- Starting a brand-new project — empty folder, fresh `pnpm init` repo, or empty git clone.
- Just ran `npx create-next-app`, `pnpm create vite`, `npx create-expo-app`, etc., and want to **upgrade the defaults** to your standards.
- Want a "Bymax-flavored" project (lime palette, Instrument Serif + DM Sans, etc.) — see the design-system skills after bootstrap.

## When NOT to use

- The project already has ESLint / Prettier / Husky configured. Use **`/bymax-bootstrap:upgrade-standards`** instead, which is non-destructive.

## Workflow

### Step 1 — Detect or ask

Read these to classify the stack:

1. `package.json` → `dependencies` and `scripts`
2. Presence of `next.config.*`, `expo`, `app.config.*`, `vite.config.*`, framework-specific files
3. If genuinely empty / ambiguous, **ask the user** which stack to target.

Stack profiles:

| Profile | Signals | ESLint template | Notes |
|---|---|---|---|
| **Next.js** | `next` in deps, `next.config.*` | `eslint.config.next.cjs` | App Router or Pages — both work |
| **Expo / RN** | `expo`, `react-native`, `app.config.*` | `eslint.config.expo-rn.cjs` | New Architecture preferred |
| **Vite + React** | `vite`, `react`, no `next` | `eslint.config.vite-react.cjs` | SPA or library |
| **Node backend** | `express`/`fastify`/`hono`/`@nestjs/core`, no React | `eslint.config.node.cjs` | API / worker / CLI |
| **Other / mixed** | none of the above | Ask user; fall back to universal-only | Vue/Svelte/etc. — universal layer still applies |

Also detect the **package manager** (presence of `pnpm-lock.yaml` / `yarn.lock` / `bun.lockb` / `package-lock.json`). Default to pnpm when none exists yet.

Detect optional UI lib:

- Tailwind: presence of `tailwind.config.*` or ask. **Also detect major version** — read `tailwindcss` from `package.json`. v4 → install `prettier-plugin-tailwindcss` + `eslint-plugin-tailwindcss` and copy the `eslint.config.tailwind.cjs` overlay (it auto-detects v3/v4 and applies canonical-class warnings on v4 only). v3 → install only `prettier-plugin-tailwindcss` (sorting works on both versions).
- shadcn/ui: presence of `components.json` or ask
- NativeWind: paired with Expo/RN. NativeWind 4 ships against **Tailwind 3** — do NOT enable v4 canonical-class rules; the long form (`bg-[var(--x)]`, `aria-[invalid=true]:`) is the only valid syntax there.
- Chakra: presence of `@chakra-ui/react` or ask

### Step 2 — Show the plan, wait for approval

Before writing anything, list every file that will be created/modified and ask for explicit confirmation. Example:

```
About to scaffold:
  ✚ tsconfig.json                              (strict + noUncheckedIndexedAccess + path aliases)
  ✚ eslint.config.cjs                          (Next.js preset + universal layer)
  ✚ .prettierrc.json
  ✚ .editorconfig
  ✚ .gitignore                                 (merged with existing if any)
  ✚ .vscode/settings.json
  ✚ .vscode/extensions.json
  ✚ commitlint.config.cjs
  ✚ lint-staged.config.cjs
  ✚ .husky/pre-commit
  ✚ .husky/commit-msg
  ✚ CLAUDE.md                                  (filled with detected stack)
  ✎ package.json                               (add scripts: lint / format / type-check / prepare)
  ✎ package.json devDependencies               (eslint, prettier, husky, lint-staged, commitlint, plugins)

Proceed? (yes / modify / cancel)
```

### Step 3 — Write files

For each file, **read** the corresponding template from the plugin's templates folder (`${CLAUDE_PLUGIN_ROOT}/templates/` when installed via marketplace, or `~/.claude/templates/` when restored via `scripts/install.sh`), customize the placeholders, and write it.

Templates and their targets:

| Template | Target |
|---|---|
| `tsconfig.universal.json` | `tsconfig.json` (adjust `paths` to project layout, drop DOM lib for Node, keep all strict flags) |
| `eslint.config.<stack>.cjs` | `eslint.config.cjs` (or `.js` if project is ESM-first) |
| `prettier.universal.json` | `.prettierrc.json` |
| `editorconfig.universal` | `.editorconfig` |
| `gitignore.universal` | `.gitignore` (merge with existing — never overwrite existing entries) |
| `vscode-settings.json` | `.vscode/settings.json` |
| `vscode-extensions.json` | `.vscode/extensions.json` |
| `commitlint.universal.cjs` | `commitlint.config.cjs` |
| `lint-staged.universal.cjs` | `lint-staged.config.cjs` |
| `husky-pre-commit` | `.husky/pre-commit` (then `chmod +x`) |
| `husky-commit-msg` | `.husky/commit-msg` (then `chmod +x`) |
| `claude-md.template.md` | `CLAUDE.md` (fill in `{{PROJECT_NAME}}`, `{{RUNTIME}}`, `{{FRAMEWORK}}`, etc.) |

After `CLAUDE.md` is written, seed the review calibration: run
`/bymax-quality:review-md` so the repo starts with a root `REVIEW.md` — the file
Anthropic's built-in Code Review (cloud `@claude review` on PRs, `/code-review
ultra`) injects into every review agent. Skip only if the plugin is not
installed; note it in the report so the user can run it later.

For the universal ESLint base, copy `eslint.config.universal.cjs` into the project so the stack config can `require('./eslint.config.universal.cjs')` without depending on `~/.claude/`.

### Step 4 — Update package.json

Add these scripts (preserve existing scripts):

```json
{
  "scripts": {
    "lint": "eslint .",
    "lint:fix": "eslint . --fix",
    "format": "prettier --write \"**/*.{ts,tsx,js,cjs,mjs,json,md,yml}\"",
    "format:check": "prettier --check \"**/*.{ts,tsx,js,cjs,mjs,json,md,yml}\"",
    "type-check": "tsc --noEmit",
    "prepare": "husky"
  }
}
```

Add devDependencies (use the project's package manager):

**Always:**
- `eslint@^9`
- `prettier@^3`
- `husky@^9`
- `lint-staged@^16`
- `@commitlint/cli@^20`
- `@commitlint/config-conventional@^20`
- `eslint-plugin-import@^2`
- `eslint-plugin-security@^3`
- `eslint-plugin-prettier@^5`
- `eslint-config-prettier@^10`
- `eslint-import-resolver-typescript@^4`
- `typescript@~5.9`
- `@types/node` (Node + Vite + Next stacks)

**Per-stack additions:**

| Stack | Extra deps |
|---|---|
| Next | `eslint-config-next`, `@eslint/eslintrc` |
| Expo / RN | `eslint-config-expo` |
| Vite + React | `typescript-eslint`, `eslint-plugin-react`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `globals`, `@eslint/js` |
| Node | `typescript-eslint`, `eslint-plugin-n`, `globals`, `@eslint/js` |

### Step 5 — Install + initialize

Run (using the detected package manager):

```bash
<pm> install
<pm> exec husky init    # creates .husky/_ and base hook stubs (we then overwrite pre-commit and commit-msg)
chmod +x .husky/pre-commit .husky/commit-msg
```

### Step 6 — Smoke test

Run all four gates to confirm everything is wired:

```bash
<pm> type-check
<pm> lint
<pm> format:check
<pm> test --passWithNoTests
```

If any fails, fix the underlying issue (never `--no-verify`).

### Step 7 — Report

Print:

```
✅ Bootstrap complete.

Stack:        <profile>
Pkg manager:  <pm>
Files added:  <count>
Scripts:      lint, lint:fix, format, format:check, type-check, prepare
Hooks:        pre-commit (lint-staged), commit-msg (commitlint)

Next steps:
  - git add . && git commit -m "chore: bootstrap project with universal standards"
  - Open in VS Code — accept the recommended extensions
  - When you start a feature: /bymax-workflow:brainstorm or /bymax-workflow:plan
  - Review REVIEW.md (cloud code-review calibration) — refresh anytime with /bymax-quality:review-md
```

## Rules

- **Never overwrite an existing config silently.** If `tsconfig.json`, `eslint.config.*`, `.prettierrc*`, etc. already exist, stop and route the user to `/bymax-bootstrap:upgrade-standards`.
- **Merge, don't replace** for `.gitignore` and `package.json` — preserve existing content; add missing entries.
- **Fix root cause if a gate fails.** No `--no-verify`, no `// @ts-ignore`. See `/bymax-workflow:standards` §8.
- **Defer to project specifics.** This is the universal floor. Project-specific rules go into `CLAUDE.md`, not into the global templates.

## Integration with other commands

```
/bymax-bootstrap:bootstrap   →  set up infrastructure (this command)
    ↓
/bymax-workflow:brainstorm  →  refine first feature idea
    ↓
/bymax-workflow:plan / /bymax-quality:tdd / /bymax-workflow:verify / /bymax-quality:code-review  →  build
```
