# AGENTS.md — bymax-claude-code

Guidance for coding agents working in this repository, and the rules Codex applies when it
reviews a pull request here. Codex reads this file from the tree under review: per its GitHub
review documentation, root-level rules apply broadly and a nested `AGENTS.md` governs the code
in its directory, and per its `AGENTS.md` guide at most one file is read per directory, up to a
combined `project_doc_max_bytes` of 32 KiB by default. So the shared half below has to exist
here as a real file, kept in step by the `agents-sync` workflow.

## What this repository is

A Claude Code plugin marketplace. The product is **instruction text**: every file under
`plugins/*/commands/`, `plugins/*/skills/*/SKILL.md` and `plugins/*/agents/` is a contract read
by a model at run time, and most of the reviewable surface is Markdown. The executable parts are
small — `scripts/validate.sh`, `scripts/lib/check-frontmatter.py`, `plugins/*/scripts/*.sh` and
`plugins/*/hooks/*.sh`.

## How to verify work

```bash
./scripts/validate.sh        # manifests, +x bits, shellcheck, frontmatter, required files
```

It needs the `claude` CLI and PyYAML (`python3 -m pip install pyyaml`; `--break-system-packages`
on a PEP 668 Python, as CI does). A missing `claude`, `python3` or PyYAML is a red run, not a
skipped check. **shellcheck is the one optional dependency:** absent locally, the lint step
prints a warning and is skipped, and CI — which installs it — is where that gate is enforced.
So a green local run proves the manifests, the frontmatter and the required files, and proves
shellcheck only when it is installed. Done means `validate.sh` is green **and** the command text
says what it means — see the first narrowing below.

## Code Review Rules

<!-- shared:begin -->
<!--
  CANONICAL COPY: bymaxone/.github → agents/code-review-rules.md
  Do not edit this block in a consuming repository. It is replaced wholesale by
  the `agents-sync` reusable workflow, so a local edit is reverted on the next
  run. Change it here, cut a release, and every repository is offered the update.

  Repository-specific rules go OUTSIDE this block, below the closing marker.

  FOR WHOEVER EDITS THIS FILE, not for the reviewer who reads it:

  Codex reads one AGENTS.md per directory, root to nested, within
  project_doc_max_bytes (32 KiB default). Never name a template or fixture
  AGENTS.md below the root: a change under it is read as the repo's guidance.

  This block is charged against every consumer's budget. A rule added here must
  be worth the bytes in the smallest-headroom repository, not only in this one;
  agents-sync reports each consumer's headroom and fails when it is exceeded.

  When you scope a rule, scope every rule in its paragraph or split the
  paragraph -- an unscoped neighbour reads as deliberate.
-->

These rules hold in every Bymax repository. What is specific to this one is written after this
block, and the two are read together.

The pipeline already enforces formatting, linting, dependency policy, coverage and — where the
repository has one — the mutation gate. Do not spend a review on a **violation** of one of those: it
is a red check, not a comment. What follows is what CI cannot see.

A violation of a rule in this block is reported at **P1** at minimum. Codex surfaces only P0 and P1
on a pull request, so a rule whose violations land at P2 is a rule nobody sees.

**When a rule moves from here into a check, it leaves here.** A red check is proportionate to a
correctness failure that is invisible without it, and disproportionate to style enforced at an
inconvenient moment. Never carry both: a rule stated here _and_ enforced by CI spends a reviewer's
attention on what a gate already reports.

**A change to the enforcing configuration is the opposite case, and it is in scope.** Every gate runs
the configuration from the branch under review — that branch's lint config, its coverage thresholds,
its mutation thresholds. So a pull request that deletes a rule, lowers a threshold or widens an
ignore glob turns the check **green**, because a gate reports on the rules it was handed. For those
diffs the review is the only independent check there is, and a weakened gate needs the same
justification a suppression does.

### A finding names what it read

Every factual claim in a review — about a library's API, about this repository's history, about what
a file contains — has to come from something read in the tree under review, and the finding should
say which. A claim assembled from recollection is likely to describe a previous version of whatever
it is about.

**Safe path**, by the kind of claim:

