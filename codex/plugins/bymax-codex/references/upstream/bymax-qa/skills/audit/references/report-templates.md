# Report templates

Two artefacts close a run: a consolidated report for the engineer who will act
on it, and a one-screen executive summary for whoever decides whether to ship.
Both are assembled from the registry and the finding files, never from memory.

## Consolidated report — `reports/<run>.md`

```
# QA Audit Report — <project> @ <short-sha><dirty?>
Run: <run-id>   Target: <ticket KEY | branch | range | whole system>
Depth: <quick|full|deep>   Live: <yes|no>   Date: <ISO>
Scope: <hosts tested>   Domains: <list>   Approved-by: <name, date>

## Acceptance verdict  (ticket targets only)
<one line: MEETS CRITERIA / FAILS CRITERIA — n of m verified>
| AC | Verdict | Criterion | Method | Evidence |
| --- | --- | --- | --- | --- |
| AC-1 | PASS | <verbatim> | api-probe | evidence/<run>/AC-1/… |
| AC-2 | FAIL | <verbatim> | browser | evidence/<run>/AC-2/… → QA-014 |
| AC-3 | NOT VERIFIABLE | <verbatim> | — | (no runnable path — why) |
<omit this whole section for non-ticket targets>

## Security verdict
<one line: BLOCK ship / SHIP WITH FIXES / CLEAN for the scope examined>
<CRITICAL: n · HIGH: n · MEDIUM: n · LOW: n · candidates dropped: n>

## Findings
| ID | Sev | Status | Component | Title | Refs |
| --- | --- | --- | --- | --- | --- |
| QA-012 | HIGH | HANDED-OFF | POST /auth/refresh | refresh reuse does not revoke family | V9.2.1 / CWE-384 |
<one row per finding; full detail in findings/QA-NNN.md>

## Coverage — what was and was not examined
Examined:     <domains × boundaries actually hunted, static and/or live>
Not examined: <domains skipped, why — not in --domains, no reference yet, target down>
Delegated:    <controls found DELEGATED, with where they live — not gaps>
Considered and excluded: <candidates dropped by the exclusion list, with reason>

## Needs a human
<findings with no owner; public-repo HIGH/CRITICAL awaiting a private channel;
 scope questions; anything the run could not route>

## Evidence & reproduction
All captures under .claude/qa/evidence/<run>/. Each finding names its own.
This report is stamped to commit <full-sha>; re-running against a later commit
may differ — the audit is a point-in-time read, not a proof of absence.
```

The **Coverage** block is not optional. A report that lists findings without
saying what it did not look at invites the reader to assume the silence means
"clean". State the boundary of the audit as plainly as its findings.

## Executive summary — `reports/<run>-exec.md`

Five lines, no jargon, for a non-specialist:

```
# <project> security audit — <date>

Bottom line: <one sentence — safe to ship? blocked on what?>
Found:       <n> issues — <n> critical, <n> high, <n> medium, <n> low.
Worst:       <the single most serious finding, in one plain sentence>
Status:      <n> handed to owners, <n> filed as issues, <n> awaiting a decision.
Not covered: <one line — what this audit did not examine>
```

For a ticket target, replace "Found" with the acceptance verdict first
("Meets 4 of 5 acceptance criteria; AC-2 fails") and the security count second —
the reader asked "is the task done", and both axes answer it.

The "Not covered" line matters most here: an executive who reads only this must
not mistake a scoped audit for a whole-system guarantee.

## `status` mode output

`/bymax-qa:audit status` reads the registry and prints, no messages sent:

```
QA REGISTRY — <project>
Open findings:    QA-014 (CRITICAL, OPEN, no owner) · QA-012 (HIGH, HANDED-OFF, nest-auth-08)
Awaiting re-test: QA-009 (FIX-CLAIMED, PR #181 — retest pending)
Validated:        QA-003, QA-005, QA-008
Rejected:         2 candidates (see candidates/)
Last run:         <run-id> — <date>, depth <d>, <n> findings
Needs a human:    QA-014 has no owner and no issue repo in scope
```

Health line first, the way the PM report leads with health: the reader may act
on the first line alone (any CRITICAL/HIGH `OPEN` or `REOPENED` → not clear).
Every claim traces to a registry row; every "Validated" is backed by a re-test
evidence path, never an owner's word.
