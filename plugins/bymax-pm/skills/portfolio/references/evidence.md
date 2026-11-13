# Evidence: what counts as shipped

A deliverable is **shipped** only when a release exists that a read can prove.
Commits, merged pull requests and green CI are progress: they never move a product to
`shipped` and never appear under "Shipped" in a report.

| Ship type | Counts as shipped when | The read that proves it |
| --- | --- | --- |
| `npm` | the version named in the deliverable is published | `npm view <pkg>@<version> version` prints that version |
| `github-release` | the tag exists on the default branch's history | `gh api repos/<o>/<r>/releases/tags/<tag>` returns it, and `gh api repos/<o>/<r>/compare/<default>...<tag>` has `status` of `behind` or `identical` |
| `deployment` | a deployment of the commit reached the named environment with success | `gh api "repos/<o>/<r>/deployments?environment=<env>"`, then `gh api repos/<o>/<r>/deployments/<id>/statuses` whose newest `state` is `success`; or an HTTP 200 from the health URL recorded in `portfolio.md` |
| `store-build` | the build is in the store track the deliverable names | **not verifiable by the agent.** Recorded only from an explicit human confirmation, labelled `HUMAN-CONFIRMED` with the date, never inferred |
| anything else | not counted | the human adds a ship type to `done.md` with its read first |

REST endpoints only. GraphQL is unavailable in some Claude Code cloud sessions, so
`gh api graphql` and `gh pr view --json` forms that call it are not used here.

## Running the reads

Write one line per deliverable to `.claude/portfolio/.run/ship.txt` with the file
tool: `<type>|<target>|<version or tag>|<environment>|<health URL>`, always five fields,
the ones a type does not use left empty (a deployment has no version:
`deployment|owner/repo||production|https://example.test/health`). The separator is `|`
because a tab is whitespace to `read`, which merges adjacent tabs and would shift every
field after an empty one; a value containing `|` is refused. The block reads the file and
prints one result line per deliverable.
Values are quoted arguments read from the file, never pasted into command text, and a
value starting with `-` is refused. A health URL must start with `http://` or
`https://`:

```bash
PDIR=$(python3 -c 'import json, os; p = os.path.expanduser("~/.claude/bymax-portfolio.json"); print(os.environ.get("BYMAX_PORTFOLIO_DIR") or (json.load(open(p)).get("dir", "") if os.path.exists(p) else ""))')
if [ -z "$PDIR" ]; then
  echo "No portfolio workspace: set BYMAX_PORTFOLIO_DIR or write ~/.claude/bymax-portfolio.json." >&2
  exit 1
fi
SHIP="${PDIR}/.claude/portfolio/.run/ship.txt"
if [ ! -f "$SHIP" ]; then
  echo "No ship.txt at ${SHIP}: write one line per deliverable first." >&2
  exit 1
fi
while IFS='|' read -r TYPE TARGET VERSION EXTRA HEALTH || [ -n "$TYPE" ]; do
  BAD=""
  for FIELD in "$TARGET" "$VERSION" "$EXTRA" "$HEALTH"; do
    case "$FIELD" in
      -*|*'|'*) BAD="a value starts with a dash or holds a separator" ;;
    esac
  done
  case "$HEALTH" in
    ""|http://*|https://*) ;;
    *) BAD="the health URL is not http(s)" ;;
  esac
  if [ -n "$BAD" ]; then
    echo "REFUSED ${TARGET}: ${BAD}"
    continue
  fi
  case "$TYPE" in
    npm)
      GOT=$(npm view "${TARGET}@${VERSION}" version 2>/dev/null)
      if [ "$GOT" = "$VERSION" ]; then echo "SHIPPED npm ${TARGET}@${VERSION}"; else echo "NOT-SHIPPED npm ${TARGET}@${VERSION}"; fi
      ;;
    github-release)
      DEFAULT=$(gh api "repos/${TARGET}" --jq .default_branch 2>/dev/null)
      REL=$(gh api "repos/${TARGET}/releases/tags/${VERSION}" --jq .tag_name 2>/dev/null)
      REL_STATE=$(gh api "repos/${TARGET}/compare/${DEFAULT}...${VERSION}" --jq .status 2>/dev/null)
      if [ -n "$REL" ] && { [ "$REL_STATE" = "behind" ] || [ "$REL_STATE" = "identical" ]; }; then
        echo "SHIPPED github-release ${TARGET}@${VERSION}"
      elif [ -z "$DEFAULT" ]; then
        echo "UNREAD github-release ${TARGET}@${VERSION}: gh could not read the repository"
      else
        echo "NOT-SHIPPED github-release ${TARGET}@${VERSION}"
      fi
      ;;
    deployment)
      DEP=$(gh api "repos/${TARGET}/deployments?environment=${EXTRA}&per_page=1" --jq '.[0].id' 2>/dev/null)
      if [ -z "$DEP" ] && [ -n "$HEALTH" ]; then
        CODE=$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$HEALTH")
        if [ "$CODE" = "200" ]; then echo "SHIPPED deployment ${TARGET} ${EXTRA} (health ${HEALTH} returned 200)"; else echo "NOT-SHIPPED deployment ${TARGET} ${EXTRA}: health ${HEALTH} returned ${CODE}"; fi
      elif [ -z "$DEP" ]; then
        echo "UNREAD deployment ${TARGET} ${EXTRA}: no deployment or gh could not read it"
      else
        STATE=$(gh api "repos/${TARGET}/deployments/${DEP}/statuses?per_page=1" --jq '.[0].state' 2>/dev/null)
        if [ "$STATE" = "success" ]; then echo "SHIPPED deployment ${TARGET} ${EXTRA} (${DEP})"; else echo "NOT-SHIPPED deployment ${TARGET} ${EXTRA}: latest state ${STATE:-none}"; fi
      fi
      ;;
    store-build)
      echo "HUMAN-ONLY store-build ${TARGET}: shipped only with a recorded HUMAN-CONFIRMED line"
      ;;
    *)
      echo "NOT-COUNTED ${TYPE}: add the ship type to done.md with its read"
      ;;
  esac
done < "$SHIP"
```

Read the output whole. The result word decides the state:

| Output | Meaning |
| --- | --- |
| `SHIPPED` | counts; the result line is the proof printed under the entry |
| `NOT-SHIPPED` | the read ran and the release is absent: the product stays "advanced, not shipped" |
| `UNREAD` | the read could not run (`gh` signed out, rate limit, no access): reported under Coverage, never as `NOT-SHIPPED` |
| `HUMAN-ONLY` | look for the `HUMAN-CONFIRMED` record in `activity.md` or the inbox; with one, the deliverable ships and the proof is that record with its date; without one, it does not |
| `REFUSED`, `NOT-COUNTED` | fix the input (`portfolio.md`, `done.md`), do not count it |

A release whose evidence predates the deliverable (a tag older than `Started:` in
`now.md`) is a different release: the read proves the deliverable only when the
version in `Ship version:` is the one named for it.

## What a store build needs

The store dashboard is outside the agent's reach, so the agent never marks one shipped
on its own. The human writes a line in the session or in `activity.md`:
`HUMAN-CONFIRMED <product> <track> <build> YYYY-MM-DD`. `review` then lists it under
Shipped with that line as the proof. A merge, a tag or a green build workflow for the
same app is progress.
