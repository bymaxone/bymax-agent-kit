#!/bin/bash
# QA scope guard — PreToolUse hook for bymax-qa.
#
# Enforces the audit scope while an audit is running. It is inert unless the
# audit workspace marker `.claude/qa/.active` exists in the session's working
# directory — outside an audit it never blocks anything.
#
# While active, it is a FLOOR under two boundaries the /bymax-qa:audit skill
# relies on. A floor, not a sandbox: it catches the common slip, and the skill's
# "never edit the target" discipline plus read-only finder agents are the real
# control.
#   1. A network tool (curl, wget, nc, nmap, sqlmap, nuclei, zap, ffuf, openssl
#      -connect, ssh/scp, the qa-probe wrapper, ...) invoked in command position
#      may only reach a host listed under `allowed-hosts:` in .claude/qa/scope.md.
#      A command whose host cannot be resolved from its text is blocked too —
#      an unresolvable target cannot be checked against the allow-list. It does
#      not recognise every network-capable binary (a `python3 -c` one-liner, an
#      unlisted tool); those rest on the skill's discipline. The hook inspects
#      the COMMAND, not the ambient environment: a proxy set in the environment
#      (HTTP_PROXY/HTTPS_PROXY/ALL_PROXY) is invisible here, so run probes through
#      qa-probe (which passes `--noproxy '*'`) or keep no off-scope proxy in the
#      audit environment.
#   2. A Write/Edit/MultiEdit tool call may only land inside this project's
#      .claude/qa/. It does NOT police file writes made by an arbitrary Bash
#      command (`sed -i`, a `>` redirect, `rm`) — the hook cannot parse every
#      shell write, so "never edit the target" is enforced by the skill, and
#      this rule stops the common tool-based slip.
#
# Exit codes:
#   0  → allow (not active, or allowed)
#   2  → block — Claude Code surfaces the JSON systemMessage to the user
#
# To disable, remove .claude/qa/.active (the skill does this when a run ends) or
# comment out the hook entry in the plugin's hooks.json.

set -u

input=$(cat)

# Resolve the session working directory the tool will act in.
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
[ -z "$cwd" ] && cwd="$PWD"

marker="$cwd/.claude/qa/.active"
scope="$cwd/.claude/qa/scope.md"

# Not in an active audit → this hook does nothing.
[ -f "$marker" ] || exit 0

# The guard parses its input with jq. Without jq it cannot read the tool name or
# the command, and falling through would make the control a silent no-op (fail
# open). While an audit is active, a missing jq fails CLOSED instead.
if ! command -v jq >/dev/null 2>&1; then
  printf '%s\n' "🛡️ BLOCKED by qa-guard: jq is required to enforce the audit scope and is not installed. Install jq, or end the audit by removing .claude/qa/.active." >&2
  exit 2
fi

tool=$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null)

block() {
  # $1 = message shown to the user. Emit the current PreToolUse deny shape
  # (hookSpecificOutput.permissionDecision) AND the legacy decision field for
  # older hosts, on stdout; the same text on stderr so the reason is never lost;
  # and exit 2, the authoritative deny under the hook protocol.
  jq -nc --arg msg "$1" '{
    hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $msg },
    systemMessage: $msg,
    decision: "block"
  }'
  printf '%s\n' "$1" >&2
  exit 2
}