| Claim about                             | Read this                                                                      |
| --------------------------------------- | ------------------------------------------------------------------------------ |
| A library's API **shape**               | `node_modules/<pkg>/dist/**/*.d.ts` in this tree                               |
| A library's **runtime behaviour**       | that version's changelog entry, its documentation, or a test that exercises it |
| A commit's author or committer identity | out of scope: it is not text a change introduces                               |
| What a file contains                    | the file at the revision under review, not an earlier one                      |

The first two rows are separate on purpose, and the rule below says why: a field can stay optional
in the published type while becoming mandatory in behaviour. A `.d.ts` settles what a signature
accepts and nothing about what the implementation does with it, so a behavioural claim resting on
one is unfounded.

Weight the checking by what acting on the finding would cost. A comment that asks for a reworded
sentence is cheap to be wrong about; one that asks for history to be rewritten, a merge reverted, or
a release pulled is not — verify that class before raising it, and raise it at the severity the
evidence supports rather than the severity the consequence would deserve if true.

### A dependency upgrade migrates every call site, not only the ones that fail to compile

When an upgrade tightens a contract, the compiler catches only the call sites whose **shape**
changed. A field that stays optional in the published type while becoming mandatory in behaviour
compiles, passes the unit suite, and fails in production.

A `@bymax-one/*` version number carries **no compatibility information** while the libraries are
pre-stable: breaking changes ship in minor and patch releases by explicit policy, so `^` and `~`
protect against nothing. The migration note under **Apply to a derived backend** in the library's own
changelog is the compatibility contract.

**Safe path:** read **every** changelog entry from the version being replaced up to the proposed
one, not only the proposed one's, and check every call site they name — not only the ones the
compiler rejected. Upgrades routinely skip releases, and the entry that matters is often not the
last one: adopting `@bymax-one/nest-cache` 1.1.0 → 1.2.1 skipped 1.2.0, where a namespace-validation
security fix lives; 1.2.1's own entry is a field rename. Diff the `.d.ts` of the **previously adopted** version against
the **proposed** one — `npm pack` both, and name the two versions. Reaching for "the installed
declarations" is the trap: in a checkout of the branch under review the installed tree is already
the new version, so that diff compares a release with itself and shows nothing.

### Settled decisions are not review findings

Both are settled deliberately, and reopening either costs a round trip and changes nothing:

- **Do not propose a major version bump** for a breaking change in a `@bymax-one/*` library, and do
  not assert that this ecosystem follows strict SemVer. Until an API is declared stable, breaking
  changes ship in minor and patch releases; the migration note carries the compatibility information
  the number does not. If a document claims strict SemVer, the finding is that the claim is wrong —
  not that the version should be raised.
- **Do not propose pinning `bymaxone/.github` reusable workflows to a commit SHA.** They are
  referenced by the `@v1` alias on purpose: a fix has to land once and reach every repository, the
  tag is immutable and the alias moves only on a release, and pinning was measured to cost ~58
  dependency pull requests to propagate one change. Third-party actions are the opposite case and
  **are** pinned by SHA.

**Safe path:** if you believe a settled decision is now wrong, say so as a question in the pull
request rather than as a finding.

### Suppressions are refusals, not exceptions

`@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`, `eslint-disable` in any form,
`as unknown as` laundering a real type error, `istanbul ignore`, and in Rust `#[allow(...)]` over a
lint gate or `unsafe` without a `// SAFETY:` comment are blocking findings.

Anything a configured gate already reports belongs to the gate, not to a review: where a repository
lints `no-explicit-any` as an error — most do — an `as any` is a red check, and raising it here only
duplicates it. Check the repository's lint configuration before reporting a suppression rather than
assuming the list is exhaustive in either direction.

A failing gate means the code is wrong, the type is wrong, or the rule is wrong. **Safe path:** fix
whichever it is. Changing a rule's configuration with a stated reason is legitimate; scattering
per-call-site silencers is not.

### A key built from more than one field keeps its boundaries

A key or digest derived from **two or more variable fields** must not let a field's content move the
boundary between them. `${tenantId}:${recipient}` makes `('a:b','c')` and `('a','b:c')` one key,
which no digest strength repairs, and one tenant's lookup then resolves another's record. Rejecting
empty fields does not fix it, and neither does a caller that validates its input — the property has
to hold in the construction. A fixed prefix beside a single field is not this shape.

**Safe path:** encode each field so it cannot contain the delimiter, or hash each to a fixed width.
Any other composition needs an argument that every boundary is recoverable, and one bounded field
does not rescue two free ones beside it. Then assert it in a test: where the property holds only
because of the values in play, the next one added takes it away and nothing says so.

