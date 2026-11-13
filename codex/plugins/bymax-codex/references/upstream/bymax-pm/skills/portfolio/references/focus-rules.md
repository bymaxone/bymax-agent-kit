# Focus, check and the WIP limit

The focus is a limit, not a wish. This file is the protocol for `focus` and `check`,
and the classification the `review` measures effort against.

## WIP limit

`config.md` states it. The default is **one product in focus plus one enabling item**.
"Enabling" is work that sits on the dependency path of the focus (below), so it is
counted separately and does not make the focus two products. The limit is set at
`init` and changed only by editing `config.md` through `focus` with a recorded
decision.

## Classification

For a repository (and, for `check`, a described task), against `now.md` and the
dependency map in `portfolio.md`:

| Class | When |
| --- | --- |
| `IN_FOCUS` | the repository belongs to the product in `now.md` |
| `ENABLING` | the repository is a dependency, direct or transitive, of a repository of the focus product (an edge in `portfolio.md` § Dependency map), **and** the task serves the focus deliverable |
| `OUT_OF_FOCUS` | neither |

A dependency of the focus that the task does not serve for the deliverable is
`OUT_OF_FOCUS`: being on the path is necessary, not sufficient. When the repository
is in no product of `portfolio.md`, say it is untracked and classify it
`OUT_OF_FOCUS`.

## `check [task]`

Runs from a worker repository. Steps:

1. Resolve the workspace; stop when none resolves (SKILL.md Step 0).
2. Identify the repository (`git remote get-url origin`, else the directory name)
   and match it to a product in `portfolio.md`.
3. Classify it, using the text after `check` as the task when given. With no task
   text, classify the repository alone and say that the task was not stated.
4. Answer in **one line**: `IN_FOCUS`, `ENABLING (<why, one clause>)` or
   `OUT_OF_FOCUS: the focus is <product>, <deliverable>`.
5. For `OUT_OF_FOCUS` only, offer the two choices on the same line or the next:
   **(a)** proceed, which logs one deviation line, or **(b)** park the task under
   Later in `roadmap.md`. The human chooses; do not choose for them and do not wait
   in a loop.
   - (a) appends to `activity.md`: `YYYY-MM-DD HH:MM check deviation <repo>: <task> (proceeded out of focus)`.
   - (b) adds a line under Later in `roadmap.md`, which is a curated file: say that
     the line is added for the next `review`/`focus` to place, and write it to a new
     inbox file instead of editing `roadmap.md` from a worker session. (Only `init`,
     `focus` and `review` write the curated files.)

`check` never blocks, never edits the worker repository, and is not a hook. It is a
nudge: a gate would be worked around, and the report would then measure the
workaround.

`IN_FOCUS` and `ENABLING` write nothing.

## `focus <product> [reason]`

Runs from the coordination directory. Changes `now.md`.

1. Resolve the product in `portfolio.md`; an unknown name lists the known ones and stops.
2. Read the **current deliverable's ship evidence live** (`references/evidence.md`).
   - `SHIPPED` or a `HUMAN-CONFIRMED` record: the change is allowed without friction.
   - Anything else: **refuse until the human gives a reason**, in their own words, for
     abandoning an unshipped deliverable. A reason you supply yourself is not a reason.
     With one, record it as a decision (below).
3. **Enforce the WIP limit.** Count products that would be in focus after the change.
   Over the limit: refuse and name the product that must leave. The displaced product
   goes to **Next or Frozen, and the human chooses which**. Do not pick.
4. Write, in this order: `now.md` (focus, deliverable, ship type, target, version,
   started today), `roadmap.md` (Now / Next / Later / Frozen, the critical path restated
   in one sentence), `portfolio.md` states, `decisions.md` (a new `DEC-` entry with the
   evidence read in step 2 and the reason), and one `activity.md` line.
5. End by **offering** to start `/bymax-pm:pm` with the new focus as its goal, e.g.
   "Start `/bymax-pm:pm` with the goal: <deliverable>". Offer only; do not start it, do
   not message any agent.

`focus` never runs unattended: the human's reason is part of the protocol, and a
scheduled run that could change it would remove the one control the focus has.

## What changes the focus without `focus`

Nothing. A `review` may report that the focus should change, as its one Decision
needed; the change itself is a `focus` call by the human.
