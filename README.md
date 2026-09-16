<p align="center">
  <img src="https://img.shields.io/badge/%40bymaxone-claude--code-A3FF3C?style=for-the-badge&logo=anthropic&logoColor=000000" alt="@bymaxone/claude-code" />
</p>

<h1 align="center">Bymax Claude Code</h1>

<p align="center">
  <strong>A complete, opinionated toolkit for Claude Code</strong><br />
  <sub>Phased Planning · Loop-Engineering Autopilot · Strict Quality Gates · Project Bootstrap · Mobile Sims · Battle-tested Templates</sub>
</p>

<p align="center">
  <a href="https://github.com/bymaxone/bymax-claude-code/blob/main/LICENSE"><img src="https://img.shields.io/github/license/bymaxone/bymax-claude-code?style=flat-square&colorA=000000&colorB=000000" alt="license" /></a>
  <a href="https://github.com/bymaxone/bymax-claude-code/stargazers"><img src="https://img.shields.io/github/stars/bymaxone/bymax-claude-code?style=flat-square&colorA=000000&colorB=000000" alt="stars" /></a>
  <a href="https://github.com/bymaxone/bymax-claude-code"><img src="https://img.shields.io/badge/Claude_Code-marketplace-A3FF3C?style=flat-square&colorA=000000" alt="claude code marketplace" /></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-strict-3178C6?style=flat-square&logo=typescript&logoColor=white" alt="TypeScript" /></a>
  <a href="https://www.rust-lang.org/"><img src="https://img.shields.io/badge/Rust-edition%202024-000000?style=flat-square&logo=rust&logoColor=white" alt="Rust" /></a>
  <a href="https://eslint.org/"><img src="https://img.shields.io/badge/ESLint-flat--config-4B32C3?style=flat-square&logo=eslint&logoColor=white" alt="ESLint" /></a>
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square&colorA=000000" alt="PRs welcome" />
</p>

<p align="center">
  <a href="#-overview">Overview</a> ·
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-plugins">Plugins</a> ·
  <a href="#-the-workflow">The Workflow</a> ·
  <a href="#-loop-engineering-the-autopilot">Loop Engineering</a> ·
  <a href="#-architecture">Architecture</a> ·
  <a href="#-contributing">Contributing</a>
</p>

---

## ✨ Overview

**Installing or updating?** Start with [INSTALL.md](./INSTALL.md) for prerequisites, both runtimes, hooks, authentication and verification.

**Using Codex?** Read [CODEX.md](./CODEX.md) for the separate Codex package, one-command installation, native code review, and capability boundaries. The Claude installation below is unchanged.

**Bymax Claude Code** is a production-ready toolkit that turns Claude Code into a **disciplined senior engineer**. Instead of ad-hoc prompts, you get:

