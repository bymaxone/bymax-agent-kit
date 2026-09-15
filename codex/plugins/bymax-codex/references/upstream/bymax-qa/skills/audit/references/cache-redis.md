# Cache & Redis (isolation, poisoning, TTL, exposure)

Maps to ASVS 5.0 V13 (Configuration) and V14 (Data Protection) as they apply to
a cache tier, and to the tenant-isolation concerns of V8. A cache is a shared
mutable store keyed by strings the app builds; the whole security question is
who can influence a key, and what a key's value discloses.

## What to expect by stack

- A typed cache library (`@bymax-one/nest-cache`, a repository pattern) composes
  every key as `{namespace}{sep}{prefix}{sep}{id}` with no bare-key path. The
  isolation boundary is the namespace; the risk is a namespace or a key segment
  that is attacker-influenced or unvalidated. `nest-cache` 1.2.0 fixed exactly
  this — a namespace with a Redis glob metacharacter reached a destructive
  `flushNamespace` match pattern.
- A raw `ioredis`/`node-redis` client with hand-built keys is the higher-risk
  case: check every `get`/`set`/`del`/`keys`/`scan` for a key built from
  request input.

## Deterministic

- Advisories on the client library.
- Grep key construction: a cache key built from `req`/`params`/`query`/`body`
  without the tenant/user in it, or with a raw user string as a segment —
  candidates for cache poisoning or cross-tenant reads.
- Grep for `KEYS`/`FLUSHDB`/`FLUSHALL`/`CONFIG`/`DEBUG` reachable from request
  input, and for a match/glob pattern built from user input (`del(pattern)`).
- Check the Redis connection config: `requirepass`/ACL set, `protected-mode`
  on, bound to a private interface not `0.0.0.0`, TLS where it crosses a
  network. An unauthenticated Redis reachable off-box is a finding.

## Static hunt (the finder's brief)

- **Key isolation** — is every key namespaced by tenant **and** user where the
  value is per-user? Can caller A's request produce a key that serves caller
  B's value (poisoning), or read B's key (a key built from a header/param B
  also controls)?
- **Sensitive data at rest** — are tokens, session data, PII, or MFA secrets
  cached? If so, are they encrypted or scoped so a cache dump does not hand
  them over? A JWT or a password reset token sitting in plaintext under a
  guessable key is a finding.
- **TTL / revocation staleness** — does a revoked session, a changed role, or a
  logged-out token stay served from cache past its revocation because the TTL
  outlives the auth change? A cache that caches an authz decision without an
  invalidation path is the bug.
- **Unbounded growth** — a key space that grows with attacker input
  (one key per request with no cap or TTL) is a memory-exhaustion path.

## Live (`--live` only, in-session)

- With two throwaway accounts, request a cached resource as A, then as B with
  A's identifier in whatever field builds the key; confirm B does not get A's
  value.
- Change a role or revoke a session, then immediately request the resource
  whose authz is cached; confirm the change is honoured, not served stale past
  the revocation.
- Never run `FLUSHALL`/`KEYS *` against a shared cache; inspect key shape with a
  scoped `SCAN MATCH {namespace}:*` only if the scope permits direct Redis
  access, and never mutate.

## Common non-findings (drop these)

- Keys built from request input where the tenant/user is already in the
  namespace and the input is validated — read the key builder.
- A short-TTL cache of non-sensitive, non-authz data served slightly stale —
  that is caching working as designed.
- Redis bound to localhost with no auth in a local dev compose the scope marks
  `local` — a dev convenience, not a finding, unless the scope says otherwise.
