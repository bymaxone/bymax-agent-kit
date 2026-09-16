#!/usr/bin/env bash
#
# Validate the marketplace + every plugin in this repo against whatever schema
# the installed Claude Code expects.
#
# Delegates the marketplace and plugin manifest checks to `claude plugin validate`
# so this stays aligned with upstream as the schema evolves. The remaining checks
# (executable bits, shellcheck, required project files) are still run here.
#
# Checks:
#   1. .claude-plugin/marketplace.json validates via `claude plugin validate`.
#   2. Every plugin under plugins/ validates via `claude plugin validate`.
#   3. Every shell hook is executable (chmod +x).
#   4. Every shell script passes shellcheck (if installed).
#   5. Every command / skill / agent Markdown file has valid YAML frontmatter.
#   6. Every required project-level file is present.
#
# Exit codes:
#   0 — all valid
#   1 — at least one validation error

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -t 1 ]]; then
  GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
else
  GREEN=''; YELLOW=''; RED=''; BLUE=''; NC=''
fi

ok()      { printf "${GREEN}  ✓${NC} %s\n" "$*"; }
warn()    { printf "${YELLOW}  ⚠${NC} %s\n" "$*"; }
fail()    { printf "${RED}  ✗${NC} %s\n" "$*" >&2; ((errors++)); }
section() { printf "${BLUE}==>${NC} %s\n" "$*"; }

errors=0

if ! command -v claude >/dev/null 2>&1; then
  printf "${RED}claude CLI is required but not installed.${NC}\n" >&2
  printf "Install: https://docs.claude.com/claude-code\n" >&2
  exit 1
fi

