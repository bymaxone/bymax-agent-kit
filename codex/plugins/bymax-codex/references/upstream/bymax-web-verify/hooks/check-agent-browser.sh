#!/bin/bash
# agent-browser presence check — SessionStart hook for bymax-web-verify.
#
# If the `agent-browser` CLI is installed, this is silent (no nagging).
# If it is missing, it injects a one-line note via additionalContext so Claude
# can proactively offer to run /bymax-web-verify:setup. It NEVER installs
# anything itself and NEVER blocks the session.
#
# Exit code is always 0 — this hook only informs, it never gates.

set -u

# CLI already installed → stay quiet.
if command -v agent-browser >/dev/null 2>&1; then
  exit 0
fi

note="bymax-web-verify: the 'agent-browser' CLI is not installed, so /bymax-web-verify:verify will not work yet. If the user wants real-browser verification, offer to run /bymax-web-verify:setup (installs the CLI + Chrome). Do not install it unprompted — just offer."

# Prefer the structured hook output when jq is available; fall back to plain
# stdout (Claude Code treats SessionStart stdout as added context too).
if command -v jq >/dev/null 2>&1; then
  jq -nc --arg ctx "$note" '
  {
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: $ctx
    }
  }'
else
  echo "$note"
fi

exit 0
