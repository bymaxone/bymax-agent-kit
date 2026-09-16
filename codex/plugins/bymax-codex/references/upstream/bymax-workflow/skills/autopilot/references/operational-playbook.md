# Autopilot Operational Playbook

The architecture and the operational procedures behind
`/bymax-workflow:autopilot`. Every rule here was learned on real autonomous
runs (multi-phase library and application builds); the failure each rule
prevents is named so the rule survives being questioned.

---

## 1. Architecture: who does what (the most important lesson)

The work is split across **two roles**. Mixing them is what deadlocked the
naive design.

```
┌───────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR  (the main session: long-lived, small context)               │
│                                                                           │
│  • Owns the chain. Decides which phase is next.                           │
│  • Verifies external preconditions before each phase.                     │
│  • Spawns ONE implementer sub-agent per phase (isolated git worktree).    │
│  • Picks the implementer's model per the config's model policy.           │
│  • Certifies the candidate, pushes and opens its PR.                        │
│  • Owns every long wait: CI, review bot, grace window — via background    │
│    watchers that exit on a SIGNAL, plus a ScheduleWakeup fallback.        │
│  • Merges after the full gate conjunction, updates dashboards, chains     │
│    the next phase.                                                        │
└───────────────────────────────────────────────────────────────────────────┘
                                    │ spawns (Agent tool, isolation: "worktree")
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ IMPLEMENTER  (a sub-agent: one per phase, in its own worktree)            │
│                                                                           │
│  • Implements tasks, commits the candidate and runs gates;   │
│    returns the worktree/HEAD and evidence to the orchestrator, STOPS.   │
│  • NEVER waits for the review bot. NEVER merges. NEVER spawns anything.   │
└───────────────────────────────────────────────────────────────────────────┘
```

**Why the split.** A background sub-agent that tries to "wait for the review
bot / wait for CI" simply **ends its execution** the moment it enters a long
wait — only the main session is re-invoked by task notifications when a
background job finishes. The original single-agent design ("one agent does
everything including merge and spawns the next") **deadlocked** waiting for
the code-review bot. So the long waits MUST live in the orchestrator, fed by
background polls that exit on a signal, not on a fixed sleep. That background
completion is what re-invokes the main loop and keeps the chain alive
between phases.

**Why ONE implementer at a time is non-negotiable.** Test workers reload the
project's dependency graph into their own memory (every Jest/ts-jest worker,
every Vitest fork — worst with local `file:`/`workspace:` library links,
which get duplicated per worker). Peak memory ≈
`workers × concurrent runners × concurrent agents`. A real prior run crashed
a 36 GB machine past 70 GB into swap by fanning test suites across parallel
sub-agents. Concurrent e2e stacks (docker compose, Testcontainers) also
collide on ports. Therefore: one implementer, one suite at a time, one
container stack at a time, bounded worker pools (`maxWorkers: '50%'` baked
into the test configs, `NODE_OPTIONS=--max-old-space-size=4096` as a guard).

---

## 2. Merge gate: a conjunction, after a bounded grace window

Never merge the instant CI goes green. A second bot review can land ~90 s
after a push; merging too early turns it into a stray follow-up PR. Merge
only when **ALL** hold:

- **CI green**: `gh pr checks <N> --json bucket` shows **0 fail and
  0 pending**. Checks that are `skipping` for declared reasons (e.g.
  visibility-gated workflows on a private repo) count as pass — the config's
  CI section says which.
- **No pending review request**: `gh pr view <N> --json reviewRequests`
  is an empty array. This term is **time-bounded**: a request pending past
  the config's review-bot timeout with no review submitted is treated as
  bot-unresponsive and cleared (§9) — it must never hold the gate forever.
- **No open bot threads**: every `reviewThreads` node `isResolved: true`.
- **Every arrived review triaged**: fetch reviews and current `headRefOid` again;
  inspect the review's `commit.oid` where available and record processed review IDs.
  A clean review of the current HEAD is evidence to proceed, not a reason to push
  another commit. Revalidate stale findings against current code before acting.
- **Grace elapsed**: the config's grace window (default **≥ 4–5 min**) since
  the last push, measured concretely — record the push timestamp, compute
  the elapsed time; never eyeball it.

After a fix-push, the watcher has **three valid exit criteria**:

