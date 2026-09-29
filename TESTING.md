# Regression coverage and remaining limits

Run `scripts/validate.sh` and `scripts/validate-codex.sh` from the repository root.
Both run in CI. Python/PyYAML/Claude are required; CI also requires shellcheck and
Codex CLI discovery. Test fixtures use temporary repositories, fake model processes
and local remotes; ordinary test execution must not incur model costs or push publicly.

| Failure mode | Automated coverage |
| --- | --- |
| Malformed manifests, frontmatter, missing resources | Claude validation, check-frontmatter and Codex package validator |
| Shell snippets mutate scope, lose status or interpolate unsafe refs | `scripts/tests/test_command_shell.py` |
| The suite runner in `validate.sh` passes while a module fails, or while no module ran | `scripts/tests/test_validate_runner.py` |
| Stale/dirty review, incomplete reviewers, missing gates, bad triage | `scripts/tests/test_review_flow.py` |
| Reopened finding, scope widening, changed/deleted tests, lost provenance | Review-flow behavioral tests |
| A candidate its declared gate failed cannot be replaced, or a reviewed one can | `scripts/tests/test_review_replacement.py` |
| Shell push spelling, multiple refs/tags, worktrees, foreign/custom hooks | `scripts/tests/test_review_prepush.py` and `scripts/tests/test_review_hook.py`, including actual pushes to isolated local remotes |
| Interrupted or concurrent model processes | Review-flow lock, child ownership, attempt and concurrent writer tests; the Codex pass's in `scripts/tests/test_review_codex.py` |
| Counter renewal after completed campaign, retry or archive | `scripts/tests/test_review_delivery.py` |
| Codex-led Claude review fails or gains editing tools | Delivery tests capture real process argv, input diff and structured output |
| Installer drops user configuration or omits runtime dependencies | `scripts/tests/test_review_install.py` and installed-runtime execution |
| Codex misses staged/untracked changes or pins wrong revisions | `codex/tests/test_review_scope.py` |
| Standup collector admits a harness-written line as a request, misses a worktree session, or loses a commit to git's `--since` cutoff | `scripts/tests/test_report_collect.py` |
| Standup skill block reads another run's arguments, runs the collect with no temporary directory, or leaves a failed collect's directory behind | `scripts/tests/test_report_skill_block.py` |
| Standup period resolves a typo to a default week, or a subject's type or scope, or a ref's branch name, is misread | `scripts/tests/test_report_period.py` |
| Standup collector loads a module the `python3` a machine has cannot parse, or whose annotations it cannot evaluate | `scripts/tests/test_report_interpreter.py` |
| The mutation matrix counts a node that never ran, or an enumeration cut off while a writer it left prints | `scripts/tests/test_review_collection.py` and `scripts/tests/test_review_runs.py` |
| Bundle drifts, package cannot be installed or skills are undiscoverable | `codex/tests/test_bundle.py`, `test_install.py` and isolated CLI skill discovery |

The mutation matrix reads whether a node ran from what pytest reports. Subtest cases need
pytest 9, or pytest-subtests 0.14.2 or later; on older versions a node whose subtests skip
reads as not run and is refused. On any version, a node that asserts after every subTest
skipped reads as one that returned there, and is refused too; the test pinning that
subtest behaviour skips on pytest before 9.

Instruction text also needs behavioral evaluation: a valid Markdown/YAML document may
still contain contradictory role assignments. For changes to orchestration, use an
independent fresh-context scenario: an implementer returns a candidate, a reviewer finds
a real defect and a nit, a correction is verified, then a new PR comment arrives after
push. The expected behavior is bounded minimal repair, deferred nit, both independent
reviews and continuation with the same ledger. A scenario is not a paid model benchmark
unless the actual models and external effects were exercised; report that distinction.

Tests cannot guarantee error-free AI output. Preserve each reproduced production defect
as a behavioral regression, check cumulative invariants, avoid weakening expectations,
and record gaps in browser/mobile/third-party integrations rather than marking them
covered because packaging passed. Six candidates is a configurable design choice only
through reviewed code, not a measured guarantee that almost every task will converge.
