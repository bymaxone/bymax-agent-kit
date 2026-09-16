# Install, update and verify Bymax

This checkout contains two independent plugin packages: eight Claude Code plugins and
one Codex plugin with 27 skills. A plugin installation supplies instructions, not the
project's dependencies, accounts, simulator or browser. This guide covers the complete
setup for autonomous dual-review shipping and the optional skill families.

## Core prerequisites

Use macOS or Linux for dual review: its file locks use Python's `fcntl`. On Windows,
use a Linux environment such as WSL and install both CLIs there. Keep the checkout at
a persistent path and use Python 3.10 or later, Git, Claude Code, Codex CLI and GitHub CLI.
Install those tools from their official guides:

- [Claude Code setup](https://code.claude.com/docs/en/setup)
- [Codex CLI](https://developers.openai.com/codex/cli)
- [GitHub CLI](https://cli.github.com/manual/installation)
- [Python](https://www.python.org/downloads/) and [Git](https://git-scm.com/downloads)

Authenticate locally; never paste tokens into this repository:

```bash
claude auth login
codex login
gh auth login
```

A usable subscription or API account is required for each model CLI. Availability,
rate limits and costs depend on those accounts. GitHub authentication needs access to
the target repository and permission to push the intended branch. Enterprise policy
or platform approval prompts cannot be bypassed by a skill.

Clone this repository and run subsequent installation commands from its root:

```bash
git clone https://github.com/bymaxone/bymax-claude-code.git
cd bymax-claude-code
```

## Claude package

Register the marketplace and install all eight components:

```bash
claude plugin marketplace add bymaxone/bymax-claude-code
claude plugin install bymax-quality@bymax-claude-code
claude plugin install bymax-workflow@bymax-claude-code
claude plugin install bymax-pr@bymax-claude-code
claude plugin install bymax-bootstrap@bymax-claude-code
claude plugin install bymax-mobile@bymax-claude-code
claude plugin install bymax-web-verify@bymax-claude-code
claude plugin install bymax-pm@bymax-claude-code
claude plugin install bymax-qa@bymax-claude-code
```

Install the shared reviewer runtime, global push handoff and managed policy:

```bash
python3 scripts/install-review-flow.py
```

It backs up affected files under `~/.claude/backups/`, preserves unrelated settings,
and copies all runtime dependencies into `~/.claude/bymax-review/`. Restart Claude
Code to reload instructions. For local development only, `--local-plugin-overlay`
also copies this checkout into the installed quality, workflow and PR caches; official
plugin updates may replace that overlay. Do not run `scripts/install.sh` for an ordinary
plugin installation: it restores the author's personal/vendor/MCP configuration.

The bounded reviewer uses the Codex CLI directly. The separate OpenAI Codex Companion
plugin is optional; if installed, keep its workspace stop-time review gate disabled
with its supported `/codex:setup --disable-review-gate` command. Do not add a second
mandatory built-in review or an automatic Stop-hook model review to this workflow.

## Codex package

```bash
./scripts/install-codex.sh
./scripts/install-codex.sh --check
```

The installer verifies the bundle, registers this checkout as a local marketplace,
installs/enables the plugin and compares installed cache bytes. Start a new Codex task.
Invoke `bymax-codex:bymax-code-review` using the skill picker or by name. See
[CODEX.md](CODEX.md) for all entrypoints. Standalone review needs only Codex; dual-review
shipping additionally needs the Claude CLI and the shared runtime installed above.
No Claude global hooks are installed by the Codex installer itself.

## Prepare each target project

- Install that project's own dependencies and verify its documented test/build/lint
  commands. The review context must declare the actual required commands.
- Maintain project-specific `AGENTS.md`, `CLAUDE.md` where used, and PR review guidance
  such as `REVIEW.md`. The `review-md` workflow can generate review guidance; inspect
  its output against the project's real invariants instead of importing generic nits.
- Work on a feature branch with a known destination and integration base. A candidate
  must be committed and clean; unrelated staged/unstaged files are not silently included.
- `review_flow.py start --autonomous` installs the Git pre-push checker if absent. An
  existing foreign hook or custom `core.hooksPath` must preserve its existing checks
  and delegate to the installed `review_prepush.py`, passing Git's stdin and returning
  its failure. The runtime tests compatibility; it never overwrites foreign hooks.
- Read [autonomous delivery](plugins/bymax-quality/references/autonomous-delivery.md).
  Ask the agent to push, or invoke `/bymax-pr:push` in Claude / `bymax-codex:bymax-push`
  in Codex. The agent completes both reviews, verified corrections, checks and push.
  In Claude an early blocked push returns continuation instructions to that agent.
  A bare terminal cannot run skills; Git only verifies its receipts.

## Optional skill prerequisites

| Skills | Additional requirements |
| --- | --- |
| Planning, spec, roadmap, checkpoint, standards | Repository files and applicable project instructions; no external account |
| Task, TDD, tester, verify, bootstrap | The target's Node/package manager or Rust toolchain and dependencies; use its actual gates |
| Push and babysit | `gh` authenticated, correct Git remote, repository access; monitoring needs the host's scheduler or an active supervised session |
| Autopilot | Approved roadmap/config, isolated worktree support, subagents, and supported durable continuation or supervised execution |
| PM | Addressable workers and supported messaging; a status board alone does not create workers |
| Web setup/test/verify/record | A running non-production app; supported browser tools or `agent-browser` and its installed browser engine; follow the web-setup skill |
| iOS simulator | macOS, Xcode, selected command-line tools, an installed simulator runtime, and the target Expo/React Native dependencies |
| Android simulator | Android SDK, emulator/system image and `adb`; the target Expo/React Native dependencies |
| QA audit | Explicit scope, independent verifier capability; static tools as available. Live probes require approved non-production hosts and `--live`; Codex has no Claude QA hook parity |
| Secret/config hooks and QA shell helpers | Bash and each helper's prerequisites, including `jq` where used; scanners are capability-dependent, not bundled |

Missing optional capabilities must be reported as unavailable, never as successful
verification. Do not install every scanner or external connector to run a code review.

## Verify and test

```bash
python3 scripts/doctor.py --auth
./scripts/install-codex.sh --check
```

Doctor exits nonzero when a dual-review CLI/runtime is missing, outdated or unauthenticated;
it reports no credentials. It lists optional tool availability separately. It does not
certify the selected project's hook, repository permissions or optional mobile/browser
setup. The runtime verifies the hook when starting; use each capability's setup skill.

For repository development, install PyYAML in the Python environment running validation
and install shellcheck (mandatory in CI, optional locally). Then run:

```bash
python3 -m pip install pyyaml
./scripts/validate.sh
./scripts/validate-codex.sh
```

Use a virtual environment if the system Python refuses package installation. Validation
covers manifests, frontmatter, shell snippets, runtime/receipt behavior, installation,
bundle parity and real isolated Codex skill discovery. It does not prove model reasoning
or every optional external integration. See [TESTING.md](TESTING.md) for the coverage map.

## Update and recover

Update this persistent checkout with a clean working tree, then update the Claude
marketplace/plugins using `claude plugin marketplace update bymax-claude-code` and the
CLI's plugin update commands. Re-run `python3 scripts/install-review-flow.py` for the
shared runtime and `./scripts/install-codex.sh` for Codex; restart/new task, then doctor.
For local package edits use the documented cachebuster workflow in [CODEX.md](CODEX.md).
Never silently overwrite uncommitted checkout changes during an update.

If a reviewer fails, inspect its attempt log and correct the environment before the one
allowed retry. Preserve campaign and delivery state; do not reset counters, skip a
reviewer or disable hooks to obtain a push. For rollback, restore the specific backed-up
files after stopping active reviewers, preserving unrelated settings changed since that
backup. Do not publish while runtime/checker policy versions disagree.
