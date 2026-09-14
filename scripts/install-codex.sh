#!/usr/bin/env bash
# Installation entrypoint: install the isolated Codex package from any checkout path.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo 'Python 3 is required for Codex installation.' >&2; exit 1; }
exec python3 "${script_dir}/../codex/scripts/install.py" "$@"
