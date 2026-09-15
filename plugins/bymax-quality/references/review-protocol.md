# Bounded dual-review protocol

The orchestration layer records evidence; it does not prove that a model's reasoning is
true. Never fabricate a report, test result or disposition to satisfy its schema. The
human remains able to inspect the reports and decide a blocked campaign's next scope.

## Context and lifecycle

Run helpers from the target repository, with their absolute plugin paths. Set `FLOW`
to `${CLAUDE_PLUGIN_ROOT}/scripts/review_flow.py`. State lives under the shared Git
common directory in `bymax-review/<branch-hash>/`, survives sessions and does not enter
the diff. Put the context and report input files outside the working tree, such as a
private temporary directory. Do not include credentials or unrelated conversation logs.

The context is a JSON object, for example:

```json
{
  "intent": "Requested behavior",
  "acceptance": ["Observable success criterion"],
  "constraints": ["Preserve the existing API contract"],
  "scope": "Integration base, components and exclusions",
  "stack": "Versions and applicable policy paths",
  "checks": [["npm", "test"], ["npm", "run", "lint"]]
}
```

Use the target project's actual check argument lists, not these example commands.
The context must contain:

- User-requested behavior and observable acceptance criteria.
- Intended integration base, changed components and invariants to preserve.
- Scope exclusions; distinguish unrelated pre-existing defects from regressions.
- Relevant stack/dependency versions and authoritative local policy paths.
- Required project check commands and the regression evidence expected for fixes.

```bash
python3 "$FLOW" status
python3 "$FLOW" start --base <merge-base-sha> --context <context-file>
python3 "$FLOW" prompt
python3 "$FLOW" codex
```

A missing `status` is expected only before the first campaign. `start` is idempotent for
the same HEAD/base/context: reuse recorded reviewers instead of rerunning them. When a
campaign is unfinished, keep its original base and context. After a batch of committed
corrections, `start` advances the round and sets `review_base` to the preceding candidate.
Both reviewers see the delta plus prior dispositions and inspect impacted callers.

`codex` uses `codex exec` with a custom prompt, read-only sandbox, approval policy `never`,
and no reused thread. It does not use `codex exec review --base`: that interface cannot
combine custom instructions with its scope flags in the installed CLI. The shared prompt
includes explicit Git endpoints instead. Codex receives an output schema and must return JSON without Markdown fences. A report
with `status: incomplete` is rejected even if its findings list is empty.
One failed attempt may be retried for an infrastructure/format error; never retry a valid
review to seek a different opinion. Each attempt has a ten-minute ceiling. Failure or a
missing CLI blocks completion; it does not imply a code defect.
A separate OS lock prevents simultaneous Codex attempts while Claude can still record.
The Codex child inherits that lock: if its launcher dies, wait for the child to exit before
retrying `codex`. Once both processes exit, the next invocation recovers an abandoned
reservation automatically and retains the consumed attempt count. `codex_running` is
persisted diagnostic metadata, not a liveness check; the lock determines availability.
Never reset the attempt counter to work around an exhausted budget.

The caller performs the Claude read-only review from that same generated prompt, freezes
its report before reading Codex output, and records it:

```bash
python3 "$FLOW" record --reviewer claude --report <claude-report.json>
python3 "$FLOW" status
```

Report format (the helper supplies exact `head` and `base` in its prompt):

```json
{
  "status": "completed",
  "head": "<candidate-sha>",
  "base": "<review-base-sha>",
  "summary": "Files, callers and contracts actually inspected; limitations",
  "findings": [
    {"id": "src/job.py:restart-state", "priority": "P1", "kind": "defect",
     "evidence": "Trigger, file:line, affected path and concrete consequence"}
  ],
  "resolutions": []
}
```

