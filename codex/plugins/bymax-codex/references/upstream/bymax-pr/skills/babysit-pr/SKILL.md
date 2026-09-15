---
name: babysit-pr
description: Autonomously shepherd an open PR to merge-readiness on ANY project — verify the gh CLI is ready, resolve merge conflicts, monitor CI checks at a cadence matched to the CI's real duration (270-second floor), classify failures as real vs flaky (re-running flaky checks), fix real failures locally before pushing, triage bot review comments, and notify the developer when the PR is green. Never merges. Invoked via /bymax-pr:babysit-pr.
user-invocable: true
argument-hint: "[pr-number-or-url]"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Grep
  - Glob
  - ScheduleWakeup
  - PushNotification
---

# Babysit-PR Skill (generic)

You are the **babysit loop** for an open pull request, in **any** repository.
Your job is to drive the PR toward merge-ready and notify the developer when
it gets there. You wake up at fixed intervals, resolve conflicts, check CI,
classify and fix failures, triage bot comments, then re-arm yourself for the
next wake-up.

You **never merge** the PR and you **never push to the default branch**.

This skill is **project-agnostic**: it auto-detects the package manager and the
lint/test/typecheck/build commands from the repo, and it reads the project's
own `CLAUDE.md` (if present) to respect local rules. There are no hardcoded
paths or workflow names.

---

## Phase −1: Preflight (MANDATORY — run FIRST, every first invocation)

Before anything else, verify the GitHub CLI is usable. **This skill cannot
function without `gh` installed and authenticated.**

```bash
# 1. Is gh installed?
if ! command -v gh >/dev/null 2>&1; then
  echo "❌ GitHub CLI (gh) is not installed."
  exit 1
fi

# 2. Is gh authenticated?
if ! gh auth status >/dev/null 2>&1; then
  echo "❌ GitHub CLI is installed but not authenticated."
  exit 1
fi
```

- **If `gh` is NOT installed**, stop immediately and tell the developer
  (do not schedule a wake-up):

  > ⚠️ **babysit-pr needs the GitHub CLI.** It isn't installed.
  > Install it, then re-run `/bymax-pr:babysit-pr`:
  > - macOS: `brew install gh`
  > - Linux: see <https://github.com/cli/cli/blob/trunk/docs/install_linux.md>
  > - Windows: `winget install --id GitHub.cli`

- **If `gh` is installed but NOT authenticated**, stop immediately and tell
  the developer (do not schedule a wake-up):

  > ⚠️ **GitHub CLI is installed but not logged in.** babysit-pr needs an
  > authenticated session. Run this in your terminal (prefix with `!` in
  > Claude Code) and re-run `/bymax-pr:babysit-pr`:
  > ```
  > gh auth login
  > ```
  > Verify with `gh auth status`.

Only continue past this phase once both checks pass. Skip this phase on
subsequent wake-ups within the same babysit session (already verified).

---

## Overview

The loop has these moving parts:

1. **Preflight** — verify gh is installed + authenticated (above).
2. **Loop entry** — identify the PR, detect project commands, schedule wake-up.
3. **Conflict resolution** — auto-rebase onto the base branch when the PR is
   `CONFLICTING`. Pause only if auto-rebase fails.
4. **CI monitoring** — fetch checks, classify each failure as **real** or
   **flaky**, re-run flaky checks, fix real failures locally, then push.
5. **Bot comment handler** — process unhandled bot review threads on every
   wake-up with a 4-tier triage.
6. **Termination check** — if the PR is green and all bot threads are
   resolved, fire a `PushNotification` and stop scheduling.
7. **State** — a single PR comment marked `<!-- babysit-state -->` stores
   per-check failure/flaky counts and processed comment IDs so the loop is
   idempotent across wake-ups and session restarts.

If you cannot make progress (same real failure recurs after 3 fix attempts,
flaky check fails 3 re-runs, or an external dependency surfaces), pause the
loop and notify the developer. **Never push speculative fixes.**

---

## Wake-up Execution Order (MANDATORY — never skip a phase)

On **every** wake-up — regardless of CI state — run these phases in order:

```
0. Conflict Resolution   ← rebase onto base branch if CONFLICTING; pause only if rebase fails
1. CI Monitoring         ← classify real vs flaky; re-run flaky; fix real locally
2. Bot Comment Handler   ← process ALL unhandled bot threads on EVERY wake-up
3. Termination Check     ← stop and notify, or reschedule
```

**The Bot Comment Handler is NOT optional when CI is pending.** New bot
comments can arrive at any time. Skipping the handler when CI is pending is
the primary cause of missed comments. Always run it.

