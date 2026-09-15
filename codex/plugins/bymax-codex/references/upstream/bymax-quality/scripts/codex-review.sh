#!/usr/bin/env bash
#
# codex-review.sh — optional independent second review via the Codex CLI.
#
# Runs a review against a scope the caller resolved and prints it verbatim. It is
# a standalone SECOND OPINION. Bounded push campaigns use review_flow.py instead.
#
# Two modes, two different questions:
#   standard     `codex exec review` — is this change correct? Needs only the
#                `codex` binary.
#   adversarial  the openai-codex plugin's `adversarial-review` — is this the
#                right approach at all? Challenges design, tradeoffs and
#                assumptions rather than hunting implementation defects.
#
# The adversarial mode drives the openai-codex plugin's own runtime
# (`codex-companion.mjs`) instead of reimplementing it. That plugin marks
# `/codex:adversarial-review` as `disable-model-invocation: true`, so the slash
# command cannot be called from a skill — but the runtime underneath it is a
# plain Node script that locates its own prompts via `import.meta.url`, so it
# runs fine when invoked by absolute path. Reusing it means the adversarial
# prompt keeps tracking upstream instead of drifting in a copy here.
#
# On whether that is a bypass of upstream's boundary — answered here rather than
# left to be re-argued each round:
#   - `disable-model-invocation` gates the slash-command WRAPPER. The runtime
#     carries no such flag, and upstream's own `codex-rescue` subagent invokes
#     that same runtime (`task`) from an agent.
#   - What the flag protects is consent: a model must not start a billed Codex
#     run on its own. Invoking the calling command does not supply that consent —
#     no Bymax command sets `disable-model-invocation`, and commands and skills
#     across the toolkit invoke the review command from a model. So the caller
#     must pass `--mode adversarial` only when the user asked for it with the
#     `--adversarial` flag, which is off by default. Anything that makes this
#     mode reachable without that flag removes the only consent this
#     integration has.
#   - What the flag cannot express is "this runtime is internal": that is the
#     version allowlist below, not the wrapper.
# If upstream publishes a supported invocation surface for the adversarial
# review, prefer it and delete this mode's direct call.
#
# The two modes are meant to be launched as two concurrent background shells by
# the caller, so they cost wall-clock only once.
#
# Contract (never violated):
#   - ALWAYS exits 0. A missing CLI, an expired session, a rate limit, a
#     timeout or a parse failure are all reported as status lines, never as
#     failures that could stall /bymax-quality:code-review.
#   - NEVER prompts, NEVER installs anything, NEVER writes to the repo. In
#     standard mode this script pins the sandbox and approval policy per
#     invocation (`-c sandbox_mode=read-only -c approval_policy=never`), so it
#     holds regardless of the user's Codex config. In adversarial mode the
#     guarantee is upstream's, not this script's: the plugin runtime starts its
#     review thread with a hardcoded `sandbox: "read-only"` and an
#     `approvalPolicy` defaulting to `"never"` (lib/codex.mjs), and the app-server
#     protocol takes no `-c` overrides for this script to add. Verified against
#     openai-codex 1.0.6 — a reader auditing this contract must re-check it
#     against the version `find_companion` actually resolves.
#   - First stdout line is always `CODEX_STATUS: <status>`, so the caller can
#     branch deterministically without interpreting prose.
#
# Statuses:
#   ok                 review ran over exactly the requested scope; report follows
#   ok-unpinned        review ran, but not over exactly the requested scope —
#                      adversarial past the runtime's inline-diff limit or on a
#                      dirty tree with a branch target, standard on a branch
#                      target with untracked files. Findings are reportable;
#                      silence is not evidence. A CODEX_SCOPE line says why.
#   absent             codex CLI is not installed
#   unauthenticated    no active Codex session (logged out or expired)
#   bad-invocation     a flag without its value, an unknown flag or --mode:
#                      the caller's command line is wrong, not the scope
#   unsupported-target the caller's scope cannot be expressed as a codex flag
#   timeout            the run exceeded --budget
#   failed             codex exited non-zero, or produced no usable output
#   adversarial-absent --mode adversarial, and the runtime could not be used: node
#                      absent, the plugin missing, disabled or incomplete, the
#                      plugin list unreadable, a BYMAX_CODEX_COMPANION path that
#                      does not exist, or the installed version not on
#                      COMPANION_VERIFIED_VERSIONS. The second line carries what
#                      was detected — except that a listing that will not parse
#                      is reported as the plugin not being present.
#                      Only this mode is affected.
#
# Usage:
#   codex-review.sh [--mode standard|adversarial] --target uncommitted [--budget <sec>]
#   codex-review.sh [--mode standard|adversarial] --target base --ref <branch> [--budget <sec>]
#   codex-review.sh --target commit --ref <sha> [--budget <sec>]   # standard only
#
# The adversarial runtime is resolved through `claude plugin list --json` — the
# installed, enabled plugin with id `codex@openai-codex`, and nothing else. Set
# BYMAX_CODEX_COMPANION to an explicit codex-companion.mjs path to override that
# (a project-local install, or a pinned version); the override is trusted as the
# user's own decision.
#
# Notes for the caller:
#   - `codex exec review` rejects custom instructions whenever a scope flag is
#     present, so this review is unsteered by design. That independence is the
#     point: it is what makes the second opinion worth having.
#   - The output is NOT deterministic. Two runs over the same commit return
#     overlapping but different findings. Treat it as sampling, not as a gate.