### Comments state constraints, never history

A comment must read as true for whoever opens the file next. Flag any comment that narrates what a
previous version did, names a phase, task, ticket or review round, or explains a change rather than
the code. **Safe path:** state the constraint that still holds, and let `git log` carry the history.

Evidence for a constraint is not history, and how the evidence was obtained does not decide which it
is. The test is whether the fact still binds the next reader. A measurement that predicts what they
will hit if they take the other path — what the alternative did when it was tried, what the cost is
in numbers — belongs beside the constraint it supports, whether it came from a deliberate trial or
from something breaking. What ages is the part that cannot recur for them: what a previous version
of this code did, a version number, a registry state, a review round, a failure that has since been
fixed. Flag those; keep the measurement.

### Size and layering

Functions over **50 lines** and nesting deeper than four levels are findings **for what a change
introduces** — a new function, or a change that pushes an existing one past the limit — in the
repository's own source and test directories. A test-suite grouping construct (`describe`, `context`,
`mod tests`, a table of cases) is not a function; the unit under the limit is the body of a single
`it`/`test`/`#[test]`. On the same terms, every non-trivial source file a change introduces opens
with a header stating its purpose and its layer, and every exported symbol a change introduces
carries a doc comment.

**The 800-line file limit applies to what a change introduces, not to what it inherits.** A
repository that already carries a file past the line — a generator, a long end-to-end suite — would
otherwise produce a finding on every pull request touching three lines of it, which the author
cannot act on and did not cause. Raise it for a **new** file over the limit, or when a change pushes
a file past it or materially grows one already over.

Markdown, generated output and lockfiles are **out of scope**: a changelog is an append-only log that
only grows, a lockfile is generated, and neither has layers. Reporting their length is a false
positive on every dependency bump and every release note.

**Safe path:** extract by responsibility rather than by line count — the limit is a symptom, and one
file doing two jobs is the defect.

### Language and attribution

Everything published is English — source, comments, tests, commit messages, pull request titles and
bodies, `README.md`, `CHANGELOG.md` and everything under `.github/`.

Each repository states its language policy for `docs/` below this block. Report a language finding in
`docs/` only against what the repository states; where it states nothing, `docs/` is English like
everything else. A `docs/` language other than English is a repository-owner decision recorded in the
narrowings, not a convention a contributor may introduce.

No commit, pull request, comment or code may attribute authorship to an AI assistant or coding tool,
in any form. **Only text the change introduces is in scope** — a trailer, a "generated with" line, a
signature in a comment or a description.

A commit's author and committer fields are not that: they come from the contributor's git
configuration rather than from the diff, and a review reading the diff cannot see them. Never report
an identity field, and never present a command's reconstructed output as evidence for one. Measured:
twenty-six such findings here, eleven in one repository against four true ones, every SHA resolving
nowhere and every `git log` line unrun — one byte-identical invented identity across all eleven,
which is a template filled rather than an author guessed. Each asked to rewrite published history.

<!-- shared:end -->

## Where this repository narrows a shared rule

### The product is instruction text, so the source-shaped rules move

The shared limits on function length, nesting, file size, header comments and doc comments
apply to the executable files — `scripts/**`, `plugins/*/scripts/**`, `plugins/*/hooks/**` — and
to nothing else. The shared "Markdown is out of scope" applies to **length** only: here the
Markdown under `plugins/*/commands/`, `plugins/*/skills/` and `plugins/*/agents/` is the code,
and it is reviewed for what it instructs. Do not apply TypeScript discipline to a skill file;
do not skip a skill file because it is Markdown.

### An ambiguity in an instruction is a defect

A command file is a contract with a model. A step whose outcome depends on how the reader
resolves it is broken, even when every word is true. Measured: `/bymax-quality:code-review`
did not say that running its greps by hand records no push-gate marker; a session did exactly
that, was blocked, and had to guess why. **Safe path:** state the case, name the measured
failure when there is one, and prefer a table to a sentence when two readings are possible.

### A status the model reports must come with the read that proves it

Any instruction of the form "report X" without "and here is how you know X" invites a report
assembled from expectation. `/bymax-pr:babysit-pr` does this right — "never report success you
did not verify", with the `gh` read named. **Safe path:** pair every reportable state with its
verification, and reject an instruction that names a state without one.

