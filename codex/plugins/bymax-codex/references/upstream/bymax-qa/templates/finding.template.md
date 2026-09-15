# QA-NNN — <one-line imperative title>

- **id:** QA-NNN
- **severity:** <band> — `CVSS:3.1/AV:_/AC:_/PR:_/UI:_/S:_/C:_/I:_/A:_` = <score>
- **confidence:** <0.8–1.0>
- **references:** ASVS <V_._._> · CWE-<n> · <APIx:2023 if applicable>
- **component:** <path:line> · <METHOD /route>
- **owner:** <peer agent name | repo slug | human>
- **status:** OPEN
- **run:** <run-id, stamped to full-sha>

## Reproduction

Numbered steps another agent can run with no further context:

1. …
2. …
3. … (BUG: expected X, got Y)

## Evidence

`.claude/qa/evidence/<run>/QA-NNN/` — <what is captured: request+response,
log line, query output>. Secrets redacted to `<redacted:16 chars>`.

## Impact

<the verified consequence in one or two sentences — what an attacker gains>

## Remediation

<the concrete fix, root cause not symptom, with the safe pattern and the ASVS
requirement it satisfies>

## Verification log

Append-only. Every status transition names the read that justifies it.

- <ISO> — CONFIRMED by qa-verifier, confidence <n>. <one line of reasoning>.
- <ISO> — HANDED-OFF to <owner> via <message | issue URL>.
- <ISO> — FIX-CLAIMED: owner cited <SHA | PR>.
- <ISO> — VALIDATED: re-test at <SHA> passed, evidence at <path>.
  (or) — REOPENED: re-test at <SHA> still reproduces, evidence at <path>.