set -u

# Every number this script reasons about, named once.
DEFAULT_BUDGET=300          # seconds, when --budget is absent or unusable
MIN_BUDGET=30               # below this a run is killed before it can say anything
MAX_BUDGET=3600             # above this bash 3.2's `[` can no longer compare reliably
POLL_INTERVAL=2             # seconds between liveness checks of the review process
KILL_GRACE=2                # seconds between TERM and KILL at budget expiry
CANCEL_DEADLINE=15          # seconds the runtime's `cancel` may take before it is abandoned
REASON_MAX_CHARS=300        # tail of stderr quoted in a `failed` status line
# The plugin runtime inlines the diff in its prompt only under these limits
# (DEFAULT_INLINE_DIFF_MAX_FILES / _BYTES in its lib/git.mjs, openai-codex 1.0.6);
# past them the reviewer collects its own scope.
RUNTIME_INLINE_MAX_FILES=2
RUNTIME_INLINE_MAX_BYTES=262144

BUDGET="${DEFAULT_BUDGET}"
TARGET=""
REF=""
MODE="standard"

emit() { printf '%s\n' "$*"; }
# Tracks whether a status line has been written, so the exit trap can tell a
# normal completion from a run torn down by a signal before it reported anything.
status_emitted=0
status_only() { status_emitted=1; emit "CODEX_STATUS: $1"; [ "${2:-}" = "" ] || emit "$2"; exit 0; }

# Teardown is armed HERE, before a single gate runs — not next to the launch.
# Measured: a TERM that arrived while the availability gates and the scope
# measurement were still running hit a script with no trap yet, which died
# 143 with no status line. Everything the trap touches is guarded for "not
# set yet": `stop_review` and `workdir` only exist once the run is prepared,
# and `cleanup` must be correct at every point of the script's life.
workdir=""
cancel_failed=0
companion=""
companion_error=""
review_session=""
review_rc=1
cancel_remedy() {
  printf 'and the cancel FAILED, so the Codex run may still be billing. Stop it with: CODEX_COMPANION_SESSION_ID=%s node "%s" cancel' "${review_session}" "${companion}"
}
cleanup() {
  # A second TERM/INT while this handler waits on the cancel deadline would
  # run `exit 0` INSIDE the EXIT trap, which bash does not re-enter: no status
  # line, no group kill, no workdir removal. Ignore further signals from here.
  trap '' TERM INT
  if declare -F stop_review >/dev/null 2>&1; then
    stop_review
  fi
  if [ "${status_emitted}" -eq 0 ]; then
    status_emitted=1
    emit "CODEX_STATUS: failed"
    if [ "${cancel_failed}" -eq 1 ]; then
      emit "interrupted — $(cancel_remedy)"
    else
      emit "interrupted before the review completed"
    fi
  fi
  [ -n "${workdir}" ] && rm -rf "${workdir}"
  # `exit 0`, not `return 0`: a returning EXIT trap leaves bash's own status
  # alone, so any exit path that is not `status_only` — an unbound variable
  # introduced by a later edit, a SIGPIPE on `emit` — would hand the caller a
  # non-zero shell while the header promises this script always exits 0.
  exit 0
}
trap cleanup EXIT
trap 'exit 0' TERM INT

# `--flag=value` is rewritten to `--flag value` up front, so a single `case`
# handles both spellings. Two parallel copies of the flag list once let the
# equals form fall through to a silent `shift` — and publish a standard review
# under the adversarial label. Anything unrecognised is an invocation error,
# reported as such: it is not a scope problem, and calling it one sends the
# reader to the wrong table.
args=()
for arg in "$@"; do
  case "${arg}" in
    --target=*|--ref=*|--budget=*|--mode=*) args+=("${arg%%=*}" "${arg#*=}") ;;
    *) args+=("${arg}") ;;
  esac
done
# `${args[@]+"${args[@]}"}`: an empty array under `set -u` is "unbound" in bash
# 3.2, and a bare `set -- "${args[@]}"` with no arguments aborted before any
# status line was written.
set -- ${args[@]+"${args[@]}"}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target|--ref|--budget|--mode)
      [ "$#" -ge 2 ] || status_only "bad-invocation" "$1 requires a value"
      case "$1" in
        --target) TARGET="$2" ;;
        --ref)    REF="$2" ;;
        --budget) BUDGET="$2" ;;
        --mode)   MODE="$2" ;;
      esac
      shift 2
      ;;
    *) status_only "bad-invocation" "unknown argument '$1'" ;;
  esac
done

# One to four digits, then a range check. The digit cap is not cosmetic:
# `/bin/bash` here is 3.2, whose `[` fails with status 2 above 64 bits — a
# status `if` reads as false — so a range check ALONE lets a millisecond value
# through and the timeout branch then never fires. `10#` strips leading zeros.
budget_note=""
if [[ "${BUDGET}" =~ ^[0-9]{1,4}$ ]]; then
  requested_budget=$((10#${BUDGET}))
  BUDGET="${requested_budget}"
  [ "${BUDGET}" -ge "${MIN_BUDGET}" ] || BUDGET="${MIN_BUDGET}"
  [ "${BUDGET}" -le "${MAX_BUDGET}" ] || BUDGET="${MAX_BUDGET}"
  # Clamped, not reset: a user who asked for 5400 after a 3600 timeout should
  # get the ceiling, not a third of it — and be told which.
  [ "${BUDGET}" -eq "${requested_budget}" ] \
    || budget_note=" (budget clamped from ${requested_budget} to ${BUDGET}; the range is ${MIN_BUDGET}-${MAX_BUDGET})"
else
  # A five-digit or non-numeric value is either milliseconds or a typo. Either
  # way the default applies, and the reader is told on the line that matters.
  [ -z "${BUDGET}" ] || budget_note=" (budget '${BUDGET}' is not 1-4 digits; using ${DEFAULT_BUDGET})"
  BUDGET="${DEFAULT_BUDGET}"
fi

case "${MODE}" in
  standard|adversarial) ;;
  *) status_only "bad-invocation" "unknown --mode '${MODE}'" ;;