---

## Loop Entry (first invocation only)

```bash
# 1. Identify the PR — from the argument (number or URL) or the current branch.
if [ -n "$1" ]; then
  PR_NUMBER=$(gh pr view "$1" --json number -q .number)
else
  PR_NUMBER=$(gh pr view --json number -q .number 2>/dev/null)
fi
if [ -z "$PR_NUMBER" ]; then
  # No PR: notify and exit (no wake-up).
  echo "No open PR found for the argument or current branch."
  exit 1
fi

# 2. Determine the base branch (where the PR will merge into).
BASE_BRANCH=$(gh pr view "$PR_NUMBER" --json baseRefName -q .baseRefName)
```

### Detect project commands (project-agnostic)

Inspect the repo once and remember the right commands for this project. Use
these throughout the loop instead of assuming `npm`.

1. **Package manager** — pick by lockfile, in this order:
   `bun.lock`/`bun.lockb` → `bun`; `pnpm-lock.yaml` → `pnpm`;
   `yarn.lock` → `yarn`; `package-lock.json` → `npm`.
   The run prefix is `<pm> run <script>` (for `npm`/`pnpm`/`bun`) or
   `yarn <script>` (yarn). `npm test`/`pnpm test`/`yarn test`/`bun test`
   all work for the `test` script.
2. **Scripts** — read `package.json` `scripts` and map intent to whatever
   exists: a **test** command (`test`), a **lint** command
   (`lint` / `lint:fix`), a **typecheck** command (`typecheck` / `type-check`
   / `tsc`), and a **build** command (`build`). Use only the scripts that
   actually exist.
3. **Non-JS repos** — if there is no `package.json`, detect the ecosystem
   and use its conventional gate command if obvious (e.g. `cargo test`,
   `go test ./...`, `pytest`, `make test`). If you cannot confidently
   determine a local test command, **skip the local gate** and rely on CI
   alone — but say so in the state comment (`"localGate": "none"`).
4. **Project rules** — if a `CLAUDE.md` (or `AGENTS.md`) exists at the repo
   root, read it. Respect its rules when fixing code and when dismissing bot
   comments (see Bot Comment Handler).

### Create / read state

```bash
STATE=$(gh api "repos/{owner}/{repo}/issues/$PR_NUMBER/comments" --paginate \
  | jq -r '[.[] | select(.body | startswith("<!-- babysit-state -->"))][0] // empty')
```

If empty, create one with body:

```
<!-- babysit-state -->
```json
{ "consecutiveFailures": {}, "flakyReruns": {}, "processedCommentIds": [], "paused": false }
```
```

After loop entry, run all phases immediately. If the PR is **already** green
and all bot threads are resolved, fire the "ready to merge" notification and
exit without scheduling.

---

## Scheduling the next wake-up

Every code path that does NOT terminate the loop must end with:

```
ScheduleWakeup delaySeconds=<delay> prompt="/bymax-pr:babysit-pr <PR_NUMBER>"
```

Pick `<delay>` from what you are actually waiting for, with **270 seconds as
the floor**:

- **CI running** — estimate the time remaining from the workflow's typical
  duration (`gh run list --workflow=<name> --limit 5 --json updatedAt,createdAt`
  averages it) minus what has already elapsed, and wake up shortly after that.
  A pipeline that takes ~10 minutes deserves one ~600 s check, not three 270 s
  ones.
- **Waiting on a review bot or a human** — 900–1800 s; that state changes
  slowly.
- **Just pushed a fix, CI about to start** — the 270 s floor.

The prompt cache is not a constraint at these delays (the cache TTL is one
hour), so never schedule tighter wake-ups just to "stay inside the cache" —
pacing is driven by how fast the watched state actually changes. Always pass
the PR number back in the prompt so a session restart re-targets the same PR.

Skip scheduling when:
- All termination conditions are met → fire the "ready to merge" notification.
- The loop is paused (3-strike rule, flaky exhausted, or auto-rebase failed)
  → set `"paused": true` in the state comment and notify.

---

## Phase 0: Conflict Resolution

```bash
MERGEABLE=$(gh pr view "$PR_NUMBER" --json mergeable -q .mergeable)
```

- **`MERGEABLE` / `UNKNOWN`**: skip this phase, go to CI Monitoring.
- **`CONFLICTING`**: rebase.

### Rebase procedure

```bash
git fetch origin "$BASE_BRANCH"
git rebase "origin/$BASE_BRANCH"
```

**Rebase clean (exit 0):**

```bash
git push --force-with-lease
```

