# Focus, check and the WIP limit

The focus is a limit, not a wish. This file is the protocol for `focus` and `check`,
and the classification the `review` measures effort against.

## WIP limit

`config.md` states it. With lanes declared, each lane has its own limit (products in
its focus set, and enabling items), and every rule below applies **per lane**; with no
lanes table there is one implicit lane and the text reads as written. The default is
**one product in focus plus one enabling item**.
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
| `OTHER_LANE` | lanes are declared, this session works for a lane (set explicitly), and the repository is owned by another lane |

Lanes are applied in two steps. **Ownership first:** the repository's owner lane is
its product's lane; a repository owned by another lane than the one this session works for is
`OTHER_LANE`, whatever else is true. With no lane set, the session works for the
repository's own lane, so `OTHER_LANE` is never answered. **Then inside the owner lane:** the rows above,
read against **that lane's** focus set in its block of `now.md` and the dependency
map. Effort in `review` is classified the same way: a commit is measured against
**its repository's owner lane focus**, never against a global one.

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
4. Answer in **one line**: `IN_FOCUS`, `ENABLING (<why, one clause>)`,
   `OUT_OF_FOCUS: the focus is <product>, <deliverable>` or, when the lane this session
   works for differs from the repository's, `OTHER_LANE: this repository belongs to lane A
   (Platform), this session works for lane B (Apps)`. With no lane set, say that the
   repository's owner lane was used.
5. For `OUT_OF_FOCUS` and `OTHER_LANE`, offer the two choices on the same line or the next:
   **(a)** proceed, which logs one deviation line, or **(b)** park the task under
   Later in `roadmap.md`. The human chooses; do not choose for them and do not wait
   in a loop.
   - (a) appends to `activity.md`: `YYYY-MM-DD HH:MM check deviation <repo>: <task> (proceeded out of focus)`. For `OTHER_LANE` the line names both lanes: `... (proceeded in another lane: session B, repository A)`.
   - (b) adds a line under Later in `roadmap.md`, which is a curated file: say that
     the line is added for the next `review`/`focus` to place, and write it to a new
     inbox file instead of editing `roadmap.md` from a worker session. (Only `init`,
     `focus` and `review` write the curated files.)

`check` never blocks, never edits the worker repository, and is not a hook. It is a
nudge: a gate would be worked around, and the report would then measure the
workaround.

`IN_FOCUS` and `ENABLING` write nothing. `OTHER_LANE` is a nudge too: it answers in
one line and does not block.

## `focus [<lane>] <product>[,<product>...] [reason]`

Runs from the coordination directory. Changes **one lane's block** of `now.md`.

1. Resolve the lane. With lanes declared and no lane argument, **refuse and list the
   lanes**; with none declared the lane is `default` and is never named. Pull and
   rebase the coordination repository first (`references/workspace.md` § Lanes); a
   conflict in a curated file is reported, not resolved.
2. Resolve every product in `portfolio.md`; an unknown name lists the known ones and
   stops. The new focus is the set given. `+<product>` adds one to the lane's current
   set and `-<product>` removes one; both are first-class.
3. **Ownership.** Every product must belong to the lane. If one belongs to another
   lane, refuse and offer `lanes move`; never move it silently. A product already in
   **another lane's** focus is refused too, naming that lane.
4. Read the **current deliverable's ship evidence live** (`references/evidence.md`)
   for each product the change drops or replaces.
   - `SHIPPED` or a `HUMAN-CONFIRMED` record: the change is allowed without friction.
   - Anything else: **refuse until the human gives a reason**, in their own words, for
     abandoning an unshipped deliverable. A reason you supply yourself is not a reason.
     With one, record it as a decision (below).
5. **Enforce the lane's WIP limit.** Count the products that would be in the lane's
   focus after the change. Over the limit: refuse, name the limit and the product that
   must leave. The displaced product goes to **Next or Frozen, and the human chooses
   which**. Do not pick.
6. Write, in this order: the lane's block of `now.md` (focus set, deliverable, ship
   type, target, version, started today) and **no other lane's block, which stays
   byte for byte unchanged**, then `roadmap.md` (Now / Next / Later / Frozen, the
   critical path restated in one sentence), `portfolio.md` states, `decisions.md` (a
   new `DEC-` entry with the evidence read in step 4, the reason and `Lanes:`), and
   one `activity.md` line.
7. End by **offering** to start `/bymax-pm:pm` with the new focus as its goal, e.g.
   "Start `/bymax-pm:pm` with the goal: <deliverable>". Offer only; do not start it, do
   not message any agent.

A deliverable made of several products is one deliverable: it is **shipped** only
when every product in the set has its ship evidence (`references/evidence.md`), and
dropping one unshipped product from the set needs the human's reason like any other
abandonment.

`focus` never runs unattended: the human's reason is part of the protocol, and a
scheduled run that could change it would remove the one control the focus has.

## What changes the focus without `focus`

Nothing. A `review` may report that the focus should change, as its one Decision
needed; the change itself is a `focus` call by the human.