esac

# --- Build the scope flags for the chosen backend --------------------------
# `codex exec review` understands exactly three scopes; the plugin runtime
# understands two and has no per-commit form. Anything else the calling skill
# supports (a single file, a ref range not ending at HEAD) has no equivalent,
# and is reported rather than silently reviewed as the wrong thing.
codex_args=()
if [ "${MODE}" = "standard" ]; then
  case "${TARGET}" in
    uncommitted) codex_args=(--uncommitted) ;;
    base)   [ -n "${REF}" ] || status_only "unsupported-target" "--target base requires --ref"
            codex_args=(--base "${REF}") ;;
    commit) [ -n "${REF}" ] || status_only "unsupported-target" "--target commit requires --ref"
            codex_args=(--commit "${REF}") ;;
    *) status_only "unsupported-target" "no codex scope for target '${TARGET}'" ;;
  esac
else
  case "${TARGET}" in
    uncommitted) codex_args=(--scope working-tree) ;;
    base)   [ -n "${REF}" ] || status_only "unsupported-target" "--target base requires --ref"
            codex_args=(--scope branch --base "${REF}") ;;
    # The plugin runtime reviews a working tree or a branch, never a single
    # commit. Reporting that beats reviewing the wrong diff under a label the
    # reader will trust.
    *) status_only "unsupported-target" "adversarial mode has no scope for target '${TARGET}'" ;;
  esac
fi

# Validate the ref before spending a Codex run on it. Given an unresolvable ref,
# `codex exec review` exits 0 and returns "Commit X does not exist" as its final
# message — which would otherwise be reported as a successful review.
if [ -n "${REF}" ] && ! git rev-parse --verify -q "${REF}" >/dev/null 2>&1; then
  hint=""; git rev-parse --verify -q "origin/${REF}" >/dev/null 2>&1 && hint=" — origin/${REF} exists; a bare name needs a local branch"
  status_only "unsupported-target" "ref '${REF}' does not resolve in this repository${hint}"
fi
# Resolving is not enough for a base: an orphan branch has no merge base with
# HEAD. The adversarial runtime fails cleanly on that; `codex exec review
# --base` falls back to a prompt that finds a scope by itself and reports `ok`
# over whatever it chose.
# (`merge-base` has no `-q`; an unknown option exits 129, which read as "no
# history" and refused every valid base — the positive case must be tested too.)
if [ "${TARGET}" = "base" ] && ! git merge-base "${REF}" HEAD >/dev/null 2>&1; then
  status_only "unsupported-target" "ref '${REF}' shares no history with HEAD — no diff to review"
fi
# An empty range bills a reviewer over nothing and is counted as a clean second
# opinion. How empty it is depends on the backend: the adversarial runtime reads
# mergeBase..HEAD and nothing else, so the range alone decides; `codex exec
# review --base` diffs that base against the WORKING TREE, so uncommitted work
# still gives the standard reviewer something real to read.
if [ "${TARGET}" = "base" ] && git diff --quiet "${REF}...HEAD" 2>/dev/null; then
  if [ "${MODE}" = "adversarial" ]; then
    status_only "unsupported-target" "'${REF}...HEAD' is empty, and the adversarial runtime reviews only that range — nothing to review"
  fi
  # Only TRACKED edits rescue an empty range for the standard reviewer: the
  # merge-base-vs-working-tree diff `--base` builds does not contain untracked
  # files, so a tree whose only change is a new file leaves it with nothing.
  if git diff --quiet HEAD 2>/dev/null; then
    status_only "unsupported-target" "'${REF}...HEAD' is empty and no tracked file is modified — nothing for \`--base\` to review"
  fi
fi
# A clean tree is not a review either: both backends will bill a full turn over
# "(none)" sections and return a verdict on nothing.
if [ "${TARGET}" = "uncommitted" ] \
  && git diff --quiet HEAD 2>/dev/null \
  && [ -z "$(git ls-files --others --exclude-standard -- "$(git rev-parse --show-toplevel)" 2>/dev/null)" ]; then
  status_only "unsupported-target" "the working tree is clean — nothing to review; use --target base"
fi

# --- Locate the plugin runtime (adversarial mode only) ---------------------
# Resolved through `claude plugin list`, never by searching the filesystem. The
# runtime is executed with `node` under the user's own permissions — the
# read-only sandbox applies to the Codex thread it starts, not to the Node
# process itself — so whatever this function returns runs with full access to
# the repository and the user's credentials. That makes the selection a trust
# decision, and the only trustworthy answer is "the plugin the user installed
# and enabled", by its exact id. Never widen this to a glob over the plugin
# cache or a fallback to marketplace checkouts: any marketplace shipping a
# plugin named `codex`, installed or not, would then be executed merely by
# running a code review.
#
# `CLAUDE_PLUGIN_ROOT` cannot help here — it points at THIS plugin.
COMPANION_PLUGIN_ID="codex@openai-codex"