Kinds: `defect`, `policy`, `nit`, `preexisting`. Priorities P0–P3 retain the reviewer's
original assessment. Applicable explicit policy can make a convention blocking; do not
turn generic style preferences into policy defects. Every earlier **open** disposition
must appear in each new report's `resolutions` as `{ "id": "claude::<finding-id>",
"evidence": "how the fix was verified, or why it remains broken" }` (similarly `codex::`).
If still broken, also include it in the new findings. This prevents silent disappearance
from being reported as a verified fix.

## Triage and corrections

```bash
python3 "$FLOW" triage --report <dispositions.json>
```

The file is a JSON list with **every** report finding keyed by `claude::<id>` or `codex::<id>`:

```json
[
  {"id": "claude::src/job.py:restart-state", "status": "open",
   "evidence": "Reproduced with test_restart; repair only startup transition"}
]
```

Use `[]` if both findings lists are empty. Use `rejected` only with concrete code/test
counterevidence; `deferred` for nits or unrelated pre-existing work with a reason. Keep
accepted defects `open` on the old candidate. A fix is verified by both reviewers on the
next committed candidate, not by marking an unreviewed edit as fixed. Duplicate findings
retain separate provenance entries and refer to the same root cause in their evidence.

A confirmed defect needs a failing regression before the fix where feasible, a passing
result after it, and checks of affected contracts. If reproduction is impractical, record
an explicit code-path proof and the verification limitation. Do not invent tests which
merely mirror the proposed fix. If the minimal safe fix crosses the agreed scope, stop and
propose splitting the work. Do not broaden a UI change into an unrelated backend rewrite.

A correction round carries evidence the helper requires and both reviewers see:

```bash
python3 "$FLOW" start --base <sha> --context <ctx> --probe <probe.json> [--design-round] \
    [--no-regression-reason "<why>"]
