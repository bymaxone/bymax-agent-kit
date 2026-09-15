# 🧭 Bymax Workflow

> Phased planning + execution workflow for Claude Code, with explicit user-approval gates and JIRA-style task dashboards.

## Install

```bash
claude plugin marketplace add bymaxone/bymax-claude-code
claude plugin install bymax-workflow@bymax-claude-code
```

## What you get

### Slash commands

| Command         | Layer | Purpose                                                                                         |
| --------------- | ----- | ----------------------------------------------------------------------------------------------- |
| `/bymax-workflow:spec`         | 1     | Draft a complete technical spec — goal, scope, user stories, success criteria, risks.            |
| `/bymax-workflow:roadmap`      | 2     | Take an approved spec → phased plan with status dashboard, dependency DAG, definition-of-done. |
| `/bymax-workflow:phase-tasks`  | 3     | Take an approved roadmap → JIRA-style task files with self-contained agent prompts per task.   |
| `/bymax-workflow:task`         | exec  | Execute a phase or single task with `/bymax-workflow:verify` → `/security-review` → `/bymax-quality:code-review` chain.     |
| `/bymax-workflow:brainstorm`   | pre   | Refine vague ideas, explore alternatives, surface tradeoffs.                                    |
| `/bymax-workflow:plan`         | mini  | Lightweight plan for single-PR work that doesn't need the full chain.                           |
| `/bymax-workflow:verify`       | post  | 5-gate verification: static checks, exercise, root-cause, regression scan, acceptance criteria. `quick` = Gate 1 only. |
| `/bymax-workflow:checkpoint`   | util  | Snapshot SHA + tests + coverage for later comparison.                                            |

### Skills

- **`standards`** — universal coding rules with **TypeScript and Rust tracks** (type/lint discipline, JSDoc / rustdoc policy, naming, layered architecture, English-only comments, suppression bans, conventional commits). Loaded on demand by `/bymax-workflow:plan`, `/bymax-quality:tdd`, `/bymax-quality:code-review`, `/bymax-bootstrap:bootstrap`, etc.
- **`autopilot`** — the **loop-engineering executor**: autonomously drives an approved roadmap from first phase to done, **one phase per PR**, with zero human interaction after launch. An orchestrator session spawns one isolated implementer sub-agent per phase (git worktree, model picked per a per-phase policy), waits for CI + the review bot via background signals, triages findings and fixes confirmed blockers, merges only after a full merge-gate conjunction + grace window, updates the dashboards, and chains the next phase. Per-project parameters live in `docs/AUTOPILOT.md` (`/bymax-workflow:autopilot init` generates it from the roadmap and stops for your review). Requires an authenticated `gh` CLI.

## The flow

```
/bymax-workflow:spec         →  docs/specs/<feature>.md         (the WHAT and WHY)
   ⏸ user approval
/bymax-workflow:roadmap      →  docs/plans/<feature>-plan.md    (phased master plan + dashboard + DAG)
   ⏸ user approval
/bymax-workflow:phase-tasks  →  docs/tasks/phase-NN-*.md        (per-phase task files)
   ⏸ user approval per phase
/bymax-workflow:task         →  /bymax-workflow:verify → /security-review → /bymax-quality:code-review → completion-protocol
   ⏸ user reviews diff
commit (Conventional Commits — never auto-committed)
```

Each layer **stops and waits** — you review, modify, or approve. Nothing auto-chains.

## The autonomous flow (loop engineering)

Once the planning docs are approved, `autopilot` inverts the contract: **approval is given once, at launch**, and the loop owns everything after it.

```
/bymax-workflow:autopilot init   →  docs/AUTOPILOT.md   (per-project config — REVIEWED BY YOU)
   ⏸ user approval (the last one)
/bymax-workflow:autopilot        →  for each phase, sequentially:
      spawn implementer (isolated worktree, model per policy)
        → implementer: tasks + gates + /bymax-quality:code-review + security verification with confirmed blockers resolved → PR
      orchestrator: background CI/review watch → fix findings → merge gate + grace window
        → squash-merge + branch deletion (with proof) → dashboards → next phase
   🔁 until every phase is ✅ (or a precondition blocks — then it stops cleanly and tells you)
```

The architecture (orchestrator vs implementer split, one-implementer-at-a-time memory safety, anti-hallucination verification) is documented in the skill's [operational playbook](./skills/autopilot/references/operational-playbook.md) — every rule names the real failure it prevents.

## Status legend (used in every roadmap and task file)

| Emoji | Meaning      |
| ----- | ------------ |
| 📋    | ToDo         |
| 🔄    | In Progress  |
| 👀    | Review       |
| ✅    | Done         |
| ⛔    | Blocked      |
| 🟡    | Partial      |

## When to use this vs `/bymax-workflow:plan` alone

- **Big feature, multi-phase, multiple PRs** → use the chain (`/bymax-workflow:spec` → `/bymax-workflow:roadmap` → `/bymax-workflow:phase-tasks` → `/bymax-workflow:task`).
- **Whole roadmap, hands-off** → the chain above for planning, then `/bymax-workflow:autopilot` to execute every phase autonomously (one PR per phase, merge-gated).
- **Small task, single PR, clear scope** → just use `/bymax-workflow:plan` → `/bymax-quality:tdd` → `/bymax-workflow:verify` → `/bymax-quality:code-review`.

## License

MIT — see [root LICENSE](../../LICENSE).
