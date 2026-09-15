# Recon & threat model

Before hunting, know the system. Recon detects what is actually there, the
threat model decides where the finders spend effort. Skipping either produces
a hunt that is a grep with extra steps: a long list of true-but-irrelevant
observations and a miss on the one boundary that mattered.

Write everything here to `evidence/<run>/recon.md`. It is the map every later
step and every finding cites.

## 1. Detect the stack — do not assume it

The plugin is generic. Read the project; never carry an assumption from one
target to the next. Detect and record:

| Question | Where to look |
| --- | --- |
| Language / runtime | `package.json`, `Cargo.toml`, `go.mod`, `pyproject.toml`, `pom.xml` |
| HTTP framework | deps + bootstrap file — NestJS, Express, Fastify, Hono, Next.js route handlers, Axum, Actix, FastAPI, Spring |
| ORM / DB client | Prisma, Drizzle, TypeORM, Kysely, sqlx, Diesel, raw driver — and the database it points at |
| Cache / broker | Redis (ioredis, node-redis), Memcached, BullMQ, SQS |
| Auth | a first-party module, or a library (`@bymax-one/nest-auth`, Passport, NextAuth, Lucia, a custom JWT layer) |
| Logging / telemetry | Pino, Winston, `console`, OpenTelemetry, a log shipper config |
| Frontend, if any | a `web/` or `app/` tree, a framework, a bundler — or none (a headless API) |
| CI gates | `.github/workflows/`, other CI config — what already runs |

Record the versions. A finding about a library's behaviour cites the version
in the lockfile, never a remembered one.

## 2. Inventory the HTTP surface

List every route: method, path, the guards/middleware/decorators on it, and
whether it is public or authenticated. For a large codebase spawn the
`qa-recon` agent to produce this table and read its output as data.

Two traps this inventory exists to catch, both measured on real targets:

- **A grep of a route list is not the route list.** A path that appears in a
  file, a comment, a test fixture or a second framework's config is not a
  mounted route. Confirm a route is real by the router registration or, when
  `--live` and the target is up, by hitting it. A manual sweep once reported
  four routes present because they appeared in a file; the router mounted two.
- **A declared control may be dead.** A rate-limit or throttler dependency in
  the manifest that nothing imports; a CORS config never applied; a guard
  defined but not bound. Grep proves the symbol exists, not that it runs. Note
  each control as **present / absent / declared-but-unwired**, and resolve
  "declared-but-unwired" by finding where it is applied, or confirming it is
  not.

## 3. Controls have three states, not two

This is the single most important rule for keeping false positives out of a
generic audit. For every expected control (CORS, HSTS, rate limiting, a
metrics endpoint's auth, CSRF defence, a security header), classify it:

- **PRESENT** — applied on the path it should cover. Verify, then move on.
- **DELEGATED** — intentionally handled elsewhere: HSTS at the TLS terminator,
  CORS at an API gateway, tenant isolation in a library, `/metrics` behind an
  ingress. A control is DELEGATED only when something names where it lives —
  the spec, a doc, a config comment, an architecture note. Record the pointer.
- **ABSENT** — expected, and nowhere to be found. Only ABSENT is a candidate,
  and only after you looked for a DELEGATED explanation and did not find one.

The failure mode without this: a headless API behind an edge legitimately has
no in-app CORS, disables HSTS in its own middleware, returns 404 on `/metrics`
by default, and declares a throttler dependency it never wires. A naive
auditor reports five findings; all five are DELEGATED or intentional. Ask
"where would this live if not here?" before writing ABSENT.

## 4. Trust boundaries

Draw where data crosses a trust level: the public internet → the API; the API
→ the database; the API → the cache; the API → a downstream service; one
tenant → another; an unauthenticated user → an authenticated one → an admin.
A C4 container sketch in prose is enough. Every boundary is a place a finder
can look.

## 5. Threat model — STRIDE per boundary

For each boundary, one table: **S**poofing, **T**ampering, **R**epudiation,
**I**nformation disclosure, **D**enial of service, **E**levation of privilege.
One line per applicable threat: the threat, the control that should stop it,
and its state from §3. A boundary with a missing or unwired control for a
plausible threat is where a `qa-hunter` is pointed first.

This table is the hunt's plan. `--domains` selects which boundaries' threats a
finder covers; `--depth` sets how deeply they are hunted: `quick` runs **no**
finder agents (recon plus the deterministic scans only), `full` points one
`qa-hunter` at each selected boundary, and `deep` gives each a second,
adversarial pass.
