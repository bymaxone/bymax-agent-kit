---
name: bymax-code-review
description: "Review uncommitted changes, branches, commits, PRs or paths using Bymax checks and verified findings. Supports quick, full and deep review; no commit, push or merge."
---

# Bymax code review for Codex

Read [the runtime contract](../../references/runtime.md). This is the Codex
execution procedure. Read [the Bymax checklist](../../references/review-checklist.md)
for the mechanical patterns, bug-hunt axes and conventions, and read
[standards](../../references/upstream/bymax-workflow/skills/standards/SKILL.md)
for the relevant stack. Do not execute the original Claude review entrypoint,
`codex-review.sh`, `/code-review`, or this skill recursively as a second opinion.

## Bounded corrections

Review candidates, including mechanical matches, need code-path or test evidence before
edits. Preserve the requested scope and existing behavior; defer nits and unrelated bugs
with reasons. Record the frozen base/head, intent, acceptance criteria, prior findings,
dispositions and check results. After a full review, inspect correction deltas and affected
callers and explicitly verify each earlier open finding. Maximum initial review plus two
correction rounds; if still blocked, stop with evidence and a scope proposal. The
campaign ends after those rounds even when findings remain: a remaining finding is
reported as a blocker, never answered with another full review.

When serving as the Codex side of a Claude-orchestrated campaign, use its exact supplied
prompt, endpoints and output schema. Return your read-only report; do not run its helper,
spawn a second Codex, invoke Claude, clear its receipts or start another review loop.
A standalone invocation here is a Codex review, not proof that Claude also reviewed it.

## Inputs and depth

Interpret the user's request as a mode, target and optional flags. Default to
`full` over uncommitted work, or committed work ahead of upstream when clean.
Names resembling both a path and a branch require explicit `path:` or `branch:`;
never silently choose a different scope. Paths are relative to the target repo root.

| Input | Work |
| --- | --- |
| `quick` | Added-line scans and CRITICAL/HIGH checks; read enough context to verify each candidate |
| `full` | Scans, single-pass bug hunt, stack conventions, call-site tracing and verification |
| `deep` | Full review plus independent-context stack and security finder subagents, when available |
| `--adversarial` | Also challenge the design assumptions, actual callers and simpler alternatives; use a separate context if available, otherwise disclose a same-context pass |
| `--fix` | After the report, triage all candidates, then apply only authorized, verified minimal fixes; review the correction delta and impacted callers |
| `--no-codex`, `--no-builtin` | Compatibility flags: no nested Codex CLI or Claude built-in reviewer runs in this adapter anyway; they do not disable this review |

A request for deep review authorizes its bounded finder subtasks. If the host
cannot delegate, perform the full review locally and label it `full; deep passes
unavailable`. Do not install tools or change models in the middle of a review.
Separate Codex contexts do not establish cross-model independence.

## 1. Capture the requested scope

Inspect the target repo's applicable `AGENTS.md`, git status and stack indicators.
For committed targets, read guidance and stack configuration from the captured
revision, including nested guidance governing each changed file. Do not substitute
policy or dependencies from an unrelated checkout.
Run the packaged helper from the **target repository**, with the script's absolute
path resolved from this skill:

```bash
python3 <package>/scripts/review_scope.py [scope-options]
```

| Target | Scope options |
| --- | --- |
| No target | `--mode auto` |
| Explicit working changes | `--mode uncommitted` |
| Branch | `--mode branch --base <verified-default-ref> --head <branch>` |
| `A...B` | `--mode branch --base A --head B` |
| `A..B` | `--mode range --base A --head B` (endpoint tree diff) |
| Single commit | `--mode commit --head <commit>` (first-parent diff for merge commits; disclose this) |
| File/directory | Add `--path <literal-repo-relative-path>` to the selected scope; repeat for multiple paths |
| PR | Resolve its actual base/head as described below, then use branch mode with those immutable SHAs |

For branch targets, discover the default from `refs/remotes/origin/HEAD` or the
remote's symbolic HEAD (`git ls-remote --symref origin HEAD`, noninteractive).
Resolve/fetch that exact branch. If missing, request an explicit base. Do not
substitute main/master/develop or pass an empty base. Resolve range endpoints
individually; a missing endpoint is a scope error, not an empty review.

For PRs, read `gh pr view <target> --json number,url,baseRefName,baseRefOid,headRefName,headRefOid`.
Use the PR's own base, not the repository default. Fetch missing objects from the
verified repository/PR refs without changing the checkout, then verify their SHAs
match the response. A moving PR is re-read and recaptured. Do not use
`gh pr checkout`, `git switch`, `git add -N`, stash, reset or any index mutation to
make a review target fit. For a PR from a different repository, use a separate
checkout or report that scope unavailable; never interpret its number in origin.

The helper emits pinned base/head commits, a diff, added content lines, staged
and unstaged evidence for working reviews, untracked text/binary/symlink metadata,
and a fingerprint. Keep the complete capture outside the target worktree (for
example in a private temporary directory). Do not save review artifacts into the
reviewed tree, because they would change their own scope. Diff captures can contain
credentials: keep them local and redact secret values from reports.

