# Review instructions

This repository publishes two plugin packages from one canonical `plugins/` tree: a Claude
Code marketplace at the root and a Codex plugin under `codex/`. Its product is instruction
text plus Python and shell runtimes, so most of the diff is Markdown that models read, and
calibrating severity for that is the whole point of this file.

## What Important means here

Reserve 🔴 Important for a defect with a concrete trigger in code that runs:

- `plugins/*/scripts/*`, `plugins/*/hooks/*.sh`, `scripts/*.py`, `scripts/*.sh`,
  `scripts/lib/*.py`, `personal/*.sh`, `codex/scripts/*.py`,
  `codex/plugins/bymax-codex/scripts/*.py`
- a fenced `bash` block inside a command or skill document, which a model runs verbatim
- a gate under `scripts/tests/` or `codex/tests/` that would stop failing on the defect it
  protects

A finding about instruction prose — wording, ordering, a count, a comment naming a review
round — is 🟡 Nit at most, whatever its consequence sounds like. Measured here: one branch
spent four review campaigns on one command file, and three of the last findings were
defects introduced by the previous correction to that same prose.

## Escalations

Treat these as 🔴 Important even though they look stylistic; no gate here catches them:

- A new suppression: `# noqa`, `# type: ignore`, or a per-line `shellcheck disable`. The
  accepted shape is the disable in `plugins/bymax-quality/hooks/secret-scanner.sh`, with its
  reason in the comment beside it; a new one without a reason is a finding.
- A hardcoded credential, API key or token anywhere, including test fixtures.
- `--no-verify` or another hook-bypass flag added to a script, hook or command document.
- A change to a file under `plugins/<name>/commands/`, `skills/` or `agents/` without a bump
  to that plugin's `plugin.json` version, the marketplace version and a `CHANGELOG.md` line:
  an installed copy sees no update signal otherwise.

## Cap the nits, and converge

Report at most five Nits per review; say "plus N similar items" in the summary for the
rest. **After the first review of a pull request, post Important findings only.** A branch
in this repository is usually a rule and its test; a second and third round of wording
preferences is how a one-line fix reaches its seventh round.

## Do not report

- `codex/plugins/bymax-codex/references/upstream/**` — generated copies. `validate-codex.sh`
  verifies byte-identity against the canonical sources; report the source, never the copy.
- Anything the gates already enforce, since a violation is a failing check, not a review
  finding: shellcheck (`validate.sh`), fenced-block hygiene and command-file behaviour
  (`scripts/tests/test_command_shell.py`), push-receipt invariants
  (`scripts/tests/test_review_prepush.py`, `scripts/tests/test_review_hook.py`), campaign lifecycle rules
  (`scripts/tests/test_review_flow.py`), bundle drift (`validate-codex.sh`).
- `CHANGELOG.md` wording, and the phrasing of refusal messages whose behaviour a test pins.
- A missing test for prose. Prose is reviewed once; shell inside prose is tested instead.

## Verification bar

- A behaviour claim needs `file:line` and a command that reproduces it, run in a temporary
  repository. An inference from naming is not a finding.
- A claim that a document contradicts the runtime must cite the runtime value it measured,
  not the value the document states.
- A claim that a hook, adapter or receipt can be bypassed must show the push that lands.

## Always check

- **The receipt boundary only narrows.** A change to `review_prepush.py`, `review_push.py`
  or `install_hook`/`usable_hook` in `review_hook.py` must not let a commit without a
  completed receipt reach a remote. Show the push if you think it can.
- **A fenced `bash` block assigns what it reads.** Shell state does not cross a fence, and
  a block that reads a variable an earlier block set takes the wrong branch silently.
- **No document asks a reader to paste a value into shell source.** A git ref name may
  contain `$( )`, which then executes.
- **A key built from two fields keeps its boundaries.** `f"{a}:{b}"` makes `('x:y','z')`
  and `('x','y:z')` one key; encode each field or hash each to a fixed width.
- **A document does not restate a count the runtime decides.** It is wrong the next time
  the runtime changes; cite the runtime value or leave the number out.

## Summary shape

Open with a one-line tally, for example `1 important, 3 nits`, and lead with "no blocking
issues" when that is the case. Name the files you read and what you could not verify.
