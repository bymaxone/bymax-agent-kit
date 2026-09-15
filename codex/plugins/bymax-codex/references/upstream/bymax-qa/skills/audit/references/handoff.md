# Hand-off & re-test

A finding is not done when it is written. It is done when the owner fixed it
and you proved the fix holds. This reference covers the three routes a finding
takes to its owner, and the re-test that closes it.

The auditor never fixes the code. The whole point of the peer-team model is
that the finder and the fixer are different agents, so a fix is reviewed by
the party that found the defect and cannot rubber-stamp its own work.

## Choosing the route

For each finding, in this order:

1. **A live peer owns the component** → message the peer. Owner map in the
   scope; confirm the peer is live with `ListAgents` *this turn*, never a
   remembered name.
2. **No live peer, issues allowed, repo known** → file a GitHub issue in the
   owning repo.
3. **Neither** → leave the finding `OPEN` in the registry, marked
   `HANDED-OFF-PENDING: no owner`, and surface it to the human in the report's
   "Needs a human" block. Never invent an owner.

`--no-handoff` stops at recording. `--no-issues` allows peer messages but never
issues; a finding with no live peer then routes to the human. When the target
was a **ticket**, Route 3 below additionally writes the QA result back to the
ticket as a comment — additive to the owner hand-off, not a replacement for it.

## Route 1 — message the peer

Built on the same cross-session protocol `bymax-pm` uses. The peer has not
loaded this skill, so **the message carries its own reply instructions**. First
line is self-contained — the human sees only the first line as a preview.

```
FINDING_HANDOFF QA-012 — refresh token reuse does not revoke the token family

From:      <this session's name> (Security QA)
Severity:  HIGH (CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N = 6.5)
Refs:      ASVS V9.2.1 · CWE-384 · API2:2023
Component: nest-auth/src/server/services/refresh.service.ts:88 · POST /auth/refresh

What:      Replaying a consumed refresh token issues a new token instead of
           revoking the login lineage. Reproduction and evidence below.
Reproduce:
  1. POST /auth/register (throwaway) → capture refresh token R
  2. POST /auth/refresh with R → 200, new tokens (expected)
  3. POST /auth/refresh with R again → 200 (BUG: expected 401 + family revoked)
Evidence:  paste the two request/response pairs, secrets redacted; full capture
           at .claude/qa/evidence/<run>/QA-012/ in the audit workspace
Impact:    a stolen-and-used refresh token stays valid; reuse is not detected.
Fix:       on refresh, mark the presented token consumed atomically; a second
           use of a consumed token revokes the whole family (ASVS V9.2.1).

Reply to this message (copy this message's `from` as your `to`), first line
starting with the type and id exactly:
- FIX_CLAIMED QA-012 — the commit SHA or PR that fixes it, and one line on how
- BLOCKED QA-012 — if you cannot fix it as reported, and why (wrong premise,
  missing access) so QA can re-scope or correct the finding
```

Do not paste the whole finding file or large evidence blobs into the message —
point at the workspace path and the issue. Update the finding to HANDED-OFF
with the message timestamp, and the registry row.

Subscribe for an idle notice (`notify_when_idle: true`) on the owner rather than
polling. React when it fires; re-subscribe if still waiting.

## Route 2 — file a GitHub issue

Only when no live peer owns it and the scope allows issues on that repo.

```bash
gh issue create --repo <owner>/<repo> \
  --title "QA-012: refresh token reuse does not revoke the token family" \
  --label "security,severity:high" \
  --body-file .claude/qa/findings/QA-012.body.md
```

The body is the finding without the internal fields (no confidence axis, no
verifier notes): title, severity + CVSS, references, component, reproduction,
evidence (redacted, with request/response inline), impact, remediation. Write
it to a `.body.md` beside the finding so the issue text is reviewable and the
`gh` call takes a file, not a fragile inline string.

Record the issue URL in the finding and the registry; status → HANDED-OFF.
When a peer for that repo later appears in `ListAgents`, message it once with
the issue link so the human hand-off and the agent hand-off converge.

### Public repositories

A HIGH or CRITICAL finding is **never** filed as a public issue — that is a
disclosure. For a repo the scope marks `public`:

- Prefer a private security advisory:
  `gh api repos/<owner>/<repo>/security-advisories -f ...` (or tell the human
  to open one) — never a public issue.
- If advisories are not available, keep the finding in the workspace only,
  status `HANDED-OFF-PENDING: public repo, needs private channel`, and surface
  it to the human. MEDIUM/LOW may be filed publicly if the scope permits.

## Route 3 — write the result back to the ticket

When the target was a Jira ticket, close the loop where the human is looking:
post the QA result as a **comment** on the ticket. This is additive to routes 1
and 2 — a failed criterion or a security finding still goes to the owner as a
message or an issue; the ticket comment is the summary the reporter reads.

Only when the Jira access from `references/targets.md` allows writing and
`scope.md`'s `jira.write-back` is `true`. The comment carries:

- the **acceptance table** — each `AC-n` and its PASS/FAIL/BLOCKED/NOT-VERIFIABLE
  verdict;
- a **one-line security summary** — counts by severity, with links to any
  issues filed or the workspace path;
- the audited commit SHA and the run id.

Never a status transition (the QA does not move the ticket), never a secret
value behind the evidence, and never the full finding bodies — link them. Post
through whatever Jira access resolved: the MCP's comment tool, or the CLI
(`jira issue comment add <KEY> --body-file …`, `acli jira workitem comment …`).
Record the comment url in the run report. If write-back is not permitted, say so
in the report and leave the result in the workspace for the human to relay.

## Re-test — the only thing that closes a finding

`FIX_CLAIMED` (or an issue closed) moves a finding to FIX-CLAIMED, never to
VALIDATED. To close it:

1. `git -C <repo> fetch` and check out the claimed SHA in a **disposable
   worktree** (`git worktree add` at the SHA, removed after) so the owner's
   checkout is untouched — reading, not writing.
2. Re-run the finding's exact reproduction against that revision. Under
   `--live`, the stack must be rebuilt at that SHA for the probe to mean
   anything; say so if it was not.
3. Capture the re-test evidence to `evidence/<run>/QA-NNN/retest-<date>/`.
4. **Passes** (the defect is gone) → VALIDATED, with the evidence path in the
   Verification log; reply `FINDING_VALIDATED QA-NNN` to the peer or comment on
   the issue and close it.
   **Fails** (still reproduces, or a new variant) → REOPENED; reply
   `FINDING_REOPENED QA-NNN` with the new evidence, and re-hand-off.

A fix that lands in a different PR does not close the origin finding by itself
— re-test against the merged SHA, then close. And a finding whose family you
suspect (one route wrong often means siblings wrong) gets a re-hunt of the
family before you accept the single fix, not just a re-test of the one route.
