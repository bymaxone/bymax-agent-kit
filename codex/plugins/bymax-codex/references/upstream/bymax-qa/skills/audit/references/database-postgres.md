# Database & PostgreSQL (RLS, least privilege, parameterization)

Maps to ASVS 5.0 V1/V2 (the injection surface, covered in `security-input.md`),
V8 (authorization at the data layer), and V13/V14 (configuration and data
protection). This reference is the data-tier half: isolation enforced (or not)
in the database, the app role's privileges, and how credentials and secrets
travel.

## What to expect by stack

- An ORM (Prisma, Drizzle, TypeORM, Kysely, sqlx, Diesel) parameterizes by
  default; the SQLi surface is the raw escape hatch, hunted in
  `security-input.md`. Here the question is isolation and privilege.
- Multi-tenant apps enforce isolation at the app layer (a `where tenantId`
  everywhere) and, defensively, at the database with Row-Level Security. Many
  real backends have the first and not the second — that is a genuine gap to
  weigh by severity, not a reflex CRITICAL when the app layer holds.

## Deterministic

- Migrations: `grep -riE 'enable row level security|create policy|force row
  level security'` over the migrations directory. Record present/absent per
  tenant-scoped table.
- The app's DB role: is it the owner/superuser, or a least-privilege role that
  cannot `DROP`/`ALTER`/`CREATE`? A connection string using the `postgres`
  superuser for the app is a finding.
- Connection string handling: is it built from parts and kept out of logs and
  error messages, or does a `user:pass@host` literal appear in a log line, an
  error body, or a committed file?
- `sslmode`/TLS to the database where it crosses a network.

## Static hunt (the finder's brief)

- **RLS present and enforced** — for each tenant-scoped table, is there a policy
  and is it `FORCE`d (so even the table owner is subject to it)? A policy that
  the app role bypasses because it owns the table is not enforcement.
- **App-layer isolation completeness** — does every read/write path carry the
  tenant predicate, including the "find one by id" that skips the list scope,
  raw fragments, and aggregate queries? A single unscoped path is the isolation
  hole (this overlaps `security-authz.md` — file once, at the root cause).
- **Least privilege** — can the app role alter schema, read other schemas,
  access `pg_catalog` beyond need, or use `COPY ... TO PROGRAM`? The blast
  radius of an injection is the role's privileges.
- **Secrets in migrations/seeds** — a seed file with a real credential, a
  hard-coded admin password, PII in a fixture.
- **Migration safety** — expand-then-contract, or a destructive migration
  (drop a column still read) that a rolling deploy would break — a correctness
  and availability finding, weighed accordingly.

## Live (`--live` only, in-session)

- Only if the scope grants a database connection to a `local`/`staging`
  instance. Confirm RLS with two tenants: connect as the app role, set the
  tenant context the way the app does, and try to read the other tenant's row;
  it must return nothing.
- Confirm the app role cannot `CREATE TABLE`/`DROP TABLE` — attempt one and
  expect a permission error.
- Never run a destructive statement against shared data; use a throwaway row
  you created.

## Common non-findings (drop these)

- Absent RLS where the app layer demonstrably scopes every path and the design
  names app-level isolation — a defence-in-depth MEDIUM, not a CRITICAL.
- The `postgres` superuser in a local dev compose the scope marks `local`.
- A "raw" ORM method whose arguments are bound (read the call before flagging
  SQLi — that belongs in `security-input.md` and only with a reachable, unbound
  fragment).
