# llms-install.md — AI-agent installation runbook

> **Audience:** AI coding agents (Claude Code, Cline, Cursor, Codex, …) installing the **Bymax Agent Kit** toolkit for a user.
> **Scope:** the PUBLIC toolkit only. This is **not** the author's machine-restore flow — **never run `scripts/install.sh`, never copy `personal/` or `vendor/`** unless the human explicitly states they are the repo author restoring their own machine.
>
> **This runbook installs the CLAUDE CODE package.** To install the **Codex** package instead (or
> as well), follow [`CODEX.md`](./CODEX.md): clone the repo to a persistent path and run
> `./scripts/install-codex.sh`, then `--check`. The two are independent — neither installer touches
> the other's configuration. `scripts/install.sh` is neither of them.
>
> Name mapping (the most common command-construction error):
> - GitHub slug: `bymaxone/bymax-agent-kit`
> - Marketplace name (used after `@` in install commands): `bymax-agent-kit`
> - **Renamed from `bymax-claude-code`.** The GitHub URL redirects; the marketplace id does not. If
>   `claude plugin marketplace list` shows `bymax-claude-code`, run
>   `claude plugin marketplace remove bymax-claude-code` before Step 1, then reinstall each plugin
>   under the new id. Never mix the two suffixes in one install.
> - Codex plugin: `bymax-codex@bymax-codex`, from the local `codex/` directory — not from a Git URL.

