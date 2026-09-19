# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **A fresh reader corrects the prose before the candidate freezes, inside an envelope a function checks** — `review_flow.py prose` runs on a committed, not yet frozen candidate: it hands the prose this delta added, with the code it describes, to a Claude that has never seen the author's reasoning and may edit comments, docstrings and markdown; then `review_prose.py` reads what came back and refuses — reverting every edit — if a Python file's behaviour changed, where behaviour is the syntax tree with every docstring removed, or if any file's prose grew. Comparing trees rather than lines is what lets the pass correct the comment at the end of a line of code, the commonest edit there is, while refusing the edit that changes the code beside it; a line-based envelope had to call such a line one thing or the other and was wrong for half the edits. The record binds to the text the pass left — the files the delta touched and a digest of their contents — and `start` recomputes that digest on the candidate, so a candidate whose prose is anything else was not read and is refused. The logic reviewers are told: a finding whose remedy is rewriting a comment, a docstring or a paragraph is not a finding here, unless the sentence states something false about the code that a reader would act on. Measured on the campaign that shipped the claims checks: 3 of the 6 findings in its final round were about prose, and the corrections answering prose findings wrote 203 lines of prose against 19 of code — the answer to a prose finding was more prose. Inside a Claude session, which cannot start another Claude, `prose --stage prepare` hands the task to a fresh subagent and `--stage verify` checks what it left; `verify` requires a marker `prepare` wrote on a clean tree, so what the worktree holds is the pass's own and never the author's edits blessed as prose.
- **The mutation matrix is measured by the runtime, not reported by the author** — `review_flow.py matrix` runs it and keeps the result; `--probe` never could, because "observed: the mutant fails the case" is a sentence. Three things an author's report cannot establish are checked: the anchor occurs exactly once (zero means the mutation never landed, and this package's own history records a matrix that printed `69 passed` with nothing applied), the case passes on the clean tree first (failing with a mutant says nothing when it fails without one), and it then fails. A survivor stops the run. Each rule also declares how its cases were enumerated: where that is a command it is executed and a list shorter than its own count is refused; where it is not, saying so is required, and that admission is the useful half — a rule nothing can enumerate mechanically is a mechanism not yet understood well enough to correct. A correction that changes a test carries a record bound to its head, because a gate lives in a test and every vacuous gate measured across two repositories passed its own suite. This is not tamper-proof and is not claimed to be: it removes the easy path, which until now was typing.
- **Claims a command can settle are settled before the review** — `review_claims.py` refuses a candidate whose comments or documentation name something this delta removed from the code, when that name is spelled like code rather than like an English word — measured at no false positive across 40 mainline commits. A second check, for a removal claimed of text still present, reports and never refuses: the same 40 commits produce one, a backticked shell command read as the subject of a sentence beside it, and one wrong refusal in forty is a delivery blocked by mistake. A third check — one subject given two counts in a delta — was built and deleted: measured on a real delta it produced seven false positives and no true one, because a docstring narrating history states many numbers about many things. A heuristic at that precision trains a reader to skip the report the exact checks live in. What no command settles is counted and named as unchecked, so silence stops reading as proof. Reviewers receive the delta with prose hunks elided, the ratio of code to prose it changed, and the count of files these checks could not read at all — only Python and Markdown are classified, so on a repository of other languages the checks are silent, which is not the same as clean.

