# 🛡️ Bymax Quality

> Bounded **Claude + Codex** review with a pre-push receipt, plus strict quality gates and specialist reviewers (TypeScript and Rust): red-green-refactor TDD, a multi-stack tester, seven sub-agents (incl. a Rust reviewer), and a credential-blocking pre-write hook.

## Install

```bash
claude plugin marketplace add bymaxone/bymax-agent-kit
claude plugin install bymax-quality@bymax-agent-kit
```

### First run in a repository (once, mandatory)

Run `/bymax-quality:review-md`. It writes `REVIEW.md` and the `## Code Review Rules`
section of `AGENTS.md` — the files Anthropic's Code Review and Codex read on every pull
request. Without them both bots report every wording preference as a blocking finding,
and a one-line fix can reach its seventh review round on style alone. `review_flow.py
start` prints the same reminder until the files exist.

### Claude + Codex review

Push certification requires the Codex CLI with an active login and the Claude review
pass. Run `/bymax-quality:codex-setup` if needed. The optional OpenAI Codex plugin is not
required by this flow; keep its Stop review gate disabled to avoid a second loop.

A campaign pins one candidate and gives **both reviewers the same context, base and HEAD**.
A standalone review permits three candidates — the initial one plus two correction deltas.
`start --autonomous` enrolls the branch in a **six-candidate budget shared across pushes**
and across completed campaigns, so clearance does not renew it; on exhaustion with real
blockers the campaign stops with evidence instead of looping.

Every finding is verified before an edit, and every disposition — accepted or rejected —
carries its evidence. A correction round additionally requires `--probe` (the author's own
attempts to defeat the fix), lists every test file the delta changed so a flipped
expectation is a finding, and runs `lessons`: the blocking findings that landed in files
the previous round's own correction touched. Nits and unrelated pre-existing bugs never
force a round. Missing or failed reviewers leave the review **incomplete** — not approved,
and not evidence of a product defect.

`finish` writes a receipt for the exact source SHA, and the `review_prepush.py` Git hook
verifies it at push time. Read [the protocol](references/review-protocol.md) for the
context schema, evidence format and limitations, and
[autonomous delivery](references/autonomous-delivery.md) for the budget, reviewer
ownership and the blocked-push handoff.

The runtime, the pre-push hook and the managed policy block are installed from a checkout,
not from the marketplace:

```bash
python3 scripts/install-review-flow.py                          # ordinary install
python3 scripts/install-review-flow.py --local-plugin-overlay   # plugin development only
```

Run this from the marketplace root, then restart Claude. The installer preserves unrelated
settings and hooks, reports its rollback directory under `~/.claude/backups/`, and refuses
rather than deleting a legacy hook chained to another command. `--local-plugin-overlay`
also copies this checkout over the installed quality/workflow/PR caches — official plugin
updates replace that overlay, so publish these plugin versions before relying on remote
updates. The overlay resolves a cache installed under either the current `bymax-agent-kit`
marketplace id or the former `bymax-claude-code` one.

### Also in Codex

The same procedures ship in the Codex package as `bymax-code-review`, `bymax-codex-setup`, `bymax-review-md`, `bymax-tdd`, `bymax-tester` (namespaced `bymax-codex:<name>`). Install it with `./scripts/install-codex.sh` from a checkout — see [CODEX.md](../../CODEX.md) for the entrypoints and the capability boundaries, which are not full parity.

## What you get

### Slash commands

| Command         | Purpose                                                                                                                                                  |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/bymax-quality:code-review` | Bounded Claude + Codex review with shared context, pinned scope, evidence-based triage and regression verification. Modes quick/full/deep; --preview is advisory, --fix permits minimal verified repairs. |
| `/bymax-quality:codex-setup`  | Gets the Codex CLI ready so `code-review` can run its independent second review: diagnoses what is missing (binary, session, or nothing), installs through the right channel (`brew install --cask codex` on macOS, `npm install -g @openai/codex` elsewhere), walks the user through the interactive `codex login`, and verifies with a real review run rather than an exit code. Codex is required for dual-review certification. |
| `/bymax-quality:review-md`    | Generates a repo-root `REVIEW.md` — the distilled Bymax rules injected verbatim into Anthropic's built-in Code Review (cloud `@claude review` on PRs, `/code-review ultra`), so the cloud engine enforces the same invariants the local gate blocks on. |
| `/bymax-quality:tdd`          | Strict red-green-refactor cycle (Jest/Vitest or Rust `#[test]`/`cargo test`). Forces failing test before implementation. 80%+ coverage minimum (100% on critical paths). Every `it()` / `#[test]` carries a block comment. |

### The review runtime

`scripts/` holds the campaign state machine. `scripts/install-review-flow.py` at the
repository root deploys the first six rows to `~/.claude/bymax-review/`; the last stays
in the plugin and is invoked from there:

| File | Role |
| --- | --- |
| `review_flow.py` | The campaign: `start` · `prompt` · `codex` · `claude` · `record` · `triage` · `lessons` · `range` · `check` · `finish` · `status`. State lives in the Git common directory, survives sessions, and never enters the diff. |
| `review_prepush.py` | The Git `pre-push` hook. Validates the receipt for every source SHA being pushed. Every `start` installs it when absent; it is never written over a foreign hook, nor into a custom `core.hooksPath`, which must delegate to it instead. |
| `review_push.py` | The `PreToolUse` Bash guard that turns a blocked push into a handoff instead of a dead end. |
| `review_delivery.py` | The delivery ledger: the six-candidate budget shared across pushes and completed campaigns. |
| `review_claude.py` | A constrained Claude CLI adapter, so a Codex-led session can obtain the independent Claude pass. |
| `review-report.schema.json` | The report contract both reviewers return. A report with `status: incomplete` is rejected even when its findings list is empty. |
| `codex-review.sh` (not deployed) | A standalone second opinion outside a campaign (`codex exec review`, or the `openai-codex` plugin's adversarial mode). Bounded campaigns use `review_flow.py`, not this. |

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
/bymax-workflow:verify        (5 gates: static checks, exercise, root-cause, regression scan,
   ↓                           acceptance criteria)
/security-review              (Claude Code built-in; candidates, verified before any edit)
   ↓
commit the candidate          (a campaign reviews a committed, clean tree — nothing else)
   ↓
/bymax-quality:code-review    (Claude pass + Codex pass on one pinned scope → triage with
   ↓                           evidence → minimal correction batch → check → receipt)
push                          (the pre-push hook reads the receipt for this exact SHA)
```

A confirmed blocking finding sends the flow back to `/bymax-workflow:verify`, and the next
campaign reviews **only the correction delta and the behaviour it touched** — not the whole
change again. A finding is not a fix order: verify it against the code, the dependency
contract and a reproduction first, record justified rejections with their counterevidence,
and defer nits and unrelated pre-existing issues with a reason. Never rewrite unrelated code
to obtain an empty review.

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
