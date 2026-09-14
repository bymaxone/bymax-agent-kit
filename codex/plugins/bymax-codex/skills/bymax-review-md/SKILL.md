---
name: bymax-review-md
description: "Generate REVIEW.md for Anthropic cloud Code Review from project rules; this does not configure Codex review policy."
---

# Bymax Review Md

Read [the Codex runtime contract](../../references/runtime.md) first.

This generates REVIEW.md for Anthropic cloud Code Review in a target repository; it does not configure Codex review rules. Preserve that distinction in the output. If the user wants Codex policy instead, use the target AGENTS.md and explain the difference rather than creating an irrelevant REVIEW.md.

Then read [the complete source procedure](../../references/upstream/bymax-quality/commands/review-md.md) and its routed references. Apply the Codex mappings above before executing any step.
