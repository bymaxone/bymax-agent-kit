# 🏗️ Bymax Bootstrap

> One-shot scaffolding for new projects with strict TypeScript, ESLint flat-config, Prettier, format-on-save VS Code, Husky + commitlint + lint-staged, and `CLAUDE.md` / `AGENTS.md` / `README.md` templates.

## Install

```bash
claude plugin marketplace add bymaxone/bymax-agent-kit
claude plugin install bymax-bootstrap@bymax-agent-kit
```

### Also in Codex

The same procedures ship in the Codex package as `bymax-bootstrap`, `bymax-upgrade-standards` (namespaced `bymax-codex:<name>`). Install it with `./scripts/install-codex.sh` from a checkout — see [CODEX.md](../../CODEX.md) for the entrypoints and the capability boundaries, which are not full parity.

## What you get

### Slash commands

| Command              | Purpose                                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------------------------- |
| `/bymax-bootstrap:bootstrap`         | New project — full scaffold. Detects (or asks) the stack, picks the right ESLint preset, writes everything. |
| `/bymax-bootstrap:upgrade-standards` | Existing project — non-destructive incremental upgrade with confirmation per change.                     |

### Templates (20)

#### TypeScript / JavaScript tooling

| File                              | Purpose                                                       |
| --------------------------------- | ------------------------------------------------------------- |
| `tsconfig.universal.json`         | Strict TS + `noUncheckedIndexedAccess` + path aliases.        |
| `prettier.universal.json`         | 100 col, single quotes, trailing comma all, LF.               |
| `editorconfig.universal`          | Cross-IDE consistency (indent, EOL, trim trailing).           |
| `gitignore.universal`             | Comprehensive ignores for Node / Next / Expo / Vite / etc.    |
| `vscode-settings.json`            | Format on save, ESLint flat-config, Tailwind IntelliSense.    |
| `vscode-extensions.json`          | Recommended extensions on first repo open.                    |
| `commitlint.universal.cjs`        | Conventional Commits enforcement.                             |
| `lint-staged.universal.cjs`       | Stage-only lint + format on commit.                           |
| `husky-pre-commit`                | Runs lint-staged on staged files.                             |
| `husky-commit-msg`                | Runs commitlint on the message.                               |

#### ESLint flat-configs (5 base + 1 overlay)

| File                                 | Stack                                                  |
| ------------------------------------ | ------------------------------------------------------ |
| `eslint.config.universal.cjs`        | Composable base layer (security plugin + import-order + suppression bans + risky-import bans + Prettier integration). Each per-stack config spreads this on top of its preset. |
| `eslint.config.next.cjs`             | Next.js + TypeScript (App Router or Pages).            |
| `eslint.config.expo-rn.cjs`          | Expo / React Native + TypeScript.                      |
| `eslint.config.vite-react.cjs`       | Vite + React + TypeScript.                             |
| `eslint.config.node.cjs`             | Node backend (Express / Fastify / Hono / NestJS / plain Node). |
| `eslint.config.tailwind.cjs`         | **Overlay** — spread on top of any base. Auto-detects Tailwind major version. v3: just sorting + shorthand + no-contradicting. v4: adds canonical-class warnings (CSS variable shorthand `(--x)` and ARIA boolean variants `aria-invalid:`, etc.). |

All five base configs enforce: no cross-feature imports, ban `enum` (use unions), ban suppression comments, force `node:crypto` over plain `crypto`, ban `bcrypt`/`crypto-js`/`md5`/`uuid`/`nanoid`.

#### Project + workflow doc templates (4)

| File                       | Used by                                |
| -------------------------- | -------------------------------------- |
| `claude-md.template.md`    | `/bymax-bootstrap:bootstrap` — generates `CLAUDE.md` in the new project. |
| `spec.template.md`         | `/bymax-workflow:spec` (in `bymax-workflow`)          |
| `roadmap.template.md`      | `/bymax-workflow:roadmap` (in `bymax-workflow`)       |
| `phase-tasks.template.md`  | `/bymax-workflow:phase-tasks` (in `bymax-workflow`)   |

These render `CLAUDE.md`, then the spec → roadmap → phase-tasks docs your project's `docs/` ends up with.

> Looking for the **public-facing** project starter templates (the elaborate `CLAUDE.md`, `AGENTS.md`, and `README.md`)? Those live at the repo root in [`/templates/`](../../templates/). The `claude-md.template.md` here is the leaner template that `/bymax-bootstrap:bootstrap` writes for new projects — the root templates are reference / fork material, not consumed by `/bymax-bootstrap:bootstrap`.

## The flow

### New project

```bash
cd ~/projects/my-new-app
# tell Claude Code:
"bootstrap a new Next.js project here"
# /bymax-bootstrap:bootstrap activates → detects stack → asks confirmation → writes all configs
# you `pnpm install` and run all four gates:
pnpm type-check && pnpm lint && pnpm format:check && pnpm test --passWithNoTests
```

### Existing project (non-destructive)

```bash
cd ~/projects/legacy-app
# tell Claude Code:
"upgrade this project to Bymax standards"
# /bymax-bootstrap:upgrade-standards activates → audits → groups changes by risk → asks per bucket
```

🟢 Safe (auto-applied with one confirm): `.vscode/`, `.editorconfig`, `.gitignore` merge, Prettier, `CLAUDE.md` if missing.
🟡 Needs install (asks): Husky + commitlint + lint-staged + security plugin.
🔴 Potentially breaking (asks per item, dry-runs first): strengthen `tsconfig.json`, promote rules from `warn` to `error`, ban `enum`, ban cross-feature imports.

## License

MIT — see [root LICENSE](../../LICENSE).
