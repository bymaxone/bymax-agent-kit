#!/usr/bin/env python3
"""Installation diagnostics layer: report prerequisites without modifying user configuration."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def inspect(auth=False):
    """Return explicit availability and optional authentication results, never credentials."""
    checks = [{'name': 'Python >=3.10', 'ok': sys.version_info >= (3, 10)}]
    for name in ('git', 'claude', 'codex', 'gh'):
        checks.append(dict(name=name, ok=shutil.which(name) is not None))
    home = Path.home()
    for name in ('review_flow.py', 'review_push.py', 'review_prepush.py',
                 'review_delivery.py', 'review_claude.py', 'review-report.schema.json'):
        path = home / '.claude/bymax-review' / name
        source = ROOT / 'plugins/bymax-quality/scripts' / name
        checks.append(dict(name='installed ' + name, ok=path.exists() and path.read_bytes() == source.read_bytes()))
    if auth:
        for name, command in [('Claude auth', ['claude', 'auth', 'status']),
                              ('Codex auth', ['codex', 'login', 'status']),
                              ('GitHub auth', ['gh', 'auth', 'status'])]:
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                checks.append(dict(name=name, ok=result.returncode == 0))
            except (OSError, subprocess.SubprocessError):
                checks.append(dict(name=name, ok=False))
    return checks


def main():
    """Exit nonzero for an incomplete dual-review setup; optional tools are listed separately."""
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--auth', action='store_true', help='Check existing logins; may need network access.')
    args = cli.parse_args()
    checks = inspect(args.auth)
    optional = {name: shutil.which(name) is not None for name in ('shellcheck', 'jq', 'node', 'npm', 'cargo', 'xcrun', 'adb')}
    print(json.dumps(dict(dual_review=checks, optional_tools=optional), indent=2))
    return 0 if all(item['ok'] for item in checks) else 1


if __name__ == '__main__':
    sys.exit(main())