- **The declared gates pass before a reviewer reads the tree** — `prompt` refuses to build the reviewer task until every gate the context names has run and passed on this candidate, and names the ones missing or failing with their exit codes. All three routes to a reviewer — `prompt`, `codex`, `claude` — build that text, so the rule has one home and no bypass; the task now tells both reviewers the gates already passed, which narrows their search rather than only restricting it. The gates used to run on the way to `finish`, after both readings, which asks two readers to judge a tree nobody has checked. Measured: two rounds of one campaign went to a test that read the developer machine's Codex and a bundler that swept a local cache into the shipped manifest, and a gate names either in seconds.
- **A finding blocks a receipt only if it names something to run** — `blocks_a_receipt` requires `trigger`, the command or test runnable by the author in this tree that makes the defect appear. The runtime used to trust the label a reviewer typed, so "this docstring contradicts the code" arrived as a P2 defect, `finish` refused to clear it *and* refused to let it be deferred, and the round budget went on prose. Measured across two campaigns in two repositories: every finding worth a round could have named a command, and every finding that wasted one could not. A finding without a trigger is still recorded, still triaged and still shown to the next reviewer — `record` names the ones a reviewer called blocking so the author judges them on their merits — it simply cannot hold the receipt. The runtime never executes a trigger: that text comes from a reviewer report, and the same task tells both reviewers to treat repository text as evidence rather than instructions. This is the industry norm the package was alone in violating: approve a change that improves the health of the code even when imperfect, and let a nit be a nit.
- **`measured`: one line per acceptance item, against real data** — the context contract requires, for each acceptance criterion in order, what was run against real data and what it returned; `not measurable offline` plus a reason is an honest answer and a recorded one. A tree can be self-consistently wrong and no reviewer and no gate can see it: measured elsewhere, a correct gate with green tests and thirteen of thirteen mutants caught did almost nothing in production, because 540 of 540 cached records carry an empty timestamp the date floor rejects. Two commands answered it and nobody ran them because nothing asked. Per item or it is theatre — that author had production access and used it twice in the same hour, measuring what they were curious about rather than the one thing the feature turned on. This and required status checks are two mitigations for one class, not alternatives: state the author's machine has and no other machine does, at the tooling layer and at the data layer.
- **A correction must show its case failing without the fix** — `start` refuses a correction round that changes a test unless a probe entry carries `without_fix`: what was reverted, and what failed as a result. The protocol asked for "a test case that fails on the current candidate" and never for a demonstration. Measured across two campaigns: every case an author believed exercised the fix and never watched fail turned out not to, and a reviewer found it every time. A second rule, which the package had only ever asked of reviewers, now applies to the author: a comment, a docstring or a commit message is a claim with no gate behind it, so measure it before writing it or delete the sentence.
- **The reviewer escalates on decisive rounds, by profile and never by slug** — most rounds get the standing Codex model; three do not, and the runtime decides which from the campaign's own state rather than from a caller that remembers to ask: a `--design-round`, a finding reopened after a claimed fix, and the last candidate the budget allows. On those, `codex exec` gains `-p escalated`, layering `$CODEX_HOME/escalated.config.toml` over the base config through Codex's own profile mechanism. **The package names the profile and never a model** — the slug lives in that one file, written by the user during `/bymax-quality:codex-setup` (new Step 2.5, which reads what is already there, asks, writes only the user's own answer, never overwrites, and is skipped entirely on an unattended run). A machine with no such file behaves exactly as before, silently: an absent binding is a choice, not a misconfiguration. `codex-check` reports whether one is bound. The motivating measurement, from a second machine: a plan's quota is one pool shared across models, so the most expensive model as the *standing* default is what empties an account fastest — a campaign spends up to two attempts per candidate across six candidates. A new troubleshooting row says so, and says that switching models does not restore quota.

### Changed

- **The installer derives what it copies** — a hand-kept tuple decided which runtime scripts reached `$HOME`, and a script nobody copies is a gate that does not exist, silently, because the flow imports it only when the case it guards occurs.

- **One self-inflicted round is already a design round** — the mechanism-level rewrite used to wait for two consecutive corrections that produced the finding they were then reviewed for, and waiting is what the second round was spent proving. Measured in an unrelated repository on the same loop: running a mutation matrix over the whole family instead of patching the latest instance found two cells nothing in a 3100-test suite covered, in one round — the round that should have been the second. Safe to fire this early only because a finding must now carry a trigger to count as blocking. `lessons` and both documents also ask for that matrix **before the commit** and name the way a matrix lies: CPython invalidates bytecode on `(int(mtime), size)`, so two mutants of the same size written inside one second serve the previous one's result, and the direction that fails is "broke nothing", which manufactures a false claim that a rule is uncovered.
- **A blocked phase parks the autopilot chain instead of ending it** — the termination table had no row for a review campaign that spends its candidate budget, and its nearest row is about project gates, a different event. `STEP 0` now collects the parked set, reads the roadmap's dependency graph — which existed and which the orchestrator never read — and picks the lowest-numbered phase whose transitive dependencies hold no blocked phase, capped at three parked phases. Refusing to merge past a confirmed blocker stays; letting that refusal end the whole run does not. A wrong graph degrades safely: a phase built on missing work fails its own gates, which the existing "3 full fix cycles" row already terminates.
- **The reviewer task names the one base a report may carry, and the waiver is per candidate** — `record` rejects a report whose `base` is the campaign's original rather than the round's `review_base`, the two differ on every correction round, and the prompt printed both with equal billing; two authors in two repositories hit "Report scope mismatch" that way. The task also asks for every comment, docstring and commit-message claim to be checked against the code, which no lint or type gate can see, and the substitute refusal now says a waiver is evidence about one candidate, so the previous round's does not carry.
- **A Codex this machine cannot run is waived, not a blocked push** — a campaign needs two independent readings of the diff; it does not need them from any particular vendor. `review_flow.py codex` now classifies its own failures: no Codex at any install location and none on `$PATH`, or a Codex that runs and reports an exhausted account, records a **waiver** and the second reviewer becomes `claude-b`, an independent fresh-context Claude pass recorded with `record --reviewer claude-b`. Everything else still blocks exactly as before — a timeout, a crash, an incomplete report, an unrecognised error, and deliberately a Codex that is **installed but signed out**, which is setup one command away and whose waiver would make deleting a credentials file enough to clear any candidate. Classification reads only the error lines a run ends with, because the whole prompt is echoed into the same log and a candidate whose own context discusses a usage limit must not read as one.

  **The caller never decides this.** No flag, argument or reviewer report can produce a waiver: the runtime writes one from its own probe, and nobody honours it on trust — the runtime, the Bash adapter and the `pre-push` hook each re-run the same probe before accepting a receipt. An `absent` waiver is void the moment Codex is installed, a `quota` waiver is void unless the binary it named is still the one the machine resolves, and both expire after 24 hours. Codex is resolved from a fixed list of install locations before `$PATH`, so a `codex` placed ahead of the real one is not what a waiver measures. Recording a real Codex report at any point drops the waiver and restores the ordinary pair. `review_flow.py codex-check` prints what the probe sees, spending neither an attempt nor a token.

  **The attempt budget does not decide availability.** An exhausted account is discovered only by spending attempts, so the candidate that most needs a waiver is the one whose budget is already gone — a round that hit the wall and retried, and every campaign frozen before waivers existed. With the attempts spent there is no review left to run, so `codex` asks a different question: an **availability probe**, a one-word prompt with no diff, no context and no schema. A live account answers it and the spent budget stands (the failures are a defect to report, not a missing reviewer); an exhausted one fails as always and the waiver is recorded. The probe never spends a review attempt, is bounded on its own, and never runs for a candidate whose Codex report is already on the record. Asking the machine now, rather than reclassifying an old log, is also what makes credits that came back visible — and keeps a file on disk from becoming a way to claim a reviewer is missing.

  The receipt rule lives in the `pre-push` hook, so `start` now probes a kept hook with a waived receipt built from **the runtime's own view of the machine**, which it requires the hook to share — accepting a current one, refusing an expired one — and a hook that predates the shape is named instead of silently blocking every waived push. An untouched bundled hook from an earlier release is replaced by hash; a hook somebody merged a check into is still never overwritten. That view is taken in a bounded subprocess fed no stdin, because a hand-merged hook runs its check at import — in-process, its `sys.exit()` is a `SystemExit` no `except Exception` catches and a read of stdin never returns — and the answer carries a per-call nonce so a hook that prints the fixed marker at import announces a view instead of being asked for one — not a defence against a hook that means to lie, which needs no view to defeat a check it is itself running. What is required instead is agreement: a kept hook whose view of this machine differs from the runtime's is refused and reported, because it would pass the receipt-shape probes and then refuse every real waived push. The waiver records the stable path and never the file a symlink points at, so a routine upgrade inside the window cannot void a receipt that already cleared; the hook and the runtime must agree on that name, which is why the previous bundle's hash joins the superseded set. `review_flow.py claude --as claude-b` drives the substitute through the constrained CLI adapter for Codex-led delivery, and each pass has its own attempt budget.

### Fixed

- **What this repository did not write is derived, not listed** — the prose gate's exclusion list was a hand-kept tuple, and it moved twice losing something each time: first it let the vendored trees be read, then, excluding their parent to keep them out, it took `vendor/README.md` with them — a document this repository wrote about why the folder exists. It is derived now from two markers that exist for their own reasons: `ATTRIBUTION.md`, written beside a vendored tree's `LICENSE` to record where it came from, and the bundler's own `PACKAGE` constant, which names the mirror it generates. A third vendored tree added tomorrow is excluded by the derivation without anyone remembering to say so, provided it arrives with the LICENSE the convention puts beside that marker — one marker alone is not proof, or a repository-authored file could take its own directory out of the gate, and both markers are read from the index, since a LICENSE nobody committed is not this repository saying a directory is somebody else's. What guards the derivation against shrinking is not a rule about what it leaves — four were tried and each let something through. A floor of 100 against 130 sources passed at 129. Comparing top-level directories asked the derivation for the side it was checking against, and `plugins` stays in the set while eight of nine remain. Requiring each plugin to contribute a file missed every shrink that is not plugin-shaped. What replaced them is not a rule but an identity: what the gate reads must be exactly the tracked `.md` and `.py` files minus the vendored roots, named in the test as literals. It fails a shrink of any size and a growth too, so the derivation gets no benefit of the doubt in either direction. The cost is deliberate and worth stating: a fourth vendored tree needs no edit for `foreign()` to exclude it, but does need one line added to that literal before the gate agrees — the derivation is the mechanism and the literal is the independent check on it, and a check that updates itself from the mechanism is the failure this identity exists to end.
- **The rule about which refusals share a remedy has a gate** — every writing of that sentence has been found false — some as counts, which drifted, the rest as rules whose scope excluded refusals that do ask the helper or included ones that do not. What replaced them is that there is no summary: the set is enumerated by a test, and the prose says which question `hook_remedy` answers rather than who asks it.
- **A re-measurement is not a scope change** — the `measured` contract above closed a ring on every delivery older than it: `context_contract` refused a context without the field, and the round guard and the per-branch delivery ledger both refused the edit that would add it. Reported from another repository, where a campaign sat at four of six candidates with no finding open. Reproducing it turned up the half nobody had hit: the field was write-once even in a campaign that started with it, so a second reading of the same contract was refused as a scope change — the field could not record what it exists to record. The guards were comparing evidence as if it were scope. `scope_of()` excludes `measured` and is called from all three; the ledger stores the reading of the candidate it froze, and `start` stores a corrected reading for the candidate in hand, because the reviewer task interpolates it verbatim. Any change to intent, acceptance, constraints, scope or checks is refused exactly as before.
- **The corrections that had no gate now have one** — five rules this package relies on were held only by whoever remembered them, and a mutation sweep is what said so. `own_index()` compares directory identity rather than resolved names, which is the defect the Codex bundle was rebuilt around; reverting it to name equality left the whole suite green, so an ignored file could become a canonical resource again in silence. The case now drives the bundler through a **real second name for the same directory**, detected at runtime — a case-insensitive volume or a macOS firmlink — and skips with a named reason where the filesystem offers neither, because a symlink cannot stand in: `resolve()` collapses it, so it does not discriminate. Both aliases are macOS-only, so **this gate guards a developer's machine and not CI**, which runs on Linux and skips it; no portable alias exists to close that, and the limit is recorded in the case rather than implied by a green pipeline.
- **A dangling case name in prose is now a failing test** — two findings of the previous campaign were exactly that: a docstring pointing at a case deleted in the same delta, and a claim surviving in a third file after being corrected in two. A name is the one part of prose a machine can resolve, so it is the part that gets a gate. It reads docstrings, comments and markdown outside fenced blocks, and both exclusions were measured rather than guessed — a probe's example command names a case in an imagined project, and so does the protocol's triage sample. The gate then flagged its own docstring, which is why the examples in it are described and not spelled.
- **The substitute reviewer is refused before its attempt is spent** — `record` rejects `claude-b` without a waiver the runtime's own probe wrote, and the CLI adapter had already reserved a bounded attempt by then: two refusals exhausted the per-pass budget with nothing read. The predicate and its message now live in one function called from both places, which is why this waited — a second copy that drifts is worse than a wasted attempt.
- **A probe receipt outlasts the hook that reads it** — the temporary receipt was dated exactly `HOOK_SECONDS` inside the waiver window, so a kept hook that used its whole time budget would watch the waiver expire mid-run and refuse it, and the runtime would report "shorter waiver window" for what was a timeout. The margin is derived from the bound now, and a case asserts the two are not equal.
- **A custom hooks directory is no longer told to delete its hook** — each refusal worded its own remedy, and the ones offering deletion were wrong wherever `core.hooksPath` is set. `start` writes only into the repository's own hooks directory and never into a `core.hooksPath` one, so for that reader the remedy was a way to end up with no check at all. One function answers which case the message is in: given this path, is deleting the hook a remedy or a way to end up with no check at all. Which refusals ask it is not summarised anywhere — every attempt at that sentence has been found false — and is instead enumerated by a test, where a refusal that stops asking fails.
- **Five sentences a measurement refuted** — a changelog claim stronger than the probes behind it, a pointer to a residue named in another file, a comment attributing a message to a function that only speaks when git is absent from `$PATH`, a justification citing a direction quote removal cannot produce, and a suite docstring asserting that no spelling of a push reaches a remote while carrying git's own escape sixty lines below it.
- **The push guard stops refusing commands that only read** — the disarming scan ran as a substring match over every Bash command before any parsing, so `git rev-parse `--git-dir`` was refused, and `/bymax-pr:push` Step 0 prescribes exactly that command; a `shasum` of a hook path, a `grep` whose *pattern* held one of the tokens, an `echo` of the same text, and the two piped greps this repository's own command files tell a model to run were refused too, each also injecting an "AUTOMATIC CONTINUATION: run a campaign and retry the push" instruction into a session that was not pushing. A guard that blocks reading protects nothing and teaches whoever meets it to phrase commands to slip past a matcher.

  The first attempt at the exemption listed the programs that only read, and it was wrong in a way worth recording: two independent reviewers emptied that list in one round. `rg --pre CMD`, `ack --pager=CMD` and `git ls-remote --upload-pack=CMD` each run a program the caller names while reading, and one of them deleted an installed hook end to end while the adapter returned exit 0. The set of such flags across the set of such programs has no closed form, so the question "which command is dangerous" is not asked any more. One decidable question replaces it: **could this command reach a remote** — its words, after quote removal, contain `push` and name a program able to start another, an unparseable command counting as yes — and only then is it read for a hook-skipping option, as strictly as before, in the raw text **and** in those words, because a token split across quotes is absent from one and present in the other.

  **The adapter does not defend the hook file, and now says so instead of appearing to.** Two designs tried and both were bypassed in the round after they shipped: the allowlist of reading programs, emptied by `rg --pre`, `ack --pager` and `git ls-remote --upload-pack`; and comparing the hook against a record `start` wrote, which was inert in four independent ways — no record exists on an installed copy until the next campaign, one unrefused `rm` removes it, a malformed one becomes a push refusal, and the recorded path can diverge from the path git runs hooks from. The reason is structural and the protocol already stated it about deliberate evasion: a session that can run arbitrary shell undoes any local check a local check could observe. What holds is what always held — `start` reinstalls and re-verifies the hook and a candidate cannot clear without `start`; the hook receives the pushed SHAs from git itself, so no spelling of a push command evades it **once git runs it** — a spelling that stops git running it does, and no local check closes that; and required status checks are the boundary for anything deliberate. Writes under `.git/hooks` stay in the token list for a command that could reach a remote, where they can still do something.

## [2.0.0] — 2026-09-16

Cut at `001831a`. This release covers everything after `v1.12.0`, including the work tagged
`v1.13.1`, for which no section of its own was written.

**Breaking:** the marketplace id moved from `bymax-claude-code` to `bymax-agent-kit`. The GitHub
URL redirects; the id does not. An existing install runs
`claude plugin marketplace remove bymax-claude-code`, adds `bymaxone/bymax-agent-kit`, and
reinstalls each plugin under the `@bymax-agent-kit` suffix. Plugin names, command names, hooks and
user settings are unchanged, and the Codex ids (`bymax-codex@bymax-codex`) are unaffected.

### Changed

- **Renamed to Bymax Agent Kit: marketplace `2.0.0`, every plugin patched, Codex `1.1.1`** — the repository is `bymaxone/bymax-agent-kit` and the marketplace id is `bymax-agent-kit`. The project ships two packages built from one canonical `plugins/` tree — the Claude Code marketplace and the Codex plugin — so a name that said "claude-code" described one of its two runtimes. **Breaking for existing installs:** the GitHub URL redirects, the marketplace id does not. Run `claude plugin marketplace remove bymax-claude-code`, add `bymaxone/bymax-agent-kit`, and reinstall each plugin under the new `@bymax-agent-kit` suffix. Plugin names, command names, hooks and user settings are unchanged. `scripts/install-review-flow.py --local-plugin-overlay` now resolves a plugin cache installed under either marketplace id and refuses ambiguity when both exist, with regression tests for both cases; the Codex marketplace id `bymax-codex` is unaffected.

- **Documentation rewritten for two runtimes** — the README leads with Claude Code *and* Codex (logo badges, a per-runtime quick start, a "what runs where" capability table that marks adaptation rather than claiming parity, and a migration section), promotes the bounded dual review from a stray tail section into the body with its real command sequence, and replaces the architecture tree with one that includes `codex/`, the review runtime under `plugins/bymax-quality/scripts/`, the root `scripts/` installers and gates, and the top-level docs. `AGENTS.md` now describes both packages and all four verification gates instead of `validate.sh` alone; `CONTRIBUTING.md` documents the bundle-then-bump rule, the behavioral suites and the Codex manifest bump; `llms-install.md` gains the review-runtime step, the Codex pointer and four failure rows; every plugin README names its Codex entrypoints. Corrected against the code: the pre-push checker is installed by **every** `start`, not only `start --autonomous`; the Codex CLI is **required for dual-review certification** rather than optional; the post-implementation chain reviews a committed candidate and verifies findings instead of applying every one.

- **Round retrospective: marketplace `1.17.0`, quality `1.10.0`** — at every triage the runtime records which blocking findings sit in files the round's own correction changed, one entry per round with its evidence; a rejection with counterevidence excludes a finding. `review_flow.py lessons` prints them for the author before the next correction; a finding the previous correction introduced needs a probe entry naming it (`covers`); two consecutive such triages make the next round a design round whose brief names the reason; both reviewers are told when the previous correction produced findings. `/bymax-quality:code-review` step 5 reads `lessons` before any correction.

- **Autonomous delivery: marketplace `1.16.0`, quality `1.9.0`, workflow `1.7.0`, PR `1.3.0`, Codex `1.1.0`** — share a six-candidate shipping budget across pushes and completed campaigns, continue a hook-blocked push through certification, assign independent reviewers to the orchestrator, and add a constrained Claude CLI adapter for Codex-led dual review. Add complete installation/diagnostic guidance and regression tests for budget continuity and reviewer failure. A correction after a cleared candidate names what it answers with `--answers <path:slug>`, so the correction-scope rule measures it against those files instead of going blind once no finding is open; a spent delivery budget is an alarm a human answers with `--extend-delivery "<who, why>"`, recorded in the ledger and shown to both reviewers, never by deleting the ledger.

- **Receipt hook lifecycle** — `start` keeps a hand-merged pre-push that carries the check at the current policy, accepts a custom `core.hooksPath` directory by the behaviour of its pre-push alone (never writing into it; a husky stub delegating to a tracked `.husky/pre-push` that invokes the check qualifies and survives regeneration), and refuses a hook that declares another policy or is not executable, naming the remedy; before freezing a candidate it runs the kept hook seven times, from the worktree root, with a push shaped like a real one (a temporary ref resolving to a dangling child of HEAD in the user's identity, fast-forwarding the current branch) — with no receipt, which the hook must refuse; while a held temporary receipt names that commit, which it must accept; with that receipt orphaned, with a pid-only receipt nobody holds, and with three three-ref pushes that give an unreceipted commit each position in turn, all five of which it must refuse — so a marked hook that consults no receipts, honours an unheld probe receipt, or leaves any stdin record unchecked is refused; the pushes raise the floor a kept hook must clear rather than certify it, and hook code written to recognise the probe is trusted code. A kept hook file is never rewritten; a copy of an earlier checker is refused by the third or the fourth push until deleted or repointed. The temporary receipt is valid only while the probe holds a lock the kernel releases with the process, so pid reuse cannot revive it; what an interrupted probe leaves behind is swept once older than a probe can be. The Bash adapter also refuses `HUSKY=`, husky's own skip switch. Receipts completed under policy 1 do not authorise a push: the hook and the adapter require the current policy. The protocol names `~/.claude/bymax-review/review_flow.py` as the one runtime, says to record triage on the reviewed candidate before committing corrections, keeps declared gates out of `--probe`, has the generated prompt tell both reviewers that declared checks are the caller's to run and that anything they cannot execute in their read-only sandbox is a limitation to state rather than `incomplete`, says, when an incomplete report cites a sandbox denial, that a retry fails identically and that no configuration makes the read-only reviewer sandbox writable, and states the exit when the Codex budget is spent; `triage` names the way back when HEAD has moved and lists the missing or unexpected keys. Deleted test files are listed for reviewers without counting as regressions. The hook peels annotated tags before the receipt lookup. Each reviewer's open disposition needs its own resolution. The Bash adapter matches hook-disarming options case-insensitively.

- **Review keys are `reviewer::<id>` (state policy 2)** — triage and resolution keys no longer share the `/` separator with paths, so a copied key and a real file under a `codex/` directory cannot collide; campaigns frozen under policy 1 are refused with the restart message. The two parts of a key stay recoverable by one split from the left: `record` removes one copied reviewer prefix from a finding id and refuses an id that still begins with one, rather than stripping until none is left.

- **Correction rounds carry evidence: marketplace `1.15.0`, quality `1.8.0`, pr `1.2.0`, codex `1.0.2`** — `review_flow.py start` on a correction round requires `--probe` (the author's own attempts to defeat the fix, shown to both reviewers), lists every test file the delta changed so a flipped expectation is a finding, refuses a correction that touches no test unless `--no-regression-reason` records why, and refuses a round whose previous fix reopened a finding unless it is declared `--design-round` — that round reviews the approach, not the instance. The Claude pass on a correction delta runs in a fresh-context subagent, never in the authoring session. `/bymax-pr:push` now obtains the review receipt itself, end to end, before pushing; it stops only when the protocol blocks. Six review rounds on the push guard each reopened the same invariant before these rules existed.

- **Command-file shell is tested, not just read** — `scripts/tests/test_command_shell.py` extracts every fenced `bash` block from the plugins' command and skill documents and requires each to assign what it reads (shell state does not cross a fence), to ask for no value to be pasted into shell source (a ref name may carry `$( )`), and to pass shellcheck when it carries no placeholder; the blocks `/bymax-pr:push` depends on also run against fixture repositories, where the review base must be an ancestor of HEAD that is not HEAD or the command stops. The rule found live defects in three documents. Triage defers findings about instruction prose instead of spending a round on each, and exhausting the round budget hands the campaign to the human who authorised the work.

### Fixed

- **Local review guard** — reject post-push directory changes and commands hidden after heredocs; recover interrupted Codex reservations with an OS execution lock while preserving the retry budget.

- **Review flow: marketplace `1.14.0`, quality `1.7.0`, workflow `1.6.1`** — replace unbounded apply-all review loops with shared Claude/Codex context, immutable candidates, evidence-based triage, at most two correction rounds, and exact-source push receipts. Add a backed-up local installer and regression tests for stale reports, linked worktrees, failed gates and round limits.

- **`bymax-qa` `1.0.1`** — post-release hardening of the `qa-guard` hook and `qa-probe` wrapper: reject SOCKS proxy destination overrides (`--socks4`/`--socks4a`/`--socks5`/`--socks5-hostname`); redact `--proxy-pass`, `--proxy-tlspassword` and `--proxy-cert` credentials from captured evidence; validate the physical `.claude/qa` workspace root during `init`, before the guard is armed; route the reachability probe through `--noproxy '*'`; and state that free text cannot enable live mode (only `--live` does).

### Added

- **Codex integration `1.0.1`** — separate local marketplace and self-contained package with 27 native skill entrypoints, bundled shared Bymax resources, a read-only Git review scope helper, evidence-based code review, and capability-aware runtime adapters. Add `scripts/install-codex.sh`, installation guidance in `CODEX.md`, and independent packaging/Git/installation validation. Claude hooks are not registered in Codex.

- **`bymax-qa` — whole-system QA and security audit** (`1.0.0`). `/bymax-qa:audit` runs the session
  as the Security QA engineer of a peer agent team. It is pointed at a **target**, resolved
  deterministically and reported back: a **Jira ticket key** (it verifies Jira access — an Atlassian
  MCP, the `jira`/`acli` CLI, or pasted criteria — reads the acceptance criteria, and reports each
  one PASS / FAIL / BLOCKED / NOT-VERIFIABLE with evidence, a `PASS` inferred from code that "looks
  right" being NOT-VERIFIABLE rather than a pass), a **branch, ref range or PR** (it scopes the hunt
  to the changed surface the way a code review scopes a diff, complementing `/bymax-quality:code-review`
  rather than replacing it), a **path or subtree** (`path:apps/backend` or a bare directory — it hunts
  the files under that path, tracked and untracked, as the code stands), or **nothing** (the whole system, via a signed scope
  `.claude/qa/scope.md` written and approved in `init` mode before any audit runs). A free-text
  instruction after the target steers focus and depth. It maps the stack and its trust
  boundaries, hunts by domain with read-only finder agents, probes the running stack against
  allow-listed hosts only, and admits a finding **only after an independent `qa-verifier` reproduces
  it** — candidate is not finding, and every finding carries a runnable reproduction, captured
  evidence, an ASVS 5.0 / CWE / API-Top-10 reference and a CVSS vector. The auditor never edits the
  target: findings are handed to the agent that owns the code over cross-session messaging, filed as
  a GitHub issue when no peer is live (never a public issue for a HIGH/CRITICAL), commented back on
  the ticket when the target is a ticket and write-back is allowed, or surfaced to the
  human, and each is re-tested against the claimed fix before it closes (OPEN → HANDED-OFF →
  FIX-CLAIMED → VALIDATED or REOPENED). A `qa-guard` `PreToolUse` hook makes the scope mechanical
  rather than disciplinary: while `.claude/qa/.active` exists, a network tool may only reach a host
  in `allowed-hosts` and a Write/Edit may only land in `.claude/qa/`. Eighteen references cover
  target resolution and acceptance criteria plus the domains — security (auth, authorization/tenant,
  injection, cache/Redis, database/Postgres,
  transport/config), observability (log-leak, log forging, event coverage), architecture, frontend
  and supply chain — each with a "what to expect by stack" table and a "common non-findings" list so
  a delegated or intentional control is not reported as a gap. Three helper scripts ship with it:
  `qa-tools.sh` (which external scanners are present — none bundled), `qa-probe.sh` (an HTTP probe
  that captures request+response as redacted evidence), and `qa-log-audit.sh` (searches a log for a
  secret through base64/url/hex/json decodings and states which it covered — a literal grep certifies
  the leaking case). Built on ASVS 5.0 as the finding taxonomy, the OWASP API Top 10 for the API
  layer, and the verify-before-report shape of Anthropic's Claude security tooling and Trail of Bits'
  `fp-check`. Standalone plugin, distinct from `bymax-quality`: that reviews a diff and blocks a
  commit; this audits a running system and drives each fix to a re-tested close. Marketplace to
  `1.13.0`.

### Changed

- **The Codex plugin is named where a fresh install looks for it.** `--adversarial` needs OpenAI's
  Codex plugin, and no document said which one or where from — the remedy table stopped at "install
  (or enable) the openai-codex plugin", leaving a new install to guess across three names: plugin
  `codex`, marketplace `openai-codex`, repo `openai/codex-plugin-cc`. The install pair now appears
  where each audience lands: `llms-install.md` Step 4 and its failure table, the root README's
  external-tools table, `bymax-quality`'s Install section, `codex-setup.md`'s plugin section and
  remedy table, and `code-review.md`'s own `adversarial-absent` remedy — the line a reader meets
  at report time. Both Codex rows are marked optional, since `code-review` runs without either.
  `claude plugin install` accepts no version, so the docs state that the plugin arrives at whatever
  the marketplace publishes instead of naming a version to install; `COMPANION_VERIFIED_VERSIONS`
  stays the single source for the verified list, and the remedy row now says installing a listed
  version is not among the ways out.

### Fixed

- **`/bymax-pm:pm` appeared twice in the slash menu.** The plugin shipped a command and a
  user-invocable skill under the same name, so both were listed, with different descriptions and
  no way to tell which to pick — and they were not equivalent: the command carried a session-identity
  note the skill did not, so choosing the skill lost the `claude --name pm` guidance that the peer
  message routing depends on. The command was a 25-line wrapper that said so itself ("this command
  only routes into it") and duplicated the mode routing the skill already declares, so it is gone and
  its one unique paragraph now lives in the skill's startup section. `/bymax-pm:pm` still resolves —
  to the skill — so the invocation does not change. It is the only command/skill name collision in
  the repository; the other user-invocable skills ship no sibling command.

Plugin versions: `bymax-quality` 1.6.2 → 1.6.3 · `bymax-pm` 1.0.0 → 1.0.1 · `bymax-qa` new at 1.0.0 · `bymax-all` 1.4.0 → 1.5.0 · marketplace 1.12.0 → 1.13.0.

## [1.12.0] — 2026-08-31

### Added

- **`/bymax-web-verify:record` — a UI flow recorded as reviewable video evidence** (`bymax-web-verify`
  `1.2.0`). Generalised from a project-specific skill that worked, keeping its operational lessons
  intact: `test.use({ video: 'on', launchOptions: { slowMo } })` with the test timeout resized to the
  step count; the trailing-`**` `waitForURL` rule for query-param routes (a race that hides until
  `slowMo` exposes it); the blank first-paint lead-in trimmed with ffmpeg and the cut verified by
  pulling the first frame; an `ffprobe` pacing gate before publishing, with `setpts` stretching demoted
  to a fallback; and a mandatory plain-text walkthrough derived from the spec that actually ran, with
  signed-in users named by role, never by address. New here: `--output` per run makes Playwright's
  output-wipe hazard structural instead of procedural, `--mp4` produces a universally previewable
  H.264 copy, discovery reads the project's own Playwright config and artifact conventions instead of
  assuming any, and missing ffmpeg degrades to publishing raw with the reason stated. Marketplace to
  `1.11.0`.

- **`bymax-pm` — Engineering Project Manager for multi-agent development** (`1.0.0`). `/bymax-pm:pm`
  turns a session into the PM/TPM above independent Claude Code peer sessions, built on the native
  cross-session tools: discovery via `ListAgents` (session names are the addresses — workers start as
  `claude --name <agent>`), delegation via `SendMessage` with structured task contracts that carry
  their own reply instructions (peers have nothing installed), and one-shot idle notices
  (`notify_when_idle`) instead of polling. Deterministic lifecycle (BACKLOG → … → VERIFIED → DONE)
  where a worker's "done" is a claim moved to review, never a completion — DONE requires evidence
  (commits, diffs, tests, CI via `gh`) checked by the PM through six quality gates scaled by a
  four-level risk model. Blocker/disagreement/escalation protocols, an append-only decision log, and
  a git-friendly `.claude/pm/` workspace (board + one file per task + roster + activity log) that a
  cold session can resume by reconciling against the repositories. The skill ships as
  `SKILL.md` + 8 lazily-loaded references (peer protocol, task contract, lifecycle, escalation,
  reporting, persistence, multi-repo, worked example). Marketplace to `1.10.0`; `bymax-all` to
  `1.4.0` with the new sibling listed.

- **`AGENTS.md`, with the shared Bymax code-review rules and the `agents-sync` workflow.** Codex
  reviews every pull request here and reads its guidance from `AGENTS.md` alone — root rules apply
  broadly, a nested file governs its directory, one file per directory, up to 32 KiB combined. The shared block between the
  `shared:begin`/`shared:end` markers is the canonical copy from `bymaxone/.github@v1`, byte for
  byte, and `.github/workflows/agents-sync.yml` offers a pull request whenever it drifts. What
  this repository says for itself sits below the markers: here the product is instruction text,
  so the shared source-shaped limits are moved onto the executable files, an ambiguity in a
  command is a defect, a reportable status needs its verifying read, and two passages that look
  trimmable are named as load-bearing.

### Changed

- **Two comments in the shipped command and its script no longer carry a hard count.** The consent argument for `--adversarial` named an exact number of files that invoke `/bymax-quality:code-review` from a model; the number was already stale and moves whenever a command is added, so the claim is stated without it. What it establishes — that no Bymax command sets `disable-model-invocation`, so invoking this one supplies no consent — is unchanged and still verifiable.
- **Three comments state their constraint instead of narrating the edit that produced it.** `agents-sync.yml`, `code-review.md` and `check-frontmatter.py` each explained themselves by describing what an earlier version of the same text said. A reader without that history cannot tell which half is the rule and which is the changelog; the durable reason was the only load-bearing part and is what remains.
- **The `agents-sync` caller authenticates with the organisation's GitHub App, and the shared block
  is at `v1`.** The reusable workflow's secret contract is `app-id` / `app-private-key`; the
  organisation has `AGENTS_SYNC_APP_ID` and `AGENTS_SYNC_PRIVATE_KEY` and no `AGENTS_SYNC_TOKEN`, so
  the `sync-token` mapping this repository shipped resolved to empty and read as configured while
  falling back to `GITHUB_TOKEN` — whose pull requests start no workflow runs. It is deleted rather
  than left dead. The App is installed org-wide and mints a token per run, scoped to this repository
  and revoked afterwards.
- **Shared block `075b9975` → `02b55a5`.** `docs/` language is now a per-repository statement,
  English by default, instead of a blanket Portuguese carve-out; violations of a block rule carry a
  P1 floor, since Codex surfaces only P0 and P1 on a pull request; the 50-line function limit is
  scoped to what a change introduces and excludes test-grouping constructs; and the
  empty-directory rule left the block for a CI check. None of this repository's narrowings depended
  on the two rules that moved.

Plugin versions: `bymax-quality` 1.6.0 → 1.6.1 · marketplace 1.9.0 → 1.9.1.

- **`templates/AGENTS.md` is now `templates/AGENTS.starter.md`.** It is a 26 KB starter for other
  projects, with `{{PROJECT_NAME}}` placeholders. Under its old name Codex would have discovered it
  as this repository's nested `AGENTS.md` for anything changed under `templates/` — applying a
  fictional project's rules to a review here, and pushing the combined guidance past the 32 KiB
  cap. The starter itself is unchanged.

### Fixed

- **`/bymax-workflow:roadmap`, `phase-tasks` and `spec` can now find their document templates on a
  marketplace install** (`bymax-workflow` `1.6.0`). The three commands pointed only at
  `~/.claude/templates/…`, a path that exists solely after a dotfiles restore via
  `scripts/install.sh` — installed via marketplace, the templates were unreachable (they shipped
  inside `bymax-bootstrap`, a different plugin), so generated roadmaps and task dashboards lost the
  emoji status legend and the standard table shape and were improvised per run. The templates now
  ship inside `bymax-workflow` itself, the commands read `${CLAUDE_PLUGIN_ROOT}/templates/` first
  with the dotfiles path as fallback, and when neither resolves the required sections in the command
  are the same contract, so the structure survives. `/bymax-workflow:task` now pins the same
  status vocabulary (emoji included) for every dashboard cell it writes, with the 🔄/👀/⛔
  transitions named — the autopilot skill already did. Marketplace to `1.12.0`.
- **`roadmap.template.md`'s source-spec link resolves from where the roadmap actually lives**
  (`bymax-bootstrap` `1.1.4`, and the copy now shipped in `bymax-workflow`). Rendered at
  `docs/plans/<feature>-plan.md`, the relative target `specs/…` pointed at `docs/plans/specs/…`;
  it is now `../specs/…`. Two more template defects fixed in both copies: task
  blocks after the first said `1-7 (same as task N.1)` in a prompt contractually required to be
  self-contained (the seven steps are now spelled out), and the roadmap update protocol ordered a
  commit while `/bymax-workflow:task` forbids committing — the commit now belongs to the user.

- **A dirty tree downgraded an adversarial branch review that was correctly pinned.** With
  `--target base` the requested scope is the committed `<ref>...HEAD` range, so the runtime
  reviewing exactly `mergeBase..HEAD` is that request honoured — uncommitted files were never in
  scope. The `adversarial:base` case nevertheless marked any dirty checkout `ok-unpinned`, and
  because the check sat in an `elif` it also skipped `exceeds_inline_limits`: a small, fully
  inlined range came back unpinned, and the cross-read discarded a clean verdict that was in fact
  exact. The dirty-tree condition is gone and the inline-limit measurement always runs.
  `standard:base` keeps its own dirty-tree check, which is the opposite case — `codex exec review
  --base` diffs the merge base against the working tree, so tracked uncommitted edits really are
  reviewed beyond the requested range.

## [1.9.0] — 2026-08-29

Plugin versions: `bymax-quality` 1.5.0 → 1.6.0 · `bymax-workflow` 1.4.2 → 1.5.0 ·
`bymax-web-verify` 1.1.0 → 1.1.1 · `bymax-pr`, `bymax-bootstrap`, `bymax-mobile` unchanged.

### Added

- **`/bymax-quality:code-review` now runs three reviews beside its own, not one.** The second
  opinion was a single unsteered `codex exec review`. It gains an adversarial sibling that asks a
  different question — is this the right approach, rather than is this code correct — and, in
  `full` and `deep`, Claude's own built-in review — `/code-review high` in `full`, `max` in `deep`. The two Codex runs launch as concurrent
  background shells before this command forms any opinion, so the pair costs wall-clock once and
  neither can anchor the other. Review B runs in **every** mode, `quick` included: it costs background
  wall-clock rather than session time, and a second opinion is worth as much before a quick push as
  before a merge. **Review C is opt-in behind `--adversarial`** — the Fixed entry below says why, and
  this paragraph described it as automatic until that was corrected inside the same release.
  `--no-codex` skips whichever of them was going to run.

  The adversarial mode drives the openai-codex plugin's own `codex-companion.mjs` runtime by
  absolute path rather than reimplementing it. That plugin marks `/codex:adversarial-review` as
  `disable-model-invocation: true` — a deliberate user-only gate — so the slash command stays
  off-limits to a skill, while the plain Node runtime underneath it does not. Reusing it keeps the
  adversarial prompt tracking upstream instead of drifting in a copy here; the price is that the
  mode reports the new `adversarial-absent` status when the plugin is not installed, which changes
  nothing else. The runtime is invoked without its `--background` flag on purpose: backgrounding it
  there would put the Codex process outside the group this script signals at budget expiry, leaving
  an orphan run billing after the review was already reported as `timeout`.

  The built-in review is reported as Review D and labelled for what it is — the same model family as
  the Bymax review running a different method, not a third independent voice. Two agreeing runs of
  one model is weak evidence, and a reader who mistakes it for corroboration will over-trust it. It
  forks to a background agent like the Codex shells do, so all three reviewers run in parallel and
  none of them makes the command slower to sit through. `quick` leaves it out to save tokens, not
  time — which is the honest reason, unlike the speed argument an earlier draft of this entry made.

- **`argument-hint` on every command that takes arguments** — typing a slash command showed no
  hint of what it accepts. Five files declared the field — `/bymax-pr:push`,
  `/bymax-web-verify:test`, and the three user-invocable skills (`babysit-pr`, `autopilot`,
  `tester`) — and no command beyond the first two. Eleven commands now do: `/bymax-quality:code-review`, `/bymax-quality:tdd`,
  `/bymax-web-verify:verify`, and all of `/bymax-workflow:brainstorm`, `:checkpoint`, `:phase-tasks`,
  `:plan`, `:roadmap`, `:spec`, `:task`, `:verify`. Each hint was derived from the command's own
  documented invocation, not invented. Commands that genuinely take no argument
  (`bootstrap`, `upgrade-standards`, `sim-ios`, `sim-android`, `codex-setup`, `review-md`,
  `web-verify:setup`) deliberately declare none — a hint there would promise an argument that is
  ignored.

- **`validate.sh` now parses command and skill frontmatter** — `claude plugin validate` reads the
  JSON manifests, not the Markdown that defines the commands, so a malformed frontmatter block
  shipped green: the plugin validated while the command itself silently stopped parsing. The new
  `scripts/lib/check-frontmatter.py` walks every `commands/*.md` and `skills/*/SKILL.md`, requires
  parseable YAML and a `description`, and rejects a non-string `argument-hint`. CI installs PyYAML
  explicitly, because a gate that skips itself is worse than no gate.

### Fixed

- **The adversarial review's budget did not bind it.** The plugin runtime runs the turn inside an
  app-server broker spawned `detached` and `unref()`ed, so `kill -TERM -- -$pid` reached only the
  short-lived front-end. Measured: a review abandoned at its budget left `app-server-broker.mjs`
  and `codex app-server` alive and billing for 41 minutes while the report said `timeout`. The
  script's own comment asserted the opposite as a deliberate safety measure, which is how it would
  have survived the next reading. It now cancels through the runtime's public `cancel` — which
  interrupts the billed turn and terminates that job's process tree without killing the broker
  daemon, shared per workspace — and the cleanup runs on `INT`/`TERM` too, not only `EXIT`.

  The second review of that fix found the cancel itself ambiguous: an ID-less `cancel` resolves
  the current session's jobs and refuses when there is more than one, so a user with their own
  `/codex:*` job running when this review timed out would have kept paying for both. The run now
  carries a session ID nobody else uses (`CODEX_COMPANION_SESSION_ID`, exported to the launch and
  the cancel and to nothing else), and a cancel that fails is reported in the `timeout` line rather
  than swallowed — the caller must know a run may still be billing, because nothing else in the
  script can reach it. The cancel is itself bounded to 15 s: it talks to the broker over a socket,
  and a hung broker is precisely the case a timeout is handling, so an unbounded cancel would have
  blocked forever without ever reaching the group kill or emitting `timeout` — found by the
  standard review on the following round. And the round after that found the signal path: on
  `INT`/`TERM` the exit trap ran the same cancel, recorded its failure in a variable, and exited
  without printing it — taking the session id and the recovery command with it. The signal path
  now reports exactly what the timeout path reports, verified by sending `TERM` to a run whose
  stubbed cancel refuses to confirm. The scope measurement was likewise corrected to mirror the runtime's own
  commands (staged and unstaged diffed separately, `--binary`), since `git diff HEAD` undercounts
  exactly the cases where the runtime has already switched to self-collection.

- **A failed adversarial review was published as a healthy one.** When Codex returns unparseable
  JSON the runtime still exits 0 and renders a human-readable failure page to stdout; the only
  check on that path was "is stdout non-empty", so the page shipped under `CODEX_STATUS: ok` and
  the cross-read counted Review C as an outside voice that examined the diff and found nothing.
  The output must now carry a `Verdict:` line — a positive structural test, so a change in
  upstream's format fails closed rather than silently reopening the hole.

- **Review C's scope was not the scope it was launched with.** Past two changed files or 256 KiB
  the runtime stops inlining the diff and tells the agent to collect its own with git commands, so
  the validated scope flags bound nothing — and on a branch target it resolves `mergeBase..HEAD`,
  dropping the uncommitted work the calling command deliberately includes. Practically every real
  review exceeds two files, so this was the normal case, not the edge. The script now returns a
  distinct `ok-unpinned` status in that case — not a note under `ok`, because the report branches on
  the status line and never on prose — followed by a `CODEX_SCOPE: self-collected` line. The
  review is still published and its findings still get a disposition; what changes is that its
  silence no longer counts as evidence in the cross-read. The alternative the adversarial review
  proposed, handing the backend a frozen exact diff, is not available: the runtime accepts a scope,
  not a patch.

- **`--mode=adversarial` was silently ignored.** The argument loop matched only the
  space-separated form; the equals form fell through to a catch-all `shift` and left the default
  `standard` in place. With `--target uncommitted` that launched a *second standard review*,
  indistinguishable in the output, which the cross-read's "both outside reviews found it" line
  would then report as the strongest evidence in the report. Both forms are handled now.

- **An out-of-range `--budget` disabled the timeout entirely.** The value was validated as digits
  only. `/bin/bash` here is 3.2, whose `[` fails with status 2 above 64 bits — a status `if` reads
  as false — so a caller passing milliseconds made the timeout branch unreachable while the poll
  loop spun and Codex ran unbounded. `--budget 0` failed the other way, killing a run milliseconds
  after it started. The budget is now bounded by digit count first, then by range, to [30, 3600].

- **`adversarial-absent` masked the real blocker.** The plugin check ran before the `codex` binary
  and session checks, so a machine with neither reported the shallower problem — sending the user
  to install a plugin when what they lacked was the CLI, which is precisely what the remediation
  text says that install will not fix. The fundamental gates run first now.

- **The runtime lookup would execute code the user never installed.** It globbed
  `*/codex/*/scripts/codex-companion.mjs` under the plugin cache, fell back to marketplace
  checkouts, and ran whatever matched with `node` under the user's own permissions — the
  read-only sandbox covers the Codex thread that runtime starts, not the Node process itself. Any
  marketplace shipping a plugin named `codex`, installed or not, enabled or not, would have run
  with full access to the repository and the user's credentials merely because a code review was
  requested. (Before that, the sort had also preferred the marketplace checkout over the installed
  version, and BSD `sort` has no `-V`, so `1.9.0` would have beaten `1.10.0` on macOS.) Discovery
  now goes through `claude plugin list --json` and accepts exactly one answer: the plugin with id
  `codex@openai-codex`, installed **and enabled**, at its recorded `installPath`. No glob, no
  fallback, no ordering to get wrong; `BYMAX_CODEX_COMPANION` remains as an explicit override that
  is trusted as the user's own decision. Found by the adversarial review of the previous fix.

  The next round then asked the right follow-up: the runtime contract this script relies on —
  read-only sandbox pinned per thread, the detached broker and its `cancel`, session-ID scoping,
  the scope flags, a `Verdict:` line in the output — is undocumented and was verified by reading
  1.0.6 only. A routine plugin update could change any of it, and the failure modes are the bad
  kind: a run still billing past its budget, or a Node process with the user's permissions whose
  read-only guarantee no longer holds. So only versions that were actually read are accepted — an
  exact allowlist, currently `1.0.6`. The first cut admitted `1.0.*`, which the next adversarial
  round correctly called a range hoped compatible rather than a contract verified. Any other
  version is refused with `adversarial-absent` and a message saying why;
  `BYMAX_CODEX_COMPANION_ALLOW_UNVERIFIED=1` runs it anyway as the user's explicit decision.
  Adding a version means re-reading four upstream files, and the comment names them.

  The same review argued the direct runtime call bypasses upstream's `disable-model-invocation`
  boundary. Refused, with the reasoning recorded in the script header: that flag gates the
  slash-command wrapper, not the runtime — upstream's own `codex-rescue` agent calls the same
  runtime — and the consent it protects (no model-started billed run) is met, because the billed
  run starts only when the user invokes `/bymax-quality:code-review`, exactly as Review B's
  `codex exec review` does on the same authority. If upstream publishes a supported surface for the
  adversarial review, the direct call should go.

- **`/bymax-workflow:verify quick` contradicted itself.** The mode was defined in a new table while
  the section below it still read "Walk these in order. Do not skip.", and the output template still
  prescribed all five gates and terminated in `Verdict: READY` — so a `quick` run either paid for
  everything anyway or claimed READY off a type-check and a test pass, the exact "'compiles' is not
  'works'" error the file's opening rule forbids. Both now state the `quick` shape explicitly, and
  `/bymax-workflow:checkpoint` no longer promises a pass rate and coverage that Gate 1 never produces.

- **Stale prose corrected across the review docs.** The command's opening paragraph still described
  a single Codex review gated to `full`/`deep`; `codex-setup.md` still said installing the
  openai-codex plugin "does not help here", listed neither `adversarial-absent` nor
  `unsupported-target`, and quoted budgets that omitted `quick`; the CI comment justified the
  PyYAML install by a skip path that no longer exists; the report template assumed Review C emits
  `P0`–`P3` when its runtime emits `critical`/`high`/`medium`/`low`; and Step 5.5 told the model to
  branch Review D on a `CODEX_STATUS` line an agent never produces. Review D also gained the scope
  guard Step 1.5 already had — without it, the common clean-tree case had it reviewing an empty
  diff and reporting no findings, beside three reviews that had read the real one.

- **The built-in review at `high` then found ten more, all verified, all fixed.** The `cancel`
  exit status is not its verdict — the runtime exits 0 once it has *resolved* the job even when
  the interrupt RPC failed, so the `--json` payload's `turnInterrupted` is read instead, and a
  failed cancel now prints the one command that still reaches the run (`/codex:status` cannot
  show it: it filters by the Claude session id, and this run carries its own). The `Verdict:`
  guard was satisfied by the runtime's own parse-failure page, which quotes the raw model output
  in a text fence — the page is now rejected by its markers first, then `Target:` and `Verdict:`
  are both required. A review finishing in the last poll interval was discarded as a timeout and
  falsely reported as a failed cancel; liveness is re-checked before either. The scope was
  measured after the review against a tree that may have moved, and always blamed the file
  count; it is now measured once at launch, names the limit that tripped, and also covers the
  branch-target case where uncommitted work is silently outside the reviewed range. `quick` no
  longer stalls up to a full budget on background shells. The cross-read had lost its
  strongest bucket — A and an outside review agreeing. And `codex exec review` hands back its
  final message through `--output-last-message`, which replaces two hand-written JSONL
  extractors. Every number the script reasons about is now a named constant.

- **Review C is now opt-in behind `--adversarial`, because the reason it was automatic was false.**
  The script's header justified driving the openai-codex runtime past that plugin's
  `disable-model-invocation: true` gate on the grounds that the billed run only starts when a user
  invokes this command — "a user-only command in this toolkit". It is not one: no Bymax command
  sets that flag, and fifteen files invoke this one from a model, `/bymax-workflow:task` and
  `/bymax-workflow:autopilot` among them. A model in an agentic loop could therefore start two
  billed Codex turns unasked, one of them through the very runtime upstream gated to stop that.
  The premise was written five times across five rounds and never checked; the seventh review
  checked it. Consent now lives on a flag a person has to type; Review B keeps running in every
  mode, and the workflow chains keep the reviewers that need no such gate.

  Also from that round: `codex exec review --base` builds a merge-base-vs-working-tree diff in
  which untracked files never appear, so untracked-only changes could not rescue an empty range
  from billing a verdict on nothing; `BYMAX_CODEX_COMPANION` marked itself version-verified and so
  skipped the unpinned-scope guard whose own comment names the override; the skills glob was still
  one level deep after commands and agents were fixed; and `codex-setup` still quoted 180 s for
  `quick` after it became 120.

- **The local shellcheck gate and CI's disagreed, and CI was right to fail.** A function whose only
  caller is a `trap` cannot be followed by shellcheck, and the two versions name that differently:
  0.11 (Homebrew, local) reports the function as never invoked — `SC2329`, which the exclusion
  already carried — while 0.9 (`ubuntu-latest`, and so CI) reports every statement in its body as
  unreachable, `SC2317`. A green local run therefore proved nothing about CI. Both codes are listed
  now, with the reason, because neither version reproduces the other's.

- **A final round, all diagnosability and honest labelling — no correctness defect left.** The
  harvest rule read as a sentence to serve rather than a deadline, so a model would idle to the
  budget even when both shells had returned in 45 s; it polls now. The `--adversarial` flag is
  labelled for what it is: a default that fails safe, not a gate — `codex-review.sh` accepts
  `--mode adversarial` from any caller, and the honest claim is that nothing starts the adversarial
  runtime unless something explicitly asks, not that nothing can. A file that is not UTF-8 is one
  finding instead of a traceback that left every later file unchecked. `cleanup` ends in `exit 0`,
  because a returning EXIT trap does not change bash's status and the header promises this script
  always exits 0. And the two measurement helpers now carry the constraint that made their trailing
  `exit` correct — call them only inside a command substitution.

- **A sixth round: ten findings, every one verified against the code before it was fixed.**
  `stop_review` was re-entrant — the budget path calls it with `TERM`/`INT` still armed, so a
  signal mid-cancel fired the exit trap, re-entered with `run_active` still 1, issued a second
  cancel under the same session id and reported "may still be billing" for a run the first cancel
  had stopped; it now clears and disarms on entry. `git ls-files --others` is scoped to the
  **current directory** while every other measurement is repo-wide, so from a subdirectory an
  untracked-only change read as a clean tree and both reviews were skipped — measured, and fixed
  with an explicit repo-root pathspec. An empty `<ref>...HEAD` was only refused on a clean tree,
  but the adversarial runtime reads that range and nothing else, so a dirty tree bought it a
  billed verdict on nothing. The honest "this runtime's limits were never verified" reason was
  then overwritten by a measurement against the limits it had just disclaimed: the first reason
  set now wins, and the version check is read once instead of copied twice. The `CODEX_SCOPE`
  line said "self-collected — the reviewer chose its own scope" for all four causes, including
  the deterministic ones it does not describe. `quick` launched two reviews with a 180 s budget
  and abandoned them after 60 s: the budget and the wait are one number per mode now, and `quick`
  gets 120 s — the mode is quick because Review A does less, not because a paid reviewer is cut
  off mid-sentence. The frontmatter gate globbed one directory level, so a namespaced command
  would ship unchecked behind a green "Checked N files". The agent tier check matched `sonnet`
  and `opus` as bare substrings, so `sonnet-6-preview` and `my-opus-fork` passed, and a
  non-string `model` was reported twice. Review D is skipped on a stacked branch, where a branch
  name hands the built-in `<default>...<branch>` while Step 1 resolved the commits ahead of a
  different upstream. And `codex-setup`'s verification example stopped guessing the base from
  `refs/remotes/origin/HEAD`, which is unset on any clone not made by `git clone`.

- **A fifth round, and the first one to run shellcheck.** The built-in review's conventions finder
  installed shellcheck locally; until then `validate.sh` had passed only because that step
  self-skipped. It found the validator's own comment `# shellcheck flags (SC2181)` parsed as a
  malformed directive — a red CI on every push of this branch — and five functions reported as
  never invoked because their only callers were a `trap` or a function name held in a variable.
  The indirect calls are direct now; the trap-handler case is a stated project-wide exclusion.
  `set -- "${args[@]}"` on an empty array is "unbound" under `set -u` in bash 3.2, so the script
  with no arguments died before writing a status line. And a premise of the fourth round was
  wrong: `codex exec review --uncommitted` reviews staged, unstaged **and untracked** changes —
  its own `--help` says so — so the refusal of an untracked-only tree and the `ok-unpinned` for a
  mixed one were both reverted; read the help, not the assumption. An adversarial run on a
  runtime version whose inline limits were never verified is now `ok-unpinned`, because whether
  its diff was inlined cannot be predicted. Step 1.6 passes the branch name to the built-in review
  rather than "no target", which on a clean tree is an empty diff, and skips it when no
  unprefixed `code-review` skill exists rather than risk invoking this command by its own name.

- **A fourth round, all scope and plumbing.** An empty `<base>...HEAD` range on a clean tree
  billed both reviewers over nothing and was counted as a clean second opinion; refused now, like
  the clean tree. `codex exec review --base` diffs the merge-base
  against the working tree, so tracked uncommitted hunks were reviewed as if they were part of the
  committed range — `ok-unpinned` now, with the count. Both launch lines read `</dev/null`: under
  `set -m` a background job keeps the script's stdin, which `codex exec` folds into its prompt, and
  an open pipe or a TTY would have stalled the run until the budget expired. `CODEX_API_KEY` now
  satisfies the auth gate, which only ever read the on-disk credential store. Every way the plugin
  lookup can fail says which prerequisite failed instead of "install the plugin". A bare `--ref`
  that exists only as `origin/<name>` says so. The agent model check is an allowlist (`sonnet`,
  `opus`) rather than a `haiku` denylist that `inherit` and a typo walked past. And the harvest
  rule allows for the ~19 s the script needs to stop a run after its budget — the `timeout` line
  lands after the deadline, not on it. Measured while fixing: two of these were proven with real
  Codex runs because the test harness did not stub the binary; it does now.

- **A third round of the built-in review, on the tree after the second.** A second `TERM` during
  cleanup ran `exit 0` inside the `EXIT` handler, which bash never re-enters — no status, no kill;
  the handler now ignores further signals. A review finishing in the instant between the liveness
  check and the cancel was discarded as "cancel FAILED"; a completed process with a report is
  harvested instead — and the fix for that reaped the child twice (`wait` on a reaped pid returns
  127), which the standard review caught before it was committed. A `--ref` that resolves but
  shares no history with `HEAD` is refused: `codex exec review --base` on an orphan falls back to a
  prompt that picks its own scope and reports `ok`. A clean working tree is refused for
  `--target uncommitted`: both backends bill a full turn over "(none)" and return a verdict on
  nothing — which is exactly what `codex-setup`'s documented verification step used to do. The
  `quick` budget goes back to 180 s: the 60 s reasoning confused the shell's deadline with the
  harvest's wait, which run on different clocks, and 60 s sits at the typical review duration.
  The dirty-tree and untracked counts treat a failing git as unmeasured rather than as zero. The
  `haiku` ban matches full model ids. The scope measurement moved below the free availability
  gates so an absent Codex costs no diff. The cancel remedy is one function instead of two copies.

- **A further round of the built-in review, on the fixed tree.** The failed-cancel branch was
  unreachable in the exact case it exists for: the runtime's `cancel` SIGTERMs the job's process
  tree — which is the very process the script holds — so post-cancel liveness was always false.
  Liveness is now sampled before the cancel. `quick` launched shells with a 180 s budget and waited
  60 s, so two billed runs outlived the report; the budget is 60 s there now, and the command says
  why the two must match. A wrong command line (`--mode adverserial`) was reported as
  `unsupported-target`, which sent the reader to the scope table; it is `bad-invocation` now, and
  the line after every status is reproduced verbatim in the report, since it is the script's one
  sentence of remedy. An out-of-range `--budget` is clamped and said, not silently replaced. The
  standard review on a branch target is `ok-unpinned` when untracked files exist, because
  `codex exec review --base` never sees them. The scope decision is one helper for both modes, and
  a git failure inside it makes the scope unpinned rather than "small". The frontmatter gate now
  tolerates a BOM and a trailing space on a fence, requires `tools` on agents and rejects
  `model: haiku`, as CONTRIBUTING.md already promised it did. `codex-setup` exercises the
  adversarial path and documents `adversarial-absent`'s three causes and their remedies.

- **The frontmatter gate could report success without having run, then twice more in miniature.**
  `check-frontmatter.py` first exited with a "skipped" status when PyYAML was missing while
  `validate.sh` treated that as a warning, so a machine without PyYAML got `✓ All validations
  passed` over a check that never executed. Replacing the skip with a hand-written fallback parser
  moved the problem rather than fixing it: that parser accepted `description: "bad\qescape"`, which
  PyYAML rejects, and was then measured to disagree with PyYAML in **both** directions — accepting
  `description: 12345`, `description: null` and `argument-hint: yes`, while rejecting folded
  scalars, literal scalars and trailing comments that YAML accepts.

  So the second parser is gone. PyYAML is now required, and a missing PyYAML or `python3` fails the
  gate instead of degrading it. A gate whose verdict depends on which machine ran it is worse than
  one that says plainly what it needs, and this repo does not need its own YAML implementation. The
  three rounds were found by, in order, the adversarial review, the standard review, and the
  built-in review — each on its first run against this branch.

- **The gate skipped the seven `agents/*.md` files while claiming to cover everything the loader
  reads.** 31 files under `plugins/` carry frontmatter; the check looked at 24. The missing seven
  are the specialist sub-agents, each with long unquoted `description:` prose of exactly the shape
  that attracts a colon-space — and a malformed one means `deep` mode fans out to a
  `security-reviewer` that silently never loaded, while this command reports a clean security pass.
  Agents are now checked, `name` is required on skills and agents (not merely type-checked when
  present), and a skill whose `name` does not match its directory is reported.

- **`validate.sh`'s first two gates could never fail.** `if ! claude plugin validate … | sed` tests
  `sed`'s exit status, not the validator's, so a broken `marketplace.json` or `plugin.json` printed
  its error and still finished `✓ All validations passed`. Pre-existing, and directly under the new
  section whose own comment argues that printing success over a check that did not run is the
  failure mode the gate exists to prevent. Both now read `PIPESTATUS[0]`.

- **`argument-hint` in the `tester` skill parsed as a list, not a string** — it was written
  unquoted (`argument-hint: [file-path]`), which YAML reads as a one-element sequence. Found by
  the new frontmatter check on its first run.
- **`/bymax-workflow:verify quick` was called but never defined** — `/bymax-workflow:checkpoint`
  has always run `/bymax-workflow:verify quick` before snapshotting, while `verify` documented no
  modes at all and presented its five gates as unconditional. The mode is now defined where it is
  implemented: `quick` runs Gate 1 (static gates plus the suppression scan) and nothing else,
  the default still runs all five. It is a smaller scope, not a lower bar — Gate 1 still fails on
  one type error, one failing test, or one new suppression comment.
- **`/bymax-workflow:checkpoint` documented three of its four actions** — the `## Usage` line listed
  `create|verify|list` while the `## Arguments` section below it also documented `clear`. The usage
  line now matches.

### Security

- **`validate.yml` ran with the default `GITHUB_TOKEN` scope** — the workflow declared no `permissions` block, so it inherited whatever the repository default grants (write, on many repos). CodeQL flagged it as `actions/missing-workflow-permissions` (medium). Every step only reads the repository — checkout, a toolchain install, and a local script — so it now declares `contents: read` at workflow level, which also makes any job added later inherit the restriction rather than silently getting the default.

## [1.8.0] — 2026-08-29

### Added — `/bymax-quality:code-review`: an independent second review through the Codex CLI

`full` and `deep` now run a second review in parallel with the Bymax one and report both side by side. The two are kept independent by construction, because the failure mode worth designing against is not the second model being wrong — it is the first one quietly making it agree.

- **Commitment order.** Codex is launched in Step 1.5, before this command forms any opinion, and its output is not read until Step 5.5, after the Bymax findings are frozen. Reading it early would anchor Steps 2–5 on what Codex saw.
- **No filtering.** A Codex finding may be annotated but never deleted, and its `P0`–`P3` label is never rewritten — the mapping to CRITICAL→LOW is shown next to the original, not in place of it.
- **The verdict stays independent.** BLOCK/APPROVE is computed from the Bymax findings alone, so it is identical whether or not Codex was reachable. Codex-only `P0`/`P1` findings instead require an explicit disposition — fixed, or refused with a stated reason — under the same rule the project already applies to a reviewer's comment on a PR.
- **Optional, and self-contained.** It needs only the `codex` binary with an active session (`npm install -g @openai/codex` + `codex login`) — **not** the OpenAI Codex plugin, whose `/codex:review` and `/codex:adversarial-review` are marked `disable-model-invocation` and cannot be called by a skill. `plugins/bymax-quality/scripts/codex-review.sh` always exits 0: a missing CLI, an expired session, a rate limit, a budget timeout and an unparseable response all surface as a one-line `CODEX_STATUS`, and the report is otherwise unchanged. `--no-codex` skips it; `quick` never runs it.
- **`/bymax-quality:codex-setup`** — the runbook for getting Codex ready when a user installs this toolkit without it. Diagnoses the three possible states with local, instant checks; installs through the channel that fits the machine (`brew install --cask codex` on macOS, `npm install -g @openai/codex` elsewhere) and warns against mixing the two; hands the interactive `codex login` to the user, because the browser callback cannot be completed from a tool call, and documents the API-key path for headless machines; then **verifies with a real review run**, since an install command's exit code proves nothing about whether the reviewer works. It also records what is *not* needed: no `config.toml` entry, and not the OpenAI Codex plugin. `/bymax-quality:code-review` points at it in the report footer on `absent`/`unauthenticated`, once, without interrupting the review.
- **`codex-review.sh` leaked Codex's child processes on timeout** — the budget signalled only the wrapper pid, so subprocesses Codex had started kept running and the budget was not actually enforced. The job now runs in its own process group and the group is signalled. Verified with a wrapper that spawns a background child: the child survived before the fix and dies with the group after it.
- **`codex-review.sh` reported failures without their reason** — Codex's stderr went to `/dev/null`, so a rate limit, an expired plan or blocked egress all surfaced as the bare string `codex exited 1`. Its stderr is now captured and its tail is appended to the `failed` status, which is the whole point of a script whose job is to explain why it degraded.
- **`codex-review.sh` reported an unresolvable ref as a successful review** — given a bad ref, `codex exec review` exits **0** and returns "Commit X does not exist" as its final message, which the script passed through as `CODEX_STATUS: ok`. The ref is now validated with `git rev-parse --verify` before the run, so the case is refused in milliseconds instead of spending a Codex run to produce a non-review.
- **Measured, not assumed.** `codex exec review` takes ~40–56 s largely independent of diff size (21 files/774 lines cost the same as 6 files/65 lines), so the run hides behind Steps 2–4. `--output-schema` is silently ignored in review mode, so the review is extracted from the `agent_message` item of `--json` (falling back to plain stdout when neither `jq` nor `python3` is present). The auth probe `codex login status` is a local credential read: ~13 ms, no network, exit 1 when logged out. Output is **not deterministic** — three runs over the same commit returned overlapping but different findings, and one issue moved between `P1` and `P2`; the skill states plainly that an empty Codex review is not evidence a diff is clean.

### Fixed

- **`/bymax-pr:push` could open a PR with an empty description against an empty base** — Step 0 deliberately lets the dirty-tree flow continue without a resolved default (branching and committing need no base), but Step 5 then ran `git log "$DEFAULT_REF"..HEAD` regardless, collapsing to `HEAD..HEAD`. The PR path is now gated: it skips the PR with a stated reason after a successful push, rather than creating one from nothing. The earlier round had described this hazard in prose without enforcing it.
- **`codex-review.sh` inherited the user's Codex sandbox** — the script's header promised it never writes to the repo, but `codex exec review` took its sandbox from `~/.codex/config.toml`, so a user on `workspace-write` or `danger-full-access` handed the reviewer write access to their working tree. The sandbox and approval policy are now pinned per invocation (`-c sandbox_mode="read-only" -c approval_policy="never"`), which also prevents an interactive approval policy from stalling the run until the budget expires. The user's own Codex configuration is left untouched.
- **A detected default branch could resolve to an unrelated one** — the candidate list fell through from the detected default to other conventional names, so in a `--branch develop --single-branch` clone whose remote default is `main`, `origin/develop` was silently chosen to stand in for `main`: the clean-tree review then compared against the wrong branch, and `push` measured "ahead" against a branch's own upstream. Detection and guessing are now separate paths — a detected default resolves to that branch or, if the clone never fetched it, is fetched once non-interactively; failing that it stays empty and `require_base` refuses. Conventional names are tried only when no default could be detected at all.
- **The empty-base guard covered only one of its call sites** — the branch-target path still ran with an empty `$DEFAULT_REF`, so `git diff "...<branch>"` became `HEAD...<branch>`: the target compared against whatever was checked out, or `HEAD...HEAD` when it *was* the checkout — an empty diff reported as a clean review. The requirement now lives in one `require_base` helper that every comparison goes through, in both commands, instead of a guard repeated per site. Checking at each point of use rather than up front is what keeps the uncommitted-changes scope working in a repository with no default branch at all.
- **A branch target could hand Codex the wrong head** — `codex exec review` takes a base but has no head-ref argument, so a branch target that is not the current checkout made Codex compare *your* HEAD against that base: a different diff from the one the Bymax review examined, often an empty one, and the report presented it as a second opinion on the requested branch. Codex is now skipped for any scope whose head is not checked out, rather than switching branches — a review command must not mutate the working tree.
- **An unresolvable comparison base silently reviewed nothing** — when a repository has no upstream, no reachable `origin/HEAD` and no conventional branch name, the base came out empty and git read `"...HEAD"` as `HEAD...HEAD`: exit 0, zero files, so an unreviewed branch would have passed as clean and `/bymax-pr:push` would have reported "nothing to push". Both commands now refuse an empty base **only where one is actually required** — the clean-tree comparison in `code-review`, and the "already ahead?" question in `push`. An uncommitted-changes review is scoped to `HEAD` and still works in a repository with no resolvable default branch at all. Reproduced on a repository whose only branch is `mainline`, dirty and clean.
- **The default-branch remote probe could block or prompt** — `git ls-remote` ran before any local fallback, and `2>/dev/null` hides a credential prompt's output without stopping it from blocking. It now runs with `GIT_TERMINAL_PROMPT=0` and `ssh -oBatchMode=yes`, closing both the HTTPS and the SSH prompt paths. The probe stays ahead of the local candidates on purpose: it is the only way to learn a default that is neither `main` nor `master`.
- **`/bymax-quality:code-review` assumed `main` was the default branch** — a branch target ran `git diff main...<branch>`, which fails or compares against the wrong base on a `master`/`develop` repository, and the clean-tree fallback had the same assumption. It now resolves the default branch via `git symbolic-ref refs/remotes/origin/HEAD`. Found by the Codex review during its own integration.
- **`@{upstream}` used bare on a branch that was never pushed** — in `/bymax-pr:push` (the "anything ahead?" preflight) and in `/bymax-quality:code-review` (the clean-tree fallback). Git exits `fatal: no upstream configured` instead of reporting the commits, so `/bymax-pr:push` reached "nothing to push" on a local feature branch with unpushed commits — its primary scenario. Both now resolve the base first, falling back to the default branch when there is no upstream. Reproduced in a scratch repository before and after the fix; these were the only two occurrences in the toolkit.
- **Default-branch name used as a ref that the clone may not have** — `git clone --branch develop` creates only the local `develop` while still fetching `origin/main`, so resolving the default to the *name* `main` produced `fatal: ambiguous argument 'main...HEAD'` in a perfectly valid clone. Both commands now keep the name and the ref separate: `$DEFAULT_BRANCH` for "am I on the default branch?", `$DEFAULT_REF` for every comparison, chosen as the first candidate that actually resolves and preferring the remote-tracking ref. Verified across five clone shapes (with upstream, never-pushed, no remote at all, `origin/HEAD` unset, and `--branch` clone without the default checked out).
- **Default-branch fallback assigned a ref that may not exist** — the first fix for the above fell back to `main`, then `master`, which breaks a repository whose default is `develop` (or anything else) when `origin/HEAD` is unset locally: every later diff fails with `fatal: ambiguous argument 'master...HEAD'`. Both commands now ask the remote via `git ls-remote --symref origin HEAD` — the only way to learn a non-conventional default — and only then fall back to the first conventional name that **actually exists**. Verified against a `develop` repository with and without a reachable remote. Found by the Codex second review, on the fix for the finding above.
- **`scripts/validate.sh` never linted `plugins/*/scripts/*.sh`** — the glob covered `plugins/*/hooks/`, `personal/` and `scripts/` only, so a shell script shipped under a plugin's `scripts/` directory skipped both the executable-bit check and shellcheck in CI.

- **Design-skill install commands** — the `skills` CLI takes one skill name per `--skill` flag, but `scripts/install.sh` and `vendor/README.md` passed a comma-separated list. The CLI read it as a single skill named `a,b,c`, matched nothing, and exited 1 — so none of the five `taste-skill` design skills were ever installable by either path. Now one flag per name.
- **`ui-ux-pro-max` install command** — `claude plugin install ui-ux-pro-max@ui-ux-pro-max` fails: the upstream marketplace is `ui-ux-pro-max-skill` (after the repo), only the plugin inside it is `ui-ux-pro-max`. Corrected in `vendor/README.md` and `vendor/ui-ux-pro-max/ATTRIBUTION.md`.
- **Vendor update procedure** — the documented `rm -rf vendor/ui-ux-pro-max` step deleted `ATTRIBUTION.md`, which lives inside the folder being replaced. The procedure now saves and restores it, uses `cp -R …/.` so dotfiles survive, and ends with the upstream validator + unit tests.

### Changed

- **`ui-ux-pro-max` snapshot refreshed** to upstream **v2.11.0** (from the 2026-04-25 snapshot): 67→84 styles, 96→192 palettes, 57→74 font pairings, 96→192 product types, 13→22 stacks, plus a new `references/` folder and GSAP motion presets. Verified with the skill's own `scripts/validate_data.py` and 16 unit tests.
- **Vendor content counts corrected** — `ATTRIBUTION.md` and `vendor/README.md` described an older snapshot than the one committed (claimed 161 palettes / 161 product types / 10 stacks). Counts are now verified against `data/*.csv` with a CSV-aware parser, since embedded newlines make `wc -l` undercount.
- **`ecc-skills/` audited** against upstream and deliberately left unrefreshed — the drift is cosmetic only (frontmatter renesting, ✅/❌ → `PASS:`/`FAIL:`).

### Documentation

- `vendor/README.md` now warns that the `skills` CLI always prints `PromptScript does not support global skill installation`. That is a different agent target failing, not Claude Code — the exit code stays 0 and the same output reports `symlinked: Claude Code`. Verify installs with `ls ~/.claude/skills/<name>/SKILL.md`, not the error text.

## [1.7.0] — 2026-07-17

### Changed — `/bymax-quality:code-review` v2: mechanical gate, verified bug hunt, selectable depth

The command graduates from a single-pass checklist to a pipeline that borrows the architecture of Claude Code's built-in review engine (finders → adversarial verification) while keeping what only this gate does: enforce the Bymax conventions and **block** on CRITICAL/HIGH — the built-in engine never blocks.

- **Modes**: `quick` (mechanical gate + CRITICAL/HIGH on changed lines — pre-push sanity check), `full` (default — everything, single-pass bug hunt), `deep` (bug hunt fans out to the `typescript-reviewer`/`rust-reviewer` + `security-reviewer` sub-agents in parallel as finders; read-only, never test-running).
- **Flexible targets**: branch (`main...feature-x`), explicit ref range, PR number (checked out locally so the range works with `git diff`), or single file — previously only `git diff HEAD` (uncommitted work). With a clean working tree it now reviews the branch's commits ahead of upstream instead of finding nothing.
- **Mechanical gate (Step 2)**: the regex-shaped checklist items (suppression comments, CLI bypasses, raw `console.*`, TODO without issue link, files > 800 lines, every Tailwind v4 canonical-form and v3-rename rule, hex in `className`, JIT-invisible dynamic classes) are now executed as concrete `git diff -U0 | grep` commands over added lines — findings are exact `file:line` facts instead of model impressions, faster and immune to hallucinated locations.
- **Adversarial verification (Step 5)**: candidate ≠ finding. Every non-mechanical candidate — the main agent's or a finder's — is re-checked against the file at the cited line, behavior claims must survive a call-path trace (naming-based inference is dropped), duplicates are consolidated, and the report states how many candidates were dropped. Mechanical findings skip verification because they are already exact.
- **`--fix`**: applies the deterministic mechanical MEDIUM rewrites (Tailwind renames/canonical tokens) plus any user-approved finding after the report, then re-runs the gate; never commits.
- Checklist content is otherwise preserved (zero-tolerance suppression policy, standards §0 simplicity ladder, JSDoc/rustdoc, cross-feature imports, timeless comments), reorganized into mechanical vs judgment items.

### Added — `/bymax-quality:review-md`: REVIEW.md generator for Anthropic's cloud Code Review

Anthropic's Code Review (cloud `@claude review` on PRs, `/code-review ultra`) reads a repo-root `REVIEW.md` and injects it verbatim into every review agent as the highest-priority instruction block — but it knows nothing about Bymax conventions out of the box. The new command distills the `/bymax-quality:code-review` checklist plus the project's `CLAUDE.md` invariants into that file: suppressions/secrets escalated to 🔴 Important, nit cap with re-review convergence, skip rules (generated files, lockfiles, CI-enforced checks), and a per-repo "Always check" list. Constraints are enforced by the command: self-contained (no `@` imports — the file is pasted verbatim), ≤ ~100 lines, refreshed rather than duplicated when one already exists. Division of labor stays explicit: the local command is the blocking gate; `REVIEW.md` is the projection of the same rules onto the cloud engine.

### Added — `/bymax-pr:push`: ship work safely, with an explicit PR opt-in

The user-scope `/push` skill graduates into the `bymax-pr` plugin (versioned, installable on any machine) and gains a PR mode. The flow: inspect (read-only) → branch (**a commit never lands on the default branch** — create `<type>/<slug>` when on it, reuse the current feature branch otherwise, always `git switch -c`) → stage (respect a pre-staged index; `git add -A` only when the index is empty) → commit (complete Conventional-Commits message: title ≤ 72 chars validated before committing, body bullets carrying the what + why) → push with upstream.

- **`pr` token = explicit opt-in.** `/bymax-pr:push` alone never opens a PR (it prints the compare URL); `/bymax-pr:push pr` also creates the GitHub PR via `gh` with a complete body (Summary / Changes / How to verify / Notes) authored from the **entire** `default..HEAD` range, not just the last commit. An existing PR for the branch is detected and reported, not duplicated.
- **Ship-what's-committed**: a clean tree with commits ahead of upstream skips straight to push/PR instead of reporting "nothing to do".
- Safety rails: never force-push, never `--no-verify`, no AI-attribution trailers in commits or PR bodies, timeless messages (no plan-phase refs), `gh auth` preflight when `pr` is requested, one verified git mutation per step.
- README reframed: the plugin now covers the PR lifecycle end to end — `/bymax-pr:push pr` → `/bymax-pr:babysit-pr <PR#>`.

### Added — `/bymax-web-verify:test`: assisted UI testing in the Claude Desktop preview

A new command in `bymax-web-verify` that brings the project's full stack up and tests the UI **while the user watches**. Mode is detected from the session's toolset, no argument needed: when the Claude Desktop Browser-pane tools are present it runs PREVIEW mode (the primary target — `.claude/launch.json` + `preview_start`, the user sees every click); in a plain terminal it falls back to the `agent-browser` CLI (with the plugin's existing setup pre-flight).

- **Backend orchestration**: discovers the layout (single app or `frontend/`+`backend/` monorepo), and an instance already running on the device is **reused** (port + health check probe) — never duplicated, never killed; only when nothing is running does it start the dev script in the background and wait for health before touching the frontend.
- **Assisted loop**: the flow argument (free text, e.g. `"login"`) becomes a numbered test script; each step is announced, executed via page refs (click/type/forms), and verified against **four evidence sources** — UI state, console (an error fails the step), network calls (an unexpected 4xx/5xx fails the step even when the UI looks fine), and server logs — with screenshots as proof. No argument = smoke test. `browser` forces the external browser; `mobile`/`dark` set the viewport.
- **Safety rails**: never real credentials (seeded/test users only), never destructive actions unasked, created test data is named `test-…` and listed in the report. Servers are left running at the end — the user keeps interacting with the preview — with exact stop instructions for whatever the command itself started.
- Positioning vs `verify`: `verify` confirms one change, pointed and browser-only; `test` walks a flow with the stack up, preview-first. `bymax-web-verify` bumped to `1.1.0`.

### Changed — toolkit-wide sync with recent Claude Code capabilities

An audit of every plugin against the Claude Code `2.1.174`–`2.1.212` changelog range produced four more updates:

- **`bymax-pr` / babysit-pr — CI-duration-driven pacing.** The fixed 270 s wake-up was justified by the old 5-minute prompt-cache TTL; the TTL is now one hour, so cache pressure no longer dictates cadence. The delay is now chosen from what the loop is actually waiting for — remaining CI time estimated from the workflow's recent run durations, 900–1800 s when waiting on a review bot or human — with 270 s kept as the floor. Fewer wake-ups, same responsiveness.
- **`bymax-workflow` / autopilot — unattended-session hardening (new precondition 6).** Three launch checks matching how Claude Code now treats unattended sessions: recommend `CLAUDE_CODE_RETRY_WATCHDOG` (the supported retry mechanism now that `CLAUDE_CODE_MAX_RETRIES` caps at 15), confirm the login will not expire mid-chain (an expiring login interrupts background sessions), and pre-approve implementer permissions — background sub-agents no longer auto-deny on a permission prompt; they surface it in the main session and wait, which would stall the chain.
- **`personal/settings.template.json` — attribution off at the harness level.** New `attribution: { coAuthoredBy: false, sessionUrl: false }` block: the no-AI-attribution rule is now enforced by Claude Code itself (no `Co-Authored-By` trailer, no claude.ai session link on commits/PRs) instead of relying on prompt instructions.
- **`personal/settings.template.json` — `Notification` hook.** macOS notification on `Notification` events, which since 2.1.198 include background-agent signals (`agent_needs_input` / `agent_completed`) — a stalled babysit-pr or autopilot chain waiting on input now pings the operator instead of being discovered hours later.
- **`bymax-bootstrap` — seeds `REVIEW.md`.** Bootstrap now runs `/bymax-quality:review-md` after writing `CLAUDE.md`, so every new project starts with the cloud review calibrated; `claude-md.template.md` gained the pointer line.
- **`bymax-workflow` — explicit review depth at the two decision points.** Bare `/bymax-quality:code-review` calls stay backward compatible (no argument = `full`), but the two places where depth matters are now explicit: `/bymax-workflow:task` §2.3 (the phase-closing, pre-PR pass) runs `deep` — finder fan-out + adversarial verification — while the per-task Gate 3 keeps the cheaper `full`; and the autopilot implementer prompt pins `full` with a rationale — `deep` spawns finder sub-agents and implementers are sub-agents that never spawn (the orchestrator's merge gate is the deeper second opinion).

- `bymax-quality` bumped to `1.4.0`, `bymax-pr` to `1.1.0`, `bymax-workflow` to `1.4.2`, `bymax-bootstrap` to `1.1.3`, `bymax-web-verify` to `1.1.0`; `marketplace.json` to `1.7.0`. Toolkit totals: **19 slash commands**, 4 skills, 7 sub-agents, 3 hooks, 20 templates.

## [1.6.1] — 2026-07-08

### Fixed — autopilot: unresponsive review bot could hold the merge gate forever

The merge gate's "no pending review request" term had no time bound: if the config named a review bot and the `--add-reviewer` request was **accepted** but the bot never submitted a review (bot not enabled on the org, quota, outage), `reviewRequests` never emptied and the chain waited indefinitely — alive (the wake-up fallback kept re-invoking the orchestrator) but never merging. Repos with `Review bot: none` and rejected-slug requests were already handled; this closes the third path.

- **New `BOT_TIMEOUT` watcher verdict** (SKILL.md STEP 2/3 + playbook): a review request pending longer than the config's **review-bot timeout** (default 15 min, measured from the request or the latest push, whichever is later) triggers the unresponsive-bot procedure — confirm with a fresh read that no review arrived, remove the stale request (`gh pr edit --remove-reviewer`), leave one factual PR comment as the audit trail (a declared reviewer is never dropped silently), then re-evaluate the gate CI-only.
- **Safety rationale documented**: the review floor already ran before the PR opened (the implementer iterates `/bymax-quality:code-review` + `/security-review` to zero findings); the bot is a second opinion, and a dead second opinion must not become an infinite wait. If the bot reviews after the timeout cleared it, the normal rules resume — its threads must still be resolved before the merge executes.
- **`references/config-template.md`** — new "Review-bot timeout" field in the Review bot and Merge policy sections.
- `bymax-workflow` bumped to `1.4.1`; `marketplace.json` to `1.6.1`.

## [1.6.0] — 2026-07-08

### Added — `/bymax-workflow:autopilot` (loop-engineering executor)

A new skill in `bymax-workflow` that autonomously drives an **approved roadmap from first phase to done, one merge-gated PR per phase, with zero human interaction after launch** — the toolkit's [loop-engineering](https://addyosmani.com/blog/loop-engineering/) layer. It generalizes a per-project orchestration runbook proven on real multi-phase autonomous builds (10-phase / 50+-task library and application roadmaps) into a reusable skill: the invariant operational knowledge lives in the skill, and everything project-specific collapses into one reviewable config file.

- **`skills/autopilot/SKILL.md`** — the orchestrator. Three modes: `init` (generate `docs/AUTOPILOT.md` from the existing roadmap + task files, propose a per-phase model policy, **stop for user review** — init never chains into run), `run` (drive the chain: pick next phase → spawn implementer → background CI/review watch → fix findings → merge gate + grace window → squash-merge + branch deletion with proof → dashboard updates → next phase), and `status` (read-only chain report).
- **`references/operational-playbook.md`** — the architecture and battle-tested procedures, each rule annotated with the real failure it prevents: the orchestrator/implementer role split (the naive single-agent design **deadlocked** waiting for the review bot — background sub-agents die on long waits), one-implementer/one-suite memory safety (fanned-out test agents crashed a 36 GB machine past 70 GB), the merge-gate conjunction + grace window (a second bot review lands ~90 s after a push), fresh-thread-ID resolution (stale GraphQL IDs masquerade as permission errors), anti-hallucination verification (agents confabulate SHAs and merges — verify via `git`/`gh`, never narration), and the autonomy backbone (never end a turn without a pending background job or an armed wake-up).
- **`references/implementer-prompt.md`** — the rendered-per-phase prompt template. Implementers run in isolated git worktrees, execute the phase's task files with `/bymax-workflow:standards` + `/bymax-quality:tdd`, iterate `/bymax-quality:code-review` and `/security-review` **to zero findings**, open the PR, request the review bot, return the PR number, and STOP — they never wait, never merge, never spawn.
- **`references/config-template.md`** — the `docs/AUTOPILOT.md` per-project config: identity, external preconditions (e.g. Docker up, a dependency resolvable on a registry), a per-phase **model policy** with rationale (strong tier for first-contact/security-sensitive/final-hardening phases, cheaper tier where the merge gate catches everything), gates that grow by phase, invariant greps, security invariants and review focus, review bot, and merge policy (squash, grace window, stall limit).
- **README** — new "Loop Engineering: the Autopilot" section: the term's origin (Addy Osmani's June 2026 essay, synthesizing Peter Steinberger and Boris Cherny), the full loop diagram, the failure-per-rule authority table, the mapping of Osmani's five loop components (state & memory, sub-agents, worktrees, skills, automations) onto the toolkit's plugins, and the honest constraints (it merges; it is token-intensive by design; it requires the planning chain).
- `bymax-workflow` bumped to `1.4.0`; `marketplace.json` to `1.6.0`. Toolkit totals: 16 slash commands, **4 skills**, 7 sub-agents, 3 hooks, 20 templates.

## [1.5.0] — 2026-07-06

### Added — Simplicity ladder (§0) across `bymax-workflow` + `bymax-quality`

A reuse-first decision ladder — inspired by the ladder in [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) (MIT), adapted to the Bymax reality (`@bymax-one/*` libs, sibling projects, the `shared/` layer, and the vault's stack patterns) — now runs **before code is written** and is **enforced after**, at every stage of the pipeline:

- **`/bymax-workflow:standards`** — new stack-neutral **§0 Simplicity ladder**: before writing code, stop at the first rung that holds — (1) YAGNI, (2) reuse from this codebase, (3) reuse a `@bymax-one/*` lib / promote sibling-project code instead of copy-pasting, (4) stdlib/native platform (`Intl`, `crypto.randomUUID()`, `URL`, `structuredClone`, native `<input>` types; `std`/`core` on Rust), (5) installed dependency (a NEW dep needs justification), (6) build once as a reusable unit in `shared/` or `@bymax-one/*` when a second feature/project needs it, (7) only then the minimum that works. Carve-outs are explicit: trust-boundary validation, error handling, the security baseline, accessibility, and mandatory docs/tests are never on the chopping block. Output economy (fewer generated tokens) is documented as a side effect, not the goal.
- **`planner` sub-agent** — new mandatory **Reuse Scan (2b)** planning step: every proposed new file/component/dependency is walked down the ladder, and the plan's Architecture Changes section must justify each new file with "no existing code covers this because …".
- **`/bymax-workflow:plan`** — the reuse scan added as step 3 of the command flow (search codebase → `@bymax-one/*` → sibling projects → stdlib → installed deps before proposing new files).
- **`/bymax-quality:code-review`** — new **HIGH** checks: *reinvented wheel* (new code reimplementing an existing repo symbol, `@bymax-one/*` lib, stdlib/platform API, or installed dependency) and *new dependency for something already covered*. New **MEDIUM** checks: copy-pasted logic that should be one shared unit, and speculative generality (YAGNI).
- **`/bymax-quality:tdd`** — GREEN phase now runs the ladder before writing the body: an existing util, lib, or stdlib call may already BE the green; never add a dependency just to pass a test.
- `bymax-workflow` and `bymax-quality` bumped to `1.3.0`; `marketplace.json` to `1.5.0`. Additive only — no existing rule was weakened. The ponytail plugin itself was evaluated and **not** vendored: its always-on hooks and prompt overhead are redundant with the existing gates; only the ladder concept was adopted, Bymax-adapted.

### Added — "External tools & MCP servers" README guide

- New README section documenting every external tool the plugins consult at runtime ("require, don't embed"): the CLI toolchain per plugin (Node.js, `gh`, `agent-browser`, pnpm, Xcode/simctl, Android SDK, Rust + cargo extras) and the three optional MCP servers with install commands — **context7** (`@upstash/context7-mcp`, current official docs for the §0 docs-first rule), **obsidian vault** (`@bitbonsai/mcpvault`, per-stack `Patterns.md`/`Gotchas.md` consulted by the §0 reuse ladder), and **sequential-thinking**.
- `/bymax-workflow:standards` §0 hardened for portability: the knowledge-vault and Context7 references now degrade gracefully when the MCP is absent, and a new **"official docs beat trained memory"** rule verifies library/platform APIs against current docs before writing the call.
- `personal/README.md` documents the obsidian MCP restore command (registered via `claude mcp add` — machine-specific vault path, so it stays out of `mcp.template.json`).

### Added — graphify integration (graph-first reuse scan, opt-in)

Evaluated [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) (MIT) and adopted it the same way as ponytail: the capability, not the always-on mode.

- **`/bymax-workflow:standards` §0 rung 2** — when a project has a `graphify-out/` knowledge graph, the reuse scan goes **graph-first** (`graphify query` / `explain` / `path`) instead of grepping: scoped subgraph answers at a fraction of the tokens, with cross-file/cross-package edges resolved by tree-sitter AST. Grep remains the fallback when no graph exists and the authority for code changed since the last graph build.
- **`planner` sub-agent (Reuse Scan 2b)** and **`/bymax-workflow:plan` step 3** — same graph-first rule while planning.
- **`bymax-bootstrap`** — `gitignore.universal` now excludes `graphify-out/` (local, regenerable output); bumped to `1.1.2`.
- **README** — new "Code knowledge graph" section: how graphify works (local AST build, zero LLM tokens for code, SHA256-incremental, post-commit hook), how the toolkit consumes it (presence-gated, zero cost when absent), setup commands, and the explicit recommendation **against** `graphify claude install` (its always-on `PreToolUse` hooks add per-prompt overhead and conflict with the `bymax-quality` hooks).

### Changed — branding + contact unification

- Author/owner across `LICENSE`, README, all seven `plugin.json` files, and `marketplace.json` is now **Bymax One** (`support@bymax.one`), matching the `@bymax-one/*` library repos. All contact emails (`security@`, `conduct@`) consolidated to **support@bymax.one**.

### Added — `llms-install.md` (AI-agent installation runbook)

- New machine-oriented runbook at the repo root (the location AI agents like Cline probe for): idempotent steps with a verification command after each, decision points with defaults (core pair vs project-type plugins), explicit **HUMAN HANDOFF** markers for interactive steps (session restart, `gh auth login` OAuth, App Store/GUI installers), a DO-NOT list (never `scripts/install.sh`, never `bymax-all`-as-plugins, never `graphify claude install`, never a GitHub MCP), and per-symptom failure guidance. Linked from the README Quick Start.

### Fixed — full-repo audit (three independent review passes)

- **`/bymax-web-verify:verify` now actually exists** — the command file was `web-verify.md` (registering as `:web-verify`) while every documented invocation across 12 files said `:verify`; renamed the file to `verify.md`. `bymax-web-verify` bumped to `1.0.1`.
- **Canonical repo slug** — replaced the legacy dotted slug `bymaxone/bymax.claude-code` (alive only via GitHub's rename redirect) with `bymaxone/bymax-claude-code` across 24 files (badges, plugin.json homepages, marketplace.json, CHANGELOG links, CONTRIBUTING, install.sh, templates, vendor attribution).
- **Stale ECC-era references scrubbed** — `tdd.md` no longer claims a nonexistent `tdd-guide` agent or points to `/build-fix`, `/test-coverage`, `/e2e`; `plan.md` now correctly credits the `planner` sub-agent to the `bymax-quality` plugin; dead "Related Agents" ECC sections removed.
- **Portability** — `standards` §0 no longer hard-codes the author's machine layout (`~/Documents/MyApps/...`) or dangling "see the README" pointers inside the installable skill; org lib scope and sibling-repo locations are now declared per-project in `CLAUDE.md`.
- **Docs accuracy** — CHANGELOG compare links completed (1.1.1→1.5.0, Unreleased repointed); broken VS16-emoji anchors fixed (`## 🧱 Architecture`, `## 🔖 Versioning`); `brew install claude` corrected to the real Claude Code install command; the unsupported `--scope` flag claim replaced with the `enabledPlugins` mechanism; `/security-review` labeled as the Claude Code built-in; CONTRIBUTING's dead Discussions link → Issues and its local-dev install list completed (6/6 plugins); SECURITY.md hook-wiring and `scripts/install.sh` path corrected; vendor README gained the missing `marketplace add` line and a current ECC star count; tester skill report now includes Profile F; `bymax-all` description names the `bymax-pr` plugin correctly.

### Removed — github MCP from the restore flow

- The restore path (README step 6, `scripts/install.sh` hints, `personal/settings.template.json`, `personal/README.md`) no longer recommends the `@modelcontextprotocol/server-github` MCP. GitHub access is **`gh` CLI only** (`brew install gh && gh auth login`) — the same tool `bymax-pr:babysit-pr` requires. Rationale: `gh` uses a short-lived OAuth token that works across orgs whose token policies reject long-lived fine-grained PATs, which is what broke the MCP setup.

## [1.4.0] — 2026-06-17

### Added — Rust support across `bymax-workflow` + `bymax-quality`

The workflow and quality plugins are now **language-detecting**: TypeScript/JS behavior is unchanged, and a parallel **Rust track** activates when a `Cargo.toml` is present. This makes the full `spec → … → task` quality cycle usable on Rust projects (first consumer: the `rust-auth` library).

- **`/bymax-workflow:standards`** — new **§15 Rust track** (edition/MSRV pinning, `cargo clippy -- -D warnings` + `cargo fmt`, no `unwrap`/`expect`/`panic!` on lib paths, typed `thiserror` errors, `#![forbid(unsafe_code)]`, rustdoc `//!`/`///` + `#![deny(missing_docs)]`, `#[test]` discipline, `cargo deny`/`audit`/`vet` supply chain, RustCrypto/`subtle`/`secrecy` security baseline) + a "which track applies" detector and a TS→Rust tooling map.
- **`/bymax-workflow:verify`** — Rust gate set (`fmt`/`clippy`/`build`/`test`/`llvm-cov`/`deny`/`audit` + wasm build) and Rust suppressions (`#[allow]`-to-dodge, `unsafe`, `#[ignore]`, `unwrap`-in-lib) added to the scan.
- **`/bymax-workflow:task`** — stack detection in Step 0, `rust-reviewer` dispatch, and a stack-adaptive close-phase audit.
- **`/bymax-quality:code-review`** — Rust CRITICAL/HIGH/MEDIUM checks; the Tailwind/TS-syntax checks are skipped on Rust.
- **`/bymax-quality:tdd`** + the **`tester`** skill — a Rust variant of the red-green-refactor cycle and a new **Profile F (Rust)** (`#[cfg(test)] mod tests` + `cargo test` + `cargo llvm-cov`).
- **New `rust-reviewer` sub-agent** (ownership/borrow, typed errors, async/Tokio soundness, `unsafe` discipline, idiomatic crate design); **`code-reviewer`** and **`security-reviewer`** made Rust-aware.
- `bymax-workflow` and `bymax-quality` bumped to `1.2.0`; `marketplace.json` to `1.4.0`. TypeScript/JS behavior is fully preserved (additive only).

### Changed — `bymax-pr` review-thread resolution

- **`/bymax-pr:babysit-pr`** — hardened the GraphQL review-thread resolution: re-fetch thread IDs fresh each turn, match every thread to its comment by `databaseId`, check `viewerCanResolve`, and verify `isResolved` before reporting; added anti-stale-ID / anti-hallucination rules so a `FORBIDDEN` / `NOT_FOUND` is treated as a stale-ID symptom, not a permission wall. `bymax-pr` bumped to `1.0.1`.

## [1.3.0] — 2026-05-22

### Added — `bymax-pr` plugin (autonomous PR babysitting)

A new optional plugin that autonomously drives an open pull request to merge-readiness on **any** project, powered by the [`gh`](https://cli.github.com/) CLI. Like `bymax-mobile` and `bymax-web-verify`, it follows the "require, don't embed" pattern — it depends on `gh` + `git` but never bundles them.

- **`/bymax-pr:babysit-pr`** — wakes up every 270s (`ScheduleWakeup`, inside the prompt-cache TTL) and runs four phases per pass: conflict auto-rebase → CI monitoring (classifies failures **real vs flaky**, re-running flaky checks up to 3× via `gh run rerun --failed`) → bot-comment triage (4-tier, resolves threads via GraphQL) → termination check (fires a `PushNotification` when green). State persists in a `<!-- babysit-state -->` PR comment, so the loop is idempotent across wake-ups and session restarts.
- **Phase −1 preflight** — verifies the `gh` CLI is installed **and** authenticated, stopping with exact install / `gh auth login` instructions if not. `gh` is an execution prerequisite, so it's checked inside the skill (no SessionStart hook).
- **Project-agnostic** — auto-detects the package manager and lint/test/typecheck/build scripts, and respects the project's own `CLAUDE.md` / `AGENTS.md`. **Never merges**, never pushes to the base branch, never force-greens a check.
- **`marketplace.json`** bumped to `1.3.0`; new `bymax-pr` entry added (category `workflow`); `bymax-all` reference (manifest + README) updated to list all six functional plugins.

### Added — third-party design skills fetched on restore

`scripts/install.sh` now optionally fetches three third-party **design** skills from their upstream repos via the `skills` CLI (`npx skills add … --global`) — **not** vendored, for licensing + freshness:

- **[Emil Design Engineering](https://github.com/emilkowalski/skill)** (Emil Kowalski), **[Impeccable](https://github.com/pbakaus/impeccable)** (Paul Bakaus, Apache-2.0), and a **[Taste-Skill](https://github.com/Leonxlnx/taste-skill)** subset (Leonxlnx, MIT: `design-taste-frontend`, `redesign-existing-projects`, `minimalist-ui`, `industrial-brutalist-ui`, `high-end-visual-design`).
- New `--no-design-skills` flag skips the fetch. Documented in `vendor/README.md` and the README restore table.

### Fixed — docs caught up with `bymax-web-verify`

The `1.2.0` plugin was missing from the README plugin list, repo tree, install blocks, and `bymax-all`. All are now complete and consistent (6 installable plugins, 16 slash commands, 3 skills, 6 sub-agents, 3 hooks).

## [1.2.0] — 2026-05-20

### Added — `bymax-web-verify` plugin (real-browser verification)

A new optional plugin that brings real-browser verification to the toolkit via the [`agent-browser`](https://github.com/vercel-labs/agent-browser) CLI (Vercel Labs, Apache-2.0). It follows the same "require, don't embed" pattern as `bymax-mobile`: it depends on the external CLI rather than bundling it, so the CLI's own version-matched skills never drift.

- **`/bymax-web-verify:setup`** — one-shot, idempotent installer for the `agent-browser` CLI **and** its Chrome for Testing engine, finished with a live smoke test. Designed as a portable backup step after a fresh macOS install. Refuses `sudo`; points at `nvm` on `EACCES`.
- **`/bymax-web-verify:verify`** — drives a real browser to confirm a web change works: opens a URL (auto-probes local dev ports `3000, 5173, 8080, 4321, 3001`), exercises the path using snapshot refs, and reports PASS/FAIL with a screenshot plus console/page errors. Read-only by default.
- **`SessionStart` hook** (`check-agent-browser.sh`) — silent when the CLI is present; when missing, injects `additionalContext` so Claude can proactively offer `/bymax-web-verify:setup`. Never installs unprompted, never blocks the session.
- **`marketplace.json`** bumped to `1.2.0`; new `bymax-web-verify` entry added (category `quality`); `bymax-all` reference updated to list the fifth plugin.

## [1.1.1] — 2026-05-08

### Changed — qualified plugin slash references for namespace correctness

Per the official Claude Code [Plugins reference](https://code.claude.com/docs/en/plugins), plugin skills and commands are always namespaced as `/<plugin>:<skill>` to prevent conflicts when other marketplaces ship a command with the same short name (e.g., `engineering:code-review`, `product-management:brainstorm`). Internal cross-references inside bymax plugin files were using bare names (`/tdd`, `/verify`, `/code-review`), which would silently resolve to the wrong plugin in users' multi-marketplace setups.

- **All cross-references qualified** with the `bymax-<plugin>:` prefix in 35 files (`commands/*.md`, `skills/*/SKILL.md`, `agents/*.md`, plugin `README.md`, and bootstrap `templates/`). 232 references in total.
- **Marketplace + plugin manifest descriptions** also qualified — the `description` field of `marketplace.json` plugin entries and each `<plugin>/.claude-plugin/plugin.json` now show the canonical `/bymax-quality:tdd` form instead of bare `/tdd`. Display-only field, but consistency matters in the plugin browser UI.
- **`/security-review` left bare** — it is the user-level vendor skill / built-in Claude Code command, not a bymax plugin command.
- **No double-prefix and no mangled command arguments** (verified: `/bymax-workflow:checkpoint verify "core-done"` still parses with `verify` as an arg, not as a slash command).
- **`claude plugin validate` passes** on the marketplace and on all five plugin manifests.

## [1.1.0] — 2026-05-08

### Changed — schema migration to Claude Code v2.1.x plugin marketplace

Claude Code's plugin marketplace tightened the schema between v2.1.128 and v2.1.133. The bymax repo has been migrated so `claude plugin validate` passes on every plugin and `claude plugin install` works out of the box.

- **`marketplace.json`** moved to the new schema: now requires `owner` (object); each plugin entry uses `source` (relative path string `./plugins/<name>` for in-repo plugins) instead of the old `path` field; the obsolete root-level fields (`displayName`, `homepage`, `repository`, `author`, `license`, `keywords`) have been removed.
- **`plugin.json`** moved from `<plugin>/plugin.json` to **`<plugin>/.claude-plugin/plugin.json`** for all five plugins. The old root-level `plugin.json` files were removed.
- **Hooks config** moved from inside `bymax-quality/plugin.json` to **`bymax-quality/hooks/hooks.json`** (the convention used by official marketplace plugins).
- **YAML frontmatter** in 10 command files (`bootstrap`, `upgrade-standards`, `code-review`, `tdd`, `checkpoint`, `phase-tasks`, `plan`, `roadmap`, `spec`, `task`) had unquoted `description:` values containing inline `Triggers:`, `Modes:`, or `Args:` substrings — Claude Code's stricter YAML parser silently dropped the entire frontmatter. The descriptions are now wrapped in YAML single quotes.
- **`bymax-all`** demoted from "auto-install everything" meta-plugin to a docs-only reference index. Claude Code's plugin manifest does not support cross-plugin `dependencies`, so the previous `bymax-all` install command was a no-op. Users now install the four real plugins individually.
- **`install.sh`** dropped the plugin-symlinking section. Plugins are installed via `claude plugin install` against the marketplace; the script keeps its vendor / personal / MCP backup logic.
- **`validate.sh`** rewritten on top of `claude plugin validate` so it stays aligned with whatever schema the installed Claude Code expects.

## [1.0.0] — 2026-04-25

Initial public release of the toolkit. Five composable plugins, six specialist sub-agents, two pre/post hooks, twenty stack-aware project templates, a phased planning workflow with explicit user-approval gates, and a strict-quality `/standards` skill referenced by every other command.

### Added

#### `bymax-workflow` — phased planning + execution

- **`/spec`** — Layer 1 of the feature workflow. Drafts a complete technical spec (goal, scope, user stories, success criteria, technical approach, constraints, risks, open questions). Asks clarifying questions if the request is vague.
- **`/roadmap`** — Layer 2. Takes an approved spec and produces a phased master plan with a status dashboard, dependency DAG, and definition-of-done per phase.
- **`/phase-tasks`** — Layer 3. Takes an approved roadmap and scaffolds JIRA-style task files with verbose self-contained agent prompts (Role / PROJECT / PRECONDITIONS / REQUIRED READING / TASK / DELIVERABLES / Constraints / Verification / Completion Protocol).
- **`/task`** — End-to-end executor with `/verify` → `/security-review` → `/code-review` chain and a completion-protocol that closes the phase by auditing every acceptance criterion. Modes: `/task phase <N>` runs all tasks in a phase; `/task <task-id>` runs one task only. Never auto-commits.
- **`/brainstorm`** — Pre-spec idea refinement: clarifying questions, alternatives, tradeoffs. Hands off to `/spec` only after explicit user approval.
- **`/plan`** — Lightweight single-PR planning command for small tasks that don't need the full spec → roadmap → phase-tasks chain.
- **`/verify`** — Five-gate post-implementation verification (static checks, exercise the change, root-cause vs. symptom, regression scan, acceptance criteria audit).
- **`/checkpoint`** — Named SHA + tests + coverage snapshots so you can compare against a baseline later (e.g., "did this refactor regress tests?"). Logs to `.claude/checkpoints.log`.
- **`/standards` skill** — universal coding rules referenced by every other command. **14 sections**: 1. TypeScript discipline (strict + `noUncheckedIndexedAccess`, zero `any`, banned `// @ts-ignore`); 2. Naming conventions; 3. Code documentation (JSDoc on every export); 4. Test documentation (mandatory `it()` block comments); 5. Layered architecture (`app` → `features` → `shared`, no cross-feature imports); 6. Imports (alphabetical, alias-only); 7. Error handling (validate at boundaries, never swallow); 8. Suppression comments — zero tolerance; 9. Conventional Commits; 10. Performance; 11. Accessibility (WCAG AA); 12. Tailwind CSS conventions (full v3 vs v4 split, canonical-class shortcuts, default scale, ARIA boolean variants, renamed utilities, type scale, filter px scale, z-index integers, negative zero); 13. Security baseline (banned imports — `crypto` → `node:crypto`, `bcrypt` → `argon2`, `crypto-js`/`md5`/`uuid`/`nanoid` → `crypto.randomUUID`); 14. Conflict-resolution rules.

#### `bymax-quality` — review + testing + agents + hooks

- **`/code-review`** — CRITICAL → HIGH → MEDIUM → LOW severity review with **hard ban on suppression comments** (`@ts-ignore`, `eslint-disable`, `as any`, `--no-verify`), and **30+ Tailwind v4 canonical-class patterns** flagged on Tailwind 4 projects (skipped on v3 / NativeWind 4): CSS variable shorthand (`[var(--x)]` → `(--x)`), ARIA boolean variants (`aria-[invalid=true]:` → `aria-invalid:`), on-scale `rem` values (`[8rem]` → `32`), gradient renames (`bg-gradient-to-r` → `bg-linear-to-r`), scale shifts (`shadow` → `shadow-sm`, `rounded` → `rounded-sm`, etc.), individual renames (`outline-none` → `outline-hidden`, `flex-shrink-*` → `shrink-*`, etc.), opacity-modifier deprecation (`bg-opacity-50` → `bg-blue-500/50`), arbitrary z-index integers (`z-[200]` → `z-200`), on-scale filter px (`backdrop-blur-[12px]` → `backdrop-blur-md`), and negative zero (`-bottom-0` → `bottom-0`).
- **`/tdd`** — Strict red-green-refactor cycle. Forces failing test before implementation. 80%+ coverage minimum (100% on critical paths). Every `it()` carries a block comment per `/standards` § 4.
- **`tester` skill** — Multi-stack test writer that auto-detects the project's stack (Jest / Vitest / React Native / React DOM / pure logic). 100% file coverage. Every `it()` carries a scenario + rule-it-protects comment. No fake `className`s, no fake branches.
- **6 specialist sub-agents** — `architect` (system design, scalability), `code-reviewer` (quality + security + maintainability), `database-reviewer` (PostgreSQL + Supabase patterns), `planner` (complex-feature planning), `security-reviewer` (OWASP Top 10, SSRF, injection, unsafe crypto), `typescript-reviewer` (type safety, async correctness, idiomatic patterns). All Sonnet/Opus, never Haiku.
- **`secret-scanner` hook** (PreToolUse Write/Edit/MultiEdit) — **blocks** the write if the new content contains a plausible credential: AWS keys, GitHub PATs, OpenAI / Anthropic / Stripe / Slack tokens, JWTs, or PEM private keys. Allowlists test fixtures, examples, docs, and `node_modules`. Exit 2 on block.
- **`console-log-scan` hook** (Stop) — warns on stray `console.log/warn/error/debug/info` in git-modified TS/JS files at session end. Cheap exits (skips silently if not in a git repo or no JS/TS modified).

#### `bymax-bootstrap` — project scaffolding

- **`/bootstrap`** — Scaffold a new project with all the standards wired in one shot. Detects the stack and picks the right ESLint preset. Detects Tailwind major version and recommends the right plugin set (`prettier-plugin-tailwindcss` for v3+v4, plus `eslint-plugin-tailwindcss` and the new overlay for v4). Writes `.vscode/`, `tsconfig.json`, `.prettierrc.json`, `.editorconfig`, `.gitignore`, `commitlint.config.cjs`, `lint-staged.config.cjs`, `.husky/{pre-commit,commit-msg}`, and a `CLAUDE.md` filled with the detected stack.
- **`/upgrade-standards`** — Non-destructive incremental upgrade for existing projects: adds what's missing (`.vscode`, Prettier, Husky, EditorConfig, CLAUDE.md), proposes strengthening tsconfig and ESLint with explicit user confirmation per change. Never overwrites existing configs silently.
- **20 templates**:
  - **6 ESLint flat-configs** — `eslint.config.universal.cjs` (base: `eslint-plugin-security`, import-order, suppression bans, risky-import bans), `eslint.config.next.cjs` (Next 15+/16, App Router or Pages), `eslint.config.expo-rn.cjs` (Expo / React Native), `eslint.config.vite-react.cjs` (Vite + React, SPA or library), `eslint.config.node.cjs` (Express / Fastify / Hono / NestJS / plain Node), `eslint.config.tailwind.cjs` (overlay — auto-detects v3/v4 and applies the right rule set; canonical-class warnings on v4 only).
  - **Strict TypeScript** — `tsconfig.universal.json`.
  - **Formatting** — `prettier.universal.json`, `editorconfig.universal`.
  - **Git hygiene** — `gitignore.universal`, `husky-pre-commit`, `husky-commit-msg`, `commitlint.universal.cjs`, `lint-staged.universal.cjs`.
  - **VS Code** — `vscode-settings.json` (format-on-save), `vscode-extensions.json`.
  - **Project docs** — `claude-md.template.md` (lean per-project `CLAUDE.md`).
  - **Workflow docs** — `spec.template.md`, `roadmap.template.md`, `phase-tasks.template.md`.

#### `bymax-mobile` — iOS Simulator + Android Emulator

- **`/sim-ios`** — Boots the iOS Simulator (default `iPhone 17`, override via `$BYMAX_SIM_IOS`) and runs the current Expo / React Native project. Auto-detects whether `expo start` (Metro reattach — fast) or `expo run:ios` (full rebuild + install + launch — slow) is the right call, using a build-artifact heuristic on `ios/build` and `ios/Pods`. macOS only.
- **`/sim-android`** — Boots an Android emulator (first AVD listed by `emulator -list-avds`, override via `$BYMAX_SIM_ANDROID`) and runs the current Expo project. Same start-vs-run heuristic on `android/app/build/outputs`. macOS / Linux. Prints exact install steps if the Android SDK or AVDs are missing.
- Both commands: auto-detect the package manager (`pnpm` if `pnpm-lock.yaml`, else `yarn`, else `npm`), honor `$APP_VARIANT` for Expo build flavors, and pre-flight tooling + project shape with actionable error messages.

#### `bymax-all` — meta-plugin

- Pulls in `bymax-workflow` + `bymax-quality` + `bymax-bootstrap` + `bymax-mobile` in one shot. Recommended starting point.

#### Repo

- **`README.md`** — badges (Node 24+, TypeScript strict, React 19, Next 16, Expo 55, RN 0.85, Vite 7, Express 5, Fastify 5, Hono 4, NestJS 11, Tailwind 4, NativeWind 4, ESLint 9, Prettier 3, Jest 30, Vitest 3, Husky 9, commitlint 19, lint-staged 15), tables, and emoji-rich sections grouped by category. Quick Start with à-la-carte plugin install. Personal Restore section with full step-by-step for restoring the toolkit on a new Mac (clone → dry-run → install.sh → settings → MCPs → marketplace plugins → github MCP → restart).
- **`LICENSE`** (MIT), **`CONTRIBUTING.md`**, **`CHANGELOG.md`**, **`SECURITY.md`**, **`CODE_OF_CONDUCT.md`**, **`.gitignore`**.
- **`.github/`** — `workflows/validate.yml` (runs `scripts/validate.sh` on every push and PR), `ISSUE_TEMPLATE/{bug_report,feature_request}.md`, `PULL_REQUEST_TEMPLATE.md`.
- **`templates/`** — reusable `CLAUDE.md`, `AGENTS.md`, and `README.md` starters distilled from real production projects.
- **`vendor/`** — MIT-licensed third-party skills bundled as personal backup with original `LICENSE` and `ATTRIBUTION.md` preserved per upstream MIT terms (**not** redistributed via the marketplace):
  - **`vendor/ecc-skills/`** — seven domain-knowledge skills extracted from [Everything Claude Code](https://github.com/affaan-m/everything-claude-code) by Affaan Mustafa: `api-design`, `backend-patterns`, `coding-standards`, `database-migrations`, `frontend-patterns`, `postgres-patterns`, `security-review`.
  - **`vendor/ui-ux-pro-max/`** — full UI/UX design intelligence skill from [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) by nextlevelbuilder.
- **`personal/`** — author's project-specific extras (sanitized; safe to publish): `settings.template.json` (with `{{PLACEHOLDERS}}` and inline `_comment_*` keys documenting the full restore flow), `mcp.template.json` (`context7` + `sequential-thinking` user-scope MCPs), `prettier-format.sh` (PostToolUse Write/Edit hook).
- **`scripts/install.sh`** — symlinks every plugin's `commands/`, `agents/`, `skills/`, `hooks/`, and `templates/` into `~/.claude/`; symlinks `vendor/ecc-skills/*.md` and `vendor/ui-ux-pro-max/` too; symlinks `personal/prettier-format.sh`; copies (not symlinks) `personal/mcp.template.json` to `~/.mcp.json` (no-clobber). Idempotent. Flags: `--dry-run` (preview without writing), `--no-vendor`, `--no-personal`, `--no-mcp`, `--plugins-only`, `--write-mcp-enabled` (also writes `~/.claude/settings.local.json` with `enabledMcpjsonServers`).
- **`scripts/validate.sh`** — validates `marketplace.json` and every `plugin.json` (valid JSON, required fields, every command/agent/skill path exists, every command file has a YAML frontmatter `description`, every agent file has `name` + `description` + `tools`, every shell hook is `chmod +x`, shellcheck on every shell script when installed, every required project-level file is present). Used by CI and locally before pushing.
- **`docs/PROPOSAL.md`** — original design proposal preserved for context.

[Unreleased]: https://github.com/bymaxone/bymax-agent-kit/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.12.0...v2.0.0
[1.12.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.9.0...v1.12.0
[1.9.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.6.1...v1.7.0
[1.6.1]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/bymaxone/bymax-agent-kit/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/bymaxone/bymax-agent-kit/releases/tag/v1.0.0
