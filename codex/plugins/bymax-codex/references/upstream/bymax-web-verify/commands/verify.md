---
description: Verify a web change in a real browser using the agent-browser CLI. Navigates to a URL (default the local dev server), exercises the affected path, and reports what it observed — screenshots, console errors, page errors, and the accessibility snapshot. Read-only by default; only interacts when the task requires it. Pre-flights the CLI and offers /bymax-web-verify:setup if missing. Triggers, "verificar no browser", "testar no navegador", "web verify", "confirmar no browser", "rodar e2e", "validar a página", "/bymax-web-verify:verify".
argument-hint: "[url] [what to check]"
---

# /bymax-web-verify:verify — verify a web change in a real browser

Drive a real browser with `agent-browser` to confirm a change actually works. This is the web counterpart to `/bymax-workflow:verify`: it observes behavior in a live page, it does not just read code.

## Step 0 — Pre-flight

1. **CLI present.** Run `command -v agent-browser`. If missing, abort with:
   `agent-browser CLI not found. Run /bymax-web-verify:setup first.`

2. **Target URL.** Resolve `<URL>` in this order:
   - A URL the user gave in the request.
   - Else a running local dev server — probe the common ports and use the first that answers:
     ```bash
     for p in 3000 5173 8080 4321 3001; do
       curl -sf -o /dev/null "http://localhost:$p" && echo "http://localhost:$p" && break
     done
     ```
   - If nothing answers, ask the user for the URL (or tell them to start their dev server) and stop. This is the **only** allowed question.

3. **What to verify.** Restate, in one line, the behavior you are about to confirm (from the user's request or the recent change). If unclear, ask once.

## Step 1 — Open and snapshot

```bash
agent-browser open "<URL>"
agent-browser snapshot -i
```

The `-i` snapshot returns interactive elements as refs (`@e1`, `@e2`, …). Use those refs — never guess CSS selectors when a ref exists.

## Step 2 — Exercise the path

Interact only as far as the verification requires. Prefer refs from the snapshot. Re-snapshot after any navigation or DOM change:

```bash
agent-browser click @e3
agent-browser fill @e5 "test@example.com"
agent-browser snapshot -i        # refs change after the page updates
```

Keep it minimal and deterministic. Do not log into real accounts or submit destructive actions unless the user explicitly asked.

## Step 3 — Collect evidence

```bash
agent-browser screenshot /tmp/web-verify.png
agent-browser errors                 # uncaught page errors
agent-browser console --clear        # console output (warns/errors)
agent-browser get url                # confirm you ended up where expected
```

## Step 4 — Report and clean up

```bash
agent-browser close --all
```

Then report:

- **PASS / FAIL** against the behavior from Step 0.
- What you observed: final URL, any console or page errors, screenshot path.
- If FAIL: the smallest reproducible observation (what you clicked, what happened vs. what should have).

## Hard rules

- **Read-only by default.** Navigate, snapshot, screenshot freely. Click/fill/submit only to the extent the verification needs.
- **Never invent selectors.** Use snapshot refs; re-snapshot after the page changes.
- **No real credentials, no destructive submits** unless the user explicitly authorized it.
- **Always `close --all`** at the end, even on failure.
- **Don't edit project files.** This command only observes; fixes belong to a separate step.
