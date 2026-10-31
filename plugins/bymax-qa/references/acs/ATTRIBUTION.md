# Attribution — Anthropic-Cybersecurity-Skills (selected playbooks)

Every folder here is a skill copied byte for byte from the **Anthropic-Cybersecurity-Skills**
catalogue, and `LICENSE` is that repository's licence:

- **Repository**: <https://github.com/mukul975/Anthropic-Cybersecurity-Skills>
- **Maintainer**: mukul975, with the contributors named in each skill's frontmatter
- **License**: Apache License 2.0 (see [`LICENSE`](./LICENSE), preserved unchanged; each skill
  also carries its own copy). The upstream repository ships no `NOTICE` file.
- **Commit vendored**: recorded in [`upstream.json`](./upstream.json), with the SHA-256 of every
  copied file

No copied file was modified. `ATTRIBUTION.md` and `upstream.json` are the only files written by
this repository.

## Why only these playbooks

Most of the catalogue is written for security operations, forensics and red teams.
These are the defensive procedures that apply to a software project's own repository and
pipeline: CI/CD hardening, secret scanning and SAST, IaC and image scanning, SBOMs and signing,
container hardening, API controls, LLM and agent security, data subject requests and CVE
prioritization. Procedures that read as templates with no concrete steps were left out.

They are not registered as skills of their own. `/bymax-qa:security-playbooks` lists them in one
index and loads a playbook only when a task calls for it, so the catalogue adds a single entry to
the skill listing.

## How to update from upstream

Run from the repository root. It refreshes every playbook already here from a fresh clone, keeps
`ATTRIBUTION.md`, rewrites `upstream.json` and regenerates the Codex bundle.

```bash
set -euo pipefail
acs=plugins/bymax-qa/references/acs
work=$(mktemp -d)
git clone -q --depth 1 https://github.com/mukul975/Anthropic-Cybersecurity-Skills "$work/upstream"
commit=$(git -C "$work/upstream" rev-parse HEAD)
for dir in "$acs"/*/; do
  name=$(basename "$dir")
  rm -rf "${acs:?}/$name"
  cp -Rp "$work/upstream/skills/$name" "$acs/$name"
done
cp -p "$work/upstream/LICENSE" "$acs/LICENSE"
python3 scripts/tests/test_security_audit_vendor.py --write-acs-manifest "$commit"
python3 codex/scripts/bundle.py
python3 scripts/tests/test_security_audit_vendor.py
```

Then read the upstream diff before committing, scripts first: a changed script or step is a
change to what `/bymax-qa:security-playbooks` does, and it ships with a version bump.
