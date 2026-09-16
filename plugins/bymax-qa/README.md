# 🔎 Bymax QA

> Whole-system QA and security audit for **any** project, run as the Security QA
> engineer of a peer agent team. Point it at a **Jira ticket** (it verifies
> access, reads the acceptance criteria, and reports each PASS/FAIL with
> evidence), a **branch or PR** (it scopes the hunt to the change, like a code
> review), or the **whole system**. It maps the stack, hunts by domain with
> read-only finder agents, verifies every candidate against six gates before it
> becomes a finding, and hands each one to the agent that owns the code — a
> GitHub issue, or a comment back on the ticket — then re-tests until it holds.

## Install

```bash
claude plugin marketplace add bymaxone/bymax-agent-kit
claude plugin install bymax-qa@bymax-agent-kit
```

### Also in Codex

The same procedures ship in the Codex package as `bymax-audit` (namespaced `bymax-codex:<name>`). Install it with `./scripts/install-codex.sh` from a checkout — see [CODEX.md](../../CODEX.md) for the entrypoints and the capability boundaries, which are not full parity.

## Why it is a separate plugin

`bymax-quality` reviews a diff for correctness and blocks a commit. `bymax-qa`
audits a running system for exploitable weakness and drives the fix to done.
They do not overlap:

| | `bymax-quality` code-review | `bymax-qa` audit |
| --- | --- | --- |
| Scope | a diff or a file, read statically | the whole system, static **and** live |
| Output | findings in chat, a commit verdict | a persistent registry, evidence per finding, a report + exec summary |
| After a finding | you fix it (`--fix`) | handed to the owning peer or filed as an issue, then re-tested |
| Edits code | yes | never — a hook enforces it |

`bymax-qa` reuses the `security-reviewer` agent as one input and the built-in
`/security-review` as another; it does not replace either.

## Use it

```bash
/bymax-qa:audit init             # interview + write .claude/qa/scope.md, then STOP for approval
# — fill approved-by in the scope, list the allowed hosts —

/bymax-qa:audit BYM-123          # QA a Jira ticket: acceptance criteria + security on the change
/bymax-qa:audit feat/login       # QA a branch: scope the hunt to the change, like a code review
/bymax-qa:audit main..HEAD       # QA a range; or #182 for a PR
/bymax-qa:audit --live           # QA the whole system against the scope's base-url
/bymax-qa:audit BYM-123 "only the acceptance criteria, skip the security sweep"

/bymax-qa:audit status           # read the registry, no messages sent
/bymax-qa:audit retest QA-012    # re-verify one finding against the claimed fix
```

The first word is the **target** — a ticket key, a branch, a range, a PR, or
nothing for the whole system — and the rest of the line is a free-text
instruction that steers focus and depth. Flags: `--domains auth,authz,input`
restricts the hunt · `--depth quick|full|deep` (deep adds an adversarial finder
pass and the built-in review as a candidate source) · `--live` runs the live
probes against the scope's `base-url` · `--no-handoff` records only ·
`--no-issues` messages peers but never files issues.

### Targets

| Point it at | It does | Also needs |
| --- | --- | --- |
| a **Jira ticket** (`BYM-123`) | reads the acceptance criteria, verifies each PASS/FAIL/BLOCKED/NOT-VERIFIABLE with evidence, **and** hunts security on the change; can comment the result back on the ticket | Jira access — an Atlassian MCP, the `jira`/`acli` CLI, or pasted criteria; it checks and tells you which |
| a **branch / range / PR** (`feat/x`, `main..HEAD`, `#182`) | scopes the hunt to the changed surface, the way a code review scopes a diff — complements `/bymax-quality:code-review`, does not replace it | `git` (and `gh` for a PR) |
| the **whole system** (no target) | the full audit by domain | — |

Every target is authorized by an approved `.claude/qa/scope.md` (run
`/bymax-qa:audit init` once to write it); a ticket or branch needs only a
minimal scope naming the repo, and `--live` additionally needs `allowed-hosts`.

## The pipeline

```
resolve target           ticket (Jira access + acceptance criteria) · branch/PR (the diff) · whole system
   ↓
recon + threat model      detect the stack, inventory routes, draw trust boundaries, STRIDE
   ↓
deterministic scans       advisories, secret patterns, suppression greps (exact)
   ↓
hunt (≤4 parallel)        one read-only qa-hunter per domain → candidates
   ↓
live probes (--live)      in-session, allow-listed hosts only, evidence captured
   ↓
verify                    qa-verifier attacks each candidate; six gates + exclusion list
   ↓
acceptance (ticket only)  each criterion → PASS / FAIL / BLOCKED / NOT-VERIFIABLE, with evidence
   ↓
record                    findings/QA-NNN.md, registry, report, exec summary
   ↓
hand off                  peer session · GitHub issue · ticket comment · human — then re-test to close
```

