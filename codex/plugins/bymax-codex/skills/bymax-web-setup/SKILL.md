---
name: bymax-web-setup
description: "Install and smoke-test agent-browser and its browser engine when CLI web verification is requested."
---

# Bymax Setup

Read [the Codex runtime contract](../../references/runtime.md) first.

This sets up agent-browser for web verification, not Codex itself. Follow the source's dependency checks using the current host. Do not register the Claude SessionStart hook or change Claude settings. Verify the browser CLI with an actual local smoke page before reporting it usable.

Then read [the complete source procedure](../../references/upstream/bymax-web-verify/commands/setup.md) and its routed references. Apply the Codex mappings above before executing any step.
