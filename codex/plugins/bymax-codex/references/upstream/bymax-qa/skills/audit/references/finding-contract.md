# Finding contract

A finding is a document an owner can act on without asking you anything. It is
the whole output of the audit that matters. Under-specify it and the fix is
wrong or slow; over-specify it with narration and the signal drowns.

One file per finding: `.claude/qa/findings/QA-NNN.md`, from
`templates/finding.template.md`. `NNN` is zero-padded and never reused, even
after a REJECTED candidate frees its number — the number is a permanent
address.

## Required fields

| Field | Content |
| --- | --- |
| **id** | `QA-NNN` |
| **title** | one imperative line, self-contained: "Refresh token reuse does not revoke the token family" |
| **severity** | a CVSS 3.1 vector string **and** the numeric score, plus the band CRITICAL/HIGH/MEDIUM/LOW derived from it |
| **confidence** | 0.8–1.0 (below 0.8 is not filed — see `verification.md`) |
| **references** | the ASVS 5.0 id (`V9.2.1`), the CWE (`CWE-384`), and the API Top 10 id where it applies (`API2:2023`) |
| **component** | the affected file(s) and route(s), each `path:line` or `METHOD /route` |
| **owner** | the peer agent name, or the repo slug for an issue, or `human` — from the scope's owner map |
| **status** | OPEN / HANDED-OFF / FIX-CLAIMED / VALIDATED / REOPENED / REJECTED / NEEDS-WORK |
| **reproduction** | numbered steps another agent can run, including the exact request(s) or code; references the evidence file |
| **evidence** | the path(s) under `evidence/<run>/` — request+response, log line, or query output, secrets redacted |
| **impact** | the verified consequence, in one or two sentences: what an attacker gains |
| **remediation** | the concrete fix, root cause not symptom, with the safe pattern |
| **verification log** | the verifier's verdict, the confidence, and each status transition with its date and the read that justified it |

Omit a row only when it genuinely does not apply (an API id for a non-API
finding). Never omit reproduction, evidence, impact, or component.

**Functional findings** (a failed acceptance criterion on a ticket target,
`references/acceptance.md`) use this same file with two substitutions: the
severity is the acceptance band (Blocker / Major / Minor), not a CVSS vector,
and the references cite the ticket key and the criterion id (`AC-2`) instead of
ASVS/CWE. Label the finding `axis: acceptance` so the registry and report never
read it as a security vulnerability.

## Severity — CVSS, then sanity

Compute a CVSS 3.1 vector; do not eyeball a band. Then sanity-check the band
against consequence and reach:

- **CRITICAL** — auth bypass, cross-tenant data access, RCE, a secret exposed
  to an attacker. Anything touching authentication, authorization boundaries,
  payments, or credential exposure starts here and is argued down, not up.
- **HIGH** — a real exploit with a precondition (a role, a specific input),
  significant data exposure, a missing control on a sensitive path.
- **MEDIUM** — exploitable with meaningful constraints, or defence-in-depth
  that is genuinely absent (RLS missing under a working app-layer check).
- **LOW** — a real but low-consequence weakness; a hardening gap with a
  reachable-but-minor effect.

Severity is independent of confidence. A CRITICAL you are 0.85 sure of is filed
as CRITICAL with confidence 0.85, not downgraded because you are unsure — the
uncertainty lives in the confidence field, and the verifier's job was to push
it past 0.8 or drop it.

## References — why all three

- **ASVS 5.0** gives the requirement the target failed, so the owner sees the
  standard, not just your opinion. It is the audit's taxonomy.
- **CWE** classifies the weakness for tracking and for the issue label; the
  2025 CWE Top 25 is the priority lens.
- **API Top 10 2023** names the API-specific class (BOLA, BFLA, BOPLA) that
  ASVS spreads across V8 — the id an API team recognises fastest.

## The registry row

Every finding also gets one line in `.claude/qa/registry.md`:

```
| QA-012 | HIGH | HANDED-OFF | nest-auth-08 | refresh reuse does not revoke family | V9.2.1 / CWE-384 | msg 2026-09-04T14:20 |
```

The registry is the index; the finding file is the record. The registry is
rewritten as statuses change; the finding file's Verification log is
append-only, so the history survives.
