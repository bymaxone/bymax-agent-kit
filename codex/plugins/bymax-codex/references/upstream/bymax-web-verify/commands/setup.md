---
description: One-shot installer for the agent-browser CLI plus its Chrome for Testing engine. Idempotent — safe to re-run. Designed as a portable backup step after a fresh macOS install. Verifies the install with a live smoke test and never asks the user a question. Triggers, "instalar agent-browser", "setup web verify", "preparar verificação web", "install browser cli", "configurar agent-browser", "/bymax-web-verify:setup".
---

# /bymax-web-verify:setup — install everything for real-browser verification

Install the `agent-browser` CLI and its Chrome engine so `/bymax-web-verify:verify` works. Execute every step **in sequence, without asking the user any questions**. Every step is idempotent — re-running is safe.

## Step 0 — Pre-flight: Node + npm

`agent-browser` ships as a global npm package, so Node and npm must exist first.

```bash
command -v node && command -v npm
```

If **either** is missing, abort with this message exactly and stop:

```
Node.js + npm not found. Install Node first, then re-run /bymax-web-verify:setup.
Recommended (macOS, version-managed):
  brew install nvm        # then follow brew's caveats to load nvm in ~/.zshrc
  nvm install --lts
Or download the LTS installer from https://nodejs.org.
```

Do not attempt to install Node yourself — it is a version-managed, user-level choice.

## Step 1 — Install / update the CLI

```bash
npm install -g agent-browser
```

If npm reports a global-prefix permission error (`EACCES`), do **not** retry with `sudo`. Instead print:

```
npm global install was denied (EACCES). Your npm global prefix needs write access.
Easiest fix is to use a version manager (nvm) so globals live in your home dir:
  https://github.com/nvm-sh/nvm
Then re-run /bymax-web-verify:setup.
```

## Step 2 — Install the browser engine

`agent-browser` drives Chrome for Testing, which it downloads on demand:

```bash
agent-browser install
```

This is idempotent — if Chrome is already present it is a no-op.

## Step 3 — Smoke test

Prove the whole chain works end-to-end:

```bash
agent-browser --version
agent-browser open "https://example.com" && agent-browser get title && agent-browser close --all
```

Expect the version to print, the title `Example Domain` to come back, and the session to close cleanly.

## Step 4 — Report

Tell the user, verbatim and concisely:

> ✅ agent-browser `<version>` is installed and the Chrome engine passed a live smoke test.
> Run `/bymax-web-verify:verify` to verify a web change in a real browser.

## Hard rules

- **Never use `sudo`.** Permission errors are a prefix/ownership problem — point at nvm instead.
- **Idempotent.** Every step is safe to run again; never delete an existing install.
- **Never ask the user.** Every decision is rule-based above.
- **Don't pin a version.** Always install the latest `agent-browser` so the bundled skills stay version-matched.