# The runtime contract this script depends on — read-only sandbox pinned per
# thread, `approvalPolicy: never`, the detached broker and its `cancel`,
# CODEX_COMPANION_SESSION_ID scoping, the `--scope`/`--base` flags, and a
# `Verdict:` line in the output — is UNDOCUMENTED. It was verified by reading
# openai-codex 1.0.6. A routine plugin update can change any of it, and the
# failure modes are the bad kind: a run that keeps billing past its budget, or
# a Node process with the user's permissions whose read-only guarantee no
# longer holds. So only versions that were actually read are accepted — an
# exact allowlist, not a range. An earlier draft admitted `1.0.*` while its own
# comment said 1.0.6 was the only version inspected, which is a range hoped
# compatible, not a contract verified. Add a version here only after re-reading
# lib/codex.mjs, lib/broker-lifecycle.mjs, lib/job-control.mjs and
# lib/render.mjs in that version; BYMAX_CODEX_COMPANION_ALLOW_UNVERIFIED=1 runs
# any other version anyway, as the user's own explicit decision.
COMPANION_VERIFIED_VERSIONS="1.0.6"
companion_version=""
companion_record=""

find_companion() {
  # An explicit override is the user's own decision, made in their environment,
  # and is honoured as such. It is the one path that bypasses the identity check.
  if [ -n "${BYMAX_CODEX_COMPANION:-}" ]; then
    [ -f "${BYMAX_CODEX_COMPANION}" ] || { companion_error="BYMAX_CODEX_COMPANION points at a file that does not exist: ${BYMAX_CODEX_COMPANION}"; return 1; }
    # No version to report for an override: it is trusted as-is.
    printf '%s\t%s' "override" "${BYMAX_CODEX_COMPANION}"
    return 0
  fi

  command -v claude >/dev/null 2>&1 || { companion_error="the claude CLI is not on PATH, so the installed-plugin list cannot be read"; return 1; }
  local listing install_path
  listing="$(claude plugin list --json 2>/dev/null)" || { companion_error="'claude plugin list --json' failed"; return 1; }
  [ -n "${listing}" ] || { companion_error="'claude plugin list --json' returned nothing"; return 1; }

  # Exact id AND enabled. A disabled plugin is one the user turned off; running
  # its code anyway would override that choice. Version and path come out as
  # one tab-separated line so the two cannot disagree.
  local record
  if command -v jq >/dev/null 2>&1; then
    record="$(printf '%s' "${listing}" | jq -r --arg id "${COMPANION_PLUGIN_ID}" '
      map(select(.id == $id and .enabled == true)) | .[0]
      | select(. != null) | "\(.version // "")\t\(.installPath // "")"' 2>/dev/null)"
  elif command -v python3 >/dev/null 2>&1; then
    record="$(printf '%s' "${listing}" | python3 -c '
import json, sys
wanted = sys.argv[1]
try:
    plugins = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
for plugin in plugins if isinstance(plugins, list) else []:
    if plugin.get("id") == wanted and plugin.get("enabled") is True:
        print(str(plugin.get("version") or "") + "\t" + str(plugin.get("installPath") or ""))
        break
' "${COMPANION_PLUGIN_ID}" 2>/dev/null)"
  else
    companion_error="neither jq nor python3 is available to read the plugin list"; return 1
  fi

  [ -n "${record}" ] || { companion_error="openai-codex plugin not found among installed, enabled plugins — install it to enable the adversarial review"; return 1; }
  install_path="${record#*	}"
  [ -n "${install_path}" ] || { companion_error="the openai-codex plugin record carries no installPath"; return 1; }
  [ -f "${install_path}/scripts/codex-companion.mjs" ] || { companion_error="${install_path}/scripts/codex-companion.mjs does not exist — reinstall the openai-codex plugin"; return 1; }
  # Printed as "<version><TAB><path>": this runs in a command substitution, so
  # a variable set here would not survive — the caller splits the one line.
  printf '%s\t%s' "${record%%	*}" "${install_path}/scripts/codex-companion.mjs"
}

# --- Availability gates (both free: no network, no tokens) -----------------
# Both modes need the same binary and the same credential store, so these gates
# apply to the plugin runtime as they do to a direct call. They do NOT reach the
# same execution path: standard runs `codex exec`, adversarial drives the
# app-server protocol through the runtime's broker.
#
# They run BEFORE the adversarial-only plugin check on purpose. The plugin is
# the shallower prerequisite: checking it first would report `adversarial-absent`
# on a machine that has neither, sending the user to install a plugin when what
# they actually lack is the CLI or a session — the remediation Step 5.5 prints
# for that status explicitly says `codex-setup` will not help.
command -v codex >/dev/null 2>&1 || status_only "absent"

# `codex login status` is a local read of the credential store: exit 0 when a
# session is active, exit 1 ("Not logged in") otherwise. Measured at ~13 ms.
# This is what makes an expired session cost nothing to detect.
# `codex exec` also honours CODEX_API_KEY (sent as a bearer token), which the
# on-disk credential store knows nothing about — a headless machine exporting it
# would otherwise be sent to an interactive `codex login` it does not need.
[ -n "${CODEX_API_KEY:-}" ] || codex login status >/dev/null 2>&1 || status_only "unauthenticated"

