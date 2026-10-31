# Security audit in Codex

The bundled skill is Cloudflare's `security-audit`, copied unchanged. Its rules are the
procedure: guidance mode by default, full audit mode only on the requests it names, six
phases, write isolation, the two validators, and three verdicts. This page only says how its
platform-neutral terms resolve here. Nothing on it relaxes a source rule.

## Terms the source leaves to the platform

| Source term | Codex execution |
| --- | --- |
| Skill directory | The absolute `references/upstream/bymax-qa/skills/security-audit` directory of this package |
| Parent | The current Codex task, which alone writes the shared run files |
| Task tool | The host's subagent API, discovered before Phase 1 |
| `research` agent | A subagent limited to read-only source exploration and factual verification |
| `general` agent | A subagent allowed bounded local execution, writing only to its assigned `scratch/` |

The source requires that the agent checking a candidate is never the agent that found it, and
that Phase 5 uses fresh agents. When the host provides no subagent API, guidance mode still
runs, and the full workflow does not: report the missing delegation capability instead of
verifying a candidate in the context that produced it.

## Validators

Run `validate-coverage-ledger.cjs` and `validate-findings.cjs` from the skill directory with
the arguments the source gives, at the points it gives. They need Node.js. Check `node
--version` first; without Node, report each validation step as not run, never as passed.

## Execution sandbox

The source allows target-controlled code to run only inside an OS-enforced sandbox with every
control it lists: no external network, an allowlisted environment, a read-only target and
toolchain, scratch-only writes, and resource limits. Do not assume the Codex sandbox provides
all of them. Unless the host demonstrably enforces each one, follow the source: do not execute
target code, keep the lead as `needs_validation`, and give the safe validation plan.

## Output directory

The source default, `~/security-audit-skill/<repo-name>/run-<N>`, is outside the workspace. If
the host refuses that write, ask for approval or for another external path. Do not fall back to
`/tmp`, to the host home directory, or to a directory inside the target that version control
does not ignore; the source forbids each. This audit does not use `.bymax/codex/`.
