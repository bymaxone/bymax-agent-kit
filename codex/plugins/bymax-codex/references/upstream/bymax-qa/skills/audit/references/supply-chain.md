# Supply chain & pipeline (OWASP Top 10:2025 A03 / A08)

Maps to OWASP Top 10:2025 A03 (Software Supply Chain Failures) and A08
(Software and Data Integrity Failures), and ASVS 5.0 V13. The dependency tree
and the CI pipeline are attack surface: a vulnerable transitive dependency, an
unpinned third-party Action, a secret in git history, a gate that can be passed
without being satisfied.

## Deterministic (the tools do most of this)

Run what `qa-tools.sh` reports as available; each absent tool is a coverage
gap, not an error.

- **Dependency advisories** — `osv-scanner --recursive` (or `npm audit`,
  `cargo audit`, `trivy fs`) over the **lockfile**, direct and transitive.
  Record each advisory with its id and the path. A finding here is an advisory
  reachable in this app, not merely present in the tree — but the advisory
  itself is the evidence (this is the exception in `verification.md`: a
  supply-chain observation stands on the advisory, and only a bespoke
  reproduction raises it to a full exploited finding).
- **Declared-range drift** — a `peerDependencies`/`dependencies` range that a
  new advisory now admits, which a lockfile scan misses until the next resolve.
- **Secrets in history** — `gitleaks detect` (working tree) and `trufflehog git`
  (history, verified). A live, un-rotated credential in history is a finding
  regardless of whether the current tree is clean.
- **Image/IaC** — `trivy image`/`trivy config` on a Dockerfile or compose:
  base image advisories, a container running as root, a `latest` tag, a mounted
  Docker socket.

## Pipeline integrity (read the workflows)

- **Action pinning** — third-party GitHub Actions pinned by full commit SHA,
  not a moving tag. A `uses: some/action@v3` for a third-party action is the
  supply-chain risk (a first-party reusable referenced by a version alias is a
  deliberate, different choice — do not flag it without reading the repo's own
  convention).
- **Least privilege** — `permissions:` scoped per workflow, not a blanket
  `write-all`. A `contents: write` where a read would do is a finding.
- **A gate that passes without being satisfied** — the most valuable finding in
  this domain. Every gate runs the configuration on the branch under review, so
  a change that weakens a threshold, widens an ignore glob, or disables a check
  turns the gate green while removing the protection. A diff that lowers a
  coverage or mutation threshold, adds a lint ignore, or removes a required
  check is a finding even though CI is green — the review is the only thing that
  sees it.
- **Coverage of security scanning** — is there dependency scanning, secret
  scanning, and SAST in CI at all? Their absence is a gap to report at a
  severity matched to the app's exposure, framed as a recommendation with the
  concrete workflow to add.

## Common non-findings (drop these)

- An advisory on a dev-only, non-shipped dependency with no runtime reach —
  note it, low severity, do not inflate.
- A first-party reusable workflow referenced by a moving major alias where the
  repo's own convention (its `AGENTS.md`/CONTRIBUTING) documents that choice and
  the alias is protected by a release ruleset — read the convention before
  proposing a SHA pin; that specific pin has been proposed and rejected on
  measured grounds in some estates.
- A secret pattern in a `.env.example`, a test fixture, or a doc — trusted by
  design (the exclusion list in `verification.md`).
- A `latest`-tagged image in a local dev compose the scope marks `local`.
