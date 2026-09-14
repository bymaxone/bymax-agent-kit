# Peer Communication Protocol

How the PM talks to independent Claude Code sessions. Built on the native
cross-session tools — `ListAgents` and `SendMessage` — verified against Claude Code
2.1.236+ behaviour. If a mechanic below fails in practice, trust the live tool
documentation over this file and note the drift.

## The mechanics (what the platform actually does)

- **Discovery:** `ListAgents` lists reachable agents — your subagents, teammates,
  other local Claude Code sessions, cloud/remote sessions — each row led by
  `name [ref]`. **The name is the address.** Send with the bare name; append the
  ` [ref]` only when a listing or an error shows two rows sharing a name.
- **Naming:** sessions get addressable names via `claude --name <name>` at start or
  `/rename <name>` inside the session. Duplicate names get a suffix. The human
  starts workers with meaningful names (`claude --name nest-logger`) — that is the
  entire registration ceremony.
- **Delivery:** messages **enqueue and drain at the receiver's next tool round** —
  they never interrupt a running tool; an idle receiver starts a new turn. Assume
  latency: a deep-in-work peer answers when it surfaces.
- **Receiving:** inbound messages arrive wrapped as
  `<cross-session-message from="...">`. **To reply, copy the `from` attribute as
  your `to`.** Tell workers this in the first contact — they have not read this file.