if [ "${MODE}" = "adversarial" ]; then
  command -v node >/dev/null 2>&1 \
    || status_only "adversarial-absent" "node is required by the openai-codex plugin runtime"
  # find_companion runs in a command substitution, so its error text travels
  # through a file rather than a variable.
  companion_error_file="$(mktemp 2>/dev/null)" || status_only "failed" "cannot create a temp file"
  companion_record="$(find_companion 2>/dev/null; printf '%s' "${companion_error}" >"${companion_error_file}")"
  companion_error="$(cat "${companion_error_file}" 2>/dev/null)"; rm -f "${companion_error_file}"
  [ -n "${companion_record}" ] || status_only "adversarial-absent" "${companion_error:-openai-codex plugin not found — install it to enable the adversarial review}"
  companion_version="${companion_record%%	*}"
  companion="${companion_record#*	}"
  # Two different questions. `version_verified` — may this runtime run at all?
  # An explicit override says yes, because the user chose it. `limits_known` —
  # do 1.0.6's inline-diff constants describe it? Only a version on the list
  # answers that, and an override never does: the user pointed at a file, not at
  # a version whose lib/git.mjs anyone read.
  version_verified=0
  limits_known=0
  [ "${companion_version}" = "override" ] && version_verified=1
  for verified in ${COMPANION_VERIFIED_VERSIONS}; do
    [ "${companion_version}" = "${verified}" ] && { version_verified=1; limits_known=1; }
  done
  if [ "${version_verified}" -eq 0 ] && [ "${BYMAX_CODEX_COMPANION_ALLOW_UNVERIFIED:-0}" != "1" ]; then
    status_only "adversarial-absent" \
      "openai-codex ${companion_version:-?} is not a verified version (verified: ${COMPANION_VERIFIED_VERSIONS}) — the runtime contract this script relies on is undocumented and was read in those versions only; set BYMAX_CODEX_COMPANION_ALLOW_UNVERIFIED=1 to run it anyway"
  fi
fi

# --- Will the reviewer see exactly this scope? -------------------------------
# Decided HERE, before launch, against the tree the backend is about to read —
# not after the review, against a tree that may have moved in the meantime.
#
# Adversarial: past the runtime's inline limits it stops putting the diff in
# the prompt and tells the agent to collect its own with git commands, so the
# validated scope flags bind nothing; and on a branch target it resolves
# mergeBase..HEAD, dropping every uncommitted file. Standard:
# `--uncommitted` reviews staged, unstaged and untracked changes (its --help),
# an exact match for Step 1; `--base` diffs the merge-base against the WORKING
# TREE, so tracked uncommitted hunks are in but untracked files are not — a
# different scope from the committed range Step 1 resolves for a branch.
#
# Measurements mirror the runtime's own commands (staged and unstaged diffed
# separately, `--binary`); untracked contents are not in the byte count
# because they are not in the runtime's either. The file count is checked
# first because it alone usually decides, and the byte diff is the expensive
# one. A git command that fails makes the scope unpinned rather than pinned:
# stderr is discarded and `grep -c` of nothing is 0, which would otherwise
# read as "small change, inlined".
scope_unpinned=0
scope_reason=""
diff_flags=(--binary --no-ext-diff --submodule=diff)

# exceeds_inline_limits <kind> — <kind> is `uncommitted` or `base`.
# Each measurement is a named function that receives the ref as a quoted
# argument. Never `eval` a string that carries the ref: git accepts a branch
# named `$(printf pwn)`, `rev-parse` only proves it resolves, and an eval'd
# measurement would run that payload with the user's permissions — before any
# Codex gate, so without Codex even installed.
list_changed_uncommitted() {
  git diff --cached --name-only && git diff --name-only && list_untracked
}
diff_uncommitted() { git diff --cached "${diff_flags[@]}" && git diff "${diff_flags[@]}"; }
list_changed_base()  { git diff --name-only "$1...HEAD"; }
diff_base()          { git diff "${diff_flags[@]}" "$1...HEAD"; }

# changed_files <kind> / changed_bytes <kind>: the two measurements, each
# dispatching on the kind with a direct call — shellcheck cannot follow a
# function name held in a variable and reports every such function as unused.
changed_files() {
  case "$1" in
    uncommitted) list_changed_uncommitted ;;
    base)        list_changed_base "${REF}" ;;
  esac
}
changed_bytes() {
  case "$1" in
    uncommitted) diff_uncommitted ;;
    base)        diff_base "${REF}" ;;
  esac
}

# Sets scope_reason only when nothing has set it yet: the first reason recorded
# is the most fundamental one. An unverified runtime whose limits are unknown
# must not have that fact overwritten by a measurement against 1.0.6's numbers —
# the reader would be handed a figure the script had just said it cannot trust.
set_scope_reason() { [ -n "${scope_reason}" ] || scope_reason="$1"; }

