---
name: bymax-standup
description: "Write the weekly silent-standup report for one repository from evidence: PROGRESS from what was asked in Claude Code and Codex sessions, UPDATES from merged PRs and commits; plain text to paste, no hashes or PR numbers."
---

# Bymax Standup

Read [the Codex runtime contract](../../references/runtime.md) first.

The collector is `scripts/collect.py` of the bundled `bymax-report` plugin; run it with the package's copy where the source says `${CLAUDE_PLUGIN_ROOT}`. It reads `~/.claude/projects` and `~/.codex/sessions` on the host: a Codex session counts only when it is interactive and its `cwd` is the repository. Read `collect.json` whole before writing; write no line it does not support, print the report in a fenced block with its evidence under it, and delete the temporary directory: nothing stays on disk.

Then read [the complete source procedure](../../references/upstream/bymax-report/skills/standup/SKILL.md). Apply the Codex mappings above before executing any step.
