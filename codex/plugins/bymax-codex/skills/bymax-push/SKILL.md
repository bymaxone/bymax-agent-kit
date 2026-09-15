---
name: bymax-push
description: "Commit and push requested work on a feature branch, respect the staged set, and optionally open a PR when requested."
---

# Bymax Push

Read [the Codex runtime contract](../../references/runtime.md) first.

Use the source's branch/stage/commit/push sequence only for a shipping request. Default new branch names to codex/<slug> unless the user specifies one. Do not claim a review ran just because this skill was invoked: when review is required, run bymax-code-review on the exact staged or committed content before committing/pushing. Respect the existing staged set and do not fabricate hook markers. Verify the remote branch SHA after push; if that read fails, report the push exit status and the unverified remote state separately.

Then read [the complete source procedure](../../references/upstream/bymax-pr/commands/push.md) and its routed references. Apply the Codex mappings above before executing any step.
