# Bounded dual-review protocol

The orchestration layer records evidence; it does not prove that a model's reasoning is
true. Never fabricate a report, test result or disposition to satisfy its schema. The
human remains able to inspect the reports and decide a blocked campaign's next scope.

For a push request, [autonomous delivery](autonomous-delivery.md) supplies the budget,
continuation and reviewer-ownership rules. Enroll with `start --autonomous`: six candidates
shared across this feature branch's pushes, with no automatic renewal after clearance.
Where this document describes a new campaign after clearance, that applies only outside
an enrolled delivery; its next candidate remains a correction delta with the same budget.

## Context and lifecycle

Run helpers from the target repository. Set `FLOW` to `~/.claude/bymax-review/review_flow.py`:
the runtime that `scripts/install-review-flow.py` installs there, beside the hook and the
Bash adapter, is the one that enforces receipts, and the plugin's `scripts/` directory is
its source, not a second runtime. State lives under the shared Git
common directory in `bymax-review/<branch-hash>/`, survives sessions and does not enter
the diff. Put the context and report input files outside the working tree, such as a
private temporary directory. Do not include credentials or unrelated conversation logs.

The context is a JSON object, for example:

```json
{
  "intent": "Requested behavior",
  "acceptance": ["Observable success criterion", "A second one"],
  "measured": ["540 of 540 cached records carry the field the gate reads",
               "not measurable offline: the counter exists only in production telemetry"],
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
- `measured`: **one entry per acceptance item, in the same order**, saying what you ran against
  real data and what it returned — a number, not an adjective. Where it cannot be answered
  offline, write `not measurable offline` and why; that is an honest answer and a recorded one.
  A tree can be self-consistently wrong and no reviewer and no gate can see it: measured
  elsewhere, a correct gate with green tests and thirteen of thirteen mutants caught did almost
  nothing in production because 540 of 540 cached records carry an empty timestamp the date
  floor rejects. Two commands answered it, and nobody ran them because nothing asked. Per item
  or it is theatre — that author had production access and used it twice in the same hour,
  measuring what they were curious about rather than the thing the feature turned on.
  This and required status checks are **two mitigations for one class**, not alternatives: the
  state a machine has and no other machine does, at the tooling layer and at the data layer.

```bash
python3 "$FLOW" status
python3 "$FLOW" start --base <merge-base-sha> --context <context-file>
python3 "$FLOW" prompt
python3 "$FLOW" codex
```

A missing `status` is expected only before the first campaign. `start` is idempotent for
the same HEAD/base/context: reuse recorded reviewers instead of rerunning them. When a
campaign is unfinished, keep its original base and contract — intent, acceptance, constraints,
scope and checks. `measured` is the exception and must move: it records what was run against
real data for the candidate in hand, so a correction that changes the candidate changes it. The
scope guards compare everything but that field. After a batch of committed
corrections, `start` advances the round and sets `review_base` to the preceding candidate.
Both reviewers see the delta plus prior dispositions and inspect impacted callers.

`codex` uses `codex exec` with a custom prompt, read-only sandbox, approval policy `never`,
and no reused thread. It does not use `codex exec review --base`: that interface cannot
combine custom instructions with its scope flags in the installed CLI. The shared prompt
includes explicit Git endpoints instead. Codex receives an output schema and must return JSON without Markdown fences. A report
with `status: incomplete` is rejected even if its findings list is empty.
One failed attempt may be retried for an infrastructure/format error; never retry a valid
review to seek a different opinion, and do not spend the retry on a report whose summary
cites a sandbox or permission denial: the same sandbox fails identically, and `record` says
so. Two of the ways a run can fail are not reviews that failed but a reviewer this machine
cannot run, and those are waived rather than retried — see
[When Codex cannot run](#when-codex-cannot-run). The generated prompt tells both reviewers that the declared checks are the caller's to
run, that they already passed on this candidate, and that anything they cannot execute is a
limitation to state, not `incomplete`. The
Codex sandbox is read-only by construction (`--sandbox read-only`), so no project
configuration makes a test suite or build runnable inside it; a reviewer that reaches for
the suite dies on the first cache write (Jest under `$TMPDIR`, for instance) and the
remedy is the instruction, not the configuration. Each attempt has a ten-minute ceiling. Failure or a
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

## When Codex cannot run

A campaign needs two independent readings of the diff. It does not need them from any
particular vendor, and a machine with no Codex to run is not a product defect, a blocked
push or a reason to edit anything. `codex` therefore has three outcomes, and **the runtime
decides which, from its own probe**. No flag, argument or report a caller passes can
produce a waiver, and a caller's claim that Codex is missing is not evidence of anything.

| What the probe finds | Outcome |
|---|---|
| No Codex at any install location, and none on `$PATH` | waived (`absent`) |
| Codex runs and reports an exhausted account — a usage limit, spent credits, no quota | waived (`quota`) |
| Codex runs and reports it is not signed in | **blocked**: run `/bymax-quality:codex-setup`, then `codex` again |
| Anything else — a timeout, a crash, an incomplete report, an error nobody recognises | **blocked**, exactly as before |

Being signed out is setup, one command away, and waiving it would make deleting a
credentials file enough to clear any candidate. A run that fails without saying why is a
review that did not happen. Classification reads only the error lines Codex ends with,
because the whole prompt is echoed into the same log and a candidate whose own context
discusses a usage limit must not read as one.

The attempt budget does not decide this. An exhausted account is discovered only by
spending attempts, so the candidate that most needs a waiver is the one whose budget is
already gone — a round that hit the wall and retried, and every campaign frozen before
waivers existed. With the attempts spent there is no review left to run, so `codex` asks
the machine a different question instead: an **availability probe**, a prompt asking for
one word, with no diff, no context and no schema. A live account answers it for a token or
two and the spent budget stands (the two failures are a defect to report, not a missing
reviewer); an exhausted one fails exactly as it always does and the waiver is recorded.
The probe never spends a review attempt, has a small budget of its own, and is never run
for a candidate whose Codex report is already on the record.

A waiver does not lower the bar to one reviewer. It changes who the second reviewer is:

```bash
python3 "$FLOW" codex                      # the probe decides; a waiver is printed
python3 "$FLOW" record --reviewer claude   --report <claude-report.json>
python3 "$FLOW" record --reviewer claude-b --report <substitute-report.json>
```

`claude-b` is a second Claude pass in a **fresh-context reviewer subagent that shares
nothing with the first one and nothing with the session that wrote the candidate** — the
same independence the Codex pass provides, from the same generated prompt, which tells
both passes they are standing in for Codex. Running it in the authoring session, or
reusing the first pass's context, produces one reading recorded twice. `record` refuses
`claude-b` on any candidate without a valid waiver, and `triage`, `finish` and the next
`start` all require the pair the waiver names.

A waiver is evidence about a machine at a moment, so it is re-checked and never trusted:
the runtime, the Bash adapter and the `pre-push` hook each re-run the same probe before
honouring one. An `absent` waiver is void the moment Codex is installed; a `quota` waiver
is void unless the binary it named is still the one this machine resolves; both expire
after 24 hours. Codex is resolved from a fixed list of install locations first and only
then from `$PATH`, so a `codex` placed ahead of the real one is not what a waiver measures.
Recording a real Codex report at any point drops the waiver and restores the ordinary pair.

Report the waiver to the user in the campaign's result — which reviewer was missing, why,
and that the second reading came from `claude-b`. `python3 "$FLOW" codex-check` prints what
the probe sees at any time, spending neither an attempt nor a token.

## The reviewer on a decisive round

Most rounds get the standing Codex model. Three do not, and the runtime decides which from
the campaign's own state rather than from a caller that remembers to ask:

- `--design-round`: the approach is under review, not a patch.
- A finding reopened after a claimed fix.
- The last candidate the budget allows.

Those are the rounds where a defect the reviewer misses costs the whole delivery. On them
`codex` adds `-p <profile>` to `codex exec`, layering `$CODEX_HOME/escalated.config.toml`
over the base config through Codex's own profile mechanism.

**The package names the profile; it never names a model.** The slug lives in that one file,
written by the user during `/bymax-quality:codex-setup` from their own answer — the catalog
rots, and a slug committed into a plugin is wrong within a release or two. A machine with no
such file gets exactly today's behaviour, silently: an absent binding is a choice, not a
misconfiguration. `review_flow.py codex-check` reports whether one is bound.

This is a cost and quality argument, not an availability one. The quota pool is shared
across models, so a cheaper standing model buys more runs from the same allowance — but
switching models does not survive exhaustion. The waiver above is what does that.

## Triage and corrections

```bash
python3 "$FLOW" triage --report <dispositions.json>
```

The file is a JSON list with **every** report finding keyed by `claude::<id>`, `codex::<id>` or, on a waived candidate, `claude-b::<id>`:

```json
[
  {"id": "claude::src/job.py:restart-state", "status": "open",
   "evidence": "Reproduced with test_restart; repair only startup transition"}
]
```

Use `[]` if both findings lists are empty. Use `rejected` only with concrete code/test
counterevidence; `deferred` for nits or unrelated pre-existing work with a reason.
A finding whose subject is instruction prose — wording, an ordinal, a count, a comment
naming a round — is deferred and batched, never corrected in a round of its own: only a
finding with a concrete trigger in runtime code or in a gate blocks a receipt. Measured:
a branch spent four campaigns on one command file whose fenced shell no test covered,
and three of the last findings were defects a previous correction to that prose had
introduced. Shell a command file tells a model to run is testable, and
`scripts/tests/test_command_shell.py` tests it; prose around that shell is reviewed once
and then left alone. Keep
accepted defects `open` on the old candidate. A fix is verified by both reviewers on the
next committed candidate, not by marking an unreviewed edit as fixed. Duplicate findings
retain separate provenance entries and refer to the same root cause in their evidence.
Record the triage **while HEAD is still the reviewed candidate**, before committing any
correction: dispositions describe that candidate, `triage` refuses once HEAD has moved
(the message says how to return), and `start` refuses a new round without them.

A confirmed defect needs a failing regression before the fix where feasible, a passing
result after it, and checks of affected contracts. If reproduction is impractical, record
an explicit code-path proof and the verification limitation. Do not invent tests which
merely mirror the proposed fix. If the minimal safe fix crosses the agreed scope, stop and
propose splitting the work. Do not broaden a UI change into an unrelated backend rewrite.

A correction round carries evidence the helper requires and both reviewers see:

```bash
python3 "$FLOW" start --base <sha> --context <ctx> --probe <probe.json> [--design-round] \
    [--no-regression-reason "<why>"] [--nit-round "<why>"] [--after-archived "<authorization>"] \
    [--widen-scope "<why>"] [--answers <path:slug>...] [--extend-delivery "<authorization>"]
