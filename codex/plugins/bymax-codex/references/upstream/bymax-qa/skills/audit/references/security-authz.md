# Authorization & tenant isolation (ASVS V8 · API1 / API3 / API5)

Maps to ASVS 5.0 V8 (Authorization) and OWASP API Security Top 10 2023 API1
(BOLA), API3 (BOPLA — broken object property level authorization), API5 (BFLA
— broken function level authorization). These are the defects an LLM finds most
reliably and the ones that hurt most, because a passing test suite rarely
exercises the second tenant. Cite the API id, the ASVS id and the CWE
(CWE-639, CWE-862, CWE-284).

## What to expect by stack

- **Ownership checks** live in a service, a guard, a policy layer, or an ORM
  filter (`where: { tenantId }`). Find where, and whether every read/write path
  goes through it — including the "get one by id" that skips the list filter.
- **Multi-tenant** apps resolve a tenant from the host, a claim, or a header.
  The safe pattern resolves it from the authenticated identity, never from a
  request body field. `@bymax-one/nest-auth` wires a `tenantIdResolver` for
  exactly this; a target that reads `tenantId` from the body is the bug.
- **Row-Level Security** in Postgres is the defence-in-depth layer under
  app-level checks. Its absence is a real, common gap worth flagging — but as
  the severity the architecture warrants, not as CRITICAL by reflex when the
  app layer does enforce isolation.

## Deterministic

- Grep for object lookups by id that do not carry an ownership/tenant
  predicate: `findUnique({ where: { id } })`, `findById(id)`, a raw
  `WHERE id = $1` with no tenant column — candidates, each proven at the call
  site by tracing whether a guard upstream already scoped it.
- Grep create/update DTOs for mass-assignable `role`, `tenantId`, `isAdmin`,
  `permissions` — a body that can set its own authority (BOPLA).
- Check for Postgres RLS: `grep -riE 'enable row level security|create policy'`
  over migrations. Absent is a candidate for a finding, weighted by whether
  app-level isolation is present.

## Static hunt (the finder's brief)

- **BOLA / IDOR** — for every route that takes an object id, is there an
  ownership check between the id and the caller? Trace it; a check three lines
  up in a shared guard is a pass, and missing it is the most common false
  positive here.
- **Cross-tenant** — can tenant A read or write tenant B's object by supplying
  B's id? Is the tenant taken from the token/host, or can the caller influence
  it via a body field, a query param, or a header?
- **Privilege assignment** — can a create/update body set `role`/`tenantId`/
  status and have it honoured? Is an invitation's role re-validated on
  acceptance, or trusted from the invite?
- **Function-level (BFLA)** — hit an admin-only route as a low-privilege user.
  Is the guard on the server, or only the UI hiding the button? Is a
  platform/admin token accepted by a tenant route and vice versa?
- **Horizontal & vertical** — a user acting as another user (horizontal); a
  user acting as an admin (vertical). Both need a route that checks role and
  ownership, not one or the other.

## Live (`--live` only, in-session)

- Create two throwaway accounts, ideally in two tenants (the scope's method).
- **BOLA** — as account A, create an object; note its id. As account B, GET /
  PUT / DELETE that id. Every cross-account access to a private object must be
  403 or 404 (consistently — a 403 on GET and 404 on DELETE leaks existence).
- **Tenant field injection** — register or create with a `tenantId`/`role` in
  the body that differs from the resolved one; confirm it is ignored or
  refused, not honoured.
- **BFLA** — as a low-privilege account, call each admin route from the
  inventory; expect 403, and confirm it is the guard, not a 404 from a
  UI-only route.
- Capture request + response for each to `evidence/<run>/`.

## Common non-findings (drop these)

- A lookup by id with no visible tenant filter where a guard upstream already
  bound the query to the caller's tenant — read the guard before reporting.
- Absent RLS where the app layer demonstrably isolates every path and the
  architecture names app-level isolation as the design — a defence-in-depth
  recommendation, not a CRITICAL.
- A 404 (not 403) for another tenant's object — that is often deliberate
  (do not confirm existence). Only inconsistency across verbs is the finding.
