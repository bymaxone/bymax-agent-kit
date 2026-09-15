---
description: 'Assisted UI testing with the full stack running: discovers the project''s frontend/backend, reuses an already-running backend instance (or starts one and waits for its health check), opens the frontend in the Claude Desktop Browser pane via .claude/launch.json + preview_start, and drives the UI step by step while the user watches — clicks, forms, navigation — verifying each step with four evidence sources (page state, console, network calls, server logs). In a terminal session without the Browser pane it falls back to the agent-browser CLI. Optional args: a free-text flow to test (default: smoke test), `browser` to force the external browser, `mobile` viewport preset, `dark` color scheme. Never uses real credentials, never performs destructive actions unasked. Triggers: "teste assistido", "testar a ui", "testar no preview", "test the ui", "assisted test", "/bymax-web-verify:test".'
argument-hint: "[flow-to-test] [browser] [mobile] [dark]"
---

# /bymax-web-verify:test — assisted UI testing, full stack up, user watching

Bring the project's stack up and test the UI live. In the Claude Desktop app the
frontend runs in the **Browser pane** so the user watches every step; in a plain
terminal it falls back to a real external browser via `agent-browser`. The backend
(when the project has one) is orchestrated behind the scenes — an instance already
running on the device is **reused**, never duplicated.

## Arguments (all optional, any order)

- **Free text** → the flow to test (`"login"`, `"/dashboard"`, `"cadastro de treino"`).
  The text becomes the test script: derive concrete numbered steps from it.
  Without it → **smoke test**: home page renders, main navigation works, zero
  console errors, all API calls 2xx.
- `browser` → force BROWSER mode (external `agent-browser`) even when the preview
  is available.
- `mobile` → viewport preset 375×812 before testing. `dark` → dark color scheme.

## Mode detection (no argument needed)

Check which tools this session exposes:

- **Browser-pane tools present** (`preview_start`, `read_page`, `computer`,
  `read_console_messages`, …) → **PREVIEW mode** — the Claude Desktop app. This is
  the primary mode: the user sees the test happen.
- **Absent** (plain terminal) → **BROWSER mode** — pre-flight `command -v
  agent-browser`; if missing, offer `/bymax-web-verify:setup` and stop.

`browser` argument overrides detection.

## Phase 1 — Discover the stack (read-only)

1. Map the layout: single app, or monorepo with `frontend/` + `backend/` (or
   `apps/*`)? Read each `package.json` for the dev script; read `.env` /
   `.env.example` / framework config for ports.
2. Backend health endpoint: look for `/health`, `/api/health`, or the framework's
   default; fall back to "root URL answers".
3. State the plan in two lines: what will run where (ports), and the numbered test
   steps derived from the flow argument. The user is watching — narrate.

## Phase 2 — Backend (skip when the project has none)

```bash
lsof -iTCP:<port> -sTCP:LISTEN        # something already on the port?
curl -sf http://localhost:<port><health-path>
```

- **Already running and healthy** → reuse that instance/port. Never start a second
  copy, never kill the existing process.
- **Port busy but unhealthy** → report it and ask how to proceed — do not kill a
  process you didn't start.
- **Not running** → start it with the project's dev script as a background Bash
  task, then poll the health endpoint (up to ~60 s). On failure, read the server
  output, diagnose, and report before touching the frontend.
- Track whether **you** started it — the final report tells the user what is
  running and how to stop it.

## Phase 3 — Frontend up

**PREVIEW mode:** ensure `.claude/launch.json` has an entry for the frontend dev
server (create it from the discovered dev script + port if missing — the file the
Desktop app also manages), then `preview_start {name: "<entry>"}`. It reuses the
server when one is already running. Apply the viewport now: `mobile` via
`resize_window` with the 375×812 preset, `dark` via the same tool's
`colorScheme: "dark"` option (color scheme is a `resize_window` parameter, not
a side effect of resizing).

**BROWSER mode:** if a dev server already answers on the discovered port, reuse
it; else start it as a background Bash task and wait for the port. Then
`agent-browser open "http://localhost:<port>"`.

## Phase 4 — The assisted test loop

For each numbered step of the script, in order — announce the step, act, verify:

**PREVIEW mode:**
1. `read_page` → find the target elements (refs).
2. Act: `computer` (click/type/scroll) or `form_input` on the refs.
3. Verify with the four evidence sources before calling the step done:
   - `read_page` — the UI reached the expected state;
   - `read_console_messages` — no new errors (a console error fails the step);
   - `read_network_requests` — the step's API calls returned 2xx (an unexpected
     4xx/5xx fails the step even when the UI looks fine);
   - `preview_logs` — no server-side errors.
4. `computer {action: "screenshot"}` at key moments as proof.

**BROWSER mode:** same loop with `agent-browser snapshot -i` → `click @ref` /
`fill @ref` → `errors` + `console` → `screenshot`; re-snapshot after every
navigation (refs change). `agent-browser` does not expose per-request network
data, so the **2xx gate moves to the backend side**: when this command started
the backend, tail its logs (`preview_logs` equivalent — the background task's
output) for the request the step triggered and fail the step on a 4xx/5xx there;
when the backend was already running and its logs aren't reachable, scope the
2xx gate out and say so in the report (UI state + console remain the evidence).

### When a step fails

Diagnose from the evidence (console, network, backend logs) → read the source to
find the cause → report it; apply a fix only if the user asked to fix, then reload
and re-run the failed step. Never mark a step passed on partial evidence.

### Safety rails

- **Never real credentials.** Login steps use a seeded test user or `.env.test`
  values; if none exists, ask the user for the test account — never type real
  passwords or personal data (harness rules prohibit it regardless).
- **Never destructive actions unasked** — no deletes, purchases, or irreversible
  submits unless the flow argument explicitly requested them.
- Test data only: anything created during the test is named so it's recognizable
  (`test-…`), and the report lists what was created.

## Phase 5 — Report and final state

```
## Assisted UI Test  (mode: PREVIEW|BROWSER · flow: <flow> · viewport: <preset>)

| # | Step | Result | Evidence |
|---|------|--------|----------|
| 1 | <step> | ✅ / ❌ | <what proved it — UI state, 2xx calls, console clean> |

Servers: backend <reused|started> on :<port> · frontend <reused|started> on :<port>
Created test data: <list or none>
```

**Leave everything running** — the point is that the user keeps watching and
interacting with the preview. Say what you started and the exact command to stop
it. In BROWSER mode, `agent-browser close --all` after reporting (the user isn't
watching that browser).

If a failure traced to source code and wasn't fixed, offer the follow-up:
`/bymax-workflow:verify` + fix, then re-run `/bymax-web-verify:test <flow>`.

## Relationship to `/bymax-web-verify:verify`

`verify` confirms one change works — pointed, read-only by default, browser only.
`test` brings the whole stack up and walks a flow interactively, preview-first.
After a UI-touching change passes `/bymax-workflow:verify`, this command is the
"see it actually working" step.