exceeds_inline_limits() {
  local kind="$1" files bytes
  # A git failure is an unmeasured scope, and an unmeasured scope is unpinned:
  # stderr is discarded and `grep -c` of nothing is 0, which would otherwise
  # read as "small change, inlined".
  if ! files="$(changed_files "${kind}" 2>/dev/null | sort -u | grep -c .; exit "${PIPESTATUS[0]}")"; then
    set_scope_reason "${SCOPE_UNMEASURED}"; return 0
  fi
  if [ "${files}" -gt "${RUNTIME_INLINE_MAX_FILES}" ]; then
    set_scope_reason "${files} changed files exceed the runtime's inline limit of ${RUNTIME_INLINE_MAX_FILES}"; return 0
  fi
  if ! bytes="$(changed_bytes "${kind}" 2>/dev/null | wc -c; exit "${PIPESTATUS[0]}")"; then
    set_scope_reason "${SCOPE_UNMEASURED}"; return 0
  fi
  bytes="${bytes//[[:space:]]/}"
  if [ "${bytes}" -gt "${RUNTIME_INLINE_MAX_BYTES}" ]; then
    set_scope_reason "${bytes} diff bytes exceed the runtime's inline limit of ${RUNTIME_INLINE_MAX_BYTES}"; return 0
  fi
  return 1
}

# Prints the count; exits non-zero when git itself failed (grep's "no match"
# status is discarded on purpose — zero untracked files is a valid answer).
SCOPE_UNMEASURED="the scope could not be measured (git failed)"
# Repo-wide, like every other measurement here. Bare `git ls-files --others` is
# scoped to the CURRENT DIRECTORY, so from a subdirectory it reports no untracked
# files while `git diff --quiet HEAD` still answers for the whole repository —
# a clean-tree verdict on a tree that is not clean.
# CALL THESE ONLY INSIDE `$( … )`. The trailing `exit` propagates git's own
# status out of the pipeline — `grep -c` returning 1 for "no matches" is a valid
# answer, git failing is not — and inside a command substitution that exits the
# subshell. Called anywhere else it would end the script mid-review, and the EXIT
# trap would then publish `failed` for a run that was fine.
list_untracked() { git ls-files --others --exclude-standard -- "$(git rev-parse --show-toplevel)"; }
count_untracked() { list_untracked 2>/dev/null | grep -c .; exit "${PIPESTATUS[0]}"; }
count_tracked_dirty() { git diff --name-only HEAD 2>/dev/null | grep -c .; exit "${PIPESTATUS[0]}"; }

# The inline limits are 1.0.6's numbers. A runtime admitted by the override or
# by ALLOW_UNVERIFIED may use different ones, so its scope cannot be predicted:
# report it unpinned rather than `ok` on a guess.
# `limits_known` was computed once at the availability gate, alongside — and
# deliberately apart from — `version_verified`: an override may run but brings no
# version whose constants anyone checked.
if [ "${MODE}" = "adversarial" ] && [ "${limits_known:-0}" -eq 0 ]; then
  scope_unpinned=1
  scope_reason="runtime '${companion_version}' is not one whose inline limits were read, so whether the diff was inlined is unknown"
fi

case "${MODE}:${TARGET}" in
  adversarial:uncommitted)
    exceeds_inline_limits uncommitted && scope_unpinned=1 ;;
  adversarial:base)
    # A dirty tree is not a scope mismatch here: `--target base` asks for the
    # committed range, the runtime reviews exactly `mergeBase..HEAD`, and
    # uncommitted files were never in scope. Only the inline limits can unpin
    # this scope, so that measurement always runs.
    #
    # `standard:base` is the opposite case and keeps its dirty-tree check:
    # `codex exec review --base` diffs the merge base against the WORKING TREE,
    # so tracked uncommitted edits are reviewed beyond the requested range.
    exceeds_inline_limits base && scope_unpinned=1 ;;
  standard:base)
    # `codex exec review --base` diffs the merge-base against the WORKING TREE:
    # tracked uncommitted hunks are reviewed although the requested scope is the
    # committed range, and untracked files are not reviewed at all.
    if ! untracked="$(count_untracked)" || ! tracked_dirty="$(count_tracked_dirty)"; then
      scope_unpinned=1; set_scope_reason "${SCOPE_UNMEASURED}"
    elif [ "${tracked_dirty:-0}" -gt 0 ]; then
      scope_unpinned=1
      set_scope_reason "${tracked_dirty} tracked uncommitted files are included beyond '${REF}...HEAD' by \`codex exec review --base\`"
    elif [ "${untracked:-0}" -gt 0 ]; then
      scope_unpinned=1
      set_scope_reason "${untracked} untracked files are outside the diff \`codex exec review --base\` builds"
    fi ;;
  # standard:uncommitted needs no case: `codex exec review --uncommitted`
  # reviews "staged, unstaged, and untracked changes" (its own --help), which is
  # exactly the scope Step 1 resolves. Untracked files are included, so a tree
  # whose only change is a new file has a real diff and must not be refused.
esac

# --- Run under a budget -----------------------------------------------------
# macOS ships neither `timeout` nor `gtimeout`, so the budget is enforced with
# a poll-and-kill loop in pure bash.
workdir="$(mktemp -d 2>/dev/null)" || status_only "failed" "cannot create a temp dir"
raw="${workdir}/codex.out"
err="${workdir}/codex.err"

# Set once the review process is launched, cleared once it has been reaped. The
# cleanup below uses it to tell "nothing started yet / already finished" from
# "a billed run is still in flight and this script is going away".
run_active=0

# The plugin runtime scopes job lookup by CODEX_COMPANION_SESSION_ID. An ID-less
# `cancel` resolves the jobs of the current session and refuses when there is
# more than one ("Multiple Codex jobs are active") — so if the user has their own
# `/codex:*` job running when this review times out, a cancel issued under the
# shared session would fail and the billed turn would survive. Giving this run a
# session ID nobody else uses makes the ID-less cancel unambiguous: exactly one
# job carries it. The same variable is exported to the launch and to the cancel,
# and to nothing else.
review_session="bymax-review-$$-$(date +%s)"

