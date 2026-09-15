#!/bin/bash
# Secret scanner — PreToolUse hook for Write / Edit / MultiEdit.
#
# Blocks the write if the new content contains a plausible credential:
# AWS keys, GitHub PATs, OpenAI / Anthropic / Stripe / Slack tokens, JWTs,
# private keys (PEM). Allowlists test fixtures, examples, docs, and node_modules.
#
# Exit codes:
#   0  → allow (no secret found, or path is allowlisted)
#   2  → block (secret found) — Claude Code surfaces the message to the user
#
# Override for emergencies: bypass with `git commit --no-verify` is irrelevant;
# this hook runs at WRITE time, not commit time. To temporarily disable, comment
# out the hook entry in ~/.claude/settings.json.

set -u

# Read tool input JSON from stdin (Claude Code hook protocol).
input=$(cat)

# Resolve the target file path. Different tools use different field names.
file=$(echo "$input" | jq -r '
  .tool_input.file_path
  // .tool_input.path
  // .tool_input.target_file
  // empty
' 2>/dev/null)

# No file path? Nothing to do.
[ -z "$file" ] && exit 0

# Allowlist: paths where credentials may legitimately appear (tests, fixtures,
# examples, docs, dependency directories). Adjust as needed per project.
# shellcheck disable=SC2221,SC2222
# Some patterns intentionally overlap (e.g. */tests/* overlaps *.example).
# All branches lead to the same `exit 0`, so order within the alternation is irrelevant.
case "$file" in
  *.test.*    | *.spec.*   | *-spec.*    | */__tests__/* | */__fixtures__/* \
  | */tests/* | *.example  | *.example.*   | */.env.example   \
  | */templates/*           | */node_modules/*               \
  | */dist/*  | */build/*  | */.next/*    | */.expo/*        \
  | *.md      | */CHANGELOG.md )
    exit 0 ;;
esac

# Extract the new content. Field varies by tool:
#   Write       → tool_input.content
#   Edit        → tool_input.new_string
#   MultiEdit   → array of edits, each with new_string (concat all)
content=$(echo "$input" | jq -r '
  .tool_input.content
  // .tool_input.new_string
  // ([.tool_input.edits[]?.new_string] | join("\n"))
  // empty
' 2>/dev/null)

[ -z "$content" ] && exit 0

# Pattern set. Tight enough to keep false positives low.
# Each pattern is well-known and documented by the corresponding vendor.
matches=$(echo "$content" | grep -nE \
  -e 'AKIA[0-9A-Z]{16}' \
  -e 'ASIA[0-9A-Z]{16}' \
  -e 'aws_secret_access_key[[:space:]]*=[[:space:]]*[A-Za-z0-9/+=]{40}' \
  -e 'ghp_[A-Za-z0-9]{36}' \
  -e 'gho_[A-Za-z0-9]{36}' \
  -e 'ghu_[A-Za-z0-9]{36}' \
  -e 'ghs_[A-Za-z0-9]{36}' \
  -e 'ghr_[A-Za-z0-9]{36}' \
  -e 'github_pat_[A-Za-z0-9_]{82}' \
  -e 'glpat-[A-Za-z0-9_-]{20}' \
  -e 'sk-[A-Za-z0-9]{40,}' \
  -e 'sk-ant-[A-Za-z0-9_-]{40,}' \
  -e 'sk-proj-[A-Za-z0-9_-]{40,}' \
  -e 'xox[baprs]-[A-Za-z0-9-]{20,}' \
  -e 'sk_live_[A-Za-z0-9]{24,}' \
  -e 'rk_live_[A-Za-z0-9]{24,}' \
  -e 'pk_live_[A-Za-z0-9]{24,}' \
  -e 'AIza[0-9A-Za-z_-]{35}' \
  -e 'eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}' \
  -e '-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY( BLOCK)?-----' \
  -e 'SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}' \
  -e 'mongodb(\+srv)?:\/\/[^:]+:[^@]+@' \
  -e 'postgres(ql)?:\/\/[^:]+:[^@]+@[^/]+' \
  | head -10)

# Nothing matched → allow.
[ -z "$matches" ] && exit 0

# Block. Print a JSON-formatted explanation that Claude Code surfaces inline,
# and exit 2 to abort the write.
jq -nc --arg file "$file" --arg matches "$matches" '
{
  systemMessage:
    "🚨 BLOCKED by secret-scanner: a credential pattern was detected in \($file).\n\nMatches:\n\($matches)\n\nFix: move the value to .env (gitignored) and reference it via process.env / import.meta.env. If this is a known false positive, temporarily comment out the secret-scanner hook in ~/.claude/settings.json — and please open an issue so the regex can be tightened.",
  decision: "block"
}'

exit 2