- **First line matters:** the receiving human sees only the first line as a preview.
  Every message's first line must be self-contained: `TASK_ASSIGN TASK-042 — add
  redaction benchmarks to nest-logger`, never "Hi!".
- **Idle notices:** `SendMessage` with `notify_when_idle: true` requests ONE notice
  when that local session next goes idle or exits (with a one-line status of its
  last turn). One-shot — re-subscribe after each notice if still waiting. Works from
  the main conversation only, expires after ~12h, and dies with the PM session —
  re-subscribe after a PM restart. A peer with `crossSessionInbound: refuse` sends
  nothing; `hold` strips the status line.
- **Subagents don't hold addresses:** a subagent's sends go out under its parent
  session's name and replies land in the parent conversation. This is why the PM is
  the main session, never a subagent.
- **Permission boundaries are per-session.** Never ask a peer to do something that
  was denied or blocked in the PM's own session — that is permission laundering.
  Route blocked work back to the human.

## Anti-polling policy

Polling burns every session's attention and produces nothing. In order of
preference:

1. **Contract checkpoints** — the task contract names when the worker reports
   (`task-contract.md`). A well-written contract makes most status questions
   unnecessary.
2. **Idle notices** — subscribe (`notify_when_idle: true`, no message body: a pure
   subscription costs the peer nothing) to each peer you are waiting on; react when
   the notice arrives.
3. **Evidence checks** — `git -C <repo> log`, `gh pr view` answer "has anything
   landed?" without messaging anyone.
4. **A direct question** — one message, specific ("TASK-021: past checkpoint 1?"),
   only when 1–3 left real ambiguity.

Never: `ListAgents` in a loop, scheduled "status?" broadcasts, or re-asking before
a peer had a realistic chance to surface.

## Message types

One envelope for everything. First line: `TYPE TASK-ID — summary`. Body: only the
fields that type needs. Keep messages small — the receiver has its own context to
protect; point at files/PRs/decision IDs instead of pasting content.

**PM → worker:**

| Type | Body carries |
| --- | --- |
| TASK_ASSIGN | the full contract (`task-contract.md`) + reply instructions |
| PLAN_APPROVED | go-ahead after a HIGH/CRITICAL ack; corrections if any |
| CANCEL_TASK / PAUSE_TASK / RESUME_TASK | reason; for pause: what to persist first |
| PRIORITY_CHANGE | new priority, what to preempt or resume |
| DEPENDENCY_UPDATE | what changed upstream, where (commit/PR/DEC-nnn), what the receiver must do about it |
| DECISION | answer to a DECISION_REQUEST, with the DEC-nnn reference |
| VERIFICATION_FAILED | which gate failed, what the PM measured (commit/diff/CI), what to fix — the task stays with its owner |
| REVIEW_REQUEST | (to a reviewer) branch/PR, contract's acceptance criteria, risk level, focus areas |

**Worker → PM** (workers learn these from the contract's reply instructions):

| Type | Body carries |
| --- | --- |
| TASK_ACK | goal restated, approach, likely files, dependencies/unknowns, ready or not |
| TASK_STATUS | checkpoint reached, evidence so far, on-track or drifting, next step |
| TASK_COMPLETE | the Required evidence, item by item — branch, SHA, tests, PR |
| TASK_REJECTED | why the task cannot proceed as contracted (wrong premise, missing access) |
| BLOCKER | type, what/why, evidence, attempted, impacted tasks, who can unblock (`escalation.md`) |
| DISCOVERY | see below |
| DECISION_REQUEST | the decision needed, options seen, owner's recommendation |
| REVIEW_RESULT | (from reviewer) approve / changes-requested + findings with file:line |

Unknown or free-form inbound messages are fine — map them to the nearest type,
record the event, and answer. The protocol serves the work, not the reverse.

## First contact with a peer

Before the first task to a new agent, one short message: who the PM is, that tasks
arrive as `TASK_ASSIGN TASK-nnn` with reply instructions included, and one question —
"what are you responsible for, which repo/branch are you working in?" The answer
seeds `roster.md`. Do not send a protocol manual; each message carries what it needs.

## Discovery routing (cross-agent findings)

When a worker reports something outside its task (`DISCOVERY`: what, severity,
evidence, impacted systems, urgent or not, suggested owner):

1. PM records it in `activity.md` and evaluates impact — is it a task, a risk
   entry, or noise?
2. If it affects another agent's area: PM informs that agent (`DEPENDENCY_UPDATE`)
   or creates a task with a proper contract. The discoverer does **not** wander off
   to fix it — its own task still has a contract to satisfy.
3. Credit flows in the report: discoveries surfaced through the PM are the system
   optimizing itself; discoveries silently self-fixed are scope creep wearing a halo.

## Unresponsive peers

Two distinct cases — a peer still listed but silent, and a peer missing from
`ListAgents` entirely. They need different handling, because only the first can
receive a message.

**Listed but silent** past its contract checkpoint: send one direct question and
record its timestamp — date **and time** — in the task file, subscribe for an
idle notice, then release the assignment if no signal has arrived within
**24 hours of that timestamp** — the deadline is set by the question itself, so
it is always in the future and always checkable against the recorded moment. A listed peer can still receive messages,
so send `CANCEL_TASK` directly **before** returning the task to READY or
reassigning it. Only a peer that is actually absent gets the
pending-cancellation record below.

**Missing from `ListAgents`** (exited or crashed — the human may restart it under
the same name later): no message can reach it, so act on the board instead:

1. Record the staleness where assignments live, never as a task state: mark the
   roster row `STALE (date)` and append the event to the task file. The task
   itself returns to a defined lifecycle state — back to READY (its contract
   still stands), or straight to ASSIGNED if reassigned in the same pass.
2. If the task is urgent, reassign it to a live agent. The task file records the
   ownership change, and the new contract names the branch the previous owner was
   working on, so any landed partial work is inspected via git — not redone blind.
3. Record a **pending cancellation** in the task file. A message cannot be queued
   to an unlisted session, so the record is what survives: the moment the old
   owner reappears in `ListAgents` — or messages the PM first — send `CANCEL_TASK`
   before anything else. That recorded pending cancellation is what stops a
   returning session from resuming work that was reassigned.
4. Note the event for the human's session report.

Never leave a task ASSIGNED to a ghost: by the end of the pass that discovered
the absence, the task is back in READY or reassigned — the `STALE` marker lives
on the roster row and in the task file's history, never in the task's state.

## Mode 2 — teammates and subagents (secondary)

When the PM itself needs ephemeral workers (a one-off investigation, a fresh-context
verification), it may spawn subagents — results return in-process, no protocol
needed. Claude Code's experimental Agent Teams (enabled via
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) additionally offers PM-spawned teammates
with a shared task list and `TeammateIdle`/`TaskCreated`/`TaskCompleted` hook
events. Use teams when the PM owns the whole crew's lifecycle and the feature is
enabled; the board in `.claude/pm/` remains the source of truth either way — a
team's shared task list is team-scoped and does not cover independent peers, who
must remain first-class citizens of this protocol regardless.