Record `"lastRebase": "<timestamp>"` in state, continue to CI Monitoring.
(The push triggers CI; the normal flow handles it.)

**Rebase with conflicts (non-zero):** list and resolve by pattern.

```bash
git diff --name-only --diff-filter=U
```

| File pattern | Resolution strategy |
|---|---|
| Lockfiles (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`, `Cargo.lock`, `poetry.lock`, `go.sum`) | Take base side / regenerate: `git checkout --theirs <file>` then re-run the install (`<pm> install`) and stage the result |
| Generated output (`dist/**`, `build/**`, `*.generated.*`, `coverage/**`, `reports/**`, `*.min.*`) | `git checkout --theirs <file>` — generated artifacts from the base branch win |
| Any hand-written source file | Read the full conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`). Understand what the base changed (`theirs`) and what the branch added (`ours`). Produce a merge that preserves **both** intents. Write the file, then `git add <file>`. |

After staging all resolutions:

```bash
git rebase --continue
```

Repeat per conflicted commit until the rebase completes, then:

```bash
git push --force-with-lease
```

Continue to CI Monitoring.

**If a conflict cannot be resolved** (same file re-conflicts after your best
attempt, or rebase otherwise can't proceed):

```bash
git rebase --abort
```

- State: `"paused": true, "pauseReason": "auto-rebase failed on <files>"`.
- `PushNotification`: "PR #<N>: automatic conflict resolution failed on
  <files>. Manual rebase needed before babysit-pr can continue."
- Do NOT schedule another wake-up.

---

## Phase 1: CI Monitoring

```bash
CHECKS_JSON=$(gh pr checks "$PR_NUMBER" --json name,state,link,bucket 2>/dev/null)
FAILING=$(echo "$CHECKS_JSON" | jq -r '.[] | select(.bucket == "fail") | .name')
PENDING=$(echo "$CHECKS_JSON" | jq -r '.[] | select(.bucket == "pending") | .name')
```

If there are no checks configured at all, note `"ci": "none"` in state and
let the Termination Check rely on mergeability + bot threads only.

For each failing check:

1. **Pull the failing log**:
   ```bash
   HEAD_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid -q .headRefOid)
   RUN_ID=$(gh run list --commit "$HEAD_SHA" --json databaseId,name,conclusion \
     -q '[.[] | select(.name == "<check-name>" and .conclusion == "failure")][0].databaseId')
   gh run view "$RUN_ID" --log-failed > /tmp/babysit-failure.log
   ```

2. **Classify: real vs flaky.** Read the tail of the log.
   - **Likely FLAKY** when the failure looks infrastructural, not code:
     network errors (`ECONNRESET`, `ETIMEDOUT`, `socket hang up`, `getaddrinfo`),
     timeouts (`timed out`, `Timeout - Async callback`), rate limits
     (`429`, `rate limit`), runner/setup failures (`The runner has received
     a shutdown signal`, `Cannot connect to the Docker daemon`,
     `npm ERR! network`), or a test that passed on the previous SHA and whose
     failure is unrelated to the files this PR changed.
   - **REAL** otherwise: `error TS####`, ESLint errors, assertion failures
     (`expect(...)`, `AssertionError`), build/compile errors, lint rule
     violations, snapshot mismatches caused by this PR's diff.

3. **If FLAKY** → re-run the failed jobs instead of editing code:
   ```bash
   gh run rerun "$RUN_ID" --failed
   ```
   Increment `flakyReruns[<check>]` in state. **Cap at 3 re-runs.** If a
   check is still failing after 3 flaky re-runs, escalate it to REAL (the
   "flaky" hypothesis was wrong) and diagnose as code, OR if the log clearly
   shows a persistent infra outage, pause and notify:
   `PushNotification`: "PR #<N>: <check> keeps failing on infrastructure
   errors after 3 re-runs — likely a CI outage, not your code."

4. **If REAL** → fix the root cause:
   - **Fingerprint** the failure: check name + first three distinct error
     signatures (`grep -oE '(FAIL [^ ]+|error TS[0-9]+|✖ [^ ]+|AssertionError|Error: [^\n]{1,80})'`).
   - **Consult state**: if this exact fingerprint reached
     `consecutiveFailures[<fingerprint>] == 3`, stop:
     `PushNotification`: "PR #<N>: <check> failed 3× with the same error after
     fix attempts. Manual intervention needed." Set `"paused": true` and stop
     scheduling.
   - **Otherwise** apply the smallest targeted fix, then **run the local gate
     before committing** (the detected test command, e.g. `<pm> test`). If the
     local gate fails, the fix is incomplete — keep diagnosing; do NOT commit
     or push until it's green. Then commit, push, and increment the
     fingerprint counter. Let CI re-run on the next wake-up.

   > **Mandatory local gate**: when a local test command was detected, it
   > must pass locally before any fix commit reaches the remote. A fix that
   > breaks other tests is worse than the original failure. (Skip only if the
   > repo has no detectable test command — `"localGate": "none"`.)

**Never** use `--no-verify`, `// @ts-ignore`, `any`, `eslint-disable`, or any
skip-hook flag to force a check green. Fix the root cause shown in the log.
If the project `CLAUDE.md` defines stricter rules, follow those too.

After pushing a fix, end the wake-up by scheduling the next one so CI has time
to re-run. When CI is entirely pending (no fail, no pass yet), do NOT
reschedule early — continue to the Bot Comment Handler first; only the
Termination Check decides to reschedule.

---

## Phase 2: Bot Comment Handler

```bash
REVIEW_COMMENTS=$(gh api "repos/{owner}/{repo}/pulls/$PR_NUMBER/comments" --paginate)
ISSUE_COMMENTS=$(gh api "repos/{owner}/{repo}/issues/$PR_NUMBER/comments" --paginate)
```

### Detection
A comment is a **bot comment** when `user.type == "Bot"` OR `user.login` ends
with `[bot]` (case-insensitive). Skip comments authored by the babysit loop
itself (replies marked `<!-- babysit-reply -->`).

### Already-processed guard
Before evaluating a comment, skip it if its thread already has a reply
starting with `<!-- babysit-reply -->`, or if its ID is in
`processedCommentIds` in the state comment. The marker + ID list are the
idempotency keys; a restart must not re-process or lose memory.

### Human reviewer comments (`user.type == "User"`)
Fire a `PushNotification` summarising it (PR number, file, one-sentence
excerpt) and **take no other action**. Never reply, never resolve, never
auto-implement. The developer triages human feedback.

### Relevance triage (bot comments only)

| Tier | Examples | Action |
|---|---|---|
| **MUST FIX** | Security vuln, correctness bug, data-loss risk, race condition, missing auth check | Fix |
| **SHOULD FIX** | Real clarity win, measured perf regression, missing error handling | Fix |
| **SKIP — nitpick** | "Consider extracting", "could be more readable", comment on self-evident code, defensive code for unreachable paths | Dismiss with reasoning |
| **SKIP — contradicts project rules** | Suggestion that violates the project's `CLAUDE.md`/`AGENTS.md` (architecture, typing, logging, dependency policy) | Dismiss citing the specific rule |
| **SKIP — new external service/dependency** | Suggests adding Redis, Kafka, a new SaaS, a heavyweight dep, etc. | Dismiss and `PushNotification` so the developer can decide |

When unsure between MUST FIX and SKIP, prefer SKIP and surface a
`PushNotification`. Never fix something whose correctness rationale you can't
articulate.

### Implementing a relevant comment
1. Open the file at the comment's `path` + `line`.
2. Apply the smallest fix that addresses the concern.
3. Run the local gate (typecheck + relevant tests) before committing.
4. Commit: `fix: address <bot-name> review — <short summary>` (use the bot's
   `user.login`, e.g. Copilot, CodeRabbit, SonarCloud).
5. Push.
6. Reply on the thread with the marker:
   `<!-- babysit-reply --> Fixed in <commit-sha>: <one-sentence explanation>.`
7. Resolve the review thread via GraphQL — **follow the MANDATORY procedure in
   "Resolving review threads correctly" below. Never reuse a thread ID.**

### Dismissing an irrelevant comment
1. Reply with the marker and a **specific** reason citing the SKIP criterion:
   `<!-- babysit-reply --> Not applied: <criterion>. <one-sentence why>.`
2. Resolve the thread (see "Resolving review threads correctly" below).
3. Add the comment ID to `processedCommentIds` in state.

### Resolving review threads correctly (MANDATORY — read every time)

Thread-resolve failures in this environment are **never** a permission/token-scope
problem and **must not** stop the loop or trigger a "you need to re-auth" message.
They are caused by **passing a stale or wrong thread ID** (one remembered from an
earlier turn, another session, a different batch, or a GraphQL query that silently
returned empty data). The token can resolve threads — prove it with `viewerCanResolve`.

Do exactly this, **one `gh` call per message** (a batched failure cancels siblings):

1. **Re-fetch the threads FRESH, right now**, with an inline-literal query (the
   `-F owner=… -F repo=…` parameterized form sometimes mis-parses here — use literals).
   Always include `viewerCanResolve` and the inline-comment `databaseId`:
   ```bash
   gh api graphql -f query='query{repository(owner:"<OWNER>",name:"<REPO>"){pullRequest(number:<N>){reviewThreads(first:100){nodes{id isResolved viewerCanResolve comments(first:1){nodes{databaseId}}}}}}}'
   ```
2. **Match each thread to its Copilot comment by `comments.nodes[0].databaseId`**
   (the inline review-comment id from `pulls/<N>/comments`), NOT by a remembered
   thread id. Thread IDs **change when the bot re-reviews a new commit** — the IDs
   from before your fix push are dead (`NOT_FOUND`).
3. If `viewerCanResolve` is `true` (it is, with push/triage/admin perms), resolve
   with the **freshly-fetched** id, one per message:
   ```bash
   gh api graphql -f query='mutation{resolveReviewThread(input:{threadId:"<FRESH_PRRT_ID>"}){thread{isResolved}}}'
   ```
4. **Verify**: re-query and confirm every thread is `isResolved:true` before claiming
   it. Never write "resolved" to the state comment or to the user without this check.
5. **If `viewerCanResolve` is `false`** (only then): that is a genuine permission case —
   note it in state and surface it once; do not loop on it.

**Anti-hallucination rules for this whole phase:**
- The **source of truth** is a fresh `gh api`/`gh api graphql` read **this turn** — never
  memory, never a prior batch, never another PR/session. Re-fetch IDs/SHAs every time.
- Cite the **real** commit SHA (`git rev-parse --short HEAD`) in replies — never invent one.
- Never dismiss a finding you have not actually reproduced/checked this turn.
- A failed `gh` call → diagnose it (re-fetch, inspect the error) and continue the loop;
  do **not** stop, do **not** claim a permission wall, do **not** ask the user to re-auth
  unless `viewerCanResolve:false` is actually observed.

### Cross-cutting bot rules
- Never re-process a thread that already has a `<!-- babysit-reply -->`.
- Push at most **one** bot-comment fix commit per wake-up so CI failures
  attribute cleanly.

---

## Phase 3: Termination Check

After Conflict Resolution, CI Monitoring, and the Bot Comment Handler, ask:

1. **CI**: every check is in the `pass` bucket — no `fail`, no `pending`
   (or `"ci": "none"`).
2. **Mergeable**: `gh pr view $PR_NUMBER --json mergeable -q .mergeable` is
   not `CONFLICTING`.
3. **Bot threads**: no open bot review thread
   (`reviewThreads.nodes[] | select(.isResolved == false)`).
4. **Not paused**: state `"paused"` is `false`.

If all hold, fire:

```
PushNotification: "PR #<N> is ready to merge 🎉 (babysit-pr will not merge it for you)"
```

…and DO NOT schedule another wake-up. Record the termination timestamp in the
state comment so a future `/bymax-pr:babysit-pr` on the same PR exits immediately.

Otherwise:

```
ScheduleWakeup delaySeconds=<delay> prompt="/bymax-pr:babysit-pr <PR_NUMBER>"
```

(with `<delay>` chosen per "Scheduling the next wake-up") and end the wake-up.

---

## Hard rules (always)

- **Never merge** the PR and **never push to the base/default branch.**
- Never force-green a check (`--no-verify`, `@ts-ignore`, `any`,
  `eslint-disable`, skip hooks).
- Never push a fix without the local gate passing (when one is detectable).
- Never re-process an already-handled comment.
- Never auto-act on human comments — only notify.
- Always end a non-terminating wake-up with a `ScheduleWakeup`.
- Respect the project's `CLAUDE.md`/`AGENTS.md` if present.
- **Resolve review threads, don't excuse them.** A `FORBIDDEN`/`NOT_FOUND` on
  `resolveReviewThread` is a **stale-ID** symptom, not a permission wall — re-fetch the
  thread IDs fresh this turn (see "Resolving review threads correctly"), match by
  `databaseId`, resolve, and verify `isResolved:true`. Never stop the loop, never tell
  the user to re-auth, unless `viewerCanResolve:false` is actually observed.
- **Source of truth = a fresh read this turn.** Never act on IDs/SHAs/state remembered
  from a previous batch, turn, session, or another PR. Re-fetch before every write.
- **Never report success you didn't verify.** Confirm with a fresh read before writing
  "resolved"/"green"/"merged" to the state comment, a reply, or the user.
- **One `gh`/`git` mutation per message** — batched fallible calls cancel as a group.
