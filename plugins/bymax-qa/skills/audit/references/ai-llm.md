# AI, LLM & agents (OWASP Top 10 for LLM Applications 2025)

Maps to LLM01 (prompt injection), LLM02 (sensitive information disclosure),
LLM05 (improper output handling), LLM06 (excessive agency), LLM07 (system
prompt leakage), LLM08 (vector and embedding weaknesses) and LLM10 (unbounded
consumption); CWE-1427 for prompt construction from untrusted input. The
question is never "can the model be talked into something" — it is whether the
code around the model lets that reach a principal, a resource or a sink the
requester could not reach directly.

## When this domain runs

Only when recon recorded LLM or agent tooling (a model provider SDK, an agent
framework, an MCP server or client). Without it, record "no LLM surface" and
skip the domain: do not hunt it on speculation.

## What to expect by stack

- A provider SDK called directly (`openai`, `@anthropic-ai/sdk`) behind an API
  route: the route's own auth, rate limit and spend cap are the controls.
- The Vercel AI SDK (`ai`, `@ai-sdk/*`) or LangChain / LlamaIndex with tool
  definitions: each tool's `execute` is a server-side handler and is audited
  like any other handler, with the model as an untrusted caller.
- An MCP server or client (`@modelcontextprotocol/sdk`, an `.mcp.json`): the
  server's tools run with whatever credentials it was given.
- A token or quota layer (`@bymax-one/nest-ai-tokens` or a hand-rolled
  counter): the per-tenant budget is the availability control.

## Deterministic

- A provider key in a client bundle: `NEXT_PUBLIC_`, `VITE_` or `EXPO_PUBLIC_`
  variables holding a model API key, or a key in mobile/web source.
- Model output reaching a sink: `eval`, `Function`, a shell, raw SQL, a file
  path, a redirect URL, `dangerouslySetInnerHTML` or a Markdown renderer that
  allows raw HTML or remote images.
- Tool definitions exposing a filesystem, a shell, an HTTP fetch of arbitrary
  URLs, or a database query built from tool arguments.
- MCP configuration: servers fetched by moving tag or `latest`, remote servers
  without authentication, credentials passed wider than the server needs.

## Static hunt (the finder's brief)

- **Authority at the tool boundary (LLM06)** — does each tool act with the
  end user's authority and check authorization itself, or does it trust the
  model's arguments? A tenant or user id taken from tool arguments rather than
  the session is the classic finding. A destructive or paid action without a
  confirmation step is excessive agency.
- **Untrusted content in context (LLM01, LLM08)** — retrieved documents,
  emails, web pages and tool results written by one principal and read into a
  context that can call tools with another principal's authority. Vector-store
  queries without a tenant filter are cross-tenant reads.
- **Output handling (LLM05)** — model output rendered as HTML or Markdown with
  links and images (a data-exfiltration channel), or used in a query, command,
  path or URL without the encoding that sink needs.
- **Disclosure (LLM02, LLM07)** — secrets, internal URLs or other users' data
  placed in a system prompt or shared context; conversation memory or a cache
  keyed so one user's history serves another.
- **Spend and availability (LLM10)** — per-user and per-tenant rate and token
  limits, a `max_tokens`, a bound on agent loop iterations, and no
  unauthenticated route that proxies to a paid model.

For the full attack-class catalogue read
[`../../security-audit/AI-AND-LLM.md`](../../security-audit/AI-AND-LLM.md),
and only its section for the boundary being hunted.

## Live (`--live` only, in-session)

Against an allow-listed, non-production host, from a low-privilege test
account: ask the assistant to act on a resource owned by another test tenant
and confirm the server refuses it, whatever the model answers; confirm the
model route returns 429 past its limit. Keep model spend bounded and never use
a production model account.

## Common non-findings (drop these)

- A jailbreak that changes only what the model says, with no boundary crossed
  and no data or action beyond what the requester already has.
- A system prompt that can be extracted and holds no secret — note it, low.
- A provider key held server-side in the environment and never shipped to a
  client.

Remediation for confirmed findings: `/bymax-qa:security-playbooks` has
procedures for LLM guardrails, agent tool-invocation controls and continuous
red-teaming in CI.
