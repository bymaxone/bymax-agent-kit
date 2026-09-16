# Attribution — Everything Claude Code (ECC)

The seven `.md` files in this folder are skills extracted from the **Everything Claude Code (ECC)** open-source agent harness:

- **Project**: Everything Claude Code (ECC)
- **Author**: Affaan Mustafa
- **Repository**: <https://github.com/affaan-m/everything-claude-code>
- **License**: MIT (see [`LICENSE`](./LICENSE) — copy of upstream license preserved)
- **Version vendored**: snapshot taken on 2026-04-25

## Why these are here

They're bundled in this repo as part of the author's **personal backup** — they're symlinked back into `~/.claude/skills/` by [`scripts/install.sh`](../../scripts/install.sh) when restoring on a new Mac.

They are **NOT** listed in [`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json) and **cannot** be installed via `/plugin install` from this repo. Anyone who wants ECC should install it directly from upstream.

## Files vendored

| File                          | Purpose                                                                                                |
| ----------------------------- | ------------------------------------------------------------------------------------------------------ |
| `api-design.md`               | REST API design patterns: naming, status codes, pagination, filtering, errors, versioning, rate limit. |
| `backend-patterns.md`         | Node.js / Express / Next.js API routes / DB optimization.                                              |
| `coding-standards.md`         | Universal TS/JS/React/Node standards.                                                                  |
| `database-migrations.md`      | Multi-ORM migration patterns (Prisma, Drizzle, Kysely, Django, TypeORM, golang-migrate).               |
| `frontend-patterns.md`        | React / Next.js / state management / performance.                                                      |
| `postgres-patterns.md`        | PG query optimization, schema design, indexing, security (Supabase best practices).                    |
| `security-review.md`          | Comprehensive security checklist for auth, input handling, secrets, payment features.                  |

## How to update these from upstream

```bash
# Clone fresh upstream
git clone https://github.com/affaan-m/everything-claude-code /tmp/ecc

# Copy the relevant skills
cp /tmp/ecc/skills/{api-design,backend-patterns,coding-standards,database-migrations,frontend-patterns,postgres-patterns,security-review}.md vendor/ecc-skills/

# Update LICENSE if upstream changed it
cp /tmp/ecc/LICENSE vendor/ecc-skills/LICENSE
```

---

If you are the author of ECC and prefer this content not be vendored here, please [open an issue](https://github.com/bymaxone/bymax-agent-kit/issues) — we'll remove it promptly.
