# Contributing to Bymax Agent Kit

Thanks for considering a contribution! This toolkit is built and used in production every day, so changes go through a deliberate review.

**One source, two packages.** `plugins/` is canonical for Claude Code *and* for Codex: the Codex
package under `codex/` ships byte-for-byte copies of it, and CI fails when the two drift. A change
to a shared procedure means editing `plugins/`, rebundling, and bumping both manifests — never
editing the copy under `codex/plugins/bymax-codex/references/upstream/`.

---

## 🐛 Reporting bugs

Open an issue with:

- **Version** — the runtime (`claude --version` or `codex --version`), and the package version: `.claude-plugin/marketplace.json` for Claude, `codex/plugins/bymax-codex/.codex-plugin/plugin.json` for Codex.
- **Reproduction** — exact slash command + minimal repo state that triggers the bug.
- **Expected vs actual** — one sentence each.
- **Logs** — relevant snippet (redact any token/credential).

For **security vulnerabilities** (e.g., a regex bypass in `secret-scanner.sh`), do **not** open a public issue. Email `support@bymax.one`.

---

## 💡 Proposing a new command, skill, or agent

Open an issue first with the `proposal` label. Cover:

1. **Goal** — what user need it solves.
2. **Trigger** — when should it be invoked (auto via description, or explicit `/name`).
3. **Sketch** — rough description of what the command/skill body would do.
4. **Why it belongs here** — vs being its own plugin.

We'll discuss before any code is written. This avoids duplicate work and keeps the toolkit focused.

---

## 🛠️ Local development

```bash
# Clone
git clone https://github.com/bymaxone/bymax-agent-kit.git
cd bymax-agent-kit

# The validators need PyYAML; shellcheck is optional locally and mandatory in CI
python3 -m pip install pyyaml       # --break-system-packages on a PEP 668 python, as CI does

# Gate 1 — the Claude package: manifests, +x bits, shellcheck, frontmatter, required
# files, AND the behavioral suite under scripts/tests (review flow, pre-push receipts,
# delivery budget, installer, command-file shell). Takes a few minutes.
./scripts/validate.sh
# (the manifest step delegates to `claude plugin validate`, so it stays in sync with upstream)

# Gate 2 — the Codex package: source drift, all 27 entrypoints, portable links, manifest
# contracts, AND the suite under codex/tests (review scope, bundle parity, installation)
./scripts/validate-codex.sh
# With the Codex CLI installed, require the isolated install + skill-discovery test too:
BYMAX_REQUIRE_CODEX_TEST=1 ./scripts/validate-codex.sh

# Rebundle whenever a canonical file under plugins/ changed — Gate 2 fails on a stale bundle
python3 codex/scripts/bundle.py

# Test locally — install the marketplace from the local path
claude plugin marketplace add ./
claude plugin install bymax-workflow@bymax-agent-kit
claude plugin install bymax-quality@bymax-agent-kit
claude plugin install bymax-bootstrap@bymax-agent-kit
claude plugin install bymax-mobile@bymax-agent-kit
claude plugin install bymax-web-verify@bymax-agent-kit
claude plugin install bymax-pr@bymax-agent-kit
claude plugin install bymax-pm@bymax-agent-kit
claude plugin install bymax-qa@bymax-agent-kit

# Restart Claude Code, then verify your changes

# For the Codex side, install from this checkout and start a new Codex task
./scripts/install-codex.sh && ./scripts/install-codex.sh --check
```

What each gate proves — and the failure modes that are **not** covered — is in
[TESTING.md](./TESTING.md). Instruction text needs behavioral evaluation, not only a green
validator: a valid Markdown/YAML document can still assign contradictory roles.

---

## ✅ Pull-request checklist

Before opening a PR, verify:

- [ ] Each new `commands/*.md` has a YAML frontmatter `description` field with **clear English** triggers (PT/EN both welcome).
- [ ] Each new `agents/*.md` has `name`, `description`, `tools`, `model` (≥ `sonnet` — no `haiku`). The frontmatter gate enforces all four and rejects `model: haiku`.
- [ ] Each new `skills/*/SKILL.md` follows the official Claude Code skill format, and its `name` matches its directory.
- [ ] **Frontmatter is valid YAML in all three.** `./scripts/validate.sh` checks every `commands/*.md`, `skills/*/SKILL.md` and `agents/*.md`, and it needs PyYAML (`python3 -m pip install pyyaml`; on a PEP 668 system Python add `--break-system-packages`, as CI does, or use a venv). Two rules cover almost every failure:
  - A value containing `: ` must be quoted — `description: Modes: quick | full` parses as a nested mapping, not a string. Single-quote it and double any apostrophe: `'Claude''s review'`.
  - `argument-hint` must be a **quoted** string. Bare `argument-hint: [file-path]` is a one-element YAML list, not the hint text — that exact bug shipped once.
- [ ] Each new `hooks/*.sh` is `chmod +x` and has an `exit 0` happy path. Plugin-level hooks are wired via `<plugin>/hooks/hooks.json`.
- [ ] Every test `it()` in any included test has a block comment (scenario + rule it protects).
- [ ] No new `// @ts-ignore`, `// eslint-disable*`, `as any`, or other suppression comments.
- [ ] `marketplace.json` and every touched `plugin.json` (under `<plugin>/.claude-plugin/plugin.json`) validate via `./scripts/validate.sh` — which also runs the frontmatter check above.
- [ ] If you touched anything under `plugins/*/{commands,skills,agents,templates,scripts,hooks,references}/`, you ran `python3 codex/scripts/bundle.py` and `./scripts/validate-codex.sh` is green. A stale bundle fails CI.
- [ ] A change to Codex content bumps `codex/plugins/bymax-codex/.codex-plugin/plugin.json` — without it an installed cache never refreshes.
- [ ] Executable changes (`scripts/**`, `plugins/*/scripts/**`, `plugins/*/hooks/**`, `codex/**/*.py`) ship with a regression test that fails before the change. Reproduced production defects stay as permanent tests; expectations are never weakened to go green.
- [ ] If you bumped a plugin version, you also bumped the marketplace version (semver appropriately — see [Versioning](#-versioning)).
- [ ] You updated [`CHANGELOG.md`](./CHANGELOG.md) with a one-liner under the appropriate section.
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g., `feat(workflow): add /release command`).

---

## 🔖 Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** — breaking changes to existing slash command behavior, removed commands, changed plugin layouts.
- **MINOR** — new commands, new skills, new agents, new templates (additive).
- **PATCH** — bug fixes, docs, internal refactors that don't change behavior.

Marketplace and individual plugins version independently. Bump **both** when a plugin changes.

---

## 🎯 What we want

- New slash commands or skills that **generalize** patterns from real projects — landing in `plugins/`, with the Codex entrypoint bundled in the same PR.
- Better stack templates (Vue, Svelte, SolidStart, Astro, Remix, etc.).
- Hardening for `secret-scanner.sh` (more patterns, lower false positives).
- Improvements to the `tester` skill for new test runners.
- Better agent prompts.
- Polished READMEs and docs.

---

## 🚫 What we don't want

- Project-specific commands (e.g., `/sim` for one app) — keep those in your own `.claude/`.
- Vendor lock-in to a paid service.
- Anything that ships secrets, API keys, or PII.
- Anything that bypasses quality gates (`--no-verify`, `// @ts-ignore`, etc.).
- Skills that duplicate `bymax-quality` or `bymax-workflow` without a clear differentiator.

---

## 📜 Code of conduct

Be kind, be precise, assume good intent. See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

---

Questions? Open an [Issue](https://github.com/bymaxone/bymax-agent-kit/issues).
