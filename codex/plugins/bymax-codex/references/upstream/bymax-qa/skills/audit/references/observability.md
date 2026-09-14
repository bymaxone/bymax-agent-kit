# Observability as a security surface (ASVS V16)

Maps to ASVS 5.0 V16 (Security Logging & Error Handling) and OWASP Top 10:2025
A09 (Security Logging & Alerting Failures). Observability is not just an ops
concern: a log that leaks a secret is a disclosure, a log an attacker can forge
defeats an investigation, and a security event that is never recorded is an
attack nobody can see. Test it as a security surface.

The governing rule of this domain, measured on real systems: a control that
matches by **name** cannot see content, and an audit that matches **literally**
cannot see an encoding. Both fail silently, both return "clean". Use
`qa-log-audit.sh`, which decodes before searching and states its coverage.

## What to expect by stack

- A structured logger (Pino, Winston) with a redaction list of field names
  (`authorization`, `cookie`, `password`, `token`, `*.secret`, PII fields). The
  boundary: redaction censors a value stored under a listed **name**; the same
  value inside a free-text string (a rendered email body, an SDK error message,
  an `Error.cause`) passes untouched.
- OpenTelemetry with span attributes; the risk is a secret or full URL (with
  query) landing in a span attribute or baggage, and traces propagating to an
  untrusted downstream.
- A log store (Loki) + dashboards (Grafana). The risk is anonymous access and
  LogQL injection from a user-controlled field.

## Deterministic

- Read the redaction config: does it cover `authorization`, `cookie`,
  `set-cookie`, request bodies with credentials, and the PII the app handles?
  Is it applied to **every** logger instance, not just the root?
- Grep for log calls that pass a whole request, a whole error, an SDK response,
  or a rendered template into the logger — the free-text leak paths.
- Check OTel span attributes for `url.full`/`db.statement`/header captures that
  could carry secrets, and whether URL query is redacted before export.

## Static & live hunt

- **Secret leakage** — run test traffic through auth, password reset, MFA and
  any OTP path, then run `qa-log-audit.sh <known-secret> <logfile>` (or against
  the Loki query output). The audit **decodes** base64/url/hex/json-escape
  first and **names** the encodings it covered. A grep that skips this
  certifies the leaking case. Report a leak with the encoding it hid under.
- **Log injection / forging** — send a value with a newline/CRLF and a forged
  log-line shape in a field that gets logged (a username, a header). If it
  produces a second, attacker-authored log entry an investigator would trust,
  that is a finding (CWE-117) — a forged audit record, not mere cosmetic noise.
- **Event coverage** — confirm that auth failures, MFA failures, privilege
  changes, token rotation/reuse detection, and rate-limit trips are each logged
  at the service level with enough context to investigate, and **without** the
  sensitive payload. Gateway/WAF logs do not satisfy this — verify in the app.
  A telemetry interceptor that runs after the guard misses every 401/403/429
  and every 404 for an unmatched route; those must be recorded by middleware,
  or the attack in progress leaves no trace. Check where request telemetry is
  emitted.
- **Detectability** — an exploit you ran in an earlier domain should have
  produced an alertable signal. Re-check: did the BOLA probe, the brute-force
  burst, the alg:none attempt leave a log line or move a metric? A blind spot
  is itself a finding.
- **Store access control** — is Loki reachable without auth (it ships with
  `auth_enabled: false` and expects a proxy)? Is Grafana anonymous access off,
  admin rotated, version hidden, CSP/HSTS set? Can a user-controlled field
  reach a LogQL query unescaped?

## Common non-findings (drop these)

- A field-name redaction that misses a secret inside a rendered string, when
  the design keeps that string out of logs entirely — verify the string reaches
  a log before reporting; the finding is the data reaching the log, not the
  redactor's inability to see inside it.
- Loki with `auth_enabled: false` behind a proxy the scope names as the auth
  boundary (DELEGATED) — confirm the proxy, then it is not a finding.
- Newline in a value that is escaped/encoded by the logger before write (no
  second entry produced) — not log forging.
