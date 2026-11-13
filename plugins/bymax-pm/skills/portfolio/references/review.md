# The weekly review

`review [period]` is the core mode. It reads every repository in `portfolio.md`, folds
the inbox, and writes `reports/YYYY-Www.md`. It must run with nobody present.

## Unattended rules

A scheduled run has no human to answer. So, in an unattended run:

- **Never ask a question.** Not to confirm the period, not to resolve an ambiguity.
  Pick the documented default and record that you did.
- **Never change the focus.** `now.md` and `roadmap.md` order are read, not edited,
  except for the state changes `Folding` below allows (a `shipped` state with its proof).
- Write the full report, put any decision in section 7, and end.

In an interactive run the same report is written first; only then may the one
"Decision needed" be put to the human as a question with its options.

How to tell: you are unattended when the run was started by a scheduled task or a
routine, or when the prompt says so. When unsure, behave as unattended; asking in a
run nobody reads stalls it, and the report is complete either way.

## Period

`[period]` takes the spellings the standup collector does (`last-week`, `this-week`,
`<n>d`, `YYYY-MM-DD..YYYY-MM-DD`). The default is `last-week`, the previous Monday
through Sunday, and the report file is named for the ISO week of the period's last
day. A review of a period whose report already exists writes
`YYYY-Www-2.md`, `-3.md` and so on; a report is never overwritten.

## Inputs

Per repository in `portfolio.md`:

1. **The standup collector**, not a second one. Locate it next to this plugin:

   ```bash
   COLLECT=$(ls -d "${CLAUDE_PLUGIN_ROOT}"/../../bymax-report/*/scripts/collect.py 2>/dev/null | sort -V | tail -n 1)
   if [ -z "$COLLECT" ]; then
     echo "bymax-report is not installed beside bymax-pm, so the collector is missing." >&2
     echo "Install it: claude plugin install bymax-report@bymax-agent-kit" >&2
     exit 1
   fi
   echo "$COLLECT"
   ```

   Missing collector: every repository goes to Coverage as "activity unread: the
   collector (`bymax-report`) is not installed"; the ship reads and the inbox still run.

2. **The folded inbox** for the period (`inbox/`, not `inbox/folded/`).
3. **Ship evidence** per deliverable (`references/evidence.md`).

### Running the collector

Write the period to `.claude/portfolio/.run/period.txt` and one absolute repository
path per line to `.claude/portfolio/.run/repos.txt` with the file tool (a product with
no local checkout is not in that list; it goes to Coverage). Then run:

```bash
PDIR=$(python3 -c 'import json, os; p = os.path.expanduser("~/.claude/bymax-portfolio.json"); print(os.environ.get("BYMAX_PORTFOLIO_DIR") or (json.load(open(p)).get("dir", "") if os.path.exists(p) else ""))')
if [ -z "$PDIR" ]; then
  echo "No portfolio workspace: set BYMAX_PORTFOLIO_DIR or write ~/.claude/bymax-portfolio.json." >&2
  exit 1
fi
RUN="${PDIR}/.claude/portfolio/.run"
COLLECT=$(ls -d "${CLAUDE_PLUGIN_ROOT}"/../../bymax-report/*/scripts/collect.py 2>/dev/null | sort -V | tail -n 1)
PERIOD=$(sed -n 1p "${RUN}/period.txt")
if [ -z "$COLLECT" ] || [ -z "$PERIOD" ] || [ ! -f "${RUN}/repos.txt" ]; then
  echo "Missing the collector, the period or the repository list: see Inputs." >&2
  exit 1
fi
mkdir -p "${RUN}/collect"
: > "${RUN}/collect/status.tsv"
N=0
while IFS= read -r REPO || [ -n "$REPO" ]; do
  N=$((N + 1))
  if [ ! -d "$REPO/.git" ] && [ ! -f "$REPO/.git" ]; then
    printf '%s\t%s\t%s\n' "$N" "$REPO" "no-checkout" >> "${RUN}/collect/status.tsv"
    continue
  fi
  if python3 "$COLLECT" --repo "$REPO" --period "$PERIOD" --out "${RUN}/collect/${N}.json" > /dev/null 2>"${RUN}/collect/${N}.err"; then
    printf '%s\t%s\t%s\n' "$N" "$REPO" "ok" >> "${RUN}/collect/status.tsv"
  else
    printf '%s\t%s\t%s\n' "$N" "$REPO" "failed" >> "${RUN}/collect/status.tsv"
  fi
done < "${RUN}/repos.txt"
cat "${RUN}/collect/status.tsv"
```