### Load-bearing reasoning is not verbosity

Some passages look like they could be trimmed and exist because the shorter form is the bug:

- The `added()` helper in `code-review.md` uses `--output-indicator-new='>'` so a `+++ b/path`
  header cannot false-positive and a content line starting with `++` is not dropped. The
  "tidier" `grep '^+' | grep -v '^+++'` is the defect it avoids.
- `/bymax-pr:babysit-pr` re-fetches review-thread ids **fresh, this turn** before acting on
  them; the anti-hallucination framing around that instruction is what keeps a stale id from
  becoming a reported resolve.

**Safe path:** a simplification of an instruction needs the same justification as a
suppression — say what the longer form guarded against and why that no longer applies.

### Trigger phrases in `Triggers:` lists may include Portuguese

A `description`'s trigger list exists to match what a user actually types, and this
toolkit's users invoke commands in Portuguese as often as in English — thirteen
command and skill files carry Portuguese trigger phrases by design (`"sobe isso"`,
`"rodar o roadmap inteiro"`, `"instalar codex"`). This is the narrowing the shared
language rule calls for: quoted trigger phrases inside a `Triggers:` list are exempt
from the English-only rule. Nothing else in those files is — prose, field names,
examples and the rest of the description stay English.

### Frontmatter is code

Command, skill and agent frontmatter is parsed at load time and validated by
`scripts/lib/check-frontmatter.py`. The failures that ship silently are an unquoted
`description:` that gains a colon-space (`Modes: quick | full` becomes a nested mapping) and an
unquoted `argument-hint: [a|b]` (a one-element list, not the hint). **Safe path:** quote the
value, double any apostrophe inside single quotes, and run `validate.sh`.

### Suppressions, narrowed to this repository's linters

`validate.sh` runs shellcheck with two project-wide exclusions, each with a stated reason
(`SC1091`, `SC2059`). Those are configuration, not suppression. The tree carries exactly one
per-line `shellcheck disable`, at `plugins/bymax-quality/hooks/secret-scanner.sh:34`, with its
reason on the lines above it (overlapping `case` globs that all lead to the same `exit 0`).
That is the accepted shape and the accepted count: a new per-line disable is a finding, raised
so the reviewer accepts it explicitly, and it needs a reason on the line above it the way that
one has. The Python here carries no suppression comments — `# noqa` and `# type: ignore` are
findings like any other.

### A command change ships with a version bump

Every `plugins/<name>/.claude-plugin/plugin.json` carries its own version, and the marketplace
version moves with any of them. A change to a command file without a bump to its plugin is a
finding: an installed copy sees no update signal. Measured: 1.8.0 had to bump `bymax-pr` after
the fact because #10 changed `push.md` substantially and left 1.1.0 in place. **Safe path:**
bump the plugin, bump the marketplace, add the `CHANGELOG.md` line, in the same change.

### `templates/` holds starters, not this repository's guidance

`templates/AGENTS.starter.md` and its siblings are reference files for **other** projects,
with `{{PROJECT_NAME}}` placeholders. The starter is named so that Codex, applying nested
guidance by file location, does not read a 26 KB fictional project's spec as this repository's
`AGENTS.md` for `templates/` — nor push root plus nested past the 32 KiB cap. A project that
adopts the starter renames it to `AGENTS.md` on copy; `templates/README.md` says so, and the
links in `templates/CLAUDE.md` already target that adopted name — unresolved here by design. Do not
apply the starter's rules to this repository, and do not rename it back here.


## Codex integration

For requests to install this repository into Codex, follow `CODEX.md` and
`scripts/install-codex.sh`. `scripts/install.sh` restores personal Claude settings
and is not the Codex installer. The Codex marketplace root is `codex/`.

Codex-only runtime code and packaging live under `codex/`. Preserve the existing
Claude runtime tree when changing Codex adapters. Run both `./scripts/validate.sh`
and `./scripts/validate-codex.sh`; regenerate bundled references with
`python3 codex/scripts/bundle.py` when their canonical sources change. Apply the
shared executable-source rules to the native Python files in `codex/scripts/`,
`codex/tests/` and `codex/plugins/bymax-codex/scripts/`; the copied resources under
`codex/plugins/bymax-codex/references/upstream/` are generated output.
