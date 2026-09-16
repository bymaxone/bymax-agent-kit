## Bounded review before push

Every source commit pushed through Claude must have a completed Claude + Codex review
under `/bymax-quality:code-review` and its bounded review protocol. Reuse an existing
completed receipt for the exact SHA. Never invoke a review just to recreate a marker.

The normal sequence is: implement the authorized scope, run project checks, create the
candidate commit when shipping is authorized, freeze context/base/HEAD, run one read-only
Claude pass and one read-only Codex pass, then verify and triage their findings. Do not
invoke the built-in `/code-review` as a third mandatory reviewer. Keep the optional Codex
Stop review gate disabled; this campaign is the only review/correction loop.

Treat every suggestion as a candidate, including grep matches and external-reviewer
findings. Confirm it against the code, actual dependency contracts and a reproduction
where feasible. Preserve original reviewer evidence and record justified rejections.
Fix confirmed introduced correctness/security defects and explicit policy violations.
Defer nits and unrelated pre-existing issues with a reason; never rewrite unrelated code
merely to obtain an empty review. Inspect related callers to preserve existing behavior.

Correct accepted blockers in one minimal batch. Run regression tests and project gates;
commit authorized fixes, then review only the correction delta and impacted behavior with
both models, verifying each earlier open finding. For shipping, use `start --autonomous`: initial candidate plus five correction candidates,
with a persistent branch/PR budget that survives completed campaigns and pushes. On exhaustion with real blockers, stop with evidence. Before that, continue ordinary
in-scope repairs and root-cause analysis without asking again. Never reset state, switch branches or disable a reviewer to evade the limit.
Missing/failed reviewers mean incomplete review, not product defects or approval.

A blocked push is an automatic handoff: run the review skill, certify the corrected candidate,
and retry the original destination/refspec. Do not end the task at the blocked hook or at a
clean review. Read the plugin autonomous-delivery contract.

The runtime is `~/.claude/bymax-review/review_flow.py`. Follow the plugin protocol for
`start`, `prompt`, `codex`, `record`, `triage`, `check`, `finish` and `status`. Save context
and reports outside the source tree. Only `finish` with completed evidence clears a
candidate. Skill invocation and the legacy `code-review-clear.sh` never authorize a push.

Use literal explicit pushes such as `git push -u origin HEAD:feature-name`. The global
Bash guard validates each source SHA; it does not run models or certify arbitrary shell
wrappers. Do not bypass it via another tool or terminal. No review system guarantees zero
bugs: report the actual coverage, checks, limitations and unresolved risks.

Apply these same verification, scope and round limits when addressing PR bot findings.
Respond/resolve only after checking current code and obtaining actual evidence. Once the
round budget is exhausted, report the blocker instead of launching another repair loop.