# Stop the Codex work this script started, by the most specific means available.
#
# In adversarial mode the plugin runtime does NOT keep Codex inside this
# script's process group: it spawns an app-server broker with `detached: true`
# and `unref()`, so the group signal below cannot reach it. Measured — a review
# abandoned at the budget left `app-server-broker.mjs` and `codex app-server`
# alive and billing for 41 minutes. `cancel` is the runtime's own public remedy:
# it interrupts the Codex turn (which is what bills) and terminates that job's
# process tree, without killing the broker daemon, which is shared per workspace
# and may be serving another session's review.
#
# Three things about that cancel, each learned from a review of the previous
# version:
#   - It is bounded. It talks to the broker over a socket, and a hung broker is
#     exactly the case a timeout is handling; unbounded, it would block here
#     forever and `timeout` would never be emitted.
#   - Its exit status is not its verdict. The runtime exits 0 once it has
#     RESOLVED the job, even when the interrupt RPC failed and the turn is still
#     running. The `--json` payload's `turnInterrupted` is the fact that matters.
#   - A cancel that fails is reported, not swallowed, with the one command that
#     can still reach the run: `/codex:status` cannot show it (it filters by the
#     Claude session id, and this run carries its own), so the remedy is the
#     ID-less cancel under this run's session id.
stop_review() {
  [ "${run_active}" -eq 1 ] || return 0
  # Cleared and disarmed on ENTRY, not on exit. This runs from two places: the
  # budget path, where TERM/INT are still `exit 0`, and cleanup. A signal
  # arriving while the bounded cancel is in flight would otherwise fire the EXIT
  # trap, re-enter here with run_active still 1, issue a second cancel under the
  # same session id, and report "may still be billing" for a run the first
  # cancel had already stopped.
  run_active=0
  trap '' TERM INT
  if [ "${MODE}" = "adversarial" ] && [ -n "${companion}" ]; then
    local cancel_out="${workdir}/cancel.json" cancel_pid cancel_waited=0 was_alive=0
    # Liveness is sampled BEFORE the cancel, never after: the runtime's cancel
    # SIGTERMs the job's process tree unconditionally — and that tree is the
    # very `node … adversarial-review` process held as codex_pid — so after the
    # cancel the pid is gone whether or not the billed turn was interrupted.
    # Reading liveness afterwards made the failure branch unreachable in the
    # exact case it exists for.
    kill -0 "${codex_pid}" 2>/dev/null && was_alive=1
    CODEX_COMPANION_SESSION_ID="${review_session}" \
      node "${companion}" cancel --json >"${cancel_out}" 2>/dev/null &
    cancel_pid=$!
    while kill -0 "${cancel_pid}" 2>/dev/null; do
      if [ "${cancel_waited}" -ge "${CANCEL_DEADLINE}" ]; then
        kill -KILL "${cancel_pid}" 2>/dev/null
        break
      fi
      sleep 1
      cancel_waited=$((cancel_waited + 1))
    done
    wait "${cancel_pid}" 2>/dev/null
    if ! grep -q '"turnInterrupted": *true' "${cancel_out}" 2>/dev/null; then
      # A review that had already finished before the cancel was issued had no
      # turn to interrupt — that is not a failure. One that was alive and whose
      # interrupt was not confirmed may still be billing, and that is.
      [ "${was_alive}" -eq 1 ] && cancel_failed=1
    fi
  fi
  # No grace sleep for a pid that is already gone.
  if kill -0 "${codex_pid}" 2>/dev/null; then
    { kill -TERM -- -"${codex_pid}"
      sleep "${KILL_GRACE}"
      kill -KILL -- -"${codex_pid}"
    } >/dev/null 2>&1
  fi
  wait "${codex_pid}" >/dev/null 2>&1
  review_rc=$?
}

# The EXIT/TERM/INT traps were armed at the top of the script. From here on
# `stop_review` exists, so a teardown also stops the run. A signal is still an
# exit of this script, and the header contract — always exit 0, first line
# always CODEX_STATUS — holds for it too: the caller backgrounded this shell and
# must never see a tool failure in place of the documented degradation.

# Keep stderr: it carries the reason a run failed (rate limit, expired plan,
# blocked egress). Discarding it would leave the caller with a bare exit code,
# which is exactly the "explain why it degraded" job this script exists to do.
#
# `set -m` puts the job in its own process group (pgid == pid). Codex spawns
# child processes of its own, and signalling only the pid at budget expiry
# leaves those children running — the budget would not actually be enforced.
#
# Standard mode: the sandbox and approval policy are pinned rather than
# inherited, so a `~/.codex/config.toml` set to `workspace-write` or
# `danger-full-access` does not hand the reviewer write access; the review text
# is written by `--output-last-message`, the CLI's own way to hand back the
# final message, so no JSONL stream needs parsing.
#
# Adversarial mode: the runtime is invoked WITHOUT its `--background` flag. That
# flag is inert there anyway — `adversarial-review` always runs in the
# foreground and the openai-codex command backgrounds it from the Claude side.
# `</dev/null` on both: under `set -m` a background job keeps the script's
# stdin, and `codex exec` reads piped stdin into its prompt — an open pipe or a
# TTY would stall the run (SIGTTIN) until the budget expired.
set -m
if [ "${MODE}" = "standard" ]; then
  codex exec review "${codex_args[@]}" --ephemeral \
    -c sandbox_mode="read-only" -c approval_policy="never" \
    --output-last-message "${raw}" \
    </dev/null >/dev/null 2>"${err}" &
