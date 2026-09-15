# Transport & configuration (ASVS V12 / V13 / V14)

Maps to ASVS 5.0 V12 (Secure Communication), V13 (Configuration) and V14 (Data
Protection). This is the perimeter: TLS, cookies, headers, CORS, error hygiene,
secret handling, and rate limiting on the paths that need it. It is also where
the three-state rule (`recon.md` §3) matters most — a headless API behind an
edge legitimately delegates half of this, and a naive audit reports the
delegation as a gap.

## Deterministic

- Security headers: is `helmet` (or equivalent) applied, and does it set the
  headers that matter for this app? HSTS may be **delegated** to the TLS
  terminator — check the recon note before flagging its absence.
- Cookies: `HttpOnly`, `Secure`, `SameSite` set on session/auth cookies? Is
  `Secure` derived from a real environment signal, not a `NODE_ENV` sniff that
  fails open on a near-miss?
- CORS: is it wildcard-with-credentials (`Access-Control-Allow-Origin: *` plus
  `Allow-Credentials: true`) — the combination browsers forbid and servers
  sometimes force? Is there any `enableCors` at all, and if not, is CORS
  **delegated** to a gateway (record where) or genuinely **absent**?
- Error handling: does a 500 return a stack trace, an internal path, a SQL
  fragment, or a driver message to the client? A framework error envelope
  should return a generic shape in production; an `exposeInternals`-style debug
  switch left on is a finding.
- Secrets: any hard-coded secret, a default credential, a secret in a committed
  file, or an env-dump/debug route (`/debug`, `/env`, `/config`, a verbose
  actuator) reachable without auth.
- Rate limiting: present on login, password reset, OTP, and expensive
  endpoints? Or **delegated** to a gateway the scope names? A declared
  throttler dependency that nothing wires is `declared-but-unwired`, not
  present.

## Static & live hunt

- **TLS** — is HTTP redirected to HTTPS, or is the app HTTP-only behind a
  terminator (DELEGATED, record it)? Under `--live` on a staging URL, check the
  negotiated protocol and that secure cookies are not sent over plain HTTP.
- **Cookie flags live** — register, capture `Set-Cookie`, confirm `HttpOnly`,
  `Secure`, `SameSite`. The other half — that no token lands in `localStorage`/
  `sessionStorage` or a non-HttpOnly cookie — a header check cannot prove;
  note it for a browser check (`bymax-web-verify`) if a frontend exists.
- **CORS live** — send an `Origin` from an untrusted host on a credentialed
  request; confirm the response does not reflect it with credentials allowed.
- **Error hygiene live** — trigger a 500 (a malformed body, a type error) and
  confirm the response carries no stack, path, or internal detail.
- **Debug routes** — request the common debug/actuator paths; expect 404 or
  auth, never a config dump.

## Common non-findings (drop these)

- HSTS disabled in the app's own middleware where the recon note (or a config
  comment) says the TLS terminator sets it — DELEGATED.
- No in-app CORS on a headless API the architecture puts behind a gateway —
  DELEGATED; confirm the gateway, then drop.
- `/metrics` or `/docs` returning 404 by default — the correct posture, not a
  missing endpoint. OpenAPI refused in production is correct.
- A throttler dependency present but unwired where rate limiting lives in the
  auth library or the gateway — resolve where it lives before flagging.
- Secrets read from environment variables — trusted input, not a finding.