Every step is idempotent — re-running is safe. After each step, run the **Verify** command; do not proceed on failure (see [Failure guidance](#failure-guidance)).

---

## Step 0 — Prerequisites

```bash
claude --version   # Claude Code CLI must exist
node --version     # ≥ 18 required for plugin hooks (≥ 20 recommended)
git --version      # any recent version
python3 --version  # ≥ 3.10 — only needed if Step 4.5 will run
```

Missing item → STOP and report to the human:

| Missing | Human action |
|---|---|
| `claude` | `npm install -g @anthropic-ai/claude-code` (or the native installer from docs.claude.com) |
| `node` | `brew install node` (macOS) / nvm — must be on the non-interactive shell PATH |
| `git` | `xcode-select --install` (macOS) or the platform package manager |
| `python3` ≥ 3.10 | Only blocks Step 4.5 (the review runtime), never Steps 1–4 — [python.org](https://www.python.org/downloads/) or the platform package manager |

## Step 1 — Add the marketplace

```bash
claude plugin marketplace add bymaxone/bymax-agent-kit
```

**Verify:** `claude plugin marketplace list` shows `bymax-agent-kit`.

## Step 2 — Choose and install plugins (decision point)

Default when the human didn't specify: install the **core pair** plus whatever the project type needs.

| Plugin | Install when | Command |
|---|---|---|
| `bymax-workflow` | always (core) | `claude plugin install bymax-workflow@bymax-agent-kit` |
| `bymax-quality` | always (core — ships the hooks + sub-agents) | `claude plugin install bymax-quality@bymax-agent-kit` |
| `bymax-bootstrap` | the human will scaffold new projects | `claude plugin install bymax-bootstrap@bymax-agent-kit` |
| `bymax-mobile` | Expo / React Native projects only | `claude plugin install bymax-mobile@bymax-agent-kit` |
| `bymax-web-verify` | web projects only (needs Step 4's `agent-browser`) | `claude plugin install bymax-web-verify@bymax-agent-kit` |
| `bymax-pr` | only if `gh` will be authenticated (Step 4) | `claude plugin install bymax-pr@bymax-agent-kit` |
| `bymax-pm` | the human coordinates multiple Claude Code sessions | `claude plugin install bymax-pm@bymax-agent-kit` |
| `bymax-qa` | the human wants a whole-system QA / security audit | `claude plugin install bymax-qa@bymax-agent-kit` |

⚠️ **Do NOT install `bymax-all`** — it is a documentation index; it installs no commands.

**Verify:** `claude plugin list` shows each installed plugin.

Scope note: plugins install user-wide by default. Only pin to a single project (via `enabledPlugins` in that project's `.claude/settings.json`) if the human asks for it.

## Step 3 — Restart Claude Code (HUMAN HANDOFF)

Commands and hooks are only picked up on a fresh session. **An agent running inside Claude Code cannot restart its own session** — tell the human:

> "Please restart Claude Code (close and reopen the session), then tell me to continue."

**Verify (after restart):** `claude plugin list` still shows the plugins, and typing `/` inside Claude Code lists `bymax-workflow:*` commands. Use the **namespaced** names (`/bymax-workflow:standards`), not bare `/standards`.

## Step 4 — External CLIs (conditional — only for plugins installed in Step 2)

Each row: check → install → verify. Skip rows whose plugin wasn't installed.

**The two Codex rows are the exception to that rule.** `bymax-quality` is always installed, which
would make them eligible on every default install — but they install external software and spend a
billed Codex turn, so being eligible is not the same as being wanted. **Default to skipping both.**
Run them only if the human has asked for the Codex second opinion; if they have not said, ask, and
skip on no answer.

Every `bymax-quality` command **runs** without them: skipping costs the second opinion, not the
plugin. What it does cost is **certification** — `/bymax-quality:code-review` completing with a
receipt needs a real Codex pass, so a campaign that cannot reach Codex reports *incomplete review*.
Say that to the human when they decline, and never record an incomplete campaign as approval.

| Tool | Check | Install | Verify |
|---|---|---|---|
| `gh` (for `bymax-pr` and `bymax-qa`) | `command -v gh` | `brew install gh` | `gh auth status` |
| Security scanners — **all optional** (for `bymax-qa`) | `bash ${CLAUDE_PLUGIN_ROOT}/scripts/qa-tools.sh` inside an audit | install per tool as needed, e.g. `brew install semgrep gitleaks osv-scanner trivy` | `/bymax-qa:audit` records any absent tool as a coverage gap — none is required |
| `gh` auth | `gh auth status` | **HUMAN HANDOFF:** `gh auth login` is an interactive OAuth flow — the human must run it | `gh auth status` exits 0 |
| pnpm (pnpm repos) | `command -v pnpm` | `corepack enable pnpm` | `pnpm --version` |
| Xcode (`/sim-ios`) | `xcrun simctl help` | **HUMAN HANDOFF:** Xcode via App Store + `xcode-select --install` | `xcrun simctl list devices` |
| Android SDK (`/sim-android`) | `command -v adb` | **HUMAN HANDOFF:** Android Studio GUI installer + PATH setup | `adb --version` |
| Rust extras (Rust repos) | `command -v cargo` | `cargo install cargo-llvm-cov cargo-mutants cargo-deny cargo-audit cargo-vet` | `cargo llvm-cov --version` |
| `agent-browser` (for `bymax-web-verify`) | `command -v agent-browser` | run `/bymax-web-verify:setup` **inside Claude Code, after Step 3's restart** (downloads Chrome for Testing — tell the human first) | the setup command ends with its own smoke test |
| `codex` CLI — **opt-in, ask first** (for `bymax-quality`'s independent second review) | `command -v codex` | run `/bymax-quality:codex-setup` **inside Claude Code, after Step 3's restart** — it installs the CLI, then hands off: `codex login` is interactive, so **only the human can finish it** | **HUMAN HANDOFF for the whole command**, not just the login: `/bymax-quality:codex-setup` ends with a real review run rather than an exit code — one billed Codex turn. If `codex@openai-codex` is installed and enabled it offers a second, adversarial run and **asks first**, because that is the run this toolkit gates behind explicit consent; a decline is a valid answer and leaves the row below unverified. The human runs it; this row passes when it reports a real review |
| `codex@openai-codex` plugin — **opt-in, ask first** (only for `/bymax-quality:code-review --adversarial`) | `claude plugin list` shows `codex@openai-codex` with `Status: ✔ enabled` — a disabled plugin still prints its id, and the runtime skips it | `claude plugin marketplace add openai/codex-plugin-cc`, then `claude plugin install codex@openai-codex` | **HUMAN HANDOFF.** Install this plugin **before** running the row above's `/bymax-quality:codex-setup`, so one invocation covers both rows; done after, it needs a second run. Verifying means that command, from a **feature branch with commits on it**, and saying **yes** to its adversarial prompt — that run is billed (~40–60 s) and gated behind explicit consent, so an agent must not start it. Declining is fine and leaves this row unverified. Read the **adversarial** run's status against the table below; a green standard run says nothing about the plugin |

Both Codex rows are **optional** — `/bymax-quality:code-review` runs without either and prints a
one-line status where the second opinion would go. Type the last row's two commands exactly: the
plugin is `codex`, its marketplace is `openai-codex`, and the repo behind it is
`openai/codex-plugin-cc` — three different names for one install. `claude plugin install` takes no
version, so the plugin arrives at whatever the marketplace publishes; if that version is not one
`bymax-quality` has verified its runtime contract against, the adversarial review answers
`adversarial-absent` and `/bymax-quality:codex-setup` documents the ways out.

Installing this plugin in Step 4 lands it **after** Step 3's restart, and it ships three hooks
(`SessionStart`, `SessionEnd`, `Stop`) plus eight `/codex:*` commands that stay inert until the
next fresh session. Review C is the exception and works immediately, because the script spawns
the runtime by path rather than through the command surface — so a passing verification here is
not evidence the rest of the plugin is live. Tell the human a second restart is needed if they
want those commands.

**Reading the plugin row's verification.** Three verdicts, not two — several statuses are
emitted before the script ever looks at the plugin, and those leave this row **unverified**
rather than passed:

| Status of the adversarial run | What it means for this row |
|---|---|
| `ok` / `ok-unpinned` | **pass** — the plugin was found, enabled and usable |
| `adversarial-absent`, second line naming an **unverified version** | **pass** for install purposes: the plugin is there, and the install cannot pin a version, so a newly published one lands here with nothing wrong |
| `absent` / `unauthenticated` | **unverified** — both fire before the plugin gate. Finish the CLI row above and re-run. An `absent` that survives it is that row failing, and belongs in the report as such |
| `unsupported-target` | **unverified** — the scope was rejected before the plugin gate. Read the second line: under this row's procedure, on a feature branch with commits, an empty range usually means the `--ref` named the wrong base, not that anything is installed correctly |
| `adversarial-absent` for any other reason | **failure** — take the second line to `/bymax-quality:codex-setup`'s remedy table, which has a row for each |
| `timeout` | **pass** for this row, and a problem for another: the run had already started, which means the runtime resolved. Take it to `codex-setup`'s Troubleshooting table, not its remedy table |
| `failed` / `bad-invocation` | **unverified** — read the second line. An argument error never reaches the plugin at all; `cannot create a temp file` and an interrupt caught by the EXIT trap both fire before the lookup. Its near-twin `cannot create a temp dir` comes after, and does prove the plugin resolved — read the words, not the shape. Only a `failed` naming the review itself — a non-zero exit, unreadable or unparseable output — proves the plugin resolved. Troubleshooting table either way |

**Unset `BYMAX_CODEX_COMPANION` before running this check, whatever the verdict says.** With it
exported the script uses that path and returns before it ever reads the plugin list, so no row above
is evidence about `codex@openai-codex` — a `pass` there can coexist with the plugin absent or
disabled.

Never record this row as passed on an *unverified* verdict: nothing about `codex@openai-codex`
was checked, and the first `--adversarial` run is where the user would find out.

## Step 4.5 — The bounded dual review runtime (only if the human wants certified pushes)

`/bymax-quality:code-review` runs without this. The **pre-push receipt**, the shared campaign state
and the global push handoff do not: they live in a runtime installed from a checkout, not from the
marketplace. Install it only when the human has said they want dual-review certification, and only
after Step 4's `codex` row is done — a receipt needs both reviewers.

```bash
git clone https://github.com/bymaxone/bymax-agent-kit.git   # persistent path; keep it
cd bymax-agent-kit
python3 scripts/install-review-flow.py
```

It writes `~/.claude/bymax-review/`, registers one `PreToolUse` Bash guard, and merges a managed
block into `~/.claude/CLAUDE.md`. **It backs up every file it touches** under `~/.claude/backups/`
and prints that directory — report the path to the human. It preserves unrelated settings and
unrelated hooks; it refuses (nonzero, no writes) when a legacy hook is chained to another command,
which needs a hand migration.

**Verify:** `python3 scripts/doctor.py --auth` exits 0. It reports no credentials. A nonzero exit
names the missing, outdated or unauthenticated CLI/runtime — fix that, do not proceed.

Do **not** pass `--local-plugin-overlay` for a user install: it copies this checkout over the
installed plugin caches and is a repo-development flag. Prerequisites: macOS or Linux (the
runtime's file locks use `fcntl`; on Windows the human needs WSL) and Python ≥ 3.10.

## Step 5 — MCP servers (optional — ask the human, default: context7 only)

Use the `claude mcp add` one-liners (do **not** use the `personal/mcp.template.json` copy method — that is the author-restore path):

```bash
claude mcp add context7 -- npx -y @upstash/context7-mcp
claude mcp add sequential-thinking -- npx -y @modelcontextprotocol/server-sequential-thinking
```

Obsidian knowledge vault — **only if the human has a vault**; the path is theirs to provide (ask, never guess):

```bash
claude mcp add obsidian -- npx -y @bitbonsai/mcpvault@latest /path/the/human/provides
```

**Verify:** `claude mcp list` shows each added server. Restart handoff applies again (Step 3).

## Step 6 — graphify (optional — ask the human; default: skip unless they want token-optimized reuse scans)

Prerequisite: Python ≥ 3.10 plus `uv` (or `pipx`). The PyPI package is **`graphifyy`** (double-y) — other `graphify*` names on PyPI are NOT affiliated.

```bash
uv tool install graphifyy      # or: pipx install graphifyy
graphify install               # registers the /graphify skill with Claude Code
# then, inside Claude Code, in each project to map:   /graphify .
graphify hook install          # post-commit graph refresh
```

**Verify:** `command -v graphify`, and after `/graphify .` the file `graphify-out/graph.json` exists in the project.

## Final verification checklist

```bash
claude plugin marketplace list   # bymax-agent-kit present, and bymax-claude-code absent
claude plugin list               # every chosen plugin present
claude mcp list                  # every chosen MCP present (if Step 5 ran)
gh auth status                   # exit 0 (only if bymax-pr or bymax-qa installed)
python3 scripts/doctor.py --auth # exit 0 (only if Step 4.5 ran)
```

Report a pass/fail summary per step to the human. Done.

---

## DO-NOT list

- ❌ **Never run `scripts/install.sh`** — it symlinks the author's personal config and vendor skills into `~/.claude/` (author-restore only).
- ❌ **Never copy or edit `personal/` or `vendor/`** — author backup and third-party content respectively.
- ❌ **Never install `bymax-all`** expecting functionality — it is a docs-only index.
- ❌ **Never run `graphify claude install`** (the "always use the graph" mode) — its always-on `PreToolUse` hooks add per-prompt overhead and conflict with the `bymax-quality` hooks. The toolkit's integration is presence-gated and needs no hooks.
- ❌ **Never add a GitHub MCP server** — GitHub access in this toolkit is `gh` CLI only (short-lived OAuth; org policies often reject long-lived PATs).
- ❌ **Never guess the Obsidian vault path** — ask the human.
- ❌ **Never run `scripts/install-review-flow.py --local-plugin-overlay`** for a user install — it overwrites the installed plugin caches with this checkout. Repo development only.
- ❌ **Never edit `codex/plugins/bymax-codex/references/upstream/`** — generated copies of `plugins/`, regenerated by the bundler and compared in CI.
- ❌ **Never report a review as passed when a reviewer was unavailable** — a missing Codex CLI or a failed pass means *incomplete review*, never approval, and never a product defect.

## Failure guidance

| Symptom | Likely cause → action |
|---|---|
| `marketplace add` fails | Network/auth → retry once; still failing → report to human with the exact error |
| `plugin install` fails | Marketplace-name typo — it is `@bymax-agent-kit` (hyphens), never `@bymax.agent-kit`; and never the old `@bymax-claude-code`, which no longer matches the registered marketplace |
| `install-review-flow.py` exits nonzero naming another hook | A legacy guard chained to somebody else's command. It refuses rather than deleting it — **hand the exact stderr to the human**; do not edit `settings.json` yourself |
| `doctor.py --auth` nonzero | It names the CLI/runtime that is missing, outdated or unauthenticated. `codex login` and `claude auth login` are interactive → HUMAN HANDOFF |
| `install-codex.sh` stops on the marketplace name | A `bymax-codex` marketplace already points at another checkout. It refuses to replace it — ask the human which checkout is current |
| Commands missing after install | Step 3 restart not done → hand off to the human again |
| MCP server missing from `claude mcp list` | Re-run the `claude mcp add` line; if listed but inactive, check `enabledMcpjsonServers` in `~/.claude/settings.local.json` |
| Hooks not firing (`secret-scanner` etc.) | Plugin disabled or restart pending → `claude plugin list`, then restart handoff |
| `adversarial-absent` from `/bymax-quality:code-review --adversarial` | The status has several causes and **the line under it names which one** — a missing plugin, but equally a missing `node`, an unreadable plugin list (no `claude` on PATH, neither `jq` nor `python3`), an install missing its runtime file, or an unverified version. Read that line, then take its row in `/bymax-quality:codex-setup`'s remedy table — it has one per line, including the plugin that is present but merely **disabled**, which Step 4's install commands would not change (`claude plugin enable codex@openai-codex` does). Only a genuinely absent plugin is fixed by Step 4's last row |
| `graphify: command not found` after install | Tool bin dir not on PATH → `uv tool update-shell` (or `pipx ensurepath`), new terminal |