A helper error, unreadable file, unmerged index entry, missing base or truncated capture is not a clean
review. Inspect large captures from their saved file in bounded sections until
all relevant content has been read. An empty scoped change set means `NO CHANGES`,
not approval of the whole branch. Binary changes, submodules and inaccessible
content require suitable inspection or an explicit coverage limitation.

## 2. Mechanical candidates with correct scope

Use the checklist's patterns over `added_lines`, the additions in `staged_diff`
and `unstaged_diff`, and every untracked text file. Preserve the `>` added-line
indicator when extracting a diff: `+++ b/path` is a header, whereas content that
starts with `++` must still be inspected. Git errors must never be consumed as
"no matches". Evaluate each changed file separately when an exclusion depends on
its path, language or whether it is a test.

For tracked working changes, inspect both index and worktree versions: a staged
secret removed only in the worktree would still be committed. An index/worktree
mismatch must be visible in the report and findings identify the affected version.
For committed targets, read `git show <captured-head>:<path>` and the corresponding
base blob, not the possibly unrelated current checkout. For index content use
`git show :<path>`; for working content read the file. Cite the actual version and
one-based line. Never follow an untracked symlink to read outside the target.

A regex hit proves text exists; it does not prove a defect. Unlike the source
checklist's automatic classification, verify context for **every** candidate:
examples in Markdown, negative test fixtures, approved exceptions, configured
lint gates and generated resources can all legitimately contain a pattern.
Target policy wins over source defaults. Where CI already enforces a rule, do not
repeat its violation as a review finding; independently inspect changes that
weaken that gate. Apply size/layer/documentation rules only to introduced or
materially grown executable/source code as required by the target's guidance.
Use the new file at the reviewed revision for line counts, not `wc` on HEAD.
Skip Tailwind checks unless the installed version and target stack support them;
skip JS/TS-specific rules for Rust and other languages.

## 3. Hunt and verify

For full/deep, read changed files and relevant callers, guards, tests and package
contracts. Trace concrete failure inputs through the code. Check races, error
paths, boundaries, migration requirements, authorization and regressions. API
shape claims require the reviewed version's declarations; behavior claims need
implementation, documentation or a reproducing test. Do not infer a known CVE
from an unfamiliar dependency name. Follow the target's version migration policy.

For deep, give each finder the request, immutable scope or captured working
snapshot, applicable guidance and the relevant bundled role
(`typescript-reviewer`, `rust-reviewer`, `security-reviewer`, or an appropriate
stack-neutral remit). Give no preliminary findings or expected answer. Finders
read only; they do not edit files, run the suite, commit, push, spawn further
review loops or invoke this skill. Keep their outputs unread until your initial
candidate list is recorded. If the host delivers their output early, disclose
that independence was reduced. Wait for completion or explicitly report pending,
failed or unavailable passes; never turn silence into agreement.

Reopen each cited version, trace the causal path and disprove the candidate before
admitting it. Record duplicates and rejected candidates with reasons. Keep finder
severity and provenance visible alongside your disposition; never silently erase
a high-severity outside finding. Confirmed issues from any pass enter the final
consolidated findings. A rejected issue requires the read that disproves it.
Use targeted reproduction only where it materially verifies behavior and the
user's environment permits it. A review does not imply the full suite ran.

## 4. Freshness, findings and verdict

Recapture with the same scope arguments before reporting. For explicit refs,
also confirm they still resolve to the captured SHAs; for PRs re-read head/base
from GitHub. If the fingerprint or target changed, review the new scope and
invalidate earlier conclusions as needed. After two consecutive moving captures,
report `INCOMPLETE — target changing` with the examined fingerprints; do not
approve a moving target indefinitely. A targeted file review never approves
unexamined files in the same branch or PR.

Report mode, resolved scope/SHAs/fingerprint, files covered, findings, rejected
candidate count, reviewer completion states, checks actually run and coverage
limitations. Each finding needs severity, path and tight line range in the
reviewed version, concrete trigger/consequence, supporting read and actionable
remedy. Follow the target's output/severity restrictions; otherwise map
CRITICAL→P0, HIGH→P1, MEDIUM→P2, LOW→P3. Preserve a finder's original severity
when displaying a mapping. Never echo credentials.

| Verified condition | Verdict |
| --- | --- |
| Confirmed unresolved P0/P1 | `BLOCK` |
| Scope/checks needed for the requested review missing, stale or pending | `INCOMPLETE` |
| Only confirmed P2/P3 | `APPROVE WITH CHANGES` |
| Requested scope fully examined and no confirmed findings | `APPROVE — no findings in the examined scope` |
| No changed content in the resolved scope | `NO CHANGES` |

Approval is a review judgment, not proof of bug absence, test success or a
machine-enforced push gate. This skill does not register a hook or create a
Claude review marker. Never bypass a rejecting hook. No commit, push, merge or
external review comment is part of this skill. With --fix, report the original
findings, perform authorized edits, rerun relevant checks and repeat freshness
verification before issuing an updated verdict.
