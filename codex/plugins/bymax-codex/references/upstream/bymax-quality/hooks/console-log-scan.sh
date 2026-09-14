#!/bin/bash
# Scans git-modified TS/JS files for console.log/warn/error/debug/info after a session.
# Outputs a systemMessage JSON only if matches are found.
# Exits silently and quickly if:
#   - not in a git repo
#   - no JS/TS files were modified
#   - no console statements found in those files

set -u

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

# Cheap exit: not inside a git working tree.
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Cheap exit: no modified files at all.
files=$(git diff --name-only HEAD 2>/dev/null | grep -E '\.(ts|tsx|js|jsx|cjs|mjs)$')
[ -z "$files" ] && exit 0

# Now do the (slightly more expensive) content scan.
matches=$(echo "$files" | xargs grep -nE 'console\.(log|warn|error|debug|info)' 2>/dev/null | head -30)
[ -z "$matches" ] && exit 0

# Format as systemMessage JSON. Prefer jq (faster, ubiquitous on macOS via brew);
# fall back to python3 only if jq is missing.
if command -v jq >/dev/null 2>&1; then
  printf '%s\n%s' "⚠️  console.log/warn/error found in modified files:" "$matches" \
    | jq -Rsc '{systemMessage: .}'
else
  python3 -c "
import json, sys
msg = '⚠️  console.log/warn/error found in modified files:\n' + sys.argv[1]
print(json.dumps({'systemMessage': msg}))
" "$matches"
fi
