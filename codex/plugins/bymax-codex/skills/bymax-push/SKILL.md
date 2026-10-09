---
name: bymax-push
description: "Commit and push requested work on a feature branch, respect the staged set, and optionally open a PR when requested."
---

# Bymax Push

Read [the Codex runtime contract](../../references/runtime.md) first.

Use the source's branch/stage/commit/push sequence only for a shipping request. Default new branch names to codex/<slug> unless the user specifies one. Do not claim a review ran just because this skill was invoked: for dual-review shipping read [autonomous delivery](../../references/upstream/bymax-quality/references/autonomous-delivery.md).
Use the installed review helper with `start --autonomous`; obtain a fresh independent
Codex report and run its `claude` action for the independent read-only Claude report.
Both CLI prerequisites must be installed/authenticated. If the helper detects exhausted
Claude account quota, run `codex --as codex-b` for a second independent ephemeral Codex
review alongside the ordinary `codex` review; disclose the substitution. Never relabel
your implementation review as Claude, waive login errors or fabricate a receipt.
If the Codex CLI rejects the configured model, do not retry the same unsupported
configuration or waive that failure; preserve its log and report the blocker.
Keep Claude confined to the helper's read-only `claude` action; Codex owns corrections,
checks, commits, push and PR creation.

Continue through triage, minimal
corrections, gates, receipt and the authorized push. Standalone bymax-code-review is
not a substitute for the two reports. Respect the existing staged set and do not fabricate hook markers. Verify the remote branch SHA after push; if that read fails, report the push exit status and the unverified remote state separately.

Then read [the complete source procedure](../../references/upstream/bymax-pr/commands/push.md) and its routed references. Apply the Codex mappings above before executing any step.
