#!/bin/bash
# qa-log-audit — search a log or captured output for a secret, DECODING common
# encodings first, and state which encodings were covered.
#
# Why this exists: grepping a log for a plaintext secret returns empty both when
# the secret is absent and when it is present but encoded (base64, URL-encoding,
# hex, JSON-escaped). A literal grep therefore certifies the exact case that
# leaks. This script decodes each line through several transforms before
# matching, and prints which transforms it applied — the ones it did not cover
# are where the next leak would hide.
#
# Usage:
#   qa-log-audit.sh <needle> <file> [<file> ...]
#   cat app.log | qa-log-audit.sh <needle> -
#
# Exit codes:
#   0  → needle NOT found in any decoding (clean, for the encodings listed)
#   1  → needle found (leak) — the matching form is printed
#   2  → NOT CHECKED — an input could not be read; not a clean scan
#   3  → usage error

set -u

if [ $# -lt 2 ]; then
  echo "usage: qa-log-audit.sh <needle> <file|-> [file ...]" >&2
  exit 3
fi

needle="$1"; shift

# The program reads data on stdin and the needle from argv[1], so stdin stays
# the data (a heredoc would be consumed as the program and read nothing — the
# false-clean this tool must never produce).
prog='
import sys, re, base64, binascii, urllib.parse
try:
    needle = sys.argv[1]
    # Decoding random high-entropy tokens (base64/hex) can, by chance, contain a
    # SHORT needle as a substring and cry a false leak. A real secret needle is
    # long, so only speculate through base64/hex when the needle is >= 6 chars.
    speculative = len(needle) >= 6
    def forms(s):
        yield ("raw", s)
        try: yield ("url", urllib.parse.unquote(s))
        except Exception: pass
        try: yield ("json-unicode", re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1),16)), s))
        except Exception: pass
        if not speculative:
            return
        for tok in re.findall(r"[A-Za-z0-9+/_-]{6,}={0,2}", s):
            # = is treated as padding only (never inside the run), so a
            # field-glued value like token=c2VjcmV0 yields the base64 part on its
            # own instead of one undecodable blob.
            t = tok.rstrip("=").replace("-", "+").replace("_", "/"); t += "=" * (-len(t) % 4)
            try:
                d = base64.b64decode(t, validate=False).decode("utf-8", "ignore")
                if d: yield ("base64", d)
            except Exception: pass
        for tok in re.findall(r"(?:[0-9a-fA-F]{2}){4,}", s):
            try:
                d = binascii.unhexlify(tok).decode("utf-8", "ignore")
                if d: yield ("hex", d)
            except Exception: pass
    hit = False
    for i, line in enumerate(sys.stdin, 1):
        for enc, dec in forms(line.rstrip("\n")):
            if needle in dec:
                # Location + encoding only, never the line content — it holds the
                # secret, and printing it would re-leak it to stdout and any
                # session log, the very thing this tool exists to check.
                print(f"LEAK line {i} via {enc}")
                hit = True; break
    # 10 = found, 0 = clean. A crash falls through to a NON-10/0 exit below, which
    # the caller reads as "could not scan" — never as a clean 0 or a found 10.
    sys.exit(10 if hit else 0)
except SystemExit:
    raise
except Exception as e:
    sys.stderr.write(f"qa-log-audit: scan error: {e}\n")
    sys.exit(3)
'

covered="raw, base64, url-encoding, hex, json-unicode-escape"
have_py=0
command -v python3 >/dev/null 2>&1 && have_py=1
[ "$have_py" -eq 0 ] && covered="raw only (python3 absent — no decoding performed)"

found=0
unreadable=0
# scan() returns three states, never collapsing an error into a verdict:
#   0 → needle not found   1 → needle found (leak)   2 → could not scan
# A tool error (grep exit >=2, a python crash) must be "could not scan", never a
# clean 0 (false-clean) or a leak 1 (false-leak) — the whole point of this tool.
scan() {
  # reads data on stdin
  if [ "$have_py" -eq 1 ]; then
    python3 -c "$prog" "$needle"
    # 0 clean · 10 found · anything else (a crash, an exit 1/2/3) → could not scan
    case $? in 0) return 0 ;; 10) return 1 ;; *) return 2 ;; esac
  else
    # `--` so a needle beginning with `-` is the pattern, not a grep flag.
    gout=$(grep -nF -- "$needle"); grc=$?
    [ "$grc" -ge 2 ] && return 2
    if [ "$grc" -eq 0 ]; then
      # line numbers only, never the matching content (it holds the secret)
      echo "LEAK (raw) at line(s): $(printf '%s' "$gout" | cut -d: -f1 | tr '\n' ' ')"
      return 1
    fi
    return 0
  fi
}

stdin_used=0
for f in "$@"; do
  if [ "$f" = "-" ]; then
    # stdin can be read once. A second `-` would read EOF and look "clean" for
    # an input never examined — the false-clean this tool exists to prevent — so
    # count it as could-not-scan instead.
    if [ "$stdin_used" -eq 1 ]; then
      echo "qa-log-audit: stdin ('-') given more than once; only the first is read" >&2
      unreadable=1
      continue
    fi
    stdin_used=1
    scan < /dev/stdin; case $? in 1) found=1 ;; 2) unreadable=1 ;; esac
  elif [ -f "$f" ] && [ -r "$f" ]; then
    scan < "$f"; case $? in 1) found=1 ;; 2) unreadable=1 ;; esac
  else
    # A missing or unreadable input must NEVER read as a clean scan — a typo'd
    # or deleted capture reporting "not found" is exactly the false-clean this
    # tool exists to prevent. It is the third result: not "clean", but "could
    # not look".
    echo "qa-log-audit: cannot read: $f" >&2
    unreadable=1
  fi
done

echo "-- coverage: decoded and searched through: ${covered}"
# A real leak outranks an unread input — a found secret is a found secret.
if [ "$found" -eq 1 ]; then
  echo "-- result: LEAK FOUND"
  exit 1
fi
if [ "$unreadable" -eq 1 ]; then
  echo "-- result: NOT CHECKED — an input could not be read; this is not a clean scan"
  exit 2
fi
echo "-- result: not found in the encodings above (absence in others is NOT proven)"
exit 0
