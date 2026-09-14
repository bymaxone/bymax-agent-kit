# QA execution in Codex

The bundled audit supplies domain routing, the finding contract, signed scope,
independent verification and retest lifecycle. Use `.bymax/codex/qa/` as its
workspace. Validate the canonical physical path and reject symlinked workspace
roots before writing evidence, as the source authorization reference requires.

The Claude PreToolUse guard is not installed in Codex. Do not run the bundled
`qa-probe.sh` or `qa-guard.sh`: their workspace and interception assumptions are
Claude-specific. The read-only `qa-tools.sh` inventory and `qa-log-audit.sh` helper
can run by absolute path; their exit statuses have the source's documented meaning.

`init`, `status`, scoped static inspection, finding preparation and static retests
are available with filesystem/Git tools. An unavailable independent verifier means
UNVERIFIED, not a confirmed finding. Do not weaken the source's reproduction gates.

Before live testing, require the source's explicit `--live`, approved non-production
scope and allow-listed hosts, plus host controls/tools that can preserve that
scope and capture request/response evidence. Check each probe's complete destination,
redirect and proxy behavior before running it; follow the source authorization
reference. Do not claim interception or general write confinement. If the requested
live workflow depends on the Claude guard or helper, report that operation as
BLOCKED in Codex and complete the independent static work. Do not silently replace
it with an unrestricted scanner. This package does not provide live-hook parity.

Use available Codex subagents for finder/verifier separation. For peer handoffs,
use only fresh Codex recipient IDs and authorized messaging. Without messaging or
permission to publish, provide local handoff artifacts rather than opening issues
or posting ticket comments. Preserve the source policy against publicly disclosing
HIGH/CRITICAL vulnerabilities.