else
  CODEX_COMPANION_SESSION_ID="${review_session}" \
    node "${companion}" adversarial-review "${codex_args[@]}" \
    </dev/null >"${raw}" 2>"${err}" &
fi
codex_pid=$!
set +m
run_active=1

waited=0
while kill -0 "${codex_pid}" 2>/dev/null; do
  if [ "${waited}" -ge "${BUDGET}" ]; then
    # Re-check liveness before declaring a timeout: a review that finished in
    # the last poll interval is a finished review, not a timed-out one, and
    # its output must not be thrown away.
    kill -0 "${codex_pid}" 2>/dev/null || break
    stop_review
    # The review can finish in the instant between the liveness check and the
    # cancel: the runtime then reports "no active job" (read here as a failed
    # cancel) while a complete report sits in the output file. A completed
    # process with a report is a completed review, whatever the cancel said.
    if [ "${review_rc}" -eq 0 ] && [ -s "${raw}" ]; then
      cancel_failed=0
      break
    fi
    if [ "${cancel_failed}" -eq 1 ]; then
      status_only "timeout" "exceeded ${BUDGET}s${budget_note} — $(cancel_remedy)"
    fi
    status_only "timeout" "exceeded ${BUDGET}s${budget_note}"
  fi
  sleep "${POLL_INTERVAL}"
  waited=$((waited + POLL_INTERVAL))
done

# `stop_review` reaps the child itself and records its status; reaping a pid
# twice returns 127 ("no such child"), which turned a review harvested at the
# budget into `failed — exited 127`. Reap here only if nobody has yet.
if [ "${run_active}" -eq 1 ]; then
  wait "${codex_pid}" 2>/dev/null
  codex_rc=$?
  run_active=0
else
  codex_rc="${review_rc}"
fi
if [ "${codex_rc}" -ne 0 ]; then
  # Codex writes a long agent trace to stderr; only the tail carries the error.
  reason="$(tail -n 3 "${err}" 2>/dev/null | tr '\n' ' ' | cut -c1-"${REASON_MAX_CHARS}")"
  status_only "failed" "${MODE} review exited ${codex_rc}${reason:+ — ${reason}}"
fi

# --- Accept the review ------------------------------------------------------
review="$(cat "${raw}" 2>/dev/null)"
[ -n "${review}" ] || status_only "failed" "${MODE} review produced no readable output"

# Non-empty stdout is not a review. The plugin runtime exits 0 when the *turn*
# completed even if Codex returned unparseable JSON — it renders a failure page
# to stdout instead, and that page quotes the raw model output in a text fence,
# which for a review typically contains a `Verdict:` line of its own. So the
# page is rejected by its own markers first, and only then is the structure a
# real review has required: the renderer's `Target:` line, then `Verdict:`.
# Positive tests fail closed if upstream changes its format.
if [ "${MODE}" = "adversarial" ]; then
  # Anchored to the start of a line: upstream renders each failure sentence as its
  # own line, while a legitimate review can quote either phrase inside a finding
  # body — this repository's own diff contains both, so an unanchored match would
  # discard a paid review of it as a parse failure.
  if printf '%s\n' "${review}" | grep -qE '^[[:space:]]*Codex (did not return valid structured JSON|returned JSON with an unexpected review shape)'; then
    reason="$(printf '%s\n' "${review}" | grep -E 'Parse error|unexpected review shape' | head -n 1 | cut -c1-"${REASON_MAX_CHARS}")"
    status_only "failed" "adversarial review returned unparseable output — ${reason:-see the runtime failure page}"
  fi
  if ! printf '%s\n' "${review}" | grep -qE '^[[:space:]]*Target:' \
    || ! printf '%s\n' "${review}" | grep -qE '^[[:space:]]*Verdict:'; then
    reason="$(printf '%s\n' "${review}" | grep -vE '^[[:space:]]*$' | head -n 2 | tr '\n' ' ' | cut -c1-"${REASON_MAX_CHARS}")"
    status_only "failed" "adversarial review has no Target/Verdict lines — ${reason}"
  fi
fi

# Codex reports absolute paths; make them repo-relative so the findings line up
# with the rest of the report.
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "${repo_root}" ]; then
  # The left-hand side of `${var//…}` is a glob pattern, so a repo path holding
  # `*`, `?`, `[` or `\` would match the wrong thing — escape them first.
  escaped_root="$(printf '%s' "${repo_root}" | sed 's/[][*?\\]/\\&/g')"
  review="${review//${escaped_root}\//}"
fi

# A distinct status, not a note under `ok`: the caller branches on the status
# line and never on prose, so the one fact that changes how the review may be
# used has to live in the status. The review is still published — its findings
# are about this change — but its silence is not evidence.
# Marked as emitted BEFORE the exit: the EXIT trap prints a `failed` status for
# any run that reported nothing, and a success that forgot to say so was
# measured producing two status lines — `ok-unpinned`, then `failed`.
status_emitted=1
if [ "${scope_unpinned}" -eq 1 ]; then
  emit "CODEX_STATUS: ok-unpinned"
  emit "CODEX_SCOPE: ${scope_reason}"
else
  emit "CODEX_STATUS: ok"
fi
emit "${review}"
exit 0