- `BOT_REREVIEWED` — a previously unprocessed review ID arrived; triage it against
  current HEAD, then emit `BOT_COMMENTED` for confirmed blockers or re-evaluate
  `READY_TO_MERGE` after grace. A clean review does not create another push, **or**
- `GRACE_NO_REVIEW` — `reviewRequests` empty **and** the grace window
  elapsed with no new review (covers PRs where the bot does not re-review),
  **or**
- `BOT_TIMEOUT` — a review request has been pending longer than the config's
  review-bot timeout with no review submitted (covers a requested bot that
  never responds — see §9 for the recovery procedure).

Do not idle during the window: sync the default branch, read the next
phase's task file, pre-draft thread replies, so the merge is immediate when
the gate opens.

---

## 3. Fix procedure (CI failed or bot commented)

1. **Release the phase branch first.** A branch is pinned to the worktree
   that created it; git refuses to check the same branch out in two
   worktrees. If the implementer's worktree still holds it:
   `git worktree remove <path> --force`.
2. **Triage before editing.** Verify each bot suggestion against current code and a
   reproduction. Batch confirmed introduced blockers; defer nits and unrelated issues
   with reasons. Apply the autonomous-delivery contract using the same persistent
   six-candidate ledger across every fix-push. Fresh comments do not renew it.
   The orchestrator owns the independent reviewers; a fix subagent only returns a
   committed correction and regression evidence. No reviewer may grade its own fix.
3. **Local gates before pushing.** The same gates the implementer ran; a fix
   that breaks other tests is worse than the original failure.
4. Push, then resolve threads (next section), then start a **new** watcher.

---

## 4. Resolving bot threads (anti-stale)

- **Re-fetch thread IDs FRESH each time**, and check `viewerCanResolve`.
  Thread IDs change when the bot re-reviews a new commit; reusing a
  remembered ID returns `NOT_FOUND` and looks — falsely — like a permission
  error. A `FORBIDDEN`/`NOT_FOUND` here is a **stale-ID symptom**, not a
  permission wall; never stop the chain or ask the operator to re-auth
  unless `viewerCanResolve: false` is actually observed.
- **Reply + resolve one call at a time** — batched GraphQL mutations cancel
  as a group when one fails. Cite the **real fix SHA**
  (`git rev-parse --short HEAD`) in each reply; never invent one.
- **Verify `isResolved: true`** with a fresh read before declaring a thread
  done.

```bash
# fresh fetch (inline literals — parameterized -F form can mis-parse):
gh api graphql -f query='query{repository(owner:"<OWNER>",name:"<REPO>"){pullRequest(number:<N>){reviewThreads(first:100){nodes{id isResolved viewerCanResolve comments(first:1){nodes{databaseId}}}}}}}'
# resolve, one per message:
gh api graphql -f query='mutation{resolveReviewThread(input:{threadId:"<FRESH_ID>"}){thread{isResolved}}}'
```

---

## 5. Autonomy backbone: never end a turn with a dead gap

- The chain stays alive only while there is **always** either a tracked
  background job pending **or** a `ScheduleWakeup` armed. End a turn with
  neither and nothing re-invokes the loop — the chain stalls waiting for a
  human, which defeats the entire point.
- `ScheduleWakeup` is a **long fallback (≥ 1200 s)**, not a poll. Tracked
  background work auto-notifies on completion; the wakeup only rescues the
  chain if a watcher dies silently. Re-arm it each relevant turn with a
  prompt describing the **current** state, never a stale one.
- **Silent-death detection**: an implementer worktree still at base
  (0 commits) after ~60 min with no completion notification suggests death.
  Investigate file mtimes (recent = alive; stale = dead), then re-spawn.
  Widen the window to ~120 min for phases the config marks *heavy*
  (container image pulls, browser installs, mutation-testing runs) and for
  any first run on a cold cache.

---

## 6. Worktree discipline

- **Every file-writing sub-agent runs in its own worktree**
  (`isolation: "worktree"`), one agent per directory. Two agents in the same
  tree collide: uncommitted edits mix and the pre-commit hook breaks on the
  blended tree (recovery: kill both, `git reset --hard` + `git clean -fd`,
  re-run isolated).