```

`--probe` is a nonempty JSON list of `{"command", "expected", "observed"}`: what the author
ran against the correction before committing it. The prompt shows it to both reviewers
with the instruction to verify each entry and go beyond it; shallow probing is a finding.
The helper lists every test file added or modified in the delta in the prompt (a renamed
test appears under its new path), so a flipped expectation — as opposed to an added case —
must be justified in triage or is a finding. Deleted test files are listed separately, with
the instruction to judge the deletion; they never count as regression evidence.
A correction that adds or modifies no test is refused unless `--no-regression-reason` records
why, and that reason reaches both reviewers for judgement.

A finding open in two consecutive triages has been **reopened**: the previous fix
addressed the instance, not the cause. `start` refuses the next round unless it is
declared `--design-round`, records the reopened ids, and tells both reviewers the round is
about the approach; a patch to the same instance is then itself a finding. A still-open
defect repeated under the prefixed id a reviewer saw in an earlier disposition still names
the same invariant: keys are `reviewer::<id>`, and no path begins with `claude::` or
`codex::`, so `record` strips those prefixes from a finding id however many were copied,
a repeat within one report is a duplicate, and a finding on a real file under a `codex/`
directory is exactly what it says.

The Claude pass on a correction delta is performed by a fresh-context subagent given only
the generated prompt, never by the session that authored the fix.

Run every required gate named in the context after the final candidate commit:

```bash
python3 "$FLOW" check -- <executable> <arguments>
python3 "$FLOW" finish
python3 "$FLOW" status
```

The helper captures command, exit code and output. A nonzero check cannot be cleared by
running a different trivial command; rerun the same failed command successfully after
fixing its cause. The helper requires every command declared in the context. It cannot infer whether that
list covers the project's requirements: check it against project docs before starting.

`finish` requires both reports, every disposition, no open or deferred confirmed P0–P2
blocker, a clean matching HEAD, and passing check records. Same-HEAD reuse is intentional.
New work after a completed campaign starts a new full campaign. A stalled campaign has
no automatic reset: explain the blockers and obtain a scope decision. Preserve its
`state.json` and round files if a human authorizes archiving it and starting over.

## Push enforcement and limits

`scripts/install-review-flow.py` installs a global Claude Bash hook plus a local plugin
overlay with backups. It removes the old invocation-only recorder and clear assertion.
It preserves unrelated hooks/settings. It does not enable the Codex Stop review gate;
keep that separate loop disabled when this workflow is active.

Enforcement is a Git **`pre-push` hook**, `review_prepush.py`. Git hands it the pushed
SHAs on stdin, so it holds however the push command was spelled: it refuses any commit
without a cleared receipt, for every ref in the push, and allows ref deletions.
`review_flow.py start` installs it into the repository's hooks directory when none is
present. An existing `pre-push` it does not manage is reported for the human to merge
the check into by hand, never overwritten; one that carries the check at the current
policy is kept as merged. A custom `core.hooksPath` directory is never written into: it
qualifies once its `pre-push` carries the check. In either place, a hook that declares
another policy or is not executable is refused at `start`, with the remedy named. Before
the candidate is frozen, `start` also runs that hook twice as git would (through `sh` when
it has no shebang, within 60 seconds each, with origin's name and URL as arguments),
feeding it one push line shaped like a real push: the current branch, fast-forwarded by a
dangling child of HEAD built from the current tree. That commit exists and has a parent,
and the pushed ref is a real branch, but no receipt names the commit: the hook must
refuse the first push. For the second push the helper holds a temporary completed
receipt for that commit (in a directory of its own under `bymax-review/`, removed
afterwards even on failure, so concurrent starts in linked worktrees do not disturb each
other): the hook must let it through. A hook that exits 0 for the first push does not enforce receipts; one that
refuses the second is refusing for some other reason and is not consulting receipts.
Both are refused at `start`, with the remedy named.

`review_push.py` is a Claude **PreToolUse Bash adapter** in front of that hook, with two
narrow jobs. It recognises exactly `[cd <path> &&] [VAR=value ...] git [-C <dir>] push
<remote> <refspec>...` and performs the receipt lookup for that form, so a missing receipt
is reported with a useful message before git runs; for that form, implicit, wildcard,
mirror, followTags, deletion and chained pushes fail with a corrective message, and
another worktree's receipt cannot authorize a different SHA. It also refuses any command
containing an option that would skip or redirect the hook (`no-verify`, `hooksPath`,
`GIT_DIR`, `--git-dir`, `GIT_WORK_TREE`, writes under `.git/hooks`), matched as a
substring wherever it appears. **Every other command passes through untouched**: a push
spelled in any other arrangement is not the adapter's to judge, and the hook decides.

The adapter is not the enforcement boundary and is not described as one. The residue no
local design closes is a hook-skipping option spelled so the adapter's substring check
cannot see it, since git itself provides that escape; the tests document it, and CI is
the boundary for deliberate evasion. A completed review is evidence of coverage, not a
guarantee that the code has no bugs.

## Basis and operating assumptions

Validated against official documentation on 2026-09-14:

- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
  supports explicit criteria, environmental feedback and iteration stopping conditions.
- [Claude local code review](https://code.claude.com/docs/en/code-review)
  documents the confidence/coverage tradeoff at high/max and isolated review contexts.
- [OpenAI custom review rules](https://developers.openai.com/blog/custom-code-review-rules-for-codex)
  explains repository-specific, actionable review instructions.
- [OpenAI Codex plugin](https://github.com/openai/codex-plugin-cc)
  warns that its optional Stop review gate can create long-running review loops.
- [Git pre-push contract](https://git-scm.com/docs/githooks#_pre_push)
  defines exact pushed-ref information for integrations requiring Git-level enforcement.

The three-candidate and two-infrastructure-attempt limits are project defaults, not
numbers established by those publications. Measure validated findings, rejected findings,
regressions introduced by fixes, scope growth and elapsed time before tuning them.

## Shell forms accepted by the local push guard

Issue one explicit `git push`, optionally preceded by `cd <literal-path> &&`.
For the literal form the adapter checks, no command may follow the push in the same
Bash invocation, and a leading `cd` takes exactly one non-option literal argument.
Heredocs, quoted text and every other command shape need no special treatment: the
adapter does not inspect them, so text may mention `git push` freely, and a push
hidden inside one is stopped by the hook when git runs it.
