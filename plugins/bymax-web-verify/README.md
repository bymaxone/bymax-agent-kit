# 🌐 Bymax Web Verify

> Real-browser verification **and assisted UI testing** for web apps. `/bymax-web-verify:test` brings the full stack up and walks a UI flow while you watch — in the Claude Desktop Browser pane (preview) when available, or the [`agent-browser`](https://github.com/vercel-labs/agent-browser) CLI (Vercel Labs) in a terminal. `/bymax-web-verify:verify` confirms a single change in a live browser. `/bymax-web-verify:record` captures a UI flow as reviewer-paced video evidence with a written walkthrough. One-command setup, plus a `SessionStart` reminder when the CLI is missing.

This plugin **depends on** `agent-browser` but never bundles it — the same "require, don't embed" approach as [`bymax-mobile`](../bymax-mobile) (which depends on Xcode / the Android SDK). `agent-browser` is `~93%` lighter on context than the Playwright MCP because it returns compact snapshot **refs** (`@e1`, `@e2`) instead of a full accessibility tree.

## Install

```bash
claude plugin marketplace add bymaxone/bymax-agent-kit
claude plugin install bymax-web-verify@bymax-agent-kit
```

Then, once (or after a fresh macOS install), let Claude install the CLI + browser:

```
/bymax-web-verify:setup
```

That's the whole "format-my-Mac" recovery path: install the plugin, run `/bymax-web-verify:setup`, done.

### Also in Codex

The same procedures ship in the Codex package as `bymax-web-setup`, `bymax-web-verify`, `bymax-web-test`, `bymax-web-record` (namespaced `bymax-codex:<name>`). Install it with `./scripts/install-codex.sh` from a checkout — see [CODEX.md](../../CODEX.md) for the entrypoints and the capability boundaries, which are not full parity.

## What you get

| Command                      | What it does                                                                                                                |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `/bymax-web-verify:setup`    | One-shot, idempotent install of the `agent-browser` CLI **and** its Chrome for Testing engine, finished by a live smoke test. |
| `/bymax-web-verify:verify`   | Drives a real browser to confirm a change works: opens a URL (default: your local dev server), exercises the path, and reports PASS/FAIL with screenshot + console/page errors. |
| `/bymax-web-verify:test`     | **Assisted UI testing, full stack up.** Discovers frontend/backend, reuses an already-running backend (or starts one and waits for health), opens the frontend in the **Claude Desktop Browser pane** (`.claude/launch.json` + preview) and walks a flow step by step while you watch — verifying each step via page state, console, network calls (2xx gate), and server logs. Falls back to `agent-browser` in a terminal. Args: free-text flow (default: smoke test), `browser`, `mobile`, `dark`. |
| `/bymax-web-verify:record`   | **Video evidence of a UI flow.** Uses the project's own Playwright with `video: 'on'` for one run, `slowMo` paced for human reviewers (timeout resized to match), per-run `--output` isolation, ffmpeg lead-in trim with a verified first frame, an `ffprobe` pacing gate, optional `--mp4`, and a mandatory plain-text walkthrough derived from the spec that ran (users named by role, never by address). Complements `verify` — one extra artifact, not a replacement. |

Plus a **`SessionStart` hook** that stays silent when the CLI is present, and — only when it's missing — nudges Claude to offer `/bymax-web-verify:setup`. It never installs anything unprompted and never blocks the session.

## Why a separate plugin (not a bundled copy)

- **Licensing & updates.** `agent-browser` is Apache-2.0 and ships its own version-matched skills (`core`, `dogfood`, `electron`, …). Pinning a copy would drift; depending on the global CLI keeps the skills in sync.
- **Optional weight.** Pure React Native projects (see `bymax-mobile`) don't need a browser. Web targets (the Next.js / Vite + React templates) do.

## Prerequisites

- **Node.js + npm** — `agent-browser` is a global npm package. `/bymax-web-verify:setup` checks for these first and points you at `nvm` if missing.
- **macOS / Linux** with enough disk for Chrome for Testing (downloaded by `agent-browser install`).
- A **running dev server** (or an explicit URL) when you run `/bymax-web-verify:verify`. It auto-probes ports `3000, 5173, 8080, 4321, 3001`.

## Manual install (if you skip the command)

```bash
npm install -g agent-browser
agent-browser install            # downloads Chrome for Testing
agent-browser --version          # verify
```

## Relationship to the rest of the toolkit

| Step                          | Plugin              |
| ----------------------------- | ------------------- |
| Plan the work                 | `bymax-workflow`    |
| Write code (TDD) + review     | `bymax-quality`     |
| Verify logic / tests pass     | `/bymax-workflow:verify` |
| **Verify it works in a browser** | **`bymax-web-verify`** |
| Run native mobile             | `bymax-mobile`      |

## License

MIT — see [root LICENSE](../../LICENSE). The `agent-browser` CLI itself is Apache-2.0 and is installed separately.
