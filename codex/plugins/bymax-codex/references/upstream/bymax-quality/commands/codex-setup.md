---
description: 'Get the Codex CLI ready so /bymax-quality:code-review can run its independent second review. Diagnoses what is missing (binary, session, or nothing), installs Codex through the right channel for the platform (Homebrew cask on macOS, npm elsewhere), walks the user through the interactive login, and verifies the result with a real review run instead of trusting the exit code. Idempotent and safe to re-run; never needed for the rest of the plugin, which works without Codex. Triggers: "instalar codex", "configurar codex", "codex setup", "preparar segunda revisão", "install codex", "codex nao funciona", "/bymax-quality:codex-setup".'
---

# Codex setup

`/bymax-quality:code-review` requires one completed Codex review alongside Claude for
push certification. This command prepares the Codex CLI and login. Without them the
campaign stays INCOMPLETE. The OpenAI Codex plugin and its adversarial tools are optional
standalone features; they are not part of the bounded pair.

## Step 0 — Diagnose before changing anything

Three checks, all local and instant. Run them first and only fix what is actually broken.

```bash
command -v codex                 # is the binary on PATH?
codex login status               # exit 0 = active session, exit 1 = "Not logged in"
codex --version
```

| Result | State | Go to |
| --- | --- | --- |
| `command -v codex` finds nothing | not installed | Step 1 |
| found, `codex login status` exits 1 | installed, no session | Step 2 |
| found, `codex login status` exits 0 | ready | Step 3 (verify) |

`codex login status` reads the local credential store — no network call, no token spent.
An expired session is therefore free to detect, which is why the review script probes with
it before every run.

For a deeper picture (install method, PATH consistency, git, state DBs), run
`codex doctor`. Use it when something behaves oddly, not as a routine check.

## Step 1 — Install

Pick the channel that matches the machine. Ask the user which they prefer only when both
apply and neither is already in use by their other tools.

**macOS with Homebrew** — preferred there, it self-updates with `brew upgrade`:

```bash
brew install --cask codex
```

**Anywhere with Node.js** — the cross-platform route:

```bash
npm install -g @openai/codex
```

Then confirm the binary resolves, and re-run Step 0:

```bash
command -v codex && codex --version
```

> **Do not mix channels.** Installing through both leaves two binaries and an ambiguous
> PATH. `codex doctor` reports the active install method and every `codex` on PATH — read
> it before adding a second one. To upgrade an existing install, use `codex update`, or
> the channel's own command (`brew upgrade --cask codex`, `npm update -g @openai/codex`).

## Step 2 — Authenticate

```bash
codex login
```

**This step is the user's, not yours.** `codex login` opens a browser for the ChatGPT
sign-in flow and waits for a callback — it cannot be completed from a tool call. Ask the
user to run it themselves; in Claude Code they can type `! codex login` to run it in the
session so the output lands in the conversation.

Two ways to authenticate, and the difference is billing:

| Method | Command | Billing |
| --- | --- | --- |
| ChatGPT account *(usual)* | `codex login` | the user's ChatGPT plan quota |
| API key | `printenv OPENAI_API_KEY \| codex login --with-api-key` | the OpenAI account, per token |

The API-key path is the one to use on a headless machine, where no browser can open. Over
plain SSH without port forwarding, `codex login` cannot complete.

Confirm before moving on — the exact string matters less than the exit code:

```bash
codex login status    # "Logged in using ChatGPT" / "Logged in using an API key", exit 0
```

## Step 3 — Verify with a real run

An exit code is not proof the reviewer works. Run the plugin's own script against a real
commit and read what comes back:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/codex-review.sh" \
  --target commit --ref "$(git rev-parse --short HEAD)" --budget 300
```

Then decide whether the adversarial path can be exercised at all. The read that settles
it — **enabled**, not merely present, because the runtime selects on `.enabled == true` and
skips a disabled one:

```bash
claude plugin list --json | jq -e '
  map(select(.id == "codex@openai-codex" and .enabled == true)) | length > 0' >/dev/null \
  && echo "adversarial path available" || echo "skip it"
