---
name: bymax-security-audit
description: "Security guidance and vulnerability review for codebases, APIs, services, CLI tools, libraries, and daemons. Use for security questions, focused reviews, vulnerability research, security audits, or pen tests. Run the complete workflow only for explicit codebase audit or pen-test requests, full/comprehensive/end-to-end reviews, or requested report artifacts."
---

# Bymax Security Audit

Read [the Codex runtime contract](../../references/runtime.md) first.

This is Cloudflare's `security-audit` skill, bundled unchanged. Read [the security audit adapter](../../references/security-audit-runtime.md) before the source: it resolves the source's platform terms to Codex, and states what to report when a required capability is missing. Preserve every source rule on operating modes, execution safety, write isolation, validation and verdicts.

Then read [the complete source procedure](../../references/upstream/bymax-qa/skills/security-audit/SKILL.md) and only the phase and attack-class references it routes to. Apply the adapter's Codex mappings before executing any step.
