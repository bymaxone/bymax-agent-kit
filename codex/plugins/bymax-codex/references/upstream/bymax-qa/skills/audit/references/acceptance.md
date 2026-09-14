# Acceptance-criteria QA (ticket targets)

When the target is a ticket (`references/targets.md`), the audit adds an axis
the other targets do not have: it verifies that the delivered change **meets the
acceptance criteria the ticket states**. This is functional QA — does the
feature do what was asked — running alongside, not instead of, the security
hunt on the same change.

The discipline that keeps it honest is the same one that governs a finding: a
criterion is verified by **exercising the system**, never by reading the code
and judging that it looks right. A criterion you cannot exercise is reported as
**not verifiable**, not quietly passed.

## 1. Read the ticket into criteria

From the ticket (fetched via the access ladder in `targets.md`), extract:

- the **summary** and **description** — what the change is for;
- the **acceptance criteria** — the checkable statements, whether a bullet list
  or Gherkin `Given/When/Then`;
- the **definition of done**, if the project uses one, as extra criteria;
- the **linked change** — branch, commits, PR — to know what to exercise.

Number the criteria `AC-1, AC-2, …`, quoting each verbatim. If the criteria are
vague or missing, say so and treat the description's implied requirements as
criteria, marking them `(inferred)` — never manufacture a criterion the ticket
does not support.

## 2. Derive one test case per criterion

For each `AC-n`, write a concrete, runnable case before running anything:

- **Given** the precondition (a seeded state, a logged-in throwaway account),
- **When** the action (an API call, a UI step, a job),
- **Then** the observable expected result.

Name the **method** that will exercise it: an API probe (`qa-probe.sh`), a
browser step (through `bymax-web-verify` when a UI is involved), a database or
cache read, or — only when nothing runnable exists — a code read, which yields
`not verifiable`, not a pass.

**A live method needs `--live`.** `qa-probe.sh` and the browser reach the
running system, which the `qa-guard` hook confines to the scope's
`allowed-hosts` — so they run only when the audit was invoked with `--live` and
the scope carries `allowed-hosts` + `base-url`. Without `--live`, a criterion
whose only method is a live probe is recorded **NOT VERIFIABLE** ("needs a live
run"); tell the human to re-run the ticket with `--live`. A code read alone can
**FAIL** a criterion (the change plainly does not implement it) or leave it
**NOT VERIFIABLE** — it can never **PASS** one, since a PASS requires exercising
the running system.

## 3. Execute and record a result

Run each case against the delivered change. Every criterion ends in exactly one
of four results — three of which are not "pass", and the fourth is honest about
its own blindness:

| Result | Meaning |
| --- | --- |
| **PASS** | exercised, the expected result was observed, evidence captured |
| **FAIL** | exercised, the result differed from the criterion — expected vs actual recorded |
| **BLOCKED** | could not be exercised because a precondition failed (the stack is down, a dependency is missing) — a gap in the run, not in the code |
| **NOT VERIFIABLE** | no way to exercise it in this run (a criterion about a system the scope does not reach, a manual step) — stated plainly so nobody reads silence as success |

A `PASS` asserted from the code "looking correct" is not a pass — it is `NOT
VERIFIABLE`, and the report says why. This is the same rule a log audit follows:
"not found" and "could not look" must never render as the same clean result.

## 4. Acceptance result contract

Record the acceptance run in the report (`references/report-templates.md`) and,
for a `FAIL` that warrants a fix, open a finding so it routes to the owner like
any other. Each criterion carries:

```
AC-n · <verdict PASS|FAIL|BLOCKED|NOT VERIFIABLE>
  Criterion:  <verbatim from the ticket>
  Test:       Given … When … Then …
  Method:     api-probe | browser | db | cache | code-read
  Evidence:   .claude/qa/evidence/<run>/AC-n/…   (request/response, screenshot, query)
  If FAIL:    expected <…> vs actual <…>          → finding QA-NNN (functional)
```

## 5. Severity of a failed criterion

A failed acceptance criterion is a functional defect, not a CVSS vulnerability,
so band it by how much it breaks the ticket, and say in the finding that the
axis is acceptance, not security:

- **Blocker** — a criterion central to the ticket fails; the task is not done.
- **Major** — a criterion fails at an edge or for a secondary path.
- **Minor** — a criterion is met in substance but deviates in a small,
  low-impact way.

A security defect found on the same change keeps the CVSS-based severity from
`references/finding-contract.md`. The two classes live in the same registry and
report, labelled, so a reader never confuses "criterion 3 fails" with "this
route has a BOLA".

## 6. Hand-off and write-back

Failed criteria and security findings both hand off through
`references/handoff.md`. When Jira access allows it and `scope.md` permits
write-back, close the loop on the ticket itself: post a comment with the
acceptance table (each `AC-n` and its verdict) and a one-line summary of any
security findings, linking the workspace and any issues filed. This is the
"point at the ticket, get the QA back on the ticket" flow — but only ever a
comment, never a status transition, and never the secret values behind the
evidence.

## The report has two axes

A ticket run's report leads with the **acceptance verdict** — does the change
satisfy the ticket — and carries the **security findings** on the touched
surface beneath it. Either axis can block: a change can meet every criterion and
still ship a vulnerability, or be clean of vulnerabilities and still fail its
own acceptance. Report both plainly; let the reader act on each.
