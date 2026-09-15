#!/bin/bash
# qa-tools — report which optional external security tools are available.
#
# The bymax-qa deterministic layer uses these when present and degrades to a
# status line when absent — none is bundled or required (the "require, don't
# embed" rule). This script prints a table the audit skill reads to decide what
# to run; it installs nothing and probes no host.
#
# Usage:   bash qa-tools.sh
# Output:  one line per tool — "<tool>  <present|absent>  <version|->  <purpose>"
#
# Exit code is always 0 — this is discovery, not a gate.

set -u

report() {
  # $1 = command, $2 = purpose, $3 = version flag (default --version)
  local cmd="$1" purpose="$2" flag="${3:---version}" ver="-"
  if command -v "$cmd" >/dev/null 2>&1; then
    ver=$("$cmd" "$flag" 2>&1 | head -1 | tr -d '\n' | cut -c1-40)
    printf '%-14s present  %-40s %s\n' "$cmd" "$ver" "$purpose"
  else
    printf '%-14s absent   %-40s %s\n' "$cmd" "-" "$purpose"
  fi
}

echo "bymax-qa external tool inventory"
echo "--------------------------------"
report osv-scanner  "dependency advisories (SCA)"
report semgrep      "SAST rulesets (p/owasp-top-ten, p/jwt, ...)"
report gitleaks     "secrets in the working tree"
report trufflehog   "secrets in git history (verified)"
report trivy        "SCA + IaC/Dockerfile misconfig + secrets"
report madge        "JS/TS import cycles"           "--version"
report depcruise    "dependency-cruiser layering rules" "--version"
report sqlmap       "active SQLi confirmation (scope-gated)" "--version"
report nuclei       "DAST templates (scope-gated)"
report zap          "OWASP ZAP baseline/API scan (scope-gated)" "-version"
report jwt_tool     "JWT alg/confusion/kid attacks"  "--help"
report axe          "accessibility (WCAG) checks"    "--version"
report lighthouse   "Core Web Vitals / perf"         "--version"
report gh           "GitHub issues + advisories"     "--version"

exit 0
