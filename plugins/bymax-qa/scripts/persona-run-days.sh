#!/usr/bin/env bash
# Run a persona's day flows one at a time, strictly in file order.
#
# Layer: plugin helper script of /bymax-qa:personas (scripted days of a mobile
# run). One `maestro test` per day keeps the pinned clock moving forward; a
# folder run does not keep the order. After each day the screenshots it took are
# copied into <flows-dir>/shots/ and a line is appended to <flows-dir>/run-log.tsv.
# The run stops at the first failed day, so a missing button is looked at, not
# skipped.
#
# Usage: persona-run-days.sh <flows-dir> [first-day] [last-day]
# Env:   MAESTRO             the command to run (default: maestro), e.g. "bash scripts/maestro.sh"
#        PERSONA_DEVICE      passed as --device before `test`
#        PERSONA_BEFORE_DAY  a command run before each day with PERSONA_DAY set;
#                            a non-zero exit stops the run
set -u

dir=${1:-}
first=${2:-1}
last=${3:-999999}
if [ -z "$dir" ] || [ ! -d "$dir" ]; then
  echo "usage: persona-run-days.sh <flows-dir> [first-day] [last-day]" >&2
  exit 2
fi
case "$first$last" in
  *[!0-9]*) echo "first-day and last-day must be numbers" >&2; exit 2 ;;
esac

read -r -a maestro <<< "${MAESTRO:-maestro}"
device=()
[ -n "${PERSONA_DEVICE:-}" ] && device=(--device "$PERSONA_DEVICE")
dir=$(cd "$dir" && pwd)
mkdir -p "$dir/shots"

# The day list is read on fd 3 and every child gets /dev/null as stdin: a hook or a
# maestro wrapper that reads stdin (`adb shell` does) would otherwise eat the list, and
# the run would end early with exit 0.

# Copy every PNG written since the marker, from the flows folder and Maestro's
# own output tree, into shots/.
collect_shots() {
  local marker=$1
  find "$dir" -maxdepth 1 -name '*.png' -newer "$marker" -exec mv {} "$dir/shots/" \;
  if [ -d "$HOME/.maestro/tests" ]; then
    find "$HOME/.maestro/tests" -name '*.png' -newer "$marker" -exec cp {} "$dir/shots/" \;
  fi
}

ran=0
while IFS= read -r flow <&3; do
  name=$(basename "$flow" .yaml)
  day=$(printf '%s' "$name" | sed -E 's/.*-0*([0-9]+)$/\1/')
  case "$day" in ''|*[!0-9]*) continue ;; esac
  [ "$day" -lt "$first" ] && continue
  [ "$day" -gt "$last" ] && break
  if [ -n "${PERSONA_BEFORE_DAY:-}" ]; then
    if ! PERSONA_DAY=$day bash -c "$PERSONA_BEFORE_DAY" < /dev/null 3<&-; then
      echo "day $day: PERSONA_BEFORE_DAY failed"
      exit 1
    fi
  fi
  marker=$(mktemp)
  sleep 1
  out=$(cd "$dir" && "${maestro[@]}" ${device[@]+"${device[@]}"} test "$flow" < /dev/null 3<&- 2>&1)
  rc=$?
  collect_shots "$marker"
  rm -f "$marker"
  printf '%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$day" "$name" "$rc" >> "$dir/run-log.tsv"
  if [ "$rc" -ne 0 ] || printf '%s' "$out" | grep -q 'FAILED'; then
    echo "day $day FAILED (exit $rc)"
    printf '%s\n' "$out" | tail -n 15
    exit 1
  fi
  echo "day $day ok"
  ran=$((ran + 1))
done 3< <(find "$dir" -maxdepth 1 -name '*.yaml' | LC_ALL=C sort)

echo "$ran day(s) ran; screenshots in $dir/shots"
