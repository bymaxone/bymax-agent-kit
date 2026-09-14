# Autopilot Config Template

`init` mode copies this structure to **`docs/AUTOPILOT.md`** in the target
repo and fills it from the roadmap, the task files, and `CLAUDE.md`. The
config is the **only per-project artifact** autopilot needs — everything
else (architecture, merge gate, worktree discipline) is invariant and lives
in the skill. Keep it declarative and complete: an orchestrator must be able
to run the whole chain from this file plus the planning docs, with no other
context.

Sections marked *(optional)* may be omitted when empty. Everything else is
required.

---

```markdown
# Autopilot Config — <project-name>

> Per-project parameters for /bymax-workflow:autopilot. Reviewed and
> approved by the operator before the first run. The planning docs own WHAT
> to build; this file owns HOW the chain runs.

## Identity

- **Project root**: /absolute/path/to/repo
- **GitHub repo**: owner/name (visibility: public | private)
- **Default branch**: main
- **Product summary** (2–4 lines): what this repo is, in the words the
  implementer needs. Name the stack and the one defining constraint.
- **Roadmap file**: docs/plans/<feature>-plan.md (or docs/DEVELOPMENT_PLAN.md)
- **Tasks index**: docs/tasks/README.md
- **Phases**: N phases / M tasks (phase files docs/tasks/phase-NN-*.md)

## External preconditions

<!-- Each row: when it applies, the exact check command, and what to do on
     failure (STOP is the default — autopilot never polls external events). -->

| Applies to | Check (exit 0 = OK) | On failure |
|---|---|---|
| launch | `docker info` | STOP — operator starts Docker |
| phases 1+ | `npm view <package> version` | mark phase ⛔ blocked on publication, STOP |

## Model policy

<!-- inherit = the orchestrator's model (the strong tier). Give each row a
     one-line rationale so the policy survives review. Fix sub-agents always
     escalate to inherit when a phase stalls on review/CI findings. -->

| Phase | Model | Rationale |
|---|---|---|
| 0 | sonnet | mechanical scaffold on a fully specified checklist |
| 1 | inherit | first contact with the consumed library — invented APIs are the failure mode |
| … | … | … |

**Heavy phases** (silent-death watch widened to ~120 min): <list phase
numbers whose gates pull container images, install browsers, or run
mutation testing>.

## Gates

<!-- The CI pipeline grows by phase. List the local gate commands the
     implementer must pass, and from which phase each becomes active.
     Job names become contractual once branch protection references them. -->

| Gate (local command) | Active from |
|---|---|
| `pnpm lint && pnpm typecheck && pnpm format:check` | phase 0 |
| `pnpm --filter api test` (coverage threshold in config) | phase 2 |
| `pnpm --filter api test:e2e` (needs Docker) | phase 5 |

**Expected-skip CI checks** *(optional)*: checks that report `skipping` and
count as pass (e.g. visibility-gated workflows while the repo is private).

## Invariant greps *(optional)*

<!-- Mechanically checkable project rules — each command must print nothing.
     These go into every implementer's phase-wide gate run. -->

```bash
grep -rn "process.env" src/ --include='*.ts' | grep -v env.schema.ts
```

## Security invariants & review focus

<!-- From the spec's security section. What /security-review and
     /bymax-quality:code-review must pay special attention to, phrased as
     auditable statements. Also list per-phase focus for the phases the
     model policy marks security-sensitive. -->

- <invariant 1 — e.g. "signed URLs are credentials: never logged, masked in
  every UI/error surface">
- <invariant 2>

## Review bot

- **Reviewer**: `copilot-pull-request-reviewer[bot]` (request with
  `gh pr edit <PR#> --add-reviewer copilot-pull-request-reviewer[bot]`)
  — or `none` (merge gate falls back to CI + whatever reviews exist).
- **Review-bot timeout**: 15 minutes — a request pending this long with no
  review submitted is treated as bot-unresponsive: the request is removed,
  a factual PR comment records it, and the gate proceeds CI-only (the
  implementer's zero-findings review floor already ran before the PR).

## Merge policy

- **Method**: squash (delete branch on merge — always)
- **Grace window**: 5 minutes since last push
- **Review-bot timeout**: 15 minutes (see Review bot above)
- **Stall limit**: 3 full fix cycles on the same phase → 🟡/⛔ + notify + STOP

## Custom conventions *(optional)*

<!-- Anything the implementer must honor beyond /bymax-workflow:standards
     and CLAUDE.md — e.g. "the web app imports only the ./shared subpath",
     "design-system files are verbatim copies from <sibling>, do not edit". -->
```