- **Release a branch before a fix touches it** (§3 rule 1).
- **Clean up on merge — always delete the merged PR's own branch**, remote
  and local, in this order, with proof:

  ```bash
  BR=$(gh pr view <N> --json headRefName -q .headRefName)   # capture FIRST
  gh pr merge <N> --squash --delete-branch
  git switch <default-branch> && git pull
  git worktree remove <path> --force        # if still present
  git branch -D "$BR" 2>/dev/null || true
  git push origin --delete "$BR" 2>/dev/null || true
  git ls-remote --heads origin "$BR"        # MUST print nothing
  git branch --list "$BR"                   # MUST print nothing
  git worktree prune
  ```

  If either verification still shows the branch, the merge is **not**
  finished.

---

## 7. Anti-hallucination: verify, never trust narration

- An agent's final message **can confabulate state** — fixes it did not
  make, invented SHAs, "I merged it". Always confirm real state via
  `git`/`gh`, never via prose.
- Agent-liveness signals: the real "still running" indicator is the
  **absence of a completion notification**, plus fresh file mtimes in the
  worktree — not any task-list UI, which can lag or return empty with jobs
  still active.
- **Never `Read` an agent's raw output/transcript file** — it is a JSONL
  transcript that will blow your context. Read only the small verdict files
  your own background watchers write.
- Before writing "resolved" / "green" / "merged" anywhere (dashboards, PR
  comments, the user), confirm with a fresh read **this turn**.

---

## 8. Concrete `gh` signal vocabulary

| Signal | Command |
|---|---|
| CI status | `gh pr checks <N> --json bucket` → count `pass` / `fail` / `pending` (config says which `skipping` are expected) |
| Pending review request | `gh pr view <N> --json reviewRequests` (empty = nothing queued) |
| Re-review detection | Fresh review IDs and reviewed `commit.oid` versus current `headRefOid` |
| Open threads | GraphQL `reviewThreads.nodes[]` → `isResolved`, `viewerCanResolve`, `comments[0].databaseId` |
| PR identity | `gh pr view <N> --json number,headRefName,state,mergeStateStatus` |
| Failing job log | `gh run view <run-id> --log-failed` |
| Registry precondition | e.g. `npm view <package> version` (exit 0 = published) — per config |

A background watcher composes these into a poll that **exits with exactly
one verdict** (`CI_FAILED` / `BOT_COMMENTED` / `READY_TO_MERGE` /
`BOT_REREVIEWED` / `GRACE_NO_REVIEW`), sleeping between iterations, writing
the verdict to a scratchpad file the orchestrator reads on re-invocation.

---

## 9. Review-bot request

If the config names a review bot (e.g. GitHub Copilot code review), the
orchestrator requests it right after `gh pr create`:

```bash
gh pr edit <PR#> --add-reviewer copilot-pull-request-reviewer[bot]
```

If the reviewer slug is rejected, the orchestrator records the failure and
requests the review via the UI-equivalent API
or proceeds with CI-only gating — the merge-gate conjunction adapts (no
pending-review / no-threads terms still apply to whatever reviews exist).

**Unresponsive bot (the request was accepted but no review ever arrives).**
Without a bound, a forever-pending `reviewRequests` entry would hold the
merge gate open eternally — the same class of deadlock the orchestrator/
implementer split exists to prevent. The bound is the config's
**review-bot timeout** (default ~15 min), measured from the review request
(or from the latest push, whichever is later). When the watcher signals
`BOT_TIMEOUT`, the orchestrator:

1. Confirms with a fresh read that no review was submitted
   (`reviews[]` vs the request time) — never on the watcher's word alone.
2. Removes the stale request:
   `gh pr edit <N> --remove-reviewer <bot-slug>`.
3. Comments once on the PR (plain, factual): the configured review bot did
   not respond within the timeout, so the gate proceeded CI-only. The
   comment is the audit trail — never silently drop a declared reviewer.
4. Re-evaluates the merge-gate conjunction (now CI + grace + any reviews
   that do exist) and proceeds normally.

This is safe because the review floor was already enforced **before the PR
opened**: the orchestrator completed independent dual review and
security verification with no unresolved confirmed blockers. The bot is a second opinion, not the
only gate — a dead second opinion must not become an infinite wait. If the
bot reviews *after* the timeout cleared it, the normal rules resume: its
threads must be resolved before merge (the no-open-threads and
all-arrived-reviews-triaged terms still apply to whatever arrives before the merge
actually executes).