case "$tool" in
  Write | Edit | MultiEdit | NotebookEdit)
    file=$(printf '%s' "$input" | jq -r '
      .tool_input.file_path // .tool_input.notebook_path // .tool_input.path // .tool_input.target_file // empty
    ' 2>/dev/null)
    [ -z "$file" ] && exit 0

    # Normalise to an absolute path so a relative target is judged correctly.
    case "$file" in
      /*) abs="$file" ;;
      *)  abs="$cwd/$file" ;;
    esac

    # A `..` component defeats the substring check below — `.claude/qa/../../x`
    # contains `/.claude/qa/` yet resolves outside it. Nothing legitimate under
    # the QA workspace needs to traverse upward, so refuse any `..` outright
    # (simpler and dependency-free versus resolving the path, and the workspace
    # is auditor-created, so a malicious symlink is not the threat here).
    case "$abs" in
      *"/../"* | */..) block "🛡️ BLOCKED by qa-guard: path traversal in a write target (${file}). Writes during an audit stay inside .claude/qa/ with no '..' — name the file by its real path under the workspace." ;;
    esac

    # Anchor to THIS project's workspace, `$cwd/.claude/qa/`, not any path that
    # merely contains `/.claude/qa/` (a bare substring test would allow
    # `/tmp/.claude/qa/x` or another project's workspace).
    qa_dir="$cwd/.claude/qa/"
    case "$abs" in
      "$qa_dir"*) : ;;
      *) block "🛡️ BLOCKED by qa-guard: an audit is active (.claude/qa/.active present), so writes are confined to ${qa_dir}. Refused a write to ${file}. The auditor never edits the target — hand the fix to the owning agent or file an issue. End the run to lift this." ;;
    esac
    # Lexical prefix is not enough: a symlink under .claude/qa (in the untrusted
    # audited repo) could point outside it — a directory symlink in the path OR
    # the write target itself being a symlink file. Resolve where the write
    # actually lands, physically, and confirm it stays under the workspace root.
    if [ -d "${qa_dir%/}" ]; then
      qa_phys=$(cd "${qa_dir%/}" 2>/dev/null && pwd -P)
      # .claude/qa (or .claude) may itself be a symlink pointing into the
      # source tree; then qa_phys is that target and every "descendant" check
      # trusts it. Require the physical workspace to be the canonical
      # <project>/.claude/qa, so a symlinked root is refused outright.
      cwd_phys=$(cd "$cwd" 2>/dev/null && pwd -P)
      if [ -z "$cwd_phys" ] || [ "$qa_phys" != "$cwd_phys/.claude/qa" ]; then
        block "🛡️ BLOCKED by qa-guard: .claude/qa is not a real directory at ${cwd}/.claude/qa (a symlinked workspace root?). The auditor writes only inside the canonical workspace, never a link into the source tree."
      fi
      # If the target is itself a symlink, follow the WHOLE chain
      # (a -> b -> /tmp/escaped) to where the write ultimately lands — bounded to
      # break a cycle. Then take the deepest existing DIRECTORY of that path (a
      # file is not cd-able), resolve it physically, and re-append the leaf name.
      resolved="$abs"; links=0
      while [ -L "$resolved" ] && [ "$links" -lt 40 ]; do
        lt=$(readlink "$resolved")
        case "$lt" in /*) resolved="$lt" ;; *) resolved="$(dirname "$resolved")/$lt" ;; esac
        links=$((links + 1))
      done
      leaf=$(basename "$resolved")
      rdir=$(dirname "$resolved")
      while [ -n "$rdir" ] && [ ! -d "$rdir" ]; do rdir=$(dirname "$rdir"); done
      rdir_phys=$(cd "$rdir" 2>/dev/null && pwd -P)
      if [ -n "$qa_phys" ] && [ -n "$rdir_phys" ]; then
        case "${rdir_phys}/${leaf}/" in
          "$qa_phys"/*) : ;;
          *) block "🛡️ BLOCKED by qa-guard: ${file} resolves outside ${qa_dir} (a symlink in .claude/qa?). The auditor never writes outside the workspace." ;;
        esac
      fi
    fi
    exit 0
    ;;

  Bash)
    cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)
    [ -z "$cmd" ] && exit 0

    # Strip shell comments before any detection, so a URL or a tool name in a
    # comment (`gh api https://… # run instead of curl`) is not read as a probe.
    # Quote-aware: a `#` inside a quoted argument (`-d 'note=a # b'`) or glued to
    # a token (a URL fragment `…#frag`) is NOT a comment and is preserved; only a
    # `#` at a word boundary OUTSIDE quotes ends its line. The whole command is
    # accumulated and walked in one pass (`buf`/END) so quote state holds ACROSS
    # newlines: a `#` inside a quoted string that spans lines stays quoted and
    # does not end a line, so a `; curl …` after it stays visible.
    cmd=$(printf '%s' "$cmd" | awk '
      { buf = buf $0 "\n" }
      END {
        out=""; inq=0; q=""; n=length(buf)
        for (i = 1; i <= n; i++) {
          c = substr(buf, i, 1)
          if (inq) { out = out c; if (c == q) inq = 0; continue }
          if (c == "\047" || c == "\"") { inq = 1; q = c; out = out c; continue }
          if (c == "#") {
            p = (i == 1) ? " " : substr(buf, i - 1, 1)
            if (p == " " || p == "\t" || p == "\n") {
              while (i <= n && substr(buf, i, 1) != "\n") i++
              out = out "\n"; continue
            }
          }
          out = out c
        }
        print out
      }')

    # Does the command INVOKE a network tool in command position, not merely
    # mention one as an argument (`grep curl helper.ts` must not trip)? Rather
    # than pattern-match every shell prefix, normalise: split on the operators
    # that begin a new simple command (| & ; ( ) { } and backtick), strip a
    # leading keyword (then/do/else/in/elif/!) and any leading VAR=val
    # assignments, then a tool at the start of a resulting line is in command
    # position. This catches `FOO=bar curl …`, `… ; then curl …`, `{ curl …}`
    # and `echo \`curl …\`` that a start-or-operator regex missed. It remains a
    # FLOOR: it covers the common network binaries and the qa-probe wrapper, not
    # every way a process can reach the network (a `python3 -c`/`node -e`
    # one-liner, an unlisted binary, an obfuscated invocation). The scope
    # discipline and the auditor's own "never probe out of scope" rule are the
    # real control; this stops the common accidental out-of-scope probe.
    # A header, referer, or request-BODY flag can carry a URL that is NOT a probe
    # target — the untrusted Origin of a CORS test, the callback URL of an SSRF
    # test, a `-L` token inside POST data. Strip those flag values first, so the
    # destination is all that the URL signal, the redirect check, and host
    # extraction below ever read. `hf` is that flag set.
    hf='-H|--header|-e|--referer|--referrer|-d|--data|--data-raw|--data-binary|--data-ascii|--data-urlencode|-F|--form|--form-string|-o|--output|-D|--dump-header|-c|--cookie-jar|-b|--cookie|-w|--write-out|-A|--user-agent|-X|--request'
    dest=$(printf '%s' "$cmd" | sed -E \
      -e "s/(^|[[:space:]])($hf)[[:space:]]+'[^']*'/ /g" \
      -e "s/(^|[[:space:]])($hf)[[:space:]]+\"[^\"]*\"/ /g" \
      -e "s/(^|[[:space:]])($hf)[[:space:]]+[^[:space:]]+/ /g")

    # The wrapper-proof signal is: a URL-fetching tool WORD appears in the command
    # (curl/wget/httpie/…, even behind `sudo -u x`, `env A=b`, a path) AND a
    # destination URL is present. Requiring the tool word is what stops a URL in a
    # non-probe command — `gh api https://…`, `git fetch https://…`, `echo <url>`,
    # the skill's own `gh issue create` hand-off — from being read as a probe.
    # `http`/`https` are excluded here on purpose: they appear in every
    # https?:// URL, so including them would make tool_word true for any URL and
    # re-block gh/git/echo. HTTPie at a command start is still caught by the
    # command-position detection below; behind a wrapper it is an exotic floor case.
    # Match the tool name only OUTSIDE quoted strings, so `grep 'curl https://x'
    # file` (curl as a search pattern) does not trip it. A wrapped real probe
    # keeps its tool word unquoted, so it still matches.
    unquoted=$(printf '%s' "$cmd" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")
    tool_word=0
    printf '%s' "$unquoted" | grep -qE '(^|[^A-Za-z0-9_-])(curl|wget|wget2|httpie|xh|xhs|httpx|sqlmap|nuclei|zap|zaproxy|ffuf|wfuzz)([^A-Za-z0-9_-]|$)' && tool_word=1
    has_url=0
    [ "$tool_word" -eq 1 ] && printf '%s' "$dest" | grep -qE 'https?://[^/?#[:space:]"'"'"']' && has_url=1

    # Command-position detection additionally covers the host-argument and ssh
    # tools that carry a bare host, not a URL. Split into simple commands, strip
    # a leading keyword and env assignments and a leading path, then match the
    # tool at a line start. It is a FLOOR: a host-argument tool hidden behind a
    # wrapper's own options and carrying no URL (an exotic, off-by-default case)
    # is not caught — the scope discipline is the real control.
    # The split is QUOTE-AWARE: an operator inside a quoted argument
    # (`printf '%s' 'curl http://x; y'`) is literal and must not begin a new
    # segment. It walks the string tracking quote state — single-quoted text is
    # literal and never splits; inside double quotes only command substitution
    # (`$(...)`, backticks) begins a new command while `; | & { }` stay literal;
    # the quote delimiters are dropped so a quoted command path
    # (`"/usr/bin/curl"`, a bare `"curl"`) resolves to its real tool token.
    starts=$(printf '%s' "$cmd" \
      | awk '
          { buf = buf $0 "\n" }
          END {
            # A stack-based tokenizer: each command substitution ($(...) or a
            # backtick pair) is its own context with independent quote state, so
            # a quote INSIDE $(...) does not toggle the OUTER quote. ctype
            # stacks each level close-type (p = $() closed by ), b = backtick).
            # A separator ( | & ; ( ) { } backtick newline ) OUTSIDE quotes
            # begins a new simple command; single quotes are fully literal.
            ctype=""; depth=0; qs[0]=0; out=""; n=length(buf)
            for (i=1; i<=n; i++) {
              c=substr(buf,i,1); s=qs[depth]
              if (s == 1) {
                if (c == "\047") { qs[depth]=0 }
                else if (c == "\n") { out = out " " }
                else { out = out c }
                continue
              }
              # Backslash escaping (not inside single quotes, where it is literal):
              # a `\"` inside double quotes is literal and does not close the quote,
              # and a `\;` is a literal semicolon that does not split — so an escaped
              # quote cannot conceal a following command from detection. Branches are
              # kept flat (guard clauses) to stay within the nesting ceiling.
              if (c == "\\" && i >= n) { out = out c; continue }
              if (c == "\\") {
                nc = substr(buf, i + 1, 1)
                if (s == 2 && (nc == "\"" || nc == "\\" || nc == "$" || nc == "\140")) { out = out nc; i++; continue }
                if (s == 2) { out = out c; continue }
                if (nc == "\n") { i++; continue }
                out = out nc; i++; continue
              }
              if (c == "\047" && s == 0) { qs[depth]=1; continue }
              if (c == "\"") { qs[depth] = (s == 2) ? 0 : 2; continue }
              if (c == "$" && i < n && substr(buf,i+1,1) == "(") { out = out "\n"; i++; depth++; qs[depth]=0; ctype = ctype "p"; continue }
              if (c == "\140") {
                if (depth > 0 && substr(ctype,depth,1) == "b") { depth--; ctype = substr(ctype,1,depth); out = out "\n"; continue }
                else { out = out "\n"; depth++; qs[depth]=0; ctype = ctype "b"; continue }
              }
              if (s == 2) { if (c == "\n") { out = out " " } else { out = out c }; continue }
              if (c == ")") { if (depth > 0 && substr(ctype,depth,1) == "p") { depth--; ctype = substr(ctype,1,depth) } out = out "\n"; continue }
              if (c == "|" || c == "&" || c == ";" || c == "(" || c == "{" || c == "}" || c == "\n") { out = out "\n"; continue }
              out = out c
            }
            print out
          }')
    # Strip a leading keyword, env-assignments, wrappers and a timeout to a FIXED
    # POINT: `env A=b nmap` needs the env wrapper removed AND then the `A=b`
    # assignment removed, in an order one pass cannot know. Loop until the line
    # stops shrinking (bounded — it only ever shortens).
    _sp=0
    while [ "$_sp" -lt 20 ]; do
      _stripped=$(printf '%s' "$starts" \
        | sed -E 's/^[[:space:]]*(if|then|elif|else|while|until|do|in|!)[[:space:]]+//' \
        | sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)+//' \
        | sed -E 's#^[[:space:]]*(command|env|exec|nice|nohup|time|stdbuf|xargs|sudo|doas|proxychains|proxychains4|torify|torsocks|unbuffer)[[:space:]]+##' \
        | sed -E 's#^[[:space:]]*timeout[[:space:]]+[0-9]+[smhd.]*[[:space:]]+##')
      [ "$_stripped" = "$starts" ] && break
      starts="$_stripped"; _sp=$((_sp + 1))
    done
    # `([^[:space:]]*/)?` before the name matches an absolute or relative path
    # (`/usr/bin/curl`, `./curl`) as the same tool, without matching `mycurl`.
    starts_with() { printf '%s' "$starts" | grep -qE "^[[:space:]]*([^[:space:]]*/)?($1)([[:space:]]|$)"; }
    is_url=0; is_ssh=0; is_ossl=0; is_hostarg=0; is_probe=0; is_wget=0; is_httpie=0
    starts_with 'curl|wget|wget2|httpie|http|https|xh|xhs|httpx|sqlmap|nuclei|zap|zaproxy|ffuf|wfuzz' && is_url=1
    starts_with 'wget|wget2' && is_wget=1
    # HTTPie-family clients accept a scheme-less, default-port target
    # (`http GET host/path`), extracted specially below.
    starts_with 'httpie|http|https|xh|xhs|httpx' && is_httpie=1
    starts_with 'ssh|scp|sftp' && is_ssh=1
    starts_with 'openssl' && printf '%s' "$cmd" | grep -qE -- '-connect[[:space:]]' && is_ossl=1
    starts_with 'nc|ncat|nmap|masscan|hydra|nikto|telnet|socat' && is_hostarg=1
    # qa-probe wrapper: as the command start (path-prefixed), or run via a shell
    # (`bash …/qa-probe.sh`). NOT a mere mention (`grep qa-probe README.md`).
    starts_with 'qa-probe(\.sh)?' && is_probe=1
    # Run via a shell, path possibly quoted (`bash "…/qa-probe.sh"`): allow an
    # optional quote before the path and after the name so the closing quote
    # does not defeat the boundary.
    printf '%s' "$cmd" | grep -qE '(bash|sh|zsh|dash)[[:space:]]+["'\'']?([^[:space:]"'\'']*/)?qa-probe(\.sh)?(["'\'']|[[:space:]]|$)' && is_probe=1

    # Fail closed on an unparsed wrapper. A wrapper's own OPTIONS (`sudo -u root
    # nmap`, `nice -n 10 wget`) cannot be consumed generically — their arity is
    # unknown — so after the strip a line may still begin with an option. When it
    # does AND the command names any network tool, the target cannot be resolved:
    # refuse it rather than let a bare-host probe (nmap/nc) or a redirect-following
    # wget slip through undetected. A non-network wrapped command (`sudo -n ls`)
    # names no tool and is unaffected.
    net_word='(^|[^A-Za-z0-9_-])(curl|wget|wget2|httpie|xh|xhs|httpx|sqlmap|nuclei|zap|zaproxy|ffuf|wfuzz|nc|ncat|nmap|masscan|hydra|nikto|telnet|socat|ssh|scp|sftp|openssl)([^A-Za-z0-9_-]|$)'
    if printf '%s' "$starts" | grep -qE '^[[:space:]]*-' \
       && printf '%s' "$unquoted" | grep -qE "$net_word"; then
      block "🛡️ BLOCKED by qa-guard: a network tool appears to run behind a wrapper whose options could not be parsed (e.g. 'sudo -u user nmap host'). Run it without the wrapper, or name the target explicitly so the scope can be checked."
    fi

    [ $((is_url + is_ssh + is_ossl + is_hostarg + is_probe + has_url)) -eq 0 ] && exit 0

    # The redirect and destination-override checks below test whether a shell
    # WORD is a dangerous flag, so split the destination into shell words the way
    # bash would: on UNQUOTED whitespace only, quotes removed and their content
    # kept within one word. A flag name inside a quoted value
    # (`-o "report --proxy copy"`) then stays one word and is not mistaken for a
    # flag, while a quoted flag (`"--socks5"`) resolves to the bare option.
    shell_words() {
      awk '
        { buf = buf $0 "\n" }
        END {
          n = length(buf); s = 0; w = ""; started = 0
          for (i = 1; i <= n; i++) {
            c = substr(buf, i, 1)
            if (s != 1 && c == "\\") { if (i < n) { i++; nc = substr(buf, i, 1); if (nc != "\n") { w = w nc; started = 1 } } else { w = w c; started = 1 }; continue }
            if (s == 1) { if (c == "\047") { s = 0 } else if (c == "\n") { w = w " "; started = 1 } else { w = w c; started = 1 }; continue }
            if (s == 2) { if (c == "\042") { s = 0 } else if (c == "\n") { w = w " "; started = 1 } else { w = w c; started = 1 }; continue }
            if (c == "$" && i < n && (substr(buf, i + 1, 1) == "\047" || substr(buf, i + 1, 1) == "\042")) { started = 1; continue }
            if (c == "\047") { s = 1; started = 1; continue }
            if (c == "\042") { s = 2; started = 1; continue }
            if (c == " " || c == "\t" || c == "\n" || c == ">" || c == "<" || c == "|" || c == "&" || c == ";" || c == "(" || c == ")" || c == "{" || c == "}" || c == "\140") { if (started) { print w; w = ""; started = 0 }; continue }
            w = w c; started = 1
          }
          if (started) { print w }
        }'
    }
    dest_words=$(printf '%s' "$dest" | shell_words)

    # Redirect following escapes the allow-list: an allowed host can 30x to an
    # unlisted one, which only the client sees at runtime. Refuse `-L` in any
    # form — standalone, bundled in a short-flag cluster (`-sL`), or
    # `--location`/`--location-trusted` — on a URL tool OR through the qa-probe
    # wrapper (which forwards its args to curl). Refuse `wget` (which follows by
    # default) unless it disables redirects with `--max-redirect=0`.
    if { [ "$is_url" -eq 1 ] || [ "$is_probe" -eq 1 ] || [ "$has_url" -eq 1 ]; } \
       && printf '%s' "$dest_words" | grep -qE -- '^(-[A-Za-z]*L[A-Za-z]*|--location(-trusted)?)(=|$)'; then
      block "🛡️ BLOCKED by qa-guard: redirect following (-L / --location) can leave the allow-list — an allowed host may redirect to an unlisted one. Probe without -L, or follow the redirect target explicitly after checking it against the scope."
    fi
    if [ "$is_wget" -eq 1 ] && ! printf '%s' "$cmd" | grep -qE -- '--max-redirect[[:space:]=]0([[:space:]]|$)'; then
      block "🛡️ BLOCKED by qa-guard: wget follows redirects by default, which can leave the allow-list. Re-run it with --max-redirect=0, or use qa-probe / curl (no -L)."
    fi
    # Destination-override options connect somewhere other than the URL host the
    # allow-list check validates: --connect-to and --resolve remap the target, a
    # proxy (`-x`, bundled `-sx` or glued `-xhost`) routes through another host,
    # and a config file (`-K`) can name a whole different url the guard never
    # sees. Refuse them — the host check would pass while the real connection
    # leaves the scope.
    if { [ "$is_url" -eq 1 ] || [ "$is_probe" -eq 1 ] || [ "$has_url" -eq 1 ]; } \
       && printf '%s' "$dest_words" | grep -qE -- '^(--connect-to|--resolve|--proxy|--preproxy|--proxy1\.0|--socks[0-9a-z-]*|--config|--unix-socket|--abstract-unix-socket)(=|$)|^-[A-Za-z]*[xK]'; then
      block "🛡️ BLOCKED by qa-guard: a destination-override option (--connect-to / --resolve / --proxy / -x / -K config) can send the request to a host the URL does not name and the allow-list never sees. Remove it, or name the real target so it can be checked against the scope."
    fi

    # Read the allow-list from scope.md: hosts under the `allowed-hosts:` line,
    # one `- host` per line, until the next non-list line.
    allowed=""
    if [ -f "$scope" ]; then
      # Grab `- host` items under `allowed-hosts:`. The block ends only at the
      # next top-level key (a line starting in column 0), so a blank line or a
      # stray indented line between the header and the items does not silently
      # truncate the list. `tr -d '\r'` tolerates a CRLF-saved scope.md, whose
      # trailing carriage return would otherwise make `localhost` never match.
      allowed=$(awk '
        /^allowed-hosts:/ { grab=1; next }
        grab && /^[[:space:]]*-[[:space:]]*/ { sub(/^[[:space:]]*-[[:space:]]*/,""); print $1; next }
        grab && /^[^[:space:]]/ { grab=0 }
      ' "$scope" | tr -d '\r')
    fi

    if [ -z "$allowed" ]; then
      block "🛡️ BLOCKED by qa-guard: a network probe was attempted but .claude/qa/scope.md lists no allowed-hosts. Add the authorized hosts to the scope before probing."
    fi

    # Extract candidate hosts by tool class, so a port, a JSON/header value, or
    # a flag's argument is never mistaken for a host:
    #   URL tools + the probe wrapper → the host inside an https?:// URL only
    #                                   (a bare `word:digits` is never a host, so
    #                                   a JSON/header value like `"12:30"` is not
    #                                   read as one)
    #   ssh/scp/sftp                  → the host in a `user@host` target
    #   openssl                       → the host in `-connect host:port`
    #   nc/nmap/telnet/socat/...      → positional tokens shaped like an FQDN,
    #                                   an IPv4, or `localhost` (a bare port such
    #                                   as the `80` in `nmap -p 80 host` is not
    #                                   FQDN/IP-shaped, so it is not taken)
    host_shape='^(localhost|([0-9]{1,3}\.){3}[0-9]{1,3}|([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z][A-Za-z0-9-]*)$'

    # For host extraction, model shell quote concatenation with a plain quote
    # strip: `http://localhost".evil"/` becomes the host `localhost.evil`. A flag
    # substring inside a value is harmless here — every extracted token must be
    # FQDN/IP/localhost-shaped. (`cmd` is stripped after the tokenizer, which
    # needs the quotes.)
    dest=$(printf '%s' "$dest" | tr -d '\042\047')
    cmd=$(printf '%s' "$cmd" | tr -d '\042\047')

    hosts=$(
      {
        if [ "$is_url" -eq 1 ] || [ "$is_probe" -eq 1 ] || [ "$has_url" -eq 1 ]; then
          # Host ends at the first / ? # space or quote, so a query or fragment
          # on a path-less URL (http://host:3000?x) does not glue to the host.
          # Strip any `user[:pass]@` userinfo and the port so `http://u@host:80`
          # resolves to `host`. Read from $dest (header values removed).
          printf '%s' "$dest" | grep -oE 'https?://[^/?#[:space:]"'"'"']+' \
            | sed -E 's#^https?://##; s#^[^/@]*@##; s#:[0-9]+$##'
          # Scheme-less `host:port[/path]` — curl accepts it and HTTPie's normal
          # syntax (`http GET localhost:3000/api`) requires it. Take only tokens
          # whose host part is FQDN/IP/localhost-shaped, so a `word:digits` value
          # is not mistaken for one.
          printf '%s' "$dest" \
            | grep -oE '(^|[[:space:]])[A-Za-z0-9.-]+:[0-9]{2,5}([/[:space:]]|$)' \
            | grep -oE '[A-Za-z0-9.-]+:[0-9]{2,5}' | sed -E 's/:[0-9]+$//' \
            | grep -E "$host_shape"
        fi
        if [ "$is_httpie" -eq 1 ]; then
          # HTTPie default-port form has neither scheme nor port: `http GET
          # host/path`. Take non-flag tokens, drop any `/path` and `:port`, and
          # keep only FQDN/IP/localhost-shaped hosts (so `GET` and a filename are
          # not mistaken for one). Gated to HTTPie so a curl `-o out.txt` value
          # is not read as a host. Not parsed (fail-closed — write the host
          # explicitly, or use curl): HTTPie's implicit-localhost shorthands
          # (`http :3000/x`, `http GET /x`) and URLs inside `key==value` items.
          printf '%s' "$dest" | tr ' \t' '\n' | grep -vE '^-' \
            | sed -E 's#[/?#].*$##; s#:[0-9]+$##; s#^[^/@]*@##' | grep -E "$host_shape"
        fi
        if [ "$is_ssh" -eq 1 ]; then
          # user@host (ssh/scp), and the bare forms: `ssh host` and scp's
          # `host:/path`. Drop a `:path`, keep FQDN/IP/localhost-shaped tokens,
          # and exclude filenames so `scp config.json host:/tmp` reads `host`,
          # not `config.json`.
          printf '%s' "$cmd" | grep -oE '[A-Za-z0-9._-]+@[A-Za-z0-9.-]+' | sed -E 's/^.*@//'
          printf '%s' "$dest" | tr ' \t' '\n' | grep -vE '^-' \
            | sed -E 's#:.*$##; s#^[^/@]*@##' \
            | grep -E "$host_shape" \
            | grep -viE '\.(html?|txt|json|xml|csv|log|md|ya?ml|out|conf|cfg|ini|pem|key|crt|cer|csr|der|sh|py|js|ts|db|sqlite|rb|pl|php|go|rs|so|dll|env|lock|tmp|bak|zip|tar|gz|tgz)$'
        fi
        if [ "$is_ossl" -eq 1 ]; then
          printf '%s' "$cmd" | grep -oE -- '-connect[[:space:]]+[A-Za-z0-9._-]+' | sed -E 's/^-connect[[:space:]]+//; s/:[0-9]+$//'
        fi
        if [ "$is_hostarg" -eq 1 ]; then
          # A dotted output filename (report.html, payloads.txt) is FQDN-shaped;
          # drop tokens with a common file extension so `-o report.html` is not
          # taken as a target host and made to block an in-scope command.
          printf '%s' "$cmd" | tr ' \t' '\n' | grep -vE '^-' \
            | grep -E "$host_shape" \
            | grep -viE '\.(html?|txt|json|xml|csv|log|md|ya?ml|out|nmap|gnmap|conf|cfg|ini|pem|key|crt|cer|csr|der|sh|py|js|ts|db|sqlite|nse|lua|rb|pl|php|go|rs|so|dll|env|lock|tmp|bak)$'
        fi
      } | grep -v '^$' | sort -u
    )

    if [ -z "$hosts" ]; then
      block "🛡️ BLOCKED by qa-guard: a network tool was invoked but its target host could not be read from the command. Write the host literally (e.g. http://localhost:3000/... , user@host, or a bare hostname/IP) so it can be checked against the scope's allowed-hosts."
    fi

    # Every extracted host must be on the allow-list. Hostnames are
    # case-insensitive, so compare lower-cased on both sides. Extracted hosts
    # have their port stripped, so strip a `:port` on the allow-list entries too
    # — an auditor who writes `- localhost:3000` (matching base-url) still
    # matches a probe to `localhost`.
    allowed_lc=$(printf '%s' "$allowed" | tr '[:upper:]' '[:lower:]' | sed -E 's/:[0-9]+$//')
    while IFS= read -r h; do
      [ -z "$h" ] && continue
      h=$(printf '%s' "$h" | tr '[:upper:]' '[:lower:]')
      found=0
      while IFS= read -r a; do
        [ "$h" = "$a" ] && { found=1; break; }
      done <<EOF
$allowed_lc
EOF
      if [ "$found" -eq 0 ]; then
        block "🛡️ BLOCKED by qa-guard: host '${h}' is not in .claude/qa/scope.md allowed-hosts. Testing is authorized only against the listed hosts; production is never in scope. Add the host to the scope (with the human's approval) or fix the target."
      fi
    done <<EOF
$hosts
EOF
    exit 0
    ;;

  *)
    exit 0
    ;;
esac