cd "${REPO_ROOT}" || { printf "Cannot cd into repo root: %s\n" "${REPO_ROOT}" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Validate the marketplace manifest
# ---------------------------------------------------------------------------

section "Validating marketplace manifest"

# `if ! cmd | sed` tests sed's status, not cmd's — so this gate could never
# fail, however broken the manifest was. PIPESTATUS keeps the indentation and
# still reads the validator's own exit code.
claude plugin validate "${REPO_ROOT}" 2>&1 | sed 's/^/  /'
[[ "${PIPESTATUS[0]}" -eq 0 ]] || fail "marketplace.json failed validation"

# ---------------------------------------------------------------------------
# 2. Validate every plugin
# ---------------------------------------------------------------------------

for plugin_dir in "${REPO_ROOT}"/plugins/*/; do
  [[ -d "${plugin_dir}" ]] || continue
  plugin_name="$(basename "${plugin_dir}")"

  section "Validating plugin: ${plugin_name}"

  claude plugin validate "${plugin_dir}" 2>&1 | sed 's/^/  /'
  [[ "${PIPESTATUS[0]}" -eq 0 ]] || fail "${plugin_name} failed validation"
done

# ---------------------------------------------------------------------------
# 3. Verify every shell script is executable
# ---------------------------------------------------------------------------

section "Verifying shell scripts are executable"

shell_scripts=()
for f in plugins/*/hooks/*.sh plugins/*/scripts/*.sh personal/*.sh scripts/*.sh; do
  [[ -f "${f}" ]] || continue
  shell_scripts+=("${f}")
  if [[ ! -x "${f}" ]]; then
    fail "${f} is not executable. Run: chmod +x ${f}"
  fi
done

if [[ "${#shell_scripts[@]}" -gt 0 ]]; then
  ok "Checked ${#shell_scripts[@]} shell scripts for +x"
else
  warn "No shell scripts found"
fi

# ---------------------------------------------------------------------------
# 4. Lint shell scripts with shellcheck (optional)
# ---------------------------------------------------------------------------

section "Linting shell scripts with shellcheck"

if command -v shellcheck >/dev/null 2>&1; then
  if [[ "${#shell_scripts[@]}" -gt 0 ]]; then
    # SC1091 — disabled because shellcheck cannot follow dynamic source paths in this repo.
    # SC2059 — disabled because we deliberately put color escapes in printf format strings.
    # SC2329 / SC2317 — the same situation under two names, because shellcheck
    #          renamed it: a function whose only caller is a `trap` cannot be
    #          followed, so 0.11 reports the FUNCTION as "never invoked" (SC2329)
    #          while 0.9 — the version on ubuntu-latest, and therefore in CI —
    #          reports each statement in its BODY as unreachable (SC2317). Both
    #          are listed because a contributor's local run and CI will not agree
    #          otherwise: this exclusion was added for 0.11, CI failed on 0.9, and
    #          neither version reproduces the other's code. Every other indirect
    #          call in this repo was rewritten as a direct one, so these cover trap
    #          handlers alone; a genuinely dead function still has to be caught in
    #          review.
    if shellcheck -e SC1091,SC2059,SC2317,SC2329 "${shell_scripts[@]}" 2>&1; then
      ok "All shell scripts pass shellcheck"
    else
      fail "shellcheck reported issues"
    fi
  fi
else
  warn "shellcheck not installed — skipping (install with: brew install shellcheck)"
fi

# ---------------------------------------------------------------------------
# 5. Verify command / skill / agent frontmatter is valid YAML
# ---------------------------------------------------------------------------
#
# `claude plugin validate` checks the JSON manifests, not the Markdown that
# defines the commands, skills and agents. That gap is not theoretical: an
# unquoted `description:` stops being a string the moment someone adds a
# colon-space to it (`Modes: quick | full`), and the manifests keep validating
# while the loader reads whatever survived. Catch it here instead.

section "Verifying command / skill / agent frontmatter"

# This gate fails closed. A missing interpreter or a missing PyYAML is an
# environment problem, not a clean repository, and printing "all validations
# passed" over a check that never ran is the failure mode the gate exists to
# prevent. shellcheck above is genuinely optional; frontmatter validity is not.
if command -v python3 >/dev/null 2>&1; then
  # Capture the status via `||` rather than reading $? in a conditional, which
  # ShellCheck reports as SC2181 and which any command in between would clobber.
  frontmatter_status=0
  frontmatter_output="$(python3 "${SCRIPT_DIR}/lib/check-frontmatter.py" 2>&1)" \
    || frontmatter_status=$?
  if [[ "${frontmatter_status}" -eq 0 ]]; then
    ok "${frontmatter_output}"
  else
    # Printed unadorned: `ok`/`fail` format a single line, so a multi-line
    # payload would lose the marker and the indentation on every line but one.
    printf '%s\n' "${frontmatter_output}" >&2
    fail "frontmatter validation failed"
  fi
else
  fail "python3 is required for the frontmatter check but is not installed"
fi

# ---------------------------------------------------------------------------
# 6. Verify required project-level files exist
# ---------------------------------------------------------------------------

section "Verifying required project files"

REQUIRED_FILES=(
  "README.md"
  "INSTALL.md"
  "TESTING.md"
  "LICENSE"
  "CONTRIBUTING.md"
  "CHANGELOG.md"
  "SECURITY.md"
  "CODE_OF_CONDUCT.md"
  ".gitignore"
  ".claude-plugin/marketplace.json"
  "templates/CLAUDE.md"
  "templates/AGENTS.starter.md"
  "templates/README.md"
  "personal/settings.template.json"
  "personal/mcp.template.json"
)

for f in "${REQUIRED_FILES[@]}"; do
  if [[ -f "${f}" ]]; then
    ok "${f} exists"
  else
    fail "${f} is missing"
  fi
done

section "Testing bounded review and push guard behavior"
python3 -m unittest discover -s scripts/tests -v || fail "review flow regression tests failed"

# ---------------------------------------------------------------------------
# 7. Summary
# ---------------------------------------------------------------------------

echo
if [[ "${errors}" -eq 0 ]]; then
  printf "${GREEN}✓ All validations passed.${NC}\n"
  exit 0
else
  printf "${RED}✗ ${errors} validation error(s) found.${NC}\n" >&2
  exit 1
fi
