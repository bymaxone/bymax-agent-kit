# Verification — candidate to finding

A candidate is a hypothesis. A finding is a candidate that survived six gates
with evidence. This step is what makes the audit worth trusting: a report with
zero false positives is acted on; a report with three is ignored, and the two
real findings in it die with the noise.

Every candidate goes through this, and every finding must satisfy all six gates
below. What differs for a **deterministic** candidate (an exact grep, a
dependency advisory) is only *how* two of them are satisfied, never *whether*:

- **Gate 1 (reproducible)** is satisfied by the match itself — the grep or the
  advisory id is the reproduction; do not re-derive it.
- **Gate 2 (evidence)** is satisfied by the matched line (with its `path:line`)
  or the advisory id recorded under `evidence/<run>/`.
- **Gates 3, 4, 5 and 6 still apply in full**: verified impact, in scope,
  real-not-informational, and independently reproducible (a deterministic match
  is trivially so). An advisory on a dependency with no reachable path here, or
  a pattern match with no exploitable consequence, fails gate 3 or 5 and is
  dropped to a supply-chain or informational observation, never promoted to a
  finding.

A deterministic candidate does **not** need a separate `qa-verifier` pass (the
match is not a judgement), but you must still make the gate-3/gate-5 impact
call yourself and record it. Spawn `qa-verifier` for every **non-deterministic**
candidate; its verdict is recorded verbatim in the finding's Verification log.

## The six gates (all must pass)

1. **Reproducible.** A concrete input/state → a concrete wrong output, written
   as steps another agent can run: a `curl`, a request pair, a query, a unit of
   code. "An attacker could…" without the steps fails this gate.
2. **Evidence captured.** The request + response, the log line, or the query
   result is saved under `.claude/qa/evidence/<run>/` and named by the finding.
   A screenshot of reasoning is not evidence; the artefact is.
3. **Impact verified, not theoretical.** The reproduction shows the actual
   consequence — data of another tenant returned, a token accepted that should
   not be, a payload reaching a sink. A claim that stops at "this is risky"
   fails.
4. **In scope.** The affected host/component is in `scope.md`. A defect on an
   out-of-scope target is recorded for the human, not filed as a finding.
5. **Real, not informational.** It changes what an attacker can do. "This
   header could be added", "this could be logged", a best-practice deviation
   with no reachable consequence — dropped.
6. **Independently reproducible.** The report lets the owner reproduce it
   without asking you a follow-up. If it needs your session's state to
   reproduce, the report is incomplete — fix the report (NEEDS-WORK), do not
   file it.

One gate failing → NEEDS-WORK (the finding is real but the report is not
usable yet) or REJECTED (not a finding). A rejected candidate stays in
`candidates/<run>/` with the reason, and is counted for the report. It is
never silently dropped — the dropped count is itself a signal.

## Confidence, separate from severity

Severity is how bad it is if real (the CVSS vector). Confidence is how sure you
are it is real (0–1). They are independent axes. Report a finding only at
**confidence ≥ 0.8**. A 0.6-confidence candidate is either raised to 0.8 with
more evidence or dropped — never filed with a hedge. The verifier's job is to
attack the candidate, not to defend it: it looks for the guard the finder
missed, the escaping, the upstream check, the reason it is not exploitable.

## The positive-control rule

A test that cannot tell "safe" from "never ran" certifies the vulnerable case.
Two measured instances, both real:

- **Timing / distribution claims** — a single slow login "proving" enumeration
  is noise. Take a distribution (N samples each side), and report only a
  separation that holds across it. One sample is not a finding.
- **Log-leak audits** — grepping a log for a secret returns empty both when the
  secret is absent and when it is present but encoded (base64, URL-encoding,
  hex, JSON-escaped). Use `qa-log-audit.sh`, which decodes before searching and
  **states which encodings it covered** — the ones it did not are exactly where
  the next leak hides. "I checked and it's clean" must name how it checked.

Generalize it: before a probe's negative result counts as "safe", prove the
probe would have caught a positive. Send the marker payload; confirm it
round-trips; then send the real one.

## The exclusion list (do not report these)

Copied from the published Claude Code security-review policy and adapted.
These are out of scope for a finding unless the scope explicitly opts one in:

- Denial of service by resource exhaustion, and rate-limiting gaps in the
  abstract (a *measured* auth-endpoint lockout bypass is in; "no global rate
  limit" as a theoretical DoS is out).
- Secrets sitting in a local `.env`, a `.env.example`, a test fixture, or a
  developer's environment — trusted by design.
- Environment variables and CLI flags treated as untrusted input — they are
  trusted; the operator sets them.
- Race conditions without a demonstrated exploit.
- Log spoofing by newline injection **unless** it crosses into a real
  consequence (forged audit record an investigator would trust) — then it is a
  finding under `observability`.
- Regex-injection and ReDoS without a demonstrated pathological input.
- SSRF limited to path manipulation on an already-permitted host with no
  reachable internal target.
- Findings in third-party dependencies whose only evidence is the advisory —
  those are a supply-chain observation (record the advisory), not a bespoke
  finding, unless you reproduce the exploit against this target.
- Anything in generated code, vendored code, or a lockfile.

An excluded candidate is noted once in the report's "Considered and excluded"
line with the reason, so the reader knows it was seen, not missed.
