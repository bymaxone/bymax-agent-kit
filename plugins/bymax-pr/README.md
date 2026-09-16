# 🤖 Bymax PR

> The PR lifecycle, end to end: `/bymax-pr:push` ships your work (branch → stage → commit → push, optionally opening a fully-described PR), and `/bymax-pr:babysit-pr` autonomously shepherds the open PR to merge-readiness — resolving conflicts, watching CI, fixing real failures (re-running flaky ones), triaging bot review comments, and pinging you when it's green. It **never merges** and **never pushes to the base branch**.

This plugin **depends on** the `gh` CLI but never bundles it — the same "require, don't embed" approach as [`bymax-mobile`](../bymax-mobile) (Xcode / Android SDK) and [`bymax-web-verify`](../bymax-web-verify) (`agent-browser`). Unlike those, the dependency here is checked by a **preflight inside the skill** (not a session hook): `gh` is an execution prerequisite, not a session-wide one, so it's verified only when you actually run the command.

## Install

```bash
claude plugin marketplace add bymaxone/bymax-agent-kit
claude plugin install bymax-pr@bymax-agent-kit
```

### Also in Codex

The same procedures ship in the Codex package as `bymax-push`, `bymax-babysit-pr` (namespaced `bymax-codex:<name>`). Install it with `./scripts/install-codex.sh` from a checkout — see [CODEX.md](../../CODEX.md) for the entrypoints and the capability boundaries, which are not full parity.

## Prerequisites

- **[`gh` CLI](https://cli.github.com/)** — installed **and** authenticated. The skill's **Phase −1 preflight** verifies both and stops with exact install / `gh auth login` instructions if either is missing. It never runs blind.
  - macOS: `brew install gh` · Linux: [install guide](https://github.com/cli/cli/blob/trunk/docs/install_linux.md) · Windows: `winget install --id GitHub.cli`
  - Then: `gh auth login` (verify with `gh auth status`).
- **`git`** — for commits, rebasing, and pushing.
- An **open PR** on the current branch (or pass a number / URL).

## Usage

```
/bymax-pr:push                   # branch + stage + commit + push (no PR)
/bymax-pr:push pr                # same, then open a fully-described PR
/bymax-pr:push my-branch [pr]    # explicit branch name

/bymax-pr:babysit-pr             # babysit the PR on the current branch
/bymax-pr:babysit-pr 123         # babysit PR #123
/bymax-pr:babysit-pr <pr-url>    # babysit a PR by URL
```

`/bymax-pr:push` guarantees a commit never lands on the default branch (it creates
or reuses a feature branch), respects a pre-staged index, authors a complete
Conventional-Commits message (title ≤ 72 chars + body bullets), and never
force-pushes or bypasses hooks. The `pr` token is explicit opt-in: without it no PR
is created; with it, the PR gets a full Summary / Changes / How to verify body
generated from the entire branch diff. The natural chain is
`/bymax-pr:push pr` → `/bymax-pr:babysit-pr <PR#>`.

## How it works

On **every** wake-up (`ScheduleWakeup`, paced to the CI's real duration with a 270 s floor), it runs four phases in order:

| Phase | What it does |
| ----- | ------------ |
| **0. Conflict resolution** | Auto-rebases onto the base branch when the PR is `CONFLICTING`; resolves by file pattern (lockfiles / generated output / hand-written source). Pauses only if the rebase can't be resolved. |
| **1. CI monitoring** | Fetches `gh pr checks`, classifies each failure as **real vs flaky**. Flaky → `gh run rerun --failed` (cap 3). Real → reads the log, applies the smallest fix, runs the **local test gate** before committing, then pushes. |
| **2. Bot comment handler** | Triages unhandled **bot** review threads on a 4-tier scale (MUST FIX / SHOULD FIX / SKIP-nitpick / SKIP-rule). Implements or dismisses with reasoning, replies with a `<!-- babysit-reply -->` marker, and resolves the thread via GraphQL. **Human** comments are only surfaced via notification — never auto-acted on. |
| **3. Termination check** | When CI is all-green, the PR is mergeable, all bot threads are resolved, and the loop isn't paused → fires a `PushNotification` ("ready to merge 🎉") and stops scheduling. |

State lives in a single `<!-- babysit-state -->` PR comment (per-check failure counts, processed comment IDs), so the loop is **idempotent across wake-ups and session restarts**.

## Project-agnostic by design

No hardcoded paths or workflow names. On entry it auto-detects:

- **Package manager** by lockfile (`bun` / `pnpm` / `yarn` / `npm`).
- **Lint / test / typecheck / build** commands from `package.json` scripts (uses only what exists).
- Non-JS repos: tries conventional gates (`cargo test`, `go test ./...`, `pytest`, `make test`); if none is detectable it skips the local gate and relies on CI.
- The project's own `CLAUDE.md` / `AGENTS.md` (if present) — respected when fixing code and when dismissing bot comments.

## Hard rules

- **Never merges** the PR and **never pushes to the base/default branch.**
- Never force-greens a check (`--no-verify`, `@ts-ignore`, `any`, `eslint-disable`, skip hooks).
- Never pushes a fix without the local gate passing (when one is detectable).
- Never re-processes an already-handled comment; never auto-acts on human comments (only notifies).
- 3-strike rule: pauses and notifies if the same real failure recurs after 3 fix attempts, or a flaky check fails 3 re-runs.

## License

MIT — see [root LICENSE](../../LICENSE). The `gh` CLI itself is MIT and is installed separately.
