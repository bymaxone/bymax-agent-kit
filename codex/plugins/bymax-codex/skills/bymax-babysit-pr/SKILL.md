---
name: bymax-babysit-pr
description: "Inspect and shepherd a PR toward merge readiness, repair authorized failures and monitor with available scheduling; never merge."
---

# Bymax Babysit Pr

Read [the Codex runtime contract](../../references/runtime.md) first.

Read the runtime persistence contract before starting. Use .bymax/codex/babysit-pr/ for state. Preserve the source's fresh, this-turn GraphQL review-thread ID reads: never reuse an ID from memory when resolving a thread. Re-read headRefOid, checks and review state before announcing readiness. Never merge. With no scheduler, complete one cycle and explicitly report that monitoring has not been armed. Do not rebase or rewrite a branch shared with another active task without resolving ownership first.

Then read [the complete source procedure](../../references/upstream/bymax-pr/skills/babysit-pr/SKILL.md) and its routed references. Apply the Codex mappings above before executing any step.