```

Without `jq`, read `claude plugin list` and look for `codex@openai-codex` with
`Status: ✔ enabled` beneath it. Anything else — absent, or present and disabled — means
skip this check and say why. Not to save money: the availability gates run before any
`codex` process starts and bill nothing, so a doomed run is free. It is to avoid asking a
human to authorise a run that cannot succeed. For the same reason the check is necessary,
not sufficient — the gate also wants `node`, a complete install, and a version on
`COMPANION_VERIFIED_VERSIONS`, so a green pre-check can still end at `adversarial-absent`.

When it is available, **ask the human before exercising the adversarial path**. Invoking this command is consent to set the CLI up, not to start the run
upstream gates behind explicit user invocation — so name the cost (a second billed turn,
~40–60 s) and run it only on a yes. Nothing else will exercise it, since Review C is opt-in
and this is the one place setup can prove it works. The
run above cannot produce its statuses, so a green standard run says nothing about it. Give
it a scope that exists: on a clean tree the script now refuses `--target uncommitted`, and
on a branch with nothing ahead of its base it refuses `--target base` — a review of nothing
bills a full turn and returns a verdict on nothing. Run this **from a feature branch with
commits on it**, and name the base yourself rather than deriving it: `refs/remotes/origin/HEAD`
is unset on any clone not made by `git clone`, and a wrong guess reports
`unsupported-target — ref does not resolve`, which reads as "this repository is unsupported"
rather than "that base was a guess".

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/codex-review.sh" \
  --mode adversarial --target base --ref "<your default branch, e.g. origin/main>" --budget 300
```

The first line is the contract:

| First line | Meaning |
| --- | --- |
| `CODEX_STATUS: ok` | working — the review follows; setup is done |
| `CODEX_STATUS: ok-unpinned` | working, but not over exactly the requested scope — the `CODEX_SCOPE:` line on the next line says why (either mode; the script header lists every cause). The report treats its findings as real and its silence as nothing |
| `CODEX_STATUS: absent` | the binary is still not on this shell's PATH → back to Step 1 |
| `CODEX_STATUS: unauthenticated` | login did not persist → back to Step 2 |
| `CODEX_STATUS: failed` | the CLI ran and exited non-zero, returned nothing readable, or (adversarial mode) returned a parse-failure page or a review without `Target:`/`Verdict:` — see troubleshooting |
| `CODEX_STATUS: timeout` | exceeded the budget; retry with a larger `--budget` |
| `CODEX_STATUS: unsupported-target` | the requested scope has no Codex equivalent, or nothing to review: a file path, a ref range not ending at HEAD, `--target commit` in adversarial mode, a clean tree for `--target uncommitted`, an empty `<ref>...HEAD` on a clean tree (the verification example below hits this on the default branch itself — run it from a feature branch), or a base with no shared history |
| `CODEX_STATUS: adversarial-absent` | adversarial mode only: the runtime could not be used — inspect the standalone wrapper's diagnostic line; this optional mode is not used by the campaign |
| `CODEX_STATUS: bad-invocation` | the command line was wrong (a flag without its value, an unknown flag or `--mode`) — not a Codex problem |

Expect roughly **40–60 seconds**, largely independent of diff size. A run that returns no
findings is a normal, healthy result — it is not evidence the setup failed.

## Configuration and the optional Codex plugin

Preserve the user's Codex configuration. The campaign helper overrides sandbox to
read-only and approvals to never for each invocation, uses an ephemeral context, and
supplies the same scope/acceptance prompt as Claude with a JSON output schema. It uses
`codex exec`, while the Step 3 standalone diagnostic uses `codex exec review` to check
CLI/login availability. That diagnostic result is not campaign clearance.

The OpenAI plugin `codex@openai-codex` is not required for this flow. Do not enable its
Stop review gate: it adds an independent review/correction loop. If the user explicitly
requests a separate adversarial audit, follow that plugin's own user-invoked entrypoint;
do not add it to every push or bypass its invocation restrictions.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `absent` right after a successful install | the shell's PATH predates the install | open a new shell, or check `codex doctor` → *PATH entries* |
| `unauthenticated` right after `codex login` | the browser flow never completed, or a different `CODEX_HOME` is in play | re-run `codex login`; check `codex doctor` → `CODEX_HOME` |
| `failed` on every run | rate limit, expired plan, or network egress blocked | run `codex exec review --uncommitted` directly and read its stderr |
| `failed` only in one repository | not a git repo, or the scope is empty | confirm with `git rev-parse --show-toplevel` and `git status` |
| `timeout` on a large change | budget too small | the bounded runner allows ten minutes per attempt and one infrastructure retry; inspect the log and split an oversized scope instead of automatically raising the budget |
| two `codex` binaries on PATH | installed via both brew and npm | remove one; `codex doctor` names the active install |

## When you are done

Tell the user plainly which state they ended in — ready, or still missing something and
why. Do not report success on the strength of an install command's exit code alone; report
it on the strength of Step 3 returning `CODEX_STATUS: ok`.
