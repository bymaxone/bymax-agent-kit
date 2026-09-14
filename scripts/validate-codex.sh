#!/usr/bin/env bash
# Validation entrypoint: check the Codex package and its behavioral regression tests.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"
python3 codex/scripts/validate.py
python3 -m unittest discover -s codex/tests -v
