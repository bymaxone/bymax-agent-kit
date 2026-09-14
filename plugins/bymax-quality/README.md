# 🛡️ Bymax Quality

> Strict quality gates and specialist reviewers for Claude Code (TypeScript and Rust). Code-review with severity blocking, red-green-refactor TDD, multi-stack tester, seven sub-agents (incl. a Rust reviewer), and a credential-blocking pre-write hook.

## Install

```bash
claude plugin marketplace add bymaxone/bymax-claude-code
claude plugin install bymax-quality@bymax-claude-code
```

### Claude + Codex review

Push certification requires the Codex CLI with an active login and the Claude review
pass. Run `/bymax-quality:codex-setup` if needed. The optional OpenAI Codex plugin is not
required by this flow; keep its Stop review gate disabled to avoid a second loop.

The default campaign uses shared context, one full review pair, then at most two
correction-delta pairs. All findings are verified before edits. Nits and unrelated
pre-existing bugs do not force new rounds. Missing reviewers leave the review incomplete.
Read [the protocol](references/review-protocol.md) for receipts, evidence and limitations.

To install the global guard and policy from this checkout, including a backed-up local
overlay of the installed quality/workflow plugins:

```bash
python3 scripts/install-review-flow.py --local-plugin-overlay
```

Run this from the marketplace root. Restart Claude afterward. Local overlays are replaced
by official plugin updates; publish these plugin versions before relying on remote updates.
The installer preserves unrelated settings and reports its rollback directory.

## What you get

### Slash commands

| Command         | Purpose                                                                                                                                                  |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/bymax-quality:code-review` | Bounded Claude + Codex review with shared context, pinned scope, evidence-based triage and regression verification. Modes quick/full/deep; --preview is advisory, --fix permits minimal verified repairs. |
| `/bymax-quality:codex-setup`  | Gets the Codex CLI ready so `code-review` can run its independent second review: diagnoses what is missing (binary, session, or nothing), installs through the right channel (`brew install --cask codex` on macOS, `npm install -g @openai/codex` elsewhere), walks the user through the interactive `codex login`, and verifies with a real review run rather than an exit code. Codex is required for dual-review certification. |
| `/bymax-quality:review-md`    | Generates a repo-root `REVIEW.md` — the distilled Bymax rules injected verbatim into Anthropic's built-in Code Review (cloud `@claude review` on PRs, `/code-review ultra`), so the cloud engine enforces the same invariants the local gate blocks on. |
| `/bymax-quality:tdd`          | Strict red-green-refactor cycle (Jest/Vitest or Rust `#[test]`/`cargo test`). Forces failing test before implementation. 80%+ coverage minimum (100% on critical paths). Every `it()` / `#[test]` carries a block comment. |

### Skill

- **`tester`** — Multi-stack test writer. Detects Jest / Vitest / RN / pure logic / Node backend / Rust `cargo test`. Enforces 100% file coverage, every `it()` has a block comment, no fake classNames, no snapshots of arbitrary objects. Auto-runs and verifies coverage on completion.

### Specialist sub-agents

| Agent                   | Model      | Specialty                                                              |
| ----------------------- | ---------- | ---------------------------------------------------------------------- |
| `architect`             | opus       | System design, scalability, technical decisions.                       |
| `code-reviewer`         | sonnet     | Quality + security + maintainability review (proactive after edits).   |
| `database-reviewer`     | sonnet     | PostgreSQL: query optimization, schema design, security.               |
| `planner`               | opus       | Complex feature and refactor planning.                                 |
| `security-reviewer`     | sonnet     | OWASP Top 10, secrets, SSRF, injection, unsafe crypto.                 |
| `typescript-reviewer`   | sonnet     | Type safety, async correctness, idiomatic patterns. |
| `rust-reviewer`         | sonnet     | Ownership/borrow correctness, typed errors, async/Tokio soundness, `unsafe` discipline, idiomatic crate design.                    |

### Hooks

| Hook                       | Trigger                       | What it does                                                                                                                                                                            |
| -------------------------- | ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `secret-scanner.sh`        | `PreToolUse` Write/Edit/MultiEdit | **Blocks** the write if the new content matches AWS keys, GitHub PATs, OpenAI/Anthropic/Stripe/Slack/Google tokens, JWTs, or PEM private keys. Returns exit code 2 + JSON systemMessage. |
| `console-log-scan.sh`      | `Stop`                        | Warns on stray `console.log/warn/error/debug/info` in modified TS/JS files (early-exit if not in git or no JS files modified).                                                          |

## The chain

Designed to be invoked one after another (or via `/bymax-workflow:task` which orchestrates them):

```
implementation
   ↓
/bymax-workflow:verify          (5 gates: static checks, exercise, root-cause, regression scan, acceptance criteria)
   ↓
/security-review (apply every finding)
   ↓
/bymax-quality:code-review     (apply CRITICAL + HIGH + MEDIUM)
   ↓
ready for commit
```

If any of `/bymax-workflow:verify`, `/security-review`, `/bymax-quality:code-review` finds something and fixes it, the flow loops back to `/bymax-workflow:verify`.

## Banned suppression patterns

`/bymax-quality:code-review` flags any of these as **CRITICAL** (blocks commit):

- `// eslint-disable*`, `// @ts-ignore`, `// @ts-expect-error`, `// @ts-nocheck`
- `as any`, `as unknown as <T>` (used to launder errors)
- `// prettier-ignore` (unless preserving a formatted table)
- `# noqa`, `# type: ignore`, `# pylint: disable=`, `@SuppressWarnings`
- Rust: `#[allow(...)]` / `#![allow(...)]` to dodge a gate, an `unsafe` block in a `#![forbid(unsafe_code)]` crate, `#[ignore]` to hide a failing test
- CLI bypasses: `--no-verify`, `--force` on protected branch, `--skip-checks`

## License

MIT — see [root LICENSE](../../LICENSE).