- A **phased planning workflow** (spec → roadmap → phase-tasks → task) with explicit user-approval gates and JIRA-style dashboards.
- A **loop-engineering autopilot** (`/bymax-workflow:autopilot`) that executes an approved roadmap **autonomously, end to end** — one merge-gated PR per phase, isolated worktree sub-agents, background CI/review watching, and dashboards kept in sync — turning the planning docs into a self-driving build. See [Loop Engineering](#-loop-engineering-the-autopilot).
- **Strict quality gates** — `/code-review` (CRITICAL → LOW), `/tdd` (red-green-refactor), `/verify` (5 checks), and a `secret-scanner` hook that **blocks** writes containing credentials.
- **Seven specialist sub-agents** (architect, code-reviewer, security-reviewer, typescript-reviewer, rust-reviewer, database-reviewer, planner) ready to delegate to.
- **A whole-system QA + security audit** (`/bymax-qa:audit`) that runs as the Security QA engineer of your agent team. Point it at a **Jira ticket** (acceptance criteria verified PASS/FAIL with evidence), a **branch or PR** (the hunt scoped to the change), or the **whole system**: a stack + threat map, read-only per-domain finders, live probes against allow-listed hosts only, and a finding admitted **only after an independent verifier reproduces it** — then handed to the owning agent, filed as a GitHub issue, or commented back on the ticket, and re-tested until it holds.
- **TypeScript _and_ Rust** — the quality + workflow skills are language-detecting: TypeScript rules for `package.json` projects, and a parallel **Rust track** (clippy/rustfmt with `-D warnings`, typed `thiserror` errors, `#![forbid(unsafe_code)]`, rustdoc, `cargo test` + `cargo llvm-cov`, `cargo deny`/`audit`/`vet`) for `Cargo.toml` projects.
- **Project bootstrap** with strict TypeScript, ESLint flat-config (security plugin + import-order + suppression bans), Prettier, format-on-save VS Code, Husky + commitlint + lint-staged — for **Next.js, Expo / React Native, Vite + React, and Node backends (Express / Fastify / Hono / NestJS / plain Node)** stacks.
- **Mobile sims** — `/sim-ios` and `/sim-android` boot the iOS Simulator and Android Emulator on Expo / React Native projects in one command (auto-detects whether to reattach Metro or do a full rebuild).
- **Beautiful starter templates** for `CLAUDE.md`, `AGENTS.md`, and `README.md` — distilled from real production projects.

Built and used daily across mobile (Expo / React Native) and web (Next.js / NestJS) products.

### Why this exists

Every Claude Code user reinvents the same scaffolding: standards docs, review skills, planning rituals, ESLint configs, hooks, agents. This repo packages a **battle-tested set** that works across stacks — install once, focus on your product.

```bash
claude plugin marketplace add bymaxone/bymax-claude-code
claude plugin install bymax-workflow@bymax-claude-code
claude plugin install bymax-quality@bymax-claude-code
claude plugin install bymax-bootstrap@bymax-claude-code
claude plugin install bymax-mobile@bymax-claude-code
claude plugin install bymax-web-verify@bymax-claude-code
claude plugin install bymax-pr@bymax-claude-code
claude plugin install bymax-pm@bymax-claude-code
claude plugin install bymax-qa@bymax-claude-code
```

That's it. Restart Claude Code and you have **8 installable plugins** with **23 slash commands**, **6 skills**, **10 sub-agents**, **4 hooks**, and **26 templates** — the full workflow ready.

---

## 🚀 Quick Start

### 1. Install the marketplace

```bash
claude plugin marketplace add bymaxone/bymax-claude-code
```

### 2. Install plugins

Claude Code installs plugins individually — install the ones you want:

```bash
claude plugin install bymax-workflow@bymax-claude-code      # planning + execution
claude plugin install bymax-quality@bymax-claude-code       # review + TDD + agents + hooks
claude plugin install bymax-bootstrap@bymax-claude-code     # scaffold new projects
claude plugin install bymax-mobile@bymax-claude-code        # iOS Simulator + Android Emulator
claude plugin install bymax-web-verify@bymax-claude-code    # real-browser verification (needs agent-browser)
claude plugin install bymax-pr@bymax-claude-code            # autonomous PR babysitting (needs gh CLI)
claude plugin install bymax-pm@bymax-claude-code            # engineering PM for multi-agent development
claude plugin install bymax-qa@bymax-claude-code            # whole-system QA + security audit
```

> Plugins install user-wide by default (available in every project). To pin a plugin to a single project instead, add it to `enabledPlugins` in that project's `.claude/settings.json`.

### 3. Restart Claude Code

Reopen your terminal session so the new commands and hooks are picked up.

### 4. Verify

In Claude Code, type `/` — you should see all the `bymax-*` commands. Try:

```
/bymax-workflow:standards     # show the universal coding rules
/bymax-workflow:spec          # start a new feature spec
/bymax-bootstrap:bootstrap    # scaffold a new project
```

Non-interactive check: `claude plugin list` should show every plugin you installed.

> 🤖 **AI agents**: installing this toolkit for a user? Follow the step-by-step runbook in [`llms-install.md`](./llms-install.md) — idempotent commands, verification after each step, and the DO-NOT list.

---

## 🔌 External tools & MCP servers

The plugins follow a **"require, don't embed"** philosophy: external CLIs and MCP servers are consulted at runtime, never bundled. Nothing below is needed to *install* the plugins — but each row unlocks a plugin or makes the skills measurably better. Install what matches your usage.

> Rows below reference **"§0"** — the [simplicity ladder](./plugins/bymax-workflow/skills/standards/SKILL.md) that opens the `/bymax-workflow:standards` skill: a reuse-first decision ladder (YAGNI → reuse → stdlib → installed dep → minimum that works) the agent runs before writing any code. "§15" is the same skill's Rust track.

### CLI toolchain

| Tool | Needed by | How to install |
|---|---|---|
| **Node.js ≥ 18** | plugin hooks (`secret-scanner`, `console-log-scan`, `check-agent-browser`), all `npx`-based tooling | `brew install node` (or `nvm`) — must be on the non-interactive shell's PATH |
| **`git` + `gh` CLI** (authenticated) | `bymax-pr` — every GitHub operation in `/bymax-pr:babysit-pr` (PR checks, CI logs, thread resolution); `bymax-qa` — filing findings as issues or advisories and re-testing a claimed fix from a PR | `brew install gh && gh auth login` |
| **Security scanners** — `semgrep`, `gitleaks`, `trufflehog`, `osv-scanner`, `trivy`, `nuclei`, `zap`, `sqlmap`, `jwt_tool` — **all optional** | `bymax-qa` — the deterministic layer of `/bymax-qa:audit` uses whichever are on PATH and records the rest as a coverage gap; none is bundled or required | install per tool as needed (e.g. `brew install semgrep gitleaks osv-scanner trivy`); run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/qa-tools.sh` inside an audit to see what is detected |
| **`axe` + Lighthouse** — **optional** | `bymax-qa` frontend domain (accessibility + Core Web Vitals), driven through `bymax-web-verify` when a UI is present | `npm i -g @axe-core/cli lighthouse` |
| **`docker` + `docker compose`** — optional | `bymax-qa` `--live` — brings a target stack up for live probes against `local`/`staging` hosts | [docs.docker.com](https://docs.docker.com/get-docker/) |
| **`agent-browser`** | `bymax-web-verify` — drives the real browser | run `/bymax-web-verify:setup` once (installs the CLI + Chrome for Testing, ends with a smoke test) |
| **Codex CLI** (authenticated) — **optional** | `bymax-quality` — Review B, the independent second opinion `/bymax-quality:code-review` runs in *every* mode | run `/bymax-quality:codex-setup` once (Homebrew cask or npm, then an interactive `codex login`, then a real review run to prove it) |
| **OpenAI Codex plugin** — `codex@openai-codex`, **optional** | `bymax-quality` — Review C, the adversarial second opinion, only under `/bymax-quality:code-review --adversarial`; needs the row above as well, since the script gates on the CLI and its session before it looks for the plugin | `claude plugin marketplace add openai/codex-plugin-cc`, then `claude plugin install codex@openai-codex` — the plugin is `codex`, its marketplace `openai-codex`, the repo behind it `openai/codex-plugin-cc`; type both commands as written |
| **pnpm** | `/bymax-workflow:verify`, `/bymax-workflow:task`, `/bymax-quality:tdd` and the `tester` skill on pnpm repos | `corepack enable pnpm` |
| **Xcode + Command Line Tools** | `bymax-mobile` `/sim-ios` (`xcrun simctl`) | App Store (Xcode) + `xcode-select --install` — macOS only |
| **Android Studio SDK** (`adb` + `emulator` on PATH) | `bymax-mobile` `/sim-android` | [developer.android.com/studio](https://developer.android.com/studio), then add `platform-tools` and `emulator` to PATH |
| **Rust toolchain + cargo extras** | the Rust track of `/bymax-workflow:verify` and `/bymax-workflow:standards` §15 | [`rustup`](https://rustup.rs), then `cargo install cargo-llvm-cov cargo-mutants cargo-deny cargo-audit cargo-vet` |
| **graphify** (PyPI package `graphifyy`) | graph-first reuse scan in `/bymax-workflow:standards` §0 and the planner (opt-in per project) | see [Code knowledge graph](#code-knowledge-graph--graphify-recommended-opt-in) below |

### MCP servers (optional — sharper results, never required)

The skills degrade gracefully when a server is absent; when present, they use it. All three are registered per-user (no project changes needed); restart Claude Code to activate.

| Server | What it improves | How to install |
|---|---|---|
| **context7** ([`@upstash/context7-mcp`](https://github.com/upstash/context7)) | `/bymax-workflow:standards` §0 mandates **official docs over trained memory** for library/platform APIs — context7 fetches current, version-accurate docs so generated calls match the installed version | `claude mcp add context7 -- npx -y @upstash/context7-mcp` — or copy [`personal/mcp.template.json`](./personal/mcp.template.json) to `~/.mcp.json` and enable via `~/.claude/settings.local.json` (see [`personal/README.md`](./personal/README.md)) |
| **obsidian vault** ([`@bitbonsai/mcpvault`](https://www.npmjs.com/package/@bitbonsai/mcpvault)) | the §0 simplicity ladder consults a knowledge vault (per-stack `Patterns.md` / `Gotchas.md` notes) before inventing a new pattern — a growing, cross-project memory of the conventions your team already settled | `claude mcp add obsidian -- npx -y @bitbonsai/mcpvault@latest /path/to/your/vault` — any Obsidian vault directory works; start with a `Patterns.md` per stack |
| **sequential-thinking** ([`@modelcontextprotocol/server-sequential-thinking`](https://github.com/modelcontextprotocol/servers)) | structured multi-step reasoning during `/bymax-workflow:plan` and `/bymax-workflow:spec` on gnarly problems | `claude mcp add sequential-thinking -- npx -y @modelcontextprotocol/server-sequential-thinking` — also pre-wired in `personal/mcp.template.json` |

> **Verify what's active:** run `claude mcp list` in a terminal. A server listed but not enabled needs its name in `enabledMcpjsonServers` inside `~/.claude/settings.local.json`.

### Code knowledge graph — [graphify](https://github.com/Graphify-Labs/graphify) (recommended, opt-in)

The skills' **reuse ladder** (`/bymax-workflow:standards` §0 and the planner's Reuse Scan) constantly asks one question: *"does something already do this?"*. On a monorepo, answering it with grep means many searches and many file reads — the most token-expensive phase of any session. [graphify](https://github.com/Graphify-Labs/graphify) (MIT, ~79k ⭐) answers it from a pre-built graph instead.

**How it works:**

1. `/graphify .` parses the project with **tree-sitter AST — fully local, deterministic, zero LLM tokens** for code; nothing leaves your machine. Output lands in `graphify-out/` (`graph.json` + `GRAPH_REPORT.md` + a clickable `graph.html`).
2. Cross-file `calls` / `imports` / `inherits` edges are resolved across ~40 languages (TypeScript and Rust included), each tagged `EXTRACTED` (explicit in source) or `INFERRED`.
3. Rebuilds are incremental (SHA256 cache — only changed files reprocess), and a post-commit hook keeps the graph fresh automatically.
4. From then on the agent queries instead of grepping: `graphify query "<question>"` (scoped subgraph), `graphify explain "<symbol>"` (one concept + all its connections), `graphify path A B` (how two things connect).

**How this toolkit uses it — presence-gated, zero always-on cost:**

- When `graphify-out/` exists in a project, the §0 simplicity ladder (rung 2) and the planner's Reuse Scan go **graph-first**: `graphify query` before `grep`.
- When it doesn't exist, everything behaves exactly as before — grep/Glob. No hooks, no per-prompt overhead, nothing to configure.
- **grep stays authoritative for fresh edits**: the graph refreshes on commit, not on every keystroke, so code written mid-session is always re-verified with grep.

**Setup (per machine, then per project):**

```bash
# 1. Install the CLI — note the package is `graphifyy` (double-y);
#    other graphify* names on PyPI are NOT affiliated.
uv tool install graphifyy        # or: pipx install graphifyy  (needs Python ≥ 3.10)

# 2. Register the skill with Claude Code (adds the /graphify command)
graphify install

# 3. In each project you want mapped — build the graph:
#    (inside Claude Code)  /graphify .

# 4. Keep it fresh automatically (post-commit rebuild):
graphify hook install
```

**Our recommendation:**

- ✅ **Do** install the CLI + skill and build graphs for your active repos — the reuse-scan savings compound with repo size, and the build itself costs zero LLM tokens.
- ✅ **Do** run `graphify hook install` so the graph tracks your commits.
- ✅ **Do** keep `graphify-out/` out of git — it's local, regenerable output (the `bymax-bootstrap` `.gitignore` template already excludes it).
- ❌ **Don't** run `graphify claude install` (the "always use the graph" mode). It installs `PreToolUse` hooks that fire before **every** search/read tool call — per-prompt overhead, and it conflicts with the `bymax-quality` hooks. This toolkit's presence-gated integration achieves the same benefit without the noise.
- ⚠️ Treat third-party "70x fewer tokens" claims as marketing; the honest way to measure is your own cache-hit ratio (`npx ccusage session --json` — [ccusage](https://github.com/ryoppippi/ccusage) is a community CLI that reads Claude Code's local usage data; consistently above ~60% on graph-enabled repos means it's working).

---

## 📦 Plugins

The toolkit ships as **eight composable plugins** (plus a reference index). Use them à la carte or all at once via `bymax-all`.

### 🧭 [`bymax-workflow`](./plugins/bymax-workflow/) — Planning + Execution

End-to-end feature pipeline with explicit approval gates between every layer.

| Command        | Purpose                                                                                               |
| -------------- | ----------------------------------------------------------------------------------------------------- |
| `/spec`        | Layer 1: write a complete technical spec (goal, scope, stories, criteria, risks). Asks if vague.      |
| `/roadmap`     | Layer 2: take an approved spec → phased master plan with status dashboard, dependency DAG, DoD.       |
| `/phase-tasks` | Layer 3: take an approved roadmap → JIRA-style task files with self-contained agent prompts per task. |
| `/task`        | Execute a phase or single task end-to-end with `/verify` → `/security-review` (Claude Code built-in) → `/code-review` chain. |
| `/brainstorm`  | Pre-spec: refine vague ideas, explore alternatives, surface tradeoffs.                                |
| `/plan`        | Lightweight plan for single-task work that doesn't need the full spec → roadmap → tasks chain.        |
| `/verify`      | 5-gate verification (static checks, exercise, root-cause, regression scan, acceptance criteria).      |
| `/checkpoint`  | Snapshot SHA + tests + coverage to compare against later (e.g., "did this refactor regress tests?").  |

Plus two skills:

- **`/standards`** — **universal coding rules** (TypeScript and Rust tracks) referenced by every other command.
- **`/autopilot`** — the **loop-engineering executor**: drives an approved roadmap to done autonomously, one merge-gated PR per phase. `init` generates the per-project `docs/AUTOPILOT.md` config (and stops for your review); `run` owns the whole chain — spawn implementer → watch CI + review bot → fix findings → merge after the gate + grace window → update dashboards → next phase. Full story in [Loop Engineering](#-loop-engineering-the-autopilot).

### 🛡️ [`bymax-quality`](./plugins/bymax-quality/) — Review + Testing + Agents

Strict quality gates and specialist reviewers.

| Item                    | Purpose                                                                                                                                    |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `/code-review` | Bounded Claude + Codex review: shared context, pinned candidate, verified findings, correction deltas and explicit check evidence. Standalone review permits three candidates; autonomous delivery permits six across pushes. Nits do not force a loop; missing reviewers leave certification incomplete. |
| `/codex-setup`          | Installs + authenticates the Codex CLI that powers `code-review`'s independent second review (Homebrew cask or npm), then verifies it with a real review run. Optional — everything works without it. |
| `/review-md`            | Generates a repo-root `REVIEW.md` so Anthropic's cloud Code Review (`@claude review`, `/code-review ultra`) enforces the same Bymax rules the local gate blocks on. |
| `/tdd`                  | Strict red-green-refactor cycle (Jest/Vitest or Rust `#[test]`/`cargo test`). Forces failing test before implementation. 80%+ coverage minimum. |
| `tester` skill          | Multi-stack test writer — auto-detects Jest / Vitest / RN / pure logic / Rust `cargo test`. 100% file coverage. Rich `it()` / `#[test]` comments. |
| `architect` agent       | System design, scalability, technical decisions.                                                                                           |
| `code-reviewer`         | Quality + security + maintainability review (proactive).                                                                                   |
| `security-reviewer`     | OWASP Top 10, secrets, SSRF, injection, unsafe crypto.                                                                                     |
| `typescript-reviewer`   | Type safety, async correctness, idiomatic patterns.                                                                                        |
| `rust-reviewer`         | Ownership/borrow correctness, typed errors, async/Tokio soundness, `unsafe` discipline, idiomatic crate design.                            |
| `database-reviewer`     | PostgreSQL: query optimization, schema design, security.                                                                                   |
| `planner`               | Complex feature and refactor planning.                                                                                                     |
| `secret-scanner` hook   | **PreToolUse** — blocks Write/Edit/MultiEdit if AWS keys, GitHub PATs, OpenAI/Anthropic/Stripe tokens, JWTs, or private keys are detected. |
| `console-log-scan` hook | **Stop** — warns on stray `console.log/warn/error/debug/info` in modified TS/JS files.                                                     |

`/code-review` also flags **30+ Tailwind v4 canonical-class patterns** in projects on Tailwind 4 (skipped on v3 / NativeWind 4): CSS variable shorthand (`[var(--x)]` → `(--x)`), ARIA boolean variants (`aria-[invalid=true]:` → `aria-invalid:`), on-scale `rem` values (`[8rem]` → `32`), gradient renames (`bg-gradient-to-r` → `bg-linear-to-r`), scale shifts (`shadow` → `shadow-sm`, `rounded` → `rounded-sm`, etc.), individual renames (`outline-none` → `outline-hidden`, `flex-shrink-*` → `shrink-*`, etc.), opacity-modifier deprecation (`bg-opacity-50` → `bg-blue-500/50`), arbitrary z-index integers (`z-[200]` → `z-200`), on-scale filter px (`backdrop-blur-[12px]` → `backdrop-blur-md`), and negative zero (`-bottom-0` → `bottom-0`). Full reference in `/standards § 12`.

### 🏗️ [`bymax-bootstrap`](./plugins/bymax-bootstrap/) — Project Scaffold

Set up a new project with **all the standards wired** in one shot. Detects the stack, picks the right ESLint preset, writes `.vscode/`, `tsconfig.json`, `.prettierrc.json`, `.editorconfig`, `.gitignore`, `commitlint.config.cjs`, `lint-staged.config.cjs`, `.husky/{pre-commit,commit-msg}`, and a `CLAUDE.md` filled with detected stack.

| Command              | Purpose                                                                    |
| -------------------- | -------------------------------------------------------------------------- |
| `/bootstrap`         | New project — full scaffold (asks/detects stack first).                    |
| `/upgrade-standards` | Existing project — non-destructive incremental upgrade with confirmations. |

#### Stacks supported by the ESLint flat-configs

| Stack                                                             | Config                              |
| ----------------------------------------------------------------- | ----------------------------------- |
| **Next.js** (15+/16) + TypeScript (App Router or Pages)           | `eslint.config.next.cjs`            |
| **Expo / React Native** + TypeScript                              | `eslint.config.expo-rn.cjs`         |
| **Vite + React** + TypeScript (SPA or library)                    | `eslint.config.vite-react.cjs`      |
| **Node backend** — Express / Fastify / Hono / NestJS / plain Node | `eslint.config.node.cjs`            |
| **Tailwind CSS** (overlay, auto-detects v3/v4)                    | `eslint.config.tailwind.cjs`        |
| Anything else (Vue, Svelte, Astro, Remix…)                        | universal layer only (still strict) |

All four stack-specific configs inherit the **universal layer**: `eslint-plugin-security`, import-order, suppression bans (`@ts-ignore`, `eslint-disable`, `as any`), risky-import bans (`crypto` → `node:crypto`, `bcrypt` → `argon2`, etc.), Prettier integration. The **Tailwind overlay** spreads on top of any of them and adds class-sorting + canonical-class warnings (v4 only — falls back to long-form lints on v3 / NativeWind 4).

20 templates included total: 5 ESLint flat-configs + 1 Tailwind overlay (auto-detects v3/v4), `tsconfig`, `prettier`, `editorconfig`, `gitignore`, `vscode-settings`, `vscode-extensions`, `commitlint`, `lint-staged`, Husky hooks, plus the `claude-md` project template and the workflow doc templates (`spec`, `roadmap`, `phase-tasks`). The repo also bundles three reference starters (`CLAUDE.md` / `AGENTS.md` / `README.md`) at [`/templates/`](./templates/) for forks and standalone use.

### 📱 [`bymax-mobile`](./plugins/bymax-mobile/) — iOS Simulator + Android Emulator

Two slash commands that take an Expo / React Native project from cold to running on a simulator in one shot.

| Command        | Platform | What it does                                                                                               |
| -------------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `/sim-ios`     | iOS      | Boots **iPhone 17** (or `$BYMAX_SIM_IOS`), runs `expo start` if app already built, else `expo run:ios`.    |
| `/sim-android` | Android  | Boots the first AVD listed (or `$BYMAX_SIM_ANDROID`), runs `expo start` if built, else `expo run:android`. |

Both commands auto-detect the package manager (`pnpm` / `yarn` / `npm`), use a build-artifact heuristic to choose between Metro reattach and full rebuild, and pre-flight tooling so they bail early with a clear, actionable error if Xcode CLI tools or the Android SDK are missing.

### 🌐 [`bymax-web-verify`](./plugins/bymax-web-verify/) — Real-browser verification & assisted UI testing

Confirms a web change works in a live browser, and drives the full stack for assisted UI testing. Preview-first in the Claude Desktop Browser pane, with an [`agent-browser`](https://github.com/vercel-labs/agent-browser) CLI (Vercel Labs) fallback in terminals. Depends on the CLI but never bundles it — the same "require, don't embed" approach as `bymax-mobile`.

| Item                       | Purpose                                                                                                                          |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `/bymax-web-verify:setup`  | One-shot, idempotent install of the `agent-browser` CLI **and** Chrome for Testing, finished by a live smoke test.              |
| `/bymax-web-verify:verify` | Drives a real browser to confirm a change works (navigate, interact, screenshot, read console/page errors). Auto-probes local dev ports. |
| `/bymax-web-verify:test`   | Assisted UI testing with the stack up: reuses or starts the backend, opens the frontend in the Claude Desktop preview, and walks a flow step by step (page state + console + network 2xx + server logs). `agent-browser` fallback in a terminal. |
| `/bymax-web-verify:record` | Records a UI flow as reviewable video evidence via the project's own Playwright — human-paced (`slowMo`), lead-in trimmed and verified, pacing gated with `ffprobe`, published with a plain-text walkthrough of the footage. |
| `check-agent-browser` hook | **SessionStart** — silent when the CLI is present; nudges Claude to offer `/bymax-web-verify:setup` only when it's missing.      |

### 🤖 [`bymax-pr`](./plugins/bymax-pr/) — The PR lifecycle

Ships your work and drives the PR to merge-readiness on **any** project, powered by the [`gh`](https://cli.github.com/) CLI. `/bymax-pr:push` originates the PR; `/bymax-pr:babysit-pr` shepherds it — resolving conflicts, watching CI at a cadence matched to the CI's real duration, fixing real failures (re-running flaky ones), triaging bot review comments, and pinging you when it's green. **Never merges**, never pushes to the base branch, never force-pushes.

| Item                              | Purpose                                                                                                                            |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `/bymax-pr:push`          | Branch (never the default) → stage → complete Conventional-Commits message → push. Pass `pr` to also open a fully-described PR (Summary / Changes / How to verify). |
| `/bymax-pr:babysit-pr`    | Babysits the PR on the current branch (or a number / URL): conflict rebase → CI fix (real vs flaky) → bot-comment triage → notify. |
| Phase −1 preflight                | Verifies the `gh` CLI is installed **and** authenticated; stops with exact install / `gh auth login` instructions if not.          |

Project-agnostic: auto-detects the package manager + lint/test/typecheck/build scripts, and respects the project's own `CLAUDE.md` / `AGENTS.md`. Depends on `gh` + `git`; never bundles them.

### 📋 [`bymax-pm`](./plugins/bymax-pm/) — Engineering Project Manager

Turns one session into the PM/TPM above your other Claude Code sessions. You talk to the PM; it discovers the workers (`ListAgents`), delegates structured task contracts (`SendMessage`), verifies completion against git/CI evidence through quality gates, resolves blockers between agents, and keeps the whole board in a persistent `.claude/pm/` workspace that survives restarts. Built on native cross-session messaging — no daemon, no database.

| Item | Purpose |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `/bymax-pm:pm`            | Operate as PM: decompose, delegate to named peer sessions, verify evidence, unblock, report. Modes: `status`, `standup`, `release-check`. |
| `pm` skill + 8 references | Peer protocol, task contracts, lifecycle + gates, escalation, reporting, persistence, multi-repo coordination, worked example. |

Start workers with names (`claude --name nest-logger`) — the name is the address. Workers need nothing installed; the PM's messages carry their own reply instructions.

### 🔎 [`bymax-qa`](./plugins/bymax-qa/) — Whole-system QA + security audit

The Security QA engineer of your agent team. Point `/bymax-qa:audit` at a **Jira ticket** (it verifies access, reads the acceptance criteria, and reports each PASS/FAIL/BLOCKED/NOT-VERIFIABLE with evidence), a **branch or PR** (it scopes the hunt to the change, like a code review), or the **whole system**. It maps the stack and its trust boundaries, hunts by domain with read-only finder agents, probes the running stack against allow-listed hosts only, and admits a finding **only after an independent verifier reproduces it**. Fixes are never applied by the auditor — each finding is handed to the agent that owns the code, filed as a GitHub issue, or commented back on the ticket, then re-tested until it holds.

| Item | Purpose |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `/bymax-qa:audit <target>`         | Target is a ticket key, a branch, a range, a PR, or nothing (whole system); a free-text instruction after it steers focus. Modes `init`, `retest QA-NNN`, `status`. Flags `--domains`, `--depth`, `--live`, `--no-handoff`, `--no-issues`. |
| `audit` skill + 18 references | Target resolution + Jira access, acceptance criteria, the security domains (auth, authz/tenant, injection, cache, database, transport), observability, architecture, frontend, supply chain, plus verification, the finding contract, hand-off and report templates. |
| 3 sub-agents | `qa-recon` (map), `qa-hunter` (per-domain finder → candidates), `qa-verifier` (adversarial, opus). |
| `qa-guard` hook | While an audit runs, confines network probes to allow-listed hosts and writes to `.claude/qa/`. |

Findings carry ASVS 5.0, CWE and API Top 10 references and a CVSS vector, and live in a `.claude/qa/` workspace that survives restarts. External scanners (`semgrep`, `gitleaks`, `osv-scanner`, `trivy`, `zap`, `axe`, Lighthouse) are used when present and never bundled.

### 🎁 [`bymax-all`](./plugins/bymax-all/) — Reference index

A docs-only marketplace entry that lists the full set. Claude Code's plugin manifest does **not** auto-install dependencies, so installing `bymax-all` does nothing on its own — install the eight sibling plugins individually for the complete toolkit.

---

## 🔥 The Workflow

This is the heart of the toolkit. **Big features** flow through three planning layers + one executor:

```
/spec         →  docs/specs/<feature>.md         (the WHAT and WHY)
   ⏸ approval
/roadmap      →  docs/plans/<feature>-plan.md    (phased master plan + dashboard + DAG)
   ⏸ approval
/phase-tasks  →  docs/tasks/phase-NN-*.md        (per-phase task files with agent prompts)
   ⏸ approval per phase
/task         →  /verify → /security-review → /code-review → completion protocol
   ⏸ user reviews diff
commit (Conventional Commits — never auto-committed)
```

Each layer **stops and waits** for explicit user approval. You review, modify, or approve. Nothing auto-chains — until you explicitly opt into the [autopilot](#-loop-engineering-the-autopilot), which flips the contract for the *execution* half only: planning always stays human-approved.

### Status legend (used in every roadmap and task file)

| Emoji | Meaning     |
| ----- | ----------- |
| 📋    | ToDo        |
| 🔄    | In Progress |
| 👀    | Review      |
| ✅    | Done        |
| ⛔    | Blocked     |
| 🟡    | Partial     |

### Small tasks / bug fixes

Skip the heavy chain — use `/plan` (single PR), then `/tdd` (new code) or the `tester` skill (existing code), then `/verify` and `/code-review`.

---

## 🔁 Loop Engineering: the Autopilot

> *"You shouldn't be prompting coding agents anymore. You should be designing loops that prompt your agents."* — Peter Steinberger
>
> *"I don't prompt Claude anymore. I have loops running that prompt Claude and figuring out what to do."* — Boris Cherny (Anthropic, creator of Claude Code)

**Loop engineering** — the term Addy Osmani coined in his June 2026 essay ([addyosmani.com](https://addyosmani.com/blog/loop-engineering/), also on [O'Reilly Radar](https://www.oreilly.com/radar/loop-engineering/)) — is the discipline that emerged when the bottleneck of AI-assisted development shifted from *model capability* to *orchestration design*: instead of prompting an agent turn by turn, you design the **system** that prompts, verifies, retries, and stops it. `/bymax-workflow:autopilot` is this toolkit's loop-engineering layer, and it exists because the rest of the toolkit makes it possible: the loop is only as trustworthy as the harness it runs in.

### From approved plan to merged main, hands-off

```
/bymax-workflow:autopilot init   →  docs/AUTOPILOT.md      (per-project config — the LAST thing you review)
   ⏸ your approval (the only one)
/bymax-workflow:autopilot        →  for each phase of the roadmap, sequentially:
      ORCHESTRATOR (main session, long-lived, small context)
        ├─ spawns ONE implementer sub-agent in an isolated git worktree
        │    └─ IMPLEMENTER: executes the phase's task files → runs every gate
        │       → gates run; /security-review candidates verified, never iterated to zero
        │       → returns committed candidate and evidence; orchestrator certifies, pushes and opens PR
        ├─ watches CI + review bot via background signals (never a dead gap)
        ├─ fixes every finding (escalating the model when a phase stalls)
        ├─ merges ONLY on the full gate conjunction + grace window
        ├─ deletes the merged branch (remote + local, with proof)
        └─ updates the dashboards → chains the next phase
   🔁 until every phase is ✅ — or a precondition blocks, and it stops cleanly and tells you
```

### Why it has authority: every rule names the failure it prevents

The autopilot's [operational playbook](./plugins/bymax-workflow/skills/autopilot/references/operational-playbook.md) is not aspirational — it is the distillation of real multi-phase autonomous builds (10-phase / 50+-task library and application roadmaps), and each rule records the incident behind it:

| Rule | The failure it prevents |
|---|---|
| Orchestrator/implementer **role split** — implementers never wait, never merge | The naive "one agent does everything" design **deadlocked** waiting for the review bot: a background sub-agent dies the moment it enters a long wait |
| **One implementer, one test suite at a time**, bounded workers | Fanned-out test agents multiplied memory by `workers × runners × agents` and crashed a 36 GB machine past 70 GB into swap |
| Merge only after a **conjunction + grace window** — never the instant CI is green | A second bot review can land ~90 s after a push; early merges turn it into a stray follow-up PR |
| **Re-fetch review-thread IDs fresh** every time | Thread IDs change when the bot re-reviews; stale IDs return `NOT_FOUND` and masquerade as permission errors |
| **Verify via `git`/`gh`, never narration** | Agents confabulate SHAs, fixes, and "I merged it" |
| **Never end a turn with a dead gap** (background job or wakeup, always) | One turn with neither and the "autonomous" chain silently stalls, waiting for a human |

### The whole toolkit, composed

Autopilot is where the other plugins compound — Osmani's five loop components map one-to-one onto what's already installed:

| Loop component (Osmani) | In this toolkit |
|---|---|
| **State & memory** | The roadmap's Progress Dashboard + task files (from `/spec` → `/roadmap` → `/phase-tasks`) are the loop's externalized state — the same docs you approved are what the loop reads and updates |
| **Sub-agents** | One implementer per phase + the `bymax-quality` reviewers; an implementer never grades its own work — Claude/Codex review and security verification must resolve confirmed blockers before any PR opens |
| **Worktrees** | Every implementer runs in an isolated `git worktree` — no file collisions, clean rollback |
| **Skills** | `/standards` (the §0 simplicity ladder), `/tdd`, `tester` — the project knowledge implementers load instead of re-deriving conventions |
| **Automations** | Background CI/review watchers + scheduled wake-up fallbacks — the mechanics proven in `/bymax-pr:babysit-pr`, promoted from one PR to the whole roadmap |

And Osmani's warning — *"unattended loops make unattended mistakes; verification remains your responsibility"* — is exactly why autopilot **only** runs on planning docs you approved, keeps a reviewable trail (one PR per phase, dashboards, completion logs), and refuses shortcuts (no suppression comments, no force-green, no weakened thresholds — the same bans `/code-review` enforces on humans).

### Honest constraints

- **It merges.** Unlike `/bymax-pr:babysit-pr` (which never merges), autopilot's whole point is unattended merging — gated by the conjunction above. Launch it only on repos where a phase-per-PR squash-merge by the loop is what you want.
- **It is token-intensive by design.** An implementer per phase, bounded review campaigns, fix cycles. The per-phase **model policy** in `docs/AUTOPILOT.md` exists to spend the strong tier only where first-pass judgment matters (first-contact APIs, security-sensitive phases, final hardening) and a cheaper tier where the merge gate catches everything anyway.
- **It needs the planning chain.** No roadmap + task files, no autopilot — it executes plans, it never invents them.

---

## 🧱 Architecture

```
bymax-claude-code/
├── .claude-plugin/
│   └── marketplace.json                ← marketplace metadata
│
├── plugins/                            ← installable via /plugin install
│   ├── bymax-workflow/                 ← planning + execution
│   ├── bymax-quality/                  ← review + TDD + agents + hooks
│   ├── bymax-bootstrap/                ← project scaffolding
│   ├── bymax-mobile/                   ← iOS Simulator + Android Emulator
│   ├── bymax-web-verify/               ← real-browser verification (needs agent-browser)
│   ├── bymax-pr/                       ← autonomous PR babysitting (needs gh CLI)
│   ├── bymax-pm/                       ← engineering PM for multi-agent development
│   ├── bymax-qa/                       ← whole-system QA + security audit
│   └── bymax-all/                      ← reference index (no auto-install in Claude Code)
│
├── templates/                          ← project bootstrapping templates
│   ├── CLAUDE.md                       ← starter CLAUDE.md (load-on-demand pattern)
│   ├── AGENTS.starter.md               ← starter AGENTS.md (full spec for agents; named so Codex does not read it as this repo's guidance)
│   └── README.md                       ← beautiful README starter (badges + sections + emojis)
│
├── vendor/                             ← third-party MIT-licensed extras (backup, not in marketplace)
│   ├── ecc-skills/                     ← Everything Claude Code domain skills
│   └── ui-ux-pro-max/                  ← UI/UX design intelligence skill
│
├── personal/                           ← author's personal config (backup, not in marketplace)
│   ├── settings.template.json          ← sanitized ~/.claude/settings.json
│   ├── mcp.template.json               ← sanitized ~/.mcp.json (context7 + sequential-thinking)
│   └── prettier-format.sh              ← personal autoformat hook
│
├── scripts/
│   ├── install.sh                      ← restore everything to ~/.claude/ (for new Mac)
│   └── validate.sh                     ← validate marketplace.json + plugin.json
│
└── docs/
    └── PROPOSAL.md                     ← original design proposal
```

### Two ways to use this repo

**A. Public marketplace** (recommended for everyone)

```bash
claude plugin marketplace add bymaxone/bymax-claude-code
claude plugin install bymax-workflow@bymax-claude-code
claude plugin install bymax-quality@bymax-claude-code
claude plugin install bymax-bootstrap@bymax-claude-code
claude plugin install bymax-mobile@bymax-claude-code
claude plugin install bymax-web-verify@bymax-claude-code
claude plugin install bymax-pr@bymax-claude-code
claude plugin install bymax-pm@bymax-claude-code
claude plugin install bymax-qa@bymax-claude-code
```

Only the `plugins/` content is exposed via `/plugin install`. The vendor/ and personal/ folders are visible in the repo for backup but not installable.

**B. Personal restore** (full Mac wipe — author workflow)

After installing Claude Code itself (`npm install -g @anthropic-ai/claude-code` or the [native installer](https://docs.claude.com/en/docs/claude-code/setup)):

```bash
# 1. Clone the repo
git clone https://github.com/bymaxone/bymax-claude-code ~/dotfiles-claude
cd ~/dotfiles-claude

# 2. Preview what install.sh will do (no writes)
./scripts/install.sh --dry-run

# 3. Restore vendor + design skills + personal + MCP config into ~/.claude/.
#    (Plugins are NOT symlinked here — they are installed below via the
#    marketplace. Design skills are fetched from their upstream repos.)
./scripts/install.sh --write-mcp-enabled

# 4. Configure your settings (template has comments inline)
cp personal/settings.template.json ~/.claude/settings.json
$EDITOR ~/.claude/settings.json

# 5. Install marketplace plugins
claude plugin marketplace add bymaxone/bymax-claude-code
claude plugin install bymax-workflow@bymax-claude-code
claude plugin install bymax-quality@bymax-claude-code
claude plugin install bymax-bootstrap@bymax-claude-code
claude plugin install bymax-mobile@bymax-claude-code
claude plugin install bymax-web-verify@bymax-claude-code
claude plugin install bymax-pr@bymax-claude-code
claude plugin install bymax-pm@bymax-claude-code
claude plugin install bymax-qa@bymax-claude-code
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install frontend-design@claude-plugins-official
claude plugin marketplace add getsentry/sentry-mcp
claude plugin install sentry-mcp@sentry-mcp

# 6. GitHub access — authenticate the gh CLI (short-lived OAuth, no PAT).
#    This is what bymax-pr and every GitHub operation in the toolkit use;
#    no github MCP server is needed.
brew install gh && gh auth login

# 7. Restart Claude Code; type "/" — you should see all bymax-* commands.
```

#### What `install.sh` restores

| Layer            | What                                                                                          | Mode             |
| ---------------- | --------------------------------------------------------------------------------------------- | ---------------- |
| **vendor**       | `ecc-skills/*.md` + the full `ui-ux-pro-max/` directory                                       | symlinks         |
| **design skills**| Emil Kowalski, Impeccable, Taste subset — fetched from upstream via `npx skills add --global` | fetched (upstream) |
| **personal**     | `prettier-format.sh` (hook)                                                                   | symlinks         |
| **MCP**          | `mcp.template.json` → `~/.mcp.json` (only if not already present)                             | **copy**         |

Skip the design-skill fetch with `./scripts/install.sh --no-design-skills`.

The bymax plugins themselves are installed via `claude plugin install` (Step 5 above), not via `install.sh` — Claude Code's plugin marketplace handles them natively. Settings (`~/.claude/settings.json`) and the marketplace plugin install commands are **manual** — the script prints them at the end so you can copy/paste.

Flags: `--dry-run`, `--no-vendor`, `--no-design-skills`, `--no-personal`, `--no-mcp`, `--write-mcp-enabled`.

---

## 📐 Standards

Every command and template enforces the same universal rules:

- **TypeScript strict** + `noUncheckedIndexedAccess`, zero `any`, zero `// @ts-ignore`, zero `// eslint-disable`.
- **JSDoc** on every non-trivial file header and every export.
- **Every test `it()`** carries a block comment (scenario + rule it protects).
- **English-only** comments.
- **Layered architecture**: `app/` → `features/*` → `shared/*`. No cross-feature imports.
- **Conventional Commits** enforced via Husky + commitlint.
- **Banned suppression comments** caught by `/code-review` and `/verify`.
- **Banned risky imports**: `crypto` (use `node:crypto`), `bcrypt` (use `argon2`), `crypto-js`, `md5`, `uuid`, `nanoid` (use `crypto.randomUUID`).

Full reference: [`/standards`](./plugins/bymax-workflow/skills/standards/SKILL.md) skill (loaded on demand).

---

## 🧱 Tech Stack

The toolkit's review, standards, and TDD skills cover **TypeScript and Rust**. The bootstrap ESLint configs and project templates target the JS/TS stacks below:

<p>
  <img src="https://img.shields.io/badge/Rust-edition%202024-000000?style=flat-square&logo=rust&logoColor=white" alt="Rust" />
  <img src="https://img.shields.io/badge/Clippy-strict-000000?style=flat-square&logo=rust&logoColor=white" alt="Clippy" />
  <img src="https://img.shields.io/badge/rustfmt-checked-000000?style=flat-square&logo=rust&logoColor=white" alt="rustfmt" />
  <img src="https://img.shields.io/badge/cargo--deny-supply%20chain-000000?style=flat-square&logo=rust&logoColor=white" alt="cargo-deny" />
  <img src="https://img.shields.io/badge/cargo--llvm--cov-coverage-000000?style=flat-square&logo=rust&logoColor=white" alt="cargo-llvm-cov" />
</p>

<p>
  <img src="https://img.shields.io/badge/Node.js-24%2B-339933?style=flat-square&logo=node.js&logoColor=white" alt="Node.js" />
  <img src="https://img.shields.io/badge/TypeScript-strict-3178C6?style=flat-square&logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React" />
</p>

<p>
  <img src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/Expo-55-000020?style=flat-square&logo=expo&logoColor=white" alt="Expo" />
  <img src="https://img.shields.io/badge/React_Native-0.85-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React Native" />
  <img src="https://img.shields.io/badge/Vite-7-646CFF?style=flat-square&logo=vite&logoColor=white" alt="Vite" />
</p>

<p>
  <img src="https://img.shields.io/badge/Express-5-000000?style=flat-square&logo=express&logoColor=white" alt="Express" />
  <img src="https://img.shields.io/badge/Fastify-5-000000?style=flat-square&logo=fastify&logoColor=white" alt="Fastify" />
  <img src="https://img.shields.io/badge/Hono-4-E36002?style=flat-square&logo=hono&logoColor=white" alt="Hono" />
  <img src="https://img.shields.io/badge/NestJS-11-E0234E?style=flat-square&logo=nestjs&logoColor=white" alt="NestJS" />
</p>

<p>
  <img src="https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white" alt="Tailwind CSS" />
  <img src="https://img.shields.io/badge/NativeWind-4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white" alt="NativeWind" />
</p>

<p>
  <img src="https://img.shields.io/badge/ESLint-9-4B32C3?style=flat-square&logo=eslint&logoColor=white" alt="ESLint" />
  <img src="https://img.shields.io/badge/Prettier-3-F7B93E?style=flat-square&logo=prettier&logoColor=black" alt="Prettier" />
  <img src="https://img.shields.io/badge/Jest-30-C21325?style=flat-square&logo=jest&logoColor=white" alt="Jest" />
  <img src="https://img.shields.io/badge/Vitest-3-6E9F18?style=flat-square&logo=vitest&logoColor=white" alt="Vitest" />
</p>

<p>
  <img src="https://img.shields.io/badge/Husky-9-FFB94A?style=flat-square&logo=husky&logoColor=black" alt="Husky" />
  <img src="https://img.shields.io/badge/commitlint-19-FE5196?style=flat-square&logo=commitlint&logoColor=white" alt="commitlint" />
  <img src="https://img.shields.io/badge/lint--staged-15-FFB94A?style=flat-square&logoColor=white" alt="lint-staged" />
</p>

---

## 🤝 Contributing

Contributions, bug reports, and ideas are very welcome! Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR.

```bash
# Clone the repo
git clone https://github.com/bymaxone/bymax-claude-code.git
cd bymax-claude-code

# Validate marketplace + plugin manifests
./scripts/validate.sh

# Test locally
claude plugin marketplace add ./
claude plugin install bymax-workflow@bymax-claude-code
claude plugin install bymax-quality@bymax-claude-code
claude plugin install bymax-bootstrap@bymax-claude-code
claude plugin install bymax-mobile@bymax-claude-code
claude plugin install bymax-web-verify@bymax-claude-code
claude plugin install bymax-pr@bymax-claude-code
claude plugin install bymax-pm@bymax-claude-code
claude plugin install bymax-qa@bymax-claude-code
```

---

## 🔒 Security

If you discover a security vulnerability (e.g., a regex bypass in `secret-scanner.sh`), please **do not** open a public issue. Email **support@bymax.one** instead. See [SECURITY.md](./SECURITY.md).

---

## 🙏 Credits

This repo bundles two MIT-licensed third-party skills as backup (not redistributed via the marketplace — see `vendor/README.md` for original sources):

- **[Everything Claude Code](https://github.com/affaan-m/everything-claude-code)** by Affaan Mustafa — domain skills (api-design, backend-patterns, postgres-patterns, etc.)
- **[ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)** by nextlevelbuilder — UI/UX design intelligence

It also **fetches** (never bundles) these third-party design skills from their upstream repos via `scripts/install.sh` (see [`vendor/README.md`](./vendor/README.md)):

- **[Emil Design Engineering](https://github.com/emilkowalski/skill)** by Emil Kowalski — UI polish, component design, animation decisions
- **[Impeccable](https://github.com/pbakaus/impeccable)** by Paul Bakaus — full frontend design language (Apache-2.0)
- **[Taste-Skill](https://github.com/Leonxlnx/taste-skill)** by Leonxlnx — anti-slop design taste (MIT)

Inspired by:

- [Anthropic Claude Code](https://github.com/anthropics/claude-code) and the [official plugin marketplace](https://github.com/anthropics/claude-plugins-official).
- [Superpowers](https://github.com/obra/superpowers) — for the spec → plan → execute discipline mindset.
- [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) — community index.

---

## 📄 License

[MIT](./LICENSE) © [Bymax One](https://github.com/bymaxone)

---

<p align="center">
  <sub>Built with ❤️ by <a href="https://github.com/bymaxone">Bymax One</a> · Used in production every day at <a href="https://bymax.one">bymax.one</a></sub>
</p>

## Bounded Claude and Codex review

`/bymax-quality:code-review` uses one Claude pass and one Codex pass with the same pinned
scope and context. Autonomous shipping uses six candidates across pushes; standalone review uses three. It verifies findings before edits
and records evidence for the exact pushed commit. See the
[protocol](plugins/bymax-quality/references/review-protocol.md) for setup and limitations.
Install the global Claude policy/guard and a local plugin overlay with
`python3 scripts/install-review-flow.py --local-plugin-overlay`; restart Claude afterward.
Existing local files are backed up. Publishing the release is a separate step.
