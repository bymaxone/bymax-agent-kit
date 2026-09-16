# Install and use Bymax in Codex

This repository distributes a **separate Codex plugin** alongside its Claude Code
marketplace. The Codex package contains 27 skills, bundled Bymax source references,
and a native code-review procedure. Installing it does not install Claude Code,
change Claude settings, or register Claude hooks.

## Give this repository to a Codex agent

Use this request:

> Install the Codex integration from https://github.com/bymaxone/bymax-claude-code.
> Read CODEX.md first, clone the repository into a persistent local directory if
> needed, run scripts/install-codex.sh, and verify the installed package. Do not
> run scripts/install.sh, which restores the author's Claude configuration.

The agent needs local filesystem and shell access. An ordinary web chat cannot
install a local Codex plugin. Keep the checkout: it is the registered local
marketplace used for updates. A directory containing spaces is supported.

For complete prerequisites, dual-review shipping and optional capabilities, read [INSTALL.md](INSTALL.md).

## Installation

Prerequisites: Git, Python **3.10+**, and a Codex CLI supporting `codex plugin
marketplace add`, `codex plugin add`, and JSON plugin listings. Obtain/update the
CLI through the [official Codex installation documentation](https://developers.openai.com/codex/cli/).
No PyYAML, Claude login, GitHub token, MCP server, browser or additional model
subscription is required just to install the toolkit. If a prerequisite is
missing, the installer stops and names it; install that prerequisite and rerun.

From a persistent checkout:

```bash
git clone https://github.com/bymaxone/bymax-claude-code.git
cd bymax-claude-code
./scripts/install-codex.sh --dry-run
./scripts/install-codex.sh
./scripts/install-codex.sh --check
```

The installer validates the bundled source snapshot, registers `./codex` as the
`bymax-codex` marketplace, installs `bymax-codex@bymax-codex`, checks the actual
cached files and reads installed/enabled state back from Codex. It uses the CLI's
configuration mechanisms and does not overwrite `config.toml` or unrelated
plugins. If that marketplace name already points elsewhere, it stops instead
of silently replacing another checkout. A failed install can leave the marketplace
registered; rerunning is safe. It does not roll back unrelated configuration.

The underlying commands are:

```bash
codex plugin marketplace add /absolute/path/to/bymax-claude-code/codex
codex plugin add bymax-codex@bymax-codex
codex plugin list --marketplace bymax-codex --json
```

Register the **`codex/` directory**, not the repository root. The root's
`.claude-plugin/marketplace.json` is the Claude marketplace. This layout deliberately
uses a clone-and-install flow rather than claiming that a bare Git marketplace
URL selects the Codex subdirectory automatically.

Start a **new Codex task** after installation. Select `bymax-code-review` from the
skill picker (CLI/IDE: `$bymax-codex:bymax-code-review`) and run a review in a target project.
Installed/enabled CLI state and actual skill discovery are separate checks; the
installer verifies the first, and the new task verifies the second.

## Code review

Examples of requests in a Codex task:

```text
Use $bymax-codex:bymax-code-review to review my uncommitted changes.
Use $bymax-codex:bymax-code-review deep branch:feature/auth against origin/trunk.
Use $bymax-codex:bymax-code-review full origin/trunk...HEAD.
Use $bymax-codex:bymax-code-review quick path:src/auth.ts.
Use $bymax-codex:bymax-code-review to review PR #123.
Use $bymax-codex:bymax-code-review full --adversarial to challenge this design too.
```

The review captures immutable revisions or working-tree evidence, includes staged,
unstaged and untracked content, and rechecks freshness before reporting. It does
not switch branches, stage files, launch Claude, recursively invoke Codex reviews,
commit, push, merge or post comments. Deep review uses independent-context finder
agents when the host provides them; unavailable passes are disclosed. A shared
model family is never presented as independent model-family corroboration.

The target project's `AGENTS.md` overrides toolkit defaults. Regex hits are
verified in context, including documentation examples, test fixtures, configured
lint rules and accepted exceptions. Findings cite the actual reviewed file
version and evidence. Scope failures produce `INCOMPLETE`; no changes produce
`NO CHANGES`. Neither is silently turned into approval.

**No push gate is installed.** A Codex review does not create the marker some
Claude integrations require. Existing hooks remain authoritative; do not bypass
them or fabricate a marker. Test-suite success is reported only when tests ran.

## Available workflows and capability boundaries

The table uses short names. Installed skills are namespaced as
`bymax-codex:<short-name>`; use the picker or that full name when mentioning one.

| Area | Codex skills | Requirements or adaptation |
| --- | --- | --- |
| Review | `bymax-code-review`, `bymax-review-md`, `bymax-codex-setup` | Native review; review-md still targets Anthropic cloud REVIEW.md, not Codex policy |
| Standards and tests | `bymax-standards`, `bymax-tester`, `bymax-tdd` | Target stack and its installed test tools |
| Planning | `bymax-brainstorm`, `bymax-spec`, `bymax-roadmap`, `bymax-phase-tasks`, `bymax-plan` | Bundled procedures and templates |
| Execution | `bymax-task`, `bymax-checkpoint`, `bymax-verify` | Target repository gates; quick verification does not claim full readiness |
| Bootstrap | `bymax-bootstrap`, `bymax-upgrade-standards` | Bundled templates; preserve existing Claude guidance |
| Shipping | `bymax-push`, `bymax-babysit-pr` | Git; authenticated `gh` for GitHub; scheduler for deferred monitoring; babysitter never merges |
| Web | `bymax-web-setup`, `bymax-web-test`, `bymax-web-verify`, `bymax-web-record` | Available Codex browser tools or installed agent-browser CLI |
| Mobile | `bymax-sim-ios`, `bymax-sim-android` | Xcode/simulator or Android SDK/emulator plus the app's dependencies |
| Orchestration | `bymax-pm`, `bymax-autopilot` | Available Codex worker coordination; durable continuation for unattended execution |
| Audit | `bymax-audit` | Static work supported; independent verifier required to admit findings; live probes require explicit scope and suitable host controls |

PM, autopilot, browsers and monitoring adapt to capabilities available in the
current Codex host. They do not install nonexistent APIs or promise continuation
without a successful scheduling response. QA's Claude guard and probe wrapper
are not ported: a workflow depending on those protections is blocked explicitly,
while independent static work can proceed. These are capability-aware adapters,
not a claim of complete Claude runtime parity.

Codex-owned operational state lives under `.bymax/codex/` in target projects.
Keep it out of commits unless deliberately publishing a sanitized artifact;
review captures can contain credentials and should stay in private temporary
storage. Existing planning document locations remain as selected by the user.

Vendor backups, personal settings, and third-party design plugins are not part of
this installation. The Claude `bymax-all` entry is an index; this Codex package
already includes every first-party command/skill entrypoint in one installation.

## Updates and removal

Review your local status, then update the persistent checkout with `git pull
--ff-only` and rerun `./scripts/install-codex.sh`. Do not discard local changes to
force an update. Releases changing Codex content must bump its own manifest
version so Codex refreshes the cache. The installer detects a same-version stale
cache instead of reporting success. `--check` verifies registration/version/state;
a full installer run also compares cached bytes.

To remove only this integration:

```bash
codex plugin remove bymax-codex@bymax-codex
codex plugin marketplace remove bymax-codex
```

## Development and verification

The architecture and maintenance procedure are in [codex/README.md](codex/README.md).
Runtime source remains under `plugins/`; the Codex package ships exact copies
under its own references so an installed cache is self-contained. Never edit the
copies. Source changes require rebundling and, when released, a Codex version bump.

```bash
python3 codex/scripts/bundle.py
./scripts/validate.sh
./scripts/validate-codex.sh
```

Development validation requires PyYAML as the existing Claude validator does.
The Codex gate checks source drift, all 27 entrypoints, portable links, manifest
contracts and real Git regression scenarios. With the Codex CLI installed it also
runs an isolated installation and actual `skills/list` discovery test. CI requires that CLI test explicitly. It does
not bill a model call or change your real Codex/Claude configuration.
