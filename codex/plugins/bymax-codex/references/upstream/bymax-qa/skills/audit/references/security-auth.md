# Authentication (ASVS V6 / V7 / V9 / V10 · API2)

Maps to OWASP ASVS 5.0 chapters V6 (Authentication), V7 (Session Management),
V9 (Self-contained Tokens), V10 (OAuth/OIDC), and OWASP API Security Top 10
2023 API2 (Broken Authentication). Cite the requirement id (e.g. `V9.2.1`) and
the CWE on every finding.

Each check below is a **hypothesis to disprove**, not a claim to assert. The
finder proposes; `verification.md` disposes. A control you cannot reach in the
target is `not applicable`, recorded as such, never a pass or a fail.

## What to expect by stack

| Stack | Where auth lives | Notes |
| --- | --- | --- |
| `@bymax-one/nest-auth` | the library; the app wires options via `registerAsync` | JWT HS256 pinned, JTI blacklist in Redis, refresh rotation + reuse detection, scrypt, TOTP MFA, per-IP + per-email rate limit. Many controls are the library's; verify the app's **wiring**, not a reimplementation. |
| Passport / NextAuth / Lucia | a strategy/adapter layer | check the session store, cookie flags, and that the strategy actually validates |
| custom JWT | a hand-rolled sign/verify | the highest-risk case: alg pinning, secret strength, expiry, revocation are all easy to get wrong |

A control the app delegates to a library is verified by reading the wiring and,
under `--live`, by the behaviour — not by re-deriving the crypto.

## Deterministic

- Dependency advisories on the auth stack (`osv-scanner`, `npm audit`,
  `cargo audit`) — record versions and any advisory.
- Grep for the classic mistakes as **candidates only**: `algorithms: ['none']`,
  a JWT verify without an `algorithms` allow-list, `jwt.decode` used where
  `verify` is meant, `Math.random()` for a token, `==`/`===` on a secret where
  a constant-time compare is expected, a hard-coded secret or a default one.
- Confirm password hashing is a memory-hard KDF (scrypt/argon2/bcrypt), not a
  bare hash. Grep is the candidate; the call site is the proof.

## Static hunt (the finder's brief)

- **Login** — is the failure response and timing the same for "unknown user"
  and "wrong password"? A different message or a branch that skips hashing on
  an unknown user is user enumeration (CWE-204). Is there a lockout or rate
  limit, and is it keyed so it cannot be bypassed by varying a header?
- **Password policy** — a minimum length, and no maximum so low it truncates;
  a null byte or a param-array trick that removes the check; a common-password
  or breach check if the spec claims one.
- **MFA / TOTP** — can a used code be replayed inside its window? Is the
  time-step window wider than ±1? Are backup codes single-use? Can the MFA
  step be skipped by calling the post-MFA endpoint directly with the pre-MFA
  token (the temp token accepted as an access token)? A race in enrolment?
- **JWT** — `alg:none` rejected even with a junk signature segment? An RS→HS
  confusion (a token signed with the public key as an HMAC secret) rejected?
  Are `exp`, `nbf`, `iat` enforced? Is a token with no `jti` rejected when
  revocation depends on the `jti`? Are `aud`/`iss` validated? Does logout
  actually invalidate the token, not just drop the cookie? On rotation, does
  replaying a consumed refresh token revoke the whole token family, and only
  that family?
- **OAuth / OIDC** — is `state` present, single-use, and bound to the
  provider (RFC 9700 mix-up)? Is PKCE used? Is `redirect_uri` validated
  against an allow-list, not a prefix or substring match? Can the callback be
  CSRF'd? Does a token or code leak into a redirect, the referrer, or a log?

## Live (`--live` only, in-session)

Use `qa-probe.sh` so every request and response is captured to
`evidence/<run>/`. Throwaway accounts only.

- Register two throwaway accounts; capture a valid access + refresh token.
- **alg:none / tamper** — take a valid token, re-encode with `alg:none` and
  again with an edited payload; each must be rejected. `jwt_tool` if the scope
  allows it, otherwise a scripted re-encode.
- **Refresh reuse** — use a refresh token, then use the same original token
  again; the second must fail and the whole lineage must be revoked. Confirm
  the first login's access token is now dead too.
- **Logout invalidation** — log out, then call an authenticated route with the
  pre-logout access token; must be 401.
- **Enumeration timing** — N login attempts with a known-absent email vs a
  known-present one with a wrong password; compare status, body and a timing
  distribution, not a single sample. Report only a difference that survives
  the distribution — a single slow request is noise (see `verification.md`).
- **Lockout / rate limit** — a bounded burst (only if the scope permits it)
  against login; confirm the lock trips and that it is not bypassed by
  changing `X-Forwarded-For` when the app does not trust that header.

## Common non-findings (drop these)

- A different message for a *disabled* vs *absent* account when the spec says
  registration is closed and both are meant to be indistinguishable — verify
  the intent before calling enumeration.
- Missing rate limit on an endpoint the scope says sits behind a gateway that
  rate-limits (DELEGATED).
- A short access-token lifetime "allowing replay" within its window — that is
  the design; the question is revocation, not lifetime.
- Secrets read from env vars or CLI flags — treated as trusted input, not a
  finding, unless they are committed.
