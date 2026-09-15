---
name: bymax-autopilot
description: "Execute an approved phased roadmap with verified PR gates and supported Codex continuation; also initialize or inspect its state."
---

# Bymax Autopilot

Read [the Codex runtime contract](../../references/runtime.md) first.

Before run, read the runtime persistence contract and the complete source operational playbook. Require an approved roadmap, task files, gh authentication, implementer capability and a verified continuation mechanism. Map the implementer prompt's Claude commands to this package, and use bymax-code-review without recursively launching CLI reviews. Honor the configured merge gate and grace window; read the current PR head and CI immediately before each authorized merge. If continuation cannot be provided, init/status remain usable; report run as unavailable before opening a phase.

Then read [the complete source procedure](../../references/upstream/bymax-workflow/skills/autopilot/SKILL.md) and its routed references. Apply the Codex mappings above before executing any step.
