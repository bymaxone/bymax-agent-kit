# Frontend quality & security

Only applies when the target has a frontend. A headless API has nothing to
grade here — say so in the coverage block and skip the domain, do not
manufacture findings. When there is a UI (Next.js, a React/Vue/Svelte app, a
server-rendered template set), grade it on security, accessibility and
performance, and drive the live checks through `bymax-web-verify` when it is
installed rather than reimplementing a browser driver.

## Security

- **XSS sinks** — `dangerouslySetInnerHTML`, `v-html`, `{@html}`, a template
  filter that disables escaping, `innerHTML =`, `document.write`. Each is a
  candidate; the finding is user input reaching one unescaped
  (`security-input.md` governs the trace).
- **Token storage** — is an access or refresh token in `localStorage`/
  `sessionStorage` or a non-HttpOnly cookie? That is reachable by any XSS and
  is a finding. The safe pattern is an HttpOnly cookie the JS never reads.
- **CSP** — is there a Content-Security-Policy, and is it real (nonce/hash
  based, not `unsafe-inline`/`unsafe-eval`)? Are Trusted Types required for
  DOM sinks where the framework supports it?
- **Secrets in the bundle** — a private key, an API secret, or a server-only
  token shipped to the client build. Grep the built output, not just source.
- **Auth-state leakage** — does a client component import a server-only JWT
  helper (a build-time guard like `server-only` should make that a build
  error)? Does an error boundary or a redirect leak a token in the URL or
  referrer?

## Accessibility (WCAG 2.2)

- Run `axe` (via `@axe-core/playwright` or the CLI) against the key pages when
  `--live` and a browser is available. Report violations by rule id and impact
  (critical/serious). Missing labels, contrast failures, keyboard traps and
  focus-order breaks are the common serious ones.
- These are quality findings, filed with the same contract at LOW/MEDIUM unless
  an accessibility failure also blocks a security-relevant flow (a login a
  keyboard user cannot complete).

## Performance (Core Web Vitals)

- Run Lighthouse against the key routes when `--live`. Report the p75 metrics
  against thresholds: LCP ≤ 2.5s, INP ≤ 200ms, CLS ≤ 0.1.
- A performance regression is a finding only when it crosses a threshold on a
  route that matters; a lab number a few ms over is noise, not a finding.

## How to run the live checks

Prefer the project's own browser tooling. If `bymax-web-verify` is installed,
its `verify`/`test` flow drives the real browser and reports console errors,
network calls and the accessibility snapshot — reuse it and cite its output as
evidence, rather than standing up a second Playwright. Without it, note the
frontend live checks as "not run: no browser driver" in the coverage block.

## Common non-findings (drop these)

- User input in a JSX/template expression that the framework auto-escapes,
  reported as XSS.
- A public, publishable key (a Stripe publishable key, a public API key meant
  for the client) flagged as a leaked secret — read what the key is.
- A Lighthouse metric a hair over threshold in a cold lab run — take p75, not a
  single sample.
- Accessibility "violations" on a third-party embed the app does not control
  (note them, do not file them against the app).
