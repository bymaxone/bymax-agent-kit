---
name: bymax-portfolio
description: "Decide which product is in focus under a WIP limit, nudge when work is out of focus, record each session's work, and write a weekly review that counts only verified releases as shipped."
---

# Bymax Portfolio

Read [the Codex runtime contract](../../references/runtime.md) first.

The portfolio decides and reports; it never edits a worker repository and never messages a worker, so no coordination API is involved. It keeps the same workspace as the Claude package, `.claude/portfolio/` in the coordination directory and the pointer `~/.claude/bymax-portfolio.json`, so a review written from either host reads the same record. Where the source says `${CLAUDE_PLUGIN_ROOT}/../../bymax-report/*/scripts/collect.py`, use the bundled `bymax-report` plugin's `scripts/collect.py` from this package's references; it reads `~/.claude/projects` and `~/.codex/sessions` on the host, and a host without them reports the asks as unavailable under Coverage. An unattended review asks nothing and changes no focus.

Then read [the complete source procedure](../../references/upstream/bymax-pm/skills/portfolio/SKILL.md) and its routed references. Apply the Codex mappings above before executing any step.
