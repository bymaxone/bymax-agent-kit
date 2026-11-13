# bymax-pm

Engineering Project Manager for multi-agent development, and the portfolio layer above
it. One Claude Code session —
the PM — coordinates independent Claude Code peer sessions across repositories:
structured task contracts, evidence-based completion, independent review, blocker
resolution, and a persistent board that survives restarts. The human talks to the
PM; the PM manages the system.

Built on Claude Code's native cross-session messaging (`ListAgents` /
`SendMessage`, including one-shot idle notifications). No daemon, no database, no
custom transport: state is markdown in `.claude/pm/`, evidence is git/GitHub.

## Install

```bash
# marketplace (once per machine, if not already added)
claude plugin marketplace add bymaxone/bymax-agent-kit
claude plugin install bymax-pm@bymax-agent-kit
```

Per-project instead of global: `claude plugin install` is user-wide regardless of
where it runs, so the genuinely project-scoped path is copying `skills/pm/` into
`<coordination-dir>/.claude/skills/pm/` — the coordination directory the PM session
runs from (step 1 below), never a worker's repository; project-level skills need no
plugin. Verify the plugin install with `claude plugin list`, or the copied skill by
typing `/pm` in a session started there.

### Also in Codex

The same procedures ship in the Codex package as `bymax-pm` (namespaced `bymax-codex:<name>`). Install it with `./scripts/install-codex.sh` from a checkout — see [CODEX.md](../../CODEX.md) for the entrypoints and the capability boundaries, which are not full parity.

## Set up the topology

1. **Pick a coordination directory** for the PM — a workspace folder *above* your
   repositories (not inside a worker's repo), e.g. `~/work/acme-program/`. The PM
   creates `.claude/pm/` (board, task files, roster, decisions, activity log)
   there. Commit it to git if you want the board versioned — it contains no secrets.
2. **Start the PM session** there, with a name:

   ```bash
   cd ~/work/acme-program
   claude --name pm
   ```

   Then invoke `/bymax-pm:pm` (or just tell it to act as PM — the skill
   description lets Claude load it from natural language).
3. **Start each worker session** in its own terminal, in its own repo, with a
   meaningful name — the name is the address the PM delegates to:

   ```bash
   cd ~/work/nest-logger        && claude --name nest-logger
   cd ~/work/backend-template   && claude --name backend-template
   cd ~/work                    && claude --name reviewer
   ```

   Workers need nothing installed — the PM's messages carry their own reply
   instructions. An already-running unnamed session can join with `/rename <name>`.
4. **Talk to the PM.** Give it goals ("prepare nest-logger for the new
   observability package"), ask `status`, `standup`, or `release-check`. It
   discovers the workers with `ListAgents`, delegates, verifies, and reports.

## Resume after a restart

Start the PM the same way in the same directory (`claude --name pm`, or resume the
previous session) and invoke `/bymax-pm:pm`. The startup routine reloads
`.claude/pm/`, reconciles it against the repositories and the currently live
agents, re-subscribes idle notices, and continues — the board, not the previous
conversation, is the source of truth. Workers that died can be restarted under the
same names at any time.

## Portfolio layer

`/bymax-pm:portfolio` sits above the PM. The PM delivers one program with several
agents; the portfolio decides **which product gets the attention this week** and
reports, from evidence, whether the work lands there and whether anything shipped.
It exists for the owner of many repositories who can push to most of them in a week
and release almost nothing.

| Level | Question | Owner |
| --- | --- | --- |
| **Portfolio** | Which product is in focus? What is frozen? Did anything ship? | `/bymax-pm:portfolio` |
| Program | How do I deliver the current focus with several agents? | `/bymax-pm:pm` |
| Project | What is the spec, roadmap and phase plan of one product? | `bymax-workflow`, `/bymax-workflow:autopilot` |
| Repository | What shipped this week in one repository? | `/bymax-report:standup` |

**Setup.** It uses the coordination directory from step 1 above, next to `.claude/pm/`:
it keeps `.claude/portfolio/` there (focus, product map, decisions, an inbox, one report
per week). Run `/bymax-pm:portfolio init` from that directory; it interviews you, proposes
a priority order with a recommendation, and writes nothing before you approve. `init`
also writes `~/.claude/bymax-portfolio.json` so a session in any worker repository can
find the workspace (or set `BYMAX_PORTFOLIO_DIR`).

**The `sync` habit.** At the end of each development session, run
`/bymax-pm:portfolio sync` in that repository. It writes one new file under
`inbox/` and nothing else, so two sessions finishing together never collide. Before
starting something, `/bymax-pm:portfolio check <task>` says in one line whether it is
in focus; it never blocks.

**Scheduling `review`.** `review` writes the weekly report and is safe to run
unattended: it asks nothing and changes no focus. Schedule it weekly, for example as a
Claude Code routine started from the coordination repository. A cloud run has no
local session logs and no local checkouts of repositories that were not cloned there;
the report names every repository it could not read under Coverage instead of
counting it as quiet. It needs `bymax-report` installed beside `bymax-pm` (it reuses
that plugin's collector) and, for the ship reads, authenticated `gh` and `npm`.

Only a verified release counts as shipped: a published package version, a deployment,
a tagged release, or a store build you confirmed yourself. Merged PRs and green CI are
progress and are reported separately. The skill never edits a worker repository and never
messages agents; it offers to start `/bymax-pm:pm` on the new focus and leaves that to you.

## Requirements

- Claude Code with cross-session messaging (2.1.236+ for idle notifications).
- `git` always; `gh` authenticated wherever verification reads PRs or CI — Gate 3,
  startup reconciliation, and `release-check` depend on it. Without `gh` the PM must
  report those checks as unverifiable, never assume them green.
- Optional: Agent Teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) if you want the
  PM to also spawn managed teammates; independent peer sessions work without it.

## What's inside

```
skills/pm/SKILL.md            → /bymax-pm:pm [status|standup|release-check]; the five laws,
                                 the operating loop, boundaries
skills/portfolio/SKILL.md     → /bymax-pm:portfolio [init|status|check|sync|review|focus]; the five
                                 laws, the modes, the boundaries
skills/portfolio/references/
  workspace.md                → .claude/portfolio/ layout, writers, locating it, recovery
  review.md                   → the weekly review: inputs, seven sections, folding, unattended rules
  focus-rules.md              → WIP limit, the check classification, the focus-change protocol
  evidence.md                 → what counts as shipped and the read that proves it
  example.md                  → an end-to-end week
skills/pm/references/
  peer-protocol.md            → discovery, message types, idle notices, stuck peers
  task-contract.md            → contract template, acks, risk & priority models
  lifecycle.md                → state machine, quality gates, evidence, release readiness
  escalation.md               → blockers, disagreements, decision log, human escalation
  reporting.md                → status / standup / release formats, health criteria
  persistence.md              → .claude/pm/ layout, startup, handoff, failover
  multi-repo.md               → dependency DAG, collisions, parallelization, Gate 5
  example.md                  → end-to-end worked scenario
```

Pairs naturally with the rest of the toolkit: workers can use
`/bymax-quality:code-review` as their review gate and `/bymax-pr:push` to ship —
the PM treats those as evidence like any other.