Read `status.tsv`, then each `collect/<N>.json` whole (one record per line). A
`failed` row's reason is in `collect/<N>.err`; read it and put it under Coverage.
In a cloud run there are no `~/.claude/projects` session logs, so `requests` is
empty there and `coverage.claude` says so: the report states that PROGRESS from
asks is unavailable, and builds every other section from commits, pull requests
and the inbox.

## Output: `reports/YYYY-Www.md`

Sections, in this order, with these headings. Omit nothing; a section with
nothing to say says "none" and why.

1. **Shipped.** Deliverables with verified ship evidence, each with its proof: the
   `SHIPPED` line from `evidence.md`, or the `HUMAN-CONFIRMED` record with its date.
   A line without a proof does not appear.
2. **Focus check.** Per product: its share of the period's commits and the number of
   days with a commit, split into in focus, enabling and out of focus
   (`references/focus-rules.md` § Classification). Count commits from `collect.json`
   `commits` by their `date`, once per commit even when it appears on several refs.
   State the metric and its limit in one sentence: commit count is a proxy for
   effort, not a measure of it, and a squash-merge hides how many commits a change was.
3. **Advanced, not shipped.** Products with progress and no ship evidence: merged PRs
   (`prs` with `shipped` true), open PRs, and for the focus product what remains to
   its next deliverable, from `now.md` against the reads. A merged PR with no release
   is here and never in section 1.
4. **Stalled.** Products whose state is `in-focus` or `next` with no commit, PR or
   inbox entry in the period. Name the last activity found and its date.
5. **WIP.** Whether the limit held: the number of products with activity classified in
   focus plus enabling against the limit in `config.md`, and every deviation line
   `check` recorded in `activity.md` in the period.
6. **Coverage.** Every repository that could not be read, named with the reason: no
   local checkout, no access, `gh` missing or signed out, collector missing or failed,
   no session logs in a cloud run, a ship read that came back `UNREAD`. A gap is
   reported, never hidden and never read as "no activity".
7. **Decision needed.** At most one: the options, a recommendation, and the evidence
   for it. With none, the section says "none". Candidates, strongest first: a focus
   deliverable shipped and the next focus is unchosen; effort concentrated outside the
   focus for the whole period; a frozen product with new activity.

## Folding the inbox

Folding is the only way an inbox file affects the curated files. For each unfolded
entry, in file-name order:

1. Append one summary line to `activity.md`, naming the entry's file. If a line
   naming it is already there (an interrupted earlier run), skip the append.
2. Update `portfolio.md` states from evidence only: a product moves to `shipped`
   **only** when its ship read returned `SHIPPED` or a `HUMAN-CONFIRMED` record
   exists. Merged PRs and tags that fail the read do not move it. When a product
   ships, record that in `activity.md` with the proof. Choosing the next focus is a
   decision for the human, not a fold.
3. Move the entry under `inbox/folded/<YYYY-Www>/`. Never edit an inbox file: not to
   fix a typo, not to add a line.

Fold only after the report is written, so an interrupted run leaves the inbox intact
and the report the first to be redone.

## Rules

- No report line without a record that supports it: a collector record, an inbox
  entry, a read from `evidence.md`, or a recorded human confirmation. Where the
  sources leave a gap, the line says what they say and stops.
- Never write inside a worker repository. The collector and `git -C` are reads. In
  particular, do not run `git fetch` here: the sources are what is already local, and
  an unfetched remote is a Coverage line, not a reason to touch the checkout.
- Report language is `config.md`'s; the section headings stay as above in every
  language so a later `review` can parse the previous report.
- At the end, remove `.claude/portfolio/.run/`, and print the report path, the one
  decision (or "none") and the number of Coverage gaps. Nothing else.

## Verification before reporting a state

Pair each reportable state with the read that proved it, in the report itself:

| State | The read |
| --- | --- |
| shipped | the `SHIPPED` line, or the `HUMAN-CONFIRMED` record |
| advanced | the merged or open PR in `collect.json`, by its number in the evidence column |
| stalled | the newest record found for the product, with its date, or "none found in <repositories read>" |
| unread | the status row or error that stopped the read |

A state with no row in this table is not reported.
