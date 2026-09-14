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
must appear in each new report's `resolutions` as `{ "id": "claude/<finding-id>",
"evidence": "how the fix was verified, or why it remains broken" }` (similarly `codex/`).
If still broken, also include it in the new findings. This prevents silent disappearance
from being reported as a verified fix.

## Triage and corrections

```bash
python3 "$FLOW" triage --report <dispositions.json>
```

The file is a JSON list with **every** report finding keyed by `claude/<id>` or `codex/<id>`:

```json
[
  {"id": "claude/src/job.py:restart-state", "status": "open",
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

Use explicit commands, for example `git push -u origin HEAD:feature-name` or
`git -C "/path with spaces" push origin feature-name`. Multiple explicit sources are
checked individually. Implicit/wildcard/mirror pushes, shell wrappers, environment
expansion and unsupported options fail with a corrective message. Another worktree's
receipt cannot authorize a different SHA. Tag sources must peel to a reviewed commit;
there is no blanket tag exemption.

This is a Claude **PreToolUse Bash guard**, not a Git server security boundary. Direct
terminal pushes, custom executable wrappers and other tools are outside that hook's
coverage. Do not describe it as tamper-proof. For repository-wide enforcement use CI or
an explicitly installed Git `pre-push` hook, which receives actual local/remote ref tuples;
never replace an existing `core.hooksPath` silently. A completed review is evidence of
coverage, not a guarantee that the code has no bugs.

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
No commands, including `cd`, may follow the push in the same Bash invocation.
Directory changes take exactly one non-option literal argument.
Heredocs must be separate invocations: the guard accepts standalone `cat` with a quoted
delimiter and an optional literal output path (letters, digits, underscores, dots,
slashes and hyphens). It rejects other heredoc forms and commands after the terminator;
issue those operations separately. Text inside an accepted quoted heredoc is literal
and may mention `git push` without requiring a review receipt.