```

A correction that adds or changes a test must also show that test failing. `start` refuses one
whose probe carries no `without_fix` entry: a string naming what was reverted and what failed as
a result. Reverting the production change and running the case takes seconds; believing the case
exercises the fix has been wrong every time it was checked, and it was always a reviewer who
checked. The entry is shown to both reviewers, who can re-run it.

Everything a comment, a docstring or a commit message says about the code is a claim with no gate
behind it. Measure it before writing it, or do not write it — a sentence that describes a branch
nobody exercised is read as fact by the next person and by the next reviewer.

`--probe` is a nonempty JSON list of `{"command", "expected", "observed"}`: what the author
ran against the correction before committing it — reproductions of the defect and of the
fix, never the declared project gates, which `check` runs and records. The prompt shows it
to both reviewers with the instruction to verify each entry and go beyond it; shallow
probing is a finding, and a probe a reviewer cannot execute in its sandbox is a limitation
to state in the summary, not a reason to report `incomplete`.
The helper lists every test file added or modified in the delta in the prompt (a renamed
test appears under its new path), so a flipped expectation — as opposed to an added case —
must be justified in triage or is a finding. Deleted test files are listed separately, with
the instruction to judge the deletion; they never count as regression evidence.
A correction that adds or modifies no test is refused unless `--no-regression-reason` records
why, and that reason reaches both reviewers for judgement.

## Retrospective: did the correction cause the finding?

A model cannot tell by rereading its own work whether its correction produced the next
finding; a diff can. At `triage`, every blocking finding whose file the round's own
correction changed is recorded as introduced by that correction, round by round, in the
campaign state. Three things follow, all enforced by `start`:

- `python3 "$FLOW" lessons` prints those findings with their evidence and the checklist
  they imply. Read it **before writing the next correction**, not after.
- Each such finding still open needs a probe entry with `"covers": "<finding id>"`: the
  case it exposed is the case you show being tried. A probe of something else does not
  answer it.
- **One** such triage makes the next round a design round, declared with `--design-round`:
  the mechanism is rewritten against its full case list or deleted, never patched again.
  This waited for two in a row, and waiting is what the second round was spent proving.
  Measured in an unrelated repository on the same loop: when the author finally ran a
  mutation matrix over the whole family instead of patching the latest instance, it found
  two cells nothing in a 3100-test suite covered — in one round, the round that should have
  been the second. Firing on the first is safe only because a finding must carry a `trigger`
  to be counted here at all, so an argument about a sentence in the file just corrected no
  longer forces a redesign.
- Run that case list as a **mutation matrix before committing**, not at round nine: disable
  each rule in turn and confirm a named case fails. Set `PYTHONDONTWRITEBYTECODE=1` and clear
  `__pycache__` between mutants — CPython invalidates bytecode on `(int(mtime), size)`, so two
  mutants of the same size written inside one second serve the previous one's result, and the
  direction that fails is "broke nothing", which manufactures a false claim that a rule is
  uncovered. A source comparison reporting "tree restored" does not clear it. Measured: twenty
  minutes of matrix against three rounds without it, and it found a case that passed for the
  wrong reason and another that built the payload it then asserted on.

Both reviewers are told when the previous correction produced findings, so they look
first at whether the new one repeats the pattern.

`start` refuses a correction round that changes a file no open finding names. This is
where a correction becomes the next review's subject: the finding names one file, the fix
arrives with a mechanism beside it, and the next round is spent on that mechanism. Revert
what the findings do not name and file it as its own campaign, or record why the round
must widen with `--widen-scope "<why>"`, which both reviewers read. Tests and the
generated bundle are how a fix is proved and shipped, so they never count as widening,
and a finding whose id names no file in the tree constrains nothing.

`python3 "$FLOW" range` prints the endpoints the campaign froze, and prints nothing once
they stop being the scope in hand — no campaign, a cleared one, a moved HEAD or a dirty
tree. The mechanical gate in `/bymax-quality:code-review` asks it rather than keeping a
copy: a copy outlives what it describes, and the block then has to guess whether it still
holds. An empty answer means the scope is the working tree against `HEAD`, which is what
a preview reviews.

**A finding blocks a receipt only if it names a trigger.** `trigger` is the command or test,
runnable by the author in this tree, that makes the defect appear; `blocks_a_receipt` requires it
alongside the kind and the priority. Until this the runtime trusted the label a reviewer typed, so
"this docstring contradicts the code" arrived as a P2 defect, `finish` refused to clear it and
refused to let it be deferred, and the budget went on prose. Measured over two campaigns in two
repositories: every finding worth a round could have named a command, and every finding that
wasted one could not. A trigger is a command, never a scenario — "set this variable and wait for a
poll" reads like one and reproduces nothing.

A finding without a trigger is still recorded, still triaged and still shown to the next reviewer,
and `record` names those the reviewer called blocking so the author judges them on their merits.
It simply cannot refuse a receipt. This is the norm the package was alone in violating: a change
that improves the health of the code is approved even when imperfect, and a nit does not force
another iteration
(<https://google.github.io/eng-practices/review/reviewer/standard.html>).

`start` refuses a correction round whose every open finding is one `finish` would not refuse to
leave open — a P3, or a claim with nothing to run — because correcting text no test can check is
where a loop starts. Defer them with their reasons and finish, or batch them into a follow-up; to spend
the round on them anyway, record why with `--nit-round "<why>"`, which both reviewers read.
`start` also refuses to open a campaign on a branch whose earlier campaign was kept aside
without clearing, unless `--after-archived "<who authorised it and for what scope>"`
records the decision, which both reviewers also read. Keep a campaign aside by renaming its
directory, keeping its whole current name and adding to it; that whole name is what the
refusal looks for, so an abbreviated hash is not enough. Renaming `state.json` in place
counts as keeping the campaign aside too, and is found the same way.

A finding open in two consecutive triages has been **reopened**: the previous fix
addressed the instance, not the cause. `start` refuses the next round unless it is
declared `--design-round`, records the reopened ids, and tells both reviewers the round is
about the approach; a patch to the same instance is then itself a finding. A still-open
defect repeated under the prefixed id a reviewer saw in an earlier disposition still names
the same invariant: keys are `reviewer::<id>`, whose two parts stay recoverable by one
split from the left, so `record` removes **one** copied prefix from a finding id and
refuses an id that still begins with `claude::`, `claude-b::` or `codex::` — such an id is not
representable, and removing prefixes until none was left would let an id's own content
move the boundary. A repeat within one report is a duplicate, and a finding on a real
file under a `codex/` directory is exactly what it says.

The Claude pass on a correction delta is performed by a fresh-context subagent given only
the generated prompt, never by the session that authored the fix.

Run every required gate named in the context **after the candidate commit and before either
reviewer reads it** — `prompt` refuses to build the reviewer task until every declared gate has
run and passed on this candidate, and that includes the `codex` and `claude` commands, which
build the same text. The gates ran on the way to `finish` until this; that ordering asked two
readers to judge a tree nobody had checked, and a round spent on a failure the suite already
prints is a round not spent on what only a reader finds.

```bash
python3 "$FLOW" check -- <executable> <arguments>   # before the reviewers, every round
python3 "$FLOW" finish
python3 "$FLOW" status
```

The helper captures command, exit code and output. A nonzero check cannot be cleared by
running a different trivial command; rerun the same failed command successfully after
fixing its cause. The helper requires every command declared in the context. It cannot infer whether that
list covers the project's requirements: check it against project docs before starting.

`finish` requires both reports — `claude` and `codex`, or `claude` and `claude-b` where the
probe waived Codex — every disposition, no open or deferred confirmed P0–P2 blocker, a
clean matching HEAD, and passing check records. Same-HEAD reuse is intentional.
New work after a completed campaign starts a new full campaign. Exhausting the round
budget hands the campaign to the human who authorised the work: report the blockers and
the proposed scope, and wait. Keeping the state aside and starting over needs that
human's explicit authorization **for that campaign** — an authorization given once is not
standing, and a second campaign on the same finding is the signal to stop and hand over,
not to archive again. A round whose Codex
budget is spent on failures the probe did not waive cannot complete: `triage` needs both
reports and `start` needs the triage. The exit is the same as for any stalled campaign, and `codex`
says so when it refuses. A stalled campaign has
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
policy is kept as merged. A custom `core.hooksPath` directory is never written into: its
`pre-push` qualifies by behaviour alone, so a generated stub that delegates to a tracked
hook — husky's `.husky/_/pre-push` running `.husky/pre-push` — qualifies when the hook it
runs invokes `review_prepush.py`, and survives the stub being regenerated. In either
place, a hook that declares another policy or is not executable is refused at `start`,
with the remedy named. Before
the candidate is frozen, `start` also runs that hook seven times as git would (from the
worktree root, through `sh` when it has no shebang, within 60 seconds each, with origin's
name and URL as arguments), feeding it one push line shaped like a real push: a temporary
ref under `refs/bymax-review/`, resolving to a dangling child of HEAD built from the
current tree in the user's own git identity, fast-forwarding the current branch. That
commit exists, has a parent, and its ref resolves to it. The pushes differ in what
names that commit, and each is described by what it carries rather than by its position,
which the runtime is free to change:

- **with no receipt** — the hook must refuse it, or it does not enforce receipts at all;
- **with a held receipt** — the helper holds a temporary completed receipt for that commit
  in a directory of its own under `bymax-review/`, so concurrent starts in linked worktrees
  do not disturb each other, and the receipt is valid only while the probe holds a lock on
  the `holder` file beside it, which the kernel releases with the process. The hook must
  let this push through; one that refuses it is refusing for a reason the probe does not
  satisfy (a local ref that is not a branch, for instance) and is refused as not consulting
  receipts;
- **with that receipt unheld**, the shape an interrupted probe leaves, and **with one naming
  a pid and nothing to hold** — the hook must refuse both, since a probe receipt nobody
  holds is void whatever pid is reused later. A hook that accepts either honours such a
  receipt, as a copy of an earlier checker does; it is refused, and the remedy named depends
  on the path: deleting it has `start` reinstall the bundled hook only where `start` writes,
  which is never a custom `core.hooksPath` directory — there the refusal says to point it at
  the current checker and not to delete it;
- **three pushes of three refs**, as git does for a push of three refs, each record with
  its own remote ref and the first fast-forwarding the branch: the unreceipted commit takes
  each of the three positions in turn while the receipted one fills the others. The hook
  must refuse all three, and a hook that leaves any one record unchecked reads only
  receipted commits in the push whose unreceipted record it skips; accepting any of them
  means an unreceipted commit went unchecked.

Every refusal names the remedy; a kept file is never rewritten, so a check merged into it
by hand survives. The refs and the directory are removed afterwards, and what
an interrupted probe left behind is swept by the next probe once older than a probe
can be. Hook code written to recognise the probe is trusted code and outside what a
local probe can establish, as is a hook that filters records by a property these
records share: the pushes raise the floor a kept hook must clear, they do not certify it.
A receipt completed under another policy does not authorise its commit: the hook and
the adapter require the current policy.

`review_push.py` is a Claude **PreToolUse Bash adapter** in front of that hook, with two
narrow jobs. It recognises exactly `[cd <path> &&] [VAR=value ...] git [-C <dir>] push
<remote> <refspec>...` and performs the receipt lookup for that form, so a missing receipt
is reported with a useful message before git runs; for that form, implicit, wildcard,
mirror, followTags, deletion and chained pushes fail with a corrective message, and
another worktree's receipt cannot authorize a different SHA. It also refuses any command
containing an option that would skip or redirect the hook (`no-verify`, `hooksPath`,
`GIT_DIR`, `--git-dir`, `GIT_WORK_TREE`, writes under `.git/hooks`) or husky's own skip
switch (`HUSKY=`, honoured by its dispatcher before the tracked hook runs), matched as a
substring wherever it appears, in the raw command **and** in its words after quote removal —
a token split across quotes is absent from one and present in the other. Quote removal is less
than the shell does: `shlex` performs no parameter expansion or command substitution, so a token
assembled by the shell from `${...}` is in neither form, and that is one spelling of the residue
this section ends with — **but only where the command could reach a remote**, which
means it contains `push` and names a program able to start another (`git`, a shell, `eval`,
`env`, `xargs`, `ssh` and the like; an unparseable command counts as yes). A command that
merely names one of these tokens — grepping for the string, `cat` or `shasum` of a hook path, the
two piped greps this repository's own command files prescribe — is not scanned at all. Reading a
hook **through git** is the exception and is refused: `git log -- <hook path>` names a runner, and
the path itself spells `push`. That is a false refusal of the class this section exists to remove,
left standing deliberately rather than closed by another rule about what a word means; it is
recorded as a deferral of this campaign.

**It does not defend the hook file, and says so rather than appearing to.** Two rounds of this
campaign were spent trying. The first exempted "commands that only read" by listing the programs
that qualify, and both reviewers emptied that list in one round: `rg --pre CMD`, `ack --pager=CMD`
and `git ls-remote --upload-pack=CMD` each run a program the caller names while reading, and one
of them deleted an installed hook end to end while the adapter returned exit 0. The second
compared the hook against a record `start` wrote, and that was inert in four independent ways — no
record exists on any installed copy until the next campaign, one unrefused `rm` removes it, a
malformed one becomes a push refusal, and the recorded path can diverge from the path git runs
hooks from.

The reason is structural, and this document already stated it about deliberate evasion: a session
that can run arbitrary shell can undo any local check that a local check could observe. What holds
instead is what always held — `start` reinstalls and re-verifies the hook, and a candidate cannot
clear without `start`; the hook receives the pushed SHAs from git itself, so no spelling of a push
command evades it **once git runs it** — a spelling that stops git running it, a redirected hooks
path the scan cannot see, does, which is exactly the residue named at the end of this section; and
required status checks are the boundary for anything deliberate. Writes
under `.git/hooks` stay in the token list for a command that could reach a remote, where they can still
do something.

**Every other command passes through untouched**: a push
spelled in any other arrangement is not the adapter's to judge, and the hook decides.

The adapter is not the enforcement boundary and is not described as one. The residue no
local design closes is a hook-skipping option spelled so the adapter's substring check
cannot see it, since git itself provides that escape; the tests document it, and CI is
the boundary for deliberate evasion. A command that removes the hook is no longer refused,
and nothing local refuses the push after it either when that push is spelled in a shape this
adapter does not recognise. That residue is named here rather than papered over, because two
attempts to close it locally were each bypassed in the round after they shipped. A completed review is evidence of coverage, not a
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
