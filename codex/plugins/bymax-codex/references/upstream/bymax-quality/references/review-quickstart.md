# Review campaign: one page

The protocol and the command file say why. This page says what to run, in order, and what
each step costs, for a candidate that is already committed on a clean tree.

```bash
FLOW="$HOME/.claude/bymax-review/review_flow.py"
CONTEXT="<outside the repository>/context.json"   # intent, acceptance, measured, checks
BASE="$(git merge-base origin/main HEAD)"

python3 "$FLOW" prose --base "$BASE" --stage prepare   # a fresh reader corrects new prose
python3 "$FLOW" prose --base "$BASE" --stage verify    # refuses prose that grew
python3 "$FLOW" start --autonomous --base "$BASE" --context "$CONTEXT"
python3 "$FLOW" check -- <each gate the context names>  # before any reviewer reads
python3 "$FLOW" prompt > "<outside the repository>/prompt.txt"
python3 "$FLOW" codex                                   # background; minutes
# Claude pass: a fresh subagent given only prompt.txt, then
python3 "$FLOW" record --reviewer claude --report "<report.json>"
python3 "$FLOW" triage --report "<dispositions.json>"   # a JSON list, [] when no findings
python3 "$FLOW" finish
```

Then push with the literal form `git push -u origin HEAD:<branch>` as a command of its own.

## Order that matters

| Step | Why it comes there |
| --- | --- |
| `check` before `prompt` | `prompt` and `codex` refuse until every declared gate has run on this head. |
| `prompt` finished before the Claude pass starts | A subagent started on a file `prompt` is still writing reads an empty task. |
| `triage` while HEAD is the reviewed commit | It refuses once HEAD has moved. |
| Context file outside the repository | A campaign reviews a clean tree. |

## A correction round

Commit the fix, run the prose pair again, then, when a test changed, `matrix --spec <file>
<test paths>` (every mutant must be caught), then `start` again with `--probe <file>` (each
entry names the command, what it expected and observed, and `without_fix` for a changed
test), `--answers <path:slug>` after a cleared candidate, and `--widen-scope "<why>"` for a
file no finding names. Tests and the generated bundle never count as widening.

## What is slow

The regression measurement runs every node of a changed test file against the base tree. It
is taken once per candidate and kept in the campaign directory, so `start`, `prompt`,
`codex` and `finish` after the first read it back. The first one can take minutes on a large
module; do not read that as a hang. `codex` also spends that time before it reserves an
attempt, so no attempt is lost to a wait.

## What the push guard refuses

A line that holds a word spelling `push` (a path such as `hooks/pre-push` counts) together
with a program able to start another, `git` among them, is refused by design. Run the read
as its own command. Only a pushed commit without a usable receipt is sent to a review; a
refusal about spelling or configuration is not.

## When something is missing

| Symptom | Read |
| --- | --- |
| Codex absent, or Claude out of quota | **When Codex cannot run** and **When Claude quota is exhausted** in `review-protocol.md`. |
| Budget spent with a real blocker | `autonomous-delivery.md`, Budget and continuity. |
| A reviewer failed or timed out | Incomplete, never approval: inspect its log in the campaign directory. |
