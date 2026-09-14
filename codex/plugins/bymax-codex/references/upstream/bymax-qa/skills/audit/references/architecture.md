# Architecture review

Not every defect is a vulnerability; some are structural weaknesses that make
vulnerabilities likely and fixes expensive. This axis grades the shape of the
system against its quality attributes. It produces findings like the security
domains, but their severity is about maintainability, scalability and blast
radius, not an immediate exploit — say so in the impact.

Ground it in a recognised frame rather than opinion: ATAM-style
quality-attribute scenarios (what must the system do under load, under change,
under partial failure?) checked against the C4 container view from `recon.md`.

## Deterministic

- **Dependency cycles** — `madge --circular --extensions ts,tsx src` or
  `depcruise --validate` if a ruleset exists. A cycle between modules is a
  coupling finding.
- **Layering violations** — imports that cross a boundary the architecture
  declares (a domain layer importing infrastructure, a feature importing
  another feature's internals). Grep the import graph against the stated layers.
- **File/function size at the seams** — a single file doing two jobs at a trust
  boundary is where isolation bugs hide (this is a hint, not the finding).

## Static hunt (the finder's brief)

- **Trust-boundary integrity** — does each boundary from the recon map have a
  single, identifiable enforcement point (a guard, a gateway, a policy), or is
  the check scattered so that adding a route can silently skip it? A boundary
  enforced in N places is N places to forget it.
- **Single responsibility at the boundary** — is authorization decided in one
  layer, or spread across controllers, services and the ORM so no one can say
  whether a path is covered? The BOLA findings in `security-authz.md` are
  usually a symptom of this.
- **Failure modes** — what happens under partial failure: does the auth cache
  fail open or closed? Does a downstream timeout drop a security check? Does a
  rolling deploy of two components at different revisions break a shared
  contract (a session keyspace one side moved and the other did not)? These are
  the highest-value architecture findings because a test suite never sees them.
- **Coupling that blocks the fix** — a cross-cutting concern reimplemented per
  feature instead of shared, so a security fix must land in N places and will
  land in N−1. Reinvented auth/crypto/validation is both a security and an
  architecture finding.
- **Scalability limits with a security face** — an unbounded in-memory store, a
  per-request resource with no cap, a synchronous call on a hot path that a
  slow client can hold open (slowloris) — availability findings that a probe
  can demonstrate.

## Live / dynamic (optional)

- If the scope allows, exercise a failure: kill the cache mid-request and see
  whether auth fails open; hold a connection with slow headers and see whether
  a timeout floor exists. Capture the behaviour as evidence.

## Output

Architecture findings use the same contract (`finding-contract.md`) with a CWE
where one fits (CWE-1047 cyclic dependency, CWE-710 improper adherence to
coding standards, CWE-693 protection mechanism failure) and an ASVS V15 (Secure
Coding & Architecture) reference. The remediation names the structural change,
and the impact is honest that it is a weakness, not an exploited hole — unless a
security domain already reproduced the exploit it enables, in which case
cross-reference that finding.

## Common non-findings (drop these)

- A "cycle" between a module and its own barrel/index file.
- A large generated file, a long migration, a long test suite — length is not a
  finding in generated or append-only content.
- A deviation from a pattern the project deliberately does not follow (read its
  own architecture doc before importing a convention from elsewhere).
