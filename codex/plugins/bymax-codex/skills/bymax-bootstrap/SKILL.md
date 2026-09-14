---
name: bymax-bootstrap
description: "Set up Bymax project tooling and standards from bundled templates, preserving existing Claude configuration."
---

# Bymax Bootstrap

Read [the Codex runtime contract](../../references/runtime.md) first.

Resolve all templates from the bundled bymax-bootstrap/templates directory. Use AGENTS.md as the Codex project entrypoint: merge needed project-specific guidance without replacing existing guidance. Do not overwrite an existing CLAUDE.md or Claude configuration. The bundled claude-md template may supply content, but Claude-specific tool and plugin installation instructions do not configure Codex.

Then read [the complete source procedure](../../references/upstream/bymax-bootstrap/commands/bootstrap.md) and its routed references. Apply the Codex mappings above before executing any step.