## Scope is enforced, not trusted

A `PreToolUse` hook (`qa-guard.sh`) reads `.claude/qa/scope.md` while a run is
active (`.claude/qa/.active` present) and:

- blocks any network tool in command position (`curl`, `nmap`, `sqlmap`,
  `nuclei`, `zap`, `openssl -connect`, `ssh`, the `qa-probe` wrapper, …)
  reaching a host not in `allowed-hosts` — or one whose host it cannot read;
- confines every `Write`/`Edit`/`MultiEdit` tool call to this project's
  `.claude/qa/`.

It is a **floor**, not a full sandbox: it does not police a file write made by
an arbitrary `Bash` command (`sed -i`, a `>` redirect) or an unlisted
network-capable binary. Those rest on the skill's "never edit the target" rule
and its read-only finder agents — the hook catches the common slip, the same
way `bymax-quality`'s secret-scanner is a floor under review discipline.
Outside a run the hook is inert.

## What you get

### Skill

- **`audit`** — `/bymax-qa:audit [init|run|retest QA-NNN|status]`. The
  orchestrator; the domain playbooks live in `skills/audit/references/` and load
  on demand.

The 18 references under `skills/audit/references/` load on demand. Two govern
scoping — `targets.md` (ticket / branch / range / PR / whole-system resolution
and the Jira access ladder) and `acceptance.md` (a ticket's criteria →
PASS/FAIL/BLOCKED/NOT-VERIFIABLE). The domain playbooks cover **security**
(authentication, authorization/tenant isolation, injection/input, cache/Redis,
database/Postgres, transport/config), **observability** (log-leak, log forging,
event coverage, store access), **architecture** (boundaries, coupling, failure
modes), **frontend** (XSS, token storage, CSP, accessibility, Core Web Vitals),
and **supply chain** (advisories, secrets in history, pipeline integrity). Each
one carries a "what to expect by stack" table and a "common non-findings" list,
so a delegated or intentional control is not reported as a gap.

### Scripts

| Script | Purpose |
| --- | --- |
| `qa-tools.sh` | reports which external scanners are installed (none bundled) |
| `qa-probe.sh` | an HTTP probe that captures request+response as evidence, credentials redacted |
| `qa-log-audit.sh` | searches a log for a secret through base64/url/hex/json decodings and states the encodings it covered — a literal grep certifies the leaking case |

### Sub-agents

| Agent | Model | Role |
| --- | --- | --- |
| `qa-recon` | sonnet | read-only stack + route + boundary map |
| `qa-hunter` | sonnet | read-only per-domain finder → candidates (never findings) |
| `qa-verifier` | opus | adversarial verifier → CONFIRMED / REJECTED / NEEDS-WORK |

### Hook

| Hook | Trigger | What it does |
| --- | --- | --- |
| `qa-guard.sh` | `PreToolUse` Bash/Write/Edit/MultiEdit | while an audit is active, enforces the host allow-list and confines writes to `.claude/qa/` |

## Standards it is built on

ASVS 5.0 requirement ids as the finding taxonomy · OWASP API Security Top 10
2023 for the API layer · CWE Top 25 for classification · the six-gate,
verify-before-report shape of Anthropic's Claude security tooling and Trail of
Bits' `fp-check`. External tools (`semgrep`, `gitleaks`, `osv-scanner`,
`trivy`, `zap`, `nuclei`, `sqlmap`, `axe`, Lighthouse, `madge`) are detected at
runtime and never bundled — an absent one degrades to a status line, never an
error.

## Requirements

- `git` always; `gh` authenticated when issues are filed, a PR is the target, or
  a claimed fix is re-tested from a PR.
- Cross-session messaging for peer hand-off (workers start with `claude --name
  <name>`); without a live peer, findings route to issues or the human.
- For a **ticket** target: Jira access — an Atlassian MCP, the `jira`/`acli`
  CLI, or pasted criteria. The skill checks and reports which it used; nothing
  breaks when none is present, it asks for the criteria instead.
- Optional: `docker`/`docker compose` to bring a stack up for `--live`;
  `bymax-web-verify` for the frontend and browser-driven acceptance checks; the
  external scanners above when a deterministic layer is wanted.

## License

MIT — see [root LICENSE](../../LICENSE).
