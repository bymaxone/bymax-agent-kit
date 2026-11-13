# Workspace

The portfolio lives in the **coordination directory** the `bymax-pm` README already
prescribes: a directory above the repositories, never inside a worker repository,
next to `.claude/pm/`. Commit it to git if you want it versioned; it holds no secrets.

## Layout

```
.claude/portfolio/
  config.md         owner, WIP limit, repository discovery source, review cadence, report language, optional lanes table
  portfolio.md      one entry per product, plus the repository dependency map
  now.md            the current focus (one block per lane when lanes are declared): product(s), next deliverable, its ship evidence, started date
  roadmap.md        Now / Next / Later / Frozen, with the critical path stated
  done.md           the definition of done per ship type (the read lives in evidence.md)
  decisions.md      append-only, same entry format as the PM's decision log
  activity.md       append-only, one dated line per state change
  inbox/            one file per `sync`, never edited after it is created
  reports/          one file per `review`, named by ISO week (YYYY-Www.md)
```

`init` creates exactly these. A `review` also uses `.claude/portfolio/.run/` as
scratch and removes it when it ends; it is never part of the record.

### `portfolio.md`

One entry per product:

```
## <product>
Stage:        idea | building | shippable | shipped | maintained
Repositories: <name> (<absolute local path or "no checkout">, <owner/repo>)
Next deliverable: <one sentence>
Ship type:    npm | github-release | deployment | store-build
Ship target:  <package name | owner/repo + tag | owner/repo + environment (+ health URL) | store track>
Ship version: <the version or tag the deliverable names, empty until decided>
Depends on:   <product or repository, comma separated>
State:        in-focus | next | later | frozen | shipped
Lane:         <lane id>   (required when lanes are declared; omitted otherwise)
```

A repository belongs to the lane of the product that lists it. A repository in no
product is `UNASSIGNED`.

Below the entries, `## Dependency map`, one edge per line, in the shape
`pm/references/multi-repo.md` describes:

```
backend-template -> nest-logger, nest-config
```

There is one map, not two.

### Lanes

`config.md` may carry a lanes table. **No table means one implicit lane `default`
with the WIP limit already in `config.md`, and everything in this directory reads as
it did before lanes existed.**

```
## Lanes
| Lane | Name     | Owner (optional) | WIP limit (products) | Enabling limit |
| ---- | -------- | ---------------- | -------------------- | -------------- |
| A    | Platform | laptop-1         | 1                    | 1              |
| B    | Apps     | alice            | 3                    | 0              |
```

A lane's focus is a **set of products** that together make one deliverable, within
that lane's WIP limit. A product is in at most one lane's focus, and in exactly one
lane.

### Which lane is this session working for

First hit wins, and the skill says which one it used:

1. `$BYMAX_PORTFOLIO_LANE`
2. `"lane"` in `~/.claude/bymax-portfolio.json` (`{"dir": "...", "lane": "B"}`), written by `init` or `lanes use`
3. none: `sync` and `check` use the current repository's owner lane and say so;
   `status` shows all lanes. This is the normal path for one machine running several
   lanes, and it never produces `OTHER_LANE`.

A lane id that is not in the lanes table is a miss that says so, never a guess.
The owner column is free text read from `config.md`; nothing else in this skill names one.

### `now.md`

Without lanes, one block:

```
Focus:        <product> (+ <enabling item>)
Deliverable:  <the next deliverable, one sentence>
Ship type:    <as in portfolio.md>
Ship target:  <as in portfolio.md>
Ship version: <as in portfolio.md>
Started:      YYYY-MM-DD
```

With lanes, one block per lane, each in the same field format, and `Focus:` lists
the set:

```
## Lane A
Focus:        platform-template (+ enabling: shared-lib)
Deliverable:  ...
Ship type:    github-release
Ship target:  owner/repo
Ship version: v1.0.0
Started:      YYYY-MM-DD

## Lane B
Focus:        app-one, app-two, app-three
Deliverable:  the three apps published in the stores, in this order: app-one, app-two, app-three
Ship type:    store-build
Ship target:  per product, in portfolio.md
Ship version:
Started:      YYYY-MM-DD
```

