---
name: bymax-personas
description: "Persona-based usability QA: interview the user (persona count, iPhone Simulator, Android emulator or browser, markets, days), research who would use the app from trusted sources and competitor App Store reviews, write evidence-labelled personas, then use the app as each of them day by day on a pinned clock and record every bug, broken flow, design error, accessibility failure and confusing copy seen, with screenshots, for hand-off and re-test. Never edits the app's source."
---

# Bymax Personas

Read [the Codex runtime contract](../../references/runtime.md) first.

Then read [the complete source procedure](../../references/upstream/bymax-qa/skills/personas/SKILL.md) and only the references it routes to. In Codex, use `.bymax/codex/qa/` wherever the source names `.claude/qa/`, and validate its canonical physical path as [the audit adapter](../../references/audit-runtime.md) requires. The Claude QA guard is not installed, so the source's never-edit-source rule is the only control: keep every write inside that workspace. Ask the interview's questions with the available question tool, or as numbered options in a plain message, and wait for the answer. Resolve `${CLAUDE_PLUGIN_ROOT}/scripts/` to the bundled `references/upstream/bymax-qa/scripts/` by absolute path. Where the source names a Claude-only driver (the Browser pane, `/bymax-mobile:*`), use the Codex skill of the same family or report that step BLOCKED.
