# Attribution — security-audit

Every file in this folder except `ATTRIBUTION.md` and `upstream.json` is a byte-for-byte copy
of the **security-audit** skill published by Cloudflare:

- **Repository**: <https://github.com/cloudflare/security-audit-skill>
- **Path upstream**: `skills/security-audit/`, plus the repository's `LICENSE`
- **Author**: Cloudflare, Inc.
- **License**: MIT (see [`LICENSE`](./LICENSE), the upstream license preserved unchanged)
- **Commit vendored**: recorded in [`upstream.json`](./upstream.json), with the SHA-256 of
  every copied file

## Why it ships here unchanged

It is installed as `/bymax-qa:security-audit` in Claude Code and as `bymax-security-audit` in
Codex so that it runs in any project the toolkit is installed in. The skill is already written
to be agent-neutral (its own "Platform terminology" section maps the parent, the delegation
tool and the two delegated roles to whatever the platform provides), so no file is edited: the
behaviour is the upstream behaviour. The Codex entrypoint only adds a short adapter in front of
this copy and changes none of its rules.

`scripts/tests/test_security_audit_vendor.py` fails if a file here differs from the hash in
`upstream.json`, if a file is added or removed, or if the upstream validator suites stop
passing.

## Requirements the skill itself states

- A model with tool use and parallel sub-agents.
- Node.js, for `validate-findings.cjs` and `validate-coverage-ledger.cjs`.
- An OS-enforced sandbox before any target-controlled code is executed. Without one, the skill
  keeps the lead as `needs_validation` instead of running target code.

## How to update from upstream

Run from the repository root. The replacement keeps `ATTRIBUTION.md`, rewrites
`upstream.json` from what was copied, and regenerates the Codex bundle.

```bash
set -euo pipefail
skill=plugins/bymax-qa/skills/security-audit
work=$(mktemp -d)
git clone -q --depth 1 https://github.com/cloudflare/security-audit-skill "$work/upstream"
commit=$(git -C "$work/upstream" rev-parse HEAD)
cp "$skill/ATTRIBUTION.md" "$work/ATTRIBUTION.md"
rm -rf "$skill"
mkdir -p "$skill"
cp -p "$work/upstream/skills/security-audit/"* "$skill/"
cp -p "$work/upstream/LICENSE" "$skill/LICENSE"
cp "$work/ATTRIBUTION.md" "$skill/ATTRIBUTION.md"
python3 scripts/tests/test_security_audit_vendor.py --write-manifest "$commit"
python3 codex/scripts/bundle.py
python3 scripts/tests/test_security_audit_vendor.py
```

Then read the upstream diff before committing: a new file or a changed requirement is a change
to what `/bymax-qa:security-audit` does, and it ships with a version bump like any other.