A write for one lane edits **only that lane's block**, so two sessions changing
different lanes on the same day merge cleanly.

### Entry formats

`decisions.md` uses the PM's entry shape (`pm/references/escalation.md` § Decision
log), numbered `DEC-001` upward in this file's own sequence:

```
## DEC-001 — 2026-11-13 — <decision in one line>
Context:    <why it came up>
Options:    A) ... B) ...
Decision:   <chosen>
Rationale:  <the evidence>
Approved:   <the human, with the date>
Affects:    <products>
Lanes:      <ids>   (only when lanes are declared)
Revisit if: <the condition that reopens it>
```

`activity.md`: `YYYY-MM-DD HH:MM <actor> <verb> <subject> (<proof>)`, one line each.
With lanes the actor carries its lane: `<actor>[B]`.

## Writers

| File | Written by |
| --- | --- |
| `config.md`, `portfolio.md`, `now.md`, `roadmap.md`, `done.md` | `init`, `focus`, `review`, and `lanes` (its changing forms only, after confirmation). No other mode. |
| `decisions.md`, `activity.md` | the three above, and `check` (a deviation line in `activity.md` only) |
| `inbox/<file>` | `sync` only, one new file per call, never edited afterwards |
| `reports/<week>.md` | `review` only |

There is one writer at a time for every curated file; with lanes, one writer at a
time for every lane's block of `now.md`. `sync` runs from *other*
sessions in worker repositories, which is why it writes only a **new file with a
unique name** and nothing else: two sessions can never collide, and `review` is the
one consumer that folds the inbox into the curated files.

Sessions on several machines may write the same coordination repository. `focus`, `lanes` and the
writing part of `review` run `git pull --rebase` on it first when it is a git
checkout, and **refuse on a conflict in a curated file, reporting it instead of
resolving it**. `sync` keeps writing one uniquely named inbox file, so it never
conflicts.

## Locating the workspace

`sync`, `check` and `status` run from inside a worker repository, so they find the
coordination directory without guessing. First hit wins, and the skill states which:

1. `$BYMAX_PORTFOLIO_DIR`
2. `~/.claude/bymax-portfolio.json` with `{"dir": "<absolute path>"}`, written by `init`
3. the current directory, only when it contains `.claude/portfolio/`

A hit counts only when `<dir>/.claude/portfolio/config.md` exists. A pointer that
names a directory without it is a miss that says so ("the pointer names X, which has
no workspace"), not a reason to fall through silently to a guess.

None found: say so, name the two settings, and stop. Never create a workspace inside
a worker repository.

The same resolution as shell, for any block that needs the directory. It assigns
everything it reads and prints the directory or fails:

```bash
PDIR=$(python3 -c 'import json, os; p = os.path.expanduser("~/.claude/bymax-portfolio.json"); print(os.environ.get("BYMAX_PORTFOLIO_DIR") or (json.load(open(p)).get("dir", "") if os.path.exists(p) else "") or (os.getcwd() if os.path.isfile(".claude/portfolio/config.md") else ""))')
if [ -z "$PDIR" ] || [ ! -f "${PDIR}/.claude/portfolio/config.md" ]; then
  echo "No portfolio workspace: set BYMAX_PORTFOLIO_DIR, or write {\"dir\": \"<absolute path>\"} to ~/.claude/bymax-portfolio.json." >&2
  exit 1
fi
echo "$PDIR"
```

## Recovery

The workspace is files, so recovery is reading them. A new session reads `config.md`,
`now.md`, `portfolio.md` and the newest `reports/` file, then the inbox entries not
under `inbox/folded/`. Where a curated file and git/GitHub disagree, the repository
wins and the disagreement is reported, not silently overwritten: `review` re-derives
every state from a read, and `now.md` is only the intent.

An interrupted `review` leaves `.run/` behind and possibly a partly folded inbox.
Folding moves a file only after its summary line is in `activity.md`, so a rerun
folds what remains and never duplicates a line: check `activity.md` for the entry's
file name before appending.
