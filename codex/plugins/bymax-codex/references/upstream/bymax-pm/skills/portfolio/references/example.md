# Worked example

An owner with a backend template and three libraries it consumes, plus one web
product. The coordination directory is `~/work/acme-program/`; the repositories sit
beside it. Every name below is invented.

## 1. `init`

In `~/work/acme-program`, the human runs `/bymax-pm:portfolio init`. The skill asks,
one question at a time, with a recommended answer each time: WIP limit (recommend
`1 + 1`), cadence (`weekly`), language (`en`), discovery source (`~/work`). It reads
five checkouts and proposes:

```
Products (proposed grouping)
  nest-logger        library      shippable   last tag v0.4.0, 3 commits after it
  nest-config        library      building    no tag
  backend-template   template     building    consumes nest-logger, nest-config
  web-console        web product  building    deploys to "production"

Proposed order
  1. nest-logger      critical path: backend-template depends on it, and it is
                      3 commits from a release (git tag --sort and git log, read live)
  2. backend-template enabled by 1
  3. nest-config, web-console later

Recommendation: focus nest-logger 0.5.0, then backend-template.
```

It stops. Nothing is on disk yet. The human approves with one change (`web-console`
frozen). Only then does it write `.claude/portfolio/` and
`~/.claude/bymax-portfolio.json`, and `decisions.md` gets `DEC-001` with the approved
order and the evidence above.

## 2. Three `sync` calls

Monday, in `~/work/nest-logger`: `/bymax-pm:portfolio sync` writes
`inbox/2026-11-16T1812-nest-logger-k3f9.md` and prints `1 file, 4 commits, 1 PR`.
Tuesday, in `~/work/backend-template`, one more. Wednesday, two sessions finish at
the same minute in `nest-logger` and `nest-config`: two files, two different names,
no collision. Each writes nothing in its repository: `git status` stays clean.

## 3. One out-of-focus `check`

Thursday, in `~/work/web-console`, before starting a redesign:
`/bymax-pm:portfolio check redesign the settings page`.

```
OUT_OF_FOCUS: the focus is nest-logger, 0.5.0 published. (a) proceed and log a deviation, or (b) park it under Later.
```

The human chooses (a). One line is appended to `activity.md`:
`2026-11-19 10:02 check deviation web-console: redesign the settings page (proceeded out of focus)`.
Nothing blocked the work.

## 4. A headless `review`

Sunday night a scheduled cloud run starts `/bymax-pm:portfolio review this-week`.
There are no session logs in a cloud run, no human, and the `web-console` checkout
is not on that machine. The run:

- reads four of five repositories with the collector, and the ship read for
  `nest-logger@0.5.0`: `NOT-SHIPPED npm nest-logger@0.5.0` (the PR merged on Wednesday,
  the publish did not happen);
- folds four inbox entries into `activity.md`, then moves them under
  `inbox/folded/2026-W47/`;
- asks nothing and changes no focus.

`reports/2026-W47.md`:

```
## Shipped
none: the one deliverable read (nest-logger@0.5.0) returned NOT-SHIPPED.

## Focus check
nest-logger 11 commits, 4 days (in focus); backend-template 5 commits, 2 days
(enabling); web-console 7 commits, 3 days (out of focus). Commit count is a proxy
for effort, not a measure of it.

## Advanced, not shipped
nest-logger: PR merged Wednesday, version not published; remaining to the deliverable:
the publish. backend-template: 1 PR open.

## Stalled
nest-config: no commit, PR or inbox entry in the period (last: 2026-11-04, a commit).

## WIP
Held on the focus pair. 1 deviation recorded: web-console, 2026-11-19.

## Coverage
web-console: no local checkout on this machine (a cloud run). Activity from asks:
unavailable, no ~/.claude/projects here. gh: ok.

## Decision needed
Effort went to web-console (7 of 23 commits) while nest-logger's release is one
publish away. Options: A) keep the focus and publish nest-logger first
(recommended: it unblocks backend-template); B) move the focus to web-console.
Evidence: the NOT-SHIPPED read above, and the dependency edge backend-template ->
nest-logger.
```

The merged PR is under "Advanced, not shipped", never "Shipped".

## 5. A focus change

Monday the human publishes `nest-logger@0.5.0` and runs
`/bymax-pm:portfolio focus backend-template`. The skill reads the deliverable live:
`SHIPPED npm nest-logger@0.5.0`. The change is allowed without friction. It writes
`now.md`, `roadmap.md`, `portfolio.md` (nest-logger `shipped`), a `DEC-002` entry with
the read as its evidence, and one activity line, then says: "Start `/bymax-pm:pm` with
the goal: backend-template consumes nest-logger 0.5.0 and ships its first release."
It does not start it.

Had the human asked for `web-console` while `0.5.0` was unpublished, the skill would
have refused until they gave a reason for leaving the deliverable unshipped, and
would have recorded that reason as the decision. Had the move made two products in
focus beyond the limit, it would have refused and named the one that must leave.

## 6. A two-lane week

Two workstreams, declared in `config.md`: **lane A** (Platform, owner `laptop-1`,
limit 1 + 1) and **lane B** (Apps, owner `alice`, limit 3). Every product has
`Lane:`. Every name is invented, and the owners are whatever `config.md` says.

`now.md` holds two blocks. Lane B's focus is the set `app-one, app-two, app-three`,
one deliverable: the three apps in the stores, in that order.

- `focus B +app-four` is refused: the set would be four products against lane B's
  limit of three, and the answer names the limit. `focus A app-two`, where `app-two`
  belongs to lane B, is refused and offers `lanes move`. Changing lane B's focus
  leaves lane A's block byte for byte as it was.
- Tuesday, in a session set to lane B (`lanes use B`), the work opens
  `platform-template` (lane A) and runs `check fix the logger import`:

  ```
  OTHER_LANE: this repository belongs to lane A (Platform), this session works for lane B (Apps). (a) proceed and log a deviation, or (b) park it under Later.
  ```

  They proceed; one line names both lanes in `activity.md`. `sync` there writes
  `Lane: B` and `Owner lane: A` in the inbox file.
- Sunday's unattended `review` writes the per-lane sections. Lane B: `app-one` and
  `app-two` have `HUMAN-CONFIRMED` store records, `app-three` does not: "2 of 3
  shipped", not Shipped. WIP held in both lanes, each against its own limit.
  Cross-lane lists one dependency (`app-two` waits on lane A's `platform-template`
  release) and one ownership mismatch (the Tuesday inbox file). It asks nothing and
  changes no focus.

**The same two lanes from a single machine, no lane set.** With no
`$BYMAX_PORTFOLIO_LANE` and no `lane` in the pointer file, `check` and `sync` take the
lane from the repository: in a lane B repository the session works for lane B, in a
lane A repository for lane A, and `OTHER_LANE` is never answered. Nothing needs setting up.
