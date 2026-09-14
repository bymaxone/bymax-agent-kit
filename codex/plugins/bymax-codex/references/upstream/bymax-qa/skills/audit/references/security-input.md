# Input & injection (ASVS V1 / V2 / V5 · API Top 10 A05/A03)

Maps to ASVS 5.0 V1 (Encoding & Sanitization), V2 (Validation & Business
Logic), V5 (File Handling), and OWASP Top 10:2025 A05 (Injection). Cite the
ASVS id and the CWE (CWE-89 SQLi, CWE-79 XSS, CWE-78 command injection, CWE-22
path traversal, CWE-611 XXE, CWE-502 unsafe deserialization, CWE-915 mass
assignment).

The rule that keeps this honest: an injection finding needs a **reproduction
that shows the payload reaching the sink**, not a payload that looks dangerous.
A string-concatenated query is a candidate; the finding is the request that
proves the concatenation is attacker-reachable and unescaped.

## What to expect by stack

- **ORM** (Prisma, Drizzle, TypeORM, sqlx) parameterizes by default. The risk
  is the escape hatch: `$queryRawUnsafe`, `sql.raw`, `.query(string)`, a
  `WHERE` built by string concatenation. Find the raw fragments; those are the
  only SQLi candidates worth live-probing.
- **NoSQL / query operators** — an object where a scalar is expected
  (`{ $ne: null }`, `{ $gt: '' }`) reaching a Mongo query or a filter builder.
- **Templating** — server-side template injection where user input reaches a
  template compiler; XSS where it reaches HTML without escaping. A framework
  that auto-escapes (React, most template engines) makes the default safe; the
  finding is where escaping is bypassed (`dangerouslySetInnerHTML`,
  `v-html`, `| safe`, `innerHTML =`).
- **File handling** — an upload path, an object key, a filename that reaches
  the filesystem or an S3 key. Path traversal (`../`), a null byte, an absolute
  path, an unbounded size.

## Deterministic

- Grep the raw-query escape hatches and the HTML-escape bypasses above —
  candidates, each proven at the call site.
- Grep for `child_process` / `exec` / `system` with a non-literal argument
  (command injection), `eval`/`Function(`, and deserializers fed untrusted
  input (`yaml.load` without a safe schema, `pickle`, Java native).
- Grep DTOs for missing validation: a body field consumed without a schema
  (Zod, class-validator, a JSON schema) or with `whitelist`/`forbidNonWhitelisted`
  off, which is how mass assignment gets in.

## Static hunt (the finder's brief)

- **SQLi** — trace each raw fragment from the request to the query. Is any part
  of it attacker-controlled and unparameterized? An ORM `where` built from a
  parsed sort/filter param is a frequent real one.
- **Mass assignment** — does a create/update spread the whole body into the
  entity? Can it set a field the caller should not (`role`, `tenantId`,
  `verified`)? This overlaps `security-authz.md` — file it once, under whichever
  is the root cause.
- **XSS / SSTI** — where does user input reach a rendered surface without
  escaping, or a template compiler?
- **Path traversal / SSRF** — a filename or object key concatenated into a
  path without normalization; a URL from the request handed to a fetch without
  an allow-list. (Path-only SSRF against an internal metadata endpoint is
  in scope; a bare "the app makes an outbound request" is not, per the
  exclusion list in `verification.md`.)
- **Deserialization / XXE** — untrusted input to a deserializer or an XML
  parser with external entities enabled.

## Live (`--live` only, in-session)

- Send a benign marker payload first (a unique string), confirm it round-trips
  where expected, then the injection payload — so a negative result means the
  sink is safe, not that the request never arrived. This is the
  positive-control rule: a scan that cannot distinguish "safe" from "never got
  there" certifies the vulnerable case (see `verification.md`).
- **SQLi** — against a raw fragment only, and only with the scope's
  permission, a boolean or time-based probe (`sqlmap` if allowed, else a
  scripted pair). A time delay that tracks the payload is the reproduction.
- **Mass assignment** — send the forbidden field, then read the object back
  and confirm whether it took.
- **Path traversal** — request `../` sequences against an upload/download path;
  confirm whether a file outside the intended root is reachable.
- Capture request + response for each to `evidence/<run>/`.

## Common non-findings (drop these)

- A parameterized query flagged because the ORM method name contains "raw" but
  the arguments are bound — read the call.
- User input in a React/JSX expression (auto-escaped) reported as XSS.
- A payload that "looks like" it injects but the response shows it was escaped,
  rejected by validation, or never reached the sink.
- Validation "missing" on a field a pipe/guard already validated upstream.
