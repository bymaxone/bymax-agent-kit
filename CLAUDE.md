# CLAUDE.md — bymax-agent-kit

Quick rules for Claude Code in this repository. The full agent guidance, including the
review rules Codex applies, is `AGENTS.md`, imported here so there is one source:

@AGENTS.md

This file adds only what is specific to working here with Claude Code.

---

## Stack

- **Product**: instruction text — commands, skills and agents as Markdown under `plugins/`,
  packaged twice: a Claude Code marketplace at the root, a Codex marketplace under `codex/`.
- **Runtimes**: Python 3.10+ (`plugins/*/scripts/`, `scripts/`, `codex/scripts/`) and
  Bash (`plugins/*/hooks/`, `plugins/*/scripts/*.sh`, `scripts/*.sh`).
- **Tests**: `unittest` suites under `scripts/tests/` and `codex/tests/`; the review runtime
  and its suites also run pytest.
- **Validation deps**: those `.github/workflows/validate.yml` installs; shellcheck and the
  Codex CLI are optional locally and required in CI.

---

## Non-negotiables

- **Edit `plugins/`, never the bundle.** `codex/plugins/bymax-codex/references/upstream/` is
  generated. After changing a canonical file, run `python3 codex/scripts/bundle.py`.
- **A command, skill or agent change ships with a version bump**: that plugin's
  `plugin.json`, the marketplace version in `.claude-plugin/marketplace.json`, and a
  `CHANGELOG.md` line, in the same change.
- **Quote frontmatter values.** An unquoted `description:` containing `: ` or an unquoted
  `argument-hint: [a|b]` parses as something else; `validate.sh` catches it.
- **Never edit between `<!-- shared:begin -->` and `<!-- shared:end -->` in `AGENTS.md`.**
  The `agents-sync` workflow replaces that block wholesale; repository rules go below it.
- **`templates/` holds starters for other projects**, with `{{PLACEHOLDER}}` values. Do not
  apply their rules here and do not rename `AGENTS.starter.md`.
- **English everywhere published**; quoted Portuguese trigger phrases in a `Triggers:` list
  are the one exception. No AI attribution in commits, PRs or code.

---

## Verification before finishing

```bash
./scripts/validate.sh        # Claude package + scripts/tests
./scripts/validate-codex.sh  # bundle drift, entrypoints, links + codex/tests
```

Together they take longer than a ten-minute foreground command allows; run them in the
background. A missing `claude`, `python3` or PyYAML is a red run, not a skipped check.

---

## The review runtime is installed, not imported

Campaigns run `~/.claude/bymax-review/review_flow.py`, a copy of
`plugins/bymax-quality/scripts/`. After changing those scripts, run
`python3 scripts/install-review-flow.py` so the next campaign exercises the new code rather
than the copy installed before it.

---

## Git

- Branch off `main`; never commit to it. Conventional Commits, title ≤ 72 characters.
- Every push needs a cleared `/bymax-quality:code-review` receipt; the `pre-push` hook
  enforces it. Push with an explicit refspec: `git push -u origin HEAD:<branch>`.

---

## When in doubt

`AGENTS.md` wins over this file for anything it states. A rule you think is wrong → raise
it in the pull request, don't work around it.
